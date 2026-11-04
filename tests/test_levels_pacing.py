"""레벨 페이싱(L2, 이슈 73·74·81) 테스트: 적이 없는 구간, 시각과 길이, 구매 시점, 쉬는 곳·보상 사이의 부담, 강한 조우의 연속. 표준 라이브러리 unittest만 사용한다."""
import json
import unittest

from _studio import ROOT, SAMPLE, STUDIO, common, levels as lv
from test_levels import BUDGET, COMBAT, ENEMIES, THREAT, both, codes, enc, level, row, run
from test_levels_field import ECONOMY, notes, printed
from test_levels_recheck import Project, warning

PLAN = {"ripen": {"id": "ripen", "at": 45.0, "stage": "s1"}, "late": {"id": "late", "at": 70.0, "stage": "s2"},
        "never": {"id": "never", "at": None, "stage": None}}


def quiet(eid="q", **over):
    """적이 없는 구간."""
    return {"id": eid, "enemies": {}, **over}


def strong(eid="hard", **over):
    """곡선 80의 1.5배인 조우(역할은 예산에 맞는 boss)."""
    return enc(eid, {"a": 12}, role="boss", **over)


def spans(result, kind="rest"):
    return [s for s in result["pacing"]["spans"] if s["kind"] == kind]


def clock_note(result):
    return next(x for x in result["notes"] if x.startswith("시각 대조"))


def warn_codes(result):
    return codes(result["warnings"])


def paced(*levels, pacing=None, **extra):
    data = {"levels": list(levels), "threat_budget": BUDGET}
    if pacing is not None:
        data["pacing"] = pacing
    args = {"enemies": ENEMIES, "threat": THREAT, "combat": COMBAT, **extra}
    return lv.validate(data, **args)


class QuietStretches(unittest.TestCase):
    """73: 적이 없는 구간을 조우로 적는다."""

    def test_an_encounter_may_have_no_enemies(self):
        r = run(both(level("s1", enc(), quiet())))
        self.assertEqual(r["errors"], [])
        self.assertEqual((row(r, "q")["threat"], row(r, "q")["flag"], row(r, "q")["expected"]), (0, "quiet", None))
        self.assertNotIn("under_budget", warn_codes(r))

    def test_the_field_report_input_works_with_a_role_outside_the_budget(self):
        r = run(both(level("s1", enc(), quiet("z2_altar", role="rest"))))
        self.assertEqual(r["errors"], [])
        self.assertEqual(row(r, "z2_altar")["role"], "rest")

    def test_leaving_out_enemies_stays_an_error_that_names_the_way_out(self):
        x = enc()
        del x["enemies"]
        r = run(both(level("s1", x, enc("e3"))))
        self.assertIn("{}", next(e["message"] for e in r["errors"] if e["code"] == "schema"))

    def test_a_fight_still_needs_a_role(self):
        x = enc()
        del x["role"]
        self.assertIn("schema", codes(run(both(level("s1", x)))["errors"]))

    def test_a_role_that_is_not_text_is_an_error_even_here(self):
        self.assertIn("schema", codes(run(both(level("s1", enc(), quiet(role=3))))["errors"]))

    def test_the_next_fight_compares_with_the_fight_before_the_stretch(self):
        r = run(both(level("s1", enc(), quiet(), enc("e3", {"a": 16}, role="boss"))))
        self.assertIsNone(row(r, "q")["vs_previous"])
        self.assertEqual(row(r, "e3")["vs_previous"], 2)

    def test_it_adds_no_kills_or_threat(self):
        with_it, without = run(both(level("s1", enc(), quiet()))), run()
        self.assertEqual(with_it["levels"][0]["threat"], without["levels"][0]["threat"])
        self.assertEqual(with_it["levels"][0]["kills"], without["levels"][0]["kills"])

    def test_a_stage_of_only_quiet_stretches_has_no_fights(self):
        r = run(both(level("s1", quiet())))
        self.assertIn("s1", r["stages_without_levels"])
        self.assertIn("stages", r["unchecked_kinds"])

    def test_the_table_says_there_are_no_enemies(self):
        r = run(both(level("s1", enc(), quiet())))
        line = next(x for x in lv.table({}, r).splitlines() if x.startswith("| s1 | q |"))
        self.assertIn("적 없음", line)
        self.assertNotIn("미확인", line)


class Hazards(unittest.TestCase):
    """73: 함정처럼 적 없이 드는 소모."""

    def test_hazard_adds_threat_but_no_kills(self):
        r = run(both(level("s1", enc(hazard=20, repeat=2))))
        self.assertEqual(row(r)["threat"], 100)
        self.assertEqual(r["levels"][0]["threat"], 200)
        self.assertEqual(r["levels"][0]["kills"], {"a": 10, "b": 2})

    def test_hazard_without_a_role_is_not_compared(self):
        r = run(both(level("s1", enc(), quiet("trap", hazard=15))))
        self.assertEqual((row(r, "trap")["threat"], row(r, "trap")["flag"]), (15, "quiet"))
        self.assertEqual(r["levels"][0]["threat"], 95)

    def test_hazard_with_a_role_is_compared(self):
        r = run(both(level("s1", enc(), quiet("trap", hazard=10, role="room"))))
        self.assertEqual(row(r, "trap")["flag"], "under")
        self.assertEqual(warning(r, "under_budget")["part"], "trap")

    def test_hazard_with_an_unknown_role_is_an_error(self):
        self.assertIn("unknown_role", codes(run(both(level("s1", enc(), quiet("trap", hazard=10, role="trapp"))))["errors"]))

    def test_table_shows_the_hazard(self):
        r = run(both(level("s1", enc(), quiet("trap", hazard=15))))
        self.assertIn("소모 15", next(x for x in lv.table({}, r).splitlines() if x.startswith("| s1 | trap |")))


class BadKeys(unittest.TestCase):
    def test_new_keys_reject_wrong_values(self):
        for key, value in (("hazard", 0), ("hazard", "큼"), ("rest", "yes"), ("reward", ""), ("reward", 3), ("at", -1), ("at", "1:00"),
                           ("duration", -1), ("duration", "1분"), ("purchases", "ripen"), ("purchases", [1]), ("purchases", [])):
            r = run(both(level("s1", enc(), enc("e3", **{key: value}))), purchases=PLAN)
            self.assertIn("schema", codes(r["errors"]), (key, value))


