#!/usr/bin/env python3
"""
Shipwatch Setup Wizard - Phase 1
Safe configuration collector. Makes no system changes.

Goals:
- Work on Windows, macOS, and Linux/Pi.
- Ask SSH questions only for remote receiver hosts.
- Support 2-SDR and 3-SDR layouts.
- Identify receivers by serial number, never USB index.
- Produce a reviewable, non-secret configuration file.
"""

from __future__ import annotations

import getpass
import base64
import json
import os
import platform
import re
import shutil
import socket
import subprocess
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import urlsplit


TITLE = "Shipwatch Setup Wizard - Phase 1"
OTA_CONSENT_VERSION = "v1"


def heading(text: str) -> None:
    print()
    print("=" * 66)
    print(text)
    print("=" * 66)


def ask(prompt: str, default: str = "") -> str:
    label = f"{prompt} [{default}]" if default else prompt
    value = input(f"{label}: ").strip()
    return value or default


def yes_no(prompt: str, default: bool = True) -> bool:
    d = "Y/n" if default else "y/N"
    value = input(f"{prompt} [{d}]: ").strip().lower()
    if not value:
        return default
    return value in {"y", "yes"}


def choose(prompt: str, options: list[tuple[str, str]], default: str | None = None) -> str:
    print()
    print(prompt)
    for key, label in options:
        marker = " (recommended)" if key == default else ""
        print(f"  {key}. {label}{marker}")
    valid = {k for k, _ in options}
    while True:
        value = input(f"Choose [{default or ''}]: ").strip() or (default or "")
        if value in valid:
            return value
        print("Please choose one of:", ", ".join(sorted(valid)))


def platform_defaults(target: str) -> dict:
    if target in {"linux", "remote"}:
        return {
            "application_path": "/opt/shipwatch",
            "config_path": "/etc/shipwatch",
            "data_path": "/var/lib/shipwatch",
            "log_path": "/var/log/shipwatch",
            "web_path": "/var/www/html/shipwatch",
            "backup_path": "/var/backups/shipwatch",
        }
    if target == "mac":
        base = "/Library/Application Support/Shipwatch"
        return {
            "application_path": "/Applications/Shipwatch",
            "config_path": f"{base}/config",
            "data_path": f"{base}/data",
            "log_path": "/Library/Logs/Shipwatch",
            "web_path": f"{base}/web",
            "backup_path": f"{base}/backups",
        }
    return {
        "application_path": r"C:\Program Files\Shipwatch",
        "config_path": r"C:\ProgramData\Shipwatch\config",
        "data_path": r"C:\ProgramData\Shipwatch\data",
        "log_path": r"C:\ProgramData\Shipwatch\logs",
        "web_path": r"C:\ProgramData\Shipwatch\web",
        "backup_path": r"C:\ProgramData\Shipwatch\backups",
    }


