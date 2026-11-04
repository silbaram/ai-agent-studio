"""레벨 구성 현장 시험(이슈 67~90) 테스트: 시험 프로젝트에서 실제로 막힌 것을 고친 동작. 표준 라이브러리 unittest만 사용한다."""
import io
import json
import unittest
from contextlib import redirect_stdout
from unittest import mock

import test_levels as base
from _studio import ROOT, STUDIO, cli, combat as cb, common, datasets, levels as lv, run_cli, viewer
from test_levels import BUDGET, COMBAT, both, codes, enc, level, row, run

TIMES = {"s1": {"a": 2.0, "b": 6.0}, "s2": {"c": 3.0}}
ECONOMY = {"economy": {}, "stages": [{"id": "s1", "duration": 60, "kills": {"a": 5, "b": 1}}, {"id": "s2", "duration": 30, "kills": {"c": 6}}]}
MEASURED = {"kind": "measured", "source": "data/playtests.json#x"}
ASSUMED = {"kind": "assumed"}
ENEMY_CURVE = {"by": "zone", "growth": "linear", "base": 10, "rate": 10}


def stage(result, sid="s1"):
    return next(x for x in result["stages"] if x["id"] == sid)


def notes(result):
    return "\n".join(result["notes"])


def printed(result):
    out = io.StringIO()
    with redirect_stdout(out):
        lv.print_extra(result)
    return out.getvalue()


def differ(result, enemy="a"):
    return next(w["message"] for w in result["warnings"] if w["code"] == "kills_differ" and w["part"] == enemy)


def stage_cells(result, sid="s1"):
    return next(x for x in lv.table({}, result).splitlines() if x.startswith(f"| {sid} | ") and x.count("|") == 9)


class EnemyRepeat(unittest.TestCase):
    """70번: 보스는 한 번, 곁의 무리는 다시 찬다."""

    def test_an_enemy_can_come_fewer_times_than_its_encounter(self):
        r = run(both(level("s1", enc(repeat=10, enemy_repeat={"b": 1}))))
        self.assertEqual(row(r)["threat"], 80)
        self.assertEqual(r["levels"][0]["kills"], {"a": 50, "b": 1})
        self.assertEqual(r["levels"][0]["threat"], 530)

    def test_the_row_keeps_it_for_the_table(self):
        self.assertEqual(row(run(both(level("s1", enc(repeat=3, enemy_repeat={"b": 1})))))["enemy_repeat"], {"b": 1})

    def test_kills_are_compared_with_it(self):
        eco = {"stages": [{"id": "s1", "kills": {"a": 50, "b": 1}}]}
        r = run(both(level("s1", enc(repeat=10, enemy_repeat={"b": 1}))), economy=eco)
        self.assertNotIn("kills_differ", codes(r["warnings"]))

    def test_it_names_only_enemies_of_the_encounter(self):
        r = run(both(level("s1", enc(enemies={"aa": 1, "b": 1}, enemy_repeat={"a": 1}))), enemies=None, threat=None)
        self.assertEqual(codes(r["errors"]), ["schema"])
        self.assertIn("'aa'의 오타", r["errors"][0]["message"])

    def test_counts_must_be_positive_numbers(self):
        for bad in ({"b": 0}, {"b": -1}, {"b": "1"}, ["b"], 2):
            r = run(both(level("s1", enc(enemy_repeat=bad))))
            self.assertEqual(codes(r["errors"]), ["schema"], bad)

    def test_cut_enemy_stays_out_of_the_counts(self):
        r = run(both(level("s1", enc(enemies={"a": 5, "b": 1, "gone": 1}, repeat=2, enemy_repeat={"gone": 1}))))
        self.assertEqual(r["levels"][0]["kills"], {"a": 10, "b": 2})