class Clock(unittest.TestCase):
    """74: 시각과 길이."""

    def test_durations_run_one_after_another(self):
        r = run(both(level("s1", enc(duration=20), enc("e3", duration=40))))
        self.assertEqual((row(r)["start"], row(r)["end"], row(r, "e3")["start"], row(r, "e3")["end"]), (0, 20, 20, 60))

    def test_at_is_on_the_run_clock(self):
        r = run(both(level("s1", enc(at=0, duration=60)), level("s2", enc("e2", {"c": 6}, at=60, duration=30))), economy=ECONOMY)
        self.assertEqual((row(r, "e2")["start"], row(r, "e2")["end"]), (60, 90))

    def test_duration_is_the_whole_stretch_not_one_visit(self):
        r = run(both(level("s1", enc(duration=60, repeat=3))))
        self.assertEqual(row(r)["end"], 60)

    def test_a_stage_starts_where_the_economy_says(self):
        r = run(both(level("s1"), level("s2", enc("e2", {"c": 6}, duration=30))), economy=ECONOMY)
        self.assertEqual((row(r, "e2")["start"], row(r, "e2")["end"]), (60, 90))

    def test_without_an_economy_levels_follow_each_other(self):
        r = run(both(level("s1", enc(duration=25)), level("s2", enc("e2", {"c": 6}, duration=5))))
        self.assertEqual(row(r, "e2")["start"], 25)

    def test_levels_follow_the_stage_order_not_the_file_order(self):
        r = run([level("s2", enc("e2", {"c": 6}, duration=5)), level("s1", enc(duration=25))])
        self.assertEqual((row(r)["start"], row(r, "e2")["start"]), (0, 25))

    def test_the_next_stretch_waits_for_the_longest_parallel_one(self):
        r = run(both(level("s1", enc(at=0, duration=40), enc("e3", at=0, duration=20), enc("e4", duration=20))), economy=ECONOMY)
        self.assertEqual(row(r, "e4")["start"], 40)

    def test_parallel_stretches_are_a_note_not_a_warning(self):
        r = run(both(level("s1", enc(at=0, duration=60), enc("e3", at=0, duration=60)), level("s2", enc("e2", {"c": 6}, duration=30))), economy=ECONOMY)
        self.assertNotIn("time_gap", warn_codes(r))
        self.assertIn("e1·e3", notes(r))

    def test_touching_stretches_do_not_overlap(self):
        r = run(both(level("s1", enc(at=0, duration=30), enc("e3", at=30, duration=30))), economy=ECONOMY)
        self.assertNotIn("겹치는", notes(r))

    def test_at_alone_is_a_moment(self):
        r = run(both(level("s1", enc(duration=60), enc("e3", at=50))), economy=ECONOMY)
        self.assertEqual((row(r, "e3")["start"], row(r, "e3")["end"]), (50, 50))
        self.assertNotIn("겹치는", notes(r))

    def test_a_moment_behind_the_clock_keeps_it_where_it_was(self):
        r = run(both(level("s1", enc(duration=30), enc("e3", at=10), enc("e4", duration=30))), economy=ECONOMY)
        self.assertEqual(row(r, "e4")["start"], 30)

    def test_a_moment_ahead_of_the_clock_moves_it(self):
        r = run(both(level("s1", enc(duration=10), enc("e3", at=50), enc("e4", duration=10))), economy=ECONOMY)
        self.assertEqual(row(r, "e4")["start"], 50)

    def test_adds_listed_after_a_boss_moment_follow_it_without_a_false_hole(self):
        r = run(both(level("s1", enc(at=0, duration=40), enc("e3", at=40), enc("e4", duration=20))), economy=ECONOMY)
        self.assertEqual(row(r, "e4")["end"], 60)
        self.assertNotIn("time_gap", warn_codes(r))

    def test_an_untimed_encounter_stops_the_clock(self):
        r = run(both(level("s1", enc(duration=20), enc("e3"), enc("e4", duration=10))))
        self.assertEqual((row(r, "e3")["start"], row(r, "e4")["start"]), (None, None))

    def test_a_stage_that_fits_warns_of_nothing(self):
        r = run(both(level("s1", enc(duration=20), quiet(duration=40)), level("s2", enc("e2", {"c": 6}, duration=30))), economy=ECONOMY)
        self.assertEqual([k for k in warn_codes(r) if k.startswith("time_")], [])
        self.assertIn("시각 대조: 2/2 단계", notes(r))

    def test_a_hole_between_stretches_is_a_warning(self):
        r = run(both(level("s1", enc(at=0, duration=20), enc("e3", at=30, duration=30))), economy=ECONOMY)
        w = warning(r, "time_gap")
        self.assertEqual((w["part"], w["owner"]), ("s1", "s1"))
        self.assertIn("20~30초", w["message"])

    def test_a_short_stretch_inside_a_long_one_leaves_no_hole(self):
        r = run(both(level("s1", enc(at=0, duration=60), enc("e3", at=10, duration=10))), economy=ECONOMY)
        self.assertNotIn("time_gap", warn_codes(r))

    def test_a_moment_does_not_split_a_hole(self):
        r = run(both(level("s1", enc(at=0, duration=20), enc("e3", at=30), enc("e4", at=40, duration=20))), economy=ECONOMY)
        self.assertIn("20~40초", warning(r, "time_gap")["message"])

    def test_a_moment_keeps_its_exact_time_at_the_end(self):
        r = run(both(level("s1", enc(duration=60), enc("e3", at=10.12345), enc("e4", at=33.33334))), economy=ECONOMY)
        self.assertEqual((row(r, "e3")["end"], row(r, "e4")["end"]), (10.12345, 33.33334))
        self.assertNotIn("겹치는", notes(r))

    def test_a_dropped_encounter_leaves_later_times_unknown(self):
        r = run(both(level("s1", enc(duration=20), enc("e3", repeat=0, duration=20), enc("e4", duration=20))), economy=ECONOMY)
        self.assertIsNone(row(r, "e4")["start"])

    def test_a_dropped_encounter_at_the_front_shifts_the_first_one_too(self):
        r = run(both(level("s1", enc("e3", repeat=0, duration=20), enc(duration=20))), economy=ECONOMY)
        self.assertIsNone(row(r)["start"])

    def test_a_written_at_survives_a_dropped_encounter(self):
        r = run(both(level("s1", enc(duration=20), enc("e3", repeat=0, duration=20), enc("e4", at=40, duration=20))), economy=ECONOMY)
        self.assertEqual(row(r, "e4")["start"], 40)

    def test_a_dropped_encounter_does_not_resync_after_a_written_at(self):
        r = run(both(level("s1", enc("e3", repeat=0, duration=20), enc(at=0, duration=20), enc("e4", duration=20))), economy=ECONOMY)
        self.assertIsNone(row(r, "e4")["start"])

    def test_a_dropped_level_leaves_later_levels_of_its_stage_unknown(self):
        r = run([level("s1", enc(duration=30)), level("s1b", enc("e9", duration=15), combat_stage="s1", status="oops"),
                 level("s1c", enc("e3", duration=15), combat_stage="s1"), level("s2", enc("e2", {"c": 6}))], economy=ECONOMY)
        self.assertIsNone(row(r, "e3")["start"])

    def test_the_next_stage_starts_clean_with_an_economy(self):
        r = run(both(level("s1", enc(duration=20), enc("e3", repeat=0)), level("s2", enc("e2", {"c": 6}, duration=30))), economy=ECONOMY)
        self.assertEqual(row(r, "e2")["start"], 60)

    def test_the_next_stage_stays_unknown_without_one(self):
        r = run(both(level("s1", enc(duration=20), enc("e3", repeat=0)), level("s2", enc("e2", {"c": 6}, duration=30))))
        self.assertIsNone(row(r, "e2")["start"])

    def test_a_stage_of_only_moments_has_no_holes(self):
        r = run(both(level("s1", enc(at=0), enc("e3", at=30), enc("e4", at=50))), economy=ECONOMY)
        self.assertNotIn("time_gap", warn_codes(r))
        self.assertIn("시각 대조: 1/2 단계", notes(r))

    def test_moments_past_the_stage_still_warn(self):
        self.assertIn("time_outside_stage", warn_codes(run(both(level("s1", enc(at=0), enc("e3", at=70))), economy=ECONOMY)))

    def test_the_hole_message_also_offers_a_length(self):
        r = run(both(level("s1", enc(at=0, duration=20), enc("e3", at=30))), economy=ECONOMY)
        self.assertIn("duration", warning(r, "time_gap")["message"])

    def test_a_stage_with_a_broken_encounter_is_not_compared(self):
        r = run(both(level("s1", enc(at=0, duration=20), enc("e3", repeat=0))), economy=ECONOMY)
        self.assertEqual([k for k in warn_codes(r) if k.startswith("time_")], [])

    def test_a_short_stage_is_a_hole_at_the_end(self):
        self.assertIn("50~60초", warning(run(both(level("s1", enc(at=0, duration=50))), economy=ECONOMY), "time_gap")["message"])

    def test_a_late_start_is_a_hole_at_the_beginning(self):
        self.assertIn("0~10초", warning(run(both(level("s1", enc(at=10, duration=50))), economy=ECONOMY), "time_gap")["message"])

    def test_running_past_the_stage_is_a_warning(self):
        w = warning(run(both(level("s1", enc(at=0, duration=70))), economy=ECONOMY), "time_outside_stage")
        self.assertEqual(w["part"], "s1")
        self.assertIn("0~60초", w["message"])
        self.assertIn("0~70초", w["message"])

    def test_starting_before_the_stage_is_a_warning(self):
        r = run(both(level("s1"), level("s2", enc("e2", {"c": 6}, at=50, duration=40))), economy=ECONOMY)
        self.assertEqual(warning(r, "time_outside_stage")["part"], "s2")

    def test_a_moment_past_the_stage_is_a_warning(self):
        r = run(both(level("s1", enc(duration=60), enc("e3", at=61))), economy=ECONOMY)
        self.assertIn("time_outside_stage", warn_codes(r))

    def test_a_stage_with_unknown_times_is_not_compared(self):
        r = run(both(level("s1", enc(duration=20), enc("e3"))), economy=ECONOMY)
        self.assertEqual([k for k in warn_codes(r) if k.startswith("time_")], [])
        self.assertIn("시각을 모르는 조우: e3", notes(r))

    def test_a_game_without_times_hears_nothing_about_them(self):
        r = run(economy=ECONOMY)
        self.assertFalse(r["pacing"]["used"])
        self.assertNotIn("시각", notes(r))

    def test_levels_of_one_stage_fill_it_together(self):
        r = run([level("s1", enc(duration=30)), level("s1b", enc("e3", duration=30), combat_stage="s1"), level("s2", enc("e2", {"c": 6}, duration=30))], economy=ECONOMY)
        self.assertEqual(row(r, "e3")["start"], 30)
        self.assertEqual([k for k in warn_codes(r) if k.startswith("time_")], [])

    def test_economy_stages_of_one_combat_stage_add_up(self):
        eco = {"economy": {}, "stages": [{"id": "r1", "combat_stage": "s1", "duration": 30}, {"id": "r2", "combat_stage": "s1", "duration": 30},
                                         {"id": "s2", "duration": 30}]}
        r = run(both(level("s1", enc(duration=60)), level("s2", enc("e2", {"c": 6}, duration=30))), economy=eco)
        self.assertEqual([k for k in warn_codes(r) if k.startswith("time_")], [])

    def test_cut_economy_stages_take_no_time(self):
        eco = {"economy": {}, "stages": [{"id": "s0", "duration": 99, "status": "cut"}, *ECONOMY["stages"]]}
        self.assertEqual(row(run(both(level("s1", enc(duration=60))), economy=eco))["start"], 0)

    def test_without_a_stage_length_only_holes_inside_are_seen(self):
        eco = {"economy": {}, "stages": [{"id": "s1"}, {"id": "s2", "duration": 30}]}
        r = run(both(level("s1", enc(at=5, duration=5), enc("e3", at=20, duration=5))), economy=eco)
        self.assertIn("10~20초", warning(r, "time_gap")["message"])
        self.assertNotIn("time_outside_stage", warn_codes(r))

    def test_a_stage_without_a_length_is_not_counted_as_compared(self):
        eco = {"economy": {}, "stages": [{"id": "s1"}, {"id": "s2", "duration": 30}]}
        text = notes(run(both(level("s1", enc(at=0, duration=5))), economy=eco))
        self.assertIn("시각 대조: 0/2 단계", text)
        self.assertIn("재화 흐름에 길이가 없는 단계: s1", text)

    def test_without_an_economy_the_note_says_so(self):
        text = clock_note(run(both(level("s1", enc(duration=25)), level("s2", enc("e2", {"c": 6}, duration=5)))))
        self.assertIn("재화 흐름을 함께 읽지 않아", text)
        self.assertNotIn("길이가 없는 단계", text)

    def test_a_broken_stage_is_named(self):
        self.assertIn("오류로 못 본 단계: s1", clock_note(run(both(level("s1", enc(at=0, duration=20), enc("e3", repeat=0))), economy=ECONOMY)))

    def test_a_stage_whose_level_fell_out_is_named_too(self):
        r = run([level("s1", enc(duration=60)), level("s2", enc("e2", {"c": 6}), status="oops")], economy=ECONOMY)
        self.assertIn("오류로 못 본 단계: s2", clock_note(r))

    def test_a_broken_game_without_times_still_hears_nothing(self):
        self.assertNotIn("시각", notes(run(both(level("s1", enc(), enc("e3", repeat=0))), economy=ECONOMY)))

    def test_an_open_ended_stage_reads_as_a_start(self):
        eco = {"economy": {}, "stages": [{"id": "s1", "duration": 10}, {"id": "s2"}]}
        text = warning(run(both(level("s1"), level("s2", enc("e2", {"c": 6}, at=1, duration=1))), economy=eco), "time_outside_stage")["message"]
        self.assertIn("10초부터", text)
        self.assertNotIn("–", text)

    def test_stages_after_an_unknown_length_have_no_start(self):
        eco = {"economy": {}, "stages": [{"id": "s1"}, {"id": "s2", "duration": 30}]}
        r = run(both(level("s1"), level("s2", enc("e2", {"c": 6}, at=500, duration=30))), economy=eco)
        self.assertNotIn("time_outside_stage", warn_codes(r))

    def test_warnings_use_the_economy_time_unit(self):
        eco = {"economy": {"time_unit": "방"}, "stages": ECONOMY["stages"]}
        self.assertIn("20~30방", warning(run(both(level("s1", enc(at=0, duration=20), enc("e3", at=30, duration=30))), economy=eco), "time_gap")["message"])

    def test_a_gap_can_be_acknowledged_on_the_stage(self):
        data = {"levels": both(level("s1", enc(at=0, duration=20), acknowledged={"time_gap": {"s1": "일부러 비운 시간"}})), "threat_budget": BUDGET}
        r = lv.validate(data, enemies=ENEMIES, threat=THREAT, combat=COMBAT, economy=ECONOMY)
        common.apply_acknowledged("levels", data, r)
        self.assertNotIn("time_gap", warn_codes(r))


