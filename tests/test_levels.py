"""레벨 구성(L1) 테스트: 조우의 위협도, 곡선 예산, 전투 단계·재화 흐름과의 연결. 표준 라이브러리 unittest만 사용한다."""
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from _studio import ROOT, SAMPLE, STUDIO, budget as bg, common, datasets, levels as lv, playtests, run_cli

ENEMIES = {"a": {"id": "a", "rank": "normal", "zone": 1, "stats": {"hp": 10}}, "b": {"id": "b", "rank": "elite", "zone": 1, "stats": {"hp": 30}},
           "c": {"id": "c", "rank": "normal", "zone": 2, "stats": {"hp": 20}}, "gone": {"id": "gone", "rank": "normal", "zone": 1, "stats": {"hp": 99}, "status": "cut"}}
THREAT = {"a": 10.0, "b": 30.0, "c": 20.0, "gone": 99.0}
COMBAT = {"stages": [{"id": "s1", "zone": 1}, {"id": "old", "zone": 3, "status": "cut"}, {"id": "s2", "zone": 2}]}
BUDGET = {"curve": {"growth": "linear", "base": 80, "rate": 40}, "roles": {"room": 1, "boss": 2}, "tolerance": 0.25, "provenance": {"kind": "assumed"}}


def enc(eid="e1", enemies=None, role="room", **over):
    return {"id": eid, "role": role, "enemies": {"a": 5, "b": 1} if enemies is None else enemies, **over}


def level(lid="s1", *encounters, **over):
    return {"id": lid, "encounters": list(encounters) or [enc()], "provenance": {"kind": "assumed"}, **over}


def both(first=None, second=None):
    """단계 둘을 모두 채운 레벨. 적 a·b는 s1, c는 s2의 적이다."""
    return [first or level("s1"), second or level("s2", enc("e2", {"c": 6}))]


def run(levels=None, budget=BUDGET, enemies=ENEMIES, threat=THREAT, combat=COMBAT, economy=None, **extra):
    data = {"levels": both() if levels is None else levels}
    if budget is not None:
        data["threat_budget"] = budget
    return lv.validate(data, enemies=enemies, threat=threat, combat=combat, economy=economy, **extra)


def codes(entries):
    return [e["code"] for e in entries]


def row(result, eid="e1"):
    return next(x for lvl in result["levels"] for x in lvl["encounters"] if x["id"] == eid)


class Threat(unittest.TestCase):
    def test_encounter_threat_adds_up_its_enemies(self):
        self.assertEqual(row(run())["threat"], 80)

    def test_counts_may_be_averages(self):
        self.assertEqual(row(run(both(level("s1", enc(enemies={"a": 1.5, "b": 2.5})))))["threat"], 90)

    def test_repeat_multiplies_kills_and_the_run_total_not_the_encounter(self):
        r = run(both(level("s1", enc(repeat=2.5))))
        self.assertEqual(row(r)["threat"], 80)
        self.assertEqual(r["levels"][0]["threat"], 200)
        self.assertEqual(r["levels"][0]["kills"], {"a": 12.5, "b": 2.5})

    def test_repeat_defaults_to_one(self):
        r = run()
        self.assertEqual(row(r)["repeat"], 1)
        self.assertEqual(r["levels"][0]["threat"], 80)


class Budget(unittest.TestCase):
    def test_budget_is_the_curve_at_the_stage_times_the_role(self):
        r = run(both(level("s1", enc(role="boss", enemies={"a": 16}))))
        self.assertEqual((row(r)["expected"], row(r)["low"], row(r)["high"], row(r)["flag"]), (160, 120, 200, "ok"))

    def test_stage_position_skips_cut_stages(self):
        self.assertEqual(row(run(), "e2")["expected"], 120)

    def test_exponential_curve(self):
        b = {**BUDGET, "curve": {"growth": "exponential", "base": 80, "rate": 0.5}}
        self.assertEqual(row(run(budget=b), "e2")["expected"], 120)

    def test_table_curve_is_keyed_by_stage_id(self):
        b = {**BUDGET, "curve": {"growth": "table", "values": {"s1": 80, "s2": 200}}}
        self.assertEqual(row(run(budget=b), "e2")["expected"], 200)

    def test_table_without_the_stage_is_an_error(self):
        b = {**BUDGET, "curve": {"growth": "table", "values": {"s1": 80}}}
        r = run(budget=b)
        self.assertTrue(any(e["where"] == "s2" and "s2" in e["message"] for e in r["errors"]))
        self.assertIsNone(row(r, "e2")["expected"])

    def test_curve_that_falls_to_nothing_is_an_error(self):
        b = {**BUDGET, "curve": {"growth": "linear", "base": 80, "rate": -80}}
        self.assertTrue(any(e["where"] == "s2" for e in run(budget=b)["errors"]))

    def test_over_and_under_are_warned_with_their_owner(self):
        r = run(both(level("s1", enc("big", {"a": 11}), enc("small", {"a": 5}))))
        got = {w["part"]: w for w in r["warnings"]}
        self.assertEqual((got["big"]["code"], got["small"]["code"]), ("over_budget", "under_budget"))
        self.assertEqual((got["big"]["where"], got["big"]["owner"]), ("s1.big", "s1"))
        self.assertEqual((row(r, "big")["flag"], row(r, "small")["flag"]), ("over", "under"))

    def test_the_edge_of_the_tolerance_is_inside(self):
        r = run(both(level("s1", enc("top", {"a": 7, "b": 1}), enc("bottom", {"a": 3, "b": 1}))))
        self.assertEqual(r["warnings"], [])

    def test_tolerance_defaults(self):
        b = {k: v for k, v in BUDGET.items() if k != "tolerance"}
        self.assertEqual(run(budget=b)["tolerance"], lv.DEFAULT_TOLERANCE)


