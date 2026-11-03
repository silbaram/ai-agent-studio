"""판 안 성장(growth) 테스트: 레벨업 선택, 빌드 정책, 전투 계산에 더한 결과, 빌드 우열. 표준 라이브러리 unittest만 사용한다."""
import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from _studio import SAMPLE, growth as gr, run_cli

COMBAT = {"combat": {"stats": {"player": {"hp": "max_hp", "attack": "attack", "defense": "armor"},
                               "enemy": {"hp": "hp", "attack": "damage"}},
                     "defense": {"form": "ratio", "k": 100}},
          "stages": [{"id": "s1", "player": {"base": {"max_hp": 100, "attack": 10}}, "enemies": ["slime"]},
                     {"id": "s2", "player": {"base": {"max_hp": 100, "attack": 10}}, "enemies": ["slime"]}]}
ENEMIES = {"slime": {"id": "slime", "rank": "normal", "stats": {"hp": 60, "damage": 10}}}
CHOICES = [{"id": "sharpen", "stats": {"attack": 2}, "max_picks": 2},
           {"id": "vigor", "stats": {"max_hp": 15}},
           {"id": "plating", "stats": {"armor": 20}}]


def data(**over):
    d = {"growth": {"level_at": {"s1": 4, "s2": 6}, "offers": 3, "trials": 400, "seed": 7},
         "choices": copy.deepcopy(CHOICES),
         "builds": [{"id": "blade", "priority": ["sharpen", "vigor"]}]}
    for k, v in over.items():
        (d["growth"] if k in ("level_at", "offers", "trials", "seed") else d)[k] = v
    return d


def codes(entries):
    return [e["code"] for e in entries]


def validate(d, combat=COMBAT, enemies=ENEMIES):
    return gr.validate(d, combat=combat, items={}, upgrades={}, enemies=enemies)


def stage(r, build, sid):
    return r["builds"][build]["stages"][sid]


class Picks(unittest.TestCase):
    def test_priority_build_takes_the_top_choice_until_it_is_maxed(self):
        r = validate(data())   # 모든 선택지가 제시된다(3개 중 3개)
        self.assertEqual(r["errors"], [])
        s1 = stage(r, "blade", "s1")      # 레벨 4 = 레벨업 3번: sharpen 2(최대), vigor 1
        self.assertEqual(s1["picks"], {"sharpen": 2, "vigor": 1})
        self.assertEqual(s1["bonus"], {"attack": 4, "max_hp": 15})
        self.assertEqual(stage(r, "blade", "s2")["picks"], {"sharpen": 2, "vigor": 3})

    def test_spread_build_alternates(self):
        r = validate(data(builds=[{"id": "mix", "priority": ["vigor", "plating"], "pick": "spread"}]))
        self.assertEqual(stage(r, "mix", "s1")["picks"], {"vigor": 2, "plating": 1})

    def test_random_offers_give_expected_picks(self):
        r = validate(data(offers=1, trials=4000))
        # 한 번에 하나만 제시되면 첫 레벨업에서 sharpen을 받을 확률은 1/3
        picks = stage(r, "blade", "s1")["picks"]
        self.assertAlmostEqual(sum(picks.values()), 3, places=6)
        self.assertGreater(picks.get("plating", 0), 0.5)     # 원하지 않아도 제시된 것을 고른다

    def test_same_seed_same_result(self):
        a = validate(data(offers=2))
        b = validate(data(offers=2))
        self.assertEqual(a["builds"], b["builds"])


class Combat(unittest.TestCase):
    def test_growth_is_added_to_the_combat_stage(self):
        r = validate(data())
        base = next(x for x in r["builds"]["blade"]["rows"] if x["stage"] == "s1")
        self.assertEqual(base["hits_to_kill"], 5)              # 공격 10 + 4 = 14 → 60 / 14 = 4.3 → 5
        self.assertEqual(r["base_rows"][0]["hits_to_kill"], 6)  # 성장 없이 60 / 10

    def test_build_better_everywhere_is_warned(self):
        builds = [{"id": "blade", "priority": ["sharpen", "plating"]}, {"id": "weak", "priority": ["vigor"]},
                  {"id": "wall", "priority": ["plating", "vigor"]}]
        r = validate(data(builds=builds))
        dominated = [w for w in r["warnings"] if w["code"] == "build_dominated"]
        self.assertEqual([w["where"] for w in dominated], ["weak"])
        self.assertIn("wall", dominated[0]["message"])


    def test_identical_builds_are_not_dominated(self):
        builds = [{"id": "a", "priority": ["sharpen", "vigor"]}, {"id": "b", "priority": ["sharpen", "vigor"]}]
        self.assertEqual(validate(data(builds=builds))["warnings"], [])


