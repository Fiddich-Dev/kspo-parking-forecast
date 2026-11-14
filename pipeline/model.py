"""올팍 주차예보의 계산. 파일·네트워크를 건드리지 않는 순수 함수만 둔다(시험 대상).

- 동시 주차: 입출차 기록에서 10분 눈금마다 "들어와 있고 아직 안 나간 차"를 센다.
- 예보: 요일 유형별 기준 곡선 x 월별 보정 + 공연 가산(공연 시작 시각에 맞춰 옮김), 2,200대에서 자름.
- 검증: 날짜 하나를 빼고 나머지로 그날을 맞힌다(leave-one-day-out). 기준 예측 둘과 견준다.
"""
import csv
import datetime as dt
import io
import re
import statistics

CAP = 2200  # 주최 「주차장 예상 이용률 서비스」 화면의 "2,200대 가능"
STEP = 10  # 분
N = 24 * 60 // STEP  # 하루 눈금 수(144)
FULL70, FULL90 = 0.7, 0.9  # 2024-07-20, 21에 잰 "차기 시작" "가득 참" 문턱
RUSH_RATIO = 0.6  # 출차 몰림: 18시 뒤 10분 출차가 그날 저녁 최대의 60% 이상
WEEKDAY, SAT, SUN = "weekday", "sat", "sun_holiday"
DAYTYPE_KO = {WEEKDAY: "평일", SAT: "토요일", SUN: "일요일·공휴일"}

# shortcut: 공휴일을 손으로 적었다. 2028년 말까지만 있다. 그 뒤로 운영하면 특일 정보 API(data.go.kr 15012690)로 바꾼다.
HOLIDAYS = {dt.date.fromisoformat(s) for s in (
    "2026-12-25 2027-01-01 2027-02-06 2027-02-07 2027-02-08 2027-02-09 2027-03-01 2027-03-03 "
    "2027-05-05 2027-05-13 2027-06-06 2027-08-15 2027-08-16 2027-09-14 2027-09-15 2027-09-16 "
    "2027-10-03 2027-10-04 2027-10-09 2027-10-11 2027-12-25 2028-01-01 2028-01-26 2028-01-27 "
    "2028-01-28 2028-03-01 2028-05-02 2028-05-05 2028-06-06 2028-08-15 2028-10-02 2028-10-03 "
    "2028-10-04 2028-10-05 2028-10-09 2028-12-25").split()}


def day_type(d):
    if d in HOLIDAYS or d.weekday() == 6:
        return SUN
    return SAT if d.weekday() == 5 else WEEKDAY


