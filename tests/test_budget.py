"""스탯 예산(budget) 테스트: 곡선, 예산 비교, 원형, 초안, 전투 계산에서 나온 스탯 원가 제안. 표준 라이브러리 unittest만 사용한다."""
import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from _studio import SAMPLE, budget as bg, combat as cb, run_cli

BASE = {
    "budget": {
        "items": {"costs": {"attack": 1.0, "max_hp": 0.2, "armor": 2.0},
                  "curve": {"by": "tier", "growth": "linear", "base": 10, "rate": 10}},
        "enemies": {"costs": {"hp": 0.1, "damage": 1.0},
                    "curve": {"by": "zone", "growth": "exponential", "base": 10, "rate": 1.0},
                    "multiplier": {"field": "rank", "values": {"normal": 1, "elite": 3}}},
        "tolerance": 0.2,
    },
    "archetypes": [
        {"id": "blade", "for": "items", "split": {"attack": 1.0}, "fields": {"slot": "weapon"}},
        {"id": "plate", "for": "items", "split": {"armor": 0.5, "max_hp": 0.5}, "fields": {"slot": "armor"}},
        {"id": "brute", "for": "enemies", "split": {"hp": 0.5, "damage": 0.5}, "fields": {"rank": "normal"}},
    ],
}
ITEMS = {"sword": {"id": "sword", "tier": 2, "stats": {"attack": 20}},          # 예산 20, 목표 20
         "big": {"id": "big", "tier": 1, "stats": {"attack": 15}},              # 15 / 10 → 넘침
         "tiny": {"id": "tiny", "tier": 3, "stats": {"attack": 10}},            # 10 / 30 → 모자람
         "odd": {"id": "odd", "tier": 1, "stats": {"attack": 1}, "unique_effect": True},
         "gone": {"id": "gone", "tier": 1, "stats": {"attack": 99}, "status": "cut"}}
ENEMIES = {"slime": {"id": "slime", "zone": 1, "rank": "normal", "stats": {"hp": 50, "damage": 5}},     # 10 / 10
           "ogre": {"id": "ogre", "zone": 2, "rank": "elite", "stats": {"hp": 300, "damage": 30}}}      # 60 / (20×3)


def data(**over):
    d = copy.deepcopy(BASE)
    d["budget"].update(over)
    return d


def codes(entries):
    return [e["code"] for e in entries]


def validate(d=None, items=ITEMS, enemies=ENEMIES, suggestions=None):
    return bg.validate(d or data(), items=items, enemies=enemies, suggestions=suggestions)


def row(r, side, eid):
    return next(x for x in r["rows"] if x["side"] == side and x["id"] == eid)


class Curves(unittest.TestCase):
    def test_growth_forms(self):
        self.assertEqual(bg.curve_value({"growth": "linear", "base": 10, "rate": 10}, 3), 30)
        self.assertEqual(bg.curve_value({"growth": "exponential", "base": 10, "rate": 1.0}, 3), 40)
        self.assertEqual(bg.curve_value({"growth": "table", "values": {"1": 5, "2": 9}}, 2), 9)
        self.assertIsNone(bg.curve_value({"growth": "table", "values": {"1": 5}}, 2))

    def test_table_without_a_point_is_an_error(self):
        d = data()
        d["budget"]["items"]["curve"] = {"by": "tier", "growth": "table", "values": {"1": 10, "2": 20}}
        r = validate(d)
        self.assertIn("curve_missing_point", codes(r["errors"]))


