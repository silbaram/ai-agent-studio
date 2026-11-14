"""371: 가설 test가 빼라고 한 판(첫 판 등)을 표본에서 뺀다. 표준 라이브러리 unittest만 사용한다."""
import unittest

from _studio import ROOT
from test_playtests import codes, session, validate, verdict

FIRST = {"learn_timing": {"runs": 3, "reason": "사람마다 첫 판(규칙 익히기)"}}


class ExcludedRuns(unittest.TestCase):
    def test_total_runs_meet_sample_but_counted_runs_do_not(self):
        """15판 했어도 test가 3판을 빼면 센 판은 12판이라 최소 표본 15판에 못 미친다."""
        self.assertEqual(codes(validate([session()], [verdict()])["errors"]), [])
        r = validate([session(excluded_runs=FIRST)], [verdict()])
        self.assertEqual(codes(r["errors"]), ["verdict_sample_short"])
        self.assertIn("3명 · 12판", r["errors"][0]["message"])
        self.assertIn("excluded_runs 3판", r["errors"][0]["message"])

    def test_exclusion_counts_only_for_its_hypothesis(self):
        r = validate([session(runs=18, excluded_runs=FIRST)], [verdict()])
        self.assertEqual(codes(r["errors"]), [])
        other = {"tempo_choice": {"runs": 3, "reason": "첫 판"}}
        r = validate([session(excluded_runs=other)], [verdict()])
        self.assertEqual(codes(r["errors"]), [])

    def test_sample_line_shows_excluded_runs(self):
        r = validate([session(excluded_runs=FIRST)], [verdict(result="unknown")])
        line = r["verdicts"]["parry_tempo.learn_timing"]["sample_text"]
        self.assertIn("12/15판", line)
        self.assertIn("test가 뺀 판 3", line)

    def test_shape_errors(self):
        bad = ({"learn_timing": 3}, {"learn_timing": {"runs": 0, "reason": "x"}}, {"learn_timing": {"runs": 2}},
               {"learn_timing": {"runs": 16, "reason": "x"}}, ["learn_timing"])
        for value in bad:
            with self.subTest(value=value):
                errors = validate([session(excluded_runs=value)], [])["errors"]
                self.assertTrue(any(e["code"] == "schema" and e["message"].startswith("excluded_runs는") for e in errors), errors)

    def test_valid_shapes_pass(self):
        for value in (FIRST, {"learn_timing": {"runs": 1, "reason": "x", "players": ["friend_b"]}}):
            with self.subTest(value=value):
                self.assertEqual(codes(validate([session(excluded_runs=value)], [])["errors"]), [])

    def test_players_with_no_counted_run_leave_the_people_count(self):
        """한 사람이 첫 판만 했으면 그 판이 빠지고 그 사람도 사람 수에서 빠진다."""
        out = {"learn_timing": {"runs": 3, "reason": "사람마다 첫 판", "players": ["friend_b"]}}
        r = validate([session(runs=18, excluded_runs=out)], [verdict()])
        self.assertEqual(codes(r["errors"]), ["verdict_sample_short"])
        self.assertIn("2명 · 15판", r["errors"][0]["message"])

    def test_excluded_players_must_be_session_players(self):
        bad = {"learn_timing": {"runs": 1, "reason": "x", "players": ["nobody"]}}
        self.assertIn("schema", codes(validate([session(excluded_runs=bad)], [])["errors"]))

    def test_hypothesis_context_shows_the_exclusion(self):
        """판정 에이전트가 보는 hypothesis 출력에 그 가설의 뺀 판이 나온다(다른 가설의 것은 안 나온다)."""
        from _studio import SAMPLE, concepts as cc, playtests as pt
        import json
        concept_data = json.loads((SAMPLE / "design/concepts.json").read_text(encoding="utf-8"))
        both = dict(FIRST, tempo_choice={"runs": 2, "reason": "다른 가설"})
        data = {"playtests": [session(excluded_runs=both)], "verdicts": []}
        report = pt.validate(data, cc.hypothesis_index(concept_data))
        got = pt.context("parry_tempo.learn_timing", concept_data, data, report, cc.criteria_stamp)
        head = got["sessions"][0]
        self.assertEqual(head["excluded_runs"], FIRST["learn_timing"])
        other = pt.context("parry_tempo.tempo_choice", concept_data, data, report, cc.criteria_stamp)
        self.assertNotIn("excluded_runs", (other["sessions"] or [{}])[0])

    def test_unknown_hypothesis_is_an_error(self):
        r = validate([session(excluded_runs={"no_such": {"runs": 1, "reason": "x"}})], [])
        self.assertIn("unknown_hypothesis", codes(r["errors"]))


class Docs(unittest.TestCase):
    def test_record_format_defines_the_field(self):
        text = (ROOT / "skills/playtest-verdict/references/playtest-record.md").read_text(encoding="utf-8")
        row = next(l for l in text.splitlines() if l.startswith("| `excluded_runs` |"))
        for word in ("test", "reason", "players", "verdict_sample_short", "events", "hypothesis"):
            self.assertIn(word, row, word)

    def test_record_step_names_the_field(self):
        text = (ROOT / "skills/playtest-verdict/SKILL.md").read_text(encoding="utf-8")
        step = text[text.index("### 2. 플레이한 뒤"):text.index("### 3. 판정한다")]
        self.assertIn("`excluded_runs`", step)


if __name__ == "__main__":
    unittest.main()
