# Shipwatch Step-by-Step Installer Wizard

This document defines the required installation flow for Raspberry Pi/Linux, Windows 10, and macOS.

The installer must not assume paths, usernames, receiver serials, SSH configuration, ports, or service locations. It asks, validates, summarizes, and only then makes changes.

## Wizard principles

1. One question at a time.
2. Show a recommended default for every technical field.
3. Explain each question in plain language.
4. Test values immediately where possible.
5. Never continue after a failed critical test without telling the user exactly why.
6. Back up any existing Shipwatch configuration before overwriting it.
7. Never print passwords, SSH private-key contents, MastChain secrets, or feed tokens into logs.
8. Show a final review page before installation.
9. End with a PASS / FAIL health report and exact web addresses to open.
10. Allow Back, Next, Cancel, and Save Settings.

# Step 1 — Welcome

Display:

Shipwatch Installer

This wizard will configure:
- Aircraft ADS-B receiver
- Marine AIS receiver
- Voice scanner
- Aircraft and marine maps
- Web interface
- Startup services
- Optional external feeds

Buttons:
- Start Installation
- Repair Existing Installation
- Upgrade Existing Installation
- Exit

# Step 2 — Installation Type

Ask:

Where will the Shipwatch receiver software run?

Choices:
- This Windows 10 computer
- This Mac
- This Raspberry Pi / Linux computer
- A remote Raspberry Pi / Linux computer over SSH

If Windows, Mac, or local Linux/Pi is selected, do not ask SSH questions.

If remote Linux/Pi is selected, enable the SSH section below.

# Step 3 — Station Identity

Ask:

Station name
Default: Shipwatch

Location description
Example: Saint John, New Brunswick

Latitude
Default: blank until detected or entered

Longitude
Default: blank until detected or entered

Optional:
- Detect approximate location
- Enter manually

The installer must show the location on a confirmation screen before saving.

# Step 4 — Local User / Service Account

Linux / Raspberry Pi:

Ask:
- Linux username
- Home directory
- Does this user have sudo access?

Recommended:
- Use the currently logged-in non-root user.
- Dedicated services may run under separate service accounts.

Validate:
- user exists
- home directory exists
- sudo works

Windows:

Ask:
- Windows account
- Install for current user or all users
- Run receiver services at boot? Yes / No

macOS:

Ask:
- macOS account
- Install for current user or all users
- Install launchd services? Yes / No

# Step 5 — SSH Setup

Shown when installing to or managing a remote Linux/Pi host.

Ask:

SSH host or IP address
Example: 192.168.2.29

SSH hostname/alias
Example: ship-pi
Optional but recommended

SSH port
Default: 22

SSH username
Example: admin

Authentication method:
- Existing SSH key
- Create a new SSH key
- Password
- SSH agent

If Existing SSH key:
Ask for private-key path.
Examples:
Windows:
C:\Users\YourName\.ssh\id_ed25519

macOS/Linux:
~/.ssh/id_ed25519

Buttons:
- Browse
- Test SSH Connection

Validation:
- host resolves or IP responds
- TCP port is reachable
- authentication succeeds
- remote OS is identified
- sudo ability is tested separately

Never copy a private key unless the user explicitly chooses to create/manage keys with Shipwatch.

If creating a new key:
- Ask where to save it.
- Ask whether to protect it with a passphrase.
- Show the public key only.
- Guide the user through authorized_keys installation.
- Test connection afterward.

Save SSH host information separately from secrets.

# Step 6 — Installation Paths

The installer asks and displays platform defaults.

## Raspberry Pi / Linux defaults

Application:
 /opt/shipwatch

Configuration:
 /etc/shipwatch

Data:
 /var/lib/shipwatch

Logs:
 /var/log/shipwatch

Web files:
 /var/www/shipwatch

Backups:
 /var/backups/shipwatch

Shipwatch executable:
 /usr/local/bin/shipwatch-air.py

## Windows 10 defaults

Application:
 C:\Program Files\Shipwatch

Configuration:
 C:\ProgramData\Shipwatch\config

Data:
 C:\ProgramData\Shipwatch\data

Logs:
 C:\ProgramData\Shipwatch\logs

Web files:
 C:\ProgramData\Shipwatch\web

Backups:
 C:\ProgramData\Shipwatch\backups

## macOS defaults

Application:
 /Applications/Shipwatch

Configuration:
 /Library/Application Support/Shipwatch/config

Data:
 /Library/Application Support/Shipwatch/data

Logs:
 /Library/Logs/Shipwatch

Web files:
 /Library/Application Support/Shipwatch/web

Backups:
 /Library/Application Support/Shipwatch/backups

