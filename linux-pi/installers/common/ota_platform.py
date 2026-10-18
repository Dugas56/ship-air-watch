#!/usr/bin/env python3
"""Install and enroll the Shipwatch OTA agent on an already-configured receiver."""
from __future__ import annotations

import json
import os
import platform
import base64
import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path
from urllib.parse import urlsplit


PRODUCT_ROOT = Path(__file__).resolve().parents[2]
AGENT_SOURCE = PRODUCT_ROOT / "runtime" / "common" / "shipwatch_ota_agent.py"
REQUIREMENTS = PRODUCT_ROOT / "runtime" / "common" / "requirements-ota.txt"
WINDOWS_ADAPTER = PRODUCT_ROOT / "runtime" / "common" / "services" / "windows" / "Install-ShipwatchOtaTask.ps1"
MAC_ADAPTER = PRODUCT_ROOT / "runtime" / "common" / "services" / "macos" / "Install-ShipwatchOtaLaunchDaemon.sh"
MAC_PLIST = PRODUCT_ROOT / "runtime" / "common" / "services" / "macos" / "com.shipwatch.ota.plist.template"


class OtaInstallError(RuntimeError):
    pass


def run(command: list[str], *, timeout: int = 300, quiet: bool = False) -> None:
    try:
        result = subprocess.run(
            command, check=False, timeout=timeout,
            stdout=subprocess.DEVNULL if quiet else None,
            stderr=subprocess.DEVNULL if quiet else None,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise OtaInstallError("A required OTA setup command could not be completed.") from exc
    if result.returncode:
        raise OtaInstallError("A required OTA setup command failed.")


def protect_windows_directory(path: Path) -> None:
    run([
        "icacls.exe", str(path), "/inheritance:r", "/grant:r",
        "*S-1-5-18:(OI)(CI)F", "*S-1-5-32-544:(OI)(CI)F",
    ], quiet=True)


def create_private_file(path: Path, content: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(content)
    if os.name == "nt":
        run([
            "icacls.exe", str(path), "/inheritance:r", "/grant:r",
            "*S-1-5-18:F", "*S-1-5-32-544:F",
        ], quiet=True)


def verify_aiscatcher_config(path: Path, required: bool) -> None:
    if not required:
        return
    try:
        resolved = path.resolve(strict=True)
        if not resolved.is_file() or resolved.stat().st_size > 2 * 1024 * 1024:
            raise ValueError
        value = json.loads(resolved.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or not isinstance(value.get("http"), list):
            raise ValueError
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise OtaInstallError("MastChain opt-in requires a readable AIS-Catcher JSON config with an HTTP output list.") from exc


def platform_paths(system: str) -> tuple[Path, Path]:
    if system == "Windows":
        program = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Shipwatch" / "ota"
        data = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "Shipwatch" / "OTA"
    elif system == "Darwin":
        program = Path("/Library/Shipwatch/ota")
        data = Path("/Library/Application Support/Shipwatch/OTA")
    else:
        raise OtaInstallError("The OTA platform installer supports Windows and macOS only.")
    return program, data


def install_ota(cfg: dict, system: str) -> bool:
    """Return False when the user declined remote management; otherwise enroll and register."""
    installation = cfg.get("installation", {})
    consent = installation.get("ota_consent", {})
    if consent.get("remote_management_consent") is not True:
        print("RESULT: OTA_NOT_ENROLLED_NO_REMOTE_MANAGEMENT_CONSENT")
        return False
    if not installation.get("ota_controller"):
        raise OtaInstallError("A pinned OTA controller release configuration is required before enrollment.")
    if system == "Windows" and os.name != "nt":
        raise OtaInstallError("Run the Windows OTA installer on Windows.")
    if system == "Darwin" and platform.system() != "Darwin":
        raise OtaInstallError("Run the macOS OTA installer on macOS.")

    program_dir, data_dir = platform_paths(system)
    config_value = str(installation.get("ota_aiscatcher_config_path", "")).strip()
    config_path = Path(config_value) if config_value else Path()
    mastchain = consent.get("mastchain_consent") is True
    if mastchain and not config_value:
        raise OtaInstallError("MastChain opt-in requires the local AIS-Catcher configuration path.")
    if mastchain:
        verify_aiscatcher_config(config_path, True)

    controller = installation["ota_controller"]
    api_url = str(controller.get("api_url", ""))
    parsed_url = urlsplit(api_url)
    try:
        pinned_key = base64.b64decode(str(controller.get("server_verify_key_b64", "")), validate=True)
    except (ValueError, TypeError):
        pinned_key = b""
    if (parsed_url.scheme != "https" or not parsed_url.hostname or parsed_url.username or parsed_url.password
            or parsed_url.query or parsed_url.fragment or parsed_url.path.rstrip("/") != "/shipwatch-ota/api/v1"
            or len(pinned_key) != 32):
        raise OtaInstallError("The pinned controller URL or signing key is invalid.")

    program_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        protect_windows_directory(program_dir)
        protect_windows_directory(data_dir)
    else:
        os.chmod(program_dir, 0o755)
        os.chmod(data_dir, 0o700)
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            import grp
            os.chown(program_dir, 0, grp.getgrnam("wheel").gr_gid)
            os.chown(data_dir, 0, grp.getgrnam("wheel").gr_gid)

    agent_path = program_dir / "shipwatch_ota_agent.py"
    shutil.copy2(AGENT_SOURCE, agent_path)
    python_path = program_dir / "venv" / ("Scripts/python.exe" if system == "Windows" else "bin/python")
    if not python_path.exists():
        venv.create(python_path.parent.parent, with_pip=True)
    run([str(python_path), "-m", "pip", "install", "--disable-pip-version-check", "--no-input", "-r", str(REQUIREMENTS)], quiet=True)

    agent_config = data_dir / "agent.json"
    resolved_ais_config = str(config_path.resolve()) if mastchain else ""
    if not agent_config.exists():
        run([
            str(python_path), str(agent_path), "--initialize", "--data-dir", str(data_dir),
            "--api-url", api_url,
            "--server-verify-key-b64", str(controller["server_verify_key_b64"]),
            "--aiscatcher-config", resolved_ais_config,
            "--allowed-config-root", str(Path(resolved_ais_config).parent) if resolved_ais_config else "",
        ], quiet=True)
    else:
        try:
            existing = json.loads(agent_config.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise OtaInstallError("The existing OTA identity file cannot be read; it was left unchanged.") from exc
        if (not isinstance(existing, dict)
                or not isinstance(existing.get("api_url"), str)
                or existing.get("api_url", "").rstrip("/") != api_url.rstrip("/")
                or existing.get("server_verify_key_b64") != controller["server_verify_key_b64"]
                or existing.get("aiscatcher_config", "") != resolved_ais_config):
            raise OtaInstallError("The existing OTA identity uses different controller or receiver settings; it was left unchanged.")

    marker = data_dir / "enrollment-confirmed"
    if not marker.exists():
        payload = {
            "consent_version": str(consent.get("consent_version", "")),
            "station_name": str(consent.get("station_name", cfg.get("station", {}).get("name", "Shipwatch")))[:100],
            "remote_management_consent": True,
            "mastchain_consent": mastchain,
        }
        if mastchain:
            payload["latitude"] = consent.get("latitude")
            payload["longitude"] = consent.get("longitude")
        fd, temp_name = tempfile.mkstemp(prefix="shipwatch-ota-consent-", suffix=".json", dir=data_dir)
        os.close(fd)
        consent_path = Path(temp_name)
        try:
            consent_path.unlink()
            create_private_file(consent_path, json.dumps(payload).encode("utf-8"))
            run([str(python_path), str(agent_path), "--config", str(agent_config), "--enroll-consent-json", str(consent_path)], timeout=45, quiet=True)
        finally:
            consent_path.unlink(missing_ok=True)
        create_private_file(marker, b"confirmed\n")

    if system == "Windows":
        run([
            "powershell.exe", "-NoProfile", "-NonInteractive",
            "-File", str(WINDOWS_ADAPTER), "-PythonPath", str(python_path), "-AgentPath", str(agent_path),
            "-ConfigPath", str(agent_config), "-EnrollmentMarkerPath", str(marker),
        ], quiet=True)
    else:
        shutil.copy2(MAC_PLIST, program_dir / "com.shipwatch.ota.plist")
        run(["/bin/bash", str(MAC_ADAPTER)], quiet=True)
    print("PASS: OTA_DEVICE_ENROLLED_AND_POLLING_ENABLED")
    return True
