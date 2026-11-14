"""372: 혼자 개발하는 사람도 결과를 본 뒤 줄인 표본을 줄인 뒤의 새 판으로 채우면 확정할 수 있다. 표준 라이브러리 unittest만 사용한다."""
import copy
import unittest

from _studio import ROOT, changes_section
from test_verdict_field import CONCEPTS, codes, hyp, judge, session, stamp, verdict

CODE = "verdict_sample_reduced_after_results"


def solo(date="2026-11-14"):
    """3명·15판에서 1명·5판으로, 결과를 본 뒤에 줄였다."""
    data = copy.deepcopy(CONCEPTS)
    hyp(data)["sample"] = {"players": 1, "runs": 5,
                           "reduced_from": {"players": 3, "runs": 15, "after_run": 0, "before_results": False, "date": date}}
    return data


class AfterResultsReduction(unittest.TestCase):
    def test_sessions_after_the_reduction_day_can_decide(self):
        data = solo()
        new = [session("pt_new", runs=5, date="2026-11-15")]
        r = judge(new, [verdict("refuted", sessions=("pt_new",), criteria=stamp(data))], concepts=data)
        self.assertEqual(r["errors"], [])

    def test_sessions_on_or_before_the_reduction_day_still_block(self):
        data = solo()
        for day in ("2026-11-13", "2026-11-14"):
            with self.subTest(day=day):
                old = [session("pt_old", runs=5, date=day)]
                r = judge(old, [verdict("refuted", sessions=("pt_old",), criteria=stamp(data))], concepts=data)
                self.assertIn(CODE, codes(r["errors"]))

    def test_mixing_old_and_new_sessions_blocks_and_says_how_to_fix(self):
        data = solo()
        both = [session("pt_old", runs=5, date="2026-11-13"), session("pt_new", runs=5, date="2026-11-15")]
        r = judge(both, [verdict("refuted", sessions=("pt_old", "pt_new"), criteria=stamp(data))], concepts=data)
        err = next(e for e in r["errors"] if e["code"] == CODE)
        for word in ("pt_old", "2026-11-14", "뒤의 세션만"):
            self.assertIn(word, err["message"], word)

    def test_filling_the_original_sample_is_fine(self):
        data = solo()
        old = [session(f"pt_{c}", players=(c,), runs=5, date="2026-11-13") for c in "abc"]
        r = judge(old, [verdict("refuted", criteria=stamp(data))], concepts=data)
        self.assertEqual(r["errors"], [])

    def test_new_sessions_still_need_the_reduced_sample(self):
        data = solo()
        short = [session("pt_new", runs=3, date="2026-11-15")]
        r = judge(short, [verdict("refuted", sessions=("pt_new",), criteria=stamp(data))], concepts=data)
        self.assertEqual(codes(r["errors"]), ["verdict_sample_short"])


class Docs(unittest.TestCase):
    def test_brief_asks_how_many_people_can_play(self):
        text = (ROOT / "skills/concept-exploration/references/brief.md").read_text(encoding="utf-8")
        line = next(l for l in text.splitlines() if l.startswith("- **id와 표본을 플레이 전에 정한다.**"))
        for word in ("실제로 플레이할 수 있는 사람", "혼자", "1명", "`test`"):
            self.assertIn(word, line, word)

    def test_changes_step_four_allows_new_sessions(self):
        part = changes_section("표본을 줄이자는 말이 나올 때")
        step4 = next(l for l in part.splitlines() if l.startswith("4. "))
        for word in ("줄인 날 뒤", "verdict_sample_reduced_after_results", "다음 날", "brief.md", "`test`"):
            self.assertIn(word, step4, word)

    def test_reduction_between_sessions_is_not_a_deviation_of_new_sessions(self):
        part = changes_section("표본을 줄이자는 말이 나올 때")
        step7 = next(l for l in part.splitlines() if l.startswith("7. "))
        self.assertIn("마지막 세션", step7)
        self.assertIn("이탈이 아니다", step7)

    def test_play_prep_points_to_the_people_question(self):
        text = (ROOT / "skills/playtest-verdict/SKILL.md").read_text(encoding="utf-8")
        step = text[text.index("### 1. 플레이 전"):text.index("### 2. 플레이한 뒤")]
        self.assertIn("실제로 플레이할 수 있는 사람", step)
        self.assertIn("brief.md#", step)

    def test_brief_points_to_the_reduction_steps(self):
        text = (ROOT / "skills/concept-exploration/references/brief.md").read_text(encoding="utf-8")
        line = next(l for l in text.splitlines() if l.startswith("- **id와 표본을 플레이 전에 정한다.**"))
        self.assertIn("changes.md#표본을-줄이자는-말이-나올-때", line)
        self.assertNotIn("판정 전에 사용자와", line)

    def test_check_table_row_matches(self):
        text = (ROOT / "skills/playtest-verdict/references/playtest-record.md").read_text(encoding="utf-8")
        row = next(l for l in text.splitlines() if l.startswith(f"| `{CODE}` |"))
        self.assertIn("줄인 날 뒤", row)


if __name__ == "__main__":
    unittest.main()
