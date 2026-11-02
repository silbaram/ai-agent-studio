"""아이템 검증기와 메타 성장 시뮬레이터 테스트. 표준 라이브러리 unittest만 사용한다."""
import copy
import importlib.util
import io
import json
import math
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/progression-economy"


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, SKILL / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


vi = _load("validate_items", "scripts/validate_items.py")
sm = _load("simulate_meta", "scripts/simulate_meta.py")


def item(iid, slot="weapon", tier=1, price=None, **stats):
    d = {"id": iid, "slot": slot, "tier": tier, "stats": stats}
    if price is not None:
        d["price"] = price
    return d


def codes(entries):
    return [e["code"] for e in entries]


class ItemSchema(unittest.TestCase):
    def test_bad_id_duplicate_and_types_are_errors(self):
        r = vi.validate({"items": [
            item("Bad Id"), item("a"), item("a"),
            {"id": "b", "slot": "weapon", "tier": 0, "stats": {}},
            {"id": "c", "slot": "weapon", "tier": 1, "price": -1, "stats": {}},
            {"id": "d", "slot": "weapon", "tier": 1, "stats": {"attack": "high"}},
            {"id": "e", "tier": 1, "stats": {}},
        ]})
        self.assertEqual(codes(r["errors"]).count("schema"), 5)
        self.assertIn("duplicate_id", codes(r["errors"]))
        self.assertEqual(r["items"], 1)

    def test_missing_items_array_is_error(self):
        self.assertIn("schema", codes(vi.validate({})["errors"]))


class ItemBalance(unittest.TestCase):
    def test_tier_inversion_uses_weighted_budget(self):
        data = {"stat_weights": {"speed": 10}, "items": [
            item("t1", tier=1, attack=5, speed=1),   # 15
            item("t2", tier=2, attack=12),           # 12
        ]}
        self.assertIn("tier_inversion", codes(vi.validate(data)["warnings"]))
        data["stat_weights"] = {"speed": 1}         # t1 = 6 < 12
        self.assertNotIn("tier_inversion", codes(vi.validate(data)["warnings"]))

    def test_dominated_item_is_reported(self):
        r = vi.validate({"items": [item("weak", price=50, attack=5), item("strong", price=40, attack=6)]})
        self.assertEqual([(w["code"], w["where"]) for w in r["warnings"]], [("dominated", "weak")])

    def test_tradeoff_is_not_dominated(self):
        r = vi.validate({"items": [item("a", price=50, attack=8), item("b", price=40, attack=6, speed=1)]})
        self.assertNotIn("dominated", codes(r["warnings"]))

    def test_pricier_item_does_not_dominate(self):
        r = vi.validate({"items": [item("cheap", price=10, attack=5), item("pricey", price=50, attack=6)]})
        self.assertNotIn("dominated", codes(r["warnings"]))

    def test_slot_mean_inversion_without_single_item_outlier(self):
        r = vi.validate({"items": [
            item("t1_big", tier=1, attack=10), item("t1_small", tier=1, attack=2),
            item("t2_a", tier=2, attack=5), item("t2_b", tier=2, attack=5),
        ]})
        inversions = [w["where"] for w in r["warnings"] if w["code"] == "tier_inversion"]
        self.assertEqual(inversions, ["weapon"])

    def test_single_item_below_every_lower_tier_item(self):
        r = vi.validate({"items": [
            item("t1_a", tier=1, attack=5), item("t1_b", tier=1, attack=5),
            item("t2_strong", tier=2, attack=20), item("t2_weak", tier=2, attack=3, speed=0.1),
        ]})
        inversions = [w["where"] for w in r["warnings"] if w["code"] == "tier_inversion"]
        self.assertEqual(inversions, ["t2_weak"])

    def test_identical_items_are_not_dominated(self):
        r = vi.validate({"items": [item("a", price=10, attack=5), item("b", price=10, attack=5)]})
        self.assertNotIn("dominated", codes(r["warnings"]))

    def test_higher_tier_does_not_dominate_lower_tier(self):
        r = vi.validate({"items": [item("low", tier=1, price=10, attack=5), item("high", tier=2, price=10, attack=9)]})
        self.assertNotIn("dominated", codes(r["warnings"]))

    def test_other_slot_is_not_compared(self):
        r = vi.validate({"items": [item("a", slot="weapon", attack=5), item("b", slot="armor", attack=9)]})
        self.assertNotIn("dominated", codes(r["warnings"]))

    def test_unique_effect_items_are_not_assessed(self):
        weak = item("charm", price=50, attack=1)
        weak["unique_effect"] = True
        r = vi.validate({"items": [weak, item("blade", price=10, attack=9)]})
        self.assertNotIn("dominated", codes(r["warnings"]))
        self.assertEqual(r["dominance_not_assessed"], ["charm"])


