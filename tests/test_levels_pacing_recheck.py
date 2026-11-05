"""레벨 페이싱 재검증(이슈 143~160) 테스트: 놓친 경고와 다음 할 일을 말하지 않는 메시지. 표준 라이브러리 unittest만 사용한다."""
import re
import unittest

from _studio import ROOT, STUDIO, common, levels as lv
from test_economy import base, validate as economy_validate
from test_levels import BUDGET, COMBAT, ENEMIES, THREAT, both, enc, level, row, run
from test_levels_field import ECONOMY, notes, printed
from test_levels_pacing import PLAN, paced, quiet, spans, strong, warn_codes
from test_levels_pacing_field import spend
from test_levels_recheck import Project, warning

HARD_TWO = enc("e2", {"c": 12}, role="boss")


def stage_end(**over):
    d = base(**over)
    d["economy"]["purchase_timing"] = "stage_end"
    return d


class StrongAcrossLevels(unittest.TestCase):
    """143: 체력이 이어지는 게임은 carry_levels를 쓰고, 안 썼으면 놓치지 않게 알린다."""

    def test_a_run_over_the_limit_across_levels_is_pointed_out(self):
        text = notes(paced(level("s1", strong()), level("s2", HARD_TWO), pacing={"max_strong_run": 1}))
        self.assertIn("레벨을 넘으면", text)
        self.assertIn("hard~e2", text)
        self.assertIn("carry_levels", text)

    def test_it_stays_a_note(self):
        self.assertNotIn("strong_run", warn_codes(paced(level("s1", strong()), level("s2", HARD_TWO), pacing={"max_strong_run": 1})))

    def test_within_the_limit_nothing_is_said(self):
        self.assertNotIn("레벨을 넘으면", notes(paced(level("s1", strong()), level("s2", HARD_TWO), pacing={"max_strong_run": 5})))

    def test_without_a_limit_nothing_is_said(self):
        self.assertNotIn("레벨을 넘으면", notes(paced(level("s1", strong()), level("s2", HARD_TWO))))

    def test_with_carry_it_is_a_warning_instead(self):
        r = paced(level("s1", strong()), level("s2", HARD_TWO), pacing={"max_strong_run": 1, "carry_levels": True})
        self.assertIn("strong_run", warn_codes(r))
        self.assertNotIn("레벨을 넘으면", notes(r))

    def test_a_run_inside_one_level_is_not_repeated_in_the_note(self):
        self.assertNotIn("레벨을 넘으면", notes(paced(*both(level("s1", strong(), strong("h2"))), pacing={"max_strong_run": 1})))

    def test_a_level_that_fell_out_is_not_guessed_across(self):
        r = paced(level("s1", strong()), level("s1b", enc("e5"), combat_stage="s1", status="oops"), level("s2", HARD_TWO), pacing={"max_strong_run": 1})
        self.assertNotIn("레벨을 넘으면", notes(r))


class TopKeys(unittest.TestCase):
    """144: 최상위 키 오타를 잡는다."""

    def test_a_typo_in_the_levels_file(self):
        data = {"levels": both(), "threat_budget": BUDGET, "pacings": {"max_rest_load": 1}}
        r = lv.validate(data, enemies=ENEMIES, threat=THREAT, combat=COMBAT)
        self.assertIn("pacing", next(e["message"] for e in r["errors"] if e["code"] == "schema"))

    def test_memos_are_free_in_the_levels_file(self):
        data = {"levels": both(), "threat_budget": BUDGET, "_memo": 1, "note": "메모"}
        self.assertEqual(lv.validate(data, enemies=ENEMIES, threat=THREAT, combat=COMBAT)["errors"], [])

    def test_a_typo_in_the_economy_file(self):
        d = base()
        d["purchase"] = d.pop("purchases")
        self.assertIn("purchases", next(e["message"] for e in economy_validate(d)["errors"] if e["code"] == "schema"))

    def test_memos_are_free_in_the_economy_file(self):
        self.assertEqual(economy_validate(base(_memo=1, note="메모"))["errors"], [])


