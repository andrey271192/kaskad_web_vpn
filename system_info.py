"""Метрики хоста Linux + systemd / docker (best-effort)."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import psutil


def _read_machine_id() -> str:
    for p in (Path("/etc/machine-id"), Path("/var/lib/dbus/machine-id")):
        try:
            t = p.read_text(encoding="utf-8").strip()
            if t:
                return t
        except OSError:
            continue
    return "—"


def _uptime_h() -> str:
    try:
        up = float(Path("/proc/uptime").read_text().split()[0])
        d, rem = divmod(int(up), 86400)
        h, rem = divmod(rem, 3600)
        m, _ = divmod(rem, 60)
        parts = []
        if d:
            parts.append(f"{d} дн.")
        if h:
            parts.append(f"{h} ч.")
        parts.append(f"{m} мин.")
        return "up " + ", ".join(parts)
    except Exception:
        return "—"


def _load_avg() -> str:
    try:
        la = os.getloadavg()
        return ", ".join(f"{x:.2f}" for x in la)
    except Exception:
        return "—"


def _mem_mb() -> str:
    try:
        v = psutil.virtual_memory()
        used = int(v.used / (1024 * 1024))
        total = int(v.total / (1024 * 1024))
        return f"{used} / {total} MB"
    except Exception:
        return "—"


def _ipv4_addrs() -> str:
    lines: list[str] = []
    try:
        out = subprocess.run(
            ["ip", "-4", "-br", "addr"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for raw in (out.stdout or "").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            parts = raw.split()
            if len(parts) >= 3:
                iface = parts[0]
                cidrs = [x for x in parts[2:] if "/" in x]
                if cidrs:
                    lines.append(f"{iface}: {', '.join(cidrs)}")
    except Exception:
        pass
    if not lines:
        try:
            addrs = []
            for n, addrs_list in psutil.net_if_addrs().items():
                for a in addrs_list:
                    if a.family.name == "AF_INET" and not a.address.startswith("127."):
                        addrs.append(f"{n}: {a.address}")
            lines = addrs
        except Exception:
            pass
    return "\n".join(lines) if lines else "—"


def collect_system_payload() -> dict:
    ui_ver = os.environ.get("KASKAD_UI_VERSION", "v2.2").strip()

    return {
        "machine_id": _read_machine_id(),
        "uptime": _uptime_h(),
        "load": _load_avg(),
        "mem": _mem_mb(),
        "ipaddrs": _ipv4_addrs(),
        "ui_version": ui_ver,
    }


def systemd_unit_row(unit: str) -> dict[str, str]:
    unit = unit.strip()
    row = {"unit": unit, "active": "unknown", "enabled": "unknown"}
    if not shutil.which("systemctl"):
        row["active"] = "n/a"
        row["enabled"] = "n/a"
        return row
    try:
        p = subprocess.run(
            ["systemctl", "show", unit, "-p", "ActiveState", "-p", "UnitFileState", "--no-pager"],
            capture_output=True,
            text=True,
            timeout=8,
        )
        txt = p.stdout or ""
        for line in txt.splitlines():
            if line.startswith("ActiveState="):
                row["active"] = line.split("=", 1)[-1].strip() or "unknown"
            if line.startswith("UnitFileState="):
                row["enabled"] = line.split("=", 1)[-1].strip() or "unknown"
    except Exception:
        row["active"] = "error"
        row["enabled"] = "error"
    return row


def docker_container_row(name: str, display_unit: str | None = None) -> dict[str, str]:
    name = name.strip()
    disp = (display_unit or "").strip()
    row = {"unit": disp if disp else f"{name} (docker)", "active": "inactive", "enabled": "—"}
    if not shutil.which("docker"):
        row["active"] = "n/a"
        return row
    try:
        p = subprocess.run(
            [
                "docker",
                "inspect",
                "-f",
                "{{.State.Running}} {{.HostConfig.RestartPolicy.Name}}",
                name,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if p.returncode != 0:
            row["active"] = "missing"
            return row
        parts = (p.stdout or "").strip().split(None, 1)
        running = parts[0].lower() == "true"
        restart = parts[1] if len(parts) > 1 else ""
        row["active"] = "active" if running else "inactive"
        row["enabled"] = restart if restart else "no"
    except Exception:
        row["active"] = "error"
    return row


def collect_services_rows() -> list[dict[str, str]]:
    units_csv = os.environ.get(
        "SERVICE_UNITS",
        "dbus.service,systemd-networkd.service,kaskad-web.service",
    )
    units = [u.strip() for u in units_csv.split(",") if u.strip()]
    docker_web = os.environ.get("DOCKER_WEB_CONTAINER", "").strip()
    docker_disp = os.environ.get("DOCKER_WEB_DISPLAY_UNIT", "kaskad-web.service").strip()

    rows: list[dict[str, str]] = []
    for i, u in enumerate(units):
        if i == 2 and docker_web:
            rows.append(docker_container_row(docker_web, docker_disp or None))
        else:
            rows.append(systemd_unit_row(u))
    return rows
