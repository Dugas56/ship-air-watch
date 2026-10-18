# Shipwatch Common Installer

## Phase 1

`shipwatch_setup.py` is the first working installer-wizard engine.

It currently:

- asks whether Shipwatch runs on Windows, macOS, local Linux/Pi, or remote Linux/Pi;
- skips SSH entirely for local installs;
- collects SSH host, port, username and key path for remote installs;
- tests the SSH port and can test key/agent login;
- asks all major installation paths;
- supports 2-SDR and 3-SDR layouts;
- detects local rtl-sdr devices when `rtl_test` is available;
- assigns receivers by serial number;
- prevents ADS-B/AIS duplicate assignments;
- requires three unique serials in 3-SDR mode;
- creates a non-secret configuration preview;
- makes no system changes.

This is intentionally a safe configuration collector before the installation/repair engine is added.

For an existing Windows or macOS AIS-Catcher receiver, `shipwatch_installer.py --ota-only` uses the same wizard to collect default-No remote consent, then provisions the OTA agent and native polling service after signed enrollment succeeds. This path requires a valid pinned `ota-release-config.json`; it does not install the rest of Shipwatch.

## Planned Phase 2

- dependency preflight;
- admin/sudo validation;
- writable-path checks;
- free-space checks;
- USB/power checks;
- port conflicts;
- SDR serial configuration workflow;
- platform-specific service installation;
- backup and rollback;
- final health report.
