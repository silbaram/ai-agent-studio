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

from _studio import SAMPLE, STUDIO, common, concepts, datasets, meta_sim, run_cli, viewer

SCRIPT = STUDIO / "scripts/studio.py"


class ProjectDiscovery(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "game"
        shutil.copytree(SAMPLE, self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_project_root_finds_design_and_data_but_skips_meta(self):
        names = sorted(p.relative_to(self.root).as_posix() for p in datasets.discover([self.root]))
        self.assertEqual(names, ["data/enemies.json", "data/items.json", "data/playtests.json", "data/upgrades.json", "design/concepts.json"])

    def test_deeper_folders_are_not_scanned(self):
        (self.root / "data" / "old").mkdir()
        shutil.copy(self.root / "data/items.json", self.root / "data/old/items.json")
        found = [p.relative_to(self.root).parts for p in datasets.discover([self.root])]
        self.assertFalse(any("old" in parts for parts in found))  # 임시 폴더 이름에 old가 들어가도 흔들리지 않게 상대 경로로 본다

    def test_same_file_given_twice_is_listed_once(self):
        self.assertEqual(len(datasets.discover([self.root / "data", self.root / "data/items.json"])), 4)
        self.assertEqual(len(datasets.discover([self.root / "data", self.root / "data" / ".." / "data" / "items.json"])), 4)

    def test_wrong_shaped_key_is_still_that_kind(self):
        # 형식이 틀려도 종류로 인정해야 검사기가 형식 오류를 보고한다 (조용히 건너뛰면 안 된다).
        self.assertEqual(common.detect_kind({"items": "목록 아님"}), "items")
        self.assertEqual(common.detect_kind({"concepts": {"a": 1}}), "concepts")
        self.assertIsNone(common.detect_kind({"notes": []}))
        self.assertEqual(common.detect_kind({"rooms": 3, "difficulty": {}, "upgrades": []}), "meta")


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
        self.assertIn("전체: 파일 5개 · 오류 0 · 경고 0 → PASS", out)

    def test_json_payload_lists_every_dataset(self):
        code, out = run_cli("check", self.root, "--json")
        data = json.loads(out)
        self.assertEqual(sorted(d["kind"] for d in data["datasets"]), ["concepts", "enemies", "items", "playtests", "upgrades"])

    def test_assumption_gate_applies_to_data_and_brief_criteria(self):
        code, out = run_cli("check", self.root, "--fail-on-assumed")
        self.assertEqual(code, 1)
        self.assertEqual(out.count("gate:"), 5)
        code, out = run_cli("check", self.root / "design", "--fail-on-assumed")
        self.assertEqual(code, 1)
        self.assertIn("parry_tempo.brief.hypotheses[0].failure_signal", out)
        # 브리프의 판정 기준을 측정값으로 올리면 게이트를 통과한다.
        path = self.root / "design/concepts.json"
        path.write_text(path.read_text(encoding="utf-8").replace("[가정]", "[측정: playtest-1]"), encoding="utf-8")
        self.assertEqual(run_cli("check", self.root / "design", "--fail-on-assumed")[0], 0)

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


class ReviewRegressions(unittest.TestCase):
    """머지 전 코드 리뷰에서 찾은 문제가 다시 생기지 않게 막는다."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "game"
        shutil.copytree(SAMPLE, self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def load(self, rel):
        return json.loads((self.root / rel).read_text(encoding="utf-8"))

    def save(self, rel, data):
        (self.root / rel).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def test_wrong_shaped_dataset_is_reported_not_skipped(self):
        for rel, key in (("data/items.json", "items"), ("design/concepts.json", "concepts")):
            with self.subTest(rel):
                original = self.load(rel)
                broken = dict(original)
                broken[key] = {"oops": 1}
                self.save(rel, broken)
                code, out = run_cli("check", self.root)
                self.assertEqual(code, 1)
                self.assertIn(f"{key} 배열이 필요합니다", out)
                self.assertIn("파일 5개", out)
                self.save(rel, original)

    def test_non_string_origin_is_a_schema_error_not_a_crash(self):
        data = self.load("design/concepts.json")
        data["concepts"][1]["origin"] = ["parry_tempo"]
        self.save("design/concepts.json", data)
        code, out = run_cli("check", self.root / "design")
        self.assertEqual(code, 1)
        self.assertIn("origin은 'root' 또는 원본 컨셉 id", out)

    def test_duplicate_id_with_bad_status_does_not_break_table(self):
        data = self.load("design/concepts.json")
        dup = dict(data["concepts"][1], status="foo", name="중복본")
        data["concepts"].append(dup)
        self.save("design/concepts.json", data)
        code, out = run_cli("check", self.root / "design", "--table")
        self.assertEqual(code, 1)
        self.assertIn("duplicate_id", out)
        self.assertIn(f"| {dup['id']} | {data['concepts'][1]['name']} |", out)
        self.assertNotIn("중복본", out)

    def test_stress_errors_point_at_the_concept(self):
        data = self.load("design/concepts.json")
        data["concepts"][1]["stress"].append({"policy": "idle"})
        self.save("design/concepts.json", data)
        r = concepts.validate(self.load("design/concepts.json"))
        self.assertIn(data["concepts"][1]["id"], [e["where"] for e in r["errors"]])

    def test_messages_name_current_commands(self):
        code, out = run_cli("check", self.root / "data/enemies.json")
        self.assertEqual(code, 0)
        self.assertNotIn("--items", out)
        self.assertIn("items.json", out)
        ups = self.load("data/upgrades.json")
        ups["upgrades"][0]["requires"] = ["ghost"]
        self.save("data/upgrades.json", ups)
        with self.assertRaisesRegex(meta_sim.ConfigError, "studio.py check"):
            meta_sim.run_config(self.root / "data/meta.json")

    def test_validator_crash_is_contained_to_one_file(self):
        class Boom:
            @staticmethod
            def validate(data):
                raise RuntimeError("터짐")

        original = datasets.VALIDATORS["upgrades"]
        datasets.VALIDATORS["upgrades"] = Boom
        try:
            entries = datasets.collect([self.root])
            by_kind = {e["kind"]: e for e in entries}
            self.assertFalse(by_kind["upgrades"]["ok"])
            self.assertIn("RuntimeError", by_kind["upgrades"]["error"])
            self.assertTrue(by_kind["items"]["ok"] and "report" in by_kind["items"])
            self.assertEqual(run_cli("check", self.root)[0], 2)
        finally:
            datasets.VALIDATORS["upgrades"] = original

    def test_viewer_revalidates_only_when_files_change(self):
        cache = viewer.SnapshotCache([self.root])
        first = cache.body_bytes()
        self.assertEqual(cache.body_bytes(), first)
        self.assertEqual(cache.validations, 1)
        data = self.load("data/items.json")
        data["items"][0]["price"] = 1
        self.save("data/items.json", data)
        self.assertNotEqual(cache.body_bytes(), first)
        self.assertEqual(cache.validations, 2)

    def test_folder_scan_reads_each_file_once(self):
        calls = []
        original = datasets.read

        def counting(path):
            calls.append(Path(path).name)
            return original(path)

        datasets.read = counting
        try:
            datasets.collect([self.root])
        finally:
            datasets.read = original
        self.assertEqual(sorted(calls), ["concepts.json", "enemies.json", "items.json", "meta.json", "playtests.json", "upgrades.json"])


class ViewWithoutData(unittest.TestCase):
    """데이터가 아직 없어도 뷰어가 열리고, 나중에 생긴 파일을 자동으로 보여 준다."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "game"
        self.root.mkdir()
        self.served = []
        self.original_serve = viewer.serve

        def fake_serve(server, open_browser=True):  # 실제로 기다리지 않고 바로 닫는다
            self.served.append(open_browser)
            server.server_close()

        viewer.serve = fake_serve

    def tearDown(self):
        viewer.serve = self.original_serve
        self.tmp.cleanup()

    def test_empty_project_opens_with_guidance(self):
        code, out = run_cli("view", self.root, "--port", 0, "--no-browser")
        self.assertEqual(code, 0)
        self.assertEqual(self.served, [False])
        self.assertIn("아직 데이터 파일이 없습니다", out)
        self.assertIn(str(self.root.resolve() / "design"), out)
        self.assertIn(str(self.root.resolve() / "data"), out)

    def test_project_with_data_lists_files(self):
        shutil.copytree(SAMPLE / "design", self.root / "design")
        code, out = run_cli("view", self.root, "--port", 0, "--no-browser")
        self.assertEqual(code, 0)
        self.assertIn("concepts.json", out)
        self.assertNotIn("아직 데이터 파일이 없습니다", out)

    def test_missing_path_is_still_an_error(self):
        self.assertEqual(run_cli("view", self.root / "nope", "--no-browser")[0], 2)
        self.assertEqual(self.served, [])

    def test_files_created_after_start_appear(self):
        server = viewer.make_server([self.root], port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = "http://127.0.0.1:%d/api/data" % server.server_address[1]

        def get():
            with urllib.request.urlopen(url, timeout=5) as res:
                return json.loads(res.read().decode("utf-8"))

        try:
            first = get()
            self.assertEqual(first["datasets"], [])
            self.assertIn(str(self.root.resolve() / "design"), first["watched"])
            (self.root / "design").mkdir()
            shutil.copy(SAMPLE / "design/concepts.json", self.root / "design/concepts.json")
            second = get()
            self.assertEqual([d["kind"] for d in second["datasets"]], ["concepts"])
            self.assertNotEqual(first["version"], second["version"])
        finally:
            server.shutdown()
            server.server_close()


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
        self.assertEqual(set(kinds), {"concepts", "items", "upgrades", "enemies", "playtests"})
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
