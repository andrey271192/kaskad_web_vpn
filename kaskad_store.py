"""Хранение правил NAT и синхронизация с iptables (chain в table nat)."""
from __future__ import annotations

import ipaddress
import json
import logging
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

RULES_PATH = Path(os.environ.get("KASKAD_RULES_PATH", "/var/lib/kaskad/rules.json"))
CHAIN = os.environ.get("KASKAD_NAT_CHAIN", "KASKAD_WEB").strip() or "KASKAD_WEB"
_PROTO_OK = frozenset({"tcp", "udp"})


def _iptables_bin() -> str | None:
    for name in ("iptables", "iptables-nft", "iptables-legacy"):
        p = shutil.which(name)
        if p:
            return p
    return None


def ensure_state_dir() -> None:
    RULES_PATH.parent.mkdir(parents=True, exist_ok=True)


def load_rules() -> list[dict[str, Any]]:
    ensure_state_dir()
    if not RULES_PATH.is_file():
        return []
    try:
        raw = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        log.warning("rules read failed: %s", e)
        return []
    rules = raw.get("rules") if isinstance(raw, dict) else raw
    if not isinstance(rules, list):
        return []
    out: list[dict[str, Any]] = []
    for r in rules:
        if isinstance(r, dict) and r.get("id"):
            out.append(r)
    return out


def save_rules(rules: list[dict[str, Any]]) -> None:
    ensure_state_dir()
    tmp = RULES_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps({"rules": rules}, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(RULES_PATH)


def _validate_rule(r: dict[str, Any]) -> None:
    proto = str(r.get("proto", "")).lower().strip()
    if proto not in _PROTO_OK:
        raise ValueError("proto должен быть tcp или udp")
    ipaddress.IPv4Address(str(r.get("target", "")))
    for key in ("in_port", "out_port"):
        p = int(r[key])
        if not (1 <= p <= 65535):
            raise ValueError(f"порт {key} вне диапазона")
    user = str(r.get("user", "")).strip()
    if not user or len(user) > 64:
        raise ValueError("USER: 1–64 символа")
    if any(ord(c) < 32 for c in user):
        raise ValueError("USER: недопустимые символы")
    note = str(r.get("note", ""))
    where = str(r.get("where", ""))
    if len(note) > 256 or len(where) > 256:
        raise ValueError("заметка / где — не длиннее 256 символов")


def normalize_rule(body: dict[str, Any], rid: str | None = None) -> dict[str, Any]:
    try:
        in_p = int(body.get("in_port"))
        out_p = int(body.get("out_port"))
    except (TypeError, ValueError):
        raise ValueError("in_port и out_port должны быть целыми числами") from None
    r = {
        "id": rid or uuid.uuid4().hex[:16],
        "user": str(body.get("user", "")).strip(),
        "proto": str(body.get("proto", "udp")).lower().strip(),
        "in_port": in_p,
        "target": str(body.get("target", "")).strip(),
        "out_port": out_p,
        "note": str(body.get("note", "")).strip(),
        "where": str(body.get("where", "")).strip(),
    }
    _validate_rule(r)
    return r


def _run_iptables(args: list[str]) -> tuple[int, str]:
    exe = _iptables_bin()
    if not exe:
        return 127, "iptables не найден в PATH"
    try:
        p = subprocess.run(
            [exe, *args],
            capture_output=True,
            text=True,
            timeout=30,
        )
        err = (p.stderr or p.stdout or "").strip()
        return p.returncode, err
    except Exception as e:
        return 1, str(e)


def sync_iptables(rules: list[dict[str, Any]]) -> tuple[bool, str]:
    """Создаёт цепочку CHAIN в nat, вешает на PREROUTING, перезаполняет DNAT."""
    exe = _iptables_bin()
    if not exe:
        return False, "iptables недоступен (нет бинарника). Для Docker нужен образ с iptables и права NET_ADMIN."

    rc, err = _run_iptables(["-t", "nat", "-N", CHAIN])
    if rc != 0:
        el = err.lower()
        if "exists" not in el:
            return False, f"не удалось создать цепочку {CHAIN}: {err}"

    rc, out = _run_iptables(["-t", "nat", "-C", "PREROUTING", "-j", CHAIN])
    if rc != 0:
        rc2, err2 = _run_iptables(["-t", "nat", "-I", "PREROUTING", "1", "-j", CHAIN])
        if rc2 != 0:
            return False, f"не удалось привязать PREROUTING → {CHAIN}: {err2}"

    rc, ferr = _run_iptables(["-t", "nat", "-F", CHAIN])
    if rc != 0:
        return False, f"flush {CHAIN}: {ferr}"

    for r in rules:
        rid = str(r["id"])
        proto = str(r["proto"])
        comment = f"kaskad-{rid}"
        cmd = [
            "-t",
            "nat",
            "-A",
            CHAIN,
            "-p",
            proto,
            "--dport",
            str(int(r["in_port"])),
            "-j",
            "DNAT",
            "--to-destination",
            f'{r["target"]}:{int(r["out_port"])}',
            "-m",
            "comment",
            "--comment",
            comment,
        ]
        rc, emsg = _run_iptables(cmd)
        if rc != 0:
            return False, f"правило {rid}: {emsg}"

    return True, ""


def iptables_chain_dump() -> str:
    exe = _iptables_bin()
    if not exe:
        return "(iptables недоступен)"
    try:
        p = subprocess.run(
            [exe, "-t", "nat", "-S", CHAIN],
            capture_output=True,
            text=True,
            timeout=15,
        )
        out = (p.stdout or "").strip()
        err = (p.stderr or "").strip()
        if p.returncode != 0:
            return err or out or f"(цепочка {CHAIN}: не создана или недоступна)"
        return out if out else f"(цепочка {CHAIN} пуста)"
    except Exception as e:
        return f"(ошибка: {e})"


def startup_resync() -> None:
    """Поднять iptables из файла при старте воркера."""
    try:
        rules = load_rules()
        ok, msg = sync_iptables(rules)
        if ok:
            log.info("iptables синхронизированы, правил: %s", len(rules))
        else:
            log.warning("iptables не синхронизированы: %s", msg)
    except Exception as e:
        log.warning("startup_resync: %s", e)
