# Shipwatch OTA Control Plane

Status: controller deployed and preflighted on AtlanticLink.ca. The API and pinned public verification key are live; daily digest remains disabled. Native Windows/macOS receiver enrollment and end-to-end update delivery still require platform verification.

## Host and boundaries

- Host the Shipwatch control plane at AtlanticLink.ca with the device API under `/shipwatch-ota/api/v1/` and the owner review page under `/admin/shipwatch-ota.php`.
- Keep the receiver API isolated from the general website and use the existing AtlanticLink admin login for the owner approval page.
- Keep Shipwatch requests and device state in separate tables. Never let a device endpoint use an admin session or perform arbitrary commands.
- A receiver initiates outbound HTTPS polling. The controller does not open inbound connections to customer networks.
- The daily email is a notice that requests are waiting. It contains no exact coordinates, AIS data, or credentials; the owner reviews each request in the authenticated queue.

## Enrollment and MastChain handoff

1. During installation, explain remote management and MastChain data/location sharing separately. Both choices start unchecked and can be declined.
2. If remote management is accepted, create a unique receiver identity and send a pending request containing only the disclosed station name, consent record, and requested location.
3. The owner reviews the request and consent. Approval does not itself enroll a MastChain station.
4. The owner creates or authorizes the station in MastChain, since no documented delegated station-creation API has been established.
5. The owner enters the station-specific feeder configuration in the protected approval page. Encrypt it for that receiver before storage or delivery; do not place credentials in email.
6. The receiver polls over HTTPS, authenticates as that device, verifies the server signature, decrypts its own configuration, backs up the current AIS-Catcher config, applies only the MastChain output, and restarts only AIS-Catcher after validation.

## Consent record version v1

- Remote management: the receiver's station name and device public key are sent to AtlanticLink. The receiver makes outbound check-ins and can receive separately approved, signed MastChain feed settings. The agent does not accept remote shell commands.
- MastChain contribution: only after a separate opt-in, the receiver's exact location is sent to the operator's review queue. If the operator approves and configures a station, the receiver's AIS data is sent to MastChain using that station's credentials. The installer must not promise rewards or token value.
- Keep these choices separate, unchecked by default, and store the accepted consent version and time. Declining either choice must not prevent installation.

## Device security and recovery

- Generate a distinct device key during installation. Store its private part with restrictive permissions; store only the corresponding public key with the enrollment request.
- Pin the controller's Ed25519 verification key and reject HTTP redirects so device signatures are never forwarded to another host.
- Sign configuration envelopes and verify signatures using a public verification key shipped with the agent. Bind every envelope to one device, one sequence number, and an expiry.
- Support owner revocation, request cancellation, replay rejection, version checks, bounded retries, and restoring the last known-good AIS-Catcher configuration.
- The agent accepts declarative feed settings only. It never executes commands supplied by the server.
- Redact secrets from HTTP errors, service logs, diagnostics, and email.

## Build and release order

1. [x] Confirm the AtlanticLink host supports the required PHP cryptography extension, HTTPS, and database schema; configure private server keys outside the public web root. `product/runtime/common/ota-release-config.json` now contains the API URL and matching public verification key. Never distribute the private signing key or fetch the public key from an unverified endpoint.
2. [x] Build and deploy the isolated PHP API, tables, and authenticated approval page. Live preflight passes; the API returns the pinned Ed25519 public key; the admin route retains the existing login.
3. [ ] Add the daily scheduled digest using the existing mailer after confirming its deployed sender and scheduler configuration. Use the host-specific command format in `shipwatch-ota/DEPLOYMENT.md`; do not enable it until the recipient and delivery path are confirmed. The digest is currently disabled.
4. Finish the shared agent integration and connect native background-service adapters to each platform installer. Each installer must install dependencies, record consent, enroll, activate the adapter, and verify it before that platform is described as supported.
5. [x] Review a scoped deployment and deploy only the Shipwatch control-plane files and schema. Do not upload the complete local web project as an OTA release.
6. Verify a disposable receiver end to end: opt-in, notification, owner approval, station configuration, signed delivery, backup, service restart, status report, and revocation.

## Current limitations

- The Linux/Pi installer presents separate default-No consent choices when a valid pinned release config is packaged, creates a protected device identity, enrolls with the controller, and enables its timer only after signed enrollment confirmation. No end-to-end receiver has applied a configuration.
- Windows and macOS have an OTA-only enrollment path for an existing AIS-Catcher installation. Run `python product/installers/common/shipwatch_installer.py --ota-only`; this installs PyNaCl in a private virtual environment, enrolls only after default-No consent, and enables polling only after signed confirmation. MastChain consent also requires the existing AIS-Catcher config path. A release candidate bundle is at `product/releases/Shipwatch-OTA-Windows-macOS-0.1.0-rc1.zip`. This does not install Shipwatch's receiver stack or web UI on those platforms, and has not been exercised on native Windows/macOS hosts.
- The controller, six OTA tables, and private signing key are deployed. The API key endpoint and CLI preflight pass. The daily digest is not activated. The signing secret is stored outside `public_html`; only its public verification key is in the local runtime config.
- Do not describe OTA updates as available on a platform until its consent, enrollment, signed delivery, service restart, status report, and revocation flow have been verified on a receiver for that platform.
- AtlanticLink's PHP/Sodium support, HTTPS API, database tables, protected key storage, and authenticated admin route have been verified. SMTP settings are present; no test email was sent and no digest schedule was created.
- MastChain station creation remains an owner action in MastChain unless an official delegated API becomes available.
- Do not tell customers this feature is available until the complete flow is built and verified.

## Implementation checklist

- [x] Draft isolated PHP API and SQL tables.
- [x] Draft authenticated owner review, guarded status transitions with an audit record, and encrypted configuration queue.
- [x] Add shared receiver agent and platform service definitions to the payload manifest.
- [x] Package the dormant agent and service definitions in the Linux/Pi installation path.
- [x] Connect default-No installer consent and agent enrollment on Linux/Pi, gated by a pinned release config.
- [x] Add Windows Task Scheduler and macOS LaunchDaemon registration adapters guarded by enrollment confirmation.
- [x] Add an OTA-only Windows/macOS consent, dependency, protected identity, enrollment, and adapter-registration path for existing AIS-Catcher installs.
- [ ] Finish Windows and macOS base receiver installation support.
- [x] Configure and deploy the controller, signing key, and schema on AtlanticLink; digest remains disabled pending delivery-path confirmation.
- [ ] Complete opt-in through revocation checks on one receiver per platform.
