"""성장 반영의 빌드 이름(341번)과 나갈 때 레벨 값(342번). 표준 라이브러리 unittest만 사용한다."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from _studio import ROOT, SAMPLE, datasets, growth, levels as lv, run_cli
from test_grown_kill_ratio import grown, stage
from test_levels import both, enc, level, run
from test_levels_field import ECONOMY, TIMES


def over(**extra):
    return run(both(level("s1", enc(repeat=10, enemy_repeat={"b": 1}))), kill_times=TIMES, economy=ECONOMY, **extra)


def message(r):
    return next(w["message"] for w in r["warnings"] if w["code"] == "kill_time_over_length")


class BuildNames(unittest.TestCase):
    def test_the_builds_over_one_are_named_in_the_warning_341(self):
        msg = message(over(grown_kills=grown({"blade": 0.5, "wall": 0.8})))
        self.assertIn("들어설 때 1배를 넘는 빌드: wall 1.41배", msg)

    def test_a_lower_bound_is_marked_in_the_list(self):
        data = grown({"blade": 0.5, "wall": 0.8})
        del data["wall"]["s1"]["b"]
        self.assertIn("wall 1.33배 이상", message(over(grown_kills=data)))

    def test_ties_name_the_first_build(self):
        self.assertEqual(lv._spread({"by_build": {"a": 0.5, "b": 0.5, "c": 0.9, "d": 0.9}, "unknown": []}), (0.5, 0.9, "a", "c"))

    def test_when_every_build_is_over_one_none_are_listed(self):
        self.assertNotIn("1배를 넘는 빌드", message(over(grown_kills=grown({"blade": 0.9, "wall": 0.8}))))

    def test_when_no_build_is_over_one_none_are_listed(self):
        self.assertNotIn("1배를 넘는 빌드", message(over(grown_kills=grown({"blade": 0.5, "wall": 0.4}))))


class ExitLevel(unittest.TestCase):
    def test_the_exit_value_is_given_342(self):
        s = stage(over(grown_kills=grown({"blade": 0.5}), grown_exit_kills=grown({"blade": 0.25})))
        self.assertEqual(s["grown_exit_ratio"]["by_build"], {"blade": 0.44})

    def test_without_exit_values_there_is_none(self):
        self.assertIsNone(stage(over(grown_kills=grown({"blade": 0.5})))["grown_exit_ratio"])

    def test_the_warning_gives_both_and_drops_the_caveat(self):
        msg = message(over(grown_kills=grown({"blade": 0.5}), grown_exit_kills=grown({"blade": 0.25})))
        self.assertIn("들어설 때 0.88배, 나갈 때 0.44배", msg)
        self.assertNotIn("단계 안 레벨업은 넣지 않은 값", msg)

    def test_a_first_stage_says_enter_equals_base_and_gives_the_exit(self):
        msg = message(over(grown_kills=grown({"blade": 1.0}), grown_exit_kills=grown({"blade": 0.25})))
        self.assertIn("들어설 때는 기준 장비와 같고 나갈 때 0.44배", msg)


class GrowthReport(unittest.TestCase):
    def report(self, root=SAMPLE):
        return next(d["report"] for d in datasets.collect([root]) if d["kind"] == "growth")

    def test_each_build_has_exit_rows_for_all_but_the_last_stage(self):
        r = self.report()
        for info in r["builds"].values():
            self.assertEqual({x["stage"] for x in info["exit_rows"]}, {"zone_1", "zone_2"})
            self.assertEqual(info["exit_levels"], {"zone_1": 4, "zone_2": 9})

    def test_exit_rows_kill_at_least_as_fast(self):
        for info in self.report()["builds"].values():
            enter = {(x["stage"], x["enemy"]): x["time_to_kill"] for x in info["rows"]}
            for x in info["exit_rows"]:
                self.assertLessEqual(x["time_to_kill"], enter[(x["stage"], x["enemy"])])

    def test_a_build_level_override_is_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "p"
            shutil.copytree(SAMPLE, root)
            path = root / "data/growth.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["builds"][0]["level_at"] = {"zone_2": 6}
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            r = self.report(root)
        self.assertEqual(r["builds"][data["builds"][0]["id"]]["exit_levels"]["zone_1"], 6)


class ExitEdgeCases(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "p"
        shutil.copytree(SAMPLE, self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def growth_report(self):
        return next(d["report"] for d in datasets.collect([self.root]) if d["kind"] == "growth")

    def test_a_stage_before_a_skipped_stage_has_no_exit(self):
        path = self.root / "data/growth.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["growth"]["level_at"]["zone_2"] = None   # zone_1을 나갈 때 레벨을 모른다. zone_3의 레벨을 쓰면 성장이 크게 보인다
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        for info in self.growth_report()["builds"].values():
            self.assertEqual(info["exit_levels"], {})
            self.assertEqual(info["exit_rows"], [])

    def test_a_failing_exit_trial_makes_the_build_invalid(self):
        real = growth.cb.evaluate

        def failing(prep, sid, bonus):   # 들어설 때(레벨 1, 선택 없음)는 되고 나갈 때(선택 있음)만 실패한다
            return (None, "test") if sid == "zone_1" and bonus else real(prep, sid, bonus)
        with mock.patch.object(growth.cb, "evaluate", failing):
            r = self.growth_report()
        self.assertEqual(r["builds"], {})
        self.assertIn("build_invalid", [e["code"] for e in r["errors"]])

    def test_the_picks_are_simulated_once_per_build(self):
        calls = []
        real = growth.simulate_trials
        with mock.patch.object(growth, "simulate_trials", lambda *a: calls.append(a) or real(*a)):
            r = self.growth_report()
        self.assertEqual(len(calls), len(r["builds"]))


class Project(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "game"
        shutil.copytree(SAMPLE, self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_the_stage_rows_get_exit_values_except_the_last(self):
        rows = {s["id"]: s for s in next(d["report"] for d in datasets.collect([self.root]) if d["kind"] == "levels")["stages"]}
        self.assertLess(lv._spread(rows["zone_1"]["grown_exit_ratio"])[1], lv._spread(rows["zone_1"]["grown_ratio"])[0])   # 첫 단계도 단계 안에서 레벨업한다
        self.assertIsNone(rows["zone_3"]["grown_exit_ratio"])

    def test_the_table_has_the_exit_column(self):
        out = run_cli("check", self.root, "--table", "levels")[1]
        head = next(x for x in out.splitlines() if x.startswith("| 단계 |"))
        self.assertIn("성장 반영(나갈 때 레벨)", head)
        last = next(x for x in out.splitlines() if x.startswith("| zone_3 |"))
        self.assertEqual(last.split("|")[9].strip(), "–")

    def test_the_check_line_gives_both(self):
        out = run_cli("check", self.root / "data")[1]
        line = next(x for x in out.splitlines() if x.startswith("단계 zone_1") and "위협도 합" in x)
        self.assertIn("나갈 때", line)


class Docs(unittest.TestCase):
    def test_the_format_doc_explains_the_exit_value(self):
        text = (ROOT / "skills/level-design/references/levels-format.md").read_text(encoding="utf-8")
        self.assertIn("나갈 때", text)
        self.assertIn("다음 단계의 `level_at`", text)
        self.assertIn("바로 다음 전투 단계", text)


if __name__ == "__main__":
    unittest.main()
