# Ship Watch 0.1.0 RC2

This is an integrated release candidate for Ship Watch.

## Package contents

- `linux-pi/`: full Linux and Raspberry Pi receiver installer and runtime.
- `windows-macos-ota/`: optional OTA enrollment for an existing AIS-Catcher receiver.
- `web-console/`: current browser console, maps, history endpoints, and assets.
- `docs/`: installation, parts, storage, OTA, and printable console documentation.
- `RELEASE-MANIFEST.json`: size and SHA-256 for every packaged file.
- `SHA256SUMS.txt`: checksums in standard verification format.

## Platform status

- Linux and Raspberry Pi: full receiver installation release candidate.
- Windows: web console and OTA tooling are packaged; the complete native receiver installer still requires implementation and hardware validation.
- macOS: web console and OTA tooling are packaged; the complete native receiver installer still requires implementation and hardware validation.
- Phones and tablets: browser client through the local network or Tailscale. SDR receivers remain attached to a host computer.

Do not advertise Windows or macOS as production-ready full receiver installations until their native installers complete end-to-end USB, service, firewall, and live-feed validation.

## Linux/Pi dry run

    python linux-pi/installers/raspberry-pi/install_linux.py linux-pi/shipwatch.example.json

The installer makes no system changes unless `--apply` is supplied.

## Integrity verification

PowerShell:

    Get-FileHash -Algorithm SHA256 .\Shipwatch-0.1.0-rc2.zip

Linux or macOS:

    sha256sum Shipwatch-0.1.0-rc2.zip

The expected ZIP checksum is written beside the archive in `Shipwatch-0.1.0-rc2.zip.sha256`.
