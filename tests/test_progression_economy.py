"""아이템 검증기와 메타 성장 시뮬레이터 테스트. 표준 라이브러리 unittest만 사용한다."""
import copy
import io
import json
import math
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

from _studio import SAMPLE, common, enemies as ve, items as vi, meta_sim as sm, run_cli as studio_cli, upgrades as vu, viewer

DATA = SAMPLE / "data"


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
        self.assertEqual(r["count"], 1)

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


class ItemMetadata(unittest.TestCase):
    def test_status_and_provenance_are_validated(self):
        bad_status = item("a"); bad_status["status"] = "maybe"
        bad_kind = item("b"); bad_kind["provenance"] = {"kind": "guess"}
        no_source = item("c"); no_source["provenance"] = {"kind": "measured"}
        bad_name = item("d"); bad_name["name"] = 3
        r = vi.validate({"items": [bad_status, bad_kind, no_source, bad_name]})
        self.assertEqual(sorted(codes(r["errors"])), ["provenance", "provenance", "schema", "schema"])
        self.assertEqual(r["count"], 0)

    def test_korean_provenance_aliases(self):
        a = item("a"); a["provenance"] = {"kind": "계산", "source": "sim/a.json"}
        r = vi.validate({"items": [a]})
        self.assertEqual(r["errors"], [])
        self.assertEqual(r["provenance_counts"]["computed"], 1)

    def test_cut_items_are_excluded_from_comparisons(self):
        weak = item("weak", price=50, attack=5); weak["status"] = "cut"
        low = item("low_t2", tier=2, attack=1); low["status"] = "cut"
        r = vi.validate({"items": [weak, low, item("strong", price=40, attack=6)]})
        self.assertEqual(r["warnings"], [])
        self.assertEqual(r["status_counts"]["cut"], 2)

    def test_dropping_a_cut_item_warns(self):
        gone = item("gone"); gone["status"] = "cut"; gone["rarity"] = "rare"
        r = vi.validate({"items": [gone], "drop_tables": {"t": {"entries": [{"item": "gone", "weight": 1}]}}})
        self.assertEqual([(w["code"], w["where"]) for w in r["warnings"]], [("cut_item_referenced", "t")])

    def test_unverified_items_exclude_cut_and_verified(self):
        a = item("a"); a["provenance"] = {"kind": "assumed"}
        b = item("b", attack=1); b["provenance"] = {"kind": "measured", "source": "playtest-1"}
        c = item("c", attack=2)
        d = item("d", attack=3); d["status"] = "cut"
        r = vi.validate({"items": [a, b, c, d]})
        self.assertEqual(r["unverified"], ["a", "c"])
        self.assertEqual(r["provenance_counts"], {"assumed": 1, "computed": 0, "measured": 1, "unspecified": 1})


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
        return studio_cli("check", *args)

    def test_sample_passes(self):
        self.assertEqual(self.run_cli(str(DATA / "items.json"))[0], 0)

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
            self.assertEqual(json.loads(report.read_text(encoding="utf-8"))["datasets"][0]["report"]["count"], 2)

    def test_fail_on_assumed_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "items.json"
            a = item("a"); a["provenance"] = {"kind": "assumed"}
            path.write_text(json.dumps({"items": [a]}), encoding="utf-8")
            self.assertEqual(self.run_cli(str(path))[0], 0)
            code, out = self.run_cli(str(path), "--fail-on-assumed")
            self.assertEqual(code, 1)
            self.assertIn("gate", out)
            a["provenance"] = {"kind": "computed", "source": "sim/x.json"}
            path.write_text(json.dumps({"items": [a]}), encoding="utf-8")
            self.assertEqual(self.run_cli(str(path), "--fail-on-assumed")[0], 0)

    def test_csv_metadata_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "items.csv"
            path.write_text(
                "id,name,slot,tier,status,provenance_kind,provenance_source,stat.attack\n"
                "axe,도끼,weapon,1,proposed,measured,playtest-2,5\n", encoding="utf-8")
            data = vi.load(path)
            self.assertEqual(data["items"][0]["provenance"], {"kind": "measured", "source": "playtest-2"})
            r = vi.validate(data)
            self.assertEqual((r["errors"], r["status_counts"]["proposed"]), ([], 1))

    def test_unreadable_input_is_usage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.json"
            bad.write_text("{not json", encoding="utf-8")
            self.assertEqual(self.run_cli(str(bad))[0], 2)