For every path:
- Show default
- Browse / Change
- Test write permission
- Check free disk space

# Step 7 — Network Settings

Ask:

Shipwatch web port
Default: 8080 for new cross-platform installs

Radio/audio API port
Default: 8088

AIS-Catcher web port
Default: 8100

AIS service port
Default: 8118

readsb ports:
- Raw input: 30001
- Raw output: 30002
- SBS output: 30003
- Beast input: 30004
- Beast output: 30005
- Secondary Beast input: 30104

Bind address:
- Local computer only
- Local network
- Custom interface

Recommended:
Local network

Test:
- port availability
- firewall requirements
- address conflicts

Show:
http://HOST:PORT/

# Step 8 — Receiver Detection

Scan all supported SDR devices.

Display a table:

Receiver | Manufacturer | Product | Serial | USB path | In use by

Example:
AIRNAV | ADSB_1090 | 00000010
Generic | RTL2832U | 77771111153705700

After detection, ask:

How many receivers do you want Shipwatch to use?

Choices:
- 2 receivers — ADS-B dedicated, AIS and Voice shared
- 3 receivers — ADS-B dedicated, AIS dedicated, Voice dedicated
- Custom / advanced

Recommended:
3 receivers when available.

If fewer than two compatible receivers are present:
- warn clearly
- offer Retry
- offer Continue in single-receiver/test mode
- explain feature limitations

If three or more receivers are present:
- recommend a dedicated third Voice receiver;
- allow the user to remain on the two-receiver layout.

Do not assign receivers by index such as device 0/device 1.

# Step 9 — Assign ADS-B Receiver

Ask:

Which receiver is the aircraft ADS-B receiver?

Show detected devices.

Save serial number.

Test:
- open selected SDR
- tune receiver
- start temporary readsb validation
- confirm data process launches

If receiver is busy:
show which process owns it.

# Step 10 — Assign AIS and Voice Receiver(s)

The ADS-B receiver must be excluded from these selections.

## Two-receiver layout

Ask:

Which receiver is the Marine AIS / Voice shared receiver?

Save its serial number for AIS and Voice.

Test:
- open selected SDR;
- validate AIS-Catcher can claim it;
- release it after test.

Explain:

This receiver normally belongs to AIS.
The Voice Scanner temporarily borrows it.
Shipwatch automatically returns it to AIS.

Voice safety lease:
Default: 15 minutes

Allow:
- 5 minutes
- 10 minutes
- 15 minutes
- 30 minutes
- Custom

## Three-receiver layout

Ask:

Which receiver is the Marine AIS receiver?

Then ask:

Which receiver is the dedicated Voice Scanner receiver?

Each selection must be a different serial number.

Test each independently.

Explain:

With a dedicated third Voice receiver, AIS remains online continuously while Voice scanning is active.

In this layout, the Voice safety lease is not required for AIS protection, but an optional scanner timeout may still be configured.

# Step 11 — Antenna Checklist

Ask user to confirm:

- ADS-B antenna connected to ADS-B receiver
- Marine/AIS antenna connected to AIS/voice receiver
- Antennas are placed safely
- SDR USB connections are secure

Pi-specific:
Check USB power warnings.

If low-power or USB power-cycle events are detected:
Display:

Power warning detected.
Multiple SDR receivers can exceed reliable USB power on some hosts.
Three SDR installations are especially likely to benefit from a powered USB hub.
Use an adequate host/Pi power supply and/or powered USB hub.

Allow Retry after correcting hardware.

# Step 12 — Aircraft / readsb Configuration

Ask:

Receiver gain
Default: Auto

PPM correction
Default: 0

Maximum range
Default: 450 nautical miles equivalent setting used by readsb

Latitude / longitude
Use station values

Enable tar1090 aircraft map?
Default: Yes

Test:
- readsb starts
- expected SDR serial is found
- /run/readsb or platform equivalent produces JSON
- aircraft.json endpoint returns HTTP 200

Do not require an aircraft to be visible for installation success.
A healthy empty aircraft list is valid.

# Step 13 — Marine / AIS Configuration

Ask:

Enable AIS?
Default: Yes

AIS channels:
Default: A + B

Enable AIS map?
Default: Yes

Enable realtime updates?
Default: Yes

Test:
- AIS-Catcher starts
- selected receiver serial is found
- AIS map endpoint responds
- no other process owns receiver unexpectedly

# Step 14 — Voice Scanner

Ask:

Enable Voice Scanner?
Default: Yes

Banks:
- Air
- Marine
- Ham
- FRS/GMRS
- Custom banks

Default volume
Default: 70%

Default squelch
Default: 5

Voice lease
Use value selected earlier.