class PurchaseLinks(unittest.TestCase):
    """74: 구매 시점을 조우의 시각과 맞춘다."""

    def result(self, *encounters, economy=ECONOMY, purchases=PLAN):
        return run(both(level("s1", *encounters)), economy=economy, purchases=purchases)

    def test_a_purchase_inside_the_stretch_is_quiet(self):
        r = self.result(enc(duration=30), quiet(duration=30, purchases=["ripen"]))
        self.assertNotIn("purchase_off_span", warn_codes(r))
        self.assertIn("구매 대조: 1/1", notes(r))

    def test_a_purchase_outside_the_stretch_is_a_warning(self):
        w = warning(self.result(quiet(duration=30, purchases=["ripen"]), enc(duration=30)), "purchase_off_span")
        self.assertEqual((w["part"], w["owner"]), ("ripen", "s1"))
        self.assertIn("45초", w["message"])
        self.assertIn("0~30초", w["message"])

    def test_a_purchase_before_the_stretch_is_a_warning_too(self):
        self.assertIn("purchase_off_span", warn_codes(self.result(enc(duration=50), quiet(duration=10, purchases=["ripen"]))))

    def test_a_moment_has_to_match_exactly(self):
        self.assertNotIn("purchase_off_span", warn_codes(self.result(enc(duration=60), quiet(at=45, purchases=["ripen"]))))
        self.assertIn("purchase_off_span", warn_codes(self.result(enc(duration=60), quiet(at=44, purchases=["ripen"]))))

    def test_an_unknown_purchase_is_an_error_with_a_hint(self):
        r = self.result(quiet(purchases=["ripem"]), enc())
        e = next(x for x in r["errors"] if x["code"] == "unknown_purchase")
        self.assertIn("ripen", e["message"])

    def test_a_listed_purchase_without_a_computed_row_is_no_unknown_id(self):
        eco = {**ECONOMY, "purchases": [{"id": "broken_price"}]}
        r = self.result(enc(), quiet(purchases=["broken_price"]), economy=eco, purchases={})
        self.assertEqual(r["errors"], [])
        self.assertIn("시점을 모르는 구매: broken_price", notes(r))

    def test_the_hint_reads_the_listed_purchases(self):
        eco = {**ECONOMY, "purchases": [{"id": "broken_price"}]}
        r = self.result(enc(), quiet(purchases=["broken_pric"]), economy=eco, purchases={})
        self.assertIn("broken_price", next(e["message"] for e in r["errors"] if e["code"] == "unknown_purchase"))

    def test_without_an_economy_the_link_is_unchecked(self):
        r = self.result(enc(), quiet(purchases=["ripen"]), economy=None, purchases=None)
        self.assertIn("economy", r["unchecked_kinds"])
        self.assertIn("재화 흐름", printed(r))

    def test_no_link_needs_no_economy(self):
        self.assertNotIn("economy", self.result(enc(), economy=None, purchases=None)["unchecked_kinds"])

    def test_untimed_encounters_compare_the_stage(self):
        self.assertNotIn("purchase_off_span", warn_codes(self.result(enc(), quiet(purchases=["ripen"]))))
        w = warning(self.result(enc(), quiet(purchases=["late"])), "purchase_off_span")
        self.assertIn("s2", w["message"])
        self.assertIn("s1", w["message"])

    def test_the_stage_compare_follows_combat_stage_links(self):
        eco = {"economy": {}, "stages": [{"id": "r1", "combat_stage": "s1", "duration": 60}, {"id": "s2", "duration": 30}]}
        plan = {"ripen": {"id": "ripen", "at": 45.0, "stage": "r1"}}
        self.assertNotIn("purchase_off_span", warn_codes(self.result(enc(), quiet(purchases=["ripen"]), economy=eco, purchases=plan)))

    def test_a_broken_stage_does_not_blame_the_purchase_plan(self):
        r = self.result(enc(duration=20), enc("e3", repeat=0, duration=20), quiet(duration=20, purchases=["ripen"]))
        self.assertNotIn("purchase_off_span", warn_codes(r))
        self.assertIn("구매 대조: 1/1", notes(r))

    def test_a_broken_stage_still_compares_a_written_at(self):
        self.assertIn("purchase_off_span", warn_codes(self.result(enc(duration=20), enc("e3", repeat=0), quiet(at=50, duration=5, purchases=["ripen"]))))

    def between_rounds(self, shop_stage, timing="stage_end"):
        eco = {"economy": {"purchase_timing": timing}, "stages": [{"id": "s1", "duration": 60}, {"id": "s0", "status": "cut", "duration": 9}, {"id": "s2", "duration": 30}, {"id": "s3", "duration": 30}]}
        shop = quiet("shop", purchases=["buy"])
        lines = {"s1": level("s1", enc(), *([shop] if shop_stage == "s1" else [])), "s2": level("s2", *([shop] if shop_stage == "s2" else []), enc("e2", {"c": 6}))}
        return run(list(lines.values()), economy=eco, purchases={"buy": {"id": "buy", "at": 60.0, "stage": shop_stage == "s3" and "s2" or "s1"}})

    def test_a_shop_opening_the_next_round_matches_a_stage_end_purchase(self):
        self.assertNotIn("purchase_off_span", warn_codes(self.between_rounds("s2")))

    def test_a_shop_closing_the_round_still_matches(self):
        self.assertNotIn("purchase_off_span", warn_codes(self.between_rounds("s1")))

    def test_without_stage_end_the_next_stage_does_not_match(self):
        self.assertIn("purchase_off_span", warn_codes(self.between_rounds("s2", timing="any")))

    def test_a_shop_before_the_purchase_stage_does_not_match(self):
        r = run(both(level("s1", enc(), quiet("shop", purchases=["buy"]))), economy={"economy": {"purchase_timing": "stage_end"}, "stages": ECONOMY["stages"]},
                purchases={"buy": {"id": "buy", "at": 90.0, "stage": "s2"}})
        self.assertIn("purchase_off_span", warn_codes(r))

    def test_a_broken_settings_block_is_read_as_no_stage_end(self):
        r = self.result(enc(), quiet(purchases=["late"]), economy={"economy": "깨짐", "stages": ECONOMY["stages"]})
        self.assertIn("purchase_off_span", warn_codes(r))

    def test_a_purchase_at_the_very_start_has_no_stage_to_compare(self):
        r = self.result(enc(), quiet(purchases=["first"]), purchases={"first": {"id": "first", "at": 0.0, "stage": None}})
        self.assertNotIn("purchase_off_span", warn_codes(r))

    def test_a_purchase_without_a_time_is_named_in_a_note(self):
        r = self.result(enc(), quiet(purchases=["never"]))
        self.assertNotIn("purchase_off_span", warn_codes(r))
        self.assertIn("시점을 모르는 구매: never", notes(r))

    def test_a_cut_purchase_is_reported_as_cut(self):
        eco = {**ECONOMY, "purchases": [{"id": "old", "status": "cut"}]}
        r = self.result(enc(), quiet(purchases=["old"]), economy=eco)
        self.assertIn("cut_referenced", warn_codes(r))
        self.assertEqual(r["errors"], [])