class Shapes(unittest.TestCase):
    def assertSchema(self, r, word=""):
        hits = [e for e in r["errors"] if e["code"] == "schema" and word in e["message"]]
        self.assertTrue(hits, r["errors"])

    def test_levels_must_be_a_list(self):
        self.assertSchema(lv.validate({"levels": {}}))

    def test_encounters_must_be_a_list(self):
        self.assertSchema(run([{"id": "s1", "encounters": {}}]), "encounters")
        self.assertSchema(run([{"id": "s1"}]), "encounters")

    def test_encounter_fields(self):
        for bad in (enc(enemies=["a"]), enc(enemies={"a": 0}), enc(enemies={"a": -1}), enc(enemies={"a": "3"}), enc(enemies={"a": True}),
                    enc(repeat=0), enc(repeat=-1), enc(repeat="2"), enc(role=3)):
            with self.subTest(bad):
                self.assertSchema(run(both(level("s1", bad))))

    def test_encounter_that_is_not_an_object(self):
        self.assertSchema(run(both({"id": "s1", "encounters": ["e1"]})))

    def test_unknown_encounter_keys_are_refused_with_a_hint(self):
        self.assertSchema(run(both(level("s1", enc(repeats=3)))), "'repeat'의 오타")

    def test_marked_keys_are_allowed(self):
        self.assertEqual(run(both(level("s1", enc(_memo="x"))))["errors"], [])

    def test_encounter_ids_are_unique_in_the_file(self):
        self.assertIn("duplicate_id", codes(run(both(level("s1", enc("x")), level("s2", enc("x", {"c": 6}))))["errors"]))
        self.assertIn("duplicate_id", codes(run(both(level("s1", enc("x"), enc("x"))))["errors"]))

    def test_role_must_be_in_the_budget(self):
        r = run(both(level("s1", enc(role="rom"))))
        self.assertEqual(codes(r["errors"]), ["unknown_role"])
        self.assertIn("'room'의 오타", r["errors"][0]["message"])

    def test_role_is_required_only_with_a_budget(self):
        self.assertIn("schema", codes(run(both(level("s1", {"id": "e1", "enemies": {"a": 5, "b": 1}})))["errors"]))
        self.assertEqual(run(both(level("s1", {"id": "e1", "enemies": {"a": 5, "b": 1}}), level("s2", {"id": "e2", "enemies": {"c": 6}})), budget=None)["errors"], [])

    def test_budget_shape(self):
        for bad in ([], {**BUDGET, "curve": None}, {**BUDGET, "curve": {"growth": "steps"}}, {**BUDGET, "curve": {"growth": "linear", "base": 0, "rate": 1}},
                    {**BUDGET, "roles": {}}, {**BUDGET, "roles": {"room": 0}}, {**BUDGET, "roles": ["room"]}, {**BUDGET, "tolerance": 1}, {**BUDGET, "tolerance": -0.1},
                    {**BUDGET, "provenance": {"kind": "computed"}}):
            with self.subTest(bad):
                self.assertTrue(run(budget=bad)["errors"])

    def test_combat_stage_must_be_text(self):
        self.assertSchema(run(both(level("s1", combat_stage=3))), "combat_stage")

    def test_infinite_counts_are_refused(self):
        self.assertSchema(run(both(level("s1", enc(enemies={"a": float("inf")})))))


class References(unittest.TestCase):
    def test_unknown_enemy_is_an_error_with_a_hint(self):
        r = run(both(level("s1", enc(enemies={"aa": 5}))))
        self.assertIn("unknown_enemy", codes(r["errors"]))
        self.assertIsNone(row(r)["threat"])

    def test_cut_enemy_is_warned_and_left_out(self):
        r = run(both(level("s1", enc(enemies={"a": 5, "b": 1, "gone": 3}))))
        self.assertEqual(codes(r["warnings"]), ["cut_referenced"])
        self.assertEqual(r["warnings"][0]["owner"], "s1")
        self.assertEqual(row(r)["threat"], 80)
        self.assertNotIn("gone", r["levels"][0]["kills"])

    def test_enemy_with_a_broken_record_has_no_threat_and_no_crash(self):
        r = run(threat={k: v for k, v in THREAT.items() if k != "b"})
        self.assertIsNone(row(r)["threat"])
        self.assertEqual(r["levels"][0]["threat"], None)

    def test_unknown_stage_is_an_error_with_a_hint(self):
        r = run(both(level("s3")))
        self.assertEqual(codes(r["errors"]), ["unknown_stage"])
        r = run(both(level("x", combat_stage="s11")))
        self.assertIn("'s1'의 오타", r["errors"][0]["message"])

    def test_combat_stage_links_a_level_with_another_id(self):
        self.assertEqual(run(both(level("crypt", combat_stage="s1")))["levels"][0]["stage"], "s1")

    def test_cut_stage_is_warned(self):
        r = run(both(level("old", enc(enemies={"a": 5}))))
        self.assertIn("cut_referenced", codes(r["warnings"]))

    def test_enemy_outside_the_stage_is_warned_with_its_target(self):
        r = run(both(level("s1", enc(enemies={"a": 5, "b": 1, "c": 1}))))
        w = next(x for x in r["warnings"] if x["code"] == "enemy_not_in_stage")
        self.assertEqual((w["owner"], w["part"]), ("s1", "c"))

    def test_earlier_enemy_gets_the_zone_rule_hint(self):
        r = run(both(second=level("s2", enc("e2", {"c": 6, "a": 1}))))
        w = next(x for x in r["warnings"] if x["code"] == "enemy_not_in_stage")
        self.assertIn("zone_rule", w["message"])

    def test_stage_that_already_keeps_earlier_enemies_gets_no_hint(self):
        combat = {"stages": [{"id": "s1", "zone": 1}, {"id": "s2", "zone": 2, "zone_rule": "up_to", "enemies": ["c"]}]}
        r = run(both(second=level("s2", enc("e2", {"c": 6, "a": 1}))), combat=combat)
        w = next(x for x in r["warnings"] if x["code"] == "enemy_not_in_stage")
        self.assertNotIn("zone_rule", w["message"])

    def test_enemy_the_stage_counts_but_no_encounter_places_is_warned(self):
        r = run(both(level("s1", enc(enemies={"a": 8}))))
        w = next(x for x in r["warnings"] if x["code"] == "enemy_unplaced")
        self.assertEqual((w["where"], w["owner"], w["part"]), ("s1", "s1", "b"))

    def test_several_levels_of_a_stage_place_its_enemies_together(self):
        r = run([level("s1a", enc("x", {"a": 8}), combat_stage="s1"), level("s1b", enc("y", {"b": 3}), combat_stage="s1"), level("s2", enc("e2", {"c": 6}))])
        self.assertEqual([w for w in r["warnings"] if w["code"] == "enemy_unplaced"], [])

    def test_broken_encounter_does_not_report_its_enemies_as_unplaced(self):
        r = run(both(level("s1", enc(enemies={"a": 0}))))
        self.assertNotIn("enemy_unplaced", codes(r["warnings"]))

    def test_cut_level_is_not_checked(self):
        r = run(both() + [level("gone_level", enc("z", {"nobody": 1}), status="cut")])
        self.assertEqual(r["errors"], [])
        self.assertEqual([x["id"] for x in r["levels"]], ["s1", "s2"])