class ReviewFindings(unittest.TestCase):
    """코드 검토에서 나온 문제의 회귀 테스트."""

    def test_growth_that_breaks_combat_stats_is_an_error_not_a_misaligned_compare(self):
        choices = CHOICES + [{"id": "focus", "stats": {"crit_chance": 0.6}}]
        combat = copy.deepcopy(COMBAT)
        combat["combat"]["stats"]["player"]["crit_chance"] = "crit_chance"
        builds = [{"id": "crit", "priority": ["focus"]}, {"id": "wall", "priority": ["plating"]}]
        r = validate(data(choices=choices, builds=builds), combat=combat)
        self.assertEqual(codes(r["errors"]), ["build_invalid"])
        self.assertIn("crit", r["errors"][0]["where"])
        self.assertNotIn("crit", r["builds"])                  # 계산에 쓸 수 없는 빌드는 비교하지 않는다

    def test_choice_stat_unknown_to_combat_is_warned(self):
        choices = CHOICES + [{"id": "typo", "stats": {"atack": 2}}]
        r = validate(data(choices=choices))
        w = [x for x in r["warnings"] if x["code"] == "stat_not_in_combat"]
        self.assertEqual([x["where"] for x in w], ["typo"])
        self.assertIn("attack", w[0]["message"])               # 오타 안내

    def test_combat_is_averaged_over_trials_not_run_at_average_stats(self):
        # 레벨업 한 번, 선택지 둘 중 하나 제시: 절반은 공격 +4(60/14 → 5타), 절반은 체력(60/10 → 6타) → 평균 5.5타
        choices = [{"id": "big", "stats": {"attack": 4}}, {"id": "vigor", "stats": {"max_hp": 15}}]
        r = validate(data(choices=choices, level_at={"s1": 2}, offers=1, trials=4000, builds=[{"id": "b", "priority": ["big"]}]))
        row = r["builds"]["b"]["rows"][0]
        self.assertAlmostEqual(row["hits_to_kill"], 5.5, places=1)

    def test_cut_combat_stage_in_level_at_is_warned(self):
        combat = copy.deepcopy(COMBAT)
        combat["stages"][1]["status"] = "cut"
        r = validate(data(), combat=combat)
        self.assertEqual(codes(r["warnings"]), ["cut_referenced"])
        self.assertEqual(list(r["builds"]["blade"]["stages"]), ["s1"])

    def test_nothing_active_is_reported(self):
        builds = [{"id": "blade", "priority": ["sharpen"], "status": "cut"}]
        r = validate(data(builds=builds))
        self.assertEqual(codes(r["warnings"]), ["nothing_to_compare"])

    def test_trials_have_an_upper_bound(self):
        self.assertIn("schema", codes(validate(data(trials=10 ** 7))["errors"]))

    def test_table_does_not_label_the_baseline_as_level_one(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name) / "game"
        shutil.copytree(SAMPLE, root)
        code, out = run_cli("check", root, "--table")
        line = next(x for x in out.splitlines() if x.startswith("| (성장 없음"))
        self.assertNotIn("| 1 |", line)


class Schema(unittest.TestCase):
    def test_references(self):
        r = validate(data(level_at={"nope": 3}))
        self.assertEqual(codes(r["errors"]), ["unknown_stage"])
        r = validate(data(builds=[{"id": "b", "priority": ["nope"]}]))
        self.assertEqual(codes(r["errors"]), ["unknown_choice"])

    def test_bad_values(self):
        for d in (data(level_at={"s1": 0}), data(offers=0), data(trials=0),
                  data(choices=[{"id": "x", "stats": {}}]), data(choices=[{"id": "x", "stats": {"attack": 1}, "max_picks": 0}]),
                  data(builds=[{"id": "b", "priority": ["vigor"], "pick": "random"}])):
            with self.subTest(d):
                self.assertIn("schema", codes(validate(d)["errors"]))

    def test_level_going_down_is_warned(self):
        r = validate(data(level_at={"s1": 6, "s2": 4}))
        self.assertEqual(codes(r["warnings"]), ["level_decreases"])

    def test_without_combat_data_it_is_unchecked(self):
        r = gr.validate(data(), combat=None, items=None, upgrades=None, enemies=None)
        self.assertEqual(r["errors"], [])
        self.assertGreater(r["unchecked"], 0)


class CommandLine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "game"
        shutil.copytree(SAMPLE, self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_sample_growth_has_no_errors_or_warnings(self):
        code, out = run_cli("check", self.root, "--json")
        r = next(d["report"] for d in json.loads(out)["datasets"] if d["kind"] == "growth")
        self.assertEqual((r["errors"], r["warnings"], r["unchecked"]), ([], [], 0))
        self.assertGreaterEqual(len(r["builds"]), 2)

    def test_growth_file_alone_is_incomplete(self):
        code, out = run_cli("check", self.root / "data/growth.json")
        self.assertIn("INCOMPLETE", out)

    def test_table(self):
        code, out = run_cli("check", self.root, "--table")
        self.assertIn("| 빌드 | 단계 | 레벨 |", out)


if __name__ == "__main__":
    unittest.main()
