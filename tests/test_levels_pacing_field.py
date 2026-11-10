"""레벨 페이싱 현장 시험(이슈 118~142) 테스트: 네 가지 게임 모양에서 막힌 것을 고친 동작. 표준 라이브러리 unittest만 사용한다."""
import json
import re
import subprocess
import sys
import unittest

from _studio import ROOT, STUDIO, common, economy as ec, levels as lv, run_cli, level_guide, level_format
from test_economy import base, validate as economy_validate
from test_levels import BUDGET, COMBAT, ENEMIES, THREAT, both, enc, level, row, run
from test_levels_field import ECONOMY, notes, printed
from test_levels_pacing import PLAN, clock_note, paced, quiet, spans, strong, warn_codes
from test_levels_recheck import Project, warning


def spend(pid="a", amount=10, **over):
    """금화 10으로 사는 구매. base()의 수입은 처음 100초 동안 초당 1이다."""
    return {"id": pid, "price": {"amount": amount, "currency": "gold"}, **over}


def swap_pair(first, second):
    """같은 시각의 두 조우를 두 순서로 적은 레벨들."""
    return (first, second), (second, first)


class SameTime(unittest.TestCase):
    """118: 같은 시각의 조우는 목록 순서로 결과가 바뀌지 않는다."""

    def runs(self, r):
        return [(x["from"], x["to"], x["length"]) for x in r["pacing"]["strong_runs"]]

    def test_a_mixed_stretch_does_not_join_the_next_strong_one(self):
        press, hatch = enc("press", at=0, duration=40, repeat=13), strong("hatch", at=0, duration=40, repeat=2)
        for pair in swap_pair(press, hatch):
            r = run(both(level("s1", *pair, strong("surge", at=40, duration=20, repeat=5))), economy=ECONOMY)
            self.assertEqual(self.runs(r), [("surge", "surge", 5)], [x["id"] for x in pair])

    def test_parallel_strong_stretches_count_together(self):
        r = run(both(level("s1", strong("a", at=0, duration=40), strong("b", at=0, duration=40), strong("c", at=40, duration=20))), economy=ECONOMY)
        self.assertEqual(self.runs(r), [("a", "c", 3)])

    def test_a_mixed_stretch_breaks_a_run(self):
        r = run(both(level("s1", strong("a", at=0, duration=20), enc("n", at=20, duration=20), strong("b", at=20, duration=20), strong("c", at=40, duration=20))), economy=ECONOMY)
        self.assertEqual(self.runs(r), [])

    def test_a_long_stretch_keeps_its_group_open_past_a_short_one(self):
        r = run(both(level("s1", strong("a", at=0, duration=60), strong("b", at=10, duration=10), enc("n", at=30, duration=10), strong("c", at=60))), economy=ECONOMY)
        self.assertEqual(self.runs(r), [])

    def test_a_run_ending_in_parallel_stretches_names_the_last_one(self):
        r = run(both(level("s1", strong("a", at=0, duration=20), strong("b", at=20, duration=20), strong("c", at=20, duration=20))), economy=ECONOMY)
        self.assertEqual(self.runs(r), [("a", "c", 3)])

    def test_a_passing_moment_does_not_break_a_run(self):
        r = run(both(level("s1", strong("a", at=0, duration=30), quiet("altar", at=30, open_for=30, purchases=["ripen"]), strong("b", at=30, duration=30))), economy=ECONOMY, purchases=PLAN)
        self.assertEqual(self.runs(r), [("a", "b", 2)])

    def test_a_rest_moment_breaks_a_run(self):
        r = run(both(level("s1", strong("a", at=0, duration=30), quiet("q", at=30, rest=True), strong("b", at=30, duration=30))), economy=ECONOMY)
        self.assertEqual(self.runs(r), [])

    def test_a_quiet_stretch_with_a_length_breaks_a_run(self):
        r = run(both(level("s1", strong("a", at=0, duration=20), quiet("q", at=20, duration=20), strong("b", at=40, duration=20))), economy=ECONOMY)
        self.assertEqual(self.runs(r), [])

    def test_a_weak_moment_breaks_a_run(self):
        r = run(both(level("s1", strong("a", at=0, duration=30), enc("n", at=30), strong("b", at=30, duration=30))), economy=ECONOMY)
        self.assertEqual(self.runs(r), [])

    def test_a_moment_inside_a_stretch_joins_it(self):
        r = run(both(level("s1", enc("n", at=0, duration=60), strong("boss", at=30), strong("h2", at=60))), economy=ECONOMY)
        self.assertEqual(self.runs(r), [])

    def test_untimed_levels_keep_the_list_order(self):
        self.assertEqual(self.runs(run(both(level("s1", strong(), strong("h2"))))), [("hard", "h2", 2)])


