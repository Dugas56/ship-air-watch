#!/usr/bin/env python3
"""
Shipwatch Installer Launcher

Flow:
1. Guided setup
2. Read-only preflight
3. Installation-plan review
4. Explicit Install Now confirmation
5. Platform dispatch
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


HERE=Path(__file__).resolve().parent
PRODUCT_ROOT=HERE.parents[1]

SETUP=HERE/"shipwatch_setup.py"
PREFLIGHT=HERE/"shipwatch_preflight.py"
PLAN=HERE/"shipwatch_install_plan.py"
REMOTE_LINUX=HERE/"remote_linux.py"
LINUX_INSTALLER=PRODUCT_ROOT/"installers"/"raspberry-pi"/"install_linux.py"
WINDOWS_INSTALLER=PRODUCT_ROOT/"installers"/"windows"/"install_windows.py"
MAC_INSTALLER=PRODUCT_ROOT/"installers"/"macos"/"install_macos.py"
PREVIEW=HERE/"shipwatch.setup-preview.json"


def run_script(script: Path,*args: str)->int:
    return subprocess.call([sys.executable,str(script),*args])


def yes_no(prompt: str,default: bool=False)->bool:
    suffix="[Y/n]" if default else "[y/N]"
    value=input(f"{prompt} {suffix}: ").strip().lower()
    if not value:
        return default
    return value in {"y","yes"}


def run_local_linux(config: Path)->int:
    cmd=[sys.executable,str(LINUX_INSTALLER),str(config),"--apply"]

    if os.geteuid()!=0:
        sudo=shutil.which("sudo")
        if not sudo:
            print("FAIL: SUDO_NOT_AVAILABLE")
            return 2
        cmd=[sudo,*cmd]

    return subprocess.call(cmd)


def dispatch_install(config: Path)->int:
    cfg=json.loads(config.read_text(encoding="utf-8"))
    target=cfg.get("installation",{}).get("platform")
    mode=cfg.get("installation",{}).get("mode")

    if mode=="remote" or target=="remote":
        return run_script(REMOTE_LINUX,str(config),"--apply")

    if target=="linux":
        if platform.system()!="Linux":
            print("FAIL: LOCAL_LINUX_SELECTED_ON_NON_LINUX_COMPUTER")
            print("NEXT: Choose remote Raspberry Pi / Linux in the setup wizard")
            return 2
        return run_local_linux(config)

    if target=="windows":
        print("FAIL: WINDOWS_APPLY_ENGINE_NOT_READY")
        print("NEXT: Linux/Pi installer is ready first; Windows packaging follows")
        return 2

    if target=="mac":
        print("FAIL: MACOS_APPLY_ENGINE_NOT_READY")
        print("NEXT: Linux/Pi installer is ready first; macOS packaging follows")
        return 2

    print(f"FAIL: UNKNOWN_INSTALL_TARGET={target}")
    return 2


def run_ota_only()->int:
    """Provision optional OTA on an existing Windows/macOS receiver."""
    # Fail before collecting consent or touching the host when no release has
    # been pinned into this installer bundle. A successful-looking no-op here
    # would imply that OTA is available when enrollment cannot work.
    from shipwatch_setup import available_ota_release
    if not available_ota_release():
        print("FAIL: VERIFIED_OTA_CONTROLLER_RELEASE_CONFIG_MISSING")
        print("NEXT: Deploy the OTA controller, complete its server preflight, and pin its HTTPS URL and signing key in product/runtime/common/ota-release-config.json")
        return 2

    rc=run_script(SETUP)
    if rc:
        print("FAIL: SETUP_WIZARD_DID_NOT_COMPLETE")
        return rc
    if not PREVIEW.exists():
        print("FAIL: SETUP_PREVIEW_NOT_FOUND")
        return 2
    cfg=json.loads(PREVIEW.read_text(encoding="utf-8"))
    target=cfg.get("installation",{}).get("platform")
    expected={"windows":"Windows","mac":"Darwin"}
    if target not in expected:
        print("FAIL: OTA_ONLY_SUPPORTS_WINDOWS_AND_MACOS")
        return 2
    if platform.system()!=expected[target]:
        print("FAIL: RUN_OTA_SETUP_ON_THE_SELECTED_RECEIVER_COMPUTER")
        return 2
    consent=cfg.get("installation",{}).get("ota_consent",{})
    if consent.get("remote_management_consent") is not True:
        print("RESULT: OTA_NOT_ENROLLED_NO_REMOTE_MANAGEMENT_CONSENT")
        return 0
    print("\nThis operation installs and enrolls only the OTA agent on an existing AIS-Catcher receiver.")
    print("It does not install or configure the Shipwatch receiver application.")
    if not yes_no("Install the OTA agent now?",False):
        print("RESULT: OTA_SETUP_NOT_STARTED")
        return 0
    script=WINDOWS_INSTALLER if target=="windows" else MAC_INSTALLER
    command=[sys.executable,str(script),str(PREVIEW),"--ota-only"]
    if target=="mac" and os.geteuid()!=0:
        sudo=shutil.which("sudo")
        if not sudo:
            print("FAIL: SUDO_NOT_AVAILABLE")
            return 2
        command=[sudo,*command]
    rc=subprocess.call(command)
    if rc:
        return rc
    print("PASS: OTA_AGENT_SETUP_COMPLETE")
    return 0


def main()->int:
    if "--ota-only" in sys.argv[1:]:
        return run_ota_only()
    print("SHIPWATCH INSTALLER")
    print("===================")

    rc=run_script(SETUP)
    if rc:
        print("FAIL: SETUP_WIZARD_DID_NOT_COMPLETE")
        return rc

    if not PREVIEW.exists():
        print("FAIL: SETUP_PREVIEW_NOT_FOUND")
        return 2

    rc=run_script(PREFLIGHT,str(PREVIEW))
    if rc:
        print("FAIL: PREFLIGHT_BLOCKED_INSTALL")
        return rc

    rc=run_script(PLAN,str(PREVIEW))
    if rc:
        print("FAIL: INSTALL_PLAN_NOT_CREATED")
        return rc

    print()
    print("PASS: SETUP_PREFLIGHT_AND_PLAN_COMPLETE")
    print("RESULT: NO_SYSTEM_CHANGES_MADE")

    if not yes_no("Install Shipwatch now?",False):
        print("RESULT: INSTALL_NOT_STARTED")
        print("NEXT: Run the installer again when ready")
        return 0

    print("RESULT: INSTALL_CONFIRMED")
    rc=dispatch_install(PREVIEW)

    if rc:
        print(f"FAIL: INSTALL_EXIT={rc}")
        return rc

    print("PASS: SHIPWATCH_INSTALL_COMPLETE")
    print("NEXT: Open Shipwatch in your browser")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
