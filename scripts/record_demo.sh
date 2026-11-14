#!/bin/bash
# 시연 영상 만들기: ?demo=1&step=N 네 장면을 휴대폰 폭(390x844)으로 캡처해 장면당 5초짜리 mp4로 잇는다.
# 필요: python3, npx(playwright를 받아 설치된 Google Chrome으로 연다), ffmpeg
# 사용: scripts/record_demo.sh [주소]   주소를 안 주면 site/를 로컬에서 띄워 찍는다.
# 결과: docs/demo/demo.mp4, docs/demo/step*.png
set -euo pipefail
cd "$(dirname "$0")/.."
out=docs/demo
mkdir -p "$out"
url=${1:-}
if [ -z "$url" ]; then
  python3 -m http.server 8766 -d site >/dev/null 2>&1 &
  srv=$!
  trap 'kill $srv' EXIT
  sleep 1
  url=http://localhost:8766/
fi
for i in 0 1 2 3; do
  npx -y playwright@1.49.1 screenshot -b chromium --channel=chrome --viewport-size=390,844 \
    --wait-for-timeout=1500 "${url}?demo=1&step=$i" "$out/step$i.png" >/dev/null
done
ffmpeg -y -loglevel error -framerate 1/5 -i "$out/step%d.png" -vf "fps=30,format=yuv420p,scale=780:-2" "$out/demo.mp4"
echo "$out/demo.mp4"