class TimeOrder(unittest.TestCase):
    """119: 시각을 모두 알면 구간은 시각 순서로 끊는다."""

    def test_a_mark_listed_last_cuts_where_its_time_is(self):
        gift = quiet("gift", at=30, reward="제단")
        for lines in ((enc(at=0, duration=30), gift, enc("e3", at=30, duration=30)), (enc(at=0, duration=30), enc("e3", at=30, duration=30), gift)):
            r = run(both(level("s1", *lines)), economy=ECONOMY)
            self.assertEqual([(s["from"], s["to"], s["load"]) for s in spans(r, "reward") if s["level"] == "s1"][0], ("e1", "gift", 1))

    def test_a_tie_puts_the_quiet_mark_first(self):
        r = run(both(level("s1", enc("e3", at=0, duration=60), quiet("gift", at=0, reward="제단"))), economy=ECONOMY)
        self.assertEqual([s["from"] for s in spans(r, "reward")][0], "e3")

    def test_a_parallel_mark_gives_the_same_spans_either_way(self):
        press, hatch = enc("press", at=0, duration=40), enc("hatch", at=0, duration=40, reward="드랍")
        answers = [[(s["load"], s["closed_by"]) for s in spans(run(both(level("s1", *pair, enc("after", at=40, duration=20))), economy=ECONOMY), "reward")] for pair in swap_pair(press, hatch)]
        self.assertEqual(answers[0], answers[1])
        self.assertEqual(answers[0][0], (2, "hatch"))

    def test_the_rhythm_table_follows_the_clock(self):
        r = run(both(level("s1", enc("late", at=30, duration=30), enc("early", at=0, duration=30))), economy=ECONOMY)
        rhythm = lv.table({}, r).split("| 레벨 | 조우 | 시각 |")[1]
        self.assertLess(rhythm.index("early"), rhythm.index("late"))

    def test_an_unknown_time_keeps_the_list_order(self):
        r = run(both(level("s1", enc("late", at=30), enc("mid"), quiet("gift", reward="제단"), enc("early", at=0))))
        self.assertEqual(spans(r, "reward")[0]["to"], "gift")
        self.assertEqual(spans(r, "reward")[0]["from"], "late")


class SpanLength(unittest.TestCase):
    """120: 구간 길이는 쉬는 곳이나 제단 앞까지다."""

    def test_a_quiet_closer_ends_the_span_at_its_start(self):
        r = run(both(level("s1", enc(duration=20), quiet(duration=10, rest=True), enc("e3", duration=30))), economy=ECONOMY)
        self.assertEqual([s["length"] for s in spans(r) if s["level"] == "s1"], [20, 30])

    def test_a_guarded_closer_counts_its_own_fight(self):
        r = run(both(level("s1", enc(duration=20), enc("e3", duration=10, rest=True), enc("e4", duration=30))), economy=ECONOMY)
        self.assertEqual([s["length"] for s in spans(r) if s["level"] == "s1"], [30, 30])

    def test_spans_never_add_up_past_the_run(self):
        r = run(both(level("s1", quiet("gift", at=0, reward="제단", open_for=60, purchases=["ripen"]), enc(at=0, duration=30), quiet("g2", at=30, reward="상자"), enc("e3", at=30, duration=30)),
                     level("s2", enc("e2", {"c": 6}, at=60, duration=30))), economy=ECONOMY, purchases=PLAN)
        self.assertLessEqual(sum(s["length"] for s in spans(r, "reward")), 90)