class PurchaseCause(unittest.TestCase):
    """146: 구매가 늦은 까닭을 말한다."""

    def rows(self, d):
        return [p["held_by"] for p in economy_validate(d)["purchases"]]

    def test_money_decides(self):
        self.assertEqual(self.rows(base(purchases=[spend()])), ["money"])

    def test_after_decides(self):
        self.assertEqual(self.rows(base(purchases=[spend(after=50)])), ["after"])

    def test_a_stage_after_decides(self):
        self.assertEqual(self.rows(base(purchases=[spend(after="s2")])), ["after"])

    def test_the_purchase_before_decides(self):
        self.assertEqual(self.rows(base(purchases=[spend("a", after=50), spend("b", 1)])), ["after", "order"])

    def test_the_stage_end_decides(self):
        self.assertEqual(self.rows(stage_end(purchases=[spend()])), ["stage_end"])

    def test_a_second_purchase_in_the_same_stage_end_is_held_by_the_stage_end(self):
        self.assertEqual(self.rows(stage_end(purchases=[spend("a"), spend("b")])), ["stage_end", "stage_end"])

    def test_a_purchase_pushed_past_its_own_stage_end_is_held_by_the_order(self):
        rows = self.rows(stage_end(purchases=[spend("a", 150), spend("b", 1, after=5)]))
        self.assertEqual(rows, ["stage_end", "stage_end"])
        self.assertEqual(self.rows(stage_end(purchases=[spend("a", after=150), spend("b", 1)])), ["stage_end", "order"])

    def test_a_stage_end_that_money_reaches_exactly_stays_money(self):
        self.assertEqual(self.rows(stage_end(purchases=[spend(amount=100)])), ["money"])

    def message(self, held_by):
        plan = {"ripen": {"id": "ripen", "at": 45.0, "stage": "s1", "held_by": held_by}}
        r = run(both(level("s1", quiet(duration=30, purchases=["ripen"]), enc(duration=30))), economy=ECONOMY, purchases=plan)
        return warning(r, "purchase_off_span")["message"]

    def test_each_cause_has_its_own_advice(self):
        self.assertIn("돈이 늦습니다", self.message("money"))
        self.assertIn("after", self.message("after"))
        self.assertNotIn("돈이 늦습니다", self.message("after"))
        self.assertIn("앞 구매", self.message("order"))
        self.assertIn("단계 끝", self.message("stage_end"))
        self.assertNotIn("돈이 늦습니다", self.message("stage_end"))


class QuietDuration(unittest.TestCase):
    """147: 싸움과 겹치는 적 없는 조우는 구간의 끝을 늘리지 않는다."""

    def test_a_long_facility_does_not_stretch_the_span(self):
        r = run(both(level("s1", quiet("altar", at=0, duration=600), enc(at=0, duration=30), enc("e3", at=30, duration=30))), economy=ECONOMY)
        self.assertEqual(spans(r)[0]["length"], 60)

    def test_a_quiet_stretch_of_its_own_counts(self):
        r = run(both(level("s1", enc(at=0, duration=30), quiet(at=30, duration=30))), economy=ECONOMY)
        self.assertEqual(spans(r)[0]["length"], 60)

    def test_an_unknown_time_still_gives_no_length(self):
        r = run(both(level("s1", enc(duration=30), quiet(), enc("e3"))))
        self.assertIsNone(spans(r)[0]["length"])

    def test_a_facility_does_not_start_a_span(self):
        r = run(both(level("s1", quiet("altar", at=0, duration=60), enc("e3", at=30, duration=30))), economy=ECONOMY)
        self.assertEqual((spans(r)[0]["from"], spans(r)[0]["length"]), ("e3", 30))

    def test_a_moment_does_not_start_a_span(self):
        r = run(both(level("s1", quiet("altar", at=10, open_for=30, purchases=["ripen"]), enc("e3", at=30, duration=30))), economy=ECONOMY, purchases=PLAN)
        self.assertEqual((spans(r)[0]["from"], spans(r)[0]["length"]), ("e3", 30))

    def test_a_quiet_stretch_of_its_own_starts_a_span(self):
        r = run(both(level("s1", quiet("calm", at=0, duration=30), enc("e3", at=30, duration=30))), economy=ECONOMY)
        self.assertEqual((spans(r)[0]["from"], spans(r)[0]["length"]), ("calm", 60))

    def test_an_untimed_quiet_room_starts_a_span(self):
        self.assertEqual(spans(run(both(level("s1", quiet("calm"), enc("e3")))))[0]["from"], "calm")

    def test_the_outside_warning_points_at_open_for(self):
        r = run(both(level("s1", quiet("altar", at=0, duration=900), enc(at=0, duration=60))), economy=ECONOMY)
        self.assertIn("open_for", warning(r, "time_outside_stage")["message"])

    def test_a_fight_outside_the_stage_gets_no_such_hint(self):
        r = run(both(level("s1", enc(at=0, duration=90))), economy=ECONOMY)
        self.assertNotIn("open_for", warning(r, "time_outside_stage")["message"])


