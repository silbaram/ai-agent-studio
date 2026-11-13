"""세 번째 장르(덱빌딩) 시험에서 나온 문서 이슈 363·364 테스트. 표준 라이브러리 unittest만 사용한다."""
import re
import tempfile
import unittest
from pathlib import Path

from _studio import ROOT
from studio_data import provenance

SKILLS = ROOT / "skills"
RULE_LINK = "../progression-economy/SKILL.md#판정-규칙"


def read(rel):
    return (SKILLS / rel).read_text(encoding="utf-8")


def section(text, title, level="##"):
    """`level title` 절의 본문(같은 수준의 다음 제목까지)."""
    m = re.search(rf"^{level} {re.escape(title)}\n(.*?)(?=^{level} |\Z)", text, re.S | re.M)
    assert m, title
    return m.group(1)


class PrototypeNumbersInData(unittest.TestCase):
    """363: 새 게임 시험판을 만들 때 수치는 처음부터 데이터 파일에 둔다."""

    def test_system_design_points_to_single_source_rule(self):
        text = read("system-design/SKILL.md")
        line = next(l for l in text.splitlines() if "그래픽 없는 프로토타입" in l)
        self.assertIn("코드에 적지 않고", line)
        self.assertIn("../progression-economy/SKILL.md#단일-원본-규칙", line)

    def test_single_source_rule_names_prototype_code(self):
        rule = section(read("progression-economy/SKILL.md"), "단일 원본 규칙")
        self.assertIn("시험판", rule)
        self.assertIn("작업 순서 1", rule)
        self.assertNotIn("코드가 그 파일을 읽", rule)   # 할 일은 작업 순서 1에만 둔다


class RuleBasedContent(unittest.TestCase):
    """364: 효과가 규칙인 콘텐츠(카드)는 게임 규칙 코드로 만든 시뮬레이터로 비교한다."""

    def test_single_source_rule_only_links_to_field_mapping(self):
        rule = section(read("progression-economy/SKILL.md"), "단일 원본 규칙")
        self.assertIn("카드", rule)
        self.assertIn("references/data-format.md#효과가-규칙인-콘텐츠", rule)
        self.assertNotIn("unique_effect", rule)
        self.assertNotIn("게임 규칙 코드", rule)

    def test_comparison_method_is_a_verdict_rule_once(self):
        text = read("progression-economy/SKILL.md")
        rule = section(text, "판정 규칙")
        self.assertIn("게임 규칙 코드", rule)
        self.assertIn("game_build", rule)
        self.assertIn("결과 파일", rule)
        self.assertIn("[계산: reports/…]", rule)
        self.assertEqual(text.count("게임 규칙 코드"), 1)

    def test_data_format_maps_cards_to_item_fields(self):
        part = section(read("progression-economy/references/data-format.md"), "효과가 규칙인 콘텐츠")
        for word in ("`slot`", "비용", "`tier`", "`unique_effect`", "`threat_weights`", "acknowledged", "dominated"):
            self.assertIn(word, part, word)
        self.assertIn("../SKILL.md#판정-규칙", part)

    def test_other_balance_skills_link_instead_of_repeating(self):
        for rel in ("combat-balance/SKILL.md", "run-growth/SKILL.md"):
            text = read(rel)
            self.assertIn(RULE_LINK, text, rel)
            self.assertNotIn("게임 규칙 코드", text, rel)

    def test_build_fingerprint_inside_the_tag_breaks_path_check(self):
        """판정 규칙이 지문을 태그 밖(결과 파일)에 두라고 하는 까닭."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "reports").mkdir()
            (base / "reports" / "balance.json").write_text("{}", encoding="utf-8")
            ok = provenance.check_text("차이 1.17 [계산: reports/balance.json]", base_dirs=[base], check_paths=True)
            bad = provenance.check_text("차이 1.17 [계산: reports/balance.json cfge06356a4]", base_dirs=[base], check_paths=True)
        self.assertEqual([f.message for f in ok.findings], [])
        self.assertTrue(any("출처 경로를 찾을 수 없습니다" in f.message for f in bad.findings))


if __name__ == "__main__":
    unittest.main()