class OpenFor(unittest.TestCase):
    """123, 120, 124: 판의 시간을 차지하지 않고 열려 있는 시설."""

    def result(self, *encounters, second=None, purchases=PLAN):
        return run(both(level("s1", *encounters), second), economy=ECONOMY, purchases=purchases)

    def test_a_purchase_inside_the_opening_is_quiet(self):
        r = self.result(quiet("altar", at=30, reward="제단", open_for=20, purchases=["ripen"]), enc(at=0, duration=60))
        self.assertNotIn("purchase_off_span", warn_codes(r))

    def test_a_purchase_after_it_closes_warns(self):
        r = self.result(quiet("altar", at=30, open_for=10, purchases=["ripen"]), enc(at=0, duration=60))
        self.assertIn("30~40초", warning(r, "purchase_off_span")["message"])

    def test_it_can_stay_open_past_its_stage(self):
        r = self.result(quiet("altar", at=30, open_for=60, purchases=["late"]), enc(at=0, duration=60))
        self.assertNotIn("purchase_off_span", warn_codes(r))
        self.assertNotIn("time_outside_stage", warn_codes(r))

    def test_it_fills_no_time(self):
        r = self.result(quiet("altar", at=0, open_for=60, purchases=["ripen"]), enc(at=0, duration=20), enc("e3", at=40, duration=20))
        self.assertIn("20~40초", warning(r, "time_gap")["message"])

    def test_it_leaves_the_clock_alone(self):
        r = self.result(quiet("altar", at=30, open_for=30, purchases=["ripen"]), enc(duration=30), enc("e3", duration=30))
        self.assertEqual((row(r)["start"], row(r, "e3")["start"]), (0, 30))
        self.assertEqual([k for k in warn_codes(r) if k.startswith("time_")], [])

    def test_a_fight_with_a_length_still_moves_the_clock(self):
        r = self.result(enc(at=0, duration=30, open_for=40, purchases=["ripen"]), enc("e3", duration=30))
        self.assertEqual(row(r, "e3")["start"], 30)

    def test_it_needs_a_time(self):
        text = next(e["message"] for e in self.result(enc(), quiet(open_for=5, purchases=["ripen"]))["errors"] if e["code"] == "schema")
        self.assertIn("at", text)

    def test_it_needs_purchases(self):
        self.assertIn("schema", [e["code"] for e in self.result(enc(), quiet(at=0, open_for=5))["errors"]])

    def test_a_bad_value_is_an_error(self):
        self.assertIn("schema", [e["code"] for e in self.result(enc(), quiet(at=0, open_for=-1, purchases=["ripen"]))["errors"]])

    def test_the_table_shows_it(self):
        r = self.result(quiet("altar", at=30, open_for=20, purchases=["ripen"]), enc(at=0, duration=60))
        self.assertIn("30~50초 열림", lv.table({}, r))


class QuietOverFights(unittest.TestCase):
    """124: 싸움과 겹치는 적 없는 조우는 빈 시간을 메우지 않는다."""

    def test_a_long_quiet_mark_does_not_hide_a_hole(self):
        r = run(both(level("s1", quiet("altar", at=0, duration=60), enc(at=0, duration=20), enc("e3", at=40, duration=20))), economy=ECONOMY)
        self.assertIn("20~40초", warning(r, "time_gap")["message"])

    def test_a_quiet_stretch_of_its_own_still_fills(self):
        r = run(both(level("s1", enc(at=0, duration=20), quiet(at=20, duration=20), enc("e3", at=40, duration=20))), economy=ECONOMY)
        self.assertNotIn("time_gap", warn_codes(r))