class EncounterSource(unittest.TestCase):
    """80번: 측정값 레벨 안의 가정 조우를 나누고, 처치 차이에 양쪽 출처를 붙인다."""

    def test_encounter_may_carry_its_own_source(self):
        self.assertEqual(run(both(level("s1", enc(provenance={"kind": "assumed"}))))["errors"], [])

    def test_assumed_encounter_in_a_measured_level_is_unverified(self):
        r = run(both(level("s1", enc(provenance={"kind": "assumed"}), provenance=MEASURED), level("s2", enc("e2", {"c": 6}), provenance=MEASURED)),
                budget={**BUDGET, "provenance": MEASURED})
        self.assertEqual(r["unverified"], ["s1.e1"])

    def test_an_assumed_level_is_not_listed_twice(self):
        r = run(both(level("s1", enc(provenance={"kind": "assumed"}))))
        self.assertNotIn("s1.e1", r["unverified"])

    def test_measured_encounter_is_not_listed(self):
        r = run(both(level("s1", enc(provenance=MEASURED), provenance=MEASURED), level("s2", enc("e2", {"c": 6}), provenance=MEASURED)),
                budget={**BUDGET, "provenance": MEASURED})
        self.assertEqual(r["unverified"], [])

    def test_cut_level_does_not_reach_the_gate(self):
        r = run(both() + [level("x", enc("z", {"a": 1}, provenance={"kind": "assumed"}), status="cut", provenance=MEASURED)])
        self.assertNotIn("x.z", r["unverified"])

    def test_broken_source_is_an_error(self):
        r = run(both(level("s1", enc(provenance={"kind": "guess"}))))
        self.assertEqual(codes(r["errors"]), ["provenance"])

    def test_encounter_text_fields_are_checked(self):
        self.assertEqual(codes(run(both(level("s1", enc(name=3))))["errors"]), ["schema"])

    def test_status_stays_a_level_key(self):
        r = run(both(level("s1", enc(status="proposed"))))
        self.assertEqual(codes(r["errors"]), ["schema"])

    def test_kills_differ_names_both_sources(self):
        eco = {"stages": [{"id": "s1", "kills": {"a": 50, "b": 1}, "provenance": {"kind": "assumed"}}]}
        w = next(x for x in run(economy=eco)["warnings"] if x["code"] == "kills_differ")
        self.assertIn("조우 가정", w["message"])
        self.assertIn("재화 흐름 가정", w["message"])

    def test_measured_economy_says_which_side_to_change(self):
        eco = {"stages": [{"id": "s1", "kills": {"a": 50, "b": 1}, "provenance": MEASURED}]}
        w = next(x for x in run(economy=eco)["warnings"] if x["code"] == "kills_differ")
        self.assertIn("재화 흐름이 측정값", w["message"])

    def test_measured_levels_say_which_side_to_change(self):
        eco = {"stages": [{"id": "s1", "kills": {"a": 50, "b": 1}, "provenance": {"kind": "assumed"}}]}
        r = run(both(level("s1", provenance=MEASURED)), economy=eco)
        w = next(x for x in r["warnings"] if x["code"] == "kills_differ")
        self.assertIn("조우가 측정값", w["message"])

    def test_economy_stage_without_kills_does_not_blur_the_source(self):
        eco = {"stages": [{"id": "a", "combat_stage": "s1", "kills": {"a": 50, "b": 1}, "provenance": MEASURED}, {"id": "b", "combat_stage": "s1", "kills": {}}]}
        w = next(x for x in run(economy=eco)["warnings"] if x["code"] == "kills_differ")
        self.assertIn("재화 흐름이 측정값", w["message"])

    def test_both_measured_gives_no_side(self):
        eco = {"stages": [{"id": "s1", "kills": {"a": 50, "b": 1}, "provenance": MEASURED}]}
        r = run(both(level("s1", provenance=MEASURED)), economy=eco)
        w = next(x for x in r["warnings"] if x["code"] == "kills_differ")
        self.assertNotIn("측정값이", w["message"])


class Comparison(unittest.TestCase):
    """78번: 앞 조우 대비 값, 레벨·판 합계, 단계 합이 줄어드는 곳."""

    def test_each_encounter_is_compared_with_the_one_before(self):
        r = run(both(level("s1", enc("x", {"a": 8}), enc("y", {"a": 12}))))
        self.assertIsNone(row(r, "x")["vs_previous"])
        self.assertEqual(row(r, "y")["vs_previous"], 1.5)

    def test_unknown_threat_breaks_the_comparison(self):
        r = run(both(level("s1", enc("x", {"a": 8}), enc("y", {"a": 12}))), threat={"c": 20.0})
        self.assertIsNone(row(r, "y")["vs_previous"])

    def test_run_total_adds_the_levels(self):
        self.assertEqual(run()["run_threat"], 200)

    def test_run_total_is_unknown_when_a_level_is(self):
        self.assertIsNone(run(threat={"a": 10.0, "b": 30.0})["run_threat"])

    def test_stage_total_adds_its_levels(self):
        r = run([level("s1a", enc("x", {"a": 8}), combat_stage="s1"), level("s1b", enc("y", {"b": 3}), combat_stage="s1"), level("s2", enc("e2", {"c": 6}))])
        self.assertEqual(stage(r)["threat"], 170)

    def test_stage_total_is_unknown_when_a_level_is(self):
        levels = [level("s1a", enc("x", {"a": 8}), combat_stage="s1"), level("s1b", enc("y", {"nobody": 3}), combat_stage="s1"), level("s2", enc("e2", {"c": 6}))]
        self.assertIsNone(stage(run(levels, enemies=None))["threat"])

    def test_stage_that_falls_below_the_one_before_is_noted(self):
        r = run(both(level("s1", enc(repeat=3)), level("s2", enc("e2", {"c": 6}))))
        self.assertIn("앞 단계 s1", notes(r))

    def test_rising_stages_are_quiet(self):
        self.assertNotIn("앞 단계", notes(run()))

    def test_stages_follow_the_combat_order(self):
        self.assertEqual([x["id"] for x in run(list(reversed(both())))["stages"]], ["s1", "s2"])


class KillTime(unittest.TestCase):
    """69번: 처치 수를 단계 시간 안에 해낼 수 있는가."""

    def test_encounter_time_is_one_pass(self):
        self.assertEqual(row(run(kill_times=TIMES))["kill_time"], 16)

    def test_stage_time_uses_the_kills_and_the_economy_length(self):
        r = run(both(level("s1", enc(repeat=10, enemy_repeat={"b": 1}))), kill_times=TIMES, economy=ECONOMY)
        self.assertEqual((stage(r)["kill_time"], stage(r)["duration"], stage(r)["kill_ratio"]), (106, 60, 1.77))

    def test_unit_that_is_not_seconds_gives_no_ratio(self):
        eco = {**ECONOMY, "economy": {"time_unit": "방"}}
        r = run(kill_times=TIMES, economy=eco)
        self.assertEqual((stage(r)["kill_time"], stage(r)["duration"], stage(r)["time_unit"], stage(r)["kill_ratio"]), (16, 60, "방", None))

    def test_economy_stages_of_one_combat_stage_add_up(self):
        eco = {"stages": [{"id": "x", "combat_stage": "s1", "duration": 10}, {"id": "y", "combat_stage": "s1", "duration": 30}]}
        self.assertEqual(stage(run(kill_times=TIMES, economy=eco))["duration"], 40)

    def test_cut_economy_stage_has_no_length(self):
        eco = {"stages": [{"id": "s1", "duration": 60, "status": "cut"}]}
        self.assertIsNone(stage(run(kill_times=TIMES, economy=eco))["duration"])

    def test_enemy_without_a_time_is_named(self):
        r = run(kill_times={"s1": {"a": 2.0}, "s2": {"c": 3.0}})
        self.assertIsNone(row(r)["kill_time"])
        self.assertEqual((stage(r)["kill_time"], stage(r)["kill_time_unknown"]), (10, ["b"]))

    def test_broken_encounter_gives_no_stage_time(self):
        r = run(both(level("s1", enc("x", {"a": 5}), enc("y", {"b": 0}))), kill_times=TIMES)
        self.assertIsNone(stage(r)["kill_time"])

    def test_without_times_nothing_is_claimed(self):
        r = run()
        self.assertIsNone(row(r)["kill_time"])
        self.assertIsNone(stage(r)["kill_time"])

    def test_printed_with_the_ratio(self):
        line = next(x for x in printed(run(kill_times=TIMES, economy=ECONOMY)).splitlines() if x.startswith("단계 s1"))
        self.assertIn("처치 시간 16초", line)
        self.assertIn("0.27배", line)


