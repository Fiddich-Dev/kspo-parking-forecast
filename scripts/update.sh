#!/bin/bash
# 수집 -> 예보·성적표 -> 내일 예보 고정 -> main에 커밋 -> site/를 gh-pages 브랜치로 배포.
# GitHub Actions(.github/workflows/update.yml)와 맥미니 예약 작업이 이 스크립트 하나를 같이 쓴다.
# 키는 환경변수로 받는다(OPERATIONS.md). 성공하면 아무것도 출력하지 않는다.
set -uo pipefail
cd "$(dirname "$0")/.."
git pull -q --rebase --autostash origin main || { echo "git pull 실패"; exit 1; }
python3 pipeline/run.py collect >/dev/null || echo "실시간 수집 실패(예보는 계속 만든다)" >&2
python3 pipeline/run.py build || exit 1
python3 pipeline/run.py freeze >/dev/null || exit 1
git add data site/data
if ! git diff --cached --quiet; then
  git commit -q -m "data: $(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M') 갱신" && git push -q origin main || { echo "main push 실패"; exit 1; }
fi
git fetch -q origin gh-pages
tree=$(git rev-parse HEAD:site)
if [ "$tree" != "$(git rev-parse 'origin/gh-pages^{tree}')" ]; then
  c=$(git commit-tree "$tree" -p origin/gh-pages -m "배포: main $(git rev-parse --short HEAD)")
  git push -q origin "$c:refs/heads/gh-pages" || { echo "gh-pages push 실패"; exit 1; }
fi