class Forks(unittest.TestCase):
    """125: 택일 방의 값은 평균이다."""

    def fork(self):
        return run(both(level("s1", enc(duration=30), quiet("spring", rest=True, repeat=0.5, at=30, duration=30), enc("fight", repeat=0.5, at=30, duration=30))), economy=ECONOMY)

    def test_the_note_says_the_value_is_an_average(self):
        self.assertIn("평균", notes(self.fork()))
        self.assertNotIn("그 판을 기준으로", notes(self.fork()))

    def test_a_fork_is_not_read_as_both_at_once(self):
        self.assertNotIn("겹치는", notes(self.fork()))

    def test_a_real_overlap_is_still_read_as_both(self):
        r = run(both(level("s1", enc(at=0, duration=60), enc("e3", at=0, duration=60, repeat=0.5))), economy=ECONOMY)
        self.assertIn("겹치는", notes(r))


class RewardsCrossLevels(unittest.TestCase):
    """126: 보상 구간은 체력과 달리 레벨을 넘는다."""

    def test_a_drought_across_levels_is_seen_without_carry(self):
        r = paced(level("s1", enc(repeat=3)), level("s2", enc("e2", {"c": 6}, repeat=3, reward="상자")), pacing={"max_reward_load": 4})
        self.assertEqual(warning(r, "reward_drought")["part"], "e1~e2")

    def test_rest_spans_still_stop_at_the_level_end(self):
        r = paced(level("s1", enc(repeat=3)), level("s2", enc("e2", {"c": 6}, repeat=3)))
        self.assertEqual([s["load"] for s in spans(r)], [3, 3])

    def test_a_level_that_fell_out_empties_the_reward_span_when_rewards_are_used(self):
        r = paced(level("s1", enc()), level("s1b", enc("e5"), combat_stage="s1", status="oops"), level("s2", enc("e2", {"c": 6}, reward="상자")))
        self.assertEqual([s["load"] for s in spans(r, "reward")], [None])
        self.assertIn("형식 오류로 빠진 레벨", notes(r))


class StageWithoutEconomy(unittest.TestCase):
    """127: 재화 흐름에 없는 단계의 시각을 지어내지 않는다."""

    ECO = {"economy": {}, "stages": [{"id": "s1", "duration": 60}]}

    def test_the_time_is_unknown(self):
        r = run(both(level("s1", enc(duration=60)), level("s2", enc("e2", {"c": 6}, duration=30))), economy=self.ECO)
        self.assertIsNone(row(r, "e2")["start"])
        self.assertIn("시각을 모르는 조우: e2", notes(r))

    def test_a_written_at_is_kept(self):
        r = run(both(level("s1", enc(duration=60)), level("s2", enc("e2", {"c": 6}, at=30, duration=30))), economy=self.ECO)
        self.assertEqual(row(r, "e2")["start"], 30)

    def test_without_any_economy_levels_still_follow(self):
        r = run(both(level("s1", enc(duration=60)), level("s2", enc("e2", {"c": 6}, duration=30))))
        self.assertEqual(row(r, "e2")["start"], 60)