If the two-receiver layout is selected, explain that Voice temporarily pauses AIS while using the shared receiver.

If the three-receiver layout is selected, explain that Voice uses its own dedicated SDR and AIS remains online.

# Step 15 — External Feed Setup

Optional screen. MastChain participation is opt-in and must not be required to finish a Shipwatch install.

Explain that MastChain is an external AIS coverage network. Offer links to its account setup and operator instructions. Let the user create or sign into an account through MastChain; Shipwatch must not collect the account password or automate account enrollment.

Offer these choices, all optional and defaulting to No:
- Create/use the installer's own MastChain account and add this receiver.
- Contribute this receiver to the configured Shipwatch operator's MastChain account.
- Skip MastChain setup.

For the operator-account option, identify the receiving account by a configured, user-visible operator name before asking for consent. State plainly that the receiver's AIS data and location will be shared with MastChain and associated with that operator's account; any MastChain rewards for the station go to that account, not the receiver owner. Do not describe this as donating idle time: it is an ongoing AIS-data and station-location contribution. Require a separate, unchecked confirmation from the person responsible for the receiver. Allow the user to choose their own account instead, or skip.

For a remote receiver that opts into the operator account, collect the requested station name and actual receiver coordinates only after consent, then create a pending enrollment request for the operator to review. Provide an optional daily email digest that says new opt-ins are waiting; email must not include precise location, AIS data, MastChain credentials, or wallet details. The operator opens an authenticated approval queue, reviews the request and consent, and approves each station before it is added. AtlanticLink.ca is the selected host for this control plane; the API base is `https://atlanticlink.ca/shipwatch-ota/api/v1/`, with the approval queue inside the existing authenticated AtlanticLink admin. Implement this as an isolated Shipwatch module with separate data tables and narrowly scoped device endpoints. No OTA API, queue, or scheduled email is deployed yet; do not claim that this notification works until server code, database setup, mail scheduling, and protected request handling are implemented and verified.

Install and enroll the background OTA agent as part of each supported customer's initial Shipwatch installation, with clear disclosure and an opt-out if remote management is not wanted. All agents use the same AtlanticLink control plane and signed-update protocol; each platform adapter installs and runs the agent using its native background-service mechanism (systemd on Linux, a protected Windows scheduled task or service on Windows, and launchd on macOS). This makes a receiver reachable for later, separately approved MastChain configuration without another site visit. The agent needs a device identity, outbound secure connection, signed configuration updates, expiry/revocation, and rollback. After the operator creates/authorizes the station and MastChain issues its station-specific upload credential, deliver only the required receiver configuration through this authenticated, encrypted channel; do not deliver account passwords, browser cookies, wallet details, or upload credentials by ordinary email. OTA must change only the MastChain feed settings and restart only the required receiver service after approval. Linux/Pi now has local agent enrollment code gated by a pinned release configuration, but it has not been run against a deployed controller or receiver. Windows and macOS still have no apply engines; their service-registration adapters alone do not enable OTA. Do not advertise OTA support on any platform until its installer can install, enroll, and verify the complete agent flow. Do not describe the flow as available until the installer, request service, notification delivery, agents, and end-to-end checks have been built.

MastChain's dashboard supports adding a station and provides DIY AIS-Catcher setup for Raspberry Pi/Linux, Windows, and macOS. For each station, collect a short name and pin the actual receiver location on the map; enable the mobile-station option only when it is installed on a boat. Saving this profile does not start data uploads. Once the account owner has created/authorized the station and MastChain has issued that station's connection details, automate the platform-specific AIS-Catcher configuration and verify the feed is reporting. For a fresh install, generate the config with the MastChain output enabled. For an existing AIS-Catcher install, back up its config, merge the MastChain output without replacing other outputs or device settings, then restart only the affected service after review. Treat every receiver as its own station with its own MastChain-provided configuration and credentials; never reuse another station's secret.

Use an official, documented API or delegated authorization flow for remote station creation only if MastChain provides one and it authorizes the operator to add a station to the selected account. If an API is unavailable, the account owner may create the approved station manually in their own MastChain session, then securely hand off the station-specific connection details to the remote installer. Do not transfer browser cookies or account passwords to remote receivers. If no supported way to authorize creation or securely return station details exists, leave the request pending and MastChain disabled on that receiver. Do not claim automated account enrollment. If configuration cannot be applied safely without replacing the existing receiver setup, stop and leave MastChain disabled.

Before enabling upload, explain exactly which AIS messages and station metadata will be sent. MastChain asks for station location to verify coverage, so disclose that the user will share the receiver's location with MastChain and, for operator-account enrollment, the operator account owner. Explain that uploading continues while enabled. Never request or store an account password. Store any required station credential only in the protected secret store/config, and never print it in logs, diagnostics, or documentation. Provide a connection check only when it can be done without exposing the credential.

