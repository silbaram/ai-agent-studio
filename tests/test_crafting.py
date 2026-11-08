"""강화·합성(crafting) 테스트: 강화 기대 비용, 강화가 상위 티어를 넘는지, 합성 가치, 무한 증식 고리, 얻을 수 없는 아이템.
표준 라이브러리 unittest만 사용한다."""
import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from _studio import SAMPLE, budget as bg, crafting as cr, run_cli

ITEMS = {
    "a1": {"id": "a1", "tier": 1, "slot": "weapon", "rarity": "common", "stats": {"attack": 10}},
    "a2": {"id": "a2", "tier": 1, "slot": "weapon", "rarity": "common", "stats": {"attack": 10}},
    "b1": {"id": "b1", "tier": 2, "slot": "weapon", "rarity": "rare", "stats": {"attack": 20}},
    "b2": {"id": "b2", "tier": 2, "slot": "weapon", "rarity": "rare", "stats": {"attack": 20}},
    "gem": {"id": "gem", "tier": 1, "slot": "material", "rarity": "common", "stats": {}},
    "old": {"id": "old", "tier": 1, "slot": "weapon", "stats": {"attack": 1}, "status": "cut"},
}
COMMON_ONLY = {"chest": {"entries": [{"rarity": "common", "weight": 1}]}}
DROPS = dict(COMMON_ONLY, boss={"entries": [{"item": "b1", "weight": 1}, {"item": "b2", "weight": 1}]})
BUDGET = bg.read_settings({"budget": {"items": {"costs": {"attack": 1.0}, "curve": {"by": "tier", "growth": "linear", "base": 10, "rate": 10}}}}, [])


def data(**over):
    d = {"crafting": {"provenance": {"kind": "assumed"}}, "enhance": [], "recipes": []}
    d.update(copy.deepcopy(over))
    return d


def track(levels, **over):
    t = {"id": "plus", "applies_to": {"slot": "weapon"}, "levels": levels}
    t.update(over)
    return t


def codes(entries):
    return [e["code"] for e in entries]


def validate(d, items=ITEMS, drops=DROPS, budget=BUDGET):
    return cr.validate(d, items=items, drop_tables=drops, budget=budget)


class Enhancement(unittest.TestCase):
    def costs(self, levels, **over):
        r = validate(data(enhance=[track(levels, **over)]))
        self.assertEqual(r["errors"], [])
        return r["tracks"]["plus"]["levels"]

    def test_keep_on_fail(self):
        lv = self.costs([{"cost": 100}, {"cost": 200, "success": 0.5}])
        self.assertEqual([x["expected_cost"] for x in lv], [100, 500])
        self.assertEqual([x["expected_attempts"] for x in lv], [1, 3])

    def test_drop_a_level_on_fail(self):
        lv = self.costs([{"cost": 100}, {"cost": 200, "success": 0.5, "on_fail": "down"}])
        self.assertEqual(lv[1]["expected_cost"], 600)       # (200 + 0.5 × 100) / 0.5 + 100
        self.assertEqual(lv[1]["expected_attempts"], 4)

    def test_destroy_on_fail_restarts_with_a_replacement(self):
        lv = self.costs([{"cost": 100}, {"cost": 200, "success": 0.5, "on_fail": "destroy"}], replace_cost=50)
        self.assertEqual(lv[1]["expected_cost"], 650)       # (200 + 0.5 × (50 + 100)) / 0.5 + 100

    def test_cumulative_bonus(self):
        lv = self.costs([{"cost": 1, "bonus_pct": 0.1}, {"cost": 1, "bonus_pct": 0.2}])
        self.assertEqual([x["bonus_pct"] for x in lv], [0.1, 0.3])

    def test_bad_levels(self):
        for levels, over in (([{"cost": 1, "success": 0}], {}), ([{"cost": -1}], {}), ([{"cost": 1, "on_fail": "explode"}], {}),
                             ([{"cost": 1, "success": 0.5, "on_fail": "destroy"}], {})):
            with self.subTest(levels):
                self.assertEqual(codes(validate(data(enhance=[track(levels, **over)]))["errors"]), ["schema"])

    def test_enhanced_item_overtaking_the_next_tier_is_warned(self):
        r = validate(data(enhance=[track([{"cost": 1, "bonus_pct": 1.5}])]))   # a1·a2 25 > 티어 2 기대 20 × 1.2
        self.assertEqual(codes(r["warnings"]), ["enhance_overtakes_tier"])
        r = validate(data(enhance=[track([{"cost": 1, "bonus_pct": 1.0}])]))   # 20 = 20, 티어 2는 다음 티어가 없어 비교하지 않는다
        self.assertEqual(r["warnings"], [])

    def test_track_matching_nothing_is_an_error(self):
        r = validate(data(enhance=[track([{"cost": 1}], applies_to={"slot": "boots"})]))
        self.assertEqual(codes(r["errors"]), ["match_empty"])


def recipe(rid, inputs, output, **over):
    r = {"id": rid, "inputs": inputs, "output": output}
    r.update(over)
    return r