def available_ota_release() -> dict | None:
    """Return a valid, release-pinned controller config; never discover keys over HTTP."""
    path = Path(__file__).resolve().parents[2] / "runtime" / "common" / "ota-release-config.json"
    try:
        release = json.loads(path.read_text(encoding="utf-8-sig"))
        api_url = str(release["api_url"])
        key = base64.b64decode(str(release["server_verify_key_b64"]), validate=True)
        parsed = urlsplit(api_url)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment or parsed.path.rstrip("/") != "/shipwatch-ota/api/v1"
                or len(key) != 32):
            return None
        return {"api_url": api_url, "server_verify_key_b64": release["server_verify_key_b64"]}
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def collect_ota_consent(target: str, station: dict, installation: dict) -> None:
    if target not in {"linux", "remote", "windows", "mac"}:
        return
    release = available_ota_release()
    if not release:
        return

    heading("Optional remote receiver participation")
    print("Remote management sends the station name and device public key to AtlanticLink.")
    print("The receiver checks in outbound and can receive only separately approved settings.")
    remote = yes_no("Allow Shipwatch remote management?", False)
    mastchain = False
    aiscatcher_config_path = ""
    if remote:
        print("MastChain contribution separately shares the receiver's exact location and AIS feed with MastChain.")
        print("The operator must manually add the station and provide its station-specific feed settings.")
        print("No token value or reward is promised.")
        mastchain = yes_no("Contribute this receiver to MastChain under the Shipwatch operator's account?", False)
        if mastchain:
            def coordinate(label: str, low: float, high: float, current: str) -> str:
                while True:
                    value = ask(label, current)
                    try:
                        number = float(value)
                        if low <= number <= high:
                            return str(number)
                    except ValueError:
                        pass
                    print(f"Enter a number between {low} and {high}.")
            station["latitude"] = coordinate("Exact latitude shared with MastChain", -90, 90, str(station.get("latitude", "")))
            station["longitude"] = coordinate("Exact longitude shared with MastChain", -180, 180, str(station.get("longitude", "")))
            if target == "windows":
                default_config = r"C:\ProgramData\AIS-catcher\aiscatcher.json"
            elif target == "mac":
                default_config = "/usr/local/etc/AIS-catcher/aiscatcher.json"
            else:
                default_config = "/etc/AIS-catcher/aiscatcher.json"
            aiscatcher_config_path = ask("Existing AIS-Catcher JSON config path (stored locally only)", default_config)
            path_type = PureWindowsPath if target == "windows" else PurePosixPath if target == "mac" else Path
            if not path_type(aiscatcher_config_path).is_absolute():
                raise ValueError("The AIS-Catcher config path must be absolute.")

    installation["ota_controller"] = release
    installation["ota_consent"] = {
        "consent_version": OTA_CONSENT_VERSION,
        "remote_management_consent": remote,
        "mastchain_consent": mastchain,
        "station_name": str(station.get("name", "Shipwatch"))[:100],
    }
    if mastchain:
        installation["ota_consent"]["latitude"] = float(station["latitude"])
        installation["ota_consent"]["longitude"] = float(station["longitude"])
        installation["ota_aiscatcher_config_path"] = aiscatcher_config_path


def detect_local_sdrs() -> list[dict]:
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
    # Common rtl_test line:
    # 0:  AIRNAV, ADSB_1090, SN: 00000010
    rx = re.compile(r"^\s*\d+:\s*(.*?),\s*(.*?),\s*SN:\s*(\S+)\s*$")
    for line in raw.splitlines():
        m = rx.match(line)
        if m:
            devices.append(
                {
                    "manufacturer": m.group(1).strip(),
                    "product": m.group(2).strip(),
                    "serial": m.group(3).strip(),
                }
            )
    return devices


def test_tcp(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=3):
            return True
    except OSError:
        return False


def ssh_client_candidates() -> list[str]:
    candidates=[]

    found=shutil.which("ssh")
    if found:
        candidates.append(found)

    if platform.system()=="Windows":
        for candidate in (
            r"C:\Program Files\Git\usr\bin\ssh.exe",
            r"C:\Program Files\Git\bin\ssh.exe",
        ):
            if Path(candidate).exists():
                candidates.append(candidate)

    unique=[]
    for candidate in candidates:
        if candidate not in unique:
            unique.append(candidate)
    return unique


def matching_scp(ssh_path: str) -> str:
    p=Path(ssh_path)
    name="scp.exe" if platform.system()=="Windows" else "scp"
    beside=p.with_name(name)
    if beside.exists():
        return str(beside)
    return shutil.which("scp") or ""


def test_ssh(cfg: dict) -> tuple[bool, str]:
    ssh = cfg.get("ssh_path") or shutil.which("ssh")
    if not ssh:
        return False, "SSH client not found."

    cmd = [ssh, "-p", str(cfg["port"]), "-o", "ConnectTimeout=5"]
    if cfg.get("auth_method") in {"key","agent"}:
        cmd += ["-o","BatchMode=yes"]
    if cfg.get("key_path"):
        cmd += ["-i", cfg["key_path"]]
    cmd += [f'{cfg["username"]}@{cfg["host"]}', "printf SHIPWATCH_SSH_OK"]

    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        if p.returncode == 0 and "SHIPWATCH_SSH_OK" in p.stdout:
            return True, "SSH connection successful."
        msg = (p.stderr or p.stdout or "SSH connection failed.").strip()
        return False, msg.splitlines()[-1] if msg else "SSH connection failed."
    except Exception as exc:
        return False, str(exc)