class DropTables(unittest.TestCase):
    def test_capped_expected_draws_matches_closed_form(self):
        self.assertAlmostEqual(vi.capped_expected_draws(0.05, 30), (1 - 0.95 ** 30) / 0.05)
        self.assertAlmostEqual(vi.capped_expected_draws(0.05, None), 20.0)
        self.assertAlmostEqual(vi.capped_expected_draws(1.0, 10), 1.0)
        self.assertEqual(vi.capped_expected_draws(0.0, 10), 10.0)

    def test_probabilities_and_pity(self):
        r = vi.validate({"items": [], "drop_tables": {"t": {
            "entries": [{"rarity": "common", "weight": 3}, {"rarity": "rare", "weight": 1}],
            "pity": {"target_rarity": "rare", "guarantee_after": 4},
        }}})
        t = r["drop_tables"]["t"]
        self.assertEqual(t["rarity_probability"], {"common": 0.75, "rare": 0.25})
        self.assertAlmostEqual(t["pity"]["expected_draws_with_pity"], round((1 - 0.75 ** 4) / 0.25, 4))
        self.assertAlmostEqual(t["pity"]["probability_pity_triggers"], round(0.75 ** 3, 6))

    def test_item_entries_use_item_rarity(self):
        a = item("a"); a["rarity"] = "rare"
        r = vi.validate({"items": [a], "drop_tables": {"t": {"entries": [{"item": "a", "weight": 1}]}}})
        self.assertEqual(r["drop_tables"]["t"]["rarity_probability"], {"rare": 1.0})

    def test_bad_entries_are_errors(self):
        r = vi.validate({"items": [], "drop_tables": {"t": {"entries": [
            {"item": "ghost", "weight": 1}, {"rarity": "x", "weight": 0}, {"weight": 1},
        ]}}})
        self.assertEqual(sorted(codes(r["errors"])), ["schema", "schema", "unknown_item"])

    def test_missing_pity_target_warns(self):
        r = vi.validate({"items": [], "drop_tables": {"t": {
            "entries": [{"rarity": "common", "weight": 1}],
            "pity": {"target_rarity": "legendary", "guarantee_after": 10},
        }}})
        self.assertIn("pity_target_missing", codes(r["warnings"]))