class Recipes(unittest.TestCase):
    def test_references(self):
        r = validate(data(recipes=[recipe("r1", [{"item": "nope", "count": 1}], {"item": "b1"}),
                                   recipe("r2", [{"match": {"slot": "boots"}, "count": 1}], {"item": "b1"}),
                                   recipe("r3", [{"item": "old", "count": 1}], {"item": "b1"})]))
        self.assertEqual(sorted(codes(r["errors"])), ["match_empty", "unknown_item"])
        self.assertEqual(codes(r["warnings"]), ["cut_referenced"])

    def test_synthesis_that_loses_value_is_warned(self):
        r = validate(data(recipes=[recipe("r1", [{"item": "a1", "count": 3}], {"item": "b1"})]))
        self.assertEqual(codes(r["warnings"]), ["recipe_loses_value"])
        self.assertAlmostEqual(r["recipes"]["r1"]["value_ratio"], 20 / 30, places=3)
        r = validate(data(recipes=[recipe("r1", [{"item": "a1", "count": 2}], {"item": "b1"})]))
        self.assertEqual(r["warnings"], [])

    def test_value_counts_the_success_rate(self):
        r = validate(data(recipes=[recipe("r1", [{"item": "a1", "count": 2}], {"item": "b1"}, success=0.5)]))
        self.assertEqual(r["recipes"]["r1"]["value_ratio"], 0.5)   # 20 × 0.5 / 20
        self.assertEqual(codes(r["warnings"]), ["recipe_loses_value"])

    def test_random_merge_reports_the_cost_of_one_specific_item(self):
        r = validate(data(recipes=[recipe("merge", [{"match": {"tier": 1, "slot": "weapon"}, "count": 2}], {"match": {"tier": 2, "slot": "weapon"}})]))
        info = r["recipes"]["merge"]
        self.assertEqual((info["outcomes"], info["crafts_for_specific"], info["inputs_for_specific"]), (2, 2, 4))

    def test_item_multiplication_loop_is_an_error(self):
        loop = [recipe("split", [{"item": "b1", "count": 1}], {"item": "a1", "count": 3}),
                recipe("join", [{"item": "a1", "count": 2}], {"item": "b1"})]
        r = validate(data(recipes=loop))
        self.assertIn("value_loop", codes(r["errors"]))
        self.assertIn("b1", r["errors"][0]["message"])
        loop[0]["output"]["count"] = 2  # 1 b1 → 2 a1 → 1 b1: 늘어나지 않는다
        self.assertNotIn("value_loop", codes(validate(data(recipes=loop))["errors"]))

    def test_bad_recipe_shapes(self):
        for rec in (recipe("r", [], {"item": "b1"}), recipe("r", [{"item": "a1", "count": 0}], {"item": "b1"}),
                    recipe("r", [{"item": "a1"}], {}), recipe("r", [{"item": "a1"}], {"item": "b1"}, success=1.5)):
            with self.subTest(rec):
                self.assertIn("schema", codes(validate(data(recipes=[rec]))["errors"]))


class Obtainable(unittest.TestCase):
    def test_items_without_any_source_are_warned(self):
        r = validate(data(), drops=COMMON_ONLY)
        warned = [w for w in r["warnings"] if w["code"] == "unobtainable"]
        self.assertEqual(len(warned), 1)
        self.assertIn("b1", warned[0]["message"])
        self.assertNotIn("a1", warned[0]["message"])           # common 희귀도 드랍으로 얻는다

    def test_recipe_outputs_and_declared_sources_count(self):
        d = data(recipes=[recipe("r1", [{"item": "a1", "count": 2}], {"item": "b1"})])
        d["crafting"]["other_sources"] = {"b2": "상점"}
        self.assertNotIn("unobtainable", codes(validate(d, drops=COMMON_ONLY)["warnings"]))

    def test_recipe_with_unobtainable_inputs_gives_nothing(self):
        d = data(recipes=[recipe("r1", [{"item": "b2", "count": 1}], {"item": "b1"})])
        msg = " ".join(w["message"] for w in validate(d, drops=COMMON_ONLY)["warnings"] if w["code"] == "unobtainable")
        self.assertIn("b1", msg)
        self.assertIn("b2", msg)


class Unchecked(unittest.TestCase):
    def test_without_items_everything_is_unchecked(self):
        r = cr.validate(data(enhance=[track([{"cost": 1}])]), items=None, drop_tables=None, budget=None)
        self.assertEqual(r["errors"], [])
        self.assertGreater(r["unchecked"], 0)

    def test_without_budget_values_are_not_judged(self):
        r = validate(data(recipes=[recipe("r1", [{"item": "a1", "count": 3}], {"item": "b1"})]), budget=None)
        self.assertNotIn("recipe_loses_value", codes(r["warnings"]))
        self.assertIsNone(r["recipes"]["r1"]["value_ratio"])


