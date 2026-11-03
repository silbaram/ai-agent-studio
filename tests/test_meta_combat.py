"""메타 성장 시뮬레이터의 전투 계산 모델(B5b) 테스트: 단계 여유, 생존 확률, 영구 강화·판 안 성장·재화 흐름 연결.
표준 라이브러리 unittest만 사용한다."""
import json
import math
import shutil
import tempfile
import unittest
from pathlib import Path

from _studio import SAMPLE, common, economy as ec, meta_sim as sm, run_cli

CONFIG = "data/meta_combat.json"


def row(htk, ttk, htd, ttd):
    return {"hits_to_kill": htk, "time_to_kill": ttk, "hits_to_die": htd, "time_to_die": ttd}


class Margin(unittest.TestCase):
    def test_hardest_enemy_sets_the_stage_margin(self):
        rows = [row(5, 5.0, 10, 5.0), row(2, 2.0, 10, 10.0)]
        self.assertEqual(sm.stage_margin(rows), 1.0)            # 첫째 적: 5초에 잡고 5초 버팀
        self.assertEqual(sm.stage_margin(rows[::-1]), 1.0)

    def test_hits_are_used_when_there_are_no_attack_rates(self):
        self.assertEqual(sm.stage_margin([row(4, None, 8, None)]), 2.0)

    def test_zero_damage_and_untouchable(self):
        self.assertEqual(sm.stage_margin([row(None, None, 8, 8.0)]), 0.0)
        self.assertEqual(sm.stage_margin([row(4, 4.0, None, None)]), math.inf)


class Survival(unittest.TestCase):
    CFG = {"survival": {"slope": 2.0, "floor": 0.05, "ceiling": 0.95}}

    def test_even_fight_is_a_coin_flip_moved_by_skill(self):
        cfg = {"survival": {"slope": 2.0, "floor": 0.0, "ceiling": 1.0}}
        self.assertAlmostEqual(sm.combat_survival(cfg, 1.0, 0.0), 0.5)
        self.assertAlmostEqual(sm.combat_survival(cfg, math.e, 0.0), 1 / (1 + math.exp(-2)))
        self.assertGreater(sm.combat_survival(cfg, 1.0, 1.0), 0.5)

    def test_bounds(self):
        self.assertEqual(sm.combat_survival(self.CFG, 0.0, 0.0), 0.05)
        self.assertEqual(sm.combat_survival(self.CFG, math.inf, 0.0), 0.95)