BASE = json.loads((DATA / "meta.json").read_text(encoding="utf-8"))
BASE["upgrades_file"] = str(DATA / BASE["upgrades_file"])


def cfg(**changes):
    c = copy.deepcopy(BASE)
    c.update({"trials": 40, "max_runs": 30})
    if "upgrades" in changes:
        c.pop("upgrades_file", None)
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
            code, printed = studio_cli("simulate", conf, "--out", out, "--csv", curve)
            self.assertEqual(code, 0)
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertIn("abstract model", data["evidence"])
            self.assertEqual(len(data["config_sha256"]), 64)
            self.assertEqual(len(curve.read_text(encoding="utf-8").strip().splitlines()), 31)
            self.assertIn(f"[계산: {out}]", printed)
            conf.write_text(json.dumps(cfg(rooms=0)), encoding="utf-8")
            with redirect_stderr(io.StringIO()):
                self.assertEqual(studio_cli("simulate", conf)[0], 2)


def upgrade(uid, cost, power=1.0, requires=None, **extra):
    d = {"id": uid, "cost": cost, "power": power}
    if requires is not None:
        d["requires"] = requires
    d.update(extra)
    return d


def enemy(eid, rank="normal", zone=1, **stats):
    return {"id": eid, "rank": rank, "zone": zone, "stats": stats}


class Upgrades(unittest.TestCase):
    def test_sample_passes(self):
        r = vu.validate(vu.load(DATA / "upgrades.json"))
        self.assertEqual((r["errors"], r["warnings"]), ([], []))
        self.assertEqual(r["status_counts"]["cut"], 1)

    def test_schema_errors(self):
        r = vu.validate({"upgrades": [
            {"id": "a", "cost": -1}, {"id": "b", "cost": 1, "power": "big"},
            {"id": "c", "cost": 1, "requires": "a"}, {"id": "d", "cost": 1, "level": 1.5},
            {"id": "e"},
        ]})
        self.assertEqual(codes(r["errors"]), ["schema"] * 5)

    def test_missing_requires_field_is_fine(self):
        r = vu.validate({"upgrades": [upgrade("a", 1)]})
        self.assertEqual(r["errors"], [])
        self.assertEqual(r["depth"], {"a": 0})

    def test_unknown_requirement_and_cycle(self):
        r = vu.validate({"upgrades": [upgrade("a", 1, requires=["ghost"])]})
        self.assertEqual(codes(r["errors"]), ["unknown_requirement"])
        r = vu.validate({"upgrades": [upgrade("a", 1, requires=["b"]), upgrade("b", 2, requires=["a"])]})
        self.assertIn("requirement_cycle", codes(r["errors"]))
        self.assertEqual(r["depth"], {})

    def test_requires_cut_is_error(self):
        gone = upgrade("base", 10, status="cut")
        r = vu.validate({"upgrades": [gone, upgrade("child", 20, requires=["base"])]})
        self.assertEqual(codes(r["errors"]), ["requires_cut"])

    def test_cost_inversion_and_missing_power_warn(self):
        r = vu.validate({"upgrades": [upgrade("a", 50), {"id": "b", "cost": 20, "requires": ["a"]}]})
        self.assertEqual(sorted((w["code"], w["where"]) for w in r["warnings"]),
                         [("cost_inversion", "b"), ("power_missing", "b")])

    def test_totals_tracks_depth_and_efficiency_exclude_cut(self):
        r = vu.validate({"upgrades": [
            upgrade("a", 10, 2, track="hp"), upgrade("b", 30, 3, requires=["a"], track="hp"),
            upgrade("c", 99, 9, track="hp", status="cut"),
        ]})
        self.assertEqual(r["totals"], {"active": 2, "cost": 40, "power": 5})
        self.assertEqual(r["tracks"]["hp"]["count"], 2)
        self.assertEqual(r["depth"], {"a": 0, "b": 1, "c": 0})
        self.assertEqual(r["efficiency"]["a"], 0.2)

    def test_csv_requires_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "upgrades.csv"
            path.write_text("id,cost,power,requires,status\na,10,1,,approved\nb,20,2,a;c,proposed\nc,5,1,,\n", encoding="utf-8")
            data = vu.load(path)
            self.assertEqual(data["upgrades"][1]["requires"], ["a", "c"])
            r = vu.validate(data)
            self.assertEqual([(w["code"], w["where"]) for w in r["warnings"]], [])

    def test_cli_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "u.json"
            path.write_text(json.dumps({"upgrades": [upgrade("a", 1, provenance={"kind": "assumed"})]}), encoding="utf-8")
            self.assertEqual(studio_cli("check", path)[0], 0)
            self.assertEqual(studio_cli("check", path, "--fail-on-assumed")[0], 1)
            path.write_text(json.dumps({"notes": "강화 메모"}), encoding="utf-8")
            self.assertEqual(studio_cli("check", path)[0], 2)


