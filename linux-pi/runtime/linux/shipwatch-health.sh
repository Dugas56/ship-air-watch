#!/usr/bin/env bash
set -u

echo "================ RESULTS ================"

for x in AIS-catcher readsb rtl_fm rtl_test ffmpeg python3 lighttpd; do
  if command -v "$x" >/dev/null 2>&1; then
    echo "PASS: BINARY_$x"
  else
    echo "FAIL: BINARY_$x"
  fi
done

for s in ais-catcher readsb shipwatch-air tar1090 lighttpd; do
  if systemctl is-active --quiet "$s"; then
    echo "PASS: SERVICE_$s"
  else
    echo "FAIL: SERVICE_$s"
  fi
done

if curl -fsS http://127.0.0.1/tar1090/data/aircraft.json >/dev/null 2>&1; then
  echo "PASS: TAR1090_JSON_HTTP_200"
else
  echo "FAIL: TAR1090_JSON_UNAVAILABLE"
fi

if curl -fsS http://127.0.0.1:8100/ >/dev/null 2>&1; then
  echo "PASS: AIS_WEB_RESPONDING"
else
  echo "FAIL: AIS_WEB_NOT_RESPONDING"
fi

echo "RESULT: SDR_COUNT=$(rtl_test -t 2>&1 | grep -c 'SN:' || true)"
echo "RESULT: DISK=$(df -h / | awk 'NR==2 {print $3 " used / " $4 " free (" $5 ")"}')"
echo "NEXT: REVIEW_RESULTS"
