#!/usr/bin/env python3
"""
Shipwatch macOS platform adapter.
Dry-run by default.
"""
from __future__ import annotations
import argparse
import os
import shutil
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parents[1] / "common"
sys.path.insert(0,str(HERE))
from platform_common import load_config,banner,emit
from ota_platform import install_ota, OtaInstallError

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("--apply",action="store_true")
    ap.add_argument("--ota-only",action="store_true",help="Enroll this existing macOS receiver in the optional OTA service.")
    args=ap.parse_args()
    cfg=load_config(args.config)
    banner("SHIPWATCH MACOS INSTALLER")
    if args.ota_only:
        if os.geteuid()!=0:
            emit("FAIL","RUN_OTA_SETUP_WITH_SUDO")
            return 2
        try:
            install_ota(cfg,"Darwin")
        except OtaInstallError as exc:
            emit("FAIL",str(exc))
            return 2
        return 0
    emit("RESULT",f"MODE={'APPLY' if args.apply else 'DRY_RUN'}")
    emit("PASS" if os.geteuid()==0 else "WARN",f"ADMIN={'YES' if os.geteuid()==0 else 'NO'}")
    for cmd in ("python3","ffmpeg","rtl_test"):
        emit("PASS" if shutil.which(cmd) else "WARN",f"TOOL_{cmd}={'FOUND' if shutil.which(cmd) else 'MISSING'}")
    if not args.apply:
        emit("PASS","DRY_RUN_COMPLETE")
        emit("RESULT","NO_SYSTEM_CHANGES_MADE")
        emit("NEXT","REVIEW_THEN_RUN_WITH_APPLY")
        return 0
    emit("FAIL","APPLY_MODE_NOT_IMPLEMENTED_YET")
    emit("RESULT","NO_SYSTEM_CHANGES_MADE")
    return 2

if __name__=="__main__":
    raise SystemExit(main())