class Enemies(unittest.TestCase):
    def test_sample_passes_with_items(self):
        items = vi.load(DATA / "items.json")
        r = ve.validate(ve.load(DATA / "enemies.json"), items["drop_tables"])
        self.assertEqual((r["errors"], r["warnings"]), ([], []))
        self.assertEqual(r["drop_table_not_checked"], [])

    def test_schema_errors(self):
        r = ve.validate({"enemies": [
            {"id": "a", "rank": "miniboss", "zone": 1, "stats": {}}, {"id": "b", "rank": "normal", "zone": 0, "stats": {}},
            {"id": "c", "rank": "normal", "zone": 1, "reward": -1}, {"id": "d", "rank": "normal", "zone": 1, "drop_table": 3},
        ]})
        self.assertEqual(codes(r["errors"]), ["schema"] * 4)

    def test_threat_uses_weights(self):
        r = ve.validate({"threat_weights": {"hp": 0.1}, "enemies": [enemy("a", hp=50, damage=3)]})
        self.assertEqual(r["scores"]["a"], 8.0)

    def test_zone_inversion(self):
        r = ve.validate({"enemies": [enemy("a", zone=1, damage=10), enemy("b", zone=2, damage=5)]})
        self.assertEqual([(w["code"], w["where"]) for w in r["warnings"]], [("zone_inversion", "zone_2")])

    def test_rank_inversion_including_ties(self):
        r = ve.validate({"enemies": [enemy("n", "normal", damage=10), enemy("e", "elite", damage=10), enemy("b", "boss", damage=30)]})
        self.assertEqual([(w["code"], w["where"]) for w in r["warnings"]], [("rank_inversion", "zone_1")])

    def test_cut_enemies_are_ignored(self):
        weak_boss = enemy("b", "boss", damage=1); weak_boss["status"] = "cut"
        weak_boss["drop_table"] = "nowhere"
        r = ve.validate({"enemies": [enemy("n", damage=10), weak_boss]}, {})
        self.assertEqual((r["errors"], r["warnings"]), ([], []))

    def test_drop_table_reference(self):
        e = enemy("a", damage=1); e["drop_table"] = "chest"
        self.assertEqual(ve.validate({"enemies": [e]})["drop_table_not_checked"], ["a"])
        self.assertEqual(codes(ve.validate({"enemies": [e]}, {"other": {}})["errors"]), ["unknown_drop_table"])
        self.assertEqual(ve.validate({"enemies": [e]}, {"chest": {}})["errors"], [])

    def test_cli_with_items_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            e = enemy("a", damage=1); e["drop_table"] = "chest"
            ep, ip = Path(tmp) / "enemies.json", Path(tmp) / "items.json"
            ep.write_text(json.dumps({"enemies": [e]}), encoding="utf-8")
            ip.write_text(json.dumps({"items": [], "drop_tables": {"other": {"entries": [{"rarity": "x", "weight": 1}]}}}), encoding="utf-8")
            self.assertEqual(studio_cli("check", ep)[0], 0)
            self.assertEqual(studio_cli("check", ep, ip)[0], 1)


