"""Хранение правил NAT и синхронизация с iptables.

Режимы (KASKAD_IPTABLES_MODE):
- compat — DNAT в PREROUTING, INPUT/FORWARD с комментарием kaskad:PORT:proto, MASQUERADE.
- chain  — отдельная цепочка nat/KASKAD_WEB (альтернатива).
"""
from __future__ import annotations

import ipaddress
import json
import logging
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

RULES_PATH = Path(os.environ.get("KASKAD_RULES_PATH", "/var/lib/kaskad/rules.json"))
CHAIN = os.environ.get("KASKAD_NAT_CHAIN", "KASKAD_WEB").strip() or "KASKAD_WEB"
IPTABLES_MODE = os.environ.get("KASKAD_IPTABLES_MODE", "compat").strip().lower()
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


def detect_out_interface() -> str | None:
    env = os.environ.get("KASKAD_OUT_IFACE", "").strip()
    if env:
        return env
    try:
        p = subprocess.run(
            ["ip", "-4", "route", "get", "8.8.8.8"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if p.returncode != 0:
            return None
        m = re.search(r"\bdev\s+(\S+)", p.stdout or "")
        return m.group(1) if m else None
    except Exception:
        return None


def _kaskad_comment(in_port: int, proto: str) -> str:
    return f"kaskad:{int(in_port)}:{proto}"


def _iptables_delete_line(table: str | None, full_line: str) -> tuple[int, str]:
    """Строка из `iptables -S`: `-A`/`-I CHAIN ...` → удаление через `-D`."""
    parts = full_line.strip().split()
    if len(parts) < 3:
        return 1, "bad iptables line"
    op = parts[0]
    if op not in ("-A", "-I"):
        return 1, f"unsupported {op}"
    parts[0] = "-D"
    if op == "-I" and len(parts) > 3 and parts[2].isdigit():
        parts.pop(2)
    args = parts
    if table:
        args = ["-t", table] + args
    return _run_iptables(args)


def _flush_matching_rules(table: str | None, chain: str, predicate) -> None:
    for _ in range(64):
        rc, out = _run_iptables(["-t", table, "-S", chain] if table else ["-S", chain])
        if rc != 0:
            break
        prefix = f"-A {chain} "
        victim = None
        for line in (out or "").splitlines():
            line = line.strip()
            if not line.startswith(prefix):
                continue
            rest = line[len(prefix) :]
            if predicate(rest):
                victim = line
                break
        if not victim:
            break
        rc2, err = _iptables_delete_line(table, victim)
        if rc2 != 0:
            log.debug("iptables delete fail: %s", err)
            break


def compat_remove_rule(proto: str, in_port: int) -> None:
    """Удаляет связанные DNAT и правила filter по порту/протоколу."""
    cm = _kaskad_comment(in_port, proto)

    def pred_nat(rest: str) -> bool:
        return (
            f"-p {proto}" in rest
            and f"--dport {in_port}" in rest
            and "DNAT" in rest
            and "--to-destination" in rest
        )

    _flush_matching_rules("nat", "PREROUTING", pred_nat)

    def pred_filter(rest: str) -> bool:
        return cm in rest

    _flush_matching_rules(None, "INPUT", pred_filter)
    _flush_matching_rules(None, "FORWARD", pred_filter)


def compat_apply_rule(r: dict[str, Any], iface: str) -> tuple[bool, str]:
    proto = str(r["proto"])
    in_port = int(r["in_port"])
    out_port = int(r["out_port"])
    target = str(r["target"])
    cm = _kaskad_comment(in_port, proto)

    compat_remove_rule(proto, in_port)

    rc, err = _run_iptables(
        [
            "-I",
            "INPUT",
            "1",
            "-p",
            proto,
            "--dport",
            str(in_port),
            "-m",
            "comment",
            "--comment",
            cm,
            "-j",
            "ACCEPT",
        ]
    )
    if rc != 0:
        return False, f"INPUT: {err}"

    rc, err = _run_iptables(
        [
            "-t",
            "nat",
            "-A",
            "PREROUTING",
            "-p",
            proto,
            "--dport",
            str(in_port),
            "-j",
            "DNAT",
            "--to-destination",
            f"{target}:{out_port}",
        ]
    )
    if rc != 0:
        return False, f"PREROUTING DNAT: {err}"

    rc, err = _run_iptables(
        [
            "-I",
            "FORWARD",
            "1",
            "-p",
            proto,
            "-d",
            target,
            "--dport",
            str(out_port),
            "-m",
            "state",
            "--state",
            "NEW,ESTABLISHED,RELATED",
            "-m",
            "comment",
            "--comment",
            cm,
            "-j",
            "ACCEPT",
        ]
    )
    if rc != 0:
        return False, f"FORWARD→dst: {err}"

    rc, err = _run_iptables(
        [
            "-I",
            "FORWARD",
            "1",
            "-p",
            proto,
            "-s",
            target,
            "--sport",
            str(out_port),
            "-m",
            "state",
            "--state",
            "ESTABLISHED,RELATED",
            "-m",
            "comment",
            "--comment",
            cm,
            "-j",
            "ACCEPT",
        ]
    )
    if rc != 0:
        return False, f"FORWARD←src: {err}"

    return True, ""


def _ensure_masquerade(iface: str) -> tuple[bool, str]:
    rc, _ = _run_iptables(["-t", "nat", "-C", "POSTROUTING", "-o", iface, "-j", "MASQUERADE"])
    if rc == 0:
        return True, ""
    rc2, err = _run_iptables(["-t", "nat", "-A", "POSTROUTING", "-o", iface, "-j", "MASQUERADE"])
    if rc2 != 0:
        return False, err
    return True, ""


def _save_persistent() -> None:
    if shutil.which("netfilter-persistent"):
        subprocess.run(
            ["netfilter-persistent", "save"],
            capture_output=True,
            timeout=60,
        )
    elif shutil.which("iptables-save") and Path("/etc/init.d/iptables").is_file():
        subprocess.run(["service", "iptables", "save"], capture_output=True, timeout=60)


def sync_iptables_compat(rules: list[dict[str, Any]]) -> tuple[bool, str]:
    iface = detect_out_interface()
    if not iface:
        return False, "не удалось определить исходящий интерфейс (задайте KASKAD_OUT_IFACE)"

    old_disk = load_rules()
    for r in old_disk:
        compat_remove_rule(str(r["proto"]), int(r["in_port"]))

    for r in rules:
        ok, msg = compat_apply_rule(r, iface)
        if not ok:
            return False, msg

    ok_m, msg_m = _ensure_masquerade(iface)
    if not ok_m:
        return False, f"MASQUERADE: {msg_m}"

    try:
        _save_persistent()
    except Exception as e:
        log.debug("persistent save: %s", e)

    return True, ""


def sync_iptables_chain(rules: list[dict[str, Any]]) -> tuple[bool, str]:
    exe = _iptables_bin()
    if not exe:
        return False, "iptables недоступен (нет бинарника). Для Docker нужен образ с iptables и права NET_ADMIN."

    rc, err = _run_iptables(["-t", "nat", "-N", CHAIN])
    if rc != 0:
        el = err.lower()
        if "exists" not in el:
            return False, f"не удалось создать цепочку {CHAIN}: {err}"

    rc, _out = _run_iptables(["-t", "nat", "-C", "PREROUTING", "-j", CHAIN])
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


def sync_iptables(rules: list[dict[str, Any]]) -> tuple[bool, str]:
    if IPTABLES_MODE == "chain":
        return sync_iptables_chain(rules)
    return sync_iptables_compat(rules)


def iptables_chain_dump() -> str:
    exe = _iptables_bin()
    if not exe:
        return "(iptables недоступен)"
    try:
        if IPTABLES_MODE == "chain":
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

        chunks: list[str] = []
        for label, args in [
            ("# nat PREROUTING (DNAT)", ["-t", "nat", "-S", "PREROUTING"]),
            ("# filter INPUT (kaskad)", ["-S", "INPUT"]),
            ("# filter FORWARD (kaskad)", ["-S", "FORWARD"]),
            ("# nat POSTROUTING (MASQUERADE)", ["-t", "nat", "-S", "POSTROUTING"]),
        ]:
            p = subprocess.run([exe, *args], capture_output=True, text=True, timeout=15)
            body = (p.stdout or "").strip()
            lines = [
                ln
                for ln in body.splitlines()
                if "kaskad:" in ln or ("DNAT" in ln and "PREROUTING" in args[2])
                or ("MASQUERADE" in ln and "POSTROUTING" in args[2])
            ]
            chunks.append(label)
            chunks.append("\n".join(lines) if lines else "(нет совпадений)")
        return "\n".join(chunks)
    except Exception as e:
        return f"(ошибка: {e})"


def startup_resync() -> None:
    try:
        rules = load_rules()
        ok, msg = sync_iptables(rules)
        if ok:
            log.info("iptables синхронизированы (%s), правил: %s", IPTABLES_MODE, len(rules))
        else:
            log.warning("iptables не синхронизированы: %s", msg)
    except Exception as e:
        log.warning("startup_resync: %s", e)
