"""402: 기획서를 가져온 길에서 브리프 뒤 시스템 설계를 건너뛰고 바로 시험판 코드를 썼다.
문서만 바꾼 이슈라 concept-exploration의 흐름 문장을 본다. 표준 라이브러리 unittest만 사용한다."""
import re
import unittest

from _studio import ROOT

SKILL = ROOT / "skills/concept-exploration/SKILL.md"


def read(path):
    return path.read_text(encoding="utf-8")


def between(text, start, end):
    return text[text.index(start):text.index(end, text.index(start))]


class ExistingPlan(unittest.TestCase):
    def test_flow_has_a_path_for_a_plan_document(self):
        intro = between(read(SKILL), "## 흐름", "### 1.")
        self.assertIn("기획서", intro)
        self.assertIn("4단계", intro)        # 단순 전략 공격은 그대로 한다
        self.assertIn("8단계", intro)
        self.assertIn("3단계의 칸", intro)   # 후보 12개를 다시 만들라는 뜻으로 읽히지 않게

    def test_brief_step_stops_before_prototype_code(self):
        step8 = between(read(SKILL), "### 8.", "## 보고")
        self.assertIn("시험판 코드", step8)
        self.assertIn("system-design", step8)
        self.assertIn("데이터 파일", step8)  # 수치는 처음부터 데이터 파일에

    def test_stress_step_does_not_build_a_prototype(self):
        step4 = between(read(SKILL), "### 4.", "### 5.")
        self.assertIn("시험판", step4)
        self.assertIn("unknown", step4)
        self.assertIn("기준선이 나오면", step4)   # 모름으로 둔 결과를 그 근거로 고친다


if __name__ == "__main__":
    unittest.main()