class Kills(unittest.TestCase):
    def economy(self, *stages):
        return {"stages": list(stages)}

    def test_kills_within_tolerance_are_quiet(self):
        r = run(economy=self.economy({"id": "s1", "kills": {"a": 6, "b": 1}}))
        self.assertEqual(r["warnings"], [])

    def test_kills_past_tolerance_are_warned_with_their_target(self):
        r = run(economy=self.economy({"id": "s1", "kills": {"a": 20, "b": 1}}))
        w = r["warnings"][0]
        self.assertEqual((w["code"], w["where"], w["owner"], w["part"]), ("kills_differ", "s1", "s1", "a"))

    def test_edge_of_the_tolerance_is_inside(self):
        r = run(budget={**BUDGET, "kills_tolerance": 0.25}, economy=self.economy({"id": "s1", "kills": {"a": 4, "b": 1}}))
        self.assertEqual(r["warnings"], [])

    def test_an_enemy_only_one_side_counts_is_warned(self):
        r = run(economy=self.economy({"id": "s1", "kills": {"a": 5}}))
        self.assertEqual([w["part"] for w in r["warnings"]], ["b"])
        r = run(both(level("s1", enc(enemies={"a": 5}), enc("e9", {"b": 1}))), economy=self.economy({"id": "s1", "kills": {"a": 5, "b": 1, "c": 2}}))
        self.assertIn("c", [w["part"] for w in r["warnings"] if w["code"] == "kills_differ"])

    def test_repeat_counts(self):
        r = run(both(level("s1", enc(repeat=4))), economy=self.economy({"id": "s1", "kills": {"a": 20, "b": 4}}))
        self.assertEqual(r["warnings"], [])

    def test_economy_stages_link_by_combat_stage_and_add_up(self):
        r = run(economy=self.economy({"id": "x", "combat_stage": "s1", "kills": {"a": 3, "b": 1}}, {"id": "y", "combat_stage": "s1", "kills": {"a": 2}}))
        self.assertEqual(r["warnings"], [])

    def test_economy_stage_with_another_id_is_compared_through_its_link(self):
        r = run(economy=self.economy({"id": "x", "combat_stage": "s1", "kills": {"a": 90, "b": 1}}))
        self.assertEqual(codes(r["warnings"]), ["kills_differ"])

    def test_levels_of_a_stage_add_up(self):
        r = run([level("s1a", enc("x", {"a": 3, "b": 1}), combat_stage="s1"), level("s1b", enc("y", {"a": 2}), combat_stage="s1"), level("s2", enc("e2", {"c": 6}))],
                economy=self.economy({"id": "s1", "kills": {"a": 5, "b": 1}}))
        self.assertNotIn("kills_differ", codes(r["warnings"]))

    def test_cut_economy_stage_is_ignored(self):
        r = run(economy=self.economy({"id": "s1", "kills": {"a": 90}, "status": "cut"}))
        self.assertEqual(r["warnings"], [])

    def test_economy_stage_without_kills_is_not_compared(self):
        self.assertEqual(run(economy=self.economy({"id": "s1"}))["warnings"], [])

    def test_stage_with_a_broken_encounter_is_not_compared(self):
        r = run(both(level("s1", enc(), enc("bad", {"a": 0}))), economy=self.economy({"id": "s1", "kills": {"a": 90}}))
        self.assertNotIn("kills_differ", codes(r["warnings"]))

    def test_no_economy_is_not_incomplete(self):
        self.assertEqual(run()["unchecked"], 0)