class Comparison(unittest.TestCase):
    def test_over_and_under_budget_with_tolerance(self):
        r = validate()
        self.assertEqual(row(r, "items", "sword")["flag"], "ok")
        self.assertEqual(row(r, "items", "big")["flag"], "over")
        self.assertEqual(row(r, "items", "tiny")["flag"], "under")
        self.assertEqual(sorted(codes(r["warnings"])), ["over_budget", "under_budget"])
        self.assertAlmostEqual(row(r, "items", "big")["ratio"], 1.5)

    def test_multiplier_by_rank(self):
        r = validate()
        self.assertEqual(row(r, "enemies", "ogre")["expected"], 60)
        self.assertEqual(row(r, "enemies", "ogre")["flag"], "ok")

    def test_unique_and_cut_entries_are_left_out(self):
        r = validate()
        ids = [x["id"] for x in r["rows"]]
        self.assertNotIn("gone", ids)
        self.assertEqual(row(r, "items", "odd")["flag"], "excluded")

    def test_stat_without_cost_leaves_the_entry_unchecked(self):
        items = dict(ITEMS, boots={"id": "boots", "tier": 1, "stats": {"move_speed": 3}})
        r = validate(items=items)
        self.assertEqual(row(r, "items", "boots")["flag"], "unchecked")
        self.assertIn("stat_without_cost", codes(r["warnings"]))
        self.assertNotIn("boots", " ".join(w["where"] for w in r["warnings"] if w["code"] == "under_budget"))
        self.assertGreater(r["unchecked"], 0)

    def test_missing_multiplier_value_is_reported(self):
        enemies = dict(ENEMIES, king={"id": "king", "zone": 1, "rank": "boss", "stats": {"hp": 10, "damage": 1}})
        r = validate(enemies=enemies)
        self.assertEqual(row(r, "enemies", "king")["flag"], "unchecked")
        self.assertIn("multiplier_missing", codes(r["warnings"]))

    def test_entry_acknowledgement_moves_the_warning(self):
        items = dict(ITEMS, big=dict(ITEMS["big"], acknowledged={"over_budget": "초반 함정 아이템"}))
        r = validate(items=items)
        self.assertEqual(codes(r["warnings"]), ["under_budget"])
        self.assertEqual([a["code"] for a in r["acknowledged"]], ["over_budget"])

    def test_without_item_data_the_side_is_unchecked(self):
        r = validate(items=None)
        self.assertEqual([x for x in r["rows"] if x["side"] == "items"], [])
        self.assertIn("items", r["unchecked_kinds"])


class Schema(unittest.TestCase):
    def test_bad_settings(self):
        cases = []
        d = data(); d["budget"]["items"]["curve"]["growth"] = "cubic"; cases.append(d)
        d = data(); d["archetypes"][0]["split"] = {"attack": 0.7}; cases.append(d)
        d = data(); d["archetypes"][0]["split"] = {"speed": 1.0}; cases.append(d)
        d = data(); d["archetypes"][0]["for"] = "upgrades"; cases.append(d)
        d = data(tolerance=-1); cases.append(d)
        d = data(); d["budget"]["items"]["costs"]["attack"] = 0; cases.append(d)
        for d in cases:
            with self.subTest(d):
                self.assertIn("schema", codes(validate(d)["errors"]))


class Draft(unittest.TestCase):
    def test_item_draft_splits_the_tier_budget_by_cost(self):
        entry, info = bg.draft(data(), "plate", 3)
        # 예산 30: armor 15 / 2 = 7.5, max_hp 15 / 0.2 = 75
        self.assertEqual(entry["stats"], {"armor": 7.5, "max_hp": 75})
        self.assertEqual((entry["tier"], entry["slot"], entry["status"]), (3, "armor", "proposed"))
        self.assertEqual(entry["provenance"]["kind"], "computed")
        self.assertEqual(info["expected"], 30)

    def test_enemy_draft_uses_the_multiplier_field(self):
        entry, info = bg.draft(data(), "brute", 2, fields={"rank": "elite"})
        self.assertEqual(info["expected"], 60)
        self.assertEqual(entry["stats"], {"hp": 300, "damage": 30})
        self.assertEqual(entry["rank"], "elite")

    def test_drafts_land_on_the_curve(self):
        entry, _ = bg.draft(data(), "blade", 2, entry_id="new_blade")
        r = validate(items={"new_blade": entry})
        self.assertEqual(row(r, "items", "new_blade")["flag"], "ok")

    def test_unknown_archetype_is_a_value_error(self):
        with self.assertRaises(ValueError):
            bg.draft(data(), "nope", 1)


