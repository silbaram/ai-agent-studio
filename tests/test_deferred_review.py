"""미룬 이슈 묶음(2026-11-11)의 검토에서 나온 것. 표준 라이브러리 unittest만 사용한다."""
import json
import unittest
from unittest import mock

from _studio import ROOT, datasets
from studio_data import scope
from test_deferred_level import SplitKills
from test_levels import both, enc, level, run
from test_levels_field import notes
from test_levels_greybox import item
from test_scope import HookCase

FORMAT = ROOT / "skills/system-design/references/systems-format.md"


class RedirectIsNotReading(HookCase):
    """글을 찍는 명령이라도 출력을 파일로 보내면 그 파일을 실행할 수 있다. 범위 오류가 있으면 막는다."""

    def setUp(self):
        super().setUp()
        self.change()   # change_without_system으로 FAIL

    def test_writing_an_archive_into_a_file_is_blocked(self):
        for command in ("printf 'openspec archive add-tempo' > a.sh; bash a.sh", "echo openspec archive add-tempo > a.sh && sh a.sh",
                        "echo 'openspec archive add-tempo' | cat > a.sh", "echo 'openspec archive add-tempo' >> a.sh",
                        "grep -h 'openspec archive add-tempo' notes.md >a.sh"):
            with self.subTest(command):
                self.assert_blocked(self.run_hook("Bash", command=command), "change_without_system")

    def test_joining_streams_is_still_reading(self):
        for command in ('echo "openspec archive add-tempo" 2>&1 | head', 'grep -rn "openspec archive" docs 2>/dev/null'.replace(" 2>/dev/null", " 2>&1"),
                        'grep -rn "a > b openspec archive" docs'):
            with self.subTest(command):
                self.assert_silent(self.run_hook("Bash", command=command))


class ArchiveFolderCase(HookCase):
    """대소문자를 가리지 않는 것은 openspec 쪽이다. 다른 Archive 폴더로 옮기는 것은 보관이 아니다."""

    def setUp(self):
        super().setUp()
        self.change()

    def test_moving_to_an_unrelated_archive_folder_passes(self):
        self.assert_silent(self.run_hook("Bash", command="mv notes.txt Archive/"))

    def test_moving_a_change_in_other_case_is_blocked(self):
        for command in ("mv OpenSpec/Changes/add-tempo x", "mv x archive/", "MV openspec/changes/add-tempo x"):
            with self.subTest(command):
                self.assert_blocked(self.run_hook("Bash", command=command), "change_without_system")


class SplitWithoutKills(unittest.TestCase):
    """132번의 재현: 처치를 한 단계에 몰고 다른 단계는 비워도 합으로만 맞춘 것이다."""

    def test_an_empty_sibling_stage_is_named(self):
        eco = {"stages": [{"id": "x", "combat_stage": "s1", "kills": {"a": 5, "b": 1}}, {"id": "y", "combat_stage": "s1", "duration": 30, "kills": {}},
                          {"id": "s2", "kills": {"c": 6}}]}
        self.assertIn("처치 수는 합으로만 맞춰 봤습니다: s1(x, y)", notes(run(economy=eco)))

    def test_the_old_split_case_still_works(self):
        self.assertIn("s1(x, y)", notes(run(economy=SplitKills.SPLIT)))


class BrokenListElsewhere(unittest.TestCase):
    """한 레벨의 항목이 모두 형식 오류여도 다른 레벨의 '목록 없이 플레이함' 참고 줄은 남는다."""

    def test_the_other_played_level_is_still_named(self):
        r = run(both(level("s1", enc(), greybox=[item(check="")]), level("s2", enc("e2", {"c": 6}))), played_stages={"s2": 2})
        self.assertIn("그레이박스 확인 항목이 없습니다: 플레이 기록이 있는 레벨 s2", notes(r))
        self.assertNotIn("레벨 s1(", notes(r))


class CountsAreExplained(unittest.TestCase):
    def test_the_format_says_what_each_number_counts(self):
        text = FORMAT.read_text(encoding="utf-8")
        self.assertIn("상태별 수는 id와 상태를 읽은 시스템만 센다", text)


class ConceptInUseReadsOnlyConcepts(unittest.TestCase):
    """훅이 범위 파일을 고칠 때마다 프로젝트 전체를 읽지 않는다."""

    def test_the_implied_concept_comes_from_the_concept_file(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "design").mkdir()
            (root / "design/systems.json").write_text(json.dumps({"systems": []}), encoding="utf-8")
            (root / "design/concepts.json").write_text(json.dumps({"concepts": [{"id": "gems", "status": "approved"}, {"id": "b", "status": "proposed"}]}), encoding="utf-8")
            with mock.patch.object(datasets, "scan", side_effect=AssertionError("scan")):
                self.assertEqual(scope.concept_in_use(root), "gems")

    def test_two_concept_files_imply_nothing(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "design").mkdir()
            (root / "design/systems.json").write_text(json.dumps({"systems": []}), encoding="utf-8")
            for place in ("design/concepts.json", "concepts.json"):
                (root / place).write_text(json.dumps({"concepts": [{"id": place.replace("/", "_").replace(".", "_"), "status": "approved"}]}), encoding="utf-8")
            self.assertIsNone(scope.concept_in_use(root))


if __name__ == "__main__":
    unittest.main()
