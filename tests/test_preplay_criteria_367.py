"""367: 플레이 전 단계가 판정 기준의 [가정] 잣대를 사용자에게 정하게 한다. 표준 라이브러리 unittest만 사용한다."""
import re
import unittest

from _studio import ROOT

GUIDE = ROOT / "skills/playtest-verdict/SKILL.md"


def step(title_start):
    text = GUIDE.read_text(encoding="utf-8")
    m = re.search(rf"^### {re.escape(title_start)}.*?\n(.*?)(?=^### |^## |\Z)", text, re.S | re.M)
    assert m, title_start
    return m.group(1)


class PrePlayCriteria(unittest.TestCase):
    def test_step_one_asks_user_to_decide_assumed_yardsticks(self):
        body = step("1. 플레이 전")
        para = next(p for p in body.split("\n\n") if "[가정]" in p)
        for word in ("플레이 전에", "--fail-on-assumed", "컨셉 gate", "brief.hypotheses", "success_criteria", "외 N개", "hypothesis <컨셉>.<가설>",
                     "데이터 파일", "2단계", "#4-측정값을-올린다"):
            self.assertIn(word, para, word)
        self.assertNotIn("표본, 구간", para)   # 표본은 바로 위 문단이 정한다

    def test_step_two_checks_assumed_yardsticks_at_play_time(self):
        """기록 단계가 플레이 때 잣대가 [가정]이었는지 확인하고 이탈로 적는다(규칙은 여기 한 곳)."""
        body = step("2. 플레이한 뒤")
        para = next(p for p in body.split("\n\n") if p.startswith("기록하기 전에"))
        self.assertIn("[가정]", para)
        self.assertIn("deviation", para)
        self.assertNotIn("deviation", step("1. 플레이 전"))

    def test_deviation_defined_once_and_covers_preplay_decisions(self):
        record = (ROOT / "skills/playtest-verdict/references/playtest-record.md").read_text(encoding="utf-8")
        row = next(l for l in record.splitlines() if l.startswith("| `notes` |"))
        self.assertIn("플레이 전에 정할 것", row)
        bullet = next(l for l in step("2. 플레이한 뒤").splitlines() if "그 밖의 관찰과 선호" in l)
        self.assertIn("references/playtest-record.md", bullet)
        self.assertNotIn("정한 설정 순서", bullet)

    def test_decided_tag_rule_stays_in_step_four(self):
        """[결정]으로 바꾸는 규칙은 4단계 한 곳에 두고 1단계는 가리키기만 한다."""
        self.assertIn("[결정: 사용자 2026-11-09]", step("4. 측정값을 올린다"))
        self.assertNotIn("[결정: 사용자", step("1. 플레이 전"))


if __name__ == "__main__":
    unittest.main()