class SuggestedCosts(unittest.TestCase):
    def test_ratio_formula_costs_match_the_analytic_marginals(self):
        combat = {"combat": {"stats": {"player": {"hp": "max_hp", "attack": "attack", "defense": "armor"},
                                       "enemy": {"hp": "hp", "attack": "damage"}},
                             "defense": {"form": "ratio", "k": 100}},
                  "stages": [{"id": "s1", "player": {"base": {"max_hp": 100, "attack": 20, "armor": 0}}, "enemies": ["slime"]}]}
        s = cb.marginal_costs(combat, items={}, upgrades={}, enemies=ENEMIES)
        player = s["player"]["s1"]
        # 비율 공식에서 ∂ln(힘)/∂공격 = 1/공격, ∂/∂체력 = 1/체력, ∂/∂방어 = 1/(k+방어). 공격 원가 1 기준으로 환산
        self.assertAlmostEqual(player["attack"], 1.0, places=3)
        self.assertAlmostEqual(player["max_hp"], 20 / 100, places=3)
        self.assertAlmostEqual(player["armor"], 20 / 100, places=3)

    def test_suggestions_are_scaled_to_the_designer_attack_cost(self):
        d = data()
        d["budget"]["items"]["costs"]["attack"] = 2.0
        s = {"player": {"s1": {"attack": 1.0, "armor": 0.5}}, "enemy": {}, "attack_stat": {"player": "attack", "enemy": "damage"}}
        self.assertEqual(validate(d, suggestions=s)["suggested_costs"]["items"]["s1"]["armor"], 1.0)


class ReviewFindings(unittest.TestCase):
    """코드 검토에서 나온 문제의 회귀 테스트."""

    def test_non_positive_expected_budget_is_an_error_not_a_crash(self):
        d = data()
        d["budget"]["items"]["curve"] = {"by": "tier", "growth": "linear", "base": 10, "rate": -5}
        r = validate(d)
        self.assertIn("curve_not_positive", codes(r["errors"]))
        with self.assertRaises(ValueError):
            bg.draft(d, "blade", 3)

    def test_set_cannot_override_the_curve_field(self):
        with self.assertRaises(ValueError):
            bg.draft(data(), "blade", 3, fields={"tier": 5})
        d = data()
        d["archetypes"][0]["fields"]["tier"] = 2
        self.assertIn("schema", codes(validate(d)["errors"]))

    def test_unrelated_errors_do_not_block_a_valid_draft(self):
        d = data()
        d["archetypes"][2]["split"] = {"hp": 0.9}           # 적 원형 오류
        d["budget"]["enemies"]["costs"] = {"hp": -1}         # 적 쪽 설정 오류
        entry, _ = bg.draft(d, "blade", 2)
        self.assertEqual(entry["stats"], {"attack": 20})
        with self.assertRaises(ValueError):
            bg.draft(d, "brute", 1)

    def test_a_broken_side_does_not_stop_the_other_side(self):
        d = data()
        d["budget"]["enemies"]["costs"] = {"hp": -1}
        r = validate(d)
        self.assertIn("schema", codes(r["errors"]))
        self.assertEqual(row(r, "items", "sword")["flag"], "ok")

    def test_suggestions_only_list_stats_the_side_uses(self):
        s = {"player": {}, "enemy": {"s1": {"damage": 1.0, "hp": 0.1, "armor": 0.3}}, "attack_stat": {"player": "attack", "enemy": "damage"}}
        r = validate(suggestions=s)
        self.assertEqual(set(r["suggested_costs"]["enemies"]["s1"]), {"damage", "hp"})

    def test_failed_suggestions_are_reported(self):
        r = validate(suggestions={"failed": "TypeError: boom"})
        self.assertEqual(codes(r["warnings"])[-1], "suggestions_unavailable")
        self.assertIn("boom", r["warnings"][-1]["message"])

    def test_empty_acknowledgement_reason_does_not_hide_the_warning(self):
        items = dict(ITEMS, big=dict(ITEMS["big"], acknowledged={"over_budget": " "}))
        self.assertIn("over_budget", codes(validate(items=items)["warnings"]))

    def test_entry_without_the_curve_field_is_named(self):
        items = dict(ITEMS, loose={"id": "loose", "stats": {"attack": 3}})
        r = validate(items=items)
        self.assertIn("curve_field_missing", codes(r["warnings"]))
        self.assertIn("loose", " ".join(w["message"] for w in r["warnings"]))
        self.assertEqual(row(r, "items", "loose")["flag"], "unchecked")