class BudgetBasis(unittest.TestCase):
    """68번: 초안에서 뽑은 곡선은 근거가 아니다. 곡선의 바깥 기준을 보인다."""

    def test_assumed_curve_says_what_inside_the_budget_means(self):
        self.assertIn("근거가 아닙니다", notes(run()))

    def test_measured_curve_does_not(self):
        self.assertNotIn("근거가 아닙니다", notes(run(budget={**BUDGET, "provenance": MEASURED})))

    def test_no_budget_no_note(self):
        self.assertNotIn("근거가 아닙니다", notes(run(budget=None)))

    def test_curve_reads_against_the_enemy_curve(self):
        r = run(enemy_curve=ENEMY_CURVE)
        self.assertEqual((stage(r)["group_size"], stage(r, "s2")["group_size"]), (8, 6))

    def test_enemy_curve_on_another_field_is_not_compared(self):
        self.assertIsNone(stage(run(enemy_curve={**ENEMY_CURVE, "by": "tier"}))["group_size"])

    def test_stage_without_a_zone_is_not_compared(self):
        combat = {"stages": [{"id": "s1", "enemies": ["a", "b"]}, {"id": "s2", "zone": 2}]}
        self.assertIsNone(stage(run(combat=combat, enemy_curve=ENEMY_CURVE))["group_size"])

    def test_table_enemy_curve_without_that_zone_is_not_compared(self):
        curve = {"by": "zone", "growth": "table", "values": {"2": 20}}
        r = run(enemy_curve=curve)
        self.assertIsNone(stage(r)["group_size"])
        self.assertEqual(stage(r, "s2")["group_size"], 6)


class StageRulesGuidance(unittest.TestCase):
    """71번: up_to는 앞 구역의 적이 모두 이어질 때만 맞다."""

    def test_earlier_enemy_hint_offers_both_ways(self):
        hint = cb.earlier_zone_hint(["a"], {"id": "s2", "zone": 2}, base.ENEMIES)
        self.assertIn("zone_rule", hint)
        self.assertIn("enemies 목록", hint)

    def test_stage_with_a_list_points_at_the_list(self):
        hint = cb.earlier_zone_hint(["a"], {"id": "s2", "zone": 2, "enemies": ["c"]}, base.ENEMIES)
        self.assertNotIn("zone_rule", hint)
        self.assertIn("enemies 목록", hint)

    def test_hint_reads_without_a_particle_on_an_id(self):
        self.assertNotIn("a는", cb.earlier_zone_hint(["a"], {"id": "s2", "zone": 2}, base.ENEMIES))

    def test_unplaced_enemy_says_how_to_drop_it(self):
        r = run(both(level("s1", enc(enemies={"a": 8}))))
        w = next(x for x in r["warnings"] if x["code"] == "enemy_unplaced")
        self.assertIn("enemies 목록", w["message"])
        self.assertIn("acknowledged", w["message"])


class Order(unittest.TestCase):
    """75번: 곡선이 단계 순서로 읽히는 것을 보인다."""

    def test_stage_shows_its_position(self):
        self.assertEqual((stage(run())["position"], stage(run(), "s2")["position"]), (1, 2))

    def test_warning_says_a_cut_stage_moved_the_budget(self):
        r = run(both(second=level("s2", enc("e2", {"c": 20}))))
        w = next(x for x in r["warnings"] if x["code"] == "over_budget")
        self.assertIn("old", w["message"])
        self.assertIn("3 → 2", w["message"])

    def test_stage_before_the_cut_is_not_told(self):
        r = run(both(level("s1", enc(enemies={"a": 50}))))
        w = next(x for x in r["warnings"] if x["code"] == "over_budget")
        self.assertNotIn("당겨", w["message"])

    def test_table_curve_does_not_shift(self):
        b = {**BUDGET, "curve": {"growth": "table", "values": {"s1": 80, "s2": 120, "old": 100}}}
        r = run(both(second=level("s2", enc("e2", {"c": 20}))), budget=b)
        w = next(x for x in r["warnings"] if x["code"] == "over_budget")
        self.assertNotIn("당겨", w["message"])

    def test_table_shows_the_position(self):
        data = {"levels": both(), "threat_budget": BUDGET}
        self.assertIn("| s2 | 2 |", lv.table(data, run()))


