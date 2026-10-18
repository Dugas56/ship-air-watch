# Shipwatch Installer Architecture

One Shipwatch product, three platform adapters.

## Shared components

- Shipwatch web UI
- Receiver-bank definitions
- Health checks
- SDR serial assignment
- AIS/voice handoff policy
- Configuration schema
- Troubleshooting data
- Update manifest

## Raspberry Pi / Linux

Service manager: systemd

Responsibilities:
- Install AIS-catcher, readsb, tar1090/lighttpd, rtl-sdr tools, Python and FFmpeg
- Install shipwatch-air.py
- Create service units
- Configure receiver serials
- Verify USB power and receiver presence
- Start and validate services

## Windows 10

Service manager: Windows service or scheduled-task wrapper

Responsibilities:
- Install required runtimes
- Detect RTL-SDR devices and serials
- Host Shipwatch web UI
- Run receiver/background processes
- Provide firewall setup where required
- Launch browser after first-run validation

## macOS

Service manager: launchd

Responsibilities:
- Install required runtimes
- Detect SDR devices and serials
- Install LaunchAgents/LaunchDaemons
- Host Shipwatch web UI
- Validate local network/browser access

## Optional OTA on an existing Windows or macOS receiver

The general Windows and macOS Shipwatch application installers are not implemented yet. For an existing AIS-Catcher receiver, the OTA-only release candidate is at `product/releases/Shipwatch-OTA-Windows-macOS-0.1.0-rc1.zip`; its setup steps and limits are in the included `README-OTA.md`.

The same flow can be launched from a source checkout with:

```text
python product/installers/common/shipwatch_installer.py --ota-only
```

The wizard defaults both remote-management and MastChain consent to No. Windows must run from an elevated terminal; macOS prompts through `sudo`. MastChain opt-in also requires a valid local AIS-Catcher JSON config path. The OTA agent is not activated until the controller returns a signed enrollment confirmation. Native end-to-end enrollment and delivery still need verification on each platform before treating this release candidate as generally supported.

## Installer rules

1. Detect before changing.
2. Never overwrite a working configuration without backup.
3. Never store feed credentials in logs or documentation.
4. Never use USB index as the durable receiver identity.
5. Refuse to assign the same SDR to ADS-B and AIS simultaneously.
6. Verify services and data endpoints before reporting installation success.
7. Detect low-power / missing-USB conditions and present a human-readable fix.