class SuggestionRobustness(unittest.TestCase):
    def combat(self, armor):
        return {"combat": {"stats": {"player": {"hp": "max_hp", "attack": "attack", "defense": "armor"},
                                     "enemy": {"hp": "hp", "attack": "damage"}},
                           "defense": {"form": "flat", "min_damage": 0}},
                "stages": [{"id": "s1", "player": {"base": {"max_hp": 100, "attack": 20, "armor": armor}}, "enemies": ["slime", "ogre"]}]}

    def test_one_enemy_that_cannot_hurt_does_not_drop_the_stage(self):
        # 방어 10이면 slime(피해 5)의 피해가 0이 된다. ogre만으로 잰다.
        s = cb.marginal_costs(self.combat(10), items={}, upgrades={}, enemies=ENEMIES)
        self.assertIn("s1", s["player"])
        self.assertEqual(s["skipped"]["s1"], 1)

    def test_suggestions_are_not_computed_without_a_budget_file(self):
        from _studio import datasets
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name) / "game"
        shutil.copytree(SAMPLE, root)
        (root / "data/budget.json").unlink()
        calls = []
        original = cb.marginal_costs
        cb.marginal_costs = lambda *a, **k: calls.append(1) or original(*a, **k)
        try:
            datasets.collect([root])
        finally:
            cb.marginal_costs = original
        self.assertEqual(calls, [])


class CommandLine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "game"
        shutil.copytree(SAMPLE, self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def report(self):
        code, out = run_cli("check", self.root, "--json")
        return next(d["report"] for d in json.loads(out)["datasets"] if d["kind"] == "budget")

    def test_sample_budget_has_no_errors_or_warnings(self):
        r = self.report()
        self.assertEqual((r["errors"], r["warnings"], r["unchecked"]), ([], [], 0))
        self.assertGreater(len(r["rows"]), 0)
        self.assertTrue(r["suggested_costs"]["items"])

    def test_draft_command_prints_a_proposed_entry(self):
        code, out = run_cli("draft", self.root, "--archetype", "blade", "--at", "2", "--id", "new_blade")
        self.assertEqual(code, 0)
        entry = json.loads(out[out.index("{"):])
        self.assertEqual((entry["id"], entry["status"]), ("new_blade", "proposed"))

    def test_draft_command_usage_errors(self):
        self.assertEqual(run_cli("draft", self.root, "--archetype", "nope", "--at", "1")[0], 2)
        empty = Path(self.tmp.name) / "empty"
        empty.mkdir()
        self.assertEqual(run_cli("draft", empty, "--archetype", "blade", "--at", "1")[0], 2)

    def test_malformed_set_is_a_usage_error(self):
        self.assertEqual(run_cli("draft", self.root, "--archetype", "brute", "--at", "1", "--set", "rank")[0], 2)

    def test_table_includes_budget_rows(self):
        code, out = run_cli("check", self.root, "--table")
        self.assertIn("| 종류 | id | 기준 |", out)


if __name__ == "__main__":
    unittest.main()