class KillCheck(unittest.TestCase):
    """77번: 처치 수를 맞춰 보지 못한 것이 PASS에 묻히지 않는다."""

    def test_full_comparison_is_reported(self):
        self.assertIn("처치 수 대조: 2/2 단계", notes(run(economy=ECONOMY)))

    def test_missing_economy_is_reported(self):
        self.assertIn("재화 흐름을 함께 읽지 않아", notes(run()))

    def test_stage_without_kills_is_named(self):
        eco = {"stages": [{"id": "s1", "kills": {"a": 5, "b": 1}}, {"id": "s2", "duration": 30}]}
        text = notes(run(economy=eco))
        self.assertIn("처치 수 대조: 1/2 단계", text)
        self.assertIn("재화 흐름에 처치 수가 없는 단계: s2", text)

    def test_empty_kills_are_the_same_as_none(self):
        eco = {"stages": [{"id": "s1", "kills": {"a": 5, "b": 1}}, {"id": "s2", "kills": {}}]}
        r = run(economy=eco)
        self.assertNotIn("kills_differ", codes(r["warnings"]))
        self.assertIn("재화 흐름에 처치 수가 없는 단계: s2", notes(r))

    def test_broken_stage_is_named_with_its_own_reason(self):
        r = run(both(level("s1", enc("x", {"a": 5}), enc("y", {"b": 0}))), economy=ECONOMY)
        text = notes(r)
        self.assertIn("처치 수 대조: 1/2 단계", text)
        self.assertIn("오류로 못 본 단계: s1", text)

    def test_stage_without_encounters_is_not_called_an_error(self):
        text = notes(run(both(level("s1", encounters=[])), economy=ECONOMY))
        self.assertIn("처치 수 대조: 1/2 단계", text)
        self.assertIn("조우가 없는 단계: s1", text)
        self.assertNotIn("오류", text)

    def test_empty_and_broken_stages_are_told_apart(self):
        text = notes(run(both(level("s1", encounters=[]), level("s2", enc("x", {"c": 6}), enc("y", {"c": 0}))), economy=ECONOMY))
        self.assertIn("조우가 없는 단계: s1", text)
        self.assertIn("오류로 못 본 단계: s2", text)


class GroupedWarnings(unittest.TestCase):
    """83번, 84번: 같은 원인을 한 줄로, 삭제된 적은 삭제 경고만."""

    def test_one_line_per_stage_and_enemy(self):
        r = run(both(level("s1", enc("x", {"a": 5, "b": 1, "c": 1}), enc("y", {"a": 5, "c": 2}))))
        rows = [w for w in r["warnings"] if w["code"] == "enemy_not_in_stage"]
        self.assertEqual([(w["part"], w["owner"]) for w in rows], [("c", "s1")])
        self.assertIn("x, y", rows[0]["message"])

    def test_it_can_be_acknowledged_from_any_level_of_the_stage(self):
        levels = [level("s1a", enc("x", {"a": 5, "b": 1, "c": 1}), combat_stage="s1"),
                  level("s1b", enc("y", {"c": 2}), combat_stage="s1", acknowledged={"enemy_not_in_stage": {"c": "이 구역에 섞어 둔다"}}),
                  level("s2", enc("e2", {"c": 6}))]
        data = {"levels": levels, "threat_budget": BUDGET}
        r = lv.validate(data, enemies=base.ENEMIES, threat=base.THREAT, combat=COMBAT)
        common.apply_acknowledged("levels", data, r)
        self.assertNotIn("enemy_not_in_stage", codes(r["warnings"]))
        self.assertIn("enemy_not_in_stage", codes(r["acknowledged"]))

    def test_cut_enemy_gets_the_cut_warning_only(self):
        eco = {"stages": [{"id": "s1", "kills": {"a": 5, "b": 1, "gone": 40}}]}
        r = run(both(level("s1", enc(enemies={"a": 5, "b": 1, "gone": 3}))), economy=eco)
        self.assertIn("cut_referenced", codes(r["warnings"]))
        self.assertNotIn("kills_differ", codes(r["warnings"]))

    def test_cut_enemy_only_in_the_economy_is_left_to_the_economy(self):
        eco = {"stages": [{"id": "s1", "kills": {"a": 5, "b": 1, "gone": 40}}]}
        self.assertNotIn("kills_differ", codes(run(economy=eco)["warnings"]))


class KillsTolerance(unittest.TestCase):
    """85번: 위협도와 처치 수의 허용 오차는 성격이 달라 따로 둔다."""

    ECO = {"stages": [{"id": "s1", "kills": {"a": 10, "b": 1}}]}

    def test_loose_budget_does_not_loosen_the_kills(self):
        r = run(budget={**BUDGET, "tolerance": 0.9}, economy=self.ECO)
        self.assertIn("kills_differ", codes(r["warnings"]))

    def test_kills_have_their_own_key(self):
        r = run(budget={**BUDGET, "kills_tolerance": 0.6}, economy=self.ECO)
        self.assertNotIn("kills_differ", codes(r["warnings"]))
        self.assertEqual(r["kills_tolerance"], 0.6)

    def test_default_without_a_budget(self):
        self.assertEqual(run(budget=None)["kills_tolerance"], lv.DEFAULT_TOLERANCE)

    def test_bad_value_is_an_error(self):
        for bad in (1, -0.1, "0.2", True):
            self.assertEqual(codes(run(budget={**BUDGET, "kills_tolerance": bad})["errors"]), ["schema"], bad)

    def test_bad_value_does_not_stop_the_comparison(self):
        r = run(budget={**BUDGET, "kills_tolerance": 2}, economy=self.ECO)
        self.assertIn("kills_differ", codes(r["warnings"]))
        self.assertEqual(r["kills_tolerance"], lv.DEFAULT_TOLERANCE)