class Workspace(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "game"
        shutil.copytree(SAMPLE, self.root)
        self.config = self.root / CONFIG
        self.edit(CONFIG, lambda d: d.update(trials=80, max_runs=25))  # 같은 것을 확인하는 데 샘플의 200 × 40판은 필요 없다

    def tearDown(self):
        self.tmp.cleanup()

    def edit(self, rel, fn):
        p = self.root / rel
        d = json.loads(p.read_text(encoding="utf-8"))
        fn(d)
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")

    def run_cfg(self, **over):
        self.edit(CONFIG, lambda d: d.update(over))
        return sm.run_config(self.config)


class Config(Workspace):
    def test_combat_model_needs_its_files_and_no_rooms(self):
        for change in ({"combat_file": None}, {"rooms": 10}, {"build": None}, {"survival": {"floor": 0}}):
            with self.subTest(change):
                raw = json.loads(self.config.read_text(encoding="utf-8"))
                for k, v in change.items():
                    raw.pop(k) if v is None else raw.__setitem__(k, v)
                with self.assertRaises(sm.ConfigError):
                    sm.normalize(raw, self.config.parent)

    def test_economy_policy_needs_the_economy_link(self):
        raw = json.loads(self.config.read_text(encoding="utf-8"))
        raw.pop("economy")
        raw["currency"] = {"per_stage": {"zone_1": 1}}
        with self.assertRaisesRegex(sm.ConfigError, "economy"):
            sm.normalize(raw, self.config.parent)

    def test_unknown_milestone_stage(self):
        with self.assertRaisesRegex(sm.ConfigError, "zone_9"):
            self.run_cfg(milestones=[{"id": "m", "clear_stage": "zone_9"}])

    def test_broken_combat_data_is_refused(self):
        self.edit("data/combat.json", lambda d: d["stages"][0]["player"].__setitem__("items", ["nope"]))
        with self.assertRaisesRegex(sm.ConfigError, "check"):
            sm.run_config(self.config)

    def test_economy_income_must_be_linked_to_combat_stages(self):
        self.edit("data/economy.json", lambda d: d["stages"][0].pop("combat_stage"))
        with self.assertRaisesRegex(sm.ConfigError, "combat_stage"):
            sm.run_config(self.config)

    def test_upgrades_that_break_combat_stats_are_refused(self):
        self.edit("data/upgrades.json", lambda d: d["upgrades"].append({"id": "lucky", "cost": 1, "stats": {"crit_chance": 2}}))
        with self.assertRaisesRegex(sm.ConfigError, "lucky"):
            self.run_cfg(purchase_policy="cheapest_first")

    def test_broken_upgrade_is_refused_even_if_unplanned_or_unaffordable(self):
        # 전투 계산 검사가 모든 활성 강화를 기준 장비에 더해 보므로, 계획에 없거나 비싸서 닿지 않는 강화도 막는다
        self.edit("data/upgrades.json", lambda d: d["upgrades"].append({"id": "lucky", "cost": 10 ** 9, "stats": {"crit_chance": 2}}))
        for policy in ("economy", "listed_order"):
            with self.subTest(policy), self.assertRaisesRegex(sm.ConfigError, "upgrades:lucky"):
                self.run_cfg(purchase_policy=policy)

    def test_planned_upgrade_set_that_breaks_stats_together_is_refused(self):
        # 하나씩은 괜찮지만 함께 사면 치명 확률이 1을 넘는다(0.6 + 0.6). 전투 계산 검사는 하나씩만 본다
        self.edit("data/upgrades.json", lambda d: d["upgrades"].extend([{"id": "luck_a", "cost": 10 ** 9, "stats": {"crit_chance": 0.6}},
                                                                        {"id": "luck_b", "cost": 10 ** 9, "stats": {"crit_chance": 0.6}}]))
        sm.run_config(self.config)                                   # 재화 흐름 계획에 없으면 사지 않으므로 막지 않는다
        with self.assertRaisesRegex(sm.ConfigError, "crit_chance"):  # 살 수 없을 만큼 비싸도 계획(전부)에 있으면 미리 막는다
            self.run_cfg(purchase_policy="listed_order")

    def test_combat_model_file_is_a_meta_config_not_data(self):
        raw = json.loads(self.config.read_text(encoding="utf-8"))
        self.assertEqual(common.detect_kind(raw), "meta")


class Run(Workspace):
    def test_result_shape(self):
        cfg, r = sm.run_config(self.config)
        self.assertEqual(r["model"], "combat")
        self.assertEqual([s["stage"] for s in r["survival_by_stage"]], ["zone_1", "zone_2", "zone_3"])
        for s in r["survival_by_stage"]:
            self.assertGreaterEqual(s["p_all"], s["p_none"])
        self.assertEqual(r["stage_income"], {"zone_1": 8, "zone_2": 12, "zone_3": 20})
        self.assertEqual(set(r["milestones"]), {"reach_zone_3", "first_clear"})
        self.assertGreater(r["milestones"]["reach_zone_3"]["reached_fraction"], 0)
        self.assertLess(r["milestones"]["reach_zone_3"]["median"], r["milestones"]["first_clear"]["median"])  # 단계 2 < 단계 3

    def test_stage_upgrades_in_combat_data_are_replaced_by_owned_ones(self):
        cfg, a = sm.run_config(self.config)
        self.edit("data/combat.json", lambda d: d["stages"][2]["player"].__setitem__("upgrades", []))
        cfg, b = sm.run_config(self.config)
        self.assertEqual(a["survival_by_stage"], b["survival_by_stage"])
        self.assertEqual(a["milestones"], b["milestones"])

    def test_economy_policy_buys_the_economy_plan_in_order(self):
        cfg, r = sm.run_config(self.config)
        self.assertEqual(cfg["economy_order"], ["weapon_1", "vitality_1", "weapon_2"])
        medians = [r["upgrades"][u]["median"] for u in cfg["economy_order"]]
        self.assertEqual(medians, sorted(medians))
        self.assertEqual(r["upgrades"]["relic_slot"]["reached_fraction"], 0.0)   # 계획에 없는 강화는 사지 않는다
        self.assertGreater(r["all_upgrades_bought"]["reached_fraction"], 0)     # '모두 샀다'는 계획한 강화 기준

    def test_keep_on_death_applies_to_combat_runs(self):
        cfg, keep = sm.run_config(self.config)
        cfg, lose = self.run_cfg(currency={"keep_on_death": 0.0})
        self.assertGreater(lose["upgrades"]["weapon_2"]["median"], keep["upgrades"]["weapon_2"]["median"])

    def test_each_run_draws_its_own_level_ups(self):
        seeds = []
        original = sm.gr.simulate_trials
        sm.gr.simulate_trials = lambda *a: seeds.append(a[-1]) or original(*a)
        self.addCleanup(setattr, sm.gr, "simulate_trials", original)
        self.run_cfg(trials=1, max_runs=5)
        self.assertGreaterEqual(len(set(seeds)), 5)      # 판 다섯 번이 각자 다른 시드로 레벨업을 뽑는다

    def test_upgrades_raise_survival(self):
        cfg, r = sm.run_config(self.config)
        last = r["curve"][-1]
        self.assertGreaterEqual(last["median_upgrades_owned"], 1)
        self.assertGreater(r["survival_by_stage"][2]["margin_all"], r["survival_by_stage"][2]["margin_none"])

    def test_in_run_growth_is_part_of_the_run(self):
        cfg, with_growth = sm.run_config(self.config)
        raw = json.loads(self.config.read_text(encoding="utf-8"))
        raw.pop("growth_file")
        raw.pop("build")
        self.config.write_text(json.dumps(raw), encoding="utf-8")
        cfg, without = sm.run_config(self.config)
        self.assertGreater(with_growth["survival_by_stage"][2]["margin_all"], without["survival_by_stage"][2]["margin_all"])
        # 요약표만이 아니라 판 시뮬레이션에도 레벨업이 들어간다: 첫 클리어가 빨라진다
        self.assertLess(with_growth["milestones"]["first_clear"]["median"], without["milestones"]["first_clear"]["median"])

    def test_upgrades_without_combat_effect_are_listed(self):
        cfg, r = sm.run_config(self.config)
        self.assertIn("relic_slot", r["upgrades_without_combat_effect"])
        self.assertNotIn("weapon_1", r["upgrades_without_combat_effect"])

    def test_same_seed_same_result(self):
        self.assertEqual(sm.run_config(self.config)[1], sm.run_config(self.config)[1])

    def test_per_stage_income_without_economy(self):
        cfg, r = self.run_cfg(economy=None, purchase_policy="listed_order", currency={"per_stage": {"zone_1": 30, "zone_3": 50}})
        self.assertEqual(r["stage_income"], {"zone_1": 30, "zone_2": 0, "zone_3": 50})


class CommandLine(Workspace):
    def test_simulate_prints_the_stage_survival(self):
        out_csv = self.root / "reports/c.csv"
        code, out = run_cli("simulate", self.config, "--csv", out_csv)
        self.assertEqual(code, 0)
        self.assertIn("전투 계산", out)
        self.assertIn("단계 zone_1", out)
        self.assertIn("median_upgrades_owned", out_csv.read_text(encoding="utf-8").splitlines()[0])

    def test_policy_override_and_comparison_include_the_economy_plan(self):
        code, out = run_cli("simulate", self.config, "--policy", "cheapest_first", "--json")
        self.assertEqual(json.loads(out)["purchase_policy"], "cheapest_first")
        code, out = run_cli("simulate", self.config, "--compare-policies", "--json")
        self.assertEqual(sorted(json.loads(out)["results"]), ["cheapest_first", "economy", "listed_order"])

    def test_abstract_config_cannot_use_the_economy_policy(self):
        code, _ = run_cli("simulate", self.root / "data/meta.json", "--policy", "economy")
        self.assertEqual(code, 2)


class EconomyLink(Workspace):
    def test_economy_linked_to_a_combat_model_config_is_quiet(self):
        self.edit("data/economy.json", lambda d: d["economy"]["currencies"]["soul"].__setitem__("meta_config", "meta_combat.json"))
        code, out = run_cli("check", self.root, "--json")
        r = next(d["report"] for d in json.loads(out)["datasets"] if d["kind"] == "economy")
        self.assertEqual((r["errors"], r["warnings"]), ([], []))

    def test_abstract_config_linked_for_order_still_compares_income(self):
        cfg = sm.normalize({"seed": 1, "trials": 1, "max_runs": 1, "rooms": 2, "difficulty": {"base": 1, "rate": 1},
                            "player": {"base_power": 1}, "survival": {"slope": 1}, "currency": {"per_room": 50},
                            "economy": {"file": "economy.json", "currency": "soul"}, "purchase_policy": "economy", "upgrades": []})
        d = {"economy": {"currencies": {"soul": {"carry": True, "meta_config": "meta.json"}}},
             "stages": [{"id": "s1", "duration": 1, "income": {"soul": 5}}], "purchases": []}
        self.assertEqual([w["code"] for w in ec.validate(d, meta={"soul": cfg})["warnings"]], ["meta_income_differs"])

    def test_per_stage_income_is_compared_with_the_economy(self):
        cfg = sm.normalize({"model": "combat", "seed": 1, "trials": 1, "max_runs": 1, "combat_file": "combat.json",
                            "survival": {"slope": 1}, "currency": {"per_stage": {"s1": 99}},
                            "upgrades": [{"id": "w1", "cost": 25}, {"id": "w2", "cost": 10}]})
        d = {"economy": {"currencies": {"gold": {}, "soul": {"carry": True, "meta_config": "meta.json"}}, "prices": {"upgrades": "soul"}},
             "stages": [{"id": "s1", "duration": 1, "income": {"soul": 5}}], "purchases": []}
        r = ec.validate(d, upgrades={"w1": {"id": "w1", "cost": 25}, "w2": {"id": "w2", "cost": 10}}, meta={"soul": cfg})
        self.assertEqual([w["code"] for w in r["warnings"]], ["meta_income_differs"])


class ReviewFindings(Workspace):
    """B5b 코드 검토에서 나온 문제의 회귀 테스트."""

    def test_abstract_model_can_follow_the_economy_plan_without_stage_links(self):
        self.edit("data/economy.json", lambda d: [s.pop("combat_stage") for s in d["stages"]])
        self.edit("data/meta.json", lambda d: d.update(economy={"file": "economy.json", "currency": "soul"}, purchase_policy="economy",
                                                        trials=40, max_runs=30))
        cfg, r = sm.run_config(self.root / "data/meta.json")
        self.assertEqual(cfg["economy_order"], ["weapon_1", "vitality_1", "weapon_2"])
        self.assertEqual(r["upgrades"]["relic_slot"]["reached_fraction"], 0.0)

    def test_missing_data_for_another_currency_does_not_block(self):
        (self.root / "data/crafting.json").unlink()               # 골드로 사는 강화·합성만 미확인
        cfg, r = sm.run_config(self.config)
        self.assertEqual(r["model"], "combat")

    def test_missing_data_for_the_linked_currency_still_blocks(self):
        (self.root / "data/crafting.json").unlink()
        self.edit("data/economy.json", lambda d: d["economy"]["prices"].__setitem__("recipes", "soul"))   # 합성 가격이 soul로 바뀜
        with self.assertRaisesRegex(sm.ConfigError, "soul"):
            sm.run_config(self.config)

    def test_economy_reports_which_currencies_are_unchecked(self):
        (self.root / "data/crafting.json").unlink()
        code, out = run_cli("check", self.root, "--json")
        r = next(d["report"] for d in json.loads(out)["datasets"] if d["kind"] == "economy")
        self.assertEqual(r["unchecked_currencies"], ["gold"])

    def test_bad_growth_draw_names_the_picks_that_broke_the_stats(self):
        self.edit("data/upgrades.json", lambda d: d["upgrades"].append({"id": "lucky", "cost": 1, "stats": {"crit_chance": 0.9}}))
        with self.assertRaisesRegex(sm.ConfigError, "focus"):
            self.run_cfg(build="blade", purchase_policy="cheapest_first")

    def test_compare_policies_simulates_each_policy_once(self):
        calls = []
        original = sm.simulate
        sm.simulate = lambda cfg: calls.append(cfg["purchase_policy"]) or original(cfg)
        self.addCleanup(setattr, sm, "simulate", original)
        run_cli("simulate", self.config, "--compare-policies", "--json")
        self.assertEqual(sorted(calls), ["cheapest_first", "economy", "listed_order"])

    def test_attach_does_not_change_the_given_config(self):
        cfg = sm.normalize(json.loads(self.config.read_text(encoding="utf-8")), self.config.parent)
        sm.attach(cfg, self.config.parent)
        self.assertNotIn("clear_room", cfg["milestones"][0])


if __name__ == "__main__":
    unittest.main()
