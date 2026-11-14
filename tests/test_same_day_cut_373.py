"""373: 결과를 본 뒤 줄인 날에도, 줄인 시각 뒤에 시작한 세션은 줄인 표본을 채운다. 표준 라이브러리 unittest만 사용한다."""
import copy
import unittest

from _studio import ROOT, changes_section, concepts as cc
from test_verdict_field import CONCEPTS, codes, hyp, judge, session, stamp, verdict

CODE = "verdict_sample_reduced_after_results"
CUT = {"players": 3, "runs": 15, "after_run": 0, "before_results": False, "date": "2026-11-14", "at": "2026-11-14T17:00+09:00"}


def reduced(**over):
    data = copy.deepcopy(CONCEPTS)
    hyp(data)["sample"] = {"players": 1, "runs": 5, "reduced_from": dict(CUT, **over)}
    return data


def decide(data, **over):
    s = [session("pt_today", runs=5, date="2026-11-14", **over)]
    return judge(s, [verdict("refuted", sessions=("pt_today",), criteria=stamp(data))], concepts=data)


class SameDayAfterTheCut(unittest.TestCase):
    def test_session_started_after_the_cut_counts(self):
        for start in ("2026-11-14T17:30+09:00", "2026-11-14T08:30:00.000Z"):   # 판 로그는 UTC로 남긴다(08:30Z = 17:30 KST)
            with self.subTest(start=start):
                self.assertEqual(decide(reduced(), started_at=start)["errors"], [])

    def test_session_started_before_the_cut_still_blocks(self):
        for start in ("2026-11-14T16:59+09:00", "2026-11-14T03:07:14.566Z"):
            with self.subTest(start=start):
                self.assertIn(CODE, codes(decide(reduced(), started_at=start)["errors"]))

    def test_without_both_times_the_same_day_still_blocks(self):
        self.assertIn(CODE, codes(decide(reduced())["errors"]))   # 세션 시각 없음
        data = reduced()
        del hyp(data)["sample"]["reduced_from"]["at"]
        self.assertIn(CODE, codes(decide(data, started_at="2026-11-14T18:00+09:00")["errors"]))   # 줄인 시각 없음

    def test_a_later_date_does_not_hide_an_earlier_start(self):
        """다음 날 기록하며 date를 기록한 날로 적어도, 판 로그의 시작 시각이 줄인 시각 전이면 줄이기 전의 판이다."""
        data = reduced()
        s = [session("pt_late", runs=5, date="2026-11-15", started_at="2026-11-14T07:00:00.000Z")]
        r = judge(s, [verdict("refuted", sessions=("pt_late",), criteria=stamp(data))], concepts=data)
        self.assertIn(CODE, codes(r["errors"]))

    def test_bad_start_is_reported_once(self):
        """형식이 틀린 started_at은 형식 오류 하나로 알리고, 시각 없는 세션처럼 표본 오류를 또 내지 않는다."""
        self.assertNotIn(CODE, codes(decide(reduced(), started_at="17:30")["errors"]))

    def test_judge_context_shows_the_start(self):
        import json
        from _studio import playtests as pt
        data = reduced()
        play = {"playtests": [session("pt_today", runs=5, date="2026-11-14", started_at="2026-11-14T08:30:00.000Z")], "verdicts": []}
        report = pt.validate(play, cc.hypothesis_index(data))
        got = pt.context("parry_tempo.learn_timing", data, play, report, cc.criteria_stamp)
        self.assertEqual(got["sessions"][0]["started_at"], "2026-11-14T08:30:00.000Z")
        self.assertIn("2026-11-14T17:00+09:00", json.dumps(got, ensure_ascii=False))   # 줄인 시각도 가설 표본으로 보인다

    def test_block_message_names_the_time_fields(self):
        err = next(e for e in decide(reduced())["errors"] if e["code"] == CODE)
        for word in ("started_at", "reduced_from.at"):
            self.assertIn(word, err["message"], word)


class Shapes(unittest.TestCase):
    def test_bad_session_start_is_a_schema_error(self):
        for bad in ("17:30", "2026-11-14T17:30", "어제", 1730):   # 시간대가 없으면 판 로그의 UTC와 견줄 수 없다
            with self.subTest(bad=bad):
                errors = decide(reduced(), started_at=bad)["errors"]
                self.assertTrue(any(e["code"] == "schema" and e["message"].startswith("started_at은") for e in errors), errors)

    def test_bad_cut_time_is_a_sample_problem(self):
        for bad in ("17:00", "2026-11-14T17:00", "2026-11-15T01:00+09:00"):   # 시간대가 없거나 date와 다른 날
            with self.subTest(bad=bad):
                problem = cc.sample_problem({"players": 1, "runs": 5, "reduced_from": dict(CUT, at=bad)})
                self.assertIsNotNone(problem)
                self.assertIn("at", problem)
        self.assertIsNone(cc.sample_problem({"players": 1, "runs": 5, "reduced_from": CUT}))


class Docs(unittest.TestCase):
    def test_changes_step_four_says_how_to_play_the_same_day(self):
        step4 = next(l for l in changes_section("표본을 줄이자는 말이 나올 때").splitlines() if l.startswith("4. "))
        for word in ("`reduced_from.at`", "`started_at`", "시간대", "줄일 때 같이 적는다"):
            self.assertIn(word, step4, word)

    def test_changes_step_five_says_why_the_check_stays_by_date(self):
        step5 = next(l for l in changes_section("표본을 줄이자는 말이 나올 때").splitlines() if l.startswith("5. "))
        self.assertIn("진행 중이던 세션", step5)
        self.assertIn("`started_at`", step5)

    def test_record_format_defines_started_at(self):
        text = (ROOT / "skills/playtest-verdict/references/playtest-record.md").read_text(encoding="utf-8")
        row = next(l for l in text.splitlines() if l.startswith("| `started_at` |"))
        for word in ("판 로그", "시간대", "reduced_from.at"):
            self.assertIn(word, row, word)
        check = next(l for l in text.splitlines() if l.startswith(f"| `{CODE}` |"))
        self.assertIn("started_at", check)

    def test_record_step_names_the_field(self):
        text = (ROOT / "skills/playtest-verdict/SKILL.md").read_text(encoding="utf-8")
        step = text[text.index("### 2. 플레이한 뒤"):text.index("### 3. 판정한다")]
        self.assertIn("`started_at`", step)


if __name__ == "__main__":
    unittest.main()