def detect_remote_sdrs(cfg: dict) -> list[dict]:
    ssh=cfg.get("ssh_path") or shutil.which("ssh")
    if not ssh:
        return []

    cmd=[
        ssh,
        "-p",str(cfg.get("port",22)),
        "-o","ConnectTimeout=5",
    ]
    if cfg.get("auth_method") in {"key","agent"}:
        cmd += ["-o","BatchMode=yes"]
    if cfg.get("key_path"):
        cmd += ["-i",cfg["key_path"]]

    remote=r"""if command -v rtl_test >/dev/null 2>&1; then
rtl_test -t 2>&1 | head -30
else
for d in /sys/bus/usb/devices/*; do
  [ -f "$d/idVendor" ] || continue
  v=$(cat "$d/idVendor" 2>/dev/null)
  p=$(cat "$d/idProduct" 2>/dev/null)
  case "$v:$p" in
    0bda:2832|0bda:2838)
      m=$(cat "$d/manufacturer" 2>/dev/null || echo RTL-SDR)
      n=$(cat "$d/product" 2>/dev/null || echo RTL2832U)
      s=$(cat "$d/serial" 2>/dev/null || true)
      echo "USBSDR|$m|$n|$s"
      ;;
  esac
done
fi"""

    cmd += [f'{cfg.get("username")}@{cfg.get("host")}',remote]

    try:
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=10)
        raw=(p.stdout or "")+"\n"+(p.stderr or "")
    except Exception:
        return []

    devices=[]
    rx=re.compile(r"^\s*\d+:\s*(.*?),\s*(.*?),\s*SN:\s*(\S+)\s*$")
    for line in raw.splitlines():
        m=rx.match(line)
        if m:
            devices.append({
                "manufacturer":m.group(1).strip(),
                "product":m.group(2).strip(),
                "serial":m.group(3).strip(),
            })
            continue
        if line.startswith("USBSDR|"):
            parts=line.split("|",3)
            if len(parts)==4 and parts[3].strip():
                devices.append({
                    "manufacturer":parts[1].strip(),
                    "product":parts[2].strip(),
                    "serial":parts[3].strip(),
                })

    unique=[]
    seen=set()
    for dev in devices:
        if dev["serial"] and dev["serial"] not in seen:
            unique.append(dev)
            seen.add(dev["serial"])
    return unique


def pick_serial(role: str, devices: list[dict], excluded: set[str]) -> str:
    available = [d for d in devices if d["serial"] not in excluded]
    if available:
        print()
        print(f"Select {role} receiver:")
        for i, dev in enumerate(available, start=1):
            print(
                f"  {i}. {dev['manufacturer']} {dev['product']} "
                f"— serial {dev['serial']}"
            )
        print("  M. Enter serial manually")
        while True:
            value = input("Choose: ").strip()
            if value.lower() == "m":
                break
            try:
                idx = int(value) - 1
                if 0 <= idx < len(available):
                    return available[idx]["serial"]
            except ValueError:
                pass
            print("Choose a listed receiver or M.")
    return ask(f"Enter {role} receiver serial")