class Unchecked(unittest.TestCase):
    def test_full_data_is_complete(self):
        r = run()
        self.assertEqual((r["unchecked"], r["unchecked_kinds"]), (0, []))

    def test_missing_enemies(self):
        r = run(enemies=None, threat=None)
        self.assertIn("enemies", r["unchecked_kinds"])
        self.assertIsNone(row(r)["threat"])
        self.assertEqual(r["errors"], [])

    def test_missing_combat(self):
        r = run(combat=None)
        self.assertIn("combat", r["unchecked_kinds"])
        self.assertIsNone(row(r)["expected"])
        self.assertEqual(row(r)["threat"], 80)

    def test_table_curve_does_not_need_the_stage_order(self):
        b = {**BUDGET, "curve": {"growth": "table", "values": {"s1": 80, "s2": 120}}}
        self.assertEqual(row(run(budget=b, combat=None))["expected"], 80)

    def test_missing_budget(self):
        r = run(budget=None)
        self.assertIn("threat_budget", r["unchecked_kinds"])
        self.assertEqual(row(r)["threat"], 80)

    def test_nothing_computed(self):
        self.assertIn("nothing", run([])["unchecked_kinds"])
        self.assertIn("nothing", run([level("s1", status="cut")])["unchecked_kinds"])

    def test_stage_without_a_level_is_not_a_pass(self):
        r = run([level("s1")])
        self.assertIn("stages", r["unchecked_kinds"])
        self.assertEqual(r["stages_without_levels"], ["s2"])

    def test_level_with_no_encounters_does_not_cover_its_stage(self):
        self.assertEqual(run(both(second={"id": "s2", "encounters": []}))["stages_without_levels"], ["s2"])


class Gate(unittest.TestCase):
    def test_assumed_levels_and_budget_are_unverified(self):
        self.assertEqual(run()["unverified"], ["threat_budget(위협도 예산)", "s1", "s2"])

    def test_measured_values_leave_the_list(self):
        src = {"kind": "measured", "source": "data/playtests.json#x"}
        r = run(both(level("s1", provenance=src), level("s2", enc("e2", {"c": 6}), provenance=src)), budget={**BUDGET, "provenance": src})
        self.assertEqual(r["unverified"], [])