class Messages(unittest.TestCase):
    """86번."""

    def test_unlinked_kills_are_located_at_the_economy_stage(self):
        eco = {"stages": [{"id": "mid_game", "kills": {"a": 5}}]}
        w = next(x for x in run(economy=eco)["warnings"] if x["code"] == "kills_not_linked")
        self.assertEqual((w["where"], w["owner"], w["part"]), ("mid_game", "s1", "mid_game"))

    def test_renamed_stage_points_at_the_stage_with_no_level(self):
        combat = {"stages": [{"id": "s1", "zone": 1}, {"id": "midgame", "zone": 2}]}
        r = run(both(), combat=combat)
        w = next(x for x in r["errors"] if x["code"] == "unknown_stage")
        self.assertIn("레벨이 없는 전투 단계: midgame", w["message"])
        self.assertNotIn("s1", w["message"].replace("s1의", ""))

    def test_a_typo_is_still_guessed_among_free_stages(self):
        w = next(x for x in run(both(second=level("s22", enc("e2", {"c": 6}))))["errors"] if x["code"] == "unknown_stage")
        self.assertIn("'s2'의 오타", w["message"])

    def test_stage_already_taken_is_not_called_a_typo(self):
        combat = {"stages": [{"id": "zone_1", "zone": 1}, {"id": "zone_4", "zone": 2}]}
        levels = [level("zone_1", enc(enemies={"a": 5, "b": 1})), level("zone_4", enc("e2", {"c": 6})), level("zone_9", enc("e3", {"c": 1}))]
        w = next(x for x in run(levels, combat=combat)["errors"] if x["code"] == "unknown_stage")
        self.assertNotIn("오타", w["message"])
        self.assertIn("이미 레벨이 있습니다", w["message"])

    def stage_error(self, levels, combat):
        return next(x for x in run(levels, combat=combat)["errors"] if x["code"] == "unknown_stage")["message"]

    def test_typo_of_a_stage_with_a_level_names_that_stage(self):
        combat = {"stages": [{"id": "stage_one", "zone": 1}, {"id": "zone_b", "zone": 2}]}
        text = self.stage_error([level("stage_one", enc("x")), level("stage_onee", enc("y"))], combat)
        self.assertIn("이름이 비슷한 단계: stage_one", text)
        self.assertIn("레벨이 없는 전투 단계: zone_b", text)

    def test_free_stage_is_guessed_before_a_taken_one(self):
        combat = {"stages": [{"id": "stage_one", "zone": 1}, {"id": "stage_two", "zone": 2}]}
        text = self.stage_error([level("stage_one", enc("x")), level("stage_twoo", enc("y"))], combat)
        self.assertIn("'stage_two'의 오타", text)
        self.assertNotIn("이름이 비슷한 단계", text)

    def test_cut_stage_is_not_named(self):
        combat = {"stages": [{"id": "stage_one", "zone": 1, "status": "cut"}, {"id": "zone_b", "zone": 2}]}
        text = self.stage_error([level("zone_b", enc("x")), level("stage_onee", enc("y"))], combat)
        self.assertNotIn("이름이 비슷한 단계", text)
        self.assertNotIn("오타", text)

    def test_numbers_and_ids_take_no_wrong_particle(self):
        r = run(both(level("s1", enc(enemies={"a": 36, "gone": 1}))))
        text = " ".join(w["message"] for w in r["warnings"])
        self.assertNotRegex(text, r"\d가 |gone를")


class TableCurve(unittest.TestCase):
    """87번: 표 곡선의 남는 값."""

    def budget(self, **values):
        return {**BUDGET, "curve": {"growth": "table", "values": {"s1": 80, "s2": 120, **values}}}

    def test_value_for_no_stage_is_warned(self):
        r = run(budget=self.budget(s22=200))
        w = next(x for x in r["warnings"] if x["code"] == "curve_unused_point")
        self.assertEqual(w["where"], "threat_budget")
        self.assertIn("s22", w["message"])

    def test_cut_stage_keeps_its_value_quietly(self):
        self.assertNotIn("curve_unused_point", codes(run(budget=self.budget(old=100))["warnings"]))

    def test_without_combat_nothing_is_judged(self):
        self.assertNotIn("curve_unused_point", codes(run(budget=self.budget(s3=200), combat=None)["warnings"]))


class Unscored(unittest.TestCase):
    """88번: 위협도를 내지 못한 조우는 미확인이다."""

    def test_enemy_with_no_score_leaves_the_encounter_unchecked(self):
        r = run(threat={"c": 20.0})
        self.assertIn("scores", r["unchecked_kinds"])
        self.assertEqual(r["unscored"], ["s1.e1"])

    def test_missing_enemy_data_is_counted_once(self):
        r = run(enemies=None, threat=None)
        self.assertNotIn("scores", r["unchecked_kinds"])

    def test_unknown_enemy_is_already_an_error(self):
        r = run(both(level("s1", enc(enemies={"nobody": 1}))))
        self.assertIn("unknown_enemy", codes(r["errors"]))
        self.assertNotIn("scores", r["unchecked_kinds"])


class KillsToCopy(unittest.TestCase):
    """79번: 조우가 처치 수의 원본이면 재화 흐름에 옮길 값을 낸다."""

    def text(self, levels=None):
        data = {"levels": levels or both(), "threat_budget": BUDGET}
        return lv.table(data, run(levels))

    def test_table_prints_the_kills_per_stage(self):
        self.assertIn('- s1: {"a": 5, "b": 1}', self.text())

    def test_it_writes_valid_json(self):
        line = next(x for x in self.text().splitlines() if x.startswith("- s2: "))
        self.assertEqual(json.loads(line.split(": ", 1)[1]), {"c": 6})

    def test_broken_stage_prints_no_partial_kills(self):
        self.assertNotIn("- s1:", self.text(both(level("s1", enc("x", {"a": 5}), enc("y", {"b": 0})))))