class EarlyAndLatePurchases(unittest.TestCase):
    """121: 돈이 모이는 때와 상점이 열리는 때가 다르면 다음 할 일을 말한다."""

    def message(self, *encounters, plan=PLAN):
        return warning(run(both(level("s1", *encounters)), economy=ECONOMY, purchases=plan), "purchase_off_span")["message"]

    def test_money_ready_early_points_at_after(self):
        self.assertIn("after", self.message(enc(duration=50), quiet(duration=10, purchases=["ripen"])))

    def test_money_ready_late_points_at_the_plan(self):
        text = self.message(quiet(duration=10, purchases=["ripen"]), enc(duration=50))
        self.assertIn("가격이나 수입", text)
        self.assertNotIn("after", text)

    def test_after_takes_a_time(self):
        r = economy_validate(base(purchases=[spend(after=90)]))
        self.assertEqual(r["errors"], [])
        self.assertEqual(r["purchases"][0]["at"], 90)

    def test_after_as_a_time_still_waits_for_the_money(self):
        early, late = economy_validate(base(purchases=[spend()]))["purchases"][0]["at"], economy_validate(base(purchases=[spend(after=0.1)]))["purchases"][0]["at"]
        self.assertEqual(early, late)

    def test_a_negative_time_is_an_error(self):
        self.assertIn("schema", [e["code"] for e in economy_validate(base(purchases=[spend(after=-1)]))["errors"]])

    def test_a_time_past_the_run_is_an_error(self):
        r = economy_validate(base(purchases=[spend(after=201)]))
        self.assertEqual([e["code"] for e in r["errors"]], ["schema"])
        self.assertIn("200", r["errors"][0]["message"])
        self.assertIsNone(r["purchases"][0]["at"] if r["purchases"] else None)

    def test_the_very_end_of_the_run_is_fine(self):
        self.assertEqual(economy_validate(base(purchases=[spend(after=200)]))["errors"], [])

    def test_an_unknown_run_length_is_not_judged(self):
        d = base(purchases=[spend(after=999)])
        del d["stages"][1]["duration"]
        self.assertNotIn("판 끝", " ".join(e["message"] for e in economy_validate(d)["errors"]))

    def test_after_of_another_shape_is_an_error_not_a_crash(self):
        for bad in ([1], {"a": 1}, True):
            self.assertEqual([e["code"] for e in economy_validate(base(purchases=[spend(after=bad)]))["errors"]], ["unknown_stage"], bad)

    def test_a_wrong_stage_is_still_unknown(self):
        self.assertIn("unknown_stage", [e["code"] for e in economy_validate(base(purchases=[spend(after="nope")]))["errors"]])


class PurchaseRows(unittest.TestCase):
    """137: 구매 시각이 표에 보이고 어긋남이 참고 줄에 보인다."""

    def result(self, *encounters):
        return run(both(level("s1", *encounters)), economy=ECONOMY, purchases=PLAN)

    def test_the_rhythm_table_shows_the_purchase_time(self):
        self.assertIn("구매 ripen 45초", lv.table({}, self.result(enc(duration=30), quiet(duration=30, purchases=["ripen"]))))

    def test_the_note_counts_what_is_off(self):
        self.assertIn("어긋남 1", notes(self.result(quiet(duration=30, purchases=["ripen"]), enc(duration=30))))

    def test_a_clean_note_says_nothing_of_it(self):
        self.assertNotIn("어긋남", notes(self.result(enc(duration=30), quiet(duration=30, purchases=["ripen"]))))

    def test_the_same_purchase_twice_on_one_encounter_is_an_error(self):
        self.assertIn("schema", [e["code"] for e in self.result(enc(), quiet(purchases=["ripen", "ripen"]))["errors"]])

    def test_a_purchase_between_runs_is_called_that(self):
        r = run(both(level("s1", enc(), quiet(purchases=["meta"]))), economy=ECONOMY, purchases={"meta": {"id": "meta", "at": None, "stage": None, "runs": 1}})
        self.assertIn("판 사이 구매: meta", notes(r))
        self.assertNotIn("시점을 모르는 구매", notes(r))


class Messages(unittest.TestCase):
    """138, 141: 메시지가 조우를 말하고 파이썬 표기를 쓰지 않는다."""

    def test_the_outside_warning_names_the_encounters(self):
        text = warning(run(both(level("s1", enc(at=0, duration=20), enc("e3", at=50, duration=20))), economy=ECONOMY), "time_outside_stage")["message"]
        self.assertIn("e3", text)
        self.assertNotIn("e1", text)

    def test_a_run_of_one_encounter_names_it_once(self):
        r = paced(*both(level("s1", strong(repeat=5))), pacing={"max_strong_run": 2})
        self.assertNotIn("hard~hard", warning(r, "strong_run")["message"])

    def test_values_are_shown_as_json(self):
        r = run(both(level("s1", enc(), enc("e3", rest=None))))
        self.assertIn("null", next(e["message"] for e in r["errors"] if e["where"] == "s1.e3"))
        r = paced(*both(), pacing={"carry_levels": None})
        self.assertIn("null", next(e["message"] for e in r["errors"]))

    def test_whole_counts_read_as_whole_numbers(self):
        r = run(both(level("s1", enc(enemies={"a": 2.5}, repeat=2))))
        self.assertIn('"a": 5}', lv.table({}, r))