class RestSpans(unittest.TestCase):
    """81: 쉬는 곳 사이의 누적 부담."""

    def test_load_counts_normal_encounters_between_rests(self):
        r = run(both(level("s1", enc(repeat=2), enc("e3"), quiet(rest=True), enc("e4"))))
        first, second = spans(r)[:2]
        self.assertEqual((first["from"], first["to"], first["closed_by"], first["load"]), ("e1", "q", "q", 3))
        self.assertEqual((second["from"], second["closed_by"], second["load"]), ("e4", None, 1))

    def test_load_is_measured_on_each_stage_curve(self):
        r = run(both(level("s1", enc(rest=True)), level("s2", enc("e2", {"c": 6}))))
        self.assertEqual([s["load"] for s in spans(r)], [1, 1])

    def test_a_guarded_rest_counts_its_own_fight_first(self):
        r = run(both(level("s1", enc(), enc("e3", rest=True), enc("e4"))))
        self.assertEqual([s["load"] for s in spans(r) if s["level"] == "s1"], [2, 1])

    def test_enemy_repeat_counts_like_the_level_threat(self):
        r = run(both(level("s1", enc(repeat=10, enemy_repeat={"b": 1}))))
        self.assertEqual(spans(r)[0]["threat"], r["levels"][0]["threat"])

    def test_hazard_is_part_of_the_load(self):
        r = run(both(level("s1", enc(), quiet("trap", hazard=40))))
        self.assertEqual(spans(r)[0]["load"], 1.5)

    def test_a_level_end_closes_the_span_by_default(self):
        self.assertEqual(len(spans(run())), 2)

    def test_carrying_levels_keeps_the_span_open(self):
        r = paced(*both(), pacing={"carry_levels": True})
        self.assertEqual([(s["level"], s["to_level"], s["load"]) for s in spans(r)], [("s1", "s2", 2)])

    def test_carry_follows_the_stage_order(self):
        r = paced(level("s2", enc("e2", {"c": 6})), level("s1", enc()), pacing={"carry_levels": True})
        self.assertEqual((spans(r)[0]["from"], spans(r)[0]["to"]), ("e1", "e2"))

    def test_carrying_past_a_level_that_fell_out_gives_no_load(self):
        r = paced(level("s1", enc()), level("s1b", enc("e5", repeat=9), combat_stage="s1", status="oops"), level("s2", enc("e2", {"c": 6})),
                  pacing={"carry_levels": True, "max_rest_load": 1})
        self.assertEqual([s["load"] for s in spans(r)], [None])
        self.assertNotIn("long_stretch", warn_codes(r))
        self.assertIn("형식 오류로 빠진 레벨", notes(r))

    def test_a_level_that_fell_out_changes_nothing_without_carry(self):
        r = paced(level("s1", enc()), level("s1b", enc("e5"), combat_stage="s1", status="oops"), level("s2", enc("e2", {"c": 6})))
        self.assertEqual([s["load"] for s in spans(r)], [1, 1])
        self.assertNotIn("형식 오류로 빠진 레벨", notes(r))

    def test_a_rest_that_may_not_come_does_not_cut(self):
        r = run(both(level("s1", enc(), quiet(rest=True, repeat=0.5), enc("e3"))))
        self.assertEqual(spans(r)[0]["load"], 2)
        self.assertIn("횟수가 1보다 작아", notes(r))
        self.assertIn("q", notes(r))

    def test_a_rest_right_after_a_rest_makes_no_empty_span(self):
        r = run(both(level("s1", quiet("q1", rest=True), quiet("q2", rest=True), enc())))
        self.assertEqual([s["from"] for s in spans(r) if s["level"] == "s1"], ["e1"])

    def test_over_the_limit_is_a_warning_on_the_first_encounter(self):
        r = paced(level("s1", enc(repeat=3), quiet(rest=True)), level("s2", enc("e2", {"c": 6})), pacing={"max_rest_load": 2})
        w = warning(r, "long_stretch")
        self.assertEqual((w["part"], w["owner"]), ("e1", "s1"))
        self.assertIn("3", w["message"])
        self.assertIn("2", w["message"])
        self.assertTrue(spans(r)[0]["over"])

    def test_at_the_limit_is_fine(self):
        self.assertNotIn("long_stretch", warn_codes(paced(*both(level("s1", enc(repeat=2))), pacing={"max_rest_load": 2})))

    def test_no_rest_at_all_is_one_span_and_said_so(self):
        r = paced(*both(), pacing={"max_rest_load": 5})
        self.assertIn("쉬는 곳이 없습니다", notes(r))

    def test_an_unknown_threat_gives_no_load_rather_than_a_partial_one(self):
        r = run(both(level("s1", enc(), enc("e3", {"c": 1}))), threat={"a": 10.0, "b": 30.0})
        self.assertIsNone(spans(r)[0]["load"])

    def test_without_a_curve_the_threat_stays_and_the_load_is_empty(self):
        r = run(both(level("s1", enc(role="x"))), budget=None)
        self.assertEqual((spans(r)[0]["load"], spans(r)[0]["threat"]), (None, 80))

    def test_a_broken_encounter_gives_no_load_rather_than_a_partial_one(self):
        r = run(both(level("s1", enc(), enc("e3", repeat=0))))
        self.assertEqual((spans(r)[0]["load"], spans(r)[0]["threat"]), (None, None))

    def test_an_unknown_threat_empties_the_threat_sum_too(self):
        r = run(both(level("s1", enc(), enc("e3", {"c": 1}))), threat={"a": 10.0, "b": 30.0})
        self.assertIsNone(spans(r)[0]["threat"])

    def test_an_untimed_encounter_empties_the_length(self):
        r = run(both(level("s1", enc(duration=10), enc("e3"))), economy=ECONOMY)
        self.assertIsNone(spans(r)[0]["length"])
        r = run(both(level("s1", enc(), enc("e3", at=0, duration=10))), economy=ECONOMY)
        self.assertIsNone(spans(r)[0]["length"])

    def test_the_span_ends_with_its_longest_stretch(self):
        r = run(both(level("s1", enc(at=0, duration=60), enc("e3", at=0, duration=20))), economy=ECONOMY)
        self.assertEqual(spans(r)[0]["length"], 60)

    def test_the_span_knows_its_length(self):
        r = run(both(level("s1", enc(duration=20), quiet(duration=10, rest=True), enc("e3", duration=30))), economy=ECONOMY)
        self.assertEqual([s["length"] for s in spans(r) if s["level"] == "s1"], [30, 30])

    def test_a_list_out_of_time_order_keeps_the_whole_length(self):
        r = run(both(level("s1", enc(at=50, duration=10), enc("e3", at=0, duration=10))), economy=ECONOMY)
        self.assertEqual(spans(r)[0]["length"], 60)

    def test_an_acknowledged_stretch_goes_away(self):
        data = {"levels": both(level("s1", enc(repeat=3), acknowledged={"long_stretch": {"e1": "일부러 긴 구간"}})), "threat_budget": BUDGET, "pacing": {"max_rest_load": 2}}
        r = lv.validate(data, enemies=ENEMIES, threat=THREAT, combat=COMBAT)
        common.apply_acknowledged("levels", data, r)
        self.assertNotIn("long_stretch", warn_codes(r))


