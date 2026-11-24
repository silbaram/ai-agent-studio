"""398: 공용 '정할 것' 모양은 추천 줄을 늘 요구하지만, concept-exploration은 사용자가 추천을 청하기 전에는 후보 하나를 내세우지 않는다.
공용 모양이 그런 스킬의 규칙을 따르게 하고, 그때 추천 줄과 '모두 추천대로' 질문을 어떻게 하는지 정한다."""
import unittest

from _studio import ROOT

PAGE = ROOT / "skills/studio-data/references/telling-the-user.md"


def section():
    text = PAGE.read_text(encoding="utf-8")
    return text.split("## 정할 것", 1)[1].split("\n## ", 1)[0]


class DecideShape(unittest.TestCase):
    def test_a_skill_that_holds_back_a_pick_wins(self):
        s = section()
        self.assertIn("추천하지 않는", s)
        self.assertIn("그 스킬", s)

    def test_the_recommend_line_says_ask_me_instead(self):
        s = section()
        self.assertIn("추천: 청하시면 하나를 권합니다", s)
        self.assertNotIn("고릅니다", s)          # 1: 선택은 사용자가 한다

    def test_all_as_recommended_needs_a_recommendation(self):
        s = section()
        self.assertRegex(s, r"추천이 없는 것은.{0,40}하나씩")
        self.assertRegex(s, r"추천이 있는 것끼리.{0,40}먼저")   # 2: 묻는 순서를 한 문장으로
        self.assertEqual(s.count("하나씩 묻는다"), 1)

    def test_concept_exploration_keeps_the_rule_itself(self):
        # 한 규칙은 한 곳: 공용 모양은 컨셉 단계의 조건을 옮겨 적지 않는다
        self.assertNotIn("추천 요청", section())
        concept = (ROOT / "skills/concept-exploration/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("선택 전(추천 요청 없음)", concept)       # 3: 조건은 컨셉 쪽에 남아 있다
        self.assertIn("하나를 골라 내세우면", concept)


if __name__ == "__main__":
    unittest.main()