class Particles(unittest.TestCase):
    """숫자와 id 뒤의 조사는 c.josa가 정한다. 괄호 표기를 손으로 적지 않는다."""

    def test_no_message_writes_both_forms_by_hand(self):
        pattern = re.compile(r"\}(을\(를\)|은\(는\)|이\(가\)|와\(과\))")
        found = [f"{p.name}:{n}" for p in sorted((STUDIO / "scripts/studio_data").glob("*.py")) for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if pattern.search(line)]
        self.assertEqual(found, [])

    def test_a_number_takes_one_form(self):
        r = run(both(level("s1", enc(duration=50), quiet(duration=10, purchases=["ripen"]))), economy=ECONOMY, purchases=PLAN)
        self.assertIn("시각 50을 적습니다", warning(r, "purchase_off_span")["message"])


class RestColumns(unittest.TestCase):
    """134, 135: 회복이 없는 게임과 시간 게임의 표."""

    def test_a_game_without_rests_or_a_limit_has_no_rest_rows(self):
        r = run(both(level("s1", enc(reward="상자"))))
        self.assertNotIn("쉬는 곳 사이", lv.table({}, r))
        self.assertNotIn("쉬는 곳 사이", printed(r))
        self.assertIn("보상 사이", lv.table({}, r))

    def test_a_limit_keeps_the_rows(self):
        r = paced(*both(level("s1", enc(reward="상자"))), pacing={"max_rest_load": 9})
        self.assertIn("쉬는 곳 사이", lv.table({}, r))

    def test_load_per_time_shows_a_faster_refill(self):
        r = run(both(level("s1", enc(duration=30, repeat=6), enc("e3", duration=30, repeat=3))), economy=ECONOMY)
        self.assertEqual((row(r)["rate"], row(r, "e3")["rate"]), (0.2, 0.1))
        self.assertIn("길이당 부담", lv.table({}, r))

    def test_no_length_no_rate(self):
        self.assertIsNone(row(run(both(level("s1", enc(at=0)))))["rate"])


class EncounterAck(unittest.TestCase):
    """140: 조우에 적은 acknowledged는 레벨에 적으라고 말한다."""

    def test_it_says_where(self):
        r = run(both(level("s1", enc(acknowledged={"long_stretch": "이유"}))))
        text = next(e["message"] for e in r["errors"] if e["code"] == "schema")
        self.assertIn("레벨", text)
        self.assertNotIn("알 수 없는 키", text)

    def test_an_empty_reason_shows_the_target_form(self):
        data = {"levels": both(level("s1", enc(), acknowledged={"long_stretch": {"e1": ""}})), "threat_budget": BUDGET}
        r = lv.validate(data, enemies=ENEMIES, threat=THREAT, combat=COMBAT)
        common.apply_acknowledged("levels", data, r)
        self.assertIn("{대상: 이유}", next(e["message"] for e in r["errors"] if "acknowledged" in e["message"]))


class SpanAcks(unittest.TestCase):
    """129: 구간의 확인은 구간 전체를 이름으로 삼아서, 구간이 달라지면 경고가 돌아온다."""

    def result(self, *encounters, ack=None):
        lines = level("s1", *encounters, **({"acknowledged": ack} if ack else {}))
        data = {"levels": both(lines), "threat_budget": BUDGET, "pacing": {"max_rest_load": 2}}
        r = lv.validate(data, enemies=ENEMIES, threat=THREAT, combat=COMBAT)
        common.apply_acknowledged("levels", data, r)
        return r

    def test_the_span_name_acknowledges_it(self):
        r = self.result(enc(repeat=3), quiet(rest=True), ack={"long_stretch": {"e1~q": "일부러 긴 구간"}})
        self.assertNotIn("long_stretch", warn_codes(r))

    def test_moving_the_rest_brings_the_warning_back(self):
        r = self.result(enc(repeat=3), enc("e3"), quiet(rest=True), ack={"long_stretch": {"e1~e3": "옛 구간"}})
        self.assertIn("long_stretch", warn_codes(r))

    def test_the_acknowledged_line_keeps_the_value(self):
        r = self.result(enc(repeat=3), quiet(rest=True), ack={"long_stretch": {"e1~q": "일부러 긴 구간"}})
        self.assertEqual(r["acknowledged"][0]["value"], "부담 3")


