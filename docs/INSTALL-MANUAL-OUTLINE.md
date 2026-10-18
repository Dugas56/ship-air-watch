# Shipwatch Installation & Help Manual

## 1. Welcome

- What Shipwatch does
- Aircraft ADS-B map
- Marine AIS map
- Voice scanner
- Supported platforms
- How the two-receiver architecture works

## 2. Before You Start

- Required parts
- Antenna placement
- Network requirements
- Power requirements
- Two-SDR requirement
- Receiver serial-number rule

## 3. Hardware Assembly

- Connect ADS-B antenna to ADS-B SDR
- Connect marine antenna to AIS/voice SDR
- Connect SDRs to host
- Powered USB hub guidance
- Ethernet / Wi-Fi
- Power-on sequence

## 4. Installation

### Raspberry Pi
- Supported Raspberry Pi OS / Ubuntu version
- Run installer
- Verify packages
- Detect SDRs
- Assign serials
- Create services
- Open web interface

### Windows 10
- Run Shipwatch Setup
- Install runtime/dependencies
- Detect SDRs
- Install background services/tasks
- Configure local web UI
- Launch browser

### macOS
- Run package installer
- Install runtime/dependencies
- Detect SDRs
- Install launchd services
- Configure web UI
- Launch browser

## 5. First-Run Setup Wizard

- Station name
- Location
- ADS-B receiver selection
- AIS/voice receiver selection
- Port validation
- Antenna checklist
- Feed credentials
- Voice banks
- Test aircraft receiver
- Test AIS receiver
- Save configuration

## 6. Using Shipwatch

- Aircraft map
- Marine map
- Radio listening post
- Bank selection
- Hold
- Squelch
- Fine tuning
- Volume
- Voice/AIS handoff
- 15-minute voice safety lease

## 7. Feed Services

- MastChain
- Feed-health indication
- Heartbeat behavior
- Credential storage
- Privacy and secret handling

## 8. Health Screen

- SDR detected / missing
- SDR serial expected / found
- Service state
- Port state
- Current SDR owner
- Last AIS upload
- readsb message count
- USB-power warning
- Network reachability

## 9. Troubleshooting

### Ships visible, aircraft map 404
Check ADS-B SDR serial and readsb first.

### Aircraft visible, ships missing
Check AIS service and ownership of the generic SDR.

### Voice works but AIS disappears
Voice may be holding the shared SDR. Return to map/AIS mode.

### SDR missing after reboot
Check power supply, powered hub, USB cable, then reseat the affected dongle.

### tar1090 loads but shows no aircraft
Check readsb status and /run/readsb JSON generation.

### No audio
Check shipwatch-air service, current receiver mode, volume, squelch, and audio endpoint.

## 10. Backup & Restore

- Export configuration
- Preserve receiver serial assignments
- Preserve service configuration
- Restore without copying secrets into documentation

## 11. Updates

- Version check
- Backup before update
- Migrations
- Rollback

## 12. Uninstall

- Stop services
- Remove services
- Preserve or remove configuration
- Preserve user data
