# 운영 문서

올팍 주차예보를 2028년까지 돌리기 위한 문서다. 서버가 없다. GitHub 저장소 하나에 정적 화면(`site/`), 파이썬 표준 라이브러리 스크립트(`pipeline/`), 예약 실행(`.github/workflows/update.yml`)이 모두 들어 있다.

## 무엇이 언제 도나

> **기록**: 2026-11-14~11-20에는 GitHub 계정 결제 잠금("The job was not started because your account is locked due to a billing issue.")으로 Actions가 시작되지 않아 맥미니 Hermes 예약 작업 `kspo-forecast`가 같은 `scripts/update.sh`를 돌렸다. 2026-11-20 수동 실행이 성공해 워크플로 `update`를 켜고 맥미니 작업을 지웠다. 지금은 아래 표대로 GitHub Actions가 돌린다.

모든 갱신은 `scripts/update.sh` 하나가 한다: 수집 → 예보·성적표 → 22~24시면 내일 예보 고정 → main 커밋 → `site/`를 gh-pages 브랜치에 올림(GitHub Pages가 그 브랜치를 배포).

| 일 | 주기 | 어디서 |
|---|---|---|
| 실시간 주차대수 기록(`run.py collect`) | 30분마다(매시 7분, 37분) | GitHub Actions |
| 일정 읽기, 단기예보, 예보·성적표 JSON 만들기(`run.py build`) | 같은 실행에서 | GitHub Actions |
| 내일 예보 고정(`run.py freeze`) | 22~24시(한국) 첫 실행 한 번 | GitHub Actions. 결과 `data/frozen/<날짜>.json`, 커밋 시각이 저장 시각 증거 |
| 화면 배포 | 같은 실행 끝 | `site/`를 gh-pages 브랜치로 푸시 → GitHub Pages 기본 빌드 |

## 비용: 무료 조건 (2026-11-14 GitHub 공식 문서로 확인)

- 공개 저장소에서 표준 GitHub 호스트 실행기는 무료다. "The use of standard GitHub-hosted runners is free: In public repositories". https://docs.github.com/en/billing/concepts/product-billing/github-actions
- 예약 실행은 5분 간격이 가장 짧고, 부하가 많으면 늦어질 수 있다(정각이 특히). **공개 저장소에서 60일 동안 저장소 활동이 없으면 예약 실행이 자동으로 꺼진다.** https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows
- GitHub Pages 한도: 사이트 1GB 이하, 대역폭 월 100GB(느슨한 한도), 브랜치 배포는 시간당 10회 빌드(느슨한 한도). 이 서비스는 시간당 최대 2회다. https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits
- 이 서비스의 사용량: 실행 한 번 약 1분, 하루 48번. 사이트 크기 약 0.1MB. 위 한도 안이다.
- 60일 규칙: 30분마다 데이터 커밋을 하므로 활동이 계속 생긴다. 그래도 꺼지면(수집이 실패해 커밋이 멈춘 경우 등) Actions 화면의 `update` 워크플로에서 "Enable workflow"를 누른다.

## 한 달에 한 번 점검 (10분)

1. 배포 주소의 「성적표」 아래 「데이터 출처와 마지막 갱신」에서 실시간 마지막 수집 시각이 1시간 안인지 본다.
2. 저장소 Actions 탭에서 최근 `update` 실행이 초록색인지 본다. 빨간색이면 실행 기록의 어느 단계에서 멈췄는지 본다.
3. 「공연」 화면의 「일정 미확인」 목록을 본다. 있으면 아래 「일정을 손으로 고칠 때」.
4. 「성적표」의 저장해 둔 예보 줄이 공연 날마다 늘었는지 본다.

## 키 (저장소 비밀값)

코드, 문서, 로그, 커밋에 키를 쓰지 않는다. 저장소 Settings → Secrets and variables → Actions에만 둔다. 예외 하나: 실시간 주차현황 키는 주최가 누리집에 공개한 값이라 `site/app.js`에도 들어 있다(방문자 브라우저가 주최 API를 직접 불러 「지금」 값을 바로 받는다. 실패하면 30분마다 기록한 값을 보인다). 이 키가 바뀌면 비밀값과 `site/app.js`의 `PARKING_API` 두 곳을 고친다. 호출 기록(`site/data/calls.json`)에는 키를 `***`로 가린 주소만 남는다.

| 비밀값 이름 | 무엇 | 어디서 받나 |
|---|---|---|
| `KSPO_PARKING_API_KEY` | 올림픽공원 실시간 주차현황 API 키 | 한국체육산업개발 누리집 공공데이터 개방목록(https://www.ksponco.or.kr/pubData/64?mid=a10106020000) |
| `DATA_GO_KR_SERVICE_KEY` | 기상청 단기예보(공공데이터포털 15084084) | 공공데이터포털 활용신청 |
| `KCISA_KEY_675` | 2025 입출차·공연·날씨 연계 데이터(문화공공데이터광장 id 675) | 문화공공데이터광장 활용신청 |

키를 바꿀 때: `gh secret set <이름> -R <저장소>`로 새 값을 넣고 Actions에서 `update`를 수동 실행(Run workflow)해 초록색인지 본다.

## 주소나 형식이 바뀔 때

- 주소는 `pipeline/run.py` 위쪽 상수(`PARKING_URL`, `SCHEDULE_URL`, `WEATHER_URL`, `KCISA_675_URL`)에 한 줄씩 있다.
- 누리집 일정 화면의 HTML이 바뀌면 `run.parse_list_html`이 공연을 하나도 못 찾는다. 이때 지난번 결과를 그대로 쓰고 화면에 "최근 읽기 실패"가 뜬다. 정규식을 고친 뒤 `tests/fixtures/`에 새 화면 사본을 넣고 시험을 추가한다.
- 일정 문장 형식이 새로우면 그 공연은 「일정 미확인」으로 빠지고 카드와 공연 가산이 나오지 않는다(추측해서 채우지 않는다).

## 일정을 손으로 고칠 때

`data/manual_events.json`을 만들고 공연 번호(evtSeq)마다 덮어쓸 값을 적는다. 화면에 "사람이 고친 값"이 표시된다.

```json
{"5136": {"shows": [{"date": "2026-11-28", "times": ["15:00", "19:00"]}], "status": "ok"}}
```

## 무료 조건이 바뀌거나 GitHub를 못 쓰게 될 때

옮길 것이 적다(지금 맥미니가 하는 방식이 그 예다). 어느 리눅스나 맥에서든 `cron`으로 30분마다 키를 환경변수로 넣고 `scripts/update.sh`를 돌리거나, `pipeline/run.py`의 collect, build, freeze를 차례로 돌린 뒤 `site/` 폴더를 아무 정적 웹 서버(주최 누리집 서버 포함)에 올리면 된다. 파이썬 3.10 이상, 외부 패키지 없음.

## 주최에 넘길 때 (수상 시 원천 소스 제공)

저장소 전체가 원천 소스다. 넘기는 방법은 둘 중 하나다.
1. 저장소 소유권 이전(Settings → Transfer ownership). 비밀값은 옮겨지지 않으므로 받는 쪽이 세 키를 다시 넣는다.
2. 저장소를 zip으로 받아 주최 서버에서 위 「무료 조건이 바뀌거나」 방식으로 돌린다.

## 공모전 뒤 정리할 것

- 맥미니 Hermes 예약 작업 `kspo-parking`(5분마다 수집, 공모전 근거용, 이 저장소와 별개 파일)과 `kspo-forecast`는 2026-11-20 제출 뒤 지웠다. 5분 기록 CSV는 공모전 서류 폴더에 보관한다.
