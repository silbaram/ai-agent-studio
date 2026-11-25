"""407: 기준선 규칙이 한쪽만 요구했다. 주장한 행동을 뺀 봇이 문턱을 넘으면 가를 수 없다는 것만 있고,
주장한 행동을 하는 봇이 문턱을 넘어야 한다(지표가 그 행동을 잡아낼 수 있다)는 요구가 없었다.
문서의 규칙과 연결을 본다. 표준 라이브러리 unittest만 사용한다."""
import unittest

from _studio import ROOT

BRIEF = ROOT / "skills/concept-exploration/references/brief.md"
RECORD = ROOT / "skills/playtest-verdict/references/playtest-record.md"
JUDGE = ROOT / "skills/studio-data/assets/claude/studio-judge.md"
CHANGES = ROOT / "skills/playtest-verdict/references/changes.md"


def read(path):
    return path.read_text(encoding="utf-8")


def bullet(text, head):
    return next(l for l in text.splitlines() if l.startswith(f"- **{head}"))


class BehaviorBot(unittest.TestCase):
    def test_brief_asks_the_behaving_bot_to_cross_the_threshold(self):
        line = bullet(read(BRIEF), "문턱을 기준선과 견준다.")
        self.assertIn("주장한 행동을 하는 정책", line)
        self.assertIn("버팀 쪽에 닿지 못하면", line)   # 방향과 상관없는 말(검토 5)
        self.assertIn("플레이 전에", line)
        self.assertIn("두 쪽 값", line)       # 양쪽 값을 문턱 옆에 적는다

    def test_judge_and_record_treat_a_short_behaving_bot_as_unknown(self):
        for path in (RECORD, JUDGE):
            text = read(path)
            self.assertIn("주장한 행동을 하는 봇의 값이 문턱의 버팀 쪽에 닿지 못한다", text, path.name)

    def test_retest_checks_both_sides(self):
        step3 = next(l for l in read(CHANGES).splitlines() if l.startswith("3. 바꾼 규칙이 지표를"))
        self.assertIn("버팀 쪽에 닿지 못하", step3)
        self.assertIn("../../concept-exploration/references/brief.md#", step3)


class Review(unittest.TestCase):
    """407 수정을 먼저 검토해 찾은 다섯 건."""

    def setUp(self):
        self.line = bullet(read(BRIEF), "문턱을 기준선과 견준다.")

    def test_some_short_policies_are_handled_like_equal_ones_1(self):
        self.assertRegex(self.line, r"닿지 못하면.{0,120}(빼거나 모름)")
        self.assertRegex(self.line, r"모든 정책이.{0,40}닿지 못하면")

    def test_judge_applies_it_to_refuted_only_2(self):
        step5 = next(l for l in read(JUDGE).splitlines() if l.startswith("5. "))
        self.assertIn("틀림의 근거일 때", step5)

    def test_existing_hypotheses_are_checked_before_play_3(self):
        skill = read(ROOT / "skills/playtest-verdict/SKILL.md")
        step1 = skill.split("### 1.", 1)[1].split("### 2.", 1)[0]
        self.assertIn("문턱을 기준선과 견준다", step1)
        self.assertIn("양쪽 값", step1)
        self.assertLess(len(skill.encode("utf-8")), 20000)

    def test_example_is_generic_4(self):
        self.assertNotIn("0.49", self.line)
        self.assertNotIn("뛰어드는", self.line)

    def test_direction_free_wording_5(self):
        for path in (BRIEF, RECORD, JUDGE, CHANGES):
            self.assertNotIn("주장한 행동을 하는 봇의 값이 문턱에 못 미친다", read(path), path.name)
            self.assertNotIn("주장한 행동을 하는 봇이 문턱에 못 미치면", read(path), path.name)


if __name__ == "__main__":
    unittest.main()
