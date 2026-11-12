"""미뤄 둔 판정 쪽 이슈 274(사건이 한 번도 나오지 않음), 279(생존 곡선 제안의 큰 변화) 테스트. 표준 라이브러리 unittest만 사용한다."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from _studio import ROOT, calibrate as cal, run_cli
from test_retest_field import events_concepts
from test_verdict_field import hyp, judge, printed, session, stamp, three, verdict

RECORD = ROOT / "skills/playtest-verdict/references/playtest-record.md"
CALIBRATION = ROOT / "skills/playtest-verdict/references/calibration.md"


def notes(r):
    return [n for n in r.get("event_notes", []) if n["code"] == "event_never_seen"]


class EventNeverSeen(unittest.TestCase):
    """274번: 센 세션에서 사건이 한 번도 나오지 않으면 참고 줄로 알린다. 오류·경고 수와 게이트는 그대로다."""

    def test_zero_in_every_counted_session_is_noted_274(self):
        data = events_concepts()
        r = judge(three(events={"missed_parry": 0}), [verdict("unknown", criteria=stamp(data))], concepts=data)
        self.assertEqual((r["errors"], r["warnings"]), ([], []))
        [n] = notes(r)
        self.assertEqual((n["where"], n["event"], n["sessions"]), ("parry_tempo.learn_timing", "missed_parry", ["pt_a", "pt_b", "pt_c"]))
        out = printed(r)
        self.assertIn("참고 [event_never_seen] parry_tempo.learn_timing:", out)
        self.assertIn("missed_parry", out)
        self.assertIn("pt_a, pt_b, pt_c", out)
        self.assertIn("15판", out)
        self.assertIn("다시 시험할 때", out)

    def test_without_a_verdict_it_is_noted_too_274(self):
        data = events_concepts()
        r = judge(three(events={"missed_parry": 0}), [], concepts=data)
        self.assertEqual(len(notes(r)), 1)

    def test_only_sessions_since_it_was_last_seen_are_named_274(self):
        data = events_concepts()
        old = session("pt_old", date="2026-11-05", events={"missed_parry": 3})
        new = [session(f"pt_n{i}", date="2026-11-09", events={"missed_parry": 0}) for i in (1, 2)]
        r = judge([old] + new, [verdict("unknown", sessions=("pt_old", "pt_n1", "pt_n2"), criteria=stamp(data))], concepts=data)
        [n] = notes(r)
        self.assertEqual(n["sessions"], ["pt_n1", "pt_n2"])
        self.assertEqual(n["last_seen"], "pt_old")
        self.assertIn("pt_old", printed(r))

    def test_seen_in_the_last_session_is_quiet_274(self):
        data = events_concepts()
        sessions = three(events={"missed_parry": 0})
        sessions[-1]["events"] = {"missed_parry": 1}
        self.assertEqual(notes(judge(sessions, [verdict("unknown", criteria=stamp(data))], concepts=data)), [])

    def test_uncounted_is_not_zero_274(self):
        data = events_concepts()
        r = judge(three(), [verdict("unknown", criteria=stamp(data))], concepts=data)
        self.assertEqual(notes(r), [])
        self.assertNotIn("event_never_seen", printed(r))

    def test_a_decided_hypothesis_is_quiet_274(self):
        data = events_concepts()
        r = judge(three(events={"missed_parry": 0}), [verdict("refuted", criteria=stamp(data))], concepts=data)
        self.assertEqual(notes(r), [])

    def test_bot_sessions_are_not_counted_274(self):
        data = events_concepts()
        r = judge(three(events={"missed_parry": 0}, simulated=True), [], concepts=data)
        self.assertEqual(notes(r), [])

    def test_sessions_of_other_builds_are_not_counted_274(self):
        data = events_concepts()
        hyp(data)["builds"] = ["new_rule"]
        sessions = three(events={"missed_parry": 0})
        sessions[-1]["game_build"] = "new_rule"
        r = judge(sessions, [], concepts=data)
        [n] = notes(r)
        self.assertEqual(n["sessions"], ["pt_c"])

    def test_the_check_command_does_not_fail_on_it_274(self):
        data = events_concepts()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "design").mkdir()
            (root / "data").mkdir()
            (root / "design/concepts.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            (root / "data/playtests.json").write_text(json.dumps({"playtests": three(events={"missed_parry": 0}), "verdicts": []},
                                                                 ensure_ascii=False), encoding="utf-8")
            code, out = run_cli("check", str(root))
        self.assertEqual(code, 0, out)
        self.assertIn("참고 [event_never_seen]", out)
        self.assertIn("경고 0", out)

    def test_the_code_is_in_the_record_table_274(self):
        row = next(line for line in RECORD.read_text(encoding="utf-8").splitlines() if line.startswith("| `event_never_seen`"))
        self.assertIn("| 참고 |", row)


class LargeMarginChange(unittest.TestCase):
    """279번: 크게 바뀐 even_margin 제안은 레벨 구성 단계 표의 처치 시간 ÷ 길이를 먼저 보라고 가리킨다."""

    def warnings(self, now, new):
        rows = {"zone_1": [{"rank": "normal"}], "zone_2": [{"rank": "normal"}]}
        result = {"even_margin": {"fitted": {"normal": True}, "current": {"normal": now}, "suggested": {"normal": new}}}
        with mock.patch.object(cal.mm, "stage_rows", return_value=rows):
            return cal._fit_warnings({}, [{"stage": "zone_1"}], result)

    def test_a_large_change_names_the_level_stage_table_279(self):
        big = next(n for n in self.warnings(1.0, 24.0) if "배입니다" in n)
        self.assertIn("--table levels", big)
        self.assertIn("처치 시간 ÷ 길이", big)

    def test_the_threshold_is_one_named_constant_279(self):
        self.assertTrue(any("배입니다" in n for n in self.warnings(1.0, float(cal.LARGE_CHANGE))))
        self.assertFalse(any("배입니다" in n for n in self.warnings(1.0, cal.LARGE_CHANGE * 0.9)))
        self.assertIn(f"{cal.LARGE_CHANGE}배를 넘거나 1/{cal.LARGE_CHANGE} 밑", CALIBRATION.read_text(encoding="utf-8"))

    def test_one_recorded_stage_names_the_others_279(self):
        self.assertTrue(any("기록이 없는 단계(zone_2)" in n for n in self.warnings(1.0, 1.5)))


if __name__ == "__main__":
    unittest.main()
