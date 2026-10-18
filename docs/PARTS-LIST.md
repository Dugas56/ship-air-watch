# Shipwatch Parts List

## Recommended receiver setup

### Best setup — 3 SDR dongles

Use **three identical RTL-SDR-compatible dongles with configurable serial numbers**.

Recommended role labels:

- SHIPWATCH-ADSB
- SHIPWATCH-AIS
- SHIPWATCH-VOICE

Why three is best:

- ADS-B stays dedicated to aircraft.
- AIS stays online continuously.
- Voice scanning never pauses AIS.
- Identical hardware simplifies drivers, spare parts, support and troubleshooting.
- Configurable serials prevent USB-order mixups after reboot.

### Lower-cost setup — 2 SDR dongles

Use two compatible SDRs:

- one dedicated to ADS-B;
- one shared by AIS and Voice.

In this mode, AIS owns the shared receiver by default. Voice temporarily borrows it, and Shipwatch automatically returns it to AIS after the configured safety lease.

### Existing or mixed SDR hardware

Shipwatch does **not** require identical dongles.

The installer must detect supported SDR hardware and show:

- manufacturer;
- model/product;
- serial number;
- USB path;
- current process owner;
- supported role(s), where detectable.

The user then assigns each receiver a role.

Shipwatch must never rely on device index such as Device 0 / Device 1 as the permanent identity.

## Host computer choices

A Raspberry Pi is optional.

Shipwatch can run as:

- Windows-only — SDRs plug directly into the Windows PC.
- Mac-only — SDRs plug directly into the Mac.
- Raspberry Pi/Linux-only — dedicated always-on receiver appliance.
- PC/Mac + remote Pi/Linux — radios run remotely and are controlled from another computer.
- Other supported Linux computer — same receiver architecture without a Pi.

SSH is only needed when the receiver host is remote.

## Required hardware

| Part | Qty | Purpose |
|---|---:|---|
| Windows 10 PC, supported Mac, Raspberry Pi/Linux host, or remote Linux computer | 1 | Shipwatch host |
| Compatible SDR dongles | 2 minimum, 3 recommended | ADS-B, AIS and Voice |
| 1090 MHz ADS-B antenna | 1 | Aircraft reception |
| Marine VHF/AIS antenna | 1 | AIS reception |
| Voice-scanner antenna | 1 optional/recommended with third SDR | Voice reception |
| Network connection | 1 | Browser UI, feeds and remote access |
| Storage | 1 | Application, configuration and logs |

## Strongly recommended

| Part | Qty | Why |
|---|---:|---|
| Identical serial-configurable SDR dongles | 3 | Simplest supported configuration |
| Powered USB hub | 1 | Especially recommended for three SDRs |
| Adequate host/Pi power supply | 1 | Prevents USB resets/disappearing receivers |
| Quality short USB extension cables | 2-3 | Better spacing and less connector strain |
| Ethernet cable | 1 | Stable 24/7 network connection |
| Ventilated enclosure | 1 | Better long-term reliability |

## Optional

| Part | Purpose |
|---|---|
| 1090 MHz band-pass filter | Improve ADS-B reception |
| Marine VHF filter | Reduce out-of-band interference |
| Lightning/surge protection | Outdoor antenna protection |
| UPS | Keep Shipwatch online through short outages |
| GPS receiver | Future timing/location features |

## Serial-number rule

Every configured receiver must have a unique usable identity.

If identical dongles arrive with duplicate/default serials, the installer should offer a guided serial-number configuration step before role assignment.

The installer must show the proposed change and require confirmation before writing a dongle serial number.
