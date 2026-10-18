# Ship & Air Watch

**Version 0.1.0 RC2 · Public preview · Not production-ready**

Ship & Air Watch is a self-hosted marine and aviation monitoring project. It combines **AIS vessel reception**, **ADS-B aircraft tracking**, a **marine VHF listening post**, and a browser-based radio and map console. It is designed around affordable RTL-SDR receivers and a Raspberry Pi or Linux host.

> **Release status:** This is a release candidate for experimentation and development. Full hardware installation is currently targeted at Linux/Raspberry Pi. Do not assume the Windows or macOS receiver installers are complete.

## Features

- AIS vessel activity and Saint John Harbour mapping.
- ADS-B aircraft receiver support using readsb.
- Marine VHF radio listening/scanning through the receiver host.
- Browser console with radio controls, maps, and history views.
- History storage and reporting components.
- Optional over-the-air (OTA) update framework (validation in progress).

## Platform support

| Platform | Support at RC2 |
| --- | --- |
| Raspberry Pi / Linux | Receiver installer **release candidate**; validate on your own hardware |
| Windows | Web console and optional OTA tools; **native receiver installer incomplete** |
| macOS | Web console and optional OTA tools; **native receiver installer incomplete** |
| iOS / Android / tablet | Browser client on your network; not an SDR receiver host |

## Hardware

A Linux/Raspberry Pi system with compatible RTL-SDR USB receivers and suitable antennas is the intended receiver host. Separate receivers allow independent AIS, aircraft, and listening-post operation; antenna placement, local rules, and receiver serial-number assignment matter.

See [Parts List](docs/PARTS-LIST.md) and [Slim Linux Install](docs/SLIM-LINUX-INSTALL.md).

## Getting started (Linux / Raspberry Pi)

1. Review [the release notes](docs/RELEASE-README.md), [the installer guide](docs/INSTALL-MANUAL-OUTLINE.md), and the example configuration at `linux-pi/shipwatch.example.json`.
2. Copy the example configuration to a **private location**, then configure devices, interface addresses, and receiver options for your setup.
3. From the repository root, preview the installation plan without making system changes:

   ```bash
   python3 linux-pi/installers/raspberry-pi/install_linux.py linux-pi/shipwatch.example.json
   ```

4. Only on a suitable **test or freshly prepared** Linux host, after inspecting the output and understanding the changes, use the installer's documented `--apply` option. Do not run it blindly on a working receiver.

## Repository structure

| Directory | Contents |
| --- | --- |
| `linux-pi/` | Linux/Pi installer and receiver runtime |
| `web-console/` | Radio UI, maps, PHP endpoints, and front-end assets |
| `windows-macos-ota/` | Optional OTA enrollment and platform scaffolding |
| `docs/` | Setup, storage, release, design, and hardware documentation |
| `RELEASE-MANIFEST.json`, `SHA256SUMS.txt` | Package integrity metadata |

## Verification

The RC2 archive checksum was verified during release preparation. The current repository is an extracted snapshot; consult `RELEASE-MANIFEST.json` and `SHA256SUMS.txt` for package-specific checksums. A live SDR service showing “active” does **not** by itself prove reception, and native Windows/macOS installation is not yet validated.

## Security and responsible use

- Keep passwords, tokens, SSH keys, camera URLs, local configuration, and any private vessel/aircraft history out of commits.
- Do not expose administrative or receiver endpoints directly to the internet without appropriate authentication and network controls.
- Use radio receivers in accordance with local laws, frequencies, and privacy expectations.
- OTA deployment should be tested in a controlled environment before enabling unattended updates.

## License and third-party materials

**Original project source code:** [MIT License](LICENSE), except where explicitly marked otherwise. The MIT grant applies only to material the project maintainers have rights to license.

**Third-party artwork, fonts, libraries, binaries, and other externally sourced materials** retain their own licences and terms; the project MIT licence does not replace those terms. See the [ship icon attributions](web-console/assets/ship-icons/ATTRIBUTION.md), bundled font licence files, and satellite library licence notice. Some Flaticon artwork may require separate licensing for redistribution; **review those terms before mirroring or repackaging assets**. No ownership of third-party marks or assets is claimed.

## Project status

Issues, installer feedback, and reproducible bug reports are welcome. Remaining work includes native Windows/macOS receiver installers, end-to-end hardware testing, live-audio verification, OTA safety checks, and a comprehensive public security and dependency audit.
