"""전투 계산(combat) 테스트: 방어 공식, 기대 피해, 처치·버팀 계산, 목표 범위, 파일 간 참조. 표준 라이브러리 unittest만 사용한다."""
import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from _studio import SAMPLE, combat as cb, common, run_cli

ROLES = {"player": {"hp": "max_hp", "attack": "attack", "defense": "armor", "attack_rate": "attack_speed", "crit_chance": "crit_chance"},
         "enemy": {"hp": "hp", "attack": "damage", "defense": "armor", "attack_rate": "attack_rate"}}


def codes(entries):
    return [e["code"] for e in entries]


def data(defense=None, stages=None, targets=None):
    return {"combat": {"stats": copy.deepcopy(ROLES), "defense": defense or {"form": "ratio", "k": 100}, "targets": targets or {}},
            "stages": stages if stages is not None else [stage()]}


def stage(sid="s1", **over):
    s = {"id": sid, "level": 1, "player": {"base": {"max_hp": 100, "attack": 10, "attack_speed": 1.0}, "items": [], "upgrades": []},
         "enemies": ["slime"]}
    s.update(over)
    return s


ENEMIES = {"slime": {"id": "slime", "rank": "normal", "zone": 1, "stats": {"hp": 30, "damage": 5}},
           "golem": {"id": "golem", "rank": "elite", "zone": 1, "stats": {"hp": 200, "damage": 20, "armor": 100}},
           "ghost": {"id": "ghost", "rank": "normal", "zone": 1, "stats": {"hp": 10, "damage": 1}, "status": "cut"}}
ITEMS = {"sword": {"id": "sword", "stats": {"attack": 5}}, "vest": {"id": "vest", "stats": {"max_hp": 20, "armor": 10}},
         "old": {"id": "old", "stats": {"attack": 1}, "status": "cut"}}
UPGRADES = {"might_1": {"id": "might_1", "stats": {"attack": 2}},
            "might_2": {"id": "might_2", "stats": {"attack": 3}, "requires": ["might_1"]}}


def validate(d, items=ITEMS, upgrades=UPGRADES, enemies=ENEMIES):
    return cb.validate(d, items=items, upgrades=upgrades, enemies=enemies)


def row(report, sid, eid):
    return next(r for r in report["rows"] if r["stage"] == sid and r["enemy"] == eid)


class DefenseForms(unittest.TestCase):
    def test_flat_subtracts_with_a_floor(self):
        self.assertEqual(cb.hit_damage(10, 4, {"form": "flat"}), 6)
        self.assertEqual(cb.hit_damage(3, 10, {"form": "flat"}), 1)
        self.assertEqual(cb.hit_damage(3, 10, {"form": "flat", "min_damage": 0}), 0)
        self.assertEqual(cb.hit_damage(10, 4, {"form": "flat", "factor": 0.5}), 8)

    def test_ratio_halves_damage_at_k(self):
        self.assertEqual(cb.hit_damage(100, 0, {"form": "ratio", "k": 100}), 100)
        self.assertEqual(cb.hit_damage(100, 100, {"form": "ratio", "k": 100}), 50)

    def test_level_ratio_grows_k_with_stage_level(self):
        f = {"form": "level_ratio", "a": 50, "b": 0}
        self.assertEqual(cb.hit_damage(100, 100, f, level=2), 50)
        self.assertAlmostEqual(cb.hit_damage(100, 100, f, level=4), 100 * 200 / 300)

    def test_percent_is_capped(self):
        f = {"form": "percent", "cap": 80}
        self.assertEqual(cb.hit_damage(100, 50, f), 50)
        self.assertAlmostEqual(cb.hit_damage(100, 95, f), 20)

    def test_crit_is_an_expectation_per_hit(self):
        f = {"form": "ratio", "k": 100}
        self.assertEqual(cb.expected_hit(10, 0, f, crit_chance=0.5, crit_multiplier=2), 15)
        # 고정값 공식은 치명을 방어 전에 곱해야 기대값이 맞다: 0.5 × max(1, 10−8) + 0.5 × max(1, 20−8)
        self.assertEqual(cb.expected_hit(10, 8, {"form": "flat"}, crit_chance=0.5, crit_multiplier=2), 7)