class RewardSpans(unittest.TestCase):
    def test_no_reward_at_all_is_said_so(self):
        self.assertIn("보상이 없습니다", notes(paced(*both(), pacing={"max_reward_load": 5})))

    def test_without_a_limit_a_missing_mark_is_not_news(self):
        text = notes(paced(*both(level("s1", enc(duration=60)))))
        self.assertNotIn("보상이 없습니다", text)
        self.assertNotIn("쉬는 곳이 없습니다", text)

    def test_a_reward_somewhere_silences_that(self):
        self.assertNotIn("보상이 없습니다", notes(paced(*both(level("s1", enc(reward="상자"))), pacing={"max_reward_load": 5})))

    def test_rewards_cut_their_own_spans(self):
        r = run(both(level("s1", enc(), enc("e3", reward="상자"), quiet(rest=True), enc("e4"))))
        self.assertEqual([s["load"] for s in spans(r, "reward") if s["level"] == "s1"], [2, 1])
        self.assertEqual([s["load"] for s in spans(r) if s["level"] == "s1"], [2, 1])

    def test_rest_and_reward_are_independent(self):
        r = run(both(level("s1", enc(), quiet(rest=True), enc("e3"), quiet("gift", reward="제단"))))
        self.assertEqual([s["load"] for s in spans(r, "reward") if s["level"] == "s1"], [2])

    def test_the_tail_after_the_last_reward_counts(self):
        r = paced(*both(level("s1", enc(reward="상자"), enc("e3", repeat=3))), pacing={"max_reward_load": 2})
        self.assertEqual(warning(r, "reward_drought")["part"], "e3")

    def test_within_the_limit_is_fine(self):
        self.assertNotIn("reward_drought", warn_codes(paced(*both(level("s1", enc(repeat=2, reward="상자"))), pacing={"max_reward_load": 2})))

    def test_a_reward_that_may_not_come_does_not_cut(self):
        r = run(both(level("s1", enc(), quiet(reward="상자", repeat=0.5), enc("e3"))))
        self.assertEqual(spans(r, "reward")[0]["load"], 2)

    def test_the_reward_text_reaches_the_row(self):
        self.assertEqual(row(run(both(level("s1", enc(reward="상자")))))["reward"], "상자")


