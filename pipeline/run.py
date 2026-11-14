"""올팍 주차예보 파이프라인. 파이썬 표준 라이브러리만 쓴다.

  python3 pipeline/run.py collect   # 실시간 주차대수 한 줄을 data/realtime/parking.csv에 더한다
  python3 pipeline/run.py build     # 일정·날씨를 읽고 site/data/*.json(예보, 성적표, 호출 기록)을 만든다
  python3 pipeline/run.py freeze    # 22~24시(한국)에 내일 예보를 data/frozen/<날짜>.json으로 고정한다(이미 있으면 그대로)

키는 환경변수로만 받는다: KSPO_PARKING_API_KEY, DATA_GO_KR_SERVICE_KEY, KCISA_KEY_675.
호출 기록에는 키를 가린 주소만 남긴다.
"""
import csv
import datetime as dt
import html
import io
import json
import os
import pathlib
import re
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import model as M  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW, OUT = ROOT / "data/raw", ROOT / "site/data"
REALTIME, FROZEN = ROOT / "data/realtime/parking.csv", ROOT / "data/frozen"
KST = dt.timezone(dt.timedelta(hours=9))
DAYS_AHEAD = 14
PARKING_URL = "https://www.ksponco.or.kr/online/main/parkingorsApi.do"
SCHEDULE_URL = "https://www.ksponco.or.kr/olympicpark/eventInfo/eventInfoList?mid=a20301010100"
EVENT_VIEW = "https://www.ksponco.or.kr/olympicpark/eventInfo/eventInfoView.es?mid=a20301010100&evtSeq="
WEATHER_URL = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
KCISA_675_URL = "https://api.kcisa.kr/openapi/API_CPM_009/request"
PAST_EVENT_DAYS = {dt.date(2024, 7, 20), dt.date(2024, 7, 21)}  # 영문 공연정보에 7/20 시작 공연 3건, 곡선에 뚜렷한 봉우리
UPLIFT_VENUES = {"KSPO DOME"}  # 공연 가산을 적용하는 공연장(아래 build의 설명 참고)

calls = []


def now():
    return dt.datetime.now(KST)


def mask(url):
    return re.sub(r"((?:serviceKey|apiKey)=)[^&]+", r"\1***", url, flags=re.I)


def fetch(url, timeout=30):
    """GET. (상태, 본문 bytes). 호출 기록을 남긴다. 실패도 기록하고 (상태 또는 0, b'')를 돌려준다."""
    t0, status, body = time.time(), 0, b""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "allpark-parking-forecast/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status, body = r.status, r.read()
    except urllib.error.HTTPError as e:
        status = e.code
    except Exception as e:  # 시간 초과, 연결 실패
        status = "error:" + type(e).__name__
    calls.append({"at": now().isoformat(timespec="seconds"), "url": mask(url), "status": status,
                  "bytes": len(body), "seconds": round(time.time() - t0, 1)})
    return status, body


def key(name):
    v = os.environ.get(name, "").strip()
    return v if "%" in v else urllib.parse.quote(v, safe="")


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


