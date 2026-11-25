"""409: playtest-verdict 1단계가 "`test`에 문턱 양쪽 값이 있는지 본다"고만 했다.
현장 시험의 세션은 '양쪽'을 두 봇의 값으로 읽고 기준선 보고서에서 확인한 것으로 끝냈다.
test 문장에 행동하는 봇의 값이 빠진 것은 짚지 않았다. 표준 라이브러리 unittest만 사용한다."""
import unittest

from _studio import ROOT

SKILL = ROOT / "skills/playtest-verdict/SKILL.md"


def step1():
    text = SKILL.read_text(encoding="utf-8")
    return text.split("### 1.", 1)[1].split("### 2.", 1)[0]


def bot_sentence():
    return next(l for l in step1().splitlines() if "봇이 있으면" in l)


class BehavingValue(unittest.TestCase):
    def test_names_both_bots_instead_of_both_sides(self):
        line = bot_sentence()
        self.assertNotIn("문턱 양쪽 값", line)
        self.assertIn("주장한 행동을 뺀 봇과 그 행동을 하는 봇의 값", line)

    def test_report_only_value_is_missing(self):
        line = bot_sentence()
        self.assertIn("보고서에만 있으면", line)
        self.assertIn("`test`에 없는 것이다", line)

    def test_says_what_to_do_when_missing(self):
        line = bot_sentence()
        self.assertRegex(line, r"빠졌으면.{0,40}봇을 돌려.{0,40}'어긋나면 플레이 전에 고친다'대로 적는다")
        self.assertIn("어긋나면 플레이 전에 고친다:", step1())   # 가리키는 항목이 같은 단계에 있다

    def test_judged_hypothesis_is_same_meaning_fix(self):
        changes = (ROOT / "skills/playtest-verdict/references/changes.md").read_text(encoding="utf-8")
        section = changes.split("## 판정한 가설의 문장을 고칠 때", 1)[1].split("\n## ", 1)[0]
        self.assertIn("기준선 보고서에 있던 봇 값을 문턱 옆에 옮겨 적음", section)   # 뜻이 같은 고침의 예

    def test_size_limit(self):
        self.assertLess(len(SKILL.read_bytes()), 20000)


class Review(unittest.TestCase):
    """409 수정을 먼저 검토해 찾은 여섯 건."""

    def test_preplay_log_column_kept_1(self):
        self.assertRegex(step1(), r"시험 조건\(설정\)이 여러 가지면 플레이 전에 로그에 그 열을 두")
        self.assertIn("runlog --group-by", step1())

    def test_copying_is_same_meaning_only_without_exclusion_2(self):
        changes = (ROOT / "skills/playtest-verdict/references/changes.md").read_text(encoding="utf-8")
        item = next(l for l in changes.splitlines() if l.startswith("1. 고치기 전에 바꿀 문장을 보이고"))
        self.assertIn("빼는 판과 문턱은 그대로일 때", item)
        self.assertRegex(item, r"판을 빼는 줄도 더하면.{0,20}3번")

    def test_no_ambiguous_han_bot_3(self):
        self.assertNotIn("뺀 봇과 한 봇", bot_sentence())

    def test_points_at_policy_rule_when_no_bot_4(self):
        self.assertIn("주장이 맞는 쪽도 여러 정책으로 낸다", bot_sentence())

    def test_result_file_example_shows_redirect_5(self):
        skill = SKILL.read_text(encoding="utf-8")
        self.assertIn("> playtests/<세션 id>/summary.txt", skill)

    def test_history_says_roles_6(self):
        arch = (ROOT / "docs/architecture.md").read_text(encoding="utf-8")
        line = next(l for l in arch.splitlines() if "409번" in l)
        self.assertIn("역할로 적고", line)
        self.assertNotIn("이름으로 적고", line)


if __name__ == "__main__":
    unittest.main()