class StrongRuns(unittest.TestCase):
    def test_intensity_is_threat_over_the_curve(self):
        r = run(both(level("s1", strong())))
        self.assertEqual((row(r, "hard")["intensity"], row(r, "hard")["load"]), (1.5, 1.5))

    def test_load_multiplies_the_repeat_and_intensity_does_not(self):
        r = run(both(level("s1", strong(repeat=2))))
        self.assertEqual((row(r, "hard")["intensity"], row(r, "hard")["load"]), (1.5, 3))

    def test_strong_defaults_to_above_the_normal_range(self):
        r = run(both(level("s1", enc(enemies={"a": 10}), enc("e3", {"a": 9}))))
        self.assertEqual((row(r)["strong"], row(r, "e3")["strong"]), (True, False))

    def test_a_run_counts_repeats(self):
        r = run(both(level("s1", strong(repeat=2), strong("h2"))))
        self.assertEqual([(x["from"], x["to"], x["length"]) for x in r["pacing"]["strong_runs"]], [("hard", "h2", 3)])

    def test_a_lone_strong_encounter_is_no_run(self):
        self.assertEqual(run(both(level("s1", strong())))["pacing"]["strong_runs"], [])

    def test_a_normal_encounter_breaks_the_run(self):
        self.assertEqual(run(both(level("s1", strong(), enc(), strong("h2"))))["pacing"]["strong_runs"], [])

    def test_a_quiet_stretch_breaks_the_run(self):
        self.assertEqual(run(both(level("s1", strong(), quiet(), strong("h2"))))["pacing"]["strong_runs"], [])

    def test_a_guarded_rest_breaks_the_run_after_itself(self):
        self.assertEqual(run(both(level("s1", strong(rest=True), strong("h2"))))["pacing"]["strong_runs"], [])

    def test_a_rest_that_may_not_come_does_not_break_the_run(self):
        r = paced(*both(level("s1", strong(), strong("h2", rest=True, repeat=0.5), strong("h3"))), pacing={"max_strong_run": 2})
        self.assertEqual([(x["from"], x["to"], x["length"]) for x in r["pacing"]["strong_runs"]], [("hard", "h3", 2.5)])
        self.assertIn("strong_run", warn_codes(r))

    def test_a_quiet_room_that_may_not_come_does_not_break_the_run(self):
        r = run(both(level("s1", strong(), quiet(rest=True, repeat=0.5), strong("h2"))))
        self.assertEqual([x["length"] for x in r["pacing"]["strong_runs"]], [2])

    def test_a_carried_run_names_its_levels(self):
        r = paced(level("s1", strong()), level("s2", enc("e2", {"c": 12}, role="boss")), pacing={"carry_levels": True})
        self.assertIn("(s1~s2)", next(x for x in printed(r).splitlines() if "연속" in x))

    def test_a_run_does_not_cross_a_level_that_fell_out(self):
        r = paced(level("s1", strong()), level("s1b", enc("e5"), combat_stage="s1", status="oops"), level("s2", enc("e2", {"c": 12}, role="boss")),
                  pacing={"carry_levels": True})
        self.assertEqual(r["pacing"]["strong_runs"], [])

    def test_a_level_end_breaks_the_run_unless_carried(self):
        hard_two = enc("e2", {"c": 12}, role="boss")
        self.assertEqual(paced(level("s1", strong()), level("s2", hard_two))["pacing"]["strong_runs"], [])
        self.assertEqual(len(paced(level("s1", strong()), level("s2", hard_two), pacing={"carry_levels": True})["pacing"]["strong_runs"]), 1)

    def test_too_long_a_run_is_a_warning(self):
        r = paced(*both(level("s1", strong(), strong("h2"), strong("h3"))), pacing={"max_strong_run": 2})
        self.assertEqual(warning(r, "strong_run")["part"], "hard")

    def test_a_run_at_the_limit_is_fine(self):
        self.assertNotIn("strong_run", warn_codes(paced(*both(level("s1", strong(), strong("h2"))), pacing={"max_strong_run": 2})))

    def test_strong_at_moves_the_line(self):
        r = paced(*both(level("s1", enc(), enc("e3"))), pacing={"strong_at": 1, "max_strong_run": 1})
        self.assertEqual(warning(r, "strong_run")["part"], "e1")

    def test_without_a_curve_nothing_is_strong(self):
        r = run(both(level("s1", enc(role="x"))), budget=None)
        self.assertFalse(row(r)["strong"])
        self.assertIsNone(row(r)["intensity"])


