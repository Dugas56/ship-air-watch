#!/usr/bin/env python3
"""Shipwatch OTA receiver agent. Applies only validated AIS-Catcher HTTP output settings."""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import platform
import secrets
import shutil
import stat
import subprocess
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, build_opener

try:
    from nacl import bindings
    from nacl.signing import SigningKey, VerifyKey
except ImportError as exc:  # pragma: no cover - installation dependency
    raise SystemExit("PyNaCl is required by the Shipwatch OTA agent.") from exc


MAX_RESPONSE = 65536
MAX_CONFIG = 2 * 1024 * 1024


class RejectRedirects(HTTPRedirectHandler):
    """Never forward a device signature or identity to a redirect target."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("The OTA controller attempted to redirect the request.")


def validate_api_url(value: str) -> str:
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment):
        raise ValueError("The OTA controller URL must be an HTTPS base URL without credentials or query data.")
    return value.rstrip("/") + "/"


def read_json(path: Path) -> dict:
    if path.stat().st_size > MAX_CONFIG:
        raise ValueError("JSON file exceeded its size limit.")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object.")
    return value


def canonical_json(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def secret_file(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
    if os.name == "nt":
        restrict_windows_file(path)


def restrict_windows_file(path: Path) -> None:
    try:
        subprocess.run(
            ["icacls.exe", str(path), "/inheritance:r", "/grant:r", "*S-1-5-18:F", "*S-1-5-32-544:F"],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15,
        )
    except Exception as exc:
        path.unlink(missing_ok=True)
        raise RuntimeError("Could not restrict access to the OTA private data.") from exc


def load_keys(cfg: dict):
    key_path = Path(cfg["device_signing_key_file"])
    seed = base64.b64decode(key_path.read_text(encoding="ascii").strip(), validate=True)
    signing_key = SigningKey(seed)
    pinned = VerifyKey(base64.b64decode(cfg["server_verify_key_b64"], validate=True))
    return signing_key, pinned


def initialize(
    data_dir: Path,
    api_url: str,
    server_key_b64: str,
    aiscatcher_config: str = "",
    allowed_config_root: str = "",
) -> Path:
    api_url = validate_api_url(api_url)
    VerifyKey(base64.b64decode(server_key_b64, validate=True))
    device_id = str(uuid.uuid4())
    key = SigningKey.generate()
    key_path = data_dir / "device-signing-seed.b64"
    config_path = data_dir / "agent.json"
    data_dir.mkdir(parents=True, exist_ok=True)
    secret_file(key_path, base64.b64encode(bytes(key)) + b"\n")
    config = {
        "device_id": device_id,
        "api_url": api_url,
        "server_verify_key_b64": server_key_b64,
        "device_signing_key_file": str(key_path),
        "aiscatcher_config": aiscatcher_config,
        "allowed_config_roots": [allowed_config_root] if allowed_config_root else [],
    }
    fd = os.open(config_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(config, stream, indent=2)
        stream.write("\n")
    if os.name == "nt":
        restrict_windows_file(config_path)
    else:
        os.chmod(config_path, 0o600)
    return config_path


def signed_request(cfg: dict, signing_key: SigningKey, action: str, fields: dict) -> dict:
    api_url = validate_api_url(str(cfg.get("api_url", "")))
    body = {**fields, "action": action, "device_id": cfg["device_id"], "timestamp": int(time.time()), "nonce": base64.b64encode(secrets.token_bytes(16)).decode("ascii")}
    raw = canonical_json(body)
    request = urllib.request.Request(
        api_url + "?" + urlencode({"action": action}),
        data=raw,
        headers={"Content-Type": "application/json", "X-Shipwatch-Signature": base64.b64encode(signing_key.sign(raw).signature).decode("ascii")},
        method="POST",
    )
    with build_opener(RejectRedirects()).open(request, timeout=30) as response:
        data = response.read(MAX_RESPONSE + 1)
    if len(data) > MAX_RESPONSE:
        raise ValueError("Controller response exceeded its size limit.")
    return json.loads(data)


def verify_reply(reply: dict, server_key: VerifyKey) -> dict:
    raw = base64.b64decode(reply["payload"], validate=True)
    server_key.verify(raw, base64.b64decode(reply["signature"], validate=True))
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("Invalid signed controller response.")
    return payload


def acknowledge(cfg: dict, signing_key: SigningKey, server_key: VerifyKey, update_id: int, result: str) -> None:
    receipt = verify_reply(
        signed_request(cfg, signing_key, "ack", {"update_id": update_id, "result": result}),
        server_key,
    )
    if receipt.get("status") not in {"recorded", "already_recorded"}:
        raise ValueError("Controller did not confirm the update acknowledgement.")


def envelope_bytes(payload: dict) -> bytes:
    return canonical_json({
        "version": payload["version"],
        "device_id": payload["device_id"],
        "sequence": payload["sequence"],
        "expires_at": payload["expires_at"],
        "sealed_payload": payload["sealed_payload"],
    })


def open_update(cfg: dict, payload: dict, signing_key: SigningKey, server_key: VerifyKey) -> dict:
    if payload.get("status") != "update" or payload.get("version") != 1 or payload.get("device_id") != cfg["device_id"]:
        raise ValueError("Update envelope is not for this receiver.")
    server_key.verify(envelope_bytes(payload), base64.b64decode(payload["envelope_signature"], validate=True))
    expiry = dt.datetime.fromisoformat(payload["expires_at"].replace("Z", "+00:00"))
    if expiry <= dt.datetime.now(dt.timezone.utc):
        raise ValueError("Update has expired.")
    box_secret = bindings.crypto_sign_ed25519_sk_to_curve25519(bytes(signing_key) + bytes(signing_key.verify_key))
    sealed = base64.b64decode(payload["sealed_payload"], validate=True)
    clear = bindings.crypto_box_seal_open(sealed, bindings.crypto_sign_ed25519_pk_to_curve25519(bytes(signing_key.verify_key)), box_secret)
    update = json.loads(clear)
    if update.get("operation") != "replace_shipwatch_mastchain_http_output":
        raise ValueError("Unsupported OTA operation.")
    output = update.get("http_output")
    if not isinstance(output, dict) or output.get("protocol") != "AISCATCHER" or output.get("active") is not True:
        raise ValueError("Invalid AIS-Catcher output settings.")
    endpoint = urlsplit(str(output.get("url", "")))
    station_id = str(output.get("id", ""))
    userpwd = str(output.get("userpwd", ""))
    if endpoint.scheme != "https" or not endpoint.hostname or endpoint.username or endpoint.password or endpoint.fragment:
        raise ValueError("MastChain feed URL must be a valid HTTPS endpoint.")
    if not station_id or len(station_id) > 100 or any(ord(ch) < 32 for ch in station_id):
        raise ValueError("MastChain station identifier is invalid.")
    if not userpwd or len(userpwd) > 800 or any(ord(ch) < 32 for ch in userpwd):
        raise ValueError("Incomplete MastChain endpoint configuration.")
    interval = output.get("interval")
    if not isinstance(interval, int) or interval < 1 or interval > 86400:
        raise ValueError("MastChain upload interval is invalid.")
    return update


def atomic_backup_write(path: Path, content: bytes) -> Path:
    if not path.is_file() or path.stat().st_size > MAX_CONFIG:
        raise ValueError("AIS-Catcher configuration is missing or too large.")
    original_stat = path.stat()
    backup = path.with_name(path.name + ".shipwatch-backup-" + time.strftime("%Y%m%d-%H%M%S", time.gmtime()))
    shutil.copy2(path, backup)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        shutil.copystat(path, temp_name)
        if os.name != "nt":
            os.chmod(temp_name, stat.S_IMODE(original_stat.st_mode))
            if hasattr(os, "geteuid") and os.geteuid() == 0:
                os.chown(temp_name, original_stat.st_uid, original_stat.st_gid)
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
    return backup


def save_state(cfg: dict, state: dict) -> None:
    config_path = Path(cfg["agent_config_path"])
    state_path = config_path.with_name("state.json")
    fd, temp_name = tempfile.mkstemp(prefix="state.", suffix=".tmp", dir=str(state_path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(state, stream)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, state_path)
        if os.name == "nt":
            restrict_windows_file(state_path)
        else:
            os.chmod(state_path, 0o600)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def disable_agent(cfg: dict, status: str) -> None:
    save_state(cfg, {"disabled": True, "status": status})
    try:
        Path(cfg["device_signing_key_file"]).unlink()
    except OSError:
        pass


def apply_update(cfg: dict, update: dict) -> None:
    path = Path(cfg["aiscatcher_config"]).resolve(strict=True)
    allowed_roots = [Path(value).resolve() for value in cfg.get("allowed_config_roots", [])]
    if not allowed_roots or not any(path == root or root in path.parents for root in allowed_roots):
        raise ValueError("Configured AIS-Catcher file is outside the permitted path.")
    current = read_json(path)
    outputs = current.get("http", [])
    if not isinstance(outputs, list):
        raise ValueError("AIS-Catcher HTTP output section is not a list.")
    item = update["http_output"]
    index = next((i for i, row in enumerate(outputs) if isinstance(row, dict) and row.get("description") == "Shipwatch MastChain"), None)
    if index is None:
        outputs.append(item)
    else:
        outputs[index] = item
    current["http"] = outputs
    content = (json.dumps(current, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    atomic_backup_write(path, content)
    try:
        restart_receiver()
    except Exception:
        backups = sorted(path.parent.glob(path.name + ".shipwatch-backup-*"), key=lambda item: item.stat().st_mtime)
        if backups:
            restore_fd, restore_name = tempfile.mkstemp(prefix=path.name + ".restore-", suffix=".tmp", dir=str(path.parent))
            try:
                with os.fdopen(restore_fd, "wb") as stream:
                    stream.write(backups[-1].read_bytes())
                    stream.flush()
                    os.fsync(stream.fileno())
                shutil.copystat(path, restore_name)
                if os.name != "nt":
                    os.chmod(restore_name, stat.S_IMODE(path.stat().st_mode))
                    if hasattr(os, "geteuid") and os.geteuid() == 0:
                        old_stat = path.stat()
                        os.chown(restore_name, old_stat.st_uid, old_stat.st_gid)
                os.replace(restore_name, path)
            except Exception:
                try:
                    os.unlink(restore_name)
                except OSError:
                    pass
                raise
            try:
                restart_receiver()
            except Exception:
                pass
        raise


def restart_receiver() -> None:
    system = platform.system()
    if system == "Linux":
        subprocess.run(["systemctl", "restart", "ais-catcher.service"], check=True, timeout=90, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            state = subprocess.run(["systemctl", "is-active", "--quiet", "ais-catcher.service"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if state.returncode == 0:
                return
            time.sleep(2)
        raise RuntimeError("AIS-Catcher did not become active after restart.")
    elif system == "Darwin":
        command = ["launchctl", "kickstart", "-k", "system/com.shipwatch.aiscatcher"]
    elif system == "Windows":
        command = ["powershell", "-NoProfile", "-NonInteractive", "-Command", "Restart-Service -Name 'AIS-Catcher' -ErrorAction Stop; (Get-Service -Name 'AIS-Catcher').WaitForStatus('Running', [TimeSpan]::FromSeconds(60))"]
    else:
        raise RuntimeError("Unsupported service platform.")
    subprocess.run(command, check=True, timeout=90, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def once(cfg: dict, signing_key: SigningKey, server_key: VerifyKey) -> None:
    state_path = Path(cfg["agent_config_path"]).with_name("state.json")
    local_state = read_json(state_path) if state_path.exists() else {}
    if local_state.get("disabled") is True:
        return
    response = verify_reply(signed_request(cfg, signing_key, "poll", {}), server_key)
    state = response.get("status")
    if state in {"rejected", "revoked"}:
        disable_agent(cfg, str(state))
        return
    if state != "update":
        return
    try:
        update = open_update(cfg, response, signing_key, server_key)
        state = read_json(state_path) if state_path.exists() else {}
        last_sequence = int(state.get("last_applied_sequence", 0))
        sequence = int(response["sequence"])
        if sequence == last_sequence:
            acknowledge(cfg, signing_key, server_key, int(response["update_id"]), "applied")
            return
        if sequence < last_sequence:
            raise ValueError("Update sequence moved backwards.")
        apply_update(cfg, update)
        save_state(cfg, {"last_applied_sequence": sequence})
        result = "applied"
    except Exception:
        result = "failed"
    acknowledge(cfg, signing_key, server_key, int(response["update_id"]), result)


def enroll(cfg: dict, signing_key: SigningKey, server_key: VerifyKey, consent: dict) -> None:
    if consent.get("remote_management_consent") is not True:
        raise ValueError("Remote management consent is required before enrollment.")
    fields = {
        "consent_version": str(consent.get("consent_version", "")),
        "station_name": str(consent["station_name"])[:100],
        "remote_management_consent": True,
        "mastchain_consent": consent.get("mastchain_consent") is True,
        "signing_public_key": base64.b64encode(bytes(signing_key.verify_key)).decode("ascii"),
    }
    if fields["mastchain_consent"]:
        fields["latitude"] = consent["latitude"]
        fields["longitude"] = consent["longitude"]
    payload = verify_reply(signed_request(cfg, signing_key, "enroll", fields), server_key)
    if payload.get("device_id") != cfg["device_id"] or payload.get("status") not in {"pending", "approved"}:
        raise ValueError("Controller did not confirm pending or existing enrollment.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Shipwatch outbound-only OTA receiver agent")
    parser.add_argument("--config")
    parser.add_argument("--initialize", action="store_true", help="Create a device identity with a pinned controller key.")
    parser.add_argument("--data-dir")
    parser.add_argument("--api-url")
    parser.add_argument("--server-verify-key-b64")
    parser.add_argument("--aiscatcher-config", default="")
    parser.add_argument("--allowed-config-root", default="")
    parser.add_argument("--enroll-consent-json", help="One-time installer consent file; never pass credentials here.")
    args = parser.parse_args()
    if args.initialize:
        if not args.data_dir or not args.api_url or not args.server_verify_key_b64:
            raise SystemExit("Initialization requires --data-dir, an HTTPS --api-url, and a pinned server key.")
        print(str(initialize(
            Path(args.data_dir), args.api_url, args.server_verify_key_b64,
            args.aiscatcher_config, args.allowed_config_root,
        )))
        return 0
    if not args.config:
        raise SystemExit("--config is required unless --initialize is used.")
    cfg = read_json(Path(args.config))
    cfg["agent_config_path"] = str(Path(args.config).resolve())
    if not str(cfg.get("api_url", "")).startswith("https://"):
        raise SystemExit("The OTA API must use HTTPS.")
    state_path = Path(cfg["agent_config_path"]).with_name("state.json")
    if state_path.exists() and read_json(state_path).get("disabled") is True:
        return 0
    signing_key, server_key = load_keys(cfg)
    if args.enroll_consent_json:
        enroll(cfg, signing_key, server_key, read_json(Path(args.enroll_consent_json)))
        return 0
    try:
        once(cfg, signing_key, server_key)
    except Exception:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
