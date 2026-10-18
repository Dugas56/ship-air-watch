#!/bin/bash
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "FAIL: Run this installer with sudo." >&2
  exit 2
fi

label="com.shipwatch.ota"
agent="/Library/Shipwatch/ota/shipwatch_ota_agent.py"
python="/Library/Shipwatch/ota/venv/bin/python"
config="/Library/Application Support/Shipwatch/OTA/agent.json"
key="/Library/Application Support/Shipwatch/OTA/device-signing-seed.b64"
marker="/Library/Application Support/Shipwatch/OTA/enrollment-confirmed"
plist_source="/Library/Shipwatch/ota/com.shipwatch.ota.plist"
plist_target="/Library/LaunchDaemons/${label}.plist"

for file in "$python" "$agent" "$config" "$key" "$marker" "$plist_source"; do
  if [[ ! -f "$file" ]]; then
    echo "FAIL: Required enrolled OTA file is missing: $file" >&2
    exit 1
  fi
done

if ! "$python" -c 'import nacl' >/dev/null 2>&1; then
  echo "FAIL: PyNaCl is unavailable to the Shipwatch Python runtime." >&2
  exit 1
fi

/usr/sbin/chown -R root:wheel /Library/Shipwatch/ota
/usr/sbin/chown root:wheel "$config" "$key" "$marker"
/bin/chmod 0755 "$agent"
/bin/chmod 0600 "$config" "$key" "$marker"
/bin/mkdir -p /Library/LaunchDaemons
/usr/bin/install -o root -g wheel -m 0644 "$plist_source" "$plist_target"
/usr/bin/plutil -lint "$plist_target"

if /bin/launchctl print "system/${label}" >/dev/null 2>&1; then
  /bin/launchctl bootout "system/${label}"
fi
/bin/launchctl enable "system/${label}"
/bin/launchctl bootstrap system "$plist_target"

echo "PASS: Shipwatch OTA launch daemon installed after enrollment confirmation."