def main() -> int:
    heading(TITLE)
    print("This phase collects and validates settings only.")
    print("It does NOT install packages, change services, or rewrite SDRs.")

    target = choose(
        "Where will the Shipwatch receiver software run?",
        [
            ("windows", "This Windows 10 computer"),
            ("mac", "This Mac"),
            ("linux", "This Raspberry Pi / Linux computer"),
            ("remote", "A remote Raspberry Pi / Linux computer over SSH"),
        ],
        default="linux" if platform.system() == "Linux" else
                "mac" if platform.system() == "Darwin" else "windows",
    )

    cfg = {
        "schema_version": 2,
        "station": {},
        "installation": {
            "platform": target,
            "mode": "remote" if target == "remote" else "local",
            "run_at_boot": True,
        },
        "ssh": {"enabled": target == "remote"},
        "receivers": {},
        "network": {
            "web_port": 8080,
            "radio_port": 8088,
            "ais_web_port": 8100,
            "ais_service_port": 8118,
        },
    }

    heading("Station")
    cfg["station"]["name"] = ask("Station name", "Shipwatch")
    cfg["station"]["location_label"] = ask("Location description", "")
    cfg["station"]["latitude"] = ask("Latitude", "")
    cfg["station"]["longitude"] = ask("Longitude", "")
    # Explicit opt-in: no geolocation service is contacted.
    if yes_no("Suggest nearby ports and airports from a local catalog?", False):
        from regional_selection import suggest, validate_coordinate, build_station_region
        try:
            lat, lon = validate_coordinate(cfg["station"]["latitude"], cfg["station"]["longitude"])
            default_catalog = str(Path(__file__).resolve().parent / "regional_facilities.json")
            catalog_path = Path(ask("Local facility catalog (JSON)", default_catalog)).expanduser()
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
            if not isinstance(catalog, list):
                raise ValueError("Facility catalog must be a JSON array")
            cfg["station"]["regional_suggestions"] = {}
            for category in ("port", "airport"):
                options = suggest(lat, lon, catalog, category)
                print("Nearby " + category + "s:")
                for number, option in enumerate(options, 1):
                    print("  " + str(number) + ". " + option["name"] + " (" + str(option["distance_km"]) + " km)")
                if options:
                    choice = ask("Choose " + category + " number or Enter to skip", "")
                    if choice:
                        index = int(choice) - 1
                        if not 0 <= index < len(options):
                            raise ValueError("Selection out of range")
                        selected = options[index]
                        cfg["station"]["regional_suggestions"][category] = {
                            "name": selected["name"],
                            "latitude": selected["latitude"],
                            "longitude": selected["longitude"],
                        }
                else:
                    print("  No entries in range; check catalog coverage.")
            cfg["station"]["region_preview"] = build_station_region(lat, lon, cfg["station"]["regional_suggestions"])
            print("Regional suggestions saved in preview only; SDR tuning unchanged.")
        except (ValueError, KeyError, OSError, TypeError) as exc:
            print("WARN: No regional suggestion applied: " + str(exc))
            cfg["station"].pop("regional_suggestions", None)
            cfg["station"].pop("region_preview", None)
    collect_ota_consent(target, cfg["station"], cfg["installation"])

    if target == "remote":
        heading("Remote SSH")
        cfg["ssh"]["host"] = ask("SSH host or IP address")
        cfg["ssh"]["alias"] = ask("Optional SSH alias", "shipwatch-host")
        cfg["ssh"]["port"] = int(ask("SSH port", "22"))
        cfg["ssh"]["username"] = ask("SSH username")
        method = choose(
            "SSH authentication method",
            [
                ("key", "Existing SSH private key"),
                ("agent", "SSH agent"),
                ("password", "Password / interactive login"),
            ],
            default="key",
        )
        cfg["ssh"]["auth_method"] = method
        cfg["ssh"]["key_path"] = ask("Private key path", "") if method == "key" else ""

        print()
        if test_tcp(cfg["ssh"]["host"], cfg["ssh"]["port"]):
            print("PASS: SSH port is reachable")
        else:
            print("FAIL: SSH port is not reachable")

        clients=ssh_client_candidates()
        if clients:
            print("Detected SSH clients:")
            for client in clients:
                print(" -",client)

        if method in {"key", "agent"} and yes_no("Test SSH login now?", True):
            ok=False
            msg="SSH connection failed."
            for client in clients:
                cfg["ssh"]["ssh_path"]=client
                cfg["ssh"]["scp_path"]=matching_scp(client)
                ok,msg=test_ssh(cfg["ssh"])
                if ok:
                    print(f"PASS: SSH connection successful using {client}")
                    break
            if not ok:
                print("FAIL: "+msg)
                cfg["ssh"]["ssh_path"]=ask(
                    "SSH client path",
                    clients[0] if clients else (shutil.which("ssh") or "")
                )
                cfg["ssh"]["scp_path"]=ask(
                    "SCP client path",
                    matching_scp(cfg["ssh"]["ssh_path"]) if cfg["ssh"]["ssh_path"] else ""
                )
        else:
            default_ssh=clients[0] if clients else (shutil.which("ssh") or "")
            cfg["ssh"]["ssh_path"]=ask("SSH client path",default_ssh)
            cfg["ssh"]["scp_path"]=ask(
                "SCP client path",
                matching_scp(cfg["ssh"]["ssh_path"]) if cfg["ssh"]["ssh_path"] else ""
            )

    heading("Installation Paths")
    defaults = platform_defaults(target)
    for key, default in defaults.items():
        cfg["installation"][key] = ask(key.replace("_", " ").title(), default)
    cfg["installation"]["run_at_boot"] = yes_no("Start Shipwatch automatically at boot?", True)

    heading("Receiver Layout")
    layout = choose(
        "How many SDR receivers do you want to use?",
        [
            ("2", "2 SDRs — ADS-B dedicated; AIS + Voice shared"),
            ("3", "3 SDRs — ADS-B, AIS, and Voice all dedicated"),
        ],
        default="3",
    )
    cfg["receiver_layout"] = int(layout)

    devices = detect_remote_sdrs(cfg["ssh"]) if target == "remote" else detect_local_sdrs()
    if devices:
        print()
        where="remote" if target=="remote" else "local"
        print(f"Detected {len(devices)} {where} SDR receiver(s):")
        for d in devices:
            print(f"  - {d['manufacturer']} {d['product']} — {d['serial']}")
    else:
        print()
        print("No compatible SDR serials were detected automatically.")
        print("You can retry hardware detection later or enter serial numbers manually.")

    used: set[str] = set()

    adsb = pick_serial("ADS-B", devices, used)
    used.add(adsb)

    ais = pick_serial("AIS", devices, used)
    used.add(ais)

    if layout == "3":
        voice = pick_serial("Voice", devices, used)
        used.add(voice)
        share_with = ""
        voice_dedicated = True
        lease = 0
    else:
        voice = ais
        share_with = "ais"
        voice_dedicated = False
        lease = int(ask("Voice safety lease in seconds", "900"))

    cfg["receivers"] = {
        "adsb": {
            "enabled": True,
            "type": "rtlsdr",
            "serial": adsb,
            "dedicated": True,
            "gain": "auto",
            "ppm": 0,
        },
        "ais": {
            "enabled": True,
            "type": "rtlsdr",
            "serial": ais,
            "dedicated": layout == "3",
        },
        "voice": {
            "enabled": True,
            "type": "rtlsdr",
            "serial": voice,
            "dedicated": voice_dedicated,
            "share_with": share_with,
            "voice_lease_seconds": lease,
        },
    }

    # Validate role assignment.
    if adsb == ais:
        print("FAIL: ADS-B and AIS cannot use the same receiver.")
        return 2
    if layout == "3" and len({adsb, ais, voice}) != 3:
        print("FAIL: Three-receiver mode requires three unique serial numbers.")
        return 2

    heading("Network")
    default_host = cfg["ssh"].get("host") if target == "remote" else socket.gethostname()
    cfg["network"]["public_host"] = ask(
        "Hostname or IP users will enter in their browser",
        default_host or "shipwatch"
    )
    default_web_port = 80 if target in {"linux", "remote"} else 8080
    for key, default in [
        ("web_port", default_web_port),
        ("radio_port", 8088),
        ("ais_web_port", 8100),
        ("ais_service_port", 8118),
    ]:
        cfg["network"][key] = int(ask(key.replace("_", " ").title(), str(default)))

    heading("Review")
    print(f"Station:            {cfg['station']['name']}")
    print(f"Platform:           {target}")
    print(f"Install mode:       {cfg['installation']['mode']}")
    if target == "remote":
        print(f"SSH host:           {cfg['ssh']['host']}:{cfg['ssh']['port']}")
        print(f"SSH user:           {cfg['ssh']['username']}")
    print(f"Receiver layout:    {layout} SDRs")
    print(f"ADS-B serial:       {adsb}")
    print(f"AIS serial:         {ais}")
    print(f"Voice serial:       {voice}")
    print(f"Voice shares AIS:   {'Yes' if layout == '2' else 'No'}")
    print(f"Browser host:       {cfg['network']['public_host']}")
    print(f"Web port:           {cfg['network']['web_port']}")
    print()
    print("No passwords, feed tokens, or private-key contents will be saved.")
    if "ota_consent" in cfg["installation"]:
        consent = cfg["installation"]["ota_consent"]
        print("Remote management consent: " + ("Yes" if consent["remote_management_consent"] else "No"))
        print("MastChain contribution consent: " + ("Yes" if consent["mastchain_consent"] else "No"))
        if consent["mastchain_consent"]:
            print("AIS-Catcher config path (local only): " + str(cfg["installation"].get("ota_aiscatcher_config_path", "")))

    if not yes_no("Save this setup preview?", True):
        print("RESULT: Setup cancelled. No changes made.")
        return 0

    out = Path(__file__).with_name("shipwatch.setup-preview.json")
    out.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    heading("Results")
    print("PASS: Setup answers validated")
    print(f"PASS: Configuration preview saved to {out}")
    print("RESULT: No system changes were made")
    print("NEXT: Phase 2 will perform preflight checks and installation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
