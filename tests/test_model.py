"""회귀 시험. 기획 문서(plan.md, research.md)에 적은 2024년 7월 수치와 누리집 일정 실제 문장을 기준으로 한다.

실행: python3 -m unittest   (저장소 최상위에서)
"""
import datetime as dt
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
import model as M  # noqa: E402
import run  # noqa: E402

D = dt.date


class PastData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trips, cls.series = run.past()

    def s(self, day):
        return M.summary(*self.series[D(2024, 7, day)])

    def test_trip_count_and_short_stays(self):
        self.assertEqual(len(self.trips), 215528)
        stays = [(b - a).total_seconds() / 60 for a, b in self.trips]
        self.assertEqual(round(100 * sum(x <= 10 for x in stays) / len(stays), 1), 31.4)

    def test_event_weekend(self):
        d20, d21 = self.s(20), self.s(21)
        self.assertEqual((d20["max"], d20["max_at"], d20["reach70"], d20["reach90"]), (2022, "17:40", "16:20", "17:20"))
        self.assertEqual((d21["max"], d21["max_at"], d21["reach70"], d21["reach90"]), (2213, "16:50", "15:20", "16:20"))
        self.assertEqual((d20["over90_min"], d21["over90_min"]), (40, 110))
        self.assertEqual((d20["exit_peak"], d20["rush"]), (268, ["21:10", "21:50"]))
        self.assertEqual((d21["exit_peak"], d21["exit_peak_at"], d21["rush"]), (262, "20:30", ["18:40", "20:50"]))

    def test_weekend_without_event(self):
        self.assertEqual((self.s(13)["max"], self.s(14)["max"]), (1130, 916))
        self.assertEqual(sum(self.series[D(2024, 7, 20)][1][21 * 6:22 * 6]), 1188)
        self.assertEqual(sum(self.series[D(2024, 7, 13)][1][21 * 6:22 * 6]), 471)

    def test_event_start_from_peak(self):
        self.assertEqual(M.hhmm(M.event_start_from_peak(self.series[D(2024, 7, 20)][0])), "18:00")
        self.assertEqual(M.hhmm(M.event_start_from_peak(self.series[D(2024, 7, 21)][0])), "17:00")

    def test_validation_beats_baselines(self):
        rule = M.score_rule(M.validate(self.series, run.PAST_EVENT_DAYS))
        self.assertEqual((rule["n_days"], rule["n_compared"], rule["n_event_days"]), (31, 24, 2))
        self.assertLess(rule["model"], rule["typemean"])
        self.assertLess(rule["model"], rule["prevweek"])

    def test_forecast_shifts_with_start_time(self):
        m = M.Model(self.series, run.PAST_EVENT_DAYS)
        _, mid18, _ = m.forecast(D(2026, 11, 21), M.tick("18:00"))
        _, mid19, _ = m.forecast(D(2026, 11, 21), M.tick("19:00"))
        self.assertIn(M.reach(mid19, M.FULL70) - M.reach(mid18, M.FULL70), (5, 6, 7))  # 한 시간(6눈금) 안팎 늦어진다
        self.assertLessEqual(max(mid18), M.CAP)
        lo, mid, hi = m.forecast(D(2026, 11, 16))  # 공연 없는 평일
        self.assertEqual(lo, hi)


