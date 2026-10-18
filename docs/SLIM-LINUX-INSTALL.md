# Shipwatch Slim Linux Installation Strategy

## Goal

A fresh Linux/Pi installation should finish with only the runtime components required by Shipwatch.

Development tools are allowed during installation but should be removed again after the required binaries are built and verified.

## Runtime packages retained

- rtl-sdr
- ffmpeg
- lighttpd
- python3
- python3-requests
- python3-waitress
- curl
- openssh-server
- usbutils
- lsof
- AIS-Catcher runtime package
- readsb runtime binary/service
- tar1090 runtime/service
- Shipwatch runtime/service

## Temporary build phase

For components that need compilation:

1. Record the currently manually installed packages.
2. Install only the build dependencies required for the component.
3. Clone/fetch the pinned known-good upstream revision.
4. Build in a temporary directory.
5. Install only the resulting runtime files.
6. Start the component and run health checks.
7. If health checks fail, stop and preserve the build/logs for diagnosis.
8. If health checks pass, purge temporary build dependencies that were added by Shipwatch.
9. Run autoremove only against packages made unnecessary by the Shipwatch build phase.
10. Delete temporary source/build directories.

This gives us a reproducible build without leaving GNU Radio, compilers, development headers, Qt, or OP25 on the finished receiver.

## Known-good component references

### readsb

Upstream:
https://github.com/wiedehopf/readsb.git

Reference:
- Version 3.16.15
- Commit cc0d099758be794598026ec1eb9de178a5d4e53b

The reference Pi currently uses a manually built /usr/bin/readsb binary.

### tar1090

Upstream:
https://github.com/wiedehopf/tar1090

Reference:
- Version 3.14.1814
- Commit e5a017021de1a50a5bfb7d59040b141a3fc9a158

### AIS-Catcher

Upstream:
https://github.com/jvde-github/AIS-catcher

Reference package:
0.70~3459-g10781d37

Prefer an official target-architecture release package when available.

## Final verification before cleanup

The installer must verify:

- configured SDR serials are visible;
- readsb service is active;
- aircraft JSON endpoint returns HTTP 200;
- AIS-Catcher service is active;
- AIS web endpoint responds;
- Shipwatch service is active;
- tar1090 service is active;
- Lighttpd is active;
- rtl_fm and rtl_test remain installed;
- configured ports are listening;
- no required binary depends on a temporary package that is about to be removed.

Only after all required checks pass may the temporary build stack be removed.