class Workspace(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "game"
        shutil.copytree(SAMPLE, self.root)

    def edit(self, rel, fn):
        p = self.root / rel
        d = json.loads(p.read_text(encoding="utf-8"))
        fn(d)
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")

    def report(self):
        return next(d for d in datasets.collect([self.root]) if d["kind"] == "levels")["report"]

    def test_sample_is_clean_and_complete(self):
        r = self.report()
        self.assertEqual((r["errors"], r["warnings"], r["unchecked"]), ([], [], 0))
        self.assertTrue(r["levels"])

    def test_threat_uses_the_budget_costs_when_there_are_any(self):
        before = self.report()["levels"][0]["threat"]
        self.edit("data/budget.json", lambda d: d["budget"]["enemies"]["costs"].__setitem__("damage", 2.0))
        self.assertGreater(self.report()["levels"][0]["threat"], before)

    def test_threat_matches_the_enemy_report(self):
        reports = {d["kind"]: d["report"] for d in datasets.collect([self.root])}
        first = reports["levels"]["levels"][0]["encounters"][0]
        self.assertEqual(first["threat"], round(sum(n * reports["enemies"]["scores"][k] for k, n in first["enemies"].items()), 4))

    def test_threat_falls_back_to_threat_weights(self):
        (self.root / "data/budget.json").unlink()
        self.assertIsNotNone(self.report()["levels"][0]["threat"])

    def test_kills_are_compared_with_the_economy_in_the_project(self):
        self.edit("data/economy.json", lambda d: d["stages"][0]["kills"].__setitem__("slime", 400))
        # 처치가 늘면 수입이 늘어 표본의 구매가 대장간 시각보다 앞당겨진다
        self.assertEqual([(w["code"], w["part"]) for w in self.report()["warnings"]], [("kills_differ", "slime"), ("purchase_off_span", "weapon_plus_2")])

    def test_enemy_with_broken_stats_leaves_its_encounter_unscored(self):
        self.edit("data/enemies.json", lambda d: d["enemies"][0].__setitem__("stats", {"hp": "많음"}))
        r = self.report()
        self.assertIsNone(r["levels"][0]["encounters"][0]["threat"])
        self.assertIsNone(r["levels"][0]["threat"])
        self.assertIsNotNone(r["levels"][1]["threat"])

    def test_warning_can_be_acknowledged_for_its_target(self):
        def grow(d):
            d["levels"][0]["encounters"][0]["enemies"]["slime"] *= 10
            d["levels"][0]["acknowledged"] = {"over_budget": {d["levels"][0]["encounters"][0]["id"]: "여기만 일부러 어렵다"}}
        self.edit("data/levels.json", grow)
        r = self.report()
        self.assertNotIn("over_budget", codes(r["warnings"]))
        self.assertIn("over_budget", codes(r["acknowledged"]))

    def test_command_prints_levels_and_a_table(self):
        code, out = run_cli("check", self.root)
        self.assertEqual(code, 0)
        self.assertIn("레벨 ", out)
        code, out = run_cli("check", self.root, "--table", "levels")
        self.assertEqual(code, 0)
        self.assertIn("| 레벨 | 조우 |", out)

    def test_levels_alone_are_incomplete(self):
        code, out = run_cli("check", self.root / "data/levels.json")
        self.assertEqual(code, 0)
        self.assertIn("INCOMPLETE", out)
        self.assertEqual(run_cli("check", self.root / "data/levels.json", "--strict")[0], 1)

    def test_gate_names_the_assumed_budget(self):
        code, out = run_cli("check", self.root, "--fail-on-assumed")
        self.assertEqual(code, 1)
        self.assertIn("threat_budget(위협도 예산)", out)

    def test_broken_shapes_do_not_stop_the_check(self):
        (self.root / "data/levels.json").write_text('{"levels": [{"id": "x", "encounters": [{"id": "y", "enemies": {"slime": [1]}}]}], "threat_budget": 3}', encoding="utf-8")
        self.assertEqual(run_cli("check", self.root)[0], 1)
        self.assertTrue(self.report()["errors"])


class SharedCurve(unittest.TestCase):
    def test_stat_budget_curves_still_need_a_field_but_level_curves_do_not(self):
        curve, errors = {"growth": "linear", "base": 10, "rate": 1}, []
        self.assertIsNone(bg.read_curve(curve, "x", errors))
        self.assertEqual(codes(errors), ["schema"])
        self.assertEqual(bg.read_curve(curve, "x", [], by=False)["base"], 10)


class ReviewUnits(unittest.TestCase):
    def test_null_budget_is_not_a_pass(self):
        r = lv.validate({"levels": both(), "threat_budget": None}, enemies=ENEMIES, threat=THREAT, combat=COMBAT)
        self.assertIn("threat_budget", r["unchecked_kinds"])

    def test_enemies_without_scores_are_not_a_pass(self):
        self.assertIn("enemies", run(threat=None)["unchecked_kinds"])

    def test_broken_economy_link_leaves_the_levels_alone(self):
        r = run(economy={"stages": [{"id": "s1", "combat_stage": ["s1"], "kills": {"a": 90}}]})
        self.assertEqual(r["warnings"], [])
        self.assertEqual(row(r)["threat"], 80)

    def test_unknown_enemy_keeps_its_stage_out_of_the_counts(self):
        r = run(both(level("s1", enc(enemies={"aa": 5, "b": 1}))), economy={"stages": [{"id": "s1", "kills": {"a": 5, "b": 1}}]})
        self.assertEqual(codes(r["errors"]), ["unknown_enemy"])
        self.assertEqual(r["warnings"], [])

    def test_alternative_maps_divide_their_repeat(self):
        third = 1 / 3
        maps = [level(f"m{n}", enc(f"e{n}", repeat=third), combat_stage="s1") for n in (1, 2, 3)]
        r = run(maps + [level("s2", enc("e2", {"c": 6}))], economy={"stages": [{"id": "s1", "kills": {"a": 5, "b": 1}}]})
        self.assertEqual(r["warnings"], [])

    def test_unknown_budget_keys_are_refused_with_a_hint(self):
        r = run(budget={**BUDGET, "tolerence": 0.1})
        self.assertIn("'tolerance'의 오타", r["errors"][0]["message"])
        r = run(budget={**BUDGET, "curve": {**BUDGET["curve"], "by": "zone"}})
        self.assertEqual(r["errors"][0]["where"], "threat_budget.curve")
        self.assertIn("by", r["errors"][0]["message"])

    def test_marked_budget_keys_are_allowed(self):
        r = run(budget={**BUDGET, "_memo": "x", "note": "y", "curve": {**BUDGET["curve"], "_memo": "x"}})
        self.assertEqual(r["errors"], [])

    def test_table_curve_keys_are_allowed(self):
        self.assertEqual(run(budget={**BUDGET, "curve": {"growth": "table", "values": {"s1": 80, "s2": 120}}})["errors"], [])

    def test_threat_budget_alone_is_still_this_kind(self):
        self.assertEqual(common.detect_kind({"threat_budget": {}}), "levels")


class ReviewProject(Workspace):
    def second_level(self, **over):
        def add(d):
            d["levels"].append({"id": "crypt2", "combat_stage": "zone_1", "encounters": [{"id": "c2", "role": "room", "repeat": 3, "enemies": {"slime": 9}}], **over})
        self.edit("data/levels.json", add)

    def test_broken_enemy_weights_leave_the_check_running(self):
        self.edit("data/enemies.json", lambda d: d.__setitem__("threat_weights", {"hp": "x"}))
        self.assertEqual(run_cli("check", self.root)[0], 2)
        self.assertIn("enemies", self.report()["unchecked_kinds"])
        (self.root / "data/levels.json").unlink()
        self.assertEqual(run_cli("check", self.root)[0], 2)

    def test_levels_do_not_depend_on_the_file_order(self):
        scanned = datasets.scan([self.root])
        names = [d["name"] for d in reversed(scanned)]
        checked = datasets.validate_all(list(reversed(scanned)))
        self.assertEqual([d["name"] for d in checked], names)
        self.assertIsNotNone(next(d for d in checked if d["kind"] == "levels")["report"]["levels"][0]["threat"])

    def test_game_own_levels_file_is_left_alone(self):
        (self.root / "data/levels.json").write_text('{"world": [1, 2]}', encoding="utf-8")
        self.assertEqual(run_cli("check", self.root)[0], 0)
        self.assertNotIn("levels", [d["kind"] for d in datasets.collect([self.root])])

    def test_levels_key_of_another_shape_is_reported(self):
        (self.root / "data/levels.json").write_text('{"levels": [{"name": "1-1"}]}', encoding="utf-8")
        self.assertEqual(run_cli("check", self.root)[0], 1)

    def test_file_with_only_a_budget_is_reported(self):
        (self.root / "data/levels.json").write_text('{"threat_budget": {"curve": {"base": 9, "rate": 1}, "roles": {"room": 1}}}', encoding="utf-8")
        self.assertEqual(run_cli("check", self.root)[0], 1)

    def test_other_names_still_ask_for_their_key(self):
        (self.root / "data/economy.json").write_text('{"world": 1}', encoding="utf-8")
        self.assertEqual(run_cli("check", self.root)[0], 2)

    def test_stage_warning_stays_on_the_first_level_without_an_acknowledgement(self):
        self.second_level()
        w = next(x for x in self.report()["warnings"] if x["code"] == "kills_differ")
        self.assertEqual(w["where"], "crypt")

    def test_stage_warning_can_be_acknowledged_on_any_of_its_levels(self):
        self.second_level(acknowledged={"kills_differ": {"slime": "선택 경로라 늘 지나지 않는다"}})
        r = self.report()
        self.assertNotIn("kills_differ", codes(r["warnings"]))
        self.assertEqual([x["where"] for x in r["acknowledged"]], ["crypt2"])

    def test_unplaced_enemy_can_be_acknowledged_on_any_of_its_levels(self):
        self.edit("data/levels.json", lambda d: d["levels"][2]["encounters"].pop(0))
        self.edit("data/levels.json", lambda d: d["levels"].append({"id": "altar2", "combat_stage": "zone_3", "encounters": [{"id": "a2", "role": "boss_room", "enemies": {"void_herald": 1}}],
                                                                    "acknowledged": {"enemy_unplaced": "이벤트로만 나온다"}}))
        self.assertIn("enemy_unplaced", codes(self.report()["acknowledged"]))

    def test_enemies_of_the_wrong_shape_are_not_a_pass(self):
        (self.root / "data/enemies.json").write_text('{"enemies": {}}', encoding="utf-8")
        self.assertIn("enemies", self.report()["unchecked_kinds"])

    def test_no_enemy_file_gives_no_scores(self):
        self.assertIsNone(datasets._threat_scores([]))

    def test_levels_file_that_cannot_be_parsed_is_not_a_pass(self):
        good = (self.root / "data/levels.json").read_text(encoding="utf-8")
        (self.root / "data/levels.json").write_text(good[:-3], encoding="utf-8")
        self.assertEqual(run_cli("check", self.root)[0], 2)

    def test_game_own_levels_file_with_comments_is_left_alone(self):
        (self.root / "data/levels.json").write_text('{ // 게임의 맵 목록\n "world": 1 }', encoding="utf-8")
        self.assertEqual(run_cli("check", self.root)[0], 0)

    def test_broken_economy_link_does_not_stop_calibrate(self):
        self.edit("data/economy.json", lambda d: d["stages"][0].__setitem__("combat_stage", ["zone_1"]))
        self.assertEqual(run_cli("calibrate", self.root)[0], 0)


class SecondReviewUnits(unittest.TestCase):
    def test_level_keys_are_refused_with_a_hint(self):
        r = run(both(level("s1", combat_stge="s2")))
        self.assertIn("'combat_stage'의 오타", r["errors"][0]["message"])

    def test_every_level_field_is_known(self):
        lvl = level("s1", name="n", combat_stage="s1", intent="i", status="approved", note="m", _memo="x", acknowledged={"over_budget": "이유"})
        self.assertEqual(run(both(lvl))["errors"], [])

    def test_cut_level_keys_are_not_checked(self):
        self.assertEqual(run(both() + [level("x", status="cut", oops=1)])["errors"], [])

    def test_curve_note_is_a_memo(self):
        self.assertEqual(run(budget={**BUDGET, "curve": {**BUDGET["curve"], "note": "x"}})["errors"], [])

    def test_level_threat_is_unknown_when_an_encounter_is_left_out(self):
        r = run(both(level("s1", enc(), enc("bad", {"a": 0}))))
        self.assertIsNone(r["levels"][0]["threat"])
        self.assertIsNone(run(both(level("s1", enc("only", {"a": 0}))))["levels"][0]["threat"])

    def test_level_without_encounters_has_no_threat_to_add(self):
        self.assertEqual(run(both(second={"id": "s2", "encounters": []}))["levels"][1]["threat"], 0)

    def pair(self, second):
        return [level("s1a", enc("x", {"a": 3, "b": 1}), combat_stage="s1"), second, level("s2", enc("e2", {"c": 6}))]

    ECONOMY = {"stages": [{"id": "s1", "kills": {"a": 5, "b": 1}}]}

    def test_level_left_out_keeps_its_stage_out_of_the_counts(self):
        r = run(self.pair(level("s1b", enc("y", {"a": 2}), combat_stage="s1", provenance={"kind": "computed"})), economy=self.ECONOMY)
        self.assertEqual(codes(r["errors"]), ["provenance"])
        self.assertNotIn("kills_differ", codes(r["warnings"]))

    def test_other_stages_are_still_compared_then(self):
        r = run(self.pair(level("s1b", enc("y", {"a": 2}), combat_stage="s1", provenance={"kind": "computed"})),
                economy={"stages": [{"id": "s2", "kills": {"c": 90}}]})
        self.assertIn("kills_differ", codes(r["warnings"]))

    def test_level_of_an_unknown_stage_stops_every_stage_comparison(self):
        for bad in ({"combat_stage": "s9"}, {"combat_stage": 3}):
            with self.subTest(bad):
                r = run(self.pair(level("s1b", enc("y", {"a": 2}), **bad)), economy=self.ECONOMY)
                self.assertTrue(r["errors"])
                self.assertNotIn("kills_differ", codes(r["warnings"]))

    def test_cut_level_with_a_broken_source_does_not_stop_the_comparison(self):
        r = run(self.pair(level("s1b", enc("y", {"a": 2}), combat_stage="s1", status="cut", provenance={"kind": "computed"})),
                economy={"stages": [{"id": "s1", "kills": {"a": 90, "b": 1}}]})
        self.assertIn("kills_differ", codes(r["warnings"]))

    def test_cut_level_does_not_stop_the_comparison(self):
        r = run(self.pair(level("s1b", enc("y", {"a": 90}), combat_stage="s1", status="cut")), economy={"stages": [{"id": "s1", "kills": {"a": 90, "b": 1}}]})
        self.assertIn("kills_differ", codes(r["warnings"]))


class SecondReviewProject(Workspace):
    def test_broken_game_files_with_the_word_are_left_alone(self):
        (self.root / "data/rooms.json").write_text('{ // 방 목록\n "encounters": [] }', encoding="utf-8")
        (self.root / "data/rooms.csv").write_text('"id","encounters"\n"a","3"\n', encoding="utf-8")
        (self.root / "data/spawns.csv").write_text('"levels","encounters","threat_budget"\n"a","3","4"\n', encoding="utf-8")
        self.assertEqual(run_cli("check", self.root)[0], 0)

    def test_broken_budget_file_is_read_as_levels(self):
        (self.root / "data/levels.json").write_text('{ "threat_budget": { ', encoding="utf-8")
        self.assertEqual(run_cli("check", self.root)[0], 2)

    def test_file_name_wins_over_the_marks(self):
        (self.root / "data/enemies.json").write_text('{ "enemies": [ "threat_budget", ', encoding="utf-8")
        self.assertEqual([d["kind"] for d in datasets.scan([self.root]) if not d["ok"]], ["enemies"])

    def test_second_levels_file_is_an_error(self):
        data = json.loads((self.root / "data/levels.json").read_text(encoding="utf-8"))
        (self.root / "data/levels_late.json").write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(run_cli("check", self.root)[0], 1)
        reports = {d["name"]: d["report"] for d in datasets.collect([self.root]) if d["kind"] == "levels"}
        self.assertEqual(reports["levels.json"]["errors"], [])
        self.assertIn("levels.json", reports["levels_late.json"]["errors"][0]["message"])

    def test_broken_economy_id_does_not_stop_calibrate(self):
        self.edit("data/economy.json", lambda d: d["stages"][0].__setitem__("id", ["zone_1"]))
        self.assertEqual(run_cli("calibrate", self.root)[0], 0)


class SharedKeys(unittest.TestCase):
    def test_text_names_the_keys_and_keeps_memos(self):
        self.assertIsNone(common.unknown_keys_text({"a": 1, "_b": 2}, {"a"}))
        self.assertIn("'repeat'의 오타", common.unknown_keys_text({"repeats": 1}, {"repeat"}))

    def test_stage_records_and_groups_keep_memos(self):
        s = {"id": "s", "date": "2026-11-05", "concept": "c", "build": "b", "players": ["p"], "runs": 3, "observations": [],
             "groups": [{"upgrades": [], "_memo": "x", "stage_stats": [{"stage": "a", "entered": 1, "cleared": 1, "_memo": "y"}]}]}
        self.assertEqual(playtests.validate({"playtests": [s]}, {"c": {"approved": False, "hypotheses": []}})["errors"], [])

    def test_stage_records_still_refuse_typos(self):
        s = {"id": "s", "date": "2026-11-05", "concept": "c", "build": "b", "players": ["p"], "runs": 3, "upgrades": [],
             "stage_stats": [{"stage": "a", "entered": 1, "cleared": 1, "levl": 2}]}
        self.assertIn("'level'의 오타", playtests.validate({"playtests": [s]}, {"c": {"approved": False, "hypotheses": []}})["errors"][0]["message"])


class ThirdReviewUnits(unittest.TestCase):
    ECONOMY = {"stages": [{"id": "s1", "kills": {"a": 5, "b": 1}}]}

    def test_level_without_a_usable_id_stops_every_stage_comparison(self):
        for bad in (level("S1b", enc("y", {"a": 2}), combat_stage="s1"), "s1b"):
            with self.subTest(bad):
                r = run([level("s1a", enc("x", {"a": 3, "b": 1}), combat_stage="s1"), bad, level("s2", enc("e2", {"c": 6}))], economy=self.ECONOMY)
                self.assertTrue(r["errors"])
                self.assertNotIn("kills_differ", codes(r["warnings"]))

    def test_economy_kills_that_reach_no_level_are_warned(self):
        r = run(economy={"stages": [{"id": "part_1", "kills": {"a": 900}}]})
        self.assertEqual([(w["code"], w["where"], w["owner"], w["part"]) for w in r["warnings"]], [("kills_not_linked", "part_1", "s1", "part_1")])

    def test_stage_that_only_lacks_a_level_is_left_to_the_gap_report(self):
        r = run([level("s1")], economy={"stages": [{"id": "s2", "kills": {"c": 9}}]})
        self.assertEqual(r["warnings"], [])
        self.assertIn("stages", r["unchecked_kinds"])

    def test_economy_without_kills_is_not_warned(self):
        self.assertEqual(run(economy={"stages": [{"id": "part_1"}, {"id": "part_2", "kills": {}}]})["warnings"], [])

    def test_unlinked_kills_can_be_acknowledged_on_any_level(self):
        data = {"levels": both(second=level("s2", enc("e2", {"c": 6}), acknowledged={"kills_not_linked": {"part_1": "훈련장은 레벨이 아니다"}})), "threat_budget": BUDGET}
        r = lv.validate(data, enemies=ENEMIES, threat=THREAT, combat=COMBAT, economy={"stages": [{"id": "part_1", "kills": {"a": 9}}]})
        self.assertEqual(r["warnings"][0]["owner"], "s2")
        common.apply_acknowledged("levels", data, r)
        self.assertEqual(r["warnings"], [])

    def test_no_level_to_own_the_warning_is_not_a_crash(self):
        self.assertEqual(run([], economy={"stages": [{"id": "part_1", "kills": {"a": 9}}]})["warnings"], [])

    def test_unknown_level_stage_leaves_the_link_question_open(self):
        r = run(both(level("s1", combat_stage="s9")), economy={"stages": [{"id": "part_1", "kills": {"a": 9}}]})
        self.assertNotIn("kills_not_linked", codes(r["warnings"]))

    def test_dropped_level_of_that_stage_is_not_called_unlinked(self):
        r = run(both() + [level("x", combat_stage="part_1", provenance={"kind": "computed"})], combat=None, economy={"stages": [{"id": "part_1", "kills": {"a": 9}}]})
        self.assertNotIn("kills_not_linked", codes(r["warnings"]))

    def test_without_combat_data_an_unmatched_stage_is_still_named(self):
        r = run(combat=None, economy={"stages": [{"id": "part_1", "kills": {"a": 9}}]})
        self.assertEqual(codes(r["warnings"]), ["kills_not_linked"])

    def test_without_combat_data_a_matching_level_counts_as_linked(self):
        r = run(combat=None, economy={"stages": [{"id": "s1", "kills": {"a": 5, "b": 1}}]})
        self.assertNotIn("kills_not_linked", codes(r["warnings"]))

    def test_cut_level_does_not_own_the_warning(self):
        r = run([level("gone_level", status="cut")] + both(), economy={"stages": [{"id": "part_1", "kills": {"a": 9}}]})
        self.assertEqual(r["warnings"][0]["owner"], "s1")

    def test_missing_table_value_has_its_own_code(self):
        r = run(budget={**BUDGET, "curve": {"growth": "table", "values": {"s1": 80}}})
        self.assertEqual(codes(r["errors"]), ["curve_missing_point"])

    def test_curve_that_falls_to_nothing_keeps_its_code(self):
        r = run(budget={**BUDGET, "curve": {"growth": "linear", "base": 80, "rate": -80}})
        self.assertEqual(codes(r["errors"]), ["curve_not_positive"])


class ThirdReviewProject(Workspace):
    def sourced(self):
        for name in ("meta.json", "meta_combat.json"):
            self.edit(f"data/{name}", lambda d: d.__setitem__("provenance", {"kind": "computed", "source": "reports/calibrate.json"}))

    def test_game_files_with_one_config_key_stay_out_of_the_gate(self):
        self.sourced()
        (self.root / "data/waves.csv").write_text('"seed","trials","max_runs"\n"1","2","3"\n', encoding="utf-8")
        (self.root / "data/settings.json").write_text('{ // 게임 설정\n "max_runs": 3 }', encoding="utf-8")
        self.assertEqual(datasets.unverified_configs([self.root]), [])

    def test_broken_config_is_still_caught(self):
        self.sourced()
        p = self.root / "data/meta_combat.json"
        p.write_text(p.read_text(encoding="utf-8")[:-1], encoding="utf-8")
        self.assertEqual([Path(x).name for x in datasets.unverified_configs([self.root])], ["meta_combat.json"])


class Registration(unittest.TestCase):
    def test_format_doc_lists_every_code(self):
        fmt = (ROOT / "skills/level-design/references/levels-format.md").read_text(encoding="utf-8")
        source = (STUDIO / "scripts/studio_data/levels.py").read_text(encoding="utf-8")
        for code in set(re.findall(r'_err\(\w+, "(\w+)"', source)) | {"over_budget", "under_budget"}:
            self.assertIn(f"`{code}`", fmt, code)
        row = next(x for x in fmt.splitlines() if x.startswith("| `schema` |"))
        for word in ("레벨", "예산", "곡선", "파일"):
            self.assertIn(word, row)

    def test_level_tab_shows_status_and_source(self):
        page = (STUDIO / "assets/viewer.html").read_text(encoding="utf-8")
        body = page[page.index("function renderLevels"):page.index("function renderPlaytests")]
        self.assertIn("statusPill(lv)", body)
        self.assertIn("sourcePill(lv)", body)
        self.assertIn("sourcePill(cfg)", body)

    def test_viewer_filter_counts_encounter_issues(self):
        page = (STUDIO / "assets/viewer.html").read_text(encoding="utf-8")
        self.assertIn("function entryIssues", page)
        self.assertRegex(page, r"for \(const lv of list\.filter\(\(e\) => matches\(ds, e, entryIssues\(idx, e\.id\)\)\)\)")

    def test_viewer_file_mode_knows_a_budget_only_file(self):
        self.assertRegex((STUDIO / "assets/viewer.html").read_text(encoding="utf-8"), r'"threat_budget" in data \? "levels"')

    def test_lists_of_kinds_name_levels(self):
        for rel in ("README.md", "skills/studio-data/SKILL.md", "skills/studio-data/scripts/studio.py", "skills/studio-data/scripts/studio_data/cli.py",
                    "skills/studio-data/scripts/studio_data/datasets.py", "skills/studio-data/assets/viewer.html"):
            self.assertNotIn("재화 흐름·플레이 기록", (ROOT / rel).read_text(encoding="utf-8"), rel)
        doc = (STUDIO / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("`economy`, `levels`", doc)

    def test_docs_explain_stage_wide_rules(self):
        fmt = (ROOT / "skills/level-design/references/levels-format.md").read_text(encoding="utf-8")
        for word in ("대체 맵", "어느 레벨에서든"):
            self.assertIn(word, fmt)
        self.assertIn("대체 맵", (ROOT / "skills/level-design/SKILL.md").read_text(encoding="utf-8"))

    def test_kind_is_registered_everywhere(self):
        self.assertIn("levels", common.DATASET_KINDS)
        self.assertIn("levels", datasets.VALIDATORS)
        page = (STUDIO / "assets/viewer.html").read_text(encoding="utf-8")
        self.assertRegex(page, r"const KIND_ORDER = \[[^\]]*\"levels\"")
        self.assertIn("function renderLevels", page)

    def test_viewer_names_every_code_and_gap(self):
        page = (STUDIO / "assets/viewer.html").read_text(encoding="utf-8")
        source = (STUDIO / "scripts/studio_data/levels.py").read_text(encoding="utf-8")
        for code in set(re.findall(r'_err\(\w+, "(\w+)"', source)) - {"schema"}:
            self.assertRegex(page, rf"\b{code}: \"", code)
        for gap in ("threat_budget", "stages", "enemies", "combat"):
            self.assertRegex(page, rf"unchecked: \{{[^}}]*\b{gap}: \"", gap)

    def test_skill_is_documented(self):
        skill = (ROOT / "skills/level-design/SKILL.md").read_text(encoding="utf-8")
        self.assertRegex(skill.split("---")[1], r"description: \"[A-Z]")
        self.assertTrue((ROOT / "skills/level-design/references/levels-format.md").is_file())
        self.assertTrue((ROOT / "skills/level-design/agents/openai.yaml").is_file())
        self.assertIn("(skills/level-design/SKILL.md)", (ROOT / "README.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
