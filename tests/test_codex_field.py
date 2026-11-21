"""Codex 현장 시험(2026-11-22)의 이슈 393 테스트와 확인 범위 문장. 392는 test_hook_output.NoTempDir. 표준 라이브러리 unittest만 사용한다."""
import unittest

from _studio import ROOT

BRIEF = ROOT / "skills/concept-exploration/references/brief.md"
README = ROOT / "README.md"
STUDIO_DOC = ROOT / "skills/studio-data/SKILL.md"


def read(path):
    return path.read_text(encoding="utf-8")


def hypothesis_checklist():
    text = read(BRIEF)
    start = text.index('"재미있을 것이다"는 가설이 아니다.')
    return text[start:text.index("\n## ", start)]


class RuleChecksAreNotPlaytests(unittest.TestCase):
    """393번: 같은 입력이면 같은 결과가 나오는 규칙 성질은 플레이 전 계산으로 보고, 가설은 사람이 고르거나 느끼는 것을 잰다."""

    def test_checklist_sends_rule_properties_to_pre_play_checks(self):
        first = hypothesis_checklist().split("\n- ")[1]
        self.assertTrue(first.startswith("**사람이 해야 아는 것을 잰다.**"), first[:80])
        self.assertIn("같은 입력이면 같은 결과", first)
        self.assertIn("stress-policies.md", first)
        self.assertIn("기준선", first)
        self.assertIn("고르는지", first)
        self.assertIn("느끼는지", first)


class CodexScope(unittest.TestCase):
    """Codex에서 실제로 돌려 본 범위를 한 곳(studio-data 실행)에 적고, README는 그것을 가리킨다."""

    def test_studio_data_names_the_checked_codex_run(self):
        run = read(STUDIO_DOC)
        run = run[run.index("## 실행"):]
        run = run[:run.index("\n## ", 1)]
        self.assertIn("codex-cli 0.171.0", run)
        self.assertIn("읽기 전용", run)
        scope = next(line for line in run.splitlines() if line.startswith("- 확인 범위:"))
        self.assertIn("Claude Code와 Codex 모두 스킬 이름 없이", scope)   # README의 스킬 고르기 문장이 이 줄을 가리킨다

    def test_guide_points_to_the_scope_instead_of_restating_it(self):
        guide = read(ROOT / "docs/guide.md")
        self.assertNotIn("Codex에서는 아직 확인하지 않았다", guide)
        para = next(p for p in guide.split("\n\n") if "스스로 고를 수 있다" in p)
        self.assertIn("(../skills/studio-data/SKILL.md#실행)", para)
        self.assertNotIn("혼자 만들 작은 2D 게임", para)

    def test_unchecked_list_names_only_unchecked_hosts(self):
        line = next(l for l in read(ROOT / "docs/architecture.md").splitlines() if l.startswith("실제 세션으로 확인하지 못한 것:"))
        self.assertNotIn("Codex", line)

    def test_readme_status_says_field_tested_stages(self):
        text = read(README)
        self.assertNotIn("현장 시험은 아직이다", text)
        self.assertNotIn("검사기와 현장 시험은 아직이다", text)

    def test_readme_no_longer_says_codex_is_unchecked(self):
        text = read(README)
        self.assertNotIn("Codex에서는 아직 확인하지 않았다", text)
        self.assertNotIn("Codex와 Windows PowerShell은 아직 실제로 돌려 보지 않았다", text)
        self.assertIn("(skills/studio-data/SKILL.md#실행)", text)


if __name__ == "__main__":
    unittest.main()
