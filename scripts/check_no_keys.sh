#!/bin/bash
# 커밋 전에 키 문자열이 저장소 파일에 들어갔는지 본다. 키 값은 화면에 찍지 않는다.
# 사용: scripts/check_no_keys.sh <.env 파일>...   (KEY=VALUE 줄의 값만 검사)
cd "$(dirname "$0")/.."
found=0
# 주최가 누리집에 공개한 실시간 주차 키는 화면 코드(site/app.js)에 넣기로 했다(2026-11-14 사용자 결정). 검사에서 뺀다.
PUBLIC_KEYS=" KSPO_PARKING_API_KEY "
for f in "$@"; do
  while IFS='=' read -r name val; do
    [[ -z "$val" || "$name" =~ ^# || "$PUBLIC_KEYS" == *" $name "* ]] && continue
    enc=$(python3 -c 'import sys,urllib.parse as u;print(u.quote(sys.argv[1],safe=""))' "$val")
    if git ls-files -co --exclude-standard -z | xargs -0 grep -lF -e "$val" -e "$enc" 2>/dev/null; then echo "키 발견: $name"; found=1; fi
    if git log --all -p 2>/dev/null | grep -qF -e "$val" -e "$enc"; then echo "커밋 기록에 키 발견: $name"; found=1; fi
  done < <(grep -E '^[A-Za-z0-9_]+=' "$f")
done
[ $found = 0 ] && echo "키 문자열 없음"
exit $found