class Schedule(unittest.TestCase):
    def p(self, text, b, e):
        return [(d.isoformat()[5:], ts) for d, ts in M.parse_schedule(text, D(*b), D(*e))]

    def test_typo_month(self):  # 누리집 TXT 공연 원문. 셋째 날이 '1월 15일'로 잘못 적혀 있다
        self.assertEqual(self.p("11월 13일 금 7PM(KST) 11월 14일 토 6PM(KST) 1월 15일 일 5PM(KST)", (2026, 11, 13), (2026, 11, 15)),
                         [("11-13", ["19:00"]), ("11-14", ["18:00"]), ("11-15", ["17:00"])])

    def test_typo_weekday(self):  # 11/8은 일요일인데 (금)으로 적혀 있다
        self.assertEqual(self.p("2026년 11월 7일(토) 18:00 / 2026년 11월 8일(금) 17:00", (2026, 11, 7), (2026, 11, 8)),
                         [("11-07", ["18:00"]), ("11-08", ["17:00"])])

    def test_range_then_weekdays(self):
        self.assertEqual(self.p("2026년 11월 14일(토) ~ 11월 15(일)   토 오후 6시 / 일 오후 4시 ", (2026, 11, 14), (2026, 11, 15)),
                         [("11-14", ["18:00"]), ("11-15", ["16:00"])])

    def test_english_dots(self):
        self.assertEqual(self.p("2026.11.21.(SAT) 6PM  2026.11.22.(SUN) 5PM", (2026, 11, 21), (2026, 11, 22)),
                         [("11-21", ["18:00"]), ("11-22", ["17:00"])])

    def test_korean_full(self):
        self.assertEqual(self.p("2026년 10월 24일 토요일 오후 6시 2026년 10월 25일 일요일 오후 5시 2026년 10월 31일 토요일 오후 6시 "
                                "2026년 11월 1일 일요일 오후 5시", (2026, 10, 24), (2026, 11, 1)),
                         [("10-24", ["18:00"]), ("10-25", ["17:00"]), ("10-31", ["18:00"]), ("11-01", ["17:00"])])

    def test_weekday_pattern_with_minutes(self):
        self.assertEqual(self.p("금 오후 7시 28분 / 토 오후 5시 / 일 오후 4시", (2026, 10, 30), (2026, 11, 1)),
                         [("10-30", ["19:28"]), ("10-31", ["17:00"]), ("11-01", ["16:00"])])

    def test_multi_weekday_multi_time(self):
        got = self.p("수목금 19시 30분 / 토 15시, 19시 / 일 14시 (일자별 공연 시간 변동 있으며, 상세페이지 참고 부탁드립니다. )",
                     (2026, 11, 28), (2026, 12, 2))
        self.assertEqual(got, [("11-28", ["15:00", "19:00"]), ("11-29", ["14:00"]), ("12-02", ["19:30"])])

    def test_unknown_is_empty(self):
        self.assertEqual(self.p("상세페이지 참고", (2026, 11, 7), (2026, 11, 8)), [])

    def test_list_html(self):
        html = (ROOT / "tests/fixtures/eventInfoList_20261114.html").read_text(encoding="utf-8")
        evs = run.parse_list_html(html)
        self.assertEqual(len(evs), 12)
        txt = next(e for e in evs if e["id"] == "5165")
        self.assertEqual((txt["venue_key"], txt["shows"][-1]), ("KSPO DOME", {"date": "2026-11-15", "times": ["17:00"]}))
        self.assertTrue(all(e["status"] == "ok" for e in evs))


class Helpers(unittest.TestCase):
    def test_mask(self):
        self.assertEqual(run.mask("https://x/y?serviceKey=abc%2B1&n=1"), "https://x/y?serviceKey=***&n=1")
        self.assertEqual(run.mask("https://x/y?apiKey=abc"), "https://x/y?apiKey=***")

    def test_venue_key(self):
        self.assertEqual(M.venue_key("KSPO DOME(체조경기장)"), "KSPO DOME")
        self.assertEqual(M.venue_key("올림픽공원 올림픽홀 "), "올림픽홀")
        self.assertEqual(M.venue_key("올림픽공원 우리금융아트홀"), "우리금융아트홀")

    def test_baseline_check(self):
        kst = run.KST
        pts = [(dt.datetime(2026, 11, d, h, 0, tzinfo=kst), v) for d, h, v in
               [(14, 3, 1105), (14, 7, 1080), (14, 11, 1930), (15, 3, 1110), (15, 7, 1090), (15, 11, 1700)]]
        _, series = run.past()
        bc = run.baseline_check(pts, series)
        self.assertTrue(bc["stable"])
        self.assertTrue(bc["confirmed"])
        self.assertEqual(bc["offset"], 1110 - bc["night_ref_2024_07"])
        self.assertFalse(run.baseline_check(pts[:3], series)["confirmed"])  # 밤 하나로는 확인하지 않는다


if __name__ == "__main__":
    unittest.main()
