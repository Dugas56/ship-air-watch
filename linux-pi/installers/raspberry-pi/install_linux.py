#!/usr/bin/env python3
"""
Shipwatch Linux/Pi installer engine.

Default mode is dry-run.
--apply performs staged installation work.

Safety:
- timestamped backup before touching an existing installation
- installation journal
- every stage reports PASS / FAIL / RESULT / NEXT
- build dependencies are temporary
- cleanup happens only after health checks pass
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import socket
import time
import gzip
import urllib.request
from pathlib import Path


HERE = Path(__file__).resolve()
PRODUCT_ROOT = HERE.parents[2]
RUNTIME = PRODUCT_ROOT / "runtime" / "linux"
COMMON_RUNTIME = PRODUCT_ROOT / "runtime" / "common"
WEB_RUNTIME = RUNTIME / "web"
PACKAGES = RUNTIME / "packages"
MANIFEST = RUNTIME / "runtime-manifest.json"
SOURCES = RUNTIME / "component-sources.json"
AIRCRAFT_DB_URL = "https://github.com/wiedehopf/tar1090-db/raw/refs/heads/csv/aircraft.csv.gz"
AIRCRAFT_DB_PATH = Path("/usr/share/readsb/aircraft.csv.gz")


class InstallError(RuntimeError):
    pass


def emit(kind: str, msg: str) -> None:
    print(f"{kind}: {msg}", flush=True)


def run(cmd: list[str], *, check: bool = True, cwd: str | None = None) -> subprocess.CompletedProcess:
    emit("RESULT", "RUN=" + " ".join(cmd))
    p = subprocess.run(cmd, cwd=cwd, text=True)
    if check and p.returncode != 0:
        raise InstallError(f"command failed exit={p.returncode}: {' '.join(cmd)}")
    return p


def require_root() -> None:
    if os.geteuid() != 0:
        raise InstallError("Linux/Pi apply mode must run as root or through sudo.")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_config(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def backup_existing(cfg: dict) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup_root = Path(cfg["installation"].get("backup_path") or "/var/backups/shipwatch")
    target = backup_root / f"before-install-{stamp}"
    target.mkdir(parents=True, exist_ok=False)

    candidates = [
        Path("/usr/local/bin/shipwatch-air.py"),
        Path("/etc/systemd/system/shipwatch-air.service"),
        Path("/etc/systemd/system/ais-catcher.service"),
        Path("/etc/AIS-catcher/aiscatcher.json"),
        Path("/etc/default/readsb"),
        Path("/etc/default/tar1090"),
        Path("/etc/lighttpd/conf-enabled/88-tar1090.conf"),
        Path("/etc/shipwatch/shipwatch.json"),
        Path("/opt/shipwatch/ota/shipwatch_ota_agent.py"),
        Path("/etc/systemd/system/shipwatch-ota.service"),
        Path("/etc/systemd/system/shipwatch-ota.timer"),
        Path("/etc/shipwatch-ota/agent.json"),
        Path("/etc/shipwatch-ota/device-signing-seed.b64"),
        Path("/etc/shipwatch-ota/state.json"),
        Path("/etc/shipwatch-ota/enrollment-confirmed"),
    ]

    for src in candidates:
        if src.exists():
            rel = str(src).lstrip("/")
            dst = target / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    emit("PASS", f"BACKUP_CREATED={target}")
    return target


def apt_install(packages: list[str]) -> None:
    if not packages:
        return
    env = dict(os.environ)
    env["DEBIAN_FRONTEND"] = "noninteractive"
    subprocess.run(["apt-get", "update"], env=env, check=True)
    subprocess.run(["apt-get", "-y", "install", *packages], env=env, check=True)
    emit("PASS", "RUNTIME_PACKAGES_INSTALLED")


def create_paths(cfg: dict) -> None:
    inst = cfg["installation"]
    for key in ("application_path", "config_path", "data_path", "log_path", "web_path", "backup_path"):
        path = inst.get(key)
        if path:
            Path(path).mkdir(parents=True, exist_ok=True)
            emit("PASS", f"PATH_READY={path}")


def ensure_user(name: str, system: bool = True) -> None:
    try:
        subprocess.run(["id", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        emit("PASS", f"USER_EXISTS={name}")
        return
    except subprocess.CalledProcessError:
        pass

    cmd = ["useradd"]
    if system:
        cmd += ["--system", "--no-create-home"]
    cmd += [name]
    run(cmd)
    emit("PASS", f"USER_CREATED={name}")


def clone_at(repo: str, commit: str, dest: Path) -> None:
    run(["git", "clone", "--filter=blob:none", repo, str(dest)])
    run(["git", "checkout", commit], cwd=str(dest))


def package_installed(name: str) -> bool:
    p = subprocess.run(
        ["dpkg-query", "-W", name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return p.returncode == 0


def build_readsb(src_info: dict, work: Path) -> list[str]:
    repo = src_info["upstream"]
    commit = src_info["reference_commit"]
    build = work / "readsb"
    clone_at(repo, commit, build)

    runtime_deps = src_info.get("runtime_packages", [])
    build_deps = src_info.get("temporary_build_packages", [])

    apt_install(runtime_deps)

    added_build_deps = [name for name in build_deps if not package_installed(name)]
    apt_install(build_deps)

    run(["make", "-j2"], cwd=str(build))

    binary = build / "readsb"
    if not binary.exists():
        raise InstallError("readsb build completed but binary was not produced")

    shutil.copy2(binary, "/usr/bin/readsb")
    os.chmod("/usr/bin/readsb", 0o755)
    emit("PASS", f"READSB_INSTALLED commit={commit}")
    emit("RESULT", "READSB_BUILD_DEPS_ADDED=" + ",".join(added_build_deps))
    return added_build_deps


def install_aircraft_database() -> None:
    request = urllib.request.Request(AIRCRAFT_DB_URL, headers={"User-Agent": "Shipwatch-Installer/1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = response.read()
    try:
        decoded = gzip.decompress(payload)
    except (OSError, EOFError) as exc:
        raise InstallError("Aircraft lookup download was not a valid gzip database") from exc
    if len(payload) < 100_000 or len(decoded) < 1_000_000:
        raise InstallError("Aircraft lookup download was unexpectedly small")
    AIRCRAFT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = AIRCRAFT_DB_PATH.with_suffix(AIRCRAFT_DB_PATH.suffix + ".tmp")
    temp.write_bytes(payload)
    os.chmod(temp, 0o644)
    group = subprocess.check_output(["id", "-gn", "readsb"], text=True).strip()
    subprocess.run(["chown", f"readsb:{group}", str(temp)], check=True)
    temp.replace(AIRCRAFT_DB_PATH)
    emit("PASS", f"AIRCRAFT_LOOKUP_INSTALLED bytes={len(payload)}")


def install_tar1090(src_info: dict, work: Path) -> None:
    repo = src_info["upstream"]
    commit = src_info["reference_commit"]
    build = work / "tar1090"
    clone_at(repo, commit, build)

    installer = build / "install.sh"
    if not installer.exists():
        raise InstallError("tar1090 install.sh not found")

    run(["bash", str(installer)], cwd=str(build))
    emit("PASS", f"TAR1090_INSTALLED commit={commit}")


def ais_ready() -> bool:
    return Path("/usr/bin/AIS-catcher").exists()


def install_ais_catcher(src_info: dict) -> None:
    import hashlib

    arch = subprocess.check_output(["dpkg", "--print-architecture"], text=True).strip()
    matches = sorted(PACKAGES.glob(f"ais-catcher_*_{arch}.deb"))
    if not matches:
        raise InstallError(
            f"No bundled AIS-Catcher package for architecture {arch}. "
            f"Expected under {PACKAGES}"
        )

    package = matches[-1]
    expected = str(src_info.get("bundled_arm64_sha256") or "").lower()
    actual = hashlib.sha256(package.read_bytes()).hexdigest().lower()

    if expected and actual != expected:
        raise InstallError(
            f"AIS-Catcher package checksum mismatch expected={expected} actual={actual}"
        )

    emit("PASS", f"AISCATCHER_PACKAGE_SHA256={actual}")
    run(["dpkg", "-i", str(package)])

    if not ais_ready():
        raise InstallError("AIS-Catcher package installed but binary is missing")

    emit("PASS", f"AISCATCHER_INSTALLED={package.name}")


def install_shipwatch_payload(cfg: dict) -> None:
    source = COMMON_RUNTIME / "shipwatch-air.py"
    if not source.exists():
        raise InstallError(f"Shipwatch runtime payload missing: {source}")

    shutil.copy2(source, "/usr/local/bin/shipwatch-air.py")
    os.chmod("/usr/local/bin/shipwatch-air.py", 0o755)

    config_dir = Path(cfg["installation"].get("config_path") or "/etc/shipwatch")
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "shipwatch.json"
    config_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    os.chmod(config_path, 0o640)

    emit("PASS", "SHIPWATCH_AIR_RUNTIME_INSTALLED")
    emit("PASS", f"SHIPWATCH_CONFIG_WRITTEN={config_path}")


def install_ota_runtime(cfg: dict) -> None:
    """Install the agent, enrolling only with explicit consent and a release-pinned controller key."""
    agent_source = COMMON_RUNTIME / "shipwatch_ota_agent.py"
    services = COMMON_RUNTIME / "services" / "linux"
    if not agent_source.is_file():
        raise InstallError(f"Shipwatch OTA agent missing: {agent_source}")
    for name in ("shipwatch-ota.service", "shipwatch-ota.timer"):
        if not (services / name).is_file():
            raise InstallError(f"Shipwatch OTA service definition missing: {services / name}")

    ota_dir = Path("/opt/shipwatch/ota")
    ota_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(agent_source, ota_dir / "shipwatch_ota_agent.py")
    os.chmod(ota_dir / "shipwatch_ota_agent.py", 0o755)
    for name in ("shipwatch-ota.service", "shipwatch-ota.timer"):
        shutil.copy2(services / name, Path("/etc/systemd/system") / name)
        os.chmod(Path("/etc/systemd/system") / name, 0o644)
    Path("/etc/shipwatch-ota").mkdir(parents=True, exist_ok=True)
    os.chmod("/etc/shipwatch-ota", 0o700)
    consent = cfg.get("installation", {}).get("ota_consent", {})
    if consent.get("remote_management_consent") is not True:
        emit("PASS", "OTA_RUNTIME_INSTALLED_DORMANT")
        emit("RESULT", "OTA_ENROLLMENT_DISABLED_NO_REMOTE_MANAGEMENT_CONSENT")
        return

    controller = cfg.get("installation", {}).get("ota_controller", {})
    api_url = str(controller.get("api_url", ""))
    server_key = str(controller.get("server_verify_key_b64", ""))
    if not api_url.startswith("https://") or not server_key:
        raise InstallError("OTA consent was recorded, but the release-pinned controller configuration is missing.")
    agent_config = Path("/etc/shipwatch-ota/agent.json")
    if not agent_config.exists():
        init = subprocess.run([
            "/usr/bin/python3", str(ota_dir / "shipwatch_ota_agent.py"), "--initialize",
            "--data-dir", "/etc/shipwatch-ota", "--api-url", api_url,
            "--server-verify-key-b64", server_key,
            "--aiscatcher-config", "/etc/AIS-catcher/aiscatcher.json",
            "--allowed-config-root", "/etc/AIS-catcher",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if init.returncode:
            raise InstallError("Could not create the protected OTA device identity.")

    if not Path("/etc/shipwatch-ota/device-signing-seed.b64").is_file():
        raise InstallError("The OTA device identity is incomplete; refusing to enroll it.")

    enrollment_marker = Path("/etc/shipwatch-ota/enrollment-confirmed")
    if not enrollment_marker.exists():
        payload = {
            "consent_version": str(consent.get("consent_version", "")),
            "remote_management_consent": True,
            "mastchain_consent": consent.get("mastchain_consent") is True,
            "station_name": str(consent.get("station_name", cfg.get("station", {}).get("name", "Shipwatch")))[:100],
        }
        if payload["mastchain_consent"]:
            payload["latitude"] = consent.get("latitude")
            payload["longitude"] = consent.get("longitude")
        fd, consent_path = tempfile.mkstemp(prefix="shipwatch-ota-consent-", suffix=".json")
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(payload, stream)
            enrolled = subprocess.run([
                "/usr/bin/python3", str(ota_dir / "shipwatch_ota_agent.py"),
                "--config", str(agent_config), "--enroll-consent-json", consent_path,
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        finally:
            try:
                os.unlink(consent_path)
            except OSError:
                pass
        if enrolled.returncode:
            raise InstallError("OTA enrollment did not receive a signed controller confirmation.")
        marker_fd = os.open(enrollment_marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(marker_fd, "w", encoding="ascii") as stream:
            stream.write("confirmed\n")

    run(["systemctl", "daemon-reload"])
    run(["systemctl", "enable", "--now", "shipwatch-ota.timer"])
    emit("PASS", "OTA_DEVICE_ENROLLED_AND_TIMER_ENABLED")


def install_web_payload(cfg: dict) -> None:
    web_path = Path(cfg["installation"].get("web_path") or "/var/www/html/shipwatch")
    web_path.mkdir(parents=True, exist_ok=True)

    host = (
        cfg.get("network", {}).get("public_host")
        or cfg.get("ssh", {}).get("host")
        or socket.gethostname()
    )
    ais_port = cfg.get("network", {}).get("ais_web_port", 8100)
    radio_port = cfg.get("network", {}).get("radio_port", 8088)
    voice_shared = cfg.get("receivers", {}).get("voice", {}).get("share_with") == "ais"

    replacements = {
        "{{SHIPWATCH_HOST}}": str(host),
        "{{AIS_WEB_PORT}}": str(ais_port),
        "{{RADIO_PORT}}": str(radio_port),
        "{{VOICE_SHARED_JS}}": "true" if voice_shared else "false",
        "{{VOICE_NOTE}}": (
            "Voice and AIS share one receiver. Voice OFF restores AIS automatically."
            if voice_shared
            else "Voice has its own dedicated receiver. AIS remains online while listening."
        ),
        "{{RECOVERY_NOTE}}": (
            "Restarts only the selected receiver. Turn Voice OFF for marine recovery."
            if voice_shared
            else "Restarts only the selected receiver. ADS-B, AIS, and Voice operate independently."
        ),
    }

    for src in WEB_RUNTIME.iterdir():
        if not src.is_file() or src.name.startswith("."):
            continue
        text = src.read_text(encoding="utf-8")
        for key, value in replacements.items():
            text = text.replace(key, value)
        (web_path / src.name).write_text(text, encoding="utf-8")
    emit("PASS", f"WEB_PAYLOAD_INSTALLED={web_path}")


def render(text: str, values: dict[str, str]) -> str:
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", str(value))
    return text


def write_text(path: str, text: str, mode: int | None = None) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    if mode is not None:
        os.chmod(p, mode)


def install_configs(cfg: dict) -> None:
    station = cfg["station"]
    net = cfg["network"]
    rnet = net.get("readsb", {})
    rec = cfg["receivers"]

    values = {
        "ADSB_SERIAL": rec["adsb"]["serial"],
        "ADSB_GAIN": rec["adsb"].get("gain", "auto"),
        "ADSB_PPM": rec["adsb"].get("ppm", 0),
        "LATITUDE": station.get("latitude") or "0",
        "LONGITUDE": station.get("longitude") or "0",
        "MAX_RANGE": 450,
        "READSB_RAW_INPUT": rnet.get("raw_input", 30001),
        "READSB_RAW_OUTPUT": rnet.get("raw_output", 30002),
        "READSB_SBS_OUTPUT": rnet.get("sbs_output", 30003),
        "READSB_BEAST_INPUT": rnet.get("beast_input", 30004),
        "READSB_BEAST_OUTPUT": rnet.get("beast_output", 30005),
        "READSB_BEAST_SECONDARY_INPUT": rnet.get("beast_secondary_input", 30104),
        "AIS_SERIAL": rec["ais"]["serial"],
        "AIS_WEB_PORT": net.get("ais_web_port", 8100),
        "AIS_SERVICE_PORT": net.get("ais_service_port", 8118),
        "STATION_NAME": station.get("name", "Shipwatch"),
    }

    templates = RUNTIME / "templates"

    readsb = render((templates / "config" / "readsb.default.template").read_text(), values)
    write_text("/etc/default/readsb", readsb)

    ais = render((templates / "config" / "aiscatcher.json.template").read_text(), values)
    write_text("/etc/AIS-catcher/aiscatcher.json", ais)

    config_dir = Path(cfg["installation"].get("config_path") or "/etc/shipwatch")
    config_dir.mkdir(parents=True, exist_ok=True)

    ais_unit = render((templates / "systemd" / "ais-catcher.service.template").read_text(), values)
    write_text("/etc/systemd/system/ais-catcher.service", ais_unit)

    ship_unit = render((templates / "systemd" / "shipwatch-air.service.template").read_text(), values)
    write_text("/etc/systemd/system/shipwatch-air.service", ship_unit)

    emit("PASS", "CONFIG_TEMPLATES_RENDERED")


def install_readsb_service() -> None:
    unit = """[Unit]