class ItemCli(unittest.TestCase):
    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = vi.main(list(args))
        return code, out.getvalue()

    def test_sample_passes(self):
        self.assertEqual(self.run_cli(str(SKILL / "assets/sample-items.json"))[0], 0)

    def test_csv_and_strict(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "items.csv"
            path.write_text(
                "id,slot,tier,price,stat.attack,unique_effect\n"
                "weak,weapon,1,50,5,\nstrong,weapon,1,40,6,\n", encoding="utf-8")
            self.assertEqual(self.run_cli(str(path))[0], 0)
            code, out = self.run_cli(str(path), "--strict")
            self.assertEqual(code, 1)
            self.assertIn("dominated", out)
            report = Path(tmp) / "out" / "report.json"
            self.run_cli(str(path), "--out", str(report))
            self.assertEqual(json.loads(report.read_text(encoding="utf-8"))["items"], 2)

    def test_unreadable_input_is_usage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.json"
            bad.write_text("{not json", encoding="utf-8")
            self.assertEqual(self.run_cli(str(bad))[0], 2)


BASE = json.loads((SKILL / "assets/sample-meta.json").read_text(encoding="utf-8"))


def cfg(**changes):
    c = copy.deepcopy(BASE)
    c.update({"trials": 40, "max_runs": 30})
    for k, v in changes.items():
        c[k] = v
    return c


class MetaConfig(unittest.TestCase):
    def test_sample_is_valid(self):
        sm.normalize(copy.deepcopy(BASE))

    def assertConfigError(self, c):
        with self.assertRaises(sm.ConfigError):
            sm.normalize(c)

    def test_rejects_bad_values(self):
        self.assertConfigError(cfg(rooms=0))
        self.assertConfigError(cfg(purchase_policy="random"))
        self.assertConfigError(cfg(difficulty={"growth": "cubic", "base": 1, "rate": 1}))
        self.assertConfigError(cfg(survival={"slope": 1, "floor": 0.9, "ceiling": 0.5}))
        self.assertConfigError(cfg(milestones=[{"id": "m", "clear_room": 999}]))
        self.assertConfigError(cfg(upgrades=[{"id": "a", "cost": 1, "requires": ["missing"]}]))
        self.assertConfigError(cfg(upgrades=[{"id": "a", "cost": 1}, {"id": "a", "cost": 2}]))

    def test_rejects_requirement_cycle(self):
        self.assertConfigError(cfg(upgrades=[
            {"id": "a", "cost": 1, "requires": ["b"]},
            {"id": "b", "cost": 1, "requires": ["a"]},
        ]))


class MetaModel(unittest.TestCase):
    def test_difficulty_growth(self):
        lin = sm.normalize(cfg(difficulty={"growth": "linear", "base": 10, "rate": 2}))
        exp = sm.normalize(cfg(difficulty={"growth": "exponential", "base": 10, "rate": 0.1}))
        self.assertEqual(sm.difficulty(lin, 3), 14)
        self.assertAlmostEqual(sm.difficulty(exp, 3), 12.1)

    def test_survival_is_clamped(self):
        c = sm.normalize(cfg(survival={"slope": 1, "floor": 0.2, "ceiling": 0.9}))
        self.assertEqual(sm.survival_probability(c, 1000, 1, 0), 0.9)
        self.assertEqual(sm.survival_probability(c, -1000, 1, 0), 0.2)

    def test_same_seed_is_deterministic_and_seed_matters(self):
        a = sm.simulate(sm.normalize(cfg()))
        b = sm.simulate(sm.normalize(cfg()))
        c = sm.simulate(sm.normalize(cfg(seed=8)))
        self.assertEqual(a, b)
        self.assertNotEqual(a["curve"], c["curve"])

    def test_certain_survival_reaches_everything_on_first_run(self):
        r = sm.simulate(sm.normalize(cfg(survival={"slope": 1, "floor": 1.0, "ceiling": 1.0})))
        for d in r["milestones"].values():
            self.assertEqual((d["reached_fraction"], d["median"]), (1.0, 1))

    def test_impossible_run_reports_not_reached(self):
        r = sm.simulate(sm.normalize(cfg(survival={"slope": 1, "floor": 0.0, "ceiling": 0.0})))
        d = r["milestones"]["boss_1"]
        self.assertEqual(d["reached_fraction"], 0.0)
        self.assertIsNone(d["median"])
        self.assertIsNone(r["upgrades"]["vitality_1"]["median"])

    def test_currency_accounting_on_full_clear(self):
        c = sm.normalize(cfg(survival={"slope": 1, "floor": 1.0, "ceiling": 1.0}))
        depth, earned = sm.play_run(c, sm.random.Random(0), 0.0, 0.0)
        self.assertEqual(depth, 30)
        self.assertEqual(earned, 2 * 30 + 15 + 30 + 60)

    def test_keep_on_death_scales_earnings(self):
        c = sm.normalize(cfg(survival={"slope": 1, "floor": 0.0, "ceiling": 0.0}))
        self.assertEqual(sm.play_run(c, sm.random.Random(0), 0.0, 0.0), (0, 0.0))
        c = sm.normalize(cfg(rooms=5, milestones=[], currency={"per_room": 10, "keep_on_death": 0.5},
                             survival={"slope": 1, "floor": 1.0, "ceiling": 1.0}))
        self.assertEqual(sm.play_run(c, sm.random.Random(0), 0.0, 0.0), (5, 50.0))

    def test_keep_on_death_applies_when_run_ends_early(self):
        # 방 1·2는 확실히 통과, 방 3에서 확실히 사망하도록 난이도를 급격히 올린다.
        c = sm.normalize(cfg(rooms=5, milestones=[], currency={"per_room": 10, "keep_on_death": 0.5},
                             difficulty={"growth": "linear", "base": 0, "rate": 100},
                             player={"base_power": 150, "power_per_room": 0},
                             survival={"slope": 10, "floor": 0.0, "ceiling": 1.0}))
        self.assertEqual(sm.play_run(c, sm.random.Random(0), 0.0, 0.0), (2, 10.0))

    def test_listed_order_saves_for_next_item(self):
        c = sm.normalize(cfg(purchase_policy="listed_order", upgrades=[
            {"id": "expensive", "cost": 100}, {"id": "cheap", "cost": 5}]))
        bank, bought = sm.buy(c, 50.0, set())
        self.assertEqual((bank, bought), (50.0, []))

    def test_cheapest_first_respects_requirements(self):
        c = sm.normalize(cfg(purchase_policy="cheapest_first", upgrades=[
            {"id": "base", "cost": 30}, {"id": "cheap_child", "cost": 5, "requires": ["base"]},
            {"id": "other", "cost": 10}]))
        bank, bought = sm.buy(c, 45.0, set())
        self.assertEqual(bought, ["other", "base", "cheap_child"])
        self.assertEqual(bank, 0.0)

    def test_stall_ignores_runs_after_completion(self):
        r = sm.simulate(sm.normalize(cfg(survival={"slope": 1, "floor": 1.0, "ceiling": 1.0},
                                         upgrades=[{"id": "a", "cost": 1}])))
        self.assertEqual(r["longest_stall_runs"]["max"], 0)

    def test_percentile_with_unreached(self):
        self.assertEqual(sm.percentile([1, 2, 3, math.inf], 50), 2)
        self.assertIsNone(sm.percentile([1, math.inf, math.inf, math.inf], 50))


class MetaCli(unittest.TestCase):
    def test_writes_outputs_and_rejects_bad_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            conf = Path(tmp) / "meta.json"
            conf.write_text(json.dumps(cfg()), encoding="utf-8")
            out, curve = Path(tmp) / "r/out.json", Path(tmp) / "r/curve.csv"
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(sm.main([str(conf), "--out", str(out), "--csv", str(curve)]), 0)
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertIn("abstract model", data["evidence"])
            self.assertEqual(len(data["config_sha256"]), 64)
            self.assertEqual(len(curve.read_text(encoding="utf-8").strip().splitlines()), 31)
            self.assertIn(f"[계산: {out}]", buf.getvalue())
            conf.write_text(json.dumps(cfg(rooms=0)), encoding="utf-8")
            with redirect_stderr(io.StringIO()):
                self.assertEqual(sm.main([str(conf)]), 2)


if __name__ == "__main__":
    unittest.main()