class Settings(unittest.TestCase):
    def test_bad_settings_are_errors(self):
        for cfg in ([], {"max_rest_load": 0}, {"max_reward_load": "많이"}, {"max_strong_run": -1}, {"strong_at": 0}, {"carry_levels": "yes"}, {"oops": 1}):
            self.assertIn("schema", codes(paced(*both(), pacing=cfg)["errors"]), cfg)

    def test_bad_settings_do_not_stop_the_rest(self):
        r = paced(*both(), pacing={"oops": 1})
        self.assertEqual(r["encounters"], 2)

    def test_assumed_limits_are_said_and_block_the_final_gate(self):
        r = paced(*both(), pacing={"max_rest_load": 5, "provenance": {"kind": "assumed"}})
        self.assertIn("페이싱 기준의 출처가 가정입니다", notes(r))
        self.assertIn("pacing(페이싱 기준)", r["unverified"])

    def test_sourced_limits_say_nothing(self):
        r = paced(*both(), pacing={"max_rest_load": 5, "provenance": {"kind": "computed", "source": "reports/x.json"}})
        self.assertNotIn("페이싱 기준의 출처", notes(r))
        self.assertNotIn("pacing(페이싱 기준)", r["unverified"])

    def test_carry_alone_has_no_numbers_to_source(self):
        r = paced(*both(), pacing={"carry_levels": True})
        self.assertNotIn("페이싱 기준의 출처", notes(r))
        self.assertNotIn("pacing(페이싱 기준)", r["unverified"])

    def test_the_settings_alone_turn_the_tables_on(self):
        self.assertTrue(paced(*both(), pacing={"carry_levels": True})["pacing"]["used"])

    def test_a_quiet_stretch_alone_turns_the_tables_on(self):
        self.assertTrue(run(both(level("s1", enc(), quiet())))["pacing"]["used"])

    def test_times_alone_turn_the_tables_on(self):
        self.assertTrue(run(both(level("s1", enc(duration=5))))["pacing"]["used"])

    def test_marks_alone_turn_pacing_on_without_warnings(self):
        r = run(both(level("s1", enc(repeat=99), quiet(rest=True))))
        self.assertTrue(r["pacing"]["used"])
        self.assertNotIn("long_stretch", warn_codes(r))

    def test_a_game_without_pacing_keeps_its_tables(self):
        text = lv.table({}, run())
        self.assertNotIn("세기", text)
        self.assertNotIn("구간", text)


