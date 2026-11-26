"""410: 플레이 전 가설 카드가 왜 사람이 직접 해야 하는지 말하지 않았다.
사용자는 12판을 부탁받고 "지금 왜 실제 테스트 게임을 해야하지?"라고 물었다. 봇이 이미 보인 것과
사람 판만 보이는 것을 가르는 규칙은 가설을 쓰는 브리프 작성법에만 있었다.
문서만 바꾼 이슈라 문서의 틀과 연결을 본다. 표준 라이브러리 unittest만 사용한다."""
import re
import unittest

from _studio import ROOT

GUIDE = ROOT / "skills/studio-data/references/telling-the-user.md"


def card():
    text = GUIDE.read_text(encoding="utf-8")
    rest = text.split("## 가설 카드", 1)[1]
    return rest.split("\n## ", 1)[0]


def template():
    return card().split("```text", 1)[1].split("```", 1)[0]


class WhyPlay(unittest.TestCase):
    def test_card_has_the_why_line_after_what(self):
        lines = [l for l in template().splitlines() if l.startswith("- ")]
        heads = [l[2:].split(":", 1)[0] for l in lines]
        self.assertIn("왜 직접 해야 하나", heads)
        self.assertEqual(heads.index("왜 직접 해야 하나"), heads.index("무엇을 확인하나") + 1)
        why = lines[heads.index("왜 직접 해야 하나")]
        self.assertIn("봇", why)
        self.assertIn("사람", why)

    def test_after_verdict_drops_the_why_line(self):
        self.assertRegex(card(), r"판정 뒤에는 '왜 직접 해야 하나'와 '할 일' 대신")

    def test_writing_rule_takes_bot_values_from_test(self):
        rule = next(l for l in card().splitlines() if l.startswith("- **왜 직접 해야 하나"))
        self.assertIn("`test`의 문턱 옆", rule)

    def test_simulated_runs_are_linked_not_restated(self):
        rule = next(l for l in card().splitlines() if l.startswith("- **왜 직접 해야 하나"))
        self.assertIn("../../playtest-verdict/references/playtest-record.md#세션-playtests", rule)
        self.assertNotIn("표본(판·사람 수)에 세지 않고", rule)   # 규칙은 형식 문서 한 곳

    def test_rule_claim_goes_back_to_the_brief_rule(self):
        rule = next(l for l in card().splitlines() if l.startswith("- **왜 직접 해야 하나"))
        self.assertIn("../../concept-exploration/references/brief.md#가설-hypotheses-1개-이상", rule)
        self.assertIn("사람이 해야 아는 것을 잰다", rule)
        self.assertRegex(rule, r"한 줄로 쓸 수 없으면.{0,160}정할 것에 올린다")

    def test_links_resolve(self):
        rule = next(l for l in card().splitlines() if l.startswith("- **왜 직접 해야 하나"))
        for target in re.findall(r"\]\(([^)#]+)", rule):
            self.assertTrue((GUIDE.parent / target).resolve().is_file(), target)

    def test_history(self):
        arch = (ROOT / "docs/architecture.md").read_text(encoding="utf-8")
        self.assertTrue(any("410번" in l for l in arch.splitlines()))


def rule():
    return next(l for l in card().splitlines() if l.startswith("- **왜 직접 해야 하나"))


class Review(unittest.TestCase):
    """410 수정을 먼저 검토해 찾은 일곱 건."""

    def test_no_bot_before_prototype_is_not_a_gap_1(self):
        self.assertIn("시험판 전이면 '아직 봇 없음", rule())
        self.assertIn("정할 것이 아니다", rule())
        self.assertNotIn("약속서에 봇 값 없음", rule())

    def test_missing_value_with_a_bot_goes_to_step1_2(self):
        self.assertIn("봇이 있는데 `test`에 값이 없으면 '없음'으로 쓰지 않고", rule())
        self.assertIn("../../playtest-verdict/SKILL.md#1-플레이-전-가설에-id와-최소-표본을-단다", rule())

    def test_felt_answer_says_bots_cannot_answer_3(self):
        self.assertIn("봇은 이 질문에 답하지 못한다", rule())
        self.assertIn("로그 지표", rule())

    def test_simulated_sentence_has_a_place_4(self):
        self.assertIn("플레이 전 카드의 첫 카드 앞에 한 번", rule())

    def test_rule_claim_change_route_5(self):
        self.assertRegex(rule(), r"플레이 전이면 고치는 길은.{0,80}'어긋나면 플레이 전에 고친다'")

    def test_roadmap_row7_not_overstated_6(self):
        arch = (ROOT / "docs/architecture.md").read_text(encoding="utf-8")
        row7 = next(l for l in arch.splitlines() if l.startswith("| 7 |"))
        self.assertNotIn("현장 시험 전", row7)
        self.assertNotIn("2회 통과", row7)
        self.assertIn("394~396 고침", row7)

    def test_stronger_checks_7(self):
        prose = re.sub(r"\]\([^)]*\)", "]", rule())   # 링크 주소(앵커)는 빼고 본다
        for word in ("표본", "근거"):   # 세지 않는 규칙은 형식 문서 한 곳
            self.assertNotIn(word, prose)
        after = card().split("```text", 2)[2].split("```", 1)[0]
        self.assertNotIn("왜 직접 해야 하나", after)


if __name__ == "__main__":
    unittest.main()