class WarningsSayHowToAcknowledge(unittest.TestCase):
    """149, 159: 구간 경고가 확인하는 길을 말한다."""

    def test_the_message_names_the_level_and_the_key(self):
        w = warning(paced(level("s1", enc(repeat=3)), level("s2", enc("e2", {"c": 6})), pacing={"max_rest_load": 2, "carry_levels": True}), "long_stretch")
        self.assertIn("레벨 s1의 acknowledged", w["message"])
        self.assertIn('"e1~e2"', w["message"])

    def test_a_strong_run_does_too(self):
        self.assertIn('"hard~h2"', warning(paced(*both(level("s1", strong(), strong("h2"))), pacing={"max_strong_run": 1}), "strong_run")["message"])

    def test_one_encounter_is_told_so(self):
        text = warning(paced(*both(level("s1", strong(repeat=5))), pacing={"max_strong_run": 2}), "strong_run")["message"]
        self.assertIn("한 조우의 횟수", text)
        self.assertIn("나눠 사이에 약한 조우", text)


class UnusedAckHints(Project):
    """150: 쓰이지 않은 확인의 다음 할 일이 맞다."""

    def over_limit(self, d):
        d["pacing"]["max_rest_load"] = 1

    def ack_notes(self, kind="levels"):
        return "\n".join(self.report(kind)["ack_notes"])

    def test_the_right_name_on_the_wrong_level_says_where(self):
        def make(d):
            self.over_limit(d)
            d["levels"][1]["acknowledged"] = {"long_stretch": {"crypt_skirmish~crypt_forge": "이유"}}
        self.edit("data/levels.json", make)
        text = self.ack_notes()
        self.assertIn("crypt에 적습니다", text)
        self.assertNotIn("오타", text)

    def test_a_level_warning_acknowledged_in_the_economy_says_where(self):
        self.edit("data/economy.json", lambda d: d["purchases"][1].__setitem__("acknowledged", {"purchase_off_span": "이유"}))
        self.assertIn("levels.json", self.ack_notes("economy"))

    def test_an_unrelated_span_is_not_suggested(self):
        def make(d):
            self.over_limit(d)
            d["levels"][0]["acknowledged"] = {"long_stretch": {"nowhere~else": "이유"}}
        self.edit("data/levels.json", make)
        self.assertNotIn("오타", self.ack_notes())

    def test_a_span_sharing_an_end_is_suggested(self):
        def make(d):
            self.over_limit(d)
            d["levels"][0]["acknowledged"] = {"long_stretch": {"crypt_skirmish~crypt_forge (crypt~citadel)": "이유"}}
        self.edit("data/levels.json", make)
        self.assertIn("'crypt_skirmish~crypt_forge'의 오타", self.ack_notes())


class AckHomes(Project):
    """150: 어느 파일의 경고인지 양쪽으로 말한다. 코드 목록은 손으로 적으므로 검사기와 맞는지 본다."""

    def test_an_economy_warning_acknowledged_on_a_level_says_where(self):
        self.edit("data/levels.json", lambda d: d["levels"][0].__setitem__("acknowledged", {"gear_before_purchase": {"x": "이유"}}))
        self.assertIn("economy.json", "\n".join(self.report("levels")["ack_notes"]))

    def codes(self, name):
        source = (STUDIO / f"scripts/studio_data/{name}.py").read_text(encoding="utf-8")
        return set(re.findall(r'_err\(warnings, "(\w+)"', source)) - {"cut_referenced"}

    def test_the_level_list_matches_the_checker(self):
        self.assertEqual(set(common.LEVEL_ACK_CODES), self.codes("levels") | {v[2] for v in lv.SPAN_KINDS.values()})

    def test_the_economy_list_matches_the_checker(self):
        self.assertEqual(set(common.ECONOMY_ACK_CODES), self.codes("economy"))


