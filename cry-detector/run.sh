#!/usr/bin/env bash
# Build + (re)start the YAMNet baby-cry classifier container.
# Configure via environment (or copy ../.env.example to ../.env and `source` it).
set -euo pipefail
cd "$(dirname "$0")"

docker build -t baby-cry-detector .
docker rm -f baby-cry-detector >/dev/null 2>&1 || true
docker run -d --name baby-cry-detector --network host --restart unless-stopped \
  -e PYTHONUTF8=1 \
  -e NTFY_URL="${NTFY_URL:-http://localhost:8095/baby-cry}" \
  -e CRY_CLICK_URL="${CRY_CLICK_URL:-http://localhost:1985/multi.html}" \
  -e GO2RTC_RTSP="${GO2RTC_RTSP:-rtsp://localhost:8554}" \
  -e CAMS="${CAMS:-cam1=Room 1,cam2=Room 2}" \
  -e CRY_PROB="${CRY_PROB:-0.4}" \
  -e CRY_SUSTAIN_SAMPLES="${CRY_SUSTAIN_SAMPLES:-2}" \
  -e CRY_COOLDOWN="${CRY_COOLDOWN:-60}" \
  -e CRY_LOG="${CRY_LOG:-1}" \
  baby-cry-detector
echo "baby-cry-detector started. Follow logs with:  docker logs -f baby-cry-detector"
