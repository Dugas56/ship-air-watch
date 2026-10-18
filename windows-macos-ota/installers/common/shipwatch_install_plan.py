#!/usr/bin/env python3
"""
Shipwatch Installer - Phase 3 Installation Plan
Builds a complete dry-run installation plan from validated setup data.
Makes no system changes.
"""

from __future__ import annotations

import json
import platform
import sys
from pathlib import Path


def load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def add(plan: list[dict], stage: str, action: str, detail: str, critical: bool = True):
    plan.append({
        "stage": stage,
        "action": action,
        "detail": detail,
        "critical": critical,
    })


def linux_plan(cfg: dict, plan: list[dict], remote: bool):
    prefix = "remote Linux/Pi" if remote else "local Linux/Pi"

    add(plan, "preflight", "verify_privileges",
        f"Verify sudo/root privileges on {prefix}.")
    add(plan, "backup", "backup_existing",
        "Create timestamped backups of existing Shipwatch configuration and service files.")
    add(plan, "dependencies", "install_packages",
        "Install/verify Python, FFmpeg, rtl-sdr tools, AIS-Catcher, readsb, tar1090 and Lighttpd.")
    add(plan, "directories", "create_paths",
        "Create application, configuration, data, log, web and backup directories.")

    if remote:
        ssh = cfg.get("ssh", {})
        add(plan, "remote", "ssh_connect",
            f"Connect to {ssh.get('username')}@{ssh.get('host')}:{ssh.get('port',22)}.")
        add(plan, "remote", "copy_payload",
            "Copy Shipwatch installer payload to the remote host over SSH/SCP.")

    add(plan, "receivers", "assign_adsb",
        f"Configure ADS-B receiver serial {cfg['receivers']['adsb']['serial']}.")
    add(plan, "receivers", "assign_ais",
        f"Configure AIS receiver serial {cfg['receivers']['ais']['serial']}.")

    voice = cfg["receivers"]["voice"]
    if voice.get("dedicated"):
        add(plan, "receivers", "assign_voice",
            f"Configure dedicated Voice receiver serial {voice['serial']}.")
    else:
        add(plan, "receivers", "configure_shared_voice",
            f"Voice shares AIS receiver serial {voice['serial']} with safety lease "
            f"{voice.get('voice_lease_seconds',900)} seconds.")

    add(plan, "adsb", "configure_readsb",
        "Create readsb configuration using selected ADS-B serial and station coordinates.")
    add(plan, "adsb", "configure_tar1090",
        "Install/configure tar1090 aircraft map and JSON endpoint.")
    add(plan, "ais", "configure_aiscatcher",
        "Create AIS-Catcher configuration using selected AIS serial.")
    add(plan, "voice", "install_shipwatch_air",
        "Install Shipwatch voice/scanner service and receiver ownership policy.")
    add(plan, "web", "install_web_ui",
        "Install Shipwatch web interface and local proxies/endpoints.")
    add(plan, "services", "install_systemd",
        "Install/enable systemd units for Shipwatch services.")
    add(plan, "ota", "install_dormant_runtime",
        "Install the signed OTA agent and systemd definitions; leave enrollment and polling disabled until explicit consent and controller provisioning.")
    add(plan, "firewall", "configure_firewall",
        "Open only configured Shipwatch LAN ports when a host firewall is active.",
        critical=False)
    add(plan, "health", "validate",
        "Verify services, ports, receiver ownership, JSON endpoints and startup state.")


def windows_plan(cfg: dict, plan: list[dict]):
    add(plan, "preflight", "verify_admin",
        "Verify Windows administrator privileges.")
    add(plan, "backup", "backup_existing",
        "Create timestamped backup of any existing Shipwatch installation.")
    add(plan, "dependencies", "install_runtime",
        "Install/verify Python runtime, FFmpeg, RTL-SDR driver/tools, AIS/readsb-compatible components and Shipwatch web runtime.")
    add(plan, "directories", "create_paths",
        "Create Program Files and ProgramData Shipwatch directories.")
    add(plan, "drivers", "verify_sdr_driver",
        "Verify supported RTL-SDR USB driver binding for all configured receivers.")
    add(plan, "receivers", "assign_roles",
        "Bind ADS-B, AIS and optional Voice roles to configured receiver serial numbers.")
    add(plan, "services", "install_windows_services",
        "Install Shipwatch receiver/web background services with automatic startup.")
    add(plan, "ota", "install_windows_ota_task",
        "After consent and signed enrollment, register the protected OTA check with Task Scheduler.")
    add(plan, "web", "install_web_ui",
        "Install Shipwatch web UI and localhost/LAN endpoints.")
    add(plan, "firewall", "windows_firewall",
        "Create narrowly scoped Windows Defender Firewall rules for selected ports.",
        critical=False)
    add(plan, "health", "validate",
        "Verify services, SDR serials, ports, maps, radio endpoint and startup behavior.")


def mac_plan(cfg: dict, plan: list[dict]):
    add(plan, "preflight", "verify_admin",
        "Verify macOS administrator privileges.")
    add(plan, "backup", "backup_existing",
        "Create timestamped backup of any existing Shipwatch installation.")
    add(plan, "dependencies", "install_runtime",
        "Install/verify Python, FFmpeg, RTL-SDR tools and required receiver components.")
    add(plan, "directories", "create_paths",
        "Create /Applications and /Library/Application Support Shipwatch directories.")
    add(plan, "receivers", "assign_roles",
        "Bind ADS-B, AIS and optional Voice roles to configured receiver serial numbers.")
    add(plan, "services", "install_launchd",
        "Install launchd daemons/agents for Shipwatch receiver and web services.")
    add(plan, "ota", "install_macos_ota_daemon",
        "After consent and signed enrollment, register the protected OTA LaunchDaemon.")
    add(plan, "web", "install_web_ui",
        "Install Shipwatch web UI and local/LAN endpoints.")
    add(plan, "firewall", "mac_firewall",
        "Configure local firewall access only where required.",
        critical=False)
    add(plan, "health", "validate",
        "Verify launchd jobs, SDR serials, ports, maps, radio endpoint and startup behavior.")


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: shipwatch_install_plan.py shipwatch.setup-preview.json")
        return 2

    cfg = load(sys.argv[1])
    target = cfg.get("installation", {}).get("platform", "")
    plan: list[dict] = []

    if target == "windows":
        windows_plan(cfg, plan)
    elif target == "mac":
        mac_plan(cfg, plan)
    elif target == "linux":
        linux_plan(cfg, plan, False)
    elif target == "remote":
        linux_plan(cfg, plan, True)
    else:
        print(f"FAIL: UNSUPPORTED_PLATFORM={target}")
        return 2

    output = Path(sys.argv[1]).with_name("shipwatch.install-plan.json")
    output.write_text(json.dumps({
        "schema_version": 1,
        "platform": target,
        "receiver_layout": cfg.get("receiver_layout"),
        "steps": plan,
        "destructive_changes": False
    }, indent=2), encoding="utf-8")

    print("==============================================================")
    print("SHIPWATCH PHASE 3 - INSTALL PLAN")
    print("==============================================================")
    for idx, step in enumerate(plan, 1):
        flag = "REQUIRED" if step["critical"] else "OPTIONAL"
        print(f"{idx:02d}. [{flag}] {step['stage']}: {step['detail']}")
    print("==============================================================")
    print(f"PASS: INSTALL_PLAN_CREATED={output}")
    print("RESULT: NO_SYSTEM_CHANGES_MADE")
    print("NEXT: REVIEW_PLAN_BEFORE_INSTALL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