class UnusedAcks(Project):
    """128: 쓰이지 않은 확인을 알린다."""

    def set_ack(self, ack, rel="data/levels.json"):
        self.edit(rel, lambda d: d["levels"][0].__setitem__("acknowledged", ack))

    def test_a_wrong_target_is_named_with_a_hint(self):
        self.edit("data/economy.json", lambda d: d["stages"][0]["kills"].__setitem__("slime", 400))
        self.set_ack({"kills_differ": {"slimee": "이유"}})
        text = "\n".join(self.report("levels")["ack_notes"])
        self.assertIn("kills_differ(slimee)", text)
        self.assertIn("slime", text.split("kills_differ(slimee)")[1])

    def test_a_wrong_code_is_named_with_a_hint(self):
        self.edit("data/economy.json", lambda d: d["stages"][0]["kills"].__setitem__("slime", 400))
        self.set_ack({"kills_differs": "이유"})
        self.assertIn("kills_differ", "\n".join(self.report("levels")["ack_notes"]).split("kills_differs")[1])

    def test_a_used_ack_is_not_named(self):
        self.edit("data/economy.json", lambda d: d["stages"][0]["kills"].__setitem__("slime", 400))
        self.set_ack({"kills_differ": {"slime": "이유"}})
        self.assertEqual(self.report("levels")["ack_notes"], [])

    def test_a_run_with_errors_does_not_guess(self):
        def broke(d):
            d["levels"][0]["encounters"][0]["repeat"] = 0
            d["levels"][0]["acknowledged"] = {"kills_differ": {"slime": "처치 수가 다른 것은 의도"}}
        self.edit("data/levels.json", broke)
        self.edit("data/economy.json", lambda d: d["stages"][0]["kills"].__setitem__("slime", 400))
        self.assertEqual(self.report("levels")["ack_notes"], [])

    def test_a_cut_entry_is_left_alone(self):
        self.edit("data/levels.json", lambda d: d["levels"].append({"id": "old", "status": "cut", "combat_stage": "zone_1", "encounters": [], "acknowledged": {"kills_differ": {"slime": "옛 확인"}}}))
        self.assertEqual(self.report("levels")["ack_notes"], [])

    def test_check_prints_it(self):
        self.set_ack({"long_strech": "이유"})
        self.assertIn("쓰이지 않은 확인", self.check()[1])

    def test_an_incomplete_run_does_not_guess(self):
        self.set_ack({"long_strech": "이유"})
        (self.root / "data/combat.json").unlink()
        self.assertEqual(self.report("levels")["ack_notes"], [])

    def test_other_kinds_are_left_alone(self):
        self.edit("data/items.json", lambda d: d["items"][0].__setitem__("acknowledged", {"over_budget": "다른 파일이 읽는 확인"}))
        self.assertNotIn("쓰이지 않은 확인", self.check()[1])

    def test_the_viewer_shows_it_on_both_tabs(self):
        html = (STUDIO / "assets/viewer.html").read_text(encoding="utf-8")
        for name, end in (("function renderEconomy", "function renderLevels"), ("function renderLevels", "function renderPlaytests")):
            self.assertIn("r.ack_notes", html[html.index(name):html.index(end)], name)


