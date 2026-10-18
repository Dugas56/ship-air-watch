# Ship Air Watch history

Installed 2026-10-08. Console backed up before heading and SETUP changes.

SETUP opens saved history inside the LCD. The existing USB socket animates a virtual drive insertion and opens the same view. RADIO returns to the console; MENU and SETTINGS retain their radio controls.

The passive collector polls AIS-catcher and readsb every 15 seconds. Windows task: ShipAirWatch History Collector; starts at user logon and runs while the PC and user task run, even with the browser closed. Data/config: C:\ProgramData\ShipAirWatch. Portable runtime: product/runtime/common/shipwatch-history.py with --home for another data directory. Feed URLs and harbour circle are configurable.

The provisional Saint John observation circle is centred at 45.27, -66.065, radius 6 km. First sightings within it have unknown arrival times and minimum observed stays. Confirmed exit requires fresh positions beyond a 0.5 km buffer across at least 60 seconds. Gaps mark interrupted observation and do not create returns. Buoys, navigation aids and base stations are excluded. Returns are additional observed visits since logging began, not lifetime port-call totals.

Aircraft sessions are observed passes, not airport arrivals or landings. A callsign change or ten-minute reception gap ends a session. Destinations are not inferred. Voice can occupy the shared marine SDR, making AIS unavailable; history reports that outage and retries without changing radio mode.

Ship positions are sampled at most once per minute; aircraft positions once per 30 seconds. Detailed samples are retained seven days and capped at 200,000 rows, deleting oldest detail first. Profiles and visit/pass summaries remain. SQLite incremental vacuum reclaims or reuses freed storage. Daily consistent compressed SQLite backups are retained for seven days. The detail cap is not an absolute file-size cap; long-term summaries still grow slowly. Database plus WAL size is shown in the UI. Up to 500 profiles/sessions are returned per request, while full summary history remains stored.

Validation passed: product/tests/test-history.py covers sampling, signal gaps, exits, returns, aircraft sessions, retention, row cap and compressed-backup restoration using an isolated temporary database. .codex/tools/verify_history_ui.cjs verifies the actual local API and page, heading, SETUP, aircraft records, USB animation, RADIO return and existing settings. Four real aircraft profiles were captured during validation. AIS was unavailable during voice mode.

## Tug work and pop-out update
SETUP and the virtual USB control now open a reusable 1300x850 history window. The embedded panel remains a fallback when pop-ups are blocked. RADIO closes the pop-out and leaves the radio console open.
Harbour tugs (AIS ship type 52 and the supplied Hemlock/Cedar identities) have a separate TUGS list. They are excluded from visitor and visit totals, and newly received tug positions do not create visitor sessions. Existing raw history is preserved. The live list identified six harbour tugs during validation.
TUGS displays recorded tow/assist count, last assisted ship and assist time. RECORD stores a user-observed or radio-confirmed assist, with optional notes. These are confirmed user records, not automatically inferred AIS tows. Unrecorded work displays Not recorded, and zero means zero recorded assists. Exact duplicate saves do not inflate counts.
product/tests/test-tug-history.py uses an isolated temporary database and local PHP test server to validate classifications, visitor totals, assist persistence, last assisted ship, duplicate handling and request validation. .codex/tools/verify_tug_popout.cjs verifies the actual pop-out, tug columns, return control and virtual USB opening. Both passed.


### USB mascot motion repair — 2026-10-08
The deliberate socket click opts into the optional 6.2-second flight, including browsers reporting prefers-reduced-motion: reduce. Loading the page never starts a flight. The socket can replay the trip; the inserted CLICK ME drive and perched mascot open the history popout on a separate user click. The carried drive is positioned at the beak; the bird briefly winks after returning to the upper right. Asset version queries invalidate the earlier cached scripts and styles.
Validation: test_gull_motion.cjs asserted changing transforms during actual elapsed time with reduced motion enabled, no first-click popup, docking and perching, second-click history, replay, and replay after reload. Passed. Visual inspection of the beak/port approach screenshot also passed.