class Rows(unittest.TestCase):
    def test_hits_and_time_to_kill_and_die(self):
        r = validate(data(stages=[stage(player={"base": {"max_hp": 100, "attack": 10, "attack_speed": 2.0}})]))
        self.assertEqual(r["errors"], [])
        x = row(r, "s1", "slime")
        self.assertEqual((x["hits_to_kill"], x["time_to_kill"]), (3, 1.5))
        self.assertEqual(x["hits_to_die"], 20)
        self.assertIsNone(x["time_to_die"])  # 적에게 공격 속도가 없으면 시간은 계산하지 않는다

    def test_partial_hits_round_up(self):
        r = validate(data(stages=[stage(player={"base": {"max_hp": 100, "attack": 12}})]))
        self.assertEqual(row(r, "s1", "slime")["hits_to_kill"], 3)  # 30 / 12 = 2.5 → 세 번 때려야 쓰러진다

    def test_items_and_upgrades_add_to_base(self):
        s = stage(player={"base": {"max_hp": 100, "attack": 10}, "items": ["sword", "vest"], "upgrades": ["might_1"]})
        r = validate(data(stages=[s]))
        self.assertEqual(r["stages"]["s1"]["player"], {"max_hp": 120, "attack": 17, "armor": 10})
        self.assertAlmostEqual(row(r, "s1", "slime")["enemy_hit"], 5 * 100 / 110, places=3)  # 보고서는 소수 4자리로 반올림한다

    def test_enemies_by_zone_skip_cut_ones(self):
        s = stage(enemies=None, zone=1)
        del s["enemies"]
        r = validate(data(stages=[s]))
        self.assertEqual(sorted(x["enemy"] for x in r["rows"]), ["golem", "slime"])

    def test_zero_damage_is_reported_not_divided(self):
        s = stage(player={"base": {"max_hp": 100, "attack": 1}}, enemies=["golem"])
        r = validate(data(defense={"form": "flat", "min_damage": 0}, stages=[s]))
        self.assertIn("zero_damage", codes(r["warnings"]))
        self.assertIsNone(row(r, "s1", "golem")["hits_to_kill"])


class Targets(unittest.TestCase):
    def test_out_of_range_is_a_warning_and_marks_the_metric(self):
        r = validate(data(targets={"normal": {"hits_to_kill": [1, 2]}}))
        self.assertEqual(codes(r["warnings"]), ["target_out_of_range"])
        self.assertEqual(row(r, "s1", "slime")["out_of_range"], ["hits_to_kill"])
        self.assertEqual(validate(data(targets={"normal": {"hits_to_kill": [1, 3], "hits_to_die": [10, None]}}))["warnings"], [])

    def test_bad_targets_are_schema_errors(self):
        for t in ({"normal": {"hits_to_kil": [1, 2]}}, {"champion": {"hits_to_kill": [1, 2]}}, {"normal": {"hits_to_kill": [3, 1]}}):
            with self.subTest(t):
                self.assertEqual(codes(validate(data(targets=t))["errors"]), ["schema"])


class ReviewFindings(unittest.TestCase):
    """코드 검토에서 나온 문제의 회귀 테스트."""

    def test_time_target_without_attack_rate_is_reported_not_skipped(self):
        r = validate(data(targets={"normal": {"time_to_die": [5, None]}}))
        self.assertEqual(codes(r["warnings"]), ["target_unchecked"])
        self.assertIn("attack_rate", r["warnings"][0]["message"])

    def test_crit_chance_outside_zero_to_one_is_an_error(self):
        s = stage(player={"base": {"max_hp": 100, "attack": 10, "crit_chance": 5}})
        self.assertEqual(codes(validate(data(stages=[s]))["errors"]), ["bad_stat"])

    def test_non_positive_hp_or_rate_is_an_error(self):
        foes = dict(ENEMIES, slime={"id": "slime", "rank": "normal", "zone": 1, "stats": {"hp": 0, "damage": 5}})
        self.assertEqual(codes(validate(data(), enemies=foes)["errors"]), ["bad_stat"])
        s = stage(player={"base": {"max_hp": 100, "attack": 10, "attack_speed": 0}})
        self.assertEqual(codes(validate(data(stages=[s]))["errors"]), ["bad_stat"])

    def test_cut_enemy_listed_in_a_stage_is_warned(self):
        r = validate(data(stages=[stage(enemies=["slime", "ghost"])]))
        self.assertEqual(codes(r["warnings"]), ["cut_referenced"])
        self.assertEqual([x["enemy"] for x in r["rows"]], ["slime"])

    def test_loadout_upgrade_without_its_prerequisite_is_warned(self):
        s = stage(player={"base": {"max_hp": 100, "attack": 10}, "upgrades": ["might_2"]})
        r = validate(data(stages=[s]))
        self.assertEqual(codes(r["warnings"]), ["requirement_missing"])
        self.assertIn("might_1", r["warnings"][0]["message"])
        s["player"]["upgrades"] = ["might_1", "might_2"]
        self.assertEqual(validate(data(stages=[s]))["warnings"], [])

    def test_row_warnings_name_their_stage_as_owner(self):
        r = validate(data(targets={"normal": {"hits_to_kill": [1, 2]}}))
        self.assertEqual(r["warnings"][0]["owner"], "s1")