class CommonLoading(unittest.TestCase):
    def test_kind_detection(self):
        self.assertEqual(common.detect_kind({"rooms": 3, "difficulty": {}, "upgrades": []}, Path("x.json")), "meta")
        self.assertEqual(common.detect_kind({"enemies": []}, Path("x.json")), "enemies")
        self.assertIsNone(common.detect_kind({"foo": 1}, Path("x.json")))
        self.assertEqual(common.kind_from_filename(Path("Boss_Enemies.csv")), "enemies")

    def test_csv_without_kind_hint_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.csv"
            path.write_text("id\na\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                common.load_dataset(path)


class MetaUpgradesFile(unittest.TestCase):
    def test_sample_meta_reads_upgrades_file_and_skips_cut(self):
        c = sm.normalize(json.loads((DATA / "meta.json").read_text(encoding="utf-8")), DATA)
        ids = [u["id"] for u in c["upgrades"]]
        self.assertNotIn("lucky_start", ids)
        self.assertEqual(ids, ["vitality_1", "weapon_1", "vitality_2", "weapon_2", "relic_slot", "weapon_3"])
        self.assertEqual(len(c["upgrades_file"]["sha256"]), 64)

    def test_file_and_inline_give_identical_results(self):
        data = vu.load(DATA / "upgrades.json")
        inline = [{"id": u["id"], "cost": u["cost"], "power": u["power"], "requires": u.get("requires", [])}
                  for u in data["upgrades"] if u.get("status") != "cut"]
        a = sm.simulate(sm.normalize(cfg()))
        b = sm.simulate(sm.normalize(cfg(upgrades=inline)))
        self.assertEqual(a["milestones"], b["milestones"])
        self.assertEqual(a["upgrades"], b["upgrades"])

    def test_upgrades_file_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            both = cfg(); both["upgrades"] = []
            with self.assertRaises(sm.ConfigError):
                sm.normalize(both)
            with self.assertRaises(sm.ConfigError):
                sm.normalize(cfg(upgrades_file=str(d / "missing.json")))
            (d / "bad.json").write_text(json.dumps({"upgrades": [upgrade("a", 1, requires=["ghost"])]}), encoding="utf-8")
            with self.assertRaises(sm.ConfigError):
                sm.normalize(cfg(upgrades_file="bad.json"), d)
            # 시뮬레이터 자체 검사로는 잡히지 않는 데이터 오류도 거부해야 한다 (측정인데 근거 없음).
            (d / "unsourced.json").write_text(json.dumps({"upgrades": [upgrade("a", 1, provenance={"kind": "measured"})]}), encoding="utf-8")
            with self.assertRaisesRegex(sm.ConfigError, "오류"):
                sm.normalize(cfg(upgrades_file="unsourced.json"), d)
            (d / "nopower.json").write_text(json.dumps({"upgrades": [{"id": "a", "cost": 1}]}), encoding="utf-8")
            with self.assertRaisesRegex(sm.ConfigError, "power"):
                sm.normalize(cfg(upgrades_file="nopower.json"), d)
            (d / "ok.json").write_text(json.dumps({"upgrades": [upgrade("a", 1)]}), encoding="utf-8")
            self.assertEqual([u["id"] for u in sm.normalize(cfg(upgrades_file="ok.json"), d)["upgrades"]], ["a"])


class Viewer(unittest.TestCase):
    def setUp(self):
        import threading
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.write("items.json", {"items": [item("a", attack=1)], "drop_tables": {"chest": {"entries": [{"rarity": "x", "weight": 1}]}}})
        self.write("upgrades.json", {"upgrades": [upgrade("u1", 10)]})
        self.write("enemies.json", {"enemies": [dict(enemy("e1", damage=1), drop_table="chest")]})
        self.write("meta.json", {"rooms": 3, "difficulty": {"base": 1, "rate": 1}, "upgrades_file": "upgrades.json"})
        self.write("notes.json", {"hello": "world"})
        self.server = viewer.make_server([self.dir], port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:%d" % self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def write(self, name, data):
        (self.dir / name).write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")

    def get(self, route):
        import urllib.error
        import urllib.request
        try:
            with urllib.request.urlopen(self.base + route, timeout=5) as res:
                return res.status, res.headers.get("Content-Type"), res.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.headers.get("Content-Type"), exc.read()

    def api(self):
        status, ctype, body = self.get("/api/data")
        self.assertEqual(status, 200)
        self.assertIn("application/json", ctype)
        snap = json.loads(body.decode("utf-8"))
        return snap, {d["name"]: d for d in snap["datasets"]}

    def test_binds_to_loopback_by_default(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")

    def test_page_is_served(self):
        status, ctype, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", ctype)
        self.assertIn("/api/data", body.decode("utf-8"))

    def test_directory_discovery_skips_meta_and_unrelated_json(self):
        snap, by = self.api()
        self.assertEqual(sorted(by), ["enemies.json", "items.json", "upgrades.json"])
        self.assertEqual({d["kind"] for d in snap["datasets"]}, {"items", "upgrades", "enemies"})
        self.assertTrue(all(d["ok"] and "report" in d for d in snap["datasets"]))

    def test_cross_file_drop_table_check(self):
        _, by = self.api()
        self.assertEqual(by["enemies.json"]["report"]["errors"], [])
        self.write("enemies.json", {"enemies": [dict(enemy("e1", damage=1), drop_table="missing")]})
        _, by = self.api()
        self.assertEqual(codes(by["enemies.json"]["report"]["errors"]), ["unknown_drop_table"])
        (self.dir / "items.json").unlink()
        _, by = self.api()
        self.assertEqual(by["enemies.json"]["report"]["drop_table_not_checked"], ["e1"])

    def test_reads_fresh_and_picks_up_new_files(self):
        first, _ = self.api()
        self.write("upgrades.json", {"upgrades": [upgrade("u1", 10), upgrade("u2", 5, requires=["u1"])]})
        second, by = self.api()
        self.assertNotEqual(first["version"], second["version"])
        self.assertEqual(codes(by["upgrades.json"]["report"]["warnings"]), ["cost_inversion"])
        self.write("boss_enemies.json", {"enemies": [enemy("boss", "boss", damage=9)]})
        _, by = self.api()
        self.assertIn("boss_enemies.json", by)

    def test_broken_dataset_reports_error(self):
        self.write("items.json", "{ broken")
        _, by = self.api()
        self.assertFalse(by["items.json"]["ok"])
        self.assertIn("형식 오류", by["items.json"]["error"])
        self.assertEqual(by["items.json"]["kind"], "items")

    def test_explicit_non_data_file_reports_error(self):
        snap = viewer.snapshot([self.dir / "notes.json"])
        self.assertFalse(snap["datasets"][0]["ok"])
        self.assertIn("데이터가 아닙니다", snap["datasets"][0]["error"])

    def test_other_paths_are_not_served(self):
        for route in ("/items.json", "/../../etc/passwd", "/assets/data-viewer.html", "/api/items"):
            self.assertEqual(self.get(route)[0], 404, route)

    def test_cli_requires_existing_data(self):
        self.assertEqual(studio_cli("view", self.dir / "nope", "--no-browser")[0], 2)
        empty = Path(self.tmp.name) / "empty"
        empty.mkdir()
        self.assertEqual(studio_cli("view", empty, "--no-browser")[0], 2)


if __name__ == "__main__":
    unittest.main()