Description=readsb ADS-B receiver
Wants=network.target
After=network.target

[Service]
EnvironmentFile=/etc/default/readsb
User=readsb
RuntimeDirectory=readsb
RuntimeDirectoryMode=0755
ExecStart=/usr/bin/readsb --write-json /run/readsb --quiet $RECEIVER_OPTIONS $DECODER_OPTIONS $NET_OPTIONS $JSON_OPTIONS
Type=simple
Restart=always
RestartSec=15
Nice=-5

[Install]
WantedBy=default.target
"""
    write_text("/etc/systemd/system/readsb.service", unit)
    emit("PASS", "READSB_SERVICE_INSTALLED")


def health_check() -> None:
    required_bins = ["AIS-catcher", "readsb", "rtl_fm", "rtl_test", "ffmpeg", "python3", "lighttpd"]
    for name in required_bins:
        if shutil.which(name) is None:
            raise InstallError(f"required binary missing after install: {name}")

    run(["systemctl", "daemon-reload"])

    services = ["ais-catcher", "readsb", "tar1090", "lighttpd"]
    if Path("/usr/local/bin/shipwatch-air.py").exists():
        services.append("shipwatch-air")

    for service in services:
        run(["systemctl", "enable", service])
        run(["systemctl", "restart", service])

    time.sleep(3)

    for service in services:
        p = subprocess.run(["systemctl", "is-active", "--quiet", service])
        if p.returncode != 0:
            raise InstallError(f"service not active after install: {service}")
        emit("PASS", f"SERVICE_ACTIVE={service}")

    emit("PASS", "HEALTH_CHECK_COMPLETE")


def cleanup_build_deps(added_build_deps: list[str]) -> None:
    if not added_build_deps:
        emit("PASS", "NO_TEMP_BUILD_DEPENDENCIES_TO_REMOVE")
        return
    env = dict(os.environ)
    env["DEBIAN_FRONTEND"] = "noninteractive"
    subprocess.run(
        ["apt-get", "-y", "purge", *added_build_deps],
        env=env,
        check=False,
    )
    subprocess.run(
        ["apt-get", "-y", "autoremove", "--purge"],
        env=env,
        check=False,
    )
    emit("PASS", "TEMP_BUILD_DEPENDENCIES_CLEANED=" + ",".join(added_build_deps))


def dry_run(cfg: dict, manifest: dict, sources: dict) -> int:
    emit("RESULT", "MODE=DRY_RUN")
    emit("RESULT", "RECEIVER_LAYOUT=" + str(cfg.get("receiver_layout")))
    emit("RESULT", "RUNTIME_PACKAGES=" + ",".join(manifest["apt_packages"]))
    emit("RESULT", "READSB_COMMIT=" + sources["components"]["readsb"]["reference_commit"])
    emit("RESULT", "TAR1090_COMMIT=" + sources["components"]["tar1090"]["reference_commit"])
    emit("RESULT", "AIS_CATCHER_VERSION=" + sources["components"]["ais_catcher"]["reference_version"])
    emit("PASS", "DRY_RUN_COMPLETE")
    emit("RESULT", "NO_SYSTEM_CHANGES_MADE")
    emit("NEXT", "RUN_WITH_--apply_ON_A_TEST_OR_FRESH_HOST")
    return 0


def apply(cfg: dict, manifest: dict, sources: dict) -> int:
    require_root()
    emit("RESULT", "MODE=APPLY")

    backup = backup_existing(cfg)
    work = Path(tempfile.mkdtemp(prefix="shipwatch-install-"))
    emit("RESULT", f"WORKDIR={work}")

    try:
        create_paths(cfg)

        temp_installer_packages = manifest.get("temporary_installer_packages", [])
        added_installer_packages = [
            name for name in temp_installer_packages if not package_installed(name)
        ]

        apt_install([*temp_installer_packages, *manifest["apt_packages"]])

        ensure_user("readsb")
        ensure_user("aiscatcher")
        ensure_user("tar1090")

        if not ais_ready():
            install_ais_catcher(sources["components"]["ais_catcher"])
        else:
            emit("PASS", "AISCATCHER_RUNTIME_PRESENT")

        added_build_deps = build_readsb(sources["components"]["readsb"], work)
        install_readsb_service()
        install_tar1090(sources["components"]["tar1090"], work)
        install_aircraft_database()
        install_shipwatch_payload(cfg)
        install_web_payload(cfg)
        install_configs(cfg)
        install_ota_runtime(cfg)

        health_check()

        cleanup_build_deps(added_build_deps)
        cleanup_build_deps(added_installer_packages)

        shutil.rmtree(work, ignore_errors=True)
        emit("PASS", "INSTALL_COMPLETE")
        emit("RESULT", f"BACKUP={backup}")
        emit("NEXT", "OPEN_SHIPWATCH_HEALTH_PAGE")
        return 0

    except Exception as exc:
        emit("FAIL", f"INSTALL_ABORTED={exc}")
        emit("RESULT", f"BACKUP_PRESERVED={backup}")
        emit("RESULT", f"WORKDIR_PRESERVED={work}")
        emit("NEXT", "REVIEW_FAILURE_BEFORE_RETRY")
        return 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    cfg = load_config(args.config)
    manifest = load_json(MANIFEST)
    sources = load_json(SOURCES)

    if args.apply:
        return apply(cfg, manifest, sources)
    return dry_run(cfg, manifest, sources)


if __name__ == "__main__":
    raise SystemExit(main())