class ReadingTheTable(unittest.TestCase):
    def test_table_marks_an_enemy_with_its_own_count(self):
        levels = both(level("s1", enc(repeat=10, enemy_repeat={"b": 1})))
        self.assertIn("b 1 (판에 1회)", lv.table({"levels": levels}, run(levels)))

    def test_totals_are_printed_under_the_level_name(self):
        text = printed(run())
        self.assertIn("레벨 위협도", text)
        self.assertIn("판 전체 위협도 200", text)
        self.assertNotIn("한 판 위협도", text)


class EncounterSourceInKills(unittest.TestCase):
    """kills_differ의 출처는 처치 수를 정한 조우의 출처다. 레벨의 출처는 조우에 출처가 없을 때만 쓴다."""

    def economy(self, source, **kills):
        return {"stages": [{"id": "s1", "kills": kills or {"a": 50, "b": 1}, "provenance": source}]}

    def test_measured_encounter_is_not_called_assumed(self):
        text = differ(run(both(level("s1", enc(provenance=MEASURED))), economy=self.economy(MEASURED)))
        self.assertIn("조우 측정", text)
        self.assertNotIn("측정값이", text)

    def test_assumed_encounter_in_a_measured_level_is_assumed(self):
        text = differ(run(both(level("s1", enc(provenance=ASSUMED), provenance=MEASURED)), economy=self.economy(ASSUMED)))
        self.assertIn("조우 가정", text)
        self.assertNotIn("조우가 측정값", text)

    def test_measured_economy_beats_an_assumed_encounter(self):
        r = run(both(level("s1", enc(provenance=ASSUMED), provenance=MEASURED)), economy=self.economy(MEASURED))
        self.assertIn("재화 흐름이 측정값", differ(r))

    def test_measured_encounter_beats_assumed_economy(self):
        self.assertIn("조우가 측정값", differ(run(both(level("s1", enc(provenance=MEASURED))), economy=self.economy(ASSUMED))))

    def test_source_is_read_for_each_enemy(self):
        lvl = level("s1", enc("x", {"a": 5}, provenance=MEASURED), enc("y", {"b": 1}))
        r = run(both(lvl), economy=self.economy(ASSUMED, a=50, b=9))
        self.assertIn("조우 측정", differ(r, "a"))
        self.assertIn("조우 가정", differ(r, "b"))

    def test_enemy_in_encounters_with_different_sources_is_mixed(self):
        lvl = level("s1", enc("x", {"a": 3, "b": 1}, provenance=MEASURED), enc("y", {"a": 2}))
        self.assertIn("조우 섞임", differ(run(both(lvl), economy=self.economy(ASSUMED))))

    def test_enemy_only_the_economy_counts_takes_the_stage_source(self):
        r = run(both(level("s1", enc(provenance=MEASURED))), economy=self.economy(ASSUMED, a=5, b=1, c=9))
        self.assertIn("조우 측정", differ(r, "c"))


class PartialKillTime(unittest.TestCase):
    """처치 시간을 모르는 적을 뺀 합계는 실제보다 작다. 어느 출력에서도 완전한 값처럼 보이지 않는다."""

    def setUp(self):
        self.partial = run(kill_times={"s1": {"a": 2.0}, "s2": {"c": 3.0}}, economy=ECONOMY)
        self.whole = run(kill_times=TIMES, economy=ECONOMY)

    def test_table_marks_the_time_and_the_ratio(self):
        cells = stage_cells(self.partial)
        self.assertIn("10 이상 (b 제외)", cells)
        self.assertIn("0.17배 이상", cells)

    def test_check_marks_the_time_and_the_ratio(self):
        line = next(x for x in printed(self.partial).splitlines() if x.startswith("단계 s1"))
        self.assertIn("10초 이상", line)
        self.assertIn("0.17배 이상", line)
        self.assertIn("제외: b", line)

    def test_complete_total_has_no_mark(self):
        self.assertNotIn("이상", stage_cells(self.whole))
        self.assertNotIn("이상", next(x for x in printed(self.whole).splitlines() if x.startswith("단계 s1")))

    def test_table_and_check_show_the_same_ratio(self):
        self.assertIn("| 0.27배 |", stage_cells(self.whole))
        self.assertIn("0.27배", printed(self.whole))

    def test_ratio_is_rounded_once_so_every_output_agrees(self):
        eco = {"stages": [{"id": "s1", "duration": 25.6, "kills": {"a": 5, "b": 1}}]}
        self.assertEqual(stage(run(kill_times=TIMES, economy=eco))["kill_ratio"], 0.62)

    def test_stage_with_no_ratio_shows_a_dash(self):
        self.assertIn("| – |", stage_cells(run()))


class WholeTotals(unittest.TestCase):
    """빠진 레벨이나 조우가 없는 단계가 있으면 합계를 전체처럼 내지 않는다."""

    def test_failed_level_hides_its_stage_total_and_the_run_total(self):
        r = run(both() + [level("x", enc("z", {"c": 1}), combat_stage="s2", status="nope")])
        self.assertEqual(codes(r["errors"]), ["schema"])
        self.assertEqual(stage(r)["threat"], 80)
        self.assertIsNone(stage(r, "s2")["threat"])
        self.assertIsNone(r["run_threat"])

    def test_failed_level_makes_no_false_drop_note(self):
        levels = [level("s1", enc("big", {"a": 5, "b": 1})), level("s2", enc("small", {"c": 1})), level("x", enc("z", {"c": 90}), combat_stage="s2", status="nope")]
        self.assertNotIn("줄었습니다", notes(run(levels)))

    def test_drop_note_stays_for_a_real_drop(self):
        self.assertIn("줄었습니다", notes(run([level("s1", enc("big", {"a": 5, "b": 1})), level("s2", enc("small", {"c": 1}))])))

    def test_level_of_an_unknown_stage_hides_every_total(self):
        r = run(both() + [level("nowhere", enc("z", {"c": 1}))])
        self.assertEqual([stage(r, k)["threat"] for k in ("s1", "s2")], [None, None])
        self.assertIsNone(r["run_threat"])

    def test_stage_without_a_level_leaves_no_run_total(self):
        r = run([level("s1")])
        self.assertEqual(stage(r)["threat"], 80)
        self.assertIsNone(r["run_threat"])
        self.assertNotIn("판 전체 위협도", printed(r))

    def test_cut_level_is_not_a_missing_level(self):
        self.assertEqual(run(both() + [level("x", status="cut")])["run_threat"], 200)

    def test_level_of_a_cut_stage_is_not_a_missing_level(self):
        self.assertEqual(run(both() + [level("old")])["run_threat"], 200)