Explain the current reward status before opt-in. MastChain's beta documentation says beta rewards are testnet tMAST and have no mainnet value; token mechanics may change.

Offer a separate, unchecked choice to share feedback with the Shipwatch application author. Show the exact feedback and any diagnostic fields first, and require a separate user action to open/send it. Never include MastChain credentials, wallet details, account email, or precise receiver location in feedback by default.

Other future feeds should use the same provider-plugin model.

# Step 16 — Web Interface

Ask:

Interface name
Default: Shipwatch

Open browser automatically after installation?
Default: Yes

Allow access from other devices on LAN?
Default: Yes

If Yes:
- configure firewall rule where required
- show LAN URL

Optional:
- HTTPS
- reverse proxy
- hostname

# Step 17 — Startup Services

Show services that will be installed.

Linux/Pi:
- shipwatch-air.service
- ais-catcher.service
- readsb.service
- tar1090
- lighttpd or chosen web server

Windows:
- Shipwatch Receiver service
- Shipwatch Web service
- helper processes as required

macOS:
- Shipwatch launchd daemon(s)

Ask:
Start Shipwatch automatically at boot?
Default: Yes

# Step 18 — Backup / Existing Installation

If existing Shipwatch files are detected:

Show:
- current version
- installation path
- configuration path
- last modified date

Choices:
- Back up and upgrade
- Repair
- Fresh install alongside existing copy
- Cancel

Always create a timestamped backup before changing an existing installation.

# Step 19 — Review Before Installation

Display a complete summary:

Station:
Host:
Platform:
Install path:
Config path:
Data path:
Web path:
SSH host:
SSH user:
Receiver layout:
ADS-B SDR serial:
AIS SDR serial:
Voice SDR serial:
Voice shares AIS receiver:
Web port:
Radio port:
AIS port:
Voice lease:
Startup enabled:
MastChain enabled:

Do NOT display:
- SSH passwords
- private key contents
- feed secrets
- tokens

Buttons:
- Install
- Back
- Cancel
- Export Settings

# Step 20 — Installation Progress

Show named stages, not raw command spam:

1. Preflight
2. Backup
3. Dependencies
4. Application files
5. Receiver configuration
6. Aircraft service
7. AIS service
8. Voice service
9. Web interface
10. Startup services
11. Firewall
12. Health checks

Each line shows:
- Waiting
- Running
- PASS
- FAIL

Detailed logs available behind:
Show Technical Details

# Step 21 — Final Health Check

Required checks:

PASS/FAIL:
- ADS-B SDR detected by configured serial
- AIS SDR detected by configured serial
- Voice SDR detected when dedicated Voice mode is selected
- receiver role assignments match the selected two- or three-receiver layout
- no accidental duplicate serial assignments except intentional AIS/Voice sharing in two-receiver mode
- readsb running
- readsb JSON endpoint HTTP 200
- AIS-Catcher running
- AIS endpoint responding
- Shipwatch radio service running
- web UI responding
- tar1090 responding
- voice/AIS ownership policy installed
- configured ports listening
- startup services enabled
- USB power healthy or warning acknowledged
- optional MastChain upload test

Important:
No aircraft or ships currently in range is not an installation failure.

# Step 22 — Installation Complete

Show:

Shipwatch installed successfully.

Aircraft map:
http://HOST:PORT/...

Marine map:
http://HOST:PORT/...

Radio:
http://HOST:PORT/...

Admin / Health:
http://HOST:PORT/health

Buttons:
- Open Shipwatch
- Open Health Check
- View Manual
- Export Configuration
- Finish

# Saved Configuration

The installer should produce a non-secret configuration file based on shipwatch.example.json.

Secrets must be stored separately.

Suggested split:

shipwatch.json
- station
- paths
- ports
- receiver serials
- feature flags
- voice lease
- UI settings

shipwatch.secrets.json or OS key store
- feed secrets
- API tokens
- credentials when unavoidable

Permissions on secret storage must be restricted to the service/user that needs them.

# Repair Wizard

The installer must also work later as a repair tool.

Repair options:
- Test SSH
- Detect receivers
- Reassign ADS-B receiver
- Reassign AIS receiver
- Reassign Voice receiver
- Switch between two-receiver and three-receiver layouts
- Repair services
- Repair web server
- Repair firewall
- Test ports
- Test MastChain
- Check USB power
- Restore configuration backup
- Collect diagnostic report

# Uninstaller

Ask whether to preserve:
- configuration
- logs
- receiver assignments
- feed credentials
- backups

Never delete user configuration silently.
