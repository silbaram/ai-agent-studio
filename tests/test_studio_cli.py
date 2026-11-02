"""공용 도구 진입점(studio.py)과 프로젝트 폴더 탐색 테스트."""
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

from _studio import SAMPLE, STUDIO, common, run_cli, viewer

SCRIPT = STUDIO / "scripts/studio.py"


class ProjectDiscovery(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "game"
        shutil.copytree(SAMPLE, self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_project_root_finds_design_and_data_but_skips_meta(self):
        names = sorted(p.relative_to(self.root).as_posix() for p in common.discover([self.root]))
        self.assertEqual(names, ["data/enemies.json", "data/items.json", "data/upgrades.json", "design/concepts.json"])

    def test_deeper_folders_are_not_scanned(self):
        (self.root / "data" / "old").mkdir()
        shutil.copy(self.root / "data/items.json", self.root / "data/old/items.json")
        self.assertNotIn("old", " ".join(str(p) for p in common.discover([self.root])))

    def test_same_file_given_twice_is_listed_once(self):
        self.assertEqual(len(common.discover([self.root / "data", self.root / "data/items.json"])), 3)
        self.assertEqual(len(common.discover([self.root / "data", self.root / "data" / ".." / "data" / "items.json"])), 3)

    def test_kind_needs_an_array(self):
        self.assertIsNone(common.detect_kind({"items": "목록 아님"}))
        self.assertIsNone(common.detect_kind({"concepts": {"a": 1}}))
        self.assertEqual(common.detect_kind({"concepts": [], "items": "x"}), "concepts")


class Check(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "game"
        shutil.copytree(SAMPLE, self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_whole_sample_project_passes(self):
        code, out = run_cli("check", self.root)
        self.assertEqual(code, 0)
        self.assertIn("전체: 파일 4개 · 오류 0 · 경고 0 → PASS", out)

    def test_json_payload_lists_every_dataset(self):
        code, out = run_cli("check", self.root, "--json")
        data = json.loads(out)
        self.assertEqual(sorted(d["kind"] for d in data["datasets"]), ["concepts", "enemies", "items", "upgrades"])

    def test_assumption_gate_applies_to_data_not_concepts(self):
        code, out = run_cli("check", self.root, "--fail-on-assumed")
        self.assertEqual(code, 1)
        self.assertEqual(out.count("gate:"), 3)
        code, _ = run_cli("check", self.root / "design", "--fail-on-assumed")
        self.assertEqual(code, 0)

    def test_table_only_for_concepts(self):
        _, out = run_cli("check", self.root, "--table")
        self.assertEqual(out.count("| id | 이름 | 상태 |"), 1)

    def test_broken_file_in_project_is_usage_error_but_others_still_reported(self):
        (self.root / "data/items.json").write_text("{ broken", encoding="utf-8")
        code, out = run_cli("check", self.root)
        self.assertEqual(code, 2)
        self.assertIn("error [unreadable]", out)
        self.assertIn("design/concepts.json (컨셉)", out.replace("\\", "/"))

    def test_cross_file_reference_when_checking_project(self):
        enemies = json.loads((self.root / "data/enemies.json").read_text(encoding="utf-8"))
        enemies["enemies"][0]["drop_table"] = "chest_missing"
        (self.root / "data/enemies.json").write_text(json.dumps(enemies, ensure_ascii=False), encoding="utf-8")
        code, out = run_cli("check", self.root)
        self.assertEqual(code, 1)
        self.assertIn("unknown_drop_table", out)

    def test_out_file_is_written(self):
        out_path = Path(self.tmp.name) / "reports/check.json"
        run_cli("check", self.root, "--out", out_path)
        self.assertEqual(json.loads(out_path.read_text(encoding="utf-8"))["status"], "pass")

    def test_missing_or_empty_paths(self):
        self.assertEqual(run_cli("check", self.root / "nope")[0], 2)
        empty = Path(self.tmp.name) / "empty"
        empty.mkdir()
        self.assertEqual(run_cli("check", empty)[0], 2)


class ViewerWithConcepts(unittest.TestCase):
    def test_project_snapshot_includes_concepts(self):
        server = viewer.make_server([SAMPLE], port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = "http://127.0.0.1:%d/api/data" % server.server_address[1]
            with urllib.request.urlopen(url, timeout=5) as res:
                snap = json.loads(res.read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()
        kinds = {d["kind"]: d for d in snap["datasets"]}
        self.assertEqual(set(kinds), {"concepts", "items", "upgrades", "enemies"})
        self.assertEqual(kinds["concepts"]["report"]["approved"], ["parry_tempo"])

    def test_page_file_exists_where_the_server_looks(self):
        self.assertTrue(viewer.PAGE.is_file())
        self.assertEqual(viewer.PAGE, STUDIO / "assets/viewer.html")


class Layout(unittest.TestCase):
    def test_python_lives_only_in_studio_data(self):
        skills = STUDIO.parent
        stray = [p.relative_to(skills).as_posix() for p in skills.rglob("*.py")
                 if STUDIO / "scripts" not in p.parents]
        self.assertEqual(stray, [], "파이썬 코드는 skills/studio-data/scripts/ 아래에만 둔다 (AGENTS.md)")


class Launcher(unittest.TestCase):
    def run_script(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True,
                              encoding="utf-8", timeout=60, env={"PYTHONDONTWRITEBYTECODE": "1", "PATH": ""})

    def test_studio_py_runs_from_any_directory(self):
        res = self.run_script("check", SAMPLE)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("PASS", res.stdout)

    def test_help_lists_commands(self):
        res = self.run_script("--help")
        for cmd in ("view", "check", "simulate", "provenance"):
            self.assertIn(cmd, res.stdout)

    def test_unknown_command_is_rejected(self):
        self.assertNotEqual(self.run_script("explode").returncode, 0)


if __name__ == "__main__":
    unittest.main()