class TimeUnit(unittest.TestCase):
    def test_unit_is_seconds_unless_written(self):
        for cfg in (None, {}, {"time_unit": 3}, "economy"):
            self.assertEqual(common.time_unit(cfg), "초")
        self.assertEqual(common.time_unit({"time_unit": "분"}), "분")

    def test_stage_table_reads_the_unit_the_same_way(self):
        r = run(kill_times=TIMES, economy={**ECONOMY, "economy": {"time_unit": 3}})
        self.assertEqual((stage(r)["time_unit"], stage(r)["kill_ratio"]), ("초", 0.27))


class FieldProject(base.Workspace):
    def check(self, *args):
        return run_cli("check", self.root, *args)

    def write(self, rel, text):
        (self.root / rel).write_text(text, encoding="utf-8")

    def test_kill_time_reaches_the_project_report(self):
        r = self.report()
        self.assertIsNotNone(r["stages"][0]["kill_time"])
        self.assertIsNotNone(r["stages"][0]["kill_ratio"])

    def test_player_damage_changes_the_kill_time(self):
        before = self.report()["stages"][0]["kill_time"]
        self.edit("data/combat.json", lambda d: d["stages"][0]["player"]["base"].__setitem__("attack", 500))
        self.assertLess(self.report()["stages"][0]["kill_time"], before)

    def test_enemy_curve_reaches_the_project_report(self):
        self.assertIsNotNone(self.report()["stages"][0]["group_size"])

    def test_empty_object_named_levels_is_a_read_failure(self):
        self.write("data/levels.json", "{}")
        code, out = self.check()
        self.assertEqual(code, 2)
        self.assertIn("UNREADABLE", out)

    def test_empty_file_named_levels_is_a_read_failure(self):
        self.write("data/levels.json", "")
        self.assertEqual(self.check()[0], 2)

    def test_empty_file_with_another_name_stays_skipped(self):
        self.write("data/notes.json", "")
        code, out = self.check()
        self.assertEqual(code, 0)
        self.assertNotIn("notes.json", out)

    def test_file_given_directly_is_not_reported_as_skipped(self):
        self.write("data/levels.json", '{"level": []}')
        code, out = run_cli("check", self.root / "data/levels.json")
        self.assertEqual(code, 2)
        self.assertNotIn("건너뛰었습니다", out)

    def test_csv_named_levels_is_not_reported_as_skipped(self):
        self.write("data/levels.csv", "a,b\n1,2\n")
        self.assertNotIn("건너뛰었습니다", self.check()[1])

    def test_foreign_levels_file_is_named_but_does_not_fail(self):
        self.write("data/levels.json", '{"level": [{"map": "a.tmx"}]}')
        code, out = self.check()
        self.assertEqual(code, 0)
        self.assertIn("levels.json", out)
        self.assertIn("건너뛰었습니다", out)

    def test_skipped_file_is_in_the_json_payload(self):
        self.write("data/levels.json", '{"level": []}')
        code, out = self.check("--json")
        self.assertEqual([p.rsplit("/", 1)[-1] for p in json.loads(out)["skipped"]], ["levels.json"])

    def test_nothing_is_said_when_levels_are_read(self):
        self.assertNotIn("건너뛰었습니다", self.check()[1])

    def test_skipped_file_is_named_once_when_folders_overlap(self):
        self.write("data/levels.json", '{"level": []}')
        self.assertEqual(run_cli("check", self.root, self.root / "data")[1].count("건너뛰었습니다"), 1)

    def test_file_also_given_directly_is_not_called_skipped(self):
        self.write("data/levels.json", '{"level": []}')
        for paths in ((self.root / "data", self.root / "data/levels.json"), (self.root / "data/levels.json", self.root / "data")):
            code, out = run_cli("check", *paths)
            self.assertEqual(code, 2)
            self.assertNotIn("건너뛰었습니다", out)

    def test_skipped_file_is_read_once(self):
        self.write("data/levels.json", '{"level": []}')
        with mock.patch.object(datasets, "read", wraps=datasets.read) as read:
            datasets.scan_all([self.root / "data", self.root / "data"])
        self.assertEqual(sum(1 for x in read.call_args_list if x.args[0].name == "levels.json"), 1)

    def test_viewer_names_the_skipped_file(self):
        self.write("data/levels.json", '{"level": []}')
        snap = viewer.snapshot([self.root])
        self.assertEqual(len(snap["notices"]), 1)
        self.assertIn("건너뛰었습니다", snap["notices"][0])
        self.assertIn("levels.json", snap["notices"][0])

    def test_viewer_says_nothing_when_levels_are_read(self):
        self.assertEqual(viewer.snapshot([self.root])["notices"], [])

    def test_viewer_cache_notices_a_file_that_starts_being_skipped(self):
        cache = viewer.SnapshotCache([self.root])
        (self.root / "data/levels.json").unlink()
        self.assertEqual(json.loads(cache.body_bytes())["notices"], [])
        self.write("data/levels.json", '{"level": []}')
        self.assertEqual(len(json.loads(cache.body_bytes())["notices"]), 1)

    def test_broken_file_named_as_a_kind_is_a_read_failure(self):
        for name in ("economy", "growth", "combat", "budget", "crafting", "playtests"):
            with self.subTest(name):
                p = self.root / f"data/{name}.json"
                keep = p.read_text(encoding="utf-8")
                p.write_text("{oops", encoding="utf-8")
                code, out = self.check()
                self.assertEqual(code, 2, out[-300:])
                self.assertIn("UNREADABLE", out)
                p.write_text(keep, encoding="utf-8")

    def test_foreign_csv_with_a_kind_name_stays_skipped(self):
        self.write("data/economy.csv", "a,b\n1,2\n")
        self.assertEqual(self.check()[0], 0)

    def test_table_without_its_data_says_so(self):
        (self.root / "data/levels.json").unlink()
        code, out = self.check("--table", "levels")
        self.assertIn("표를 낼 데이터가 없습니다: 레벨 구성", out)

    def test_check_help_names_the_encounter_table(self):
        out = io.StringIO()
        with redirect_stdout(out), self.assertRaises(SystemExit):
            cli.main(["check", "--help"])
        self.assertIn("조우 표", " ".join(out.getvalue().split()))

    def test_assumed_encounter_reaches_the_gate(self):
        def measured(d):
            d["threat_budget"]["provenance"] = MEASURED
            for x in d["levels"]:
                x["provenance"] = MEASURED
            d["levels"][0]["encounters"][0]["provenance"] = {"kind": "assumed"}
        self.edit("data/levels.json", measured)
        code, out = self.check("--fail-on-assumed")
        self.assertEqual(code, 1)
        self.assertIn("crypt.crypt_skirmish", out)

    def test_sample_shows_an_enemy_with_its_own_count(self):
        data = json.loads((self.root / "data/levels.json").read_text(encoding="utf-8"))
        self.assertTrue(any("enemy_repeat" in x for lvl in data["levels"] for x in lvl["encounters"]))