def hhmm(k):
    return "%02d:%02d" % (k * STEP // 60, k * STEP % 60)


def tick(t):
    """'HH:MM' -> 그 시각을 포함하는 10분 눈금 번호."""
    h, m = map(int, t.split(":"))
    return (h * 60 + m) // STEP


# ---------- 입출차 기록 -> 날짜별 10분 곡선 ----------

def load_trips(raw_bytes):
    """입출차 CSV(cp949, 열: 입차일, 입차일시, 출차일시) -> [(입차, 출차)]."""
    f = "%Y-%m-%d %H:%M"
    rows = list(csv.reader(io.StringIO(raw_bytes.decode("cp949"))))[1:]
    return [(dt.datetime.strptime(a, f), dt.datetime.strptime(b, f)) for _, a, b in rows]


def day_series(trips, days):
    """{날짜: (동시 주차[144], 출차 수[144])}. 동시 주차는 눈금 시각에 들어와 있고 아직 안 나간 차."""
    out = {d: ([0] * N, [0] * N) for d in days}
    step = dt.timedelta(minutes=STEP)
    for a, b in trips:
        for i in range((b.date() - a.date()).days + 1):
            d = a.date() + dt.timedelta(days=i)
            if d not in out:
                continue
            occ, ext = out[d]
            s = dt.datetime.combine(d, dt.time())
            lo = max(0, -(-(a - s) // step))  # a 이후 첫 눈금
            hi = min(N, -(-(b - s) // step))  # b 이전 마지막 눈금 + 1
            for k in range(lo, hi):
                occ[k] += 1
            if s <= b < s + dt.timedelta(days=1):
                ext[(b - s) // step] += 1
    return out


def reach(curve, ratio):
    """곡선이 처음으로 CAP*ratio 이상이 되는 눈금. 없으면 None."""
    return next((k for k, v in enumerate(curve) if v >= ratio * CAP), None)


def rush(ext, ratio=RUSH_RATIO):
    """18시 뒤 출차가 저녁 최대의 ratio 이상인 첫 눈금과 마지막 눈금+1."""
    eve = range(18 * 60 // STEP, N)
    mx = max(eve, key=ext.__getitem__)
    ks = [k for k in eve if ext[k] >= ratio * ext[mx]]
    return ks[0], ks[-1] + 1, mx


def summary(occ, ext):
    pk = max(range(N), key=occ.__getitem__)
    r0, r1, mx = rush(ext)
    t = lambda k: None if k is None else hhmm(k)
    return {
        "max": occ[pk], "max_at": hhmm(pk), "reach70": t(reach(occ, FULL70)), "reach90": t(reach(occ, FULL90)),
        "over90_min": sum(v >= FULL90 * CAP for v in occ) * STEP,
        "exit_peak": ext[mx], "exit_peak_at": hhmm(mx), "rush": [hhmm(r0), hhmm(r1)],
    }


# ---------- 공연 일정 문장 파서 ----------

_WD = "월화수목금토일"


def _times(s):
    """문장 조각에서 시각들을 뽑는다. '오후 7시' '7PM' '19:30' '19시 30분' '오후 7시 28분'."""
    out = []
    for m in re.finditer(r"(오전|오후)?\s*(\d{1,2})\s*(?:시\s*(?:(\d{1,2})\s*분)?|:(\d{2})|\s*(PM|AM|pm|am))", s):
        ampm, h, mi = m.group(1) or m.group(5), int(m.group(2)), int(m.group(3) or m.group(4) or 0)
        if ampm in ("오후", "PM", "pm") and h < 12:
            h += 12
        if h > 23 or mi > 59:
            continue
        out.append("%02d:%02d" % (h, mi))
    return out


def parse_schedule(text, begin, end):
    """누리집 일정 문장 + 기간(begin~end, date) -> [(date, ['HH:MM', ...])] 날짜순.

    규칙(추측해서 채우지 않는다):
    1. 날짜가 적힌 문장: 'N일'이나 'YYYY.MM.DD.' 뒤에 오는 시각을 그 날짜에 붙인다. 월은 기간 안에서 일(日)이
       맞는 날로 정한다(문장의 월·요일 오타는 무시: '1월 15일'은 기간 11/13~15 안의 15일).
    2. 요일만 적힌 문장('금 오후 7시 / 토 오후 6시', '수목금 19시 30분'): 기간 안 그 요일마다 붙인다.
    3. 둘 다 아니면 빈 목록(= 일정 미확인).
    """
    days = [begin + dt.timedelta(days=i) for i in range((end - begin).days + 1)]
    by_dom = {}
    for d in days:
        by_dom.setdefault(d.day, []).append(d)
    res = {}
    # 1. 날짜 + 시각. 날짜 표시마다 바로 뒤 시각이 있어야 이 규칙을 쓴다.
    marks = list(re.finditer(r"(?:(\d{4})\s*[.년]\s*)?(\d{1,2})\s*[.월]\s*(\d{1,2})\s*(?:일|\.|(?=\())", text))
    for i, m in enumerate(marks):
        seg = text[m.end(): marks[i + 1].start() if i + 1 < len(marks) else len(text)]
        seg = re.sub(r"^\s*\.?\s*(\(\s*\w+\s*\)|[월화수목금토일](요일)?)", "", seg)
        ts, cand = _times(seg), by_dom.get(int(m.group(3)), [])
        if len(cand) != 1 or not ts:
            res = {}
            break
        res.setdefault(cand[0], []).extend(ts)
    if res:
        return sorted((d, sorted(set(t))) for d, t in res.items())
    # 2. 요일 + 시각: 괄호 밖의 요일 글자 뒤에 오는 시각들
    tm = r"(?:오전|오후)?\s*\d{1,2}\s*(?:시(?:\s*\d{1,2}\s*분)?|:\d{2}|PM|AM|pm|am)"
    for m in re.finditer(r"(?:^|[\s/])([월화수목금토일]{1,7})\s+((?:%s[\s,]*)+)" % tm, text):
        wds = {_WD.index(c) for c in m.group(1)}
        for d in days:
            if d.weekday() in wds:
                res.setdefault(d, []).extend(_times(m.group(2)))
    return sorted((d, sorted(set(t))) for d, t in res.items())


def venue_key(name):
    """공연장 이름을 묶는다. 공연장마다 표기가 여럿이다."""
    n = (name or "").replace(" ", "")
    if "KSPODOME" in n.upper() or "체조경기장" in n:
        return "KSPO DOME"
    for k in ("올림픽홀", "우리금융아트홀", "핸드볼경기장", "뮤즈라이브", "K-아트홀", "88잔디마당"):
        if k in n:
            return k
    return name.strip() if name else "기타"


VENUE_RANK = {"KSPO DOME": 0, "핸드볼경기장": 1, "올림픽홀": 2, "88잔디마당": 3, "우리금융아트홀": 4}


def venue_durations(perf_items):
    """공연정보(KCISA 96) -> {공연장: 소요시간 중앙값(분), 표본 수}."""
    by = {}
    for x in perf_items:
        m = re.match(r"(\d+)\s*분", x.get("extent") or "")
        if m and 30 <= int(m.group(1)) <= 300:
            by.setdefault(venue_key(x.get("spatial")), []).append(int(m.group(1)))
    return {k: {"minutes": int(statistics.median(v)), "n": len(v)} for k, v in by.items()}


# ---------- 예보 모델 ----------

def mean_curve(curves):
    return [sum(c[k] for c in curves) / len(curves) for k in range(N)] if curves else [0.0] * N


def shift(curve, k):
    """곡선을 k 눈금 뒤로(양수) 옮긴다. 빈자리는 0."""
    return [curve[i - k] if 0 <= i - k < N else 0.0 for i in range(N)]


def event_start_from_peak(occ):
    """과거 공연일의 공연 시작 시각 추정: 최대 동시 주차 직후의 정시.
    근거: 2024-07-20 최대 17:40 -> 18:00, 07-21 최대 16:50 -> 17:00(누리집의 일반 주말 공연 시각 토 6PM, 일 5PM과 같다)."""
    pk = max(range(N), key=occ.__getitem__)
    return (pk // 6 + 1) * 6


class Model:
    """학습 날짜의 곡선으로 만든다. 공연일 가산은 공연 시작 시각 기준으로 정렬해 평균한다."""

    def __init__(self, series, event_days, exclude=()):
        days = [d for d in series if d not in exclude]
        self.base = {}
        self.base_n = {}
        for t in (WEEKDAY, SAT, SUN):
            cs = [series[d][0] for d in days if day_type(d) == t and d not in event_days]
            self.base[t], self.base_n[t] = mean_curve(cs), len(cs)
        self.uplifts = []  # (날짜, 그날 시작 눈금, 가산 곡선)
        for d in days:
            if d in event_days:
                s = event_start_from_peak(series[d][0])
                up = [o - b for o, b in zip(series[d][0], self.base[day_type(d)])]
                self.uplifts.append((d, s, up))
        self.event_n = len(self.uplifts)

    def forecast(self, d, start_tick=None, month_factor=1.0):
        """(낮게, 가운데, 높게) 곡선. 공연이 없으면 셋이 같다."""
        b = [v * month_factor for v in self.base[day_type(d)]]
        if start_tick is None or not self.uplifts:
            return b, b, b
        ups = [shift(u, start_tick - s) for _, s, u in self.uplifts]  # 공연 시작 시각을 맞춘다
        clip = lambda c: [max(0.0, min(CAP, v)) for v in c]
        mid = clip([bv + sum(u[k] for u in ups) / len(ups) for k, bv in enumerate(b)])
        lo = clip([bv + min(u[k] for u in ups) for k, bv in enumerate(b)])
        hi = clip([bv + max(u[k] for u in ups) for k, bv in enumerate(b)])
        return lo, mid, hi


def mae(a, b, lo=6 * 6, hi=24 * 6):
    """06~24시 평균 절대 오차(대)."""
    return sum(abs(x - y) for x, y in zip(a[lo:hi], b[lo:hi])) / (hi - lo)


def validate(series, event_days):
    """날짜 하나씩 빼고 맞힌다. 모델, 요일 유형 평균, 직전 같은 요일 셋을 견준다."""
    rows = []
    for d in sorted(series):
        m = Model(series, event_days, exclude={d})
        occ = series[d][0]
        start = event_start_from_peak(occ) if d in event_days else None
        _, mid, _ = m.forecast(d, start)
        typ = [sum(series[x][0][k] for x in series if x != d and day_type(x) == day_type(d)) /
               max(1, sum(1 for x in series if x != d and day_type(x) == day_type(d))) for k in range(N)]
        prev = series.get(d - dt.timedelta(days=7))
        r = {"date": d.isoformat(), "event": d in event_days, "type": day_type(d),
             "model": round(mae(mid, occ), 1), "typemean": round(mae(typ, occ), 1),
             "prevweek": None if prev is None else round(mae(prev[0], occ), 1)}
        for name, c in (("model", mid), ("actual", occ)):
            k = reach(c, FULL70)
            r["reach70_" + name] = None if k is None else hhmm(k)
        rows.append(r)
    return rows


def score_rule(rows):
    """검증 설계 5번: 모델이 두 기준 예측보다 모두 나을 때만 '예보'라고 부른다."""
    both = [r for r in rows if r["prevweek"] is not None]
    avg = lambda key, rs: round(sum(r[key] for r in rs) / len(rs), 1) if rs else None
    out = {"n_days": len(rows), "n_compared": len(both),
           "model": avg("model", both), "typemean": avg("typemean", both), "prevweek": avg("prevweek", both),
           "n_event_days": sum(r["event"] for r in rows)}
    out["is_forecast"] = bool(both) and out["model"] < out["typemean"] and out["model"] < out["prevweek"]
    return out