class Schema(unittest.TestCase):
    def test_formula_params_are_checked(self):
        for f in ({"form": "armor"}, {"form": "ratio", "k": 0}, {"form": "percent", "cap": 120}, {"form": "flat", "factor": -1}):
            with self.subTest(f):
                self.assertEqual(codes(validate(data(defense=f))["errors"]), ["schema"])

    def test_level_ratio_needs_stage_levels(self):
        s = stage()
        del s["level"]
        r = validate(data(defense={"form": "level_ratio", "a": 50, "b": 0}, stages=[s]))
        self.assertEqual(codes(r["errors"]), ["schema"])

    def test_roles_need_hp_and_attack_on_both_sides(self):
        d = data()
        del d["combat"]["stats"]["enemy"]["attack"]
        self.assertIn("schema", codes(validate(d)["errors"]))
        d = data()
        d["combat"]["stats"]["player"]["armr"] = "armor"
        self.assertIn("armr", " ".join(e["message"] for e in validate(d)["errors"]))

    def test_missing_required_stat_is_an_error(self):
        r = validate(data(stages=[stage(player={"base": {"attack": 10}})]))
        self.assertEqual(codes(r["errors"]), ["missing_stat"])

    def test_negative_defense_with_ratio_is_an_error(self):
        r = validate(data(stages=[stage(player={"base": {"max_hp": 100, "attack": 10, "armor": -5}})]))
        self.assertEqual(codes(r["errors"]), ["negative_defense"])


class References(unittest.TestCase):
    def test_unknown_and_cut_references(self):
        s = stage(player={"base": {"max_hp": 100, "attack": 10}, "items": ["nope", "old"], "upgrades": ["nope_up"]}, enemies=["slime", "who"])
        r = validate(data(stages=[s]))
        self.assertEqual(sorted(codes(r["errors"])), ["unknown_enemy", "unknown_item", "unknown_upgrade"])
        self.assertEqual(codes(r["warnings"]), ["cut_referenced"])

    def test_cut_items_are_left_out_of_the_sum(self):
        s = stage(player={"base": {"max_hp": 100, "attack": 10}, "items": ["old", "sword"]})
        r = validate(data(stages=[s]))
        self.assertEqual(r["stages"]["s1"]["player"]["attack"], 15)

    def test_stage_acknowledgement_covers_its_rows(self):
        s = stage(acknowledged={"target_out_of_range": "초반 일반 적은 일부러 단단하게"})
        d = data(stages=[s], targets={"normal": {"hits_to_kill": [1, 2]}})
        r = validate(d)
        common.apply_acknowledged("combat", d, r)
        self.assertEqual(r["warnings"], [])
        self.assertEqual([a["code"] for a in r["acknowledged"]], ["target_out_of_range"])

    def test_without_item_or_enemy_data_the_stage_is_unchecked(self):
        s = stage(player={"base": {"max_hp": 100, "attack": 10}, "items": ["sword"]})
        r = validate(data(stages=[s]), items=None)
        self.assertEqual(r["errors"], [])
        self.assertEqual(r["rows"], [])
        self.assertGreater(r["unchecked"], 0)
        self.assertGreater(validate(data(), enemies=None)["unchecked"], 0)


class CommandLine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "game"
        shutil.copytree(SAMPLE, self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_sample_combat_has_no_errors_or_warnings(self):
        code, out = run_cli("check", self.root, "--json")
        report = next(d["report"] for d in json.loads(out)["datasets"] if d["kind"] == "combat")
        self.assertEqual((report["errors"], report["warnings"], report["unchecked"]), ([], [], 0))
        self.assertGreater(len(report["rows"]), 0)

    def test_wrong_shaped_items_file_leaves_stages_unchecked_without_cascade(self):
        (self.root / "data/items.json").write_text(json.dumps({"items": {"oops": 1}}), encoding="utf-8")
        code, out = run_cli("check", self.root, "--json")
        report = next(d["report"] for d in json.loads(out)["datasets"] if d["kind"] == "combat")
        self.assertEqual(report["errors"], [])
        self.assertIn("items", report["unchecked_kinds"])

    def test_combat_file_alone_is_incomplete(self):
        code, out = run_cli("check", self.root / "data/combat.json")
        self.assertIn("INCOMPLETE", out)

    def test_table_prints_one_row_per_stage_and_enemy(self):
        code, out = run_cli("check", self.root, "--table")
        self.assertIn("| 단계 | 적 | 등급 |", out)
        self.assertIn("| zone_1 | slime |", out)


if __name__ == "__main__":
    unittest.main()