class ReviewFindings(unittest.TestCase):
    """코드 검토에서 나온 문제의 회귀 테스트."""

    def test_loop_through_a_random_merge_is_found(self):
        loop = [recipe("merge", [{"match": {"tier": 1, "slot": "weapon"}, "count": 2}], {"match": {"tier": 2, "slot": "weapon"}}),
                recipe("salvage_b1", [{"item": "b1"}], {"item": "a1", "count": 3}),
                recipe("salvage_b2", [{"item": "b2"}], {"item": "a2", "count": 3})]
        r = validate(data(recipes=loop))
        self.assertIn("value_loop", codes(r["errors"]))
        self.assertIn("merge", " ".join(e["message"] for e in r["errors"]))
        # b2만 분해할 수 있으면 기대 수율은 1/2 × (3 + 0)/2 = 0.75배라 늘어나지 않는다
        self.assertNotIn("value_loop", codes(validate(data(recipes=loop[:2]))["errors"]))

    def test_unique_effect_items_are_not_valued_by_stats(self):
        items = dict(ITEMS, b1=dict(ITEMS["b1"], unique_effect=True))
        r = validate(data(recipes=[recipe("r1", [{"item": "a1", "count": 3}], {"item": "b1"})]), items=items)
        self.assertIsNone(r["recipes"]["r1"]["value_ratio"])
        self.assertNotIn("recipe_loses_value", codes(r["warnings"]))
        self.assertIn("고유 효과", r["recipes"]["r1"]["value_note"])

    def test_any_matching_input_is_valued_at_the_cheapest(self):
        items = dict(ITEMS, a2=dict(ITEMS["a2"], stats={"attack": 4}))
        r = validate(data(recipes=[recipe("r1", [{"match": {"tier": 1, "slot": "weapon"}, "count": 2}], {"item": "b1"})]), items=items)
        self.assertEqual(r["recipes"]["r1"]["value_in"], 8)      # 가장 싼 a2(4) × 2

    def test_unobtainable_item_can_be_acknowledged_on_the_item(self):
        items = dict(ITEMS, b1=dict(ITEMS["b1"], acknowledged={"unobtainable": "시즌 이벤트 보상"}))
        r = validate(data(), items=items, drops=COMMON_ONLY)
        self.assertIn("b2", " ".join(w["message"] for w in r["warnings"] if w["code"] == "unobtainable"))
        self.assertNotIn("b1", " ".join(w["message"] for w in r["warnings"] if w["code"] == "unobtainable"))
        self.assertEqual([a["where"] for a in r["acknowledged"]], ["b1"])

    def test_value_skip_reason_names_what_is_missing(self):
        no_items_side = bg.read_settings({"budget": {"enemies": {"costs": {"hp": 1}, "curve": {"by": "zone", "base": 1, "rate": 1}}}}, [])
        self.assertEqual(validate(data(), budget=no_items_side)["value_skipped"], "no_items_side")
        self.assertEqual(validate(data(), budget=None)["value_skipped"], "no_budget")
        self.assertIsNone(validate(data())["value_skipped"])

    def test_track_with_both_targets_is_an_error(self):
        r = validate(data(enhance=[track([{"cost": 1}], items=["a1"])]))
        self.assertEqual(codes(r["errors"]), ["schema"])

    def test_explicit_item_list_track(self):
        r = validate(data(enhance=[{"id": "plus", "items": ["a1", "nope"], "levels": [{"cost": 1}]}]))
        self.assertEqual(codes(r["errors"]), ["unknown_item"])
        self.assertEqual(r["tracks"]["plus"]["items"], ["a1"])

    def test_down_on_the_first_level_is_keep(self):
        r = validate(data(enhance=[track([{"cost": 100, "success": 0.5, "on_fail": "down"}])]))
        self.assertEqual(r["tracks"]["plus"]["levels"][0]["expected_cost"], 200)

    def test_other_sources_unknown_id_and_empty_output_match(self):
        d = data(recipes=[recipe("r1", [{"item": "a1"}], {"match": {"tier": 9}})])
        d["crafting"]["other_sources"] = {"ghost": "상점"}
        self.assertEqual(sorted(codes(validate(d)["errors"])), ["match_empty", "unknown_item"])


class CommandLine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "game"
        shutil.copytree(SAMPLE, self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_sample_crafting_has_no_errors_or_warnings(self):
        code, out = run_cli("check", self.root, "--json")
        r = next(d["report"] for d in json.loads(out)["datasets"] if d["kind"] == "crafting")
        self.assertEqual((r["errors"], r["warnings"], r["unchecked"]), ([], [], 0))
        self.assertTrue(r["tracks"] and r["recipes"])

    def test_crafting_file_alone_is_incomplete(self):
        code, out = run_cli("check", self.root / "data/crafting.json")
        self.assertIn("INCOMPLETE", out)

    def test_table(self):
        code, out = run_cli("check", self.root, "--table")
        self.assertIn("| 강화 | 단계 |", out)
        self.assertIn("| 합성 | 재료 |", out)


if __name__ == "__main__":
    unittest.main()