def read_json(path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def save_calls():
    old = read_json(OUT / "calls.json", [])
    write_json(OUT / "calls.json", (calls + old)[:300])


# ---------- collect ----------

def collect():
    k = key("KSPO_PARKING_API_KEY")
    if not k:
        sys.exit("KSPO_PARKING_API_KEY 없음")
    status, body = fetch(PARKING_URL + "?apiKey=" + k, timeout=20)
    m = re.search(rb'"parking_sum"\D*(\d+)', body)
    save_calls()
    if status != 200 or not m:
        sys.exit("실시간 주차 호출 실패: %s" % status)
    new = not REALTIME.exists()
    with REALTIME.open("a", encoding="utf-8") as f:
        if new:
            f.write("collected_at,parking_sum\n")
        f.write("%s,%s\n" % (now().strftime("%Y-%m-%dT%H:%M:%S%z"), m.group(1).decode()))


def load_realtime():
    if not REALTIME.exists():
        return []
    out = []
    for r in csv.DictReader(REALTIME.open(encoding="utf-8")):
        out.append((dt.datetime.strptime(r["collected_at"], "%Y-%m-%dT%H:%M:%S%z").astimezone(KST), int(r["parking_sum"])))
    return sorted(set(out))


# ---------- 일정 ----------

def parse_list_html(text):
    """누리집 일정 목록 HTML -> 공연 목록(원문 문장 포함)."""
    out = []
    pat = (r'evtSeq=(\d+)".*?class="place">(.*?)</em>.*?class="title">(.*?)</strong>.*?'
           r'class="date">\s*(\d{4}-\d{2}-\d{2})\s*~\s*(\d{4}-\d{2}-\d{2})\s*</span>\s*<small class="time">(.*?)</small>')
    for m in re.finditer(pat, text, re.S):
        seq, place, title, b, e, tt = (html.unescape(re.sub(r"\s+", " ", g)).strip() for g in m.groups())
        begin, end = dt.date.fromisoformat(b), dt.date.fromisoformat(e)
        shows = M.parse_schedule(tt, begin, end)
        out.append({"id": seq, "venue": place, "venue_key": M.venue_key(place), "title": title,
                    "begin": b, "end": e, "time_text": tt, "url": EVENT_VIEW + seq,
                    "shows": [{"date": d.isoformat(), "times": ts} for d, ts in shows],
                    "status": "ok" if shows else "일정 미확인"})
    return out


def load_events():
    """누리집을 읽는다. 실패하면 지난번 결과를 쓰고 그 사실을 남긴다. 수동 보정 파일이 있으면 덮어쓴다."""
    prev = read_json(OUT / "events.json", {})
    status, body = fetch(SCHEDULE_URL)
    events = parse_list_html(body.decode("utf-8", "replace")) if status == 200 else []
    if events:
        res = {"read_at": now().isoformat(timespec="seconds"), "source": SCHEDULE_URL, "ok": True, "events": events}
    else:
        res = dict(prev or {"events": []}, ok=False, failed_at=now().isoformat(timespec="seconds"))
    manual = read_json(ROOT / "data/manual_events.json", {})
    for ev in res["events"]:
        if ev["id"] in manual:
            ev.update(manual[ev["id"]], manual_fix=True)
    return res


# ---------- 날씨(기상청 단기예보, 화면 표시만) ----------

def load_weather():
    k = key("DATA_GO_KR_SERVICE_KEY")
    if not k:
        return {"ok": False, "reason": "키 없음"}
    t = now() - dt.timedelta(minutes=15)
    base = max((h for h in (2, 5, 8, 11, 14, 17, 20, 23) if h <= t.hour), default=None)
    bd = t.date() if base is not None else t.date() - dt.timedelta(days=1)
    base = 23 if base is None else base
    q = "?serviceKey=%s&pageNo=1&numOfRows=1500&dataType=JSON&base_date=%s&base_time=%02d00&nx=62&ny=126" % (
        k, bd.strftime("%Y%m%d"), base)
    status, body = fetch(WEATHER_URL + q)
    try:
        items = json.loads(body)["response"]["body"]["items"]["item"]
    except (ValueError, KeyError, TypeError):
        return {"ok": False, "reason": "응답 오류 %s" % status}
    days = {}
    for it in items:
        d = days.setdefault("%s-%s-%s" % (it["fcstDate"][:4], it["fcstDate"][4:6], it["fcstDate"][6:]), {"pop": 0})
        c, v = it["category"], it["fcstValue"]
        if c == "POP":
            d["pop"] = max(d["pop"], int(v))
        elif c in ("TMN", "TMX"):
            d[c.lower()] = round(float(v))
        elif c == "PTY" and v != "0":
            d["rain"] = True
    return {"ok": True, "base": "%s %02d:00" % (bd.isoformat(), base), "days": days}


def retry_kcisa():
    """2025 연계 데이터(675)가 다시 응답하는지 본다. 받으면 첫 쪽을 data/raw에 남긴다(수동으로 전체를 받는다)."""
    dest = RAW / "kcisa_675_page1.json"
    if dest.exists() or not key("KCISA_KEY_675"):
        return {"ok": dest.exists()}
    status, body = fetch(KCISA_675_URL + "?serviceKey=%s&numOfRows=10&pageNo=1" % key("KCISA_KEY_675"), timeout=15)
    if status == 200 and body.strip().startswith((b"{", b"<?xml", b"<response")) and b"504" not in body[:200]:
        dest.write_bytes(body)
        return {"ok": True}
    return {"ok": False, "last_status": status}


# ---------- 과거 자료 ----------

def past():
    trips = M.load_trips((RAW / "15138735_202407_입출차데이터.csv").read_bytes())
    days = [dt.date(2024, 7, d) for d in range(1, 32)]
    return trips, M.day_series(trips, days)


def monthly_factor(month):
    rows = list(csv.reader(io.StringIO((RAW / "15131671_월별주차현황_20260727.csv").read_bytes().decode("cp949"))))[1:]
    tot = {(int(y), int(m.rstrip("월"))): int(n) for y, m, p, n in rows if p == "올림픽공원"}
    return round(tot[(2024, month)] / tot[(2024, 7)], 2), tot


def full_vs_events():
    """주차장 혼잡도 정보의 만차 기록 날짜와 영문 공연정보의 공연 날짜를 견준다(2025-02-12~2026-08-12)."""
    cg = list(csv.reader(io.StringIO((RAW / "15164156_한국체육산업개발주식회사_주차장혼잡도정보.csv").read_bytes().decode("cp949"))))[1:]
    full = {dt.date.fromisoformat(r[4]) for r in cg if r[3] == "만차"}
    pf = list(csv.reader(io.StringIO((RAW / "15149169_영문공연정보_20260901.csv").read_bytes().decode("cp949"))))[1:]
    lo, hi = dt.date(2025, 2, 12), dt.date(2026, 8, 12)
    perf = {dt.date.fromisoformat(r[-1]) for r in pf if lo <= dt.date.fromisoformat(r[-1]) <= hi}
    days = [lo + dt.timedelta(days=i) for i in range((hi - lo).days + 1)]
    cell = lambda p, f: sum(1 for d in days if (d in perf) == p and (d in full) == f)
    weekend = [d for d in days if d.weekday() >= 5]
    wcell = lambda p, f: sum(1 for d in weekend if (d in perf) == p and (d in full) == f)
    return {"period": [lo.isoformat(), hi.isoformat()], "days": len(days), "full_days": len(full), "perf_days": len(perf),
            "table": {"perf_full": cell(1, 1), "perf_notfull": cell(1, 0), "noperf_full": cell(0, 1), "noperf_notfull": cell(0, 0)},
            "weekend_table": {"perf_full": wcell(1, 1), "perf_notfull": wcell(1, 0), "noperf_full": wcell(0, 1), "noperf_notfull": wcell(0, 0)}}


def past_event_profile(series):
    """2024-07 공연일 이틀의 시작 기준 수치(공연 카드의 '과거 비슷한 날')."""
    out = []
    for d in sorted(PAST_EVENT_DAYS):
        occ, ext = series[d]
        s = M.event_start_from_peak(occ)
        r0, r1, mx = M.rush(ext)
        rel = lambda k: None if k is None else (k - s) * M.STEP
        out.append({"date": d.isoformat(), "type": M.day_type(d), "start": M.hhmm(s), "max": max(occ),
                    "reach70_min": rel(M.reach(occ, M.FULL70)), "reach90_min": rel(M.reach(occ, M.FULL90)),
                    "rush_min": [rel(r0), rel(r1)], "exit_peak_min": rel(mx), "exit_peak": ext[mx],
                    "exit_rel": {str((k - s) * M.STEP): ext[k] for k in range(s, M.N)}})
    return out


# ---------- build ----------

def forecast_days(events, weather, model, rule):
    today = now().date()
    shows_by_day = {}
    for ev in events:
        for sh in ev["shows"]:
            shows_by_day.setdefault(sh["date"], []).append({"event": ev["id"], "title": ev["title"], "venue": ev["venue"],
                                                           "venue_key": ev["venue_key"], "times": sh["times"]})
    out = []
    for i in range(DAYS_AHEAD):
        d = today + dt.timedelta(days=i)
        shows = shows_by_day.get(d.isoformat(), [])
        big = sorted((s for s in shows if s["venue_key"] in UPLIFT_VENUES), key=lambda s: s["times"][-1])
        start = M.tick(big[-1]["times"][-1]) if big else None  # 하루 두 번이면 늦은 회차 기준
        lo, mid, hi = model.forecast(d, start)
        if big:
            label = "과거 비슷한 날의 범위"
        elif shows:
            label = "자료 부족(공연 가산 없음)"
        else:
            label = "예보" if rule["is_forecast"] else "과거 비슷한 날의 범위"
        r = lambda c: [round(v) for v in c]
        t = lambda k: None if k is None else M.hhmm(k)
        out.append({"date": d.isoformat(), "type": M.day_type(d), "type_ko": M.DAYTYPE_KO[M.day_type(d)],
                    "label": label, "shows": shows, "uplift_start": t(start),
                    "lo": r(lo), "mid": r(mid), "hi": r(hi),
                    "reach70": t(M.reach(mid, M.FULL70)), "reach90": t(M.reach(mid, M.FULL90)),
                    "reach70_range": [t(M.reach(hi, M.FULL70)), t(M.reach(lo, M.FULL70))],
                    "reach90_range": [t(M.reach(hi, M.FULL90)), t(M.reach(lo, M.FULL90))],
                    "max_mid": max(r(mid)), "transit_advice": M.reach(hi, M.FULL90) is not None,
                    "weather": (weather.get("days") or {}).get(d.isoformat())})
    return out


def baseline_check(rt, series):
    """실시간 값의 기준선 가설 확인(plan.md). (가) 03~05시 최저값이 밤마다 거의 같은가 (나) 아침 증가분이 비슷한가."""
    nights, morn = {}, {}
    for t, v in rt:
        if 3 <= t.hour < 5:
            nights[t.date()] = min(nights.get(t.date(), 10 ** 9), v)
    by_day = {}
    for t, v in rt:
        by_day.setdefault(t.date(), []).append((t, v))
    ref = {}
    for d, (occ, _) in series.items():
        ref.setdefault(M.day_type(d), []).append(occ[66] - occ[42])  # 11:00 - 07:00
    for d, pts in by_day.items():
        a = [v for t, v in pts if t.hour == 7]
        b = [v for t, v in pts if t.hour == 11]
        if a and b:
            r = sum(ref[M.day_type(d)]) / len(ref[M.day_type(d)])
            morn[d.isoformat()] = {"increase": b[0] - a[0], "ref_2024_07": round(r), "ratio": round((b[0] - a[0]) / r, 2)}
    mins = list(nights.values())
    stable = len(mins) >= 2 and max(mins) <= 1.05 * min(mins)
    similar = bool(morn) and all(0.5 <= x["ratio"] <= 2 for x in morn.values())
    night_ref = round(sum(o[24] for o, _ in series.values()) / len(series))  # 2024-07 04:00 평균
    offset = (mins[-1] - night_ref) if mins else None
    return {"nights": {d.isoformat(): v for d, v in sorted(nights.items())}, "morning": morn,
            "night_ref_2024_07": night_ref, "stable": stable, "similar": similar,
            "confirmed": stable and similar, "offset": offset}


def scorecard(rt, bc):
    """고정해 둔 예보(data/frozen)만 채점한다. 실측은 실시간 값(기준선 확인 뒤에는 보정값)."""
    rows = []
    for p in sorted(FROZEN.glob("*.json")):
        f = read_json(p)
        d = dt.date.fromisoformat(f["date"])
        pts = [(t, v) for t, v in rt if t.date() == d]
        if not pts:
            rows.append({"date": f["date"], "frozen_at": f["frozen_at"], "label": f["label"], "status": "실측 없음"})
            continue
        off = bc["offset"] if bc["confirmed"] else 0
        actual = {}
        for t, v in pts:
            actual.setdefault((t.hour * 60 + t.minute) // M.STEP, v - off)
        errs = [abs(f["mid"][k] - v) for k, v in actual.items() if 6 * 6 <= k]
        inside = sum(f["lo"][k] - 50 <= v <= f["hi"][k] + 50 for k, v in actual.items() if 6 * 6 <= k)
        k70 = next((k for k in sorted(actual) if actual[k] >= M.FULL70 * M.CAP), None)
        rows.append({"date": f["date"], "frozen_at": f["frozen_at"], "commit_note": "data/frozen/%s.json" % f["date"],
                     "label": f["label"], "status": "채점" if d < now().date() else "진행 중",
                     "n_points": len(errs), "mae": round(sum(errs) / len(errs)) if errs else None,
                     "in_band": inside, "reach70_forecast": f["reach70"],
                     "reach70_actual": None if k70 is None else M.hhmm(k70),
                     "actual_basis": "보정값(새벽 최저값 기준)" if bc["confirmed"] else "주최 제공 원값(기준선 확인 전)",
                     "actual": {M.hhmm(k): v for k, v in sorted(actual.items())}})
    return rows


def build():
    trips, series = past()
    model = M.Model(series, PAST_EVENT_DAYS)
    rows = M.validate(series, PAST_EVENT_DAYS)
    rule = M.score_rule(rows)
    ev = load_events()
    weather = load_weather()
    kcisa = retry_kcisa()
    rt = load_realtime()
    bc = baseline_check(rt, series)
    days = forecast_days(ev["events"], weather, model, rule)
    perf = json.loads((RAW / "kcisa_96_KSCperf_all.json").read_text(encoding="utf-8"))
    durations = M.venue_durations(perf)
    mf, _ = monthly_factor(now().month)
    t = now().isoformat(timespec="seconds")
    stays = [(b - a).total_seconds() / 60 for a, b in trips]
    write_json(OUT / "events.json", ev)
    write_json(OUT / "forecast.json", {"generated_at": t, "cap": M.CAP, "step_min": M.STEP, "days": days,
                                       "durations": durations, "past_events": past_event_profile(series)})
    last = rt[-1] if rt else None
    today_pts = [(x.strftime("%H:%M"), v) for x, v in rt if x.date() == now().date()]
    write_json(OUT / "now.json", {"generated_at": t, "last": None if not last else {"at": last[0].isoformat(), "value": last[1]},
                                  "today": today_pts, "baseline": bc})
    write_json(OUT / "scorecard.json", {
        "generated_at": t, "frozen": scorecard(rt, bc), "validation": {"rows": rows, "rule": rule},
        "past_summary": {d.isoformat(): M.summary(*series[d]) for d in sorted(PAST_EVENT_DAYS | {dt.date(2024, 7, 13), dt.date(2024, 7, 14)})},
        "trips": {"n": len(trips), "short_pct": round(100 * sum(s <= 10 for s in stays) / len(stays), 1)},
        "full_vs_events": full_vs_events(),
        "monthly": {"month": now().month, "factor_vs_2024_07": mf, "applied": False},
        "sources": {"events": {"ok": ev.get("ok"), "read_at": ev.get("read_at"), "failed_at": ev.get("failed_at")},
                    "weather": {k: weather.get(k) for k in ("ok", "base", "reason")},
                    "kcisa_675": kcisa, "realtime_points": len(rt),
                    "realtime_last": last[0].isoformat() if last else None}})
    save_calls()


def freeze(force_date=None):
    """내일 예보를 고정한다. 한 번 쓴 파일은 고치지 않는다."""
    n = now()
    if force_date is None and not 22 <= n.hour <= 23:
        print("고정 시각(22~24시)이 아님: %s" % n.strftime("%H:%M"))
        return
    target = force_date or (n.date() + dt.timedelta(days=1)).isoformat()
    dest = FROZEN / ("%s.json" % target)
    if dest.exists():
        print("이미 고정됨:", dest.name)
        return
    fc = read_json(OUT / "forecast.json")
    day = next((d for d in fc["days"] if d["date"] == target), None)
    if day is None:
        sys.exit("예보에 %s가 없음" % target)
    write_json(dest, dict(day, frozen_at=n.isoformat(timespec="seconds"), forecast_generated_at=fc["generated_at"]))
    print("고정:", dest.name)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    {"collect": collect, "build": build, "freeze": lambda: freeze(sys.argv[2] if len(sys.argv) > 2 else None)}[cmd]()
