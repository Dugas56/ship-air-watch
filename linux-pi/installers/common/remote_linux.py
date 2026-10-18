#!/usr/bin/env python3
"""
Shipwatch remote Linux/Pi installer handoff.

Packages the minimal Linux installer payload, copies it over SSH/SCP,
and invokes the Linux installer on the remote host.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path


HERE=Path(__file__).resolve()
PRODUCT_ROOT=HERE.parents[2]


class RemoteInstallError(RuntimeError):
    pass


def emit(kind: str,msg: str)->None:
    print(f"{kind}: {msg}",flush=True)


def load_config(path: str)->dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def ssh_base(cfg: dict)->list[str]:
    s=cfg.get("ssh",{})
    ssh=s.get("ssh_path") or shutil.which("ssh")
    if not ssh:
        raise RemoteInstallError("SSH client not found on this computer")
    cmd=[
        ssh,
        "-p",str(s.get("port",22)),
        "-o","ConnectTimeout=8",
    ]
    key=s.get("key_path")
    if key:
        cmd += ["-i",key]
    cmd += [f"{s.get('username')}@{s.get('host')}"]
    return cmd


def scp_base(cfg: dict)->list[str]:
    s=cfg.get("ssh",{})
    scp=s.get("scp_path") or shutil.which("scp")
    if not scp:
        raise RemoteInstallError("SCP client not found on this computer")
    cmd=[scp,"-P",str(s.get("port",22))]
    key=s.get("key_path")
    if key:
        cmd += ["-i",key]
    return cmd


def run(cmd: list[str],check: bool=True)->subprocess.CompletedProcess:
    emit("RESULT","RUN="+" ".join(cmd))
    p=subprocess.run(cmd,text=True)
    if check and p.returncode:
        raise RemoteInstallError(f"command failed exit={p.returncode}")
    return p


def create_bundle(config_path: str,work: Path)->Path:
    staging=work/"shipwatch-installer"
    staging.mkdir(parents=True)

    wanted=[
        PRODUCT_ROOT/"installers"/"raspberry-pi",
        PRODUCT_ROOT/"runtime"/"linux",
        PRODUCT_ROOT/"runtime"/"common",
    ]

    for src in wanted:
        rel=src.relative_to(PRODUCT_ROOT)
        dst=staging/rel
        shutil.copytree(src,dst)

    shutil.copy2(config_path,staging/"shipwatch.json")

    archive=work/"shipwatch-installer.tar.gz"
    with tarfile.open(archive,"w:gz") as tf:
        tf.add(staging,arcname="shipwatch-installer")

    emit("PASS",f"REMOTE_BUNDLE_CREATED={archive}")
    return archive


def remote_exec(cfg: dict,command: str,tty: bool=False)->int:
    cmd=ssh_base(cfg)
    if tty:
        cmd.insert(1,"-t")
    cmd.append(command)
    return run(cmd,check=False).returncode


def verify_remote(cfg: dict)->None:
    s=cfg.get("ssh",{})
    if not s.get("host") or not s.get("username"):
        raise RemoteInstallError("Remote SSH host and username are required")

    rc=remote_exec(
        cfg,
        "printf 'SHIPWATCH_REMOTE_OK\n'; uname -s; uname -m; command -v python3 || true"
    )
    if rc:
        raise RemoteInstallError("Remote SSH verification failed")
    emit("PASS","REMOTE_SSH_VERIFIED")


def copy_bundle(cfg: dict,archive: Path)->None:
    s=cfg["ssh"]
    target=f"{s['username']}@{s['host']}:/tmp/shipwatch-installer.tar.gz"
    run([*scp_base(cfg),str(archive),target])

    rc=remote_exec(
        cfg,
        "rm -rf /tmp/shipwatch-installer && "
        "mkdir -p /tmp/shipwatch-installer-stage && "
        "tar -xzf /tmp/shipwatch-installer.tar.gz -C /tmp && "
        "test -f /tmp/shipwatch-installer/installers/raspberry-pi/install_linux.py"
    )
    if rc:
        raise RemoteInstallError("Remote bundle extraction failed")
    emit("PASS","REMOTE_PAYLOAD_READY")


def run_remote_installer(cfg: dict,apply: bool)->int:
    script="/tmp/shipwatch-installer/installers/raspberry-pi/install_linux.py"
    config="/tmp/shipwatch-installer/shipwatch.json"

    if apply:
        command=f"sudo python3 {script} {config} --apply"
        rc=remote_exec(cfg,command,tty=True)
    else:
        command=f"python3 {script} {config}"
        rc=remote_exec(cfg,command,tty=False)

    return rc


def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("--apply",action="store_true")
    args=ap.parse_args()

    cfg=load_config(args.config)
    if cfg.get("installation",{}).get("mode")!="remote":
        emit("FAIL","CONFIG_IS_NOT_REMOTE_INSTALL")
        return 2

    work=Path(tempfile.mkdtemp(prefix="shipwatch-remote-"))
    try:
        verify_remote(cfg)
        archive=create_bundle(args.config,work)
        copy_bundle(cfg,archive)

        rc=run_remote_installer(cfg,args.apply)
        if rc:
            emit("FAIL",f"REMOTE_INSTALLER_EXIT={rc}")
            emit("RESULT","REMOTE_PAYLOAD_LEFT_IN_/tmp/shipwatch-installer")
            return rc

        emit("PASS","REMOTE_INSTALLER_COMPLETE")
        remote_exec(
            cfg,
            "rm -rf /tmp/shipwatch-installer /tmp/shipwatch-installer.tar.gz "
            "/tmp/shipwatch-installer-stage"
        )
        emit("PASS","REMOTE_TEMP_PAYLOAD_REMOVED")
        emit("RESULT",f"MODE={'APPLY' if args.apply else 'DRY_RUN'}")
        emit("NEXT","OPEN_SHIPWATCH_IN_BROWSER" if args.apply else "REVIEW_THEN_RUN_WITH_--apply")
        return 0
    except Exception as exc:
        emit("FAIL",f"REMOTE_HANDOFF={exc}")
        emit("NEXT","REVIEW_SSH_AND_REMOTE_HOST_SETTINGS")
        return 1
    finally:
        shutil.rmtree(work,ignore_errors=True)


if __name__=="__main__":
    raise SystemExit(main())