class Docs(unittest.TestCase):
    def setUp(self):
        self.skill = (ROOT / "skills/level-design/SKILL.md").read_text(encoding="utf-8")
        self.fmt = (ROOT / "skills/level-design/references/levels-format.md").read_text(encoding="utf-8")
        self.studio = (STUDIO / "SKILL.md").read_text(encoding="utf-8")
        self.page = (STUDIO / "assets/viewer.html").read_text(encoding="utf-8")

    def test_continuous_spawns_have_a_rule(self):
        for word in ("동시에", "다시 차는"):
            self.assertIn(word, self.skill)
            self.assertIn(word, self.fmt)

    def test_budget_comes_before_the_encounters(self):
        self.assertIn("근거", self.skill)
        self.assertLess(self.skill.index("### 2. 예산을 정한다"), self.skill.index("### 3. 조우를 놓는다"))
        self.assertIn("조우에 맞춰", self.skill)

    def test_new_keys_are_documented(self):
        for key in ("enemy_repeat", "kills_tolerance"):
            self.assertIn(f"`{key}`", self.fmt)
        self.assertIn("`provenance`", self.fmt[self.fmt.index("## `encounters`"):])

    def test_side_effects_of_changing_stage_enemies_are_documented(self):
        self.assertIn("simulate", self.skill)

    def test_source_of_each_shared_fact_is_named(self):
        self.assertIn("처치 수의 원본", self.skill)

    def test_stage_select_grades_are_documented(self):
        self.assertIn("등급", self.fmt)

    def test_studio_doc_lists_levels_in_the_code_table(self):
        self.assertIn("`economy`, `levels`, `playtests`", self.studio[self.studio.index("## 코드 구조"):])
        self.assertIn("level", self.studio.split("---")[1])

    def test_studio_doc_lists_levels(self):
        self.assertIn("levels.json", self.studio[self.studio.index("## 프로젝트 배치"):self.studio.index("## 뷰어")])
        self.assertIn("레벨 구성", self.studio[self.studio.index("## 뷰어"):])
        self.assertIn("`levels`", self.studio[self.studio.index("## 프로젝트 배치"):self.studio.index("## 뷰어")])

    def test_viewer_empty_page_lists_levels(self):
        self.assertIn('"data/levels.json"', self.page)

    def test_viewer_shows_the_new_values(self):
        body = self.page[self.page.index("function renderLevels"):self.page.index("function renderPlaytests")]
        for word in ("r.notes", "vs_previous", "kill_time", "enemy_repeat", "group_size", "position"):
            self.assertIn(word, body)
        self.assertNotIn("한 판 위협도", body)

    def test_old_name_of_the_level_total_is_gone(self):
        self.assertNotIn("한 판 위협도", self.skill)
        self.assertNotIn("한 판 위협도", self.fmt)

    def test_viewer_marks_a_partial_kill_time(self):
        body = self.page[self.page.index("function renderLevels"):self.page.index("function renderPlaytests")]
        self.assertIn("kill_time_unknown", body)
        self.assertIn("이상", body)

    def test_viewer_shows_notices_apart_from_failures(self):
        self.assertIn('id="notices"', self.page)
        self.assertIn("snap.notices", self.page)

    def test_encounter_source_is_documented_for_the_kill_warning(self):
        self.assertIn("조우에 출처가 있으면", self.fmt)

    def test_unscored_gap_has_a_label(self):
        self.assertRegex(self.page, r"unchecked: \{[^}]*\bscores: \"")


if __name__ == "__main__":
    unittest.main()
