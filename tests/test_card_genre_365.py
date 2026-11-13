"""363 현장 시험에서 나온 365·366 테스트: 수치가 게임 코드에만 있을 때. 표준 라이브러리 unittest만 사용한다."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from _studio import ROOT, SAMPLE, run_cli, section

GUIDE = ROOT / "skills/progression-economy/SKILL.md"
NOTE = "게임 수치 데이터 파일이 없습니다"


class Project:
    """design/만 있는 프로젝트(컨셉과 시스템 설계). data_files에 준 샘플 데이터만 data/에 복사한다."""

    def __init__(self, data_files=(), systems=True):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "design").mkdir()
        shutil.copy(SAMPLE / "design/concepts.json", self.root / "design")
        if systems:
            shutil.copy(SAMPLE / "design/systems.json", self.root / "design")
        if data_files:
            (self.root / "data").mkdir()
            for name in data_files:
                shutil.copy(SAMPLE / "data" / name, self.root / "data")

    def __enter__(self):
        return self.root

    def __exit__(self, *exc):
        self.tmp.cleanup()


class NoGameDataNote(unittest.TestCase):
    """365: 시스템 설계는 있는데 게임 수치 데이터 파일이 하나도 없으면 check가 참고 줄로 알린다."""

    def test_systems_without_data_files_prints_note(self):
        with Project() as root:
            code, out = run_cli("check", root)
        self.assertEqual(code, 0, out)
        line = next(l for l in out.splitlines() if NOTE in l)
        self.assertTrue(line.startswith("참고: "), line)
        self.assertIn("progression-economy SKILL.md", line)
        self.assertIn("'작업 순서' 1", line)

    def test_note_is_in_json_payload(self):
        with Project() as root:
            code, out = run_cli("check", root, "--json")
        notes = json.loads(out)["notes"]
        self.assertEqual(len(notes), 1)
        self.assertIn(NOTE, notes[0])

    def test_any_game_data_file_silences_note(self):
        with Project(data_files=("items.json",)) as root:
            code, out = run_cli("check", root)
        self.assertNotIn(NOTE, out)

    def test_no_systems_no_note(self):
        """컨셉 단계에는 아직 수치가 없어도 된다."""
        with Project(systems=False) as root:
            code, out = run_cli("check", root)
        self.assertNotIn(NOTE, out)

    def test_message_says_ignore_when_game_has_no_numbers(self):
        with Project() as root:
            code, out = run_cli("check", root)
        line = next(l for l in out.splitlines() if NOTE in l)
        self.assertIn("무시", line)

    def test_subfolder_target_no_note(self):
        """문서가 시키는 check design/는 data/를 보지 않으니 데이터 유무를 알 수 없다."""
        with Project(data_files=("items.json",)) as root:
            code, out = run_cli("check", root / "design")
        self.assertNotIn(NOTE, out)

    def test_unread_file_in_data_folder_no_note(self):
        """data/에 이 도구가 읽지 못한 파일(문법 오류, 게임 고유 형식)이 있으면 수치가 코드에만 있다고 하지 않는다."""
        for text in ('{"items": [', '{"cards": [{"id": "strike", "dmg": 6}]}'):
            with self.subTest(text=text), Project() as root:
                (root / "data").mkdir()
                (root / "data/cards.json").write_text(text, encoding="utf-8")
                code, out = run_cli("check", root)
                self.assertNotIn(NOTE, out)

    def test_single_file_target_no_note(self):
        """파일 하나만 검사하면 프로젝트의 데이터 파일 유무를 알 수 없다."""
        with Project() as root:
            code, out = run_cli("check", root / "design/systems.json")
        self.assertNotIn(NOTE, out)


class Docs(unittest.TestCase):
    def test_work_step_one_moves_code_numbers_first(self):
        steps = section(GUIDE, "작업 순서")
        step1 = next(l for l in steps.splitlines() if l.startswith("1. "))
        self.assertIn("코드에만", step1)
        self.assertIn("다른 점검 전에", step1)
        self.assertIn("빌드 지문", step1)

    def test_single_source_rule_covers_reports_and_tags(self):
        """366: 보고서에도 항목 수치를 옮겨 적지 않고, 옮긴 값에 [계산]을 붙이지 않는다."""
        rule = section(GUIDE, "단일 원본 규칙")
        line = next(l for l in rule.splitlines() if "`id`로만" in l)
        self.assertIn("보고서", line)
        self.assertIn("[계산", line)
        self.assertIn("뷰어", line)


if __name__ == "__main__":
    unittest.main()
