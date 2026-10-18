#!/usr/bin/env python3
"""
Shipwatch Installer - Phase 2 Preflight
Read-only readiness checks. Makes no system changes.
"""

from __future__ import annotations

import ctypes
import json
import os
import platform
import shutil
import socket
import subprocess
import shlex
import sys
from pathlib import Path


PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"
RESULT = "RESULT"


def out(kind: str, message: str) -> None:
    print(f"{kind}: {message}")


def is_admin() -> bool:
    system = platform.system()
    if system == "Windows":
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False
    try:
        return os.geteuid() == 0
    except AttributeError:
        return False


def can_sudo_noninteractive() -> bool:
    if platform.system() == "Windows":
        return is_admin()
    sudo = shutil.which("sudo")
    if not sudo:
        return False
    try:
        p = subprocess.run(
            [sudo, "-n", "true"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
        return p.returncode == 0
    except Exception:
        return False


def free_gb(path: str) -> float | None:
    try:
        target = Path(path)
        while not target.exists() and target.parent != target:
            target = target.parent
        usage = shutil.disk_usage(target)
        return usage.free / (1024 ** 3)
    except Exception:
        return None


def port_available(port: int, bind_host: str = "0.0.0.0") -> tuple[bool, str]:
    family = socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((bind_host, port))
        return True, ""
    except OSError as exc:
        return False, str(exc)
    finally:
        sock.close()


def command_version(command: str, args: list[str]) -> tuple[bool, str]:
    exe = shutil.which(command)
    if not exe:
        return False, "not found"
    try:
        p = subprocess.run(
            [exe, *args],
            capture_output=True,
            text=True,
            timeout=5,
        )
        raw = (p.stdout or p.stderr or "").strip()
        first = raw.splitlines()[0] if raw else exe
        return True, first
    except Exception as exc:
        return False, str(exc)


def detect_sdrs() -> list[dict]:
    exe = shutil.which("rtl_test")
    if not exe:
        return []

    try:
        p = subprocess.run(
            [exe, "-t"],
            capture_output=True,
            text=True,
            timeout=4,
        )
        raw = (p.stdout or "") + "\n" + (p.stderr or "")
    except Exception:
        return []

    devices = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or "SN:" not in line or ":" not in line:
            continue
        try:
            _, rest = line.split(":", 1)
            left, serial = rest.rsplit("SN:", 1)
            parts = [x.strip().strip(",") for x in left.split(",")]
            if len(parts) >= 2:
                devices.append(
                    {
                        "manufacturer": parts[0],
                        "product": parts[1],
                        "serial": serial.strip(),
                    }
                )
        except Exception:
            continue
    return devices


def duplicate_serials(devices: list[dict]) -> list[str]:
    counts: dict[str, int] = {}
    for d in devices:
        serial = d.get("serial", "")
        if serial:
            counts[serial] = counts.get(serial, 0) + 1
    return sorted([s for s, n in counts.items() if n > 1])


def linux_usb_power_warnings() -> list[str]:
    if platform.system() != "Linux":
        return []
    try:
        p = subprocess.run(
            ["dmesg"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        raw = p.stdout or ""
    except Exception:
        return []

    needles = (
        "under-voltage",
        "undervoltage",
        "power supply",
        "attempt power cycle",
        "over-current",
        "overcurrent",
    )
    matches = []
    for line in raw.splitlines():
        low = line.lower()
        if any(n in low for n in needles):
            matches.append(line.strip())
    return matches[-10:]


def ssh_test(cfg: dict) -> tuple[bool, str]:
    if not cfg.get("enabled"):
        return True, "SSH not required for local install"

    ssh = cfg.get("ssh_path") or shutil.which("ssh")
    if not ssh:
        return False, "SSH client not found"

    host = cfg.get("host", "")
    user = cfg.get("username", "")
    port = int(cfg.get("port", 22))
    key = cfg.get("key_path", "")

    cmd = [
        ssh,
        "-p", str(port),
        "-o", "ConnectTimeout=5",
    ]
    if cfg.get("auth_method") in {"key","agent"}:
        cmd += ["-o","BatchMode=yes"]
    if key:
        cmd += ["-i", key]
    cmd += [f"{user}@{host}", "printf SHIPWATCH_PREFLIGHT_OK"]

    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=8,
        )
        if p.returncode == 0 and "SHIPWATCH_PREFLIGHT_OK" in p.stdout:
            return True, "SSH login successful"
        msg = (p.stderr or p.stdout or "SSH login failed").strip()
        return False, msg.splitlines()[-1] if msg else "SSH login failed"
    except Exception as exc:
        return False, str(exc)


def remote_preflight(cfg: dict) -> int:
    failures=0
    warnings=0

    ssh_cfg=cfg.get("ssh",{})
    ok,detail=ssh_test(ssh_cfg)
    if not ok:
        out(FAIL,f"SSH={detail}")
        out(RESULT,"NO_SYSTEM_CHANGES_MADE")
        out(RESULT,"NEXT=FIX_SSH_AND_RUN_PREFLIGHT_AGAIN")
        return 1

    out(PASS,f"SSH={detail}")

    ssh=ssh_cfg.get("ssh_path") or shutil.which("ssh")
    cmd=[
        ssh,
        "-p",str(ssh_cfg.get("port",22)),
        "-o","ConnectTimeout=8",
    ]
    if ssh_cfg.get("auth_method") in {"key","agent"}:
        cmd += ["-o","BatchMode=yes"]
    if ssh_cfg.get("key_path"):
        cmd += ["-i",ssh_cfg["key_path"]]

    user_host=f"{ssh_cfg.get('username')}@{ssh_cfg.get('host')}"

    expected=[]
    for role,info in cfg.get("receivers",{}).items():
        if info.get("enabled",True) and info.get("serial"):
            expected.append((role.upper(),str(info["serial"])))

    ports=cfg.get("network",{})
    port_values=[
        ("WEB",ports.get("web_port",80)),
        ("RADIO",ports.get("radio_port",8088)),
        ("AIS_WEB",ports.get("ais_web_port",8100)),
        ("AIS_SERVICE",ports.get("ais_service_port",8118)),
    ]
    rnet=ports.get("readsb",{})
    port_values += [
        ("READSB_RAW_IN",rnet.get("raw_input",30001)),
        ("READSB_RAW_OUT",rnet.get("raw_output",30002)),
        ("READSB_SBS_OUT",rnet.get("sbs_output",30003)),
        ("READSB_BEAST_IN",rnet.get("beast_input",30004)),
        ("READSB_BEAST_OUT",rnet.get("beast_output",30005)),
        ("READSB_BEAST_SECONDARY_IN",rnet.get("beast_secondary_input",30104)),
    ]

    serial_checks="\n".join(
        f"if printf '%s\\n' \"$SERIALS\" | grep -Fxq {shlex.quote(serial)}; "
        f"then echo 'PASS: {role}_SDR_FOUND serial={serial}'; "
        f"else echo 'FAIL: {role}_SDR_NOT_FOUND serial={serial}'; fi"
        for role,serial in expected
    )

    port_checks="\n".join(
        f"if ss -ltnH 2>/dev/null | awk '{{print $4}}' | grep -Eq '[:.]({int(port)})$'; "
        f"then echo 'RESULT: PORT_{name}_{int(port)}=IN_USE'; "
        f"else echo 'PASS: PORT_{name}_{int(port)}=AVAILABLE'; fi"
        for name,port in port_values
    )

    script=f"""
echo "RESULT: REMOTE_HOST=$(hostname)"
echo "RESULT: REMOTE_OS=$(uname -s) $(uname -r)"
echo "RESULT: REMOTE_ARCH=$(uname -m)"

if [ "$(uname -s)" = "Linux" ]; then
  echo "PASS: REMOTE_LINUX"
else
  echo "FAIL: REMOTE_NOT_LINUX"
fi

if command -v python3 >/dev/null 2>&1; then
  echo "PASS: REMOTE_PYTHON3=$(python3 --version 2>&1)"
else
  echo "FAIL: REMOTE_PYTHON3_MISSING"
fi

if command -v tar >/dev/null 2>&1; then
  echo "PASS: REMOTE_TAR_AVAILABLE"
else
  echo "FAIL: REMOTE_TAR_MISSING"
fi

if sudo -n true >/dev/null 2>&1; then
  echo "PASS: REMOTE_SUDO_NONINTERACTIVE"
else
  echo "WARN: REMOTE_SUDO_WILL_REQUIRE_PASSWORD"
fi

FREE_KB=$(df -Pk / 2>/dev/null | awk 'NR==2 {{print $4}}')
if [ -n "$FREE_KB" ] && [ "$FREE_KB" -ge 2097152 ]; then
  echo "PASS: REMOTE_DISK_SPACE_OK free_kb=$FREE_KB"
else
  echo "FAIL: REMOTE_LOW_DISK free_kb=$FREE_KB"
fi

if command -v rtl_test >/dev/null 2>&1; then
  SERIALS=$(rtl_test -t 2>&1 | sed -n 's/.*SN:[[:space:]]*//p' | sed 's/[[:space:]]*$//')
else
  SERIALS=$(
    for d in /sys/bus/usb/devices/*; do
      [ -f "$d/idVendor" ] || continue
      v=$(cat "$d/idVendor" 2>/dev/null)
      p=$(cat "$d/idProduct" 2>/dev/null)
      case "$v:$p" in
        0bda:2832|0bda:2838)
          cat "$d/serial" 2>/dev/null || true
          ;;
      esac
    done
  )
fi

COUNT=$(printf '%s\n' "$SERIALS" | sed '/^$/d' | wc -l)
echo "RESULT: REMOTE_SDR_COUNT=$COUNT"
printf '%s\n' "$SERIALS" | sed '/^$/d' | while read s; do
  echo "RESULT: REMOTE_SDR_SERIAL=$s"
done

{serial_checks}

{port_checks}

DMESG_CMD="dmesg"
if sudo -n true >/dev/null 2>&1; then
  DMESG_CMD="sudo dmesg"
fi
if $DMESG_CMD 2>/dev/null | grep -Eiq 'under.?voltage|power supply|attempt power cycle|over.?current'; then
  echo "WARN: REMOTE_USB_POWER_WARNING_DETECTED"
else
  echo "PASS: REMOTE_NO_USB_POWER_WARNING_DETECTED"
fi
"""

    cmd += [user_host,script]

    try:
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=20)
    except Exception as exc:
        out(FAIL,f"REMOTE_PREFLIGHT_EXECUTION={exc}")
        out(RESULT,"NO_SYSTEM_CHANGES_MADE")
        return 1

    raw=(p.stdout or "")
    for line in raw.splitlines():
        print(line)
        if line.startswith("FAIL:"):
            failures+=1
        elif line.startswith("WARN:"):
            warnings+=1

    if p.returncode:
        out(FAIL,f"REMOTE_PREFLIGHT_SSH_EXIT={p.returncode}")
        failures+=1

    print("==============================================================")
    if failures:
        out(FAIL,f"PREFLIGHT_BLOCKED failures={failures} warnings={warnings}")
        out(RESULT,"NO_SYSTEM_CHANGES_MADE")
        out(RESULT,"NEXT=FIX_FAILURES_AND_RUN_PREFLIGHT_AGAIN")
        return 1

    out(PASS,f"PREFLIGHT_READY warnings={warnings}")
    out(RESULT,"NO_SYSTEM_CHANGES_MADE")
    out(RESULT,"NEXT=REVIEW_WARNINGS_THEN_RUN_INSTALL")
    return 0


def load_config(path: str) -> dict:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: shipwatch_preflight.py shipwatch.setup-preview.json")
        return 2

    cfg = load_config(sys.argv[1])

    print("==============================================================")
    print("SHIPWATCH PHASE 2 - READ-ONLY PREFLIGHT")
    print("==============================================================")

    failures = 0
    warnings = 0

    system = platform.system()
    release = platform.release()
    out(RESULT, f"PLATFORM={system} {release}")

    if cfg.get("installation", {}).get("mode") == "remote":
        return remote_preflight(cfg)

    # Privilege
    if is_admin():
        out(PASS, "ADMIN_PRIVILEGES_AVAILABLE")
    elif system != "Windows" and can_sudo_noninteractive():
        out(PASS, "SUDO_AVAILABLE_NONINTERACTIVE")
    else:
        out(WARN, "INSTALLER_NOT_CURRENTLY_ELEVATED")
        warnings += 1

    # Paths / free space
    install = cfg.get("installation", {})
    for key in (
        "application_path",
        "config_path",
        "data_path",
        "log_path",
        "web_path",
        "backup_path",
    ):
        value = install.get(key, "")
        if not value:
            out(FAIL, f"{key.upper()}_MISSING")
            failures += 1
            continue
        gb = free_gb(value)
        if gb is None:
            out(WARN, f"{key.upper()}_FREE_SPACE_UNKNOWN path={value}")
            warnings += 1
        elif gb < 2:
            out(FAIL, f"{key.upper()}_LOW_DISK free_gb={gb:.2f} path={value}")
            failures += 1
        else:
            out(PASS, f"{key.upper()}_SPACE_OK free_gb={gb:.2f}")

    # Required/common tools
    tools = [
        ("python", ["--version"]),
    ]
    if system != "Windows":
        tools += [
            ("ffmpeg", ["-version"]),
            ("rtl_test", ["--help"]),
        ]

    for cmd, args in tools:
        ok, version = command_version(cmd, args)
        if ok:
            out(PASS, f"TOOL_{cmd.upper()}={version}")
        else:
            out(WARN, f"TOOL_{cmd.upper()}_MISSING")
            warnings += 1

    # Network ports
    ports = cfg.get("network", {})
    port_items = {
        "WEB": ports.get("web_port", 8080),
        "RADIO": ports.get("radio_port", 8088),
        "AIS_WEB": ports.get("ais_web_port", 8100),
        "AIS_SERVICE": ports.get("ais_service_port", 8118),
    }
    readsb = ports.get("readsb", {})
    for name, key, default in (
        ("READSB_RAW_IN", "raw_input", 30001),
        ("READSB_RAW_OUT", "raw_output", 30002),
        ("READSB_SBS_OUT", "sbs_output", 30003),
        ("READSB_BEAST_IN", "beast_input", 30004),
        ("READSB_BEAST_OUT", "beast_output", 30005),
        ("READSB_BEAST_SECONDARY_IN", "beast_secondary_input", 30104),
    ):
        port_items[name] = readsb.get(key, default)

    seen_ports = {}
    for name, port in port_items.items():
        try:
            port = int(port)
        except Exception:
            out(FAIL, f"{name}_PORT_INVALID={port}")
            failures += 1
            continue
        if port in seen_ports:
            out(FAIL, f"PORT_DUPLICATE={port} used_by={seen_ports[port]},{name}")
            failures += 1
        else:
            seen_ports[port] = name

        ok, why = port_available(port)
        if ok:
            out(PASS, f"PORT_{name}_{port}_AVAILABLE")
        else:
            out(WARN, f"PORT_{name}_{port}_IN_USE {why}")
            warnings += 1

    # SSH if remote
    ok, detail = ssh_test(cfg.get("ssh", {}))
    if ok:
        out(PASS, f"SSH={detail}")
    else:
        out(FAIL, f"SSH={detail}")
        failures += 1

    # SDR checks only on local host. Remote SDR preflight will be delegated over SSH.
    if cfg.get("installation", {}).get("mode") == "local":
        devices = detect_sdrs()
        out(RESULT, f"SDR_COUNT={len(devices)}")
        for i, dev in enumerate(devices, 1):
            out(
                RESULT,
                f"SDR_{i}={dev['manufacturer']}|{dev['product']}|SERIAL={dev['serial']}",
            )

        duplicates = duplicate_serials(devices)
        if duplicates:
            for serial in duplicates:
                out(FAIL, f"DUPLICATE_SDR_SERIAL={serial}")
                failures += 1
        elif devices:
            out(PASS, "SDR_SERIALS_UNIQUE")

        layout = int(cfg.get("receiver_layout", 2))
        if len(devices) < layout:
            out(WARN, f"SDR_COUNT_BELOW_SELECTED_LAYOUT expected={layout} found={len(devices)}")
            warnings += 1

        expected = cfg.get("receivers", {})
        expected_serials = {
            role: info.get("serial", "")
            for role, info in expected.items()
            if info.get("enabled", True)
        }
        found = {d["serial"] for d in devices}
        for role, serial in expected_serials.items():
            if not serial:
                out(FAIL, f"{role.upper()}_SERIAL_MISSING")
                failures += 1
            elif serial in found:
                out(PASS, f"{role.upper()}_SDR_FOUND serial={serial}")
            else:
                out(WARN, f"{role.upper()}_SDR_NOT_CURRENTLY_FOUND serial={serial}")
                warnings += 1

    # USB power warnings
    power = linux_usb_power_warnings()
    if power:
        out(WARN, f"USB_POWER_WARNINGS={len(power)}")
        warnings += 1
        for line in power:
            out(RESULT, f"USB_POWER_EVENT={line}")
    else:
        out(PASS, "NO_USB_POWER_WARNINGS_DETECTED")

    print("==============================================================")
    if failures:
        out(FAIL, f"PREFLIGHT_BLOCKED failures={failures} warnings={warnings}")
        out(RESULT, "NO_SYSTEM_CHANGES_MADE")
        out(RESULT, "NEXT=FIX_FAILURES_AND_RUN_PREFLIGHT_AGAIN")
        return 1

    out(PASS, f"PREFLIGHT_READY warnings={warnings}")
    out(RESULT, "NO_SYSTEM_CHANGES_MADE")
    out(RESULT, "NEXT=REVIEW_WARNINGS_THEN_RUN_INSTALL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