class Output(Project):
    def result(self):
        lines = level("s1", enc(duration=20), quiet(duration=10, rest=True, reward="제단", purchases=["ripen"]), enc("e3", duration=30))
        return run(both(lines), economy=ECONOMY, purchases={"ripen": {"id": "ripen", "at": 25.0, "stage": "s1"}})

    def test_the_table_lays_out_the_rhythm(self):
        text = lv.table({}, self.result())
        self.assertIn("| s1 | q | 20~30초 |", text)
        self.assertIn("쉬는 곳", text)
        self.assertIn("보상: 제단", text)
        self.assertIn("구매 ripen", text)
        self.assertIn("쉬는 곳 사이", text)
        self.assertIn("보상 사이", text)

    def test_rounds_once_for_every_reader(self):
        r = run(both(level("s1", enc(enemies={"a": 7}, repeat=3), enc("e3", {"a": 7}))))   # 세기 0.875
        self.assertEqual((row(r)["intensity"], row(r)["load"]), (0.88, 2.62))
        self.assertEqual(spans(r)[0]["load"], 3.5)

    def test_a_span_of_one_encounter_names_it_once(self):
        r = run(both(level("s1", enc(rest=True))))
        self.assertIn("구간 쉬는 곳 사이 e1:", printed(r))

    def test_no_budget_means_a_plain_dash(self):
        r = run(both(level("s1", enc(), quiet())))
        self.assertNotIn("(–~–)", lv.table({}, r))

    def test_a_moment_shows_one_time(self):
        r = run(both(level("s1", enc(duration=60), enc("e3", at=50))), economy=ECONOMY)
        self.assertIn("| s1 | e3 | 50초 |", lv.table({}, r))

    def test_the_rhythm_table_follows_the_run(self):
        r = run([level("s2", enc("e2", {"c": 6}, duration=5)), level("s1", enc(duration=25))])
        self.assertEqual(r["pacing"]["order"], ["s1", "s2"])
        rhythm = lv.table({}, r).split("| 레벨 | 조우 | 시각 |")[1]
        self.assertLess(rhythm.index("| s1 | e1 |"), rhythm.index("| s2 | e2 |"))

    def test_the_table_says_where_strong_starts(self):
        self.assertIn("세기 1.25 이상", lv.table({}, self.result()))

    def test_the_report_says_where_strong_starts_when_it_lists_a_run(self):
        self.assertIn("세기 1.25 이상", next(x for x in printed(run(both(level("s1", strong(), strong("h2"))))).splitlines() if "연속" in x))

    def test_a_game_without_pacing_or_runs_is_not_told(self):
        self.assertNotIn("세기", printed(run()))

    def test_a_pipe_in_a_reward_stays_in_its_cell(self):
        line = next(x for x in lv.table({}, run(both(level("s1", enc(reward="상자 | 열쇠\n둘"))))).splitlines() if "상자" in x)
        self.assertEqual(line.count("|") - line.count("\\|"), 7)
        self.assertTrue(line.endswith("열쇠 둘 |"), line)

    def test_strong_runs_are_in_the_table(self):
        r = run(both(level("s1", strong(), strong("h2"))))
        self.assertIn("강한 조우 연속", lv.table({}, r))

    def test_the_check_report_lists_the_spans(self):
        text = printed(self.result())
        self.assertIn("쉬는 곳 사이", text)
        self.assertIn("e1~q", text)

    def test_sample_project_shows_pacing_without_warnings(self):
        code, out = self.check()
        self.assertEqual(code, 0, out)
        self.assertIn("쉬는 곳 사이", out)
        self.assertNotIn("long_stretch", out)

    def test_a_purchase_with_a_broken_price_blames_the_economy_not_the_link(self):
        def broken(d):
            next(x for x in d["purchases"] if x["id"] == "weapon_plus_2")["price"] = {"enhance": "nope", "level": 2}
        self.edit("data/economy.json", broken)
        r = self.report("levels")
        self.assertEqual(r["errors"], [])
        self.assertIn("시점을 모르는 구매: weapon_plus_2", notes(r))

    def test_the_viewer_labels_every_new_code(self):
        html = (STUDIO / "assets/viewer.html").read_text(encoding="utf-8")
        for code in ("long_stretch", "reward_drought", "strong_run", "time_gap", "time_outside_stage", "purchase_off_span", "unknown_purchase"):
            self.assertIn(f"{code}:", html)
        self.assertIn("r.pacing", html)
        self.assertIn("pacing.strong_at", html)

    def test_the_docs_cover_the_new_keys(self):
        fmt = (ROOT / "skills/level-design/references/levels-format.md").read_text(encoding="utf-8")
        skill = (ROOT / "skills/level-design/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("순간만 있는 단계", fmt)
        self.assertIn("`hazard` × 횟수", fmt)
        for word in ("`rest`", "`reward`", "`hazard`", "`at`", "`duration`", "`purchases`", "`pacing`", "`max_rest_load`", "`max_reward_load`",
                     "`max_strong_run`", "`strong_at`", "`carry_levels`", "`long_stretch`", "`reward_drought`", "`strong_run`", "`time_gap`",
                     "`time_outside_stage`", "`purchase_off_span`", "`unknown_purchase`"):
            self.assertIn(word, fmt)
        self.assertIn("페이싱", skill)
        tools = skill[skill.index("## 도구"):skill.index("## 절차")]
        self.assertIn("리듬 표", tools)
        self.assertIn("페이싱", tools)
        self.assertIn("stage_end", fmt[fmt.index("| `purchase_off_span` |"):])
        self.assertNotIn("L2", skill)

    def test_sample_levels_use_the_new_keys(self):
        data = json.loads((SAMPLE / "data/levels.json").read_text(encoding="utf-8"))
        text = json.dumps(data, ensure_ascii=False)
        for key in ('"pacing"', '"rest"', '"reward"', '"purchases"', '"duration"'):
            self.assertIn(key, text)


if __name__ == "__main__":
    unittest.main()