class EconomyKeys(unittest.TestCase):
    """130: 재화 흐름의 모르는 키는 오류다."""

    def errors(self, data):
        return [e for e in economy_validate(data)["errors"] if e["code"] == "schema"]

    def test_a_typo_in_the_settings(self):
        d = base()
        d["economy"]["purchase_timng"] = "stage_end"
        self.assertIn("purchase_timing", self.errors(d)[0]["message"])

    def test_a_typo_in_a_stage(self):
        d = base()
        d["stages"][0]["durration"] = 5
        self.assertIn("duration", self.errors(d)[0]["message"])

    def test_a_typo_in_a_purchase(self):
        d = base(purchases=[spend(tagret=[1, 2])])
        self.assertIn("target", self.errors(d)[0]["message"])

    def test_notes_are_free(self):
        d = base(purchases=[spend(_memo=1, note="메모")])
        d["economy"].update({"_memo": 1, "note": "메모"})
        d["stages"][0].update({"_memo": 1, "note": "메모"})
        self.assertEqual(self.errors(d), [])


class Version(unittest.TestCase):
    """141: 설치본의 판을 확인한다."""

    def run_version(self):
        return subprocess.run([sys.executable, str(STUDIO / "scripts/studio.py"), "--version"], capture_output=True, text=True, encoding="utf-8")

    def test_it_prints_a_fingerprint(self):
        out = self.run_version()
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertRegex(out.stdout.strip(), r"^studio-data [0-9a-f]{12}$")

    def test_it_follows_the_files(self):
        self.assertEqual(self.run_version().stdout.strip(), f"studio-data {common.fingerprint()}")


class AckLine(Project):
    """141: 확인한 경고 줄이 같은 말을 두 번 하지 않는다."""

    def test_a_part_inside_the_where_is_not_repeated(self):
        def make(d):
            d["pacing"]["max_rest_load"] = 1
            d["levels"][0]["acknowledged"] = {"long_stretch": {"crypt_skirmish~crypt_forge": "첫 구역은 길다"}}
        self.edit("data/levels.json", make)
        text = next(x for x in self.check()[1].splitlines() if x.startswith("확인한 경고 [long_stretch]"))
        self.assertIn("(crypt_skirmish~crypt_forge, 부담 9.15)", text)


    def test_a_part_that_is_the_where_is_not_repeated(self):
        def make(d):
            d["pacing"]["max_rest_load"] = 1
            d["levels"][1]["acknowledged"] = {"long_stretch": {"citadel_throne": "마지막 방은 쉬지 않는다"}}
        self.edit("data/levels.json", make)
        text = next(x for x in self.check()[1].splitlines() if x.startswith("확인한 경고 [long_stretch]"))
        self.assertIn("citadel.citadel_throne(부담 1.16):", text)


class Docs(unittest.TestCase):
    def test_the_docs_cover_the_field_answers(self):
        fmt = level_format()
        skill = level_guide()
        eco = (ROOT / "skills/economy-flow/references/economy-format.md").read_text(encoding="utf-8")
        data = (ROOT / "skills/studio-data/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("`open_for`", fmt)
        self.assertIn("파일 사본", skill)
        self.assertNotIn("대체 경로를 레벨로 나눠", skill)
        self.assertNotIn("웨이브 시각표", fmt)
        self.assertIn("회복이 없는 게임", skill)
        self.assertIn("길이당 부담", skill)
        self.assertNotIn("역할과 세기로 적는다", skill)
        self.assertIn("레벨에서 `{\"time_gap\"", fmt)   # 경고를 확인하는 자리는 형식의 검사 표에 있다
        self.assertIn("시각(수)", eco)
        flow = (ROOT / "skills/economy-flow/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("그 시각을 적는다", flow)
        self.assertIn("`after`의 단계나 시각", flow)
        ack_row = next(x for x in fmt.splitlines() if x.startswith("| `status`, `provenance`, `acknowledged` |"))
        self.assertIn("첫 조우~끝 조우", ack_row)
        self.assertIn("그 묶음 뒤에 끊는다", fmt)
        self.assertIn("--version", data)
        arch = (ROOT / "docs/architecture.md").read_text(encoding="utf-8")
        for number in ("132", "133", "136"):
            self.assertIn(number, arch)


if __name__ == "__main__":
    unittest.main()