class SpanSuggestions(unittest.TestCase):
    """150: 끝을 나누지 않는 구간은 이름이 닮아도 오타로 보지 않는다."""

    SEEN = [{"code": "long_stretch", "where": "a", "part": "z3_surge~z4_hatch"}]

    def test_a_single_encounter_is_not_a_part_of_a_longer_name(self):
        seen = [{"code": "long_stretch", "where": "a", "part": "e1"}]
        self.assertNotIn("오타", common._ack_advice("levels", "long_stretch", "e10~e11", seen))

    def test_a_lookalike_span_is_not_suggested(self):
        self.assertNotIn("오타", common._ack_advice("levels", "long_stretch", "z1_surge~z2_hatch", self.SEEN))

    def test_a_span_sharing_an_end_is_suggested(self):
        self.assertIn("z3_surge~z4_hatch", common._ack_advice("levels", "long_stretch", "z3_surge~z4_hatchh", self.SEEN))


class GroupRate(unittest.TestCase):
    """151: 시간을 나누는 묶음의 길이당 부담은 묶음의 값이다."""

    def result(self):
        return run(both(level("s1", enc(at=0, duration=30, repeat=6), enc("e3", at=0, duration=30, repeat=3), enc("e4", at=30, duration=30, repeat=3))), economy=ECONOMY)

    def test_parallel_rows_share_the_group_value(self):
        r = self.result()
        self.assertEqual((row(r)["rate"], row(r, "e3")["rate"], row(r, "e4")["rate"]), (0.3, 0.3, 0.1))

    def test_a_group_of_different_lengths_uses_its_whole_time(self):
        r = run(both(level("s1", enc(at=0, duration=60, repeat=6), enc("e3", at=10, duration=10, repeat=6))), economy=ECONOMY)
        self.assertEqual(row(r)["rate"], 0.2)

    def test_the_first_row_of_a_group_does_not_set_its_time(self):
        r = run(both(level("s1", enc(at=0, duration=10, repeat=6), enc("e3", at=5, duration=55, repeat=6))), economy=ECONOMY)
        self.assertEqual(row(r)["rate"], 0.2)

    def test_an_unknown_start_uses_its_own_duration(self):
        r = run(both(level("s1", enc(), enc("e3", duration=10, repeat=3))))
        self.assertEqual(row(r, "e3")["rate"], 0.3)

    def test_spans_have_the_column(self):
        self.assertEqual(spans(self.result())[0]["rate"], 0.2)
        r = run(both(level("s1", enc(at=0, duration=60, reward="상자"))), economy=ECONOMY)
        self.assertIn("| 구간 | 조우 | 끝낸 곳 | 부담 | 길이 | 길이당 부담 | 상한 |", lv.table({}, r))

    def test_a_span_without_a_length_has_no_rate(self):
        self.assertIsNone(spans(run())[0]["rate"])


class AcknowledgedMarks(Project):
    """157: 확인한 구간은 ⚠가 아니다."""

    def make(self, d):
        d["pacing"]["max_rest_load"] = 1
        d["levels"][1]["acknowledged"] = {"long_stretch": {"citadel_throne": "마지막 방은 쉬지 않는다"}}

    def test_the_report_says_acknowledged(self):
        self.edit("data/levels.json", self.make)
        lines = [x for x in self.check()[1].splitlines() if x.startswith("구간 쉬는 곳 사이 citadel_throne")]
        self.assertIn("(확인함)", lines[0])
        self.assertNotIn("⚠", lines[0])

    def test_the_table_says_acknowledged(self):
        self.edit("data/levels.json", self.make)
        out = self.check("--table", "levels")[1]
        line = next(x for x in out.splitlines() if x.startswith("| 쉬는 곳 사이 | citadel_throne |"))
        self.assertIn("(확인함)", line)

    def test_an_open_warning_keeps_its_mark(self):
        self.edit("data/levels.json", self.make)
        self.assertIn("⚠", next(x for x in self.check()[1].splitlines() if x.startswith("구간 쉬는 곳 사이 crypt_skirmish")))

    def test_the_viewer_reads_it(self):
        self.assertIn("r.acknowledged", (STUDIO / "assets/viewer.html").read_text(encoding="utf-8"))


class EmptySpans(unittest.TestCase):
    """158: 구간이 없으면 표도 없다."""

    def test_no_rows_no_table(self):
        r = paced(*both(level("s1", enc(duration=60))))
        self.assertIn("세기", lv.table({}, r))
        self.assertNotIn("| 구간 | 조우 |", lv.table({}, r))


class ValueChecks(unittest.TestCase):
    """159: 값의 빈틈."""

    def test_zero_open_for_is_an_error(self):
        r = run(both(level("s1", enc(), quiet(at=0, open_for=0, purchases=["ripen"]))), economy=ECONOMY, purchases=PLAN)
        self.assertIn("schema", [e["code"] for e in r["errors"]])

    def test_an_opening_past_the_run_is_said(self):
        r = run(both(level("s1", quiet("altar", at=30, open_for=999, purchases=["ripen"]), enc(at=0, duration=60))), economy=ECONOMY, purchases=PLAN)
        self.assertIn("판 끝(90초)을 넘어 열려 있는 시설: altar", notes(r))

    def test_an_unknown_run_end_says_nothing(self):
        eco = {"economy": {}, "stages": [{"id": "s1", "duration": 60}, {"id": "s2"}]}
        r = run(both(level("s1", quiet("altar", at=0, open_for=80, purchases=["ripen"]), enc(at=0, duration=60))), economy=eco, purchases=PLAN)
        self.assertNotIn("판 끝", notes(r))

    def test_an_opening_to_the_very_end_is_quiet(self):
        r = run(both(level("s1", quiet("altar", at=30, open_for=60, purchases=["ripen"]), enc(at=0, duration=60))), economy=ECONOMY, purchases=PLAN)
        self.assertNotIn("판 끝", notes(r))

    def test_a_time_written_as_text_gets_a_hint(self):
        r = economy_validate(base(purchases=[spend(after="4")]))
        self.assertIn("따옴표", r["errors"][0]["message"])

    def test_a_boolean_gets_no_time_hint_and_reads_as_json(self):
        text = economy_validate(base(purchases=[spend(after=True)]))["errors"][0]["message"]
        self.assertNotIn("따옴표", text)
        self.assertIn("true", text)

    def test_a_real_stage_typo_does_not(self):
        self.assertNotIn("따옴표", economy_validate(base(purchases=[spend(after="s9")]))["errors"][0]["message"])

    def test_no_stages_means_no_chained_error(self):
        d = base(purchases=[spend(after=5)])
        d["stages"] = []
        self.assertNotIn("판 끝 0", " ".join(e["message"] for e in economy_validate(d)["errors"]))


class Docs(unittest.TestCase):
    def test_the_docs_cover_the_recheck(self):
        skill = (ROOT / "skills/level-design/SKILL.md").read_text(encoding="utf-8")
        fmt = (ROOT / "skills/level-design/references/levels-format.md").read_text(encoding="utf-8")
        arch = (ROOT / "docs/architecture.md").read_text(encoding="utf-8")
        self.assertNotIn("쉬는 곳 구간에만", skill)
        self.assertIn("강한 조우 연속도", skill)
        self.assertIn("괄호의 레벨 범위는 빼고", skill)
        self.assertIn("구매 시설은 `reward`가 아니다", skill)
        self.assertIn("플레이어 행동에 달린 보상", skill)
        self.assertIn("임무를 넘는 보상 구간", skill)
        self.assertIn("가장 빡빡한 단계", skill)
        self.assertIn("층 중간에 상점", skill)
        self.assertIn("장비가 일부 라운드에서만", skill)
        self.assertIn("묶음의 값", fmt)
        self.assertNotIn("구간의 길이에 들어가지는 않지만", fmt)
        self.assertNotIn("라운드가 레벨인 게임도", skill)
        self.assertIn("최상위", next(x for x in fmt.splitlines() if x.startswith("| `schema` |")))
        self.assertIn("`pacing`", next(x for x in fmt.splitlines() if x.startswith("| `schema` |")))
        eco = (ROOT / "skills/economy-flow/references/economy-format.md").read_text(encoding="utf-8")
        self.assertIn("모르는 키", eco)
        for number in ("145", "148", "154"):
            self.assertIn(number, arch)


if __name__ == "__main__":
    unittest.main()
