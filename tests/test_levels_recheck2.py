"""레벨 구성 재검증 2(이슈 107~117) 테스트: 라운드제 게임과 남은 안내. 표준 라이브러리 unittest만 사용한다."""
import io
import json
import re
import tokenize
import unittest
from contextlib import redirect_stdout
from unittest import mock

from _studio import ROOT, STUDIO, claude, common, economy as ec, levels as lv, meta_sim as sm, level_guide, level_format
from test_economy import CRAFTING, ITEMS, base, buy, validate
from test_levels import both, enc, level, run
from test_levels_field import ECONOMY, TIMES, notes, printed, stage
from test_levels_recheck import HITS, Project, warning
from test_meta_combat import CONFIG, Workspace as MetaWorkspace

CODE_DIR = STUDIO / "scripts/studio_data"


class CommentedFiles(Project):
    """107: 주석을 지우고 다시 읽어 판별한다. 읽히지 않으면 읽기 오류다."""

    def test_broken_shapes_are_read_failures(self):
        for text in ('{ "homepage": "http://example.com', "{ 'rooms': [ { 'url': 'http://x.y' } ] }", '{ "rooms": [ { "url": http://x.y } ] }',
                     '// 메모\n{ "rooms": [', "// 아직 내용 없음\n", "/* 비었다 */", "{ // 메모\n}"):
            self.write("data/levels.json", text)
            self.assertEqual(self.check()[0], 2, text)

    def test_commented_file_of_this_format_is_a_read_failure_that_says_why(self):
        for text in ('{\n "levels": [] // m\n}', '{ /* 예산 */ "threat_budget": {} }'):
            self.write("data/levels.json", text)
            code, out = self.check()
            self.assertEqual(code, 2, text)
            self.assertIn("주석", out)

    def test_game_files_with_comments_are_still_skipped(self):
        for text in ('{ // 맵\n "world": 1 }', '{ /* 맵 */ "world": 1, "url": "http://x.y" }', "[ // 맵\n 1 ]"):
            self.write("data/levels.json", text)
            code, out = self.check()
            self.assertEqual(code, 0, text)
            self.assertIn("건너뛰었습니다", out)

    def test_other_kinds_say_why_too(self):
        self.write("data/economy.json", '{ // 재화\n "economy": {} }')
        self.assertIn("주석", self.check()[1])

    def test_a_plain_syntax_error_does_not_mention_comments(self):
        self.write("data/levels.json", "{oops")
        self.assertNotIn("주석을", self.check()[1])


class StageEndPurchases(unittest.TestCase):
    """108: 단계 사이에만 사는 게임의 구매 시점."""

    def result(self, *buys, timing="stage_end", **over):
        d = base(purchases=list(buys), **over)
        if timing:
            d["economy"]["purchase_timing"] = timing
        return validate(d)

    def row(self, r, pid="a"):
        return next(p for p in r["purchases"] if p["id"] == pid)

    def test_purchase_waits_for_the_end_of_the_stage(self):
        p = self.row(self.result(buy("a", item="cap")))
        self.assertEqual((p["at"], p["stage"]), (100, "s1"))

    def test_default_stays_inside_the_stage(self):
        p = self.row(self.result(buy("a", item="cap"), timing=None))
        self.assertEqual((p["at"], p["stage"]), (10, "s1"))

    def test_money_reached_exactly_at_the_end_buys_at_that_end(self):
        p = self.row(self.result(buy("a", item="sword")))
        self.assertEqual((p["at"], p["stage"]), (100, "s1"))

    def test_later_purchase_moves_to_the_next_end(self):
        p = self.row(self.result(buy("a", item="sword"), buy("b", item="cap")), "b")
        self.assertEqual((p["at"], p["stage"]), (200, "s2"))

    def test_after_opens_between_the_stages(self):
        p = self.row(self.result({**buy("a", item="cap"), "after": "s2"}))
        self.assertEqual((p["at"], p["stage"]), (100, "s1"))

    def test_target_on_the_stage_end_is_inside(self):
        r = self.result({**buy("a", item="cap"), "target": [100, 100]})
        self.assertEqual([w["code"] for w in r["warnings"] if w["code"] == "target_out_of_range"], [])

    def test_wrong_value_is_an_error(self):
        r = self.result(buy("a", item="cap"), timing="later")
        self.assertIn("purchase_timing", " ".join(e["message"] for e in r["errors"]))

    def test_nothing_to_wait_for_at_the_start(self):
        self.assertEqual(ec._stage_end([{"id": "s1", "duration": 10}], 0.0), (0.0, "s1"))

    def test_no_stages_do_not_stop_the_check(self):
        self.assertEqual(ec._stage_end([], 0.0), (0.0, ""))
        self.assertEqual(ec._stage_end([], 5.0), (0.0, ""))
        d = base(stages=[], purchases=[buy("a", item="gift")])
        d["economy"]["purchase_timing"] = "stage_end"
        ec.validate(d, enemies={}, items={**ITEMS, "gift": {"id": "gift", "price": 0}}, drop_tables={}, upgrades={}, crafting={})

    def test_time_past_the_last_end_stays_on_the_last_stage(self):
        self.assertEqual(ec._stage_end([{"id": "s1", "duration": 10}], 12.0), (10.0, "s1"))

    def test_output_says_it_is_the_end(self):
        r = self.result(buy("a", item="cap"))
        out = io.StringIO()
        with redirect_stdout(out):
            ec.print_extra(r)
        self.assertIn("100초 (s1 끝)", out.getvalue())

    def test_table_says_it_is_the_end(self):
        self.assertIn("| s1 끝 |", ec.table({}, self.result(buy("a", item="cap"))))

    def test_report_says_which_timing(self):
        self.assertEqual(self.result(buy("a", item="cap"))["purchase_timing"], "stage_end")
        self.assertEqual(self.result(buy("a", item="cap"), timing=None)["purchase_timing"], "any")


class GearAndPurchases(unittest.TestCase):
    """114: 기준 장비가 구매 계획보다 앞서면 알린다."""

    def result(self, kit1, kit2, timing=None, purchase="sword", **extra):
        d = base(purchases=[{**buy("a", item=purchase), **extra}])
        if timing:
            d["economy"]["purchase_timing"] = timing
        combat = {"stages": [{"id": "s1", "player": {"items": kit1}}, {"id": "s2", "player": {"items": kit2}}]}
        return ec.validate(d, enemies={}, items=ITEMS, drop_tables={}, upgrades={}, crafting={}, combat=combat)

    def gear(self, r):
        return [w for w in r["warnings"] if w["code"] == "gear_before_purchase"]

    def test_kit_ahead_of_the_purchase_is_warned(self):
        w = self.gear(self.result(["sword"], []))
        self.assertEqual(len(w), 1)
        self.assertEqual((w[0]["where"], w[0]["owner"], w[0]["part"]), ("a", "a", "s1"))
        self.assertIn("sword", w[0]["message"])

    def test_kit_after_the_purchase_is_fine(self):
        self.assertEqual(self.gear(self.result([], ["sword"])), [])

    def test_enhanced_item_in_the_kit_counts(self):
        self.assertEqual(len(self.gear(self.result([{"item": "sword", "enhance": "plus", "level": 1}], []))), 1)

    def test_item_outside_the_plan_is_left_alone(self):
        self.assertEqual(self.gear(self.result(["cap"], [])), [])

    def test_same_stage_is_fine_when_bought_during_it(self):
        self.assertEqual(self.gear(self.result(["cap"], [], purchase="cap")), [])

    def test_same_stage_is_too_early_when_bought_at_its_end(self):
        self.assertEqual(len(self.gear(self.result(["cap"], [], timing="stage_end", purchase="cap"))), 1)

    def test_next_stage_is_fine_when_bought_at_the_end(self):
        self.assertEqual(self.gear(self.result([], ["cap"], timing="stage_end", purchase="cap")), [])

    def test_item_free_at_the_start_is_in_every_kit(self):
        items = {**ITEMS, "gift": {"id": "gift", "price": 0}}
        d = base(purchases=[buy("a", item="gift")])
        d["economy"]["purchase_timing"] = "stage_end"
        combat = {"stages": [{"id": "s1", "player": {"items": ["gift"]}}, {"id": "s2", "player": {"items": []}}]}
        self.assertEqual(self.gear(ec.validate(d, enemies={}, items=items, drop_tables={}, upgrades={}, crafting={}, combat=combat)), [])

    def test_cut_stage_is_left_alone(self):
        d = base(purchases=[buy("a", item="sword")])
        combat = {"stages": [{"id": "s1", "status": "cut", "player": {"items": ["sword"]}}, {"id": "s2", "player": {"items": []}}]}
        self.assertEqual(self.gear(ec.validate(d, enemies={}, items=ITEMS, drop_tables={}, upgrades={}, crafting={}, combat=combat)), [])

    def test_the_first_purchase_of_an_item_counts(self):
        stages = [{"id": k, "duration": 100, "income": {"gold": 100}} for k in ("s1", "s2", "s3")]
        d = base(stages=stages, purchases=[buy("a", item="cap"), buy("b", item="sword"), buy("c", item="sword"), buy("d", item="cap")])
        combat = {"stages": [{"id": "s1", "player": {"items": []}}, {"id": "s2", "player": {"items": ["cap"]}}, {"id": "s3", "player": {"items": []}}]}
        self.assertEqual(self.gear(ec.validate(d, enemies={}, items=ITEMS, drop_tables={}, upgrades={}, crafting={}, combat=combat)), [])

    def enhanced(self, kit_level, *purchases, kit_stage=0):
        d = base(purchases=list(purchases))
        kit = [{"item": "sword", "enhance": "plus", "level": kit_level}]
        combat = {"stages": [{"id": "s1", "player": {"items": kit if kit_stage == 0 else []}}, {"id": "s2", "player": {"items": kit if kit_stage == 1 else []}}]}
        return self.gear(ec.validate(d, enemies={}, items=ITEMS, drop_tables={}, upgrades={}, crafting=CRAFTING, combat=combat))

    PLUS_1 = {"id": "p1", "price": {"enhance": "plus", "level": 1}}
    PLUS_2 = {"id": "p2", "price": {"enhance": "plus", "level": 2, "from": 1}}

    def test_enhancement_ahead_of_its_purchase_is_warned(self):
        w = self.enhanced(1, self.PLUS_1)
        self.assertEqual((w[0]["where"], w[0]["part"]), ("p1", "s1"))
        self.assertIn("sword +1", w[0]["message"])

    def test_enhancement_after_its_purchase_is_fine(self):
        self.assertEqual(self.enhanced(1, self.PLUS_1, kit_stage=1), [])

    def test_the_purchase_that_reaches_the_level_counts(self):
        self.assertEqual([w["where"] for w in self.enhanced(2, self.PLUS_1, self.PLUS_2, kit_stage=1)], [])
        self.assertEqual([w["where"] for w in self.enhanced(1, self.PLUS_1, self.PLUS_2, kit_stage=0)], ["p1"])

    def test_level_the_plan_never_reaches_is_left_alone(self):
        self.assertEqual(self.enhanced(2, self.PLUS_1), [])

    def test_no_combat_data_says_nothing(self):
        self.assertEqual(self.gear(validate(base(purchases=[buy("a", item="sword")]))), [])

    def test_unaffordable_purchase_is_left_to_its_own_warning(self):
        d = base(purchases=[buy("a", item="sword")])
        d["stages"] = [{"id": "s1", "duration": 100, "income": {"gold": 1}}, {"id": "s2", "duration": 100, "income": {"gold": 1}}]
        combat = {"stages": [{"id": "s1", "player": {"items": ["sword"]}}, {"id": "s2", "player": {"items": []}}]}
        self.assertEqual(self.gear(ec.validate(d, enemies={}, items=ITEMS, drop_tables={}, upgrades={}, crafting={}, combat=combat)), [])

    def test_a_linked_economy_stage_is_followed(self):
        d = base(purchases=[buy("a", item="sword")])
        d["stages"][0]["combat_stage"], d["stages"][1]["combat_stage"] = "c1", "c2"
        combat = {"stages": [{"id": "c1", "player": {"items": ["sword"]}}, {"id": "c2", "player": {"items": []}}]}
        self.assertEqual(len(self.gear(ec.validate(d, enemies={}, items=ITEMS, drop_tables={}, upgrades={}, crafting={}, combat=combat))), 1)

    def test_it_can_be_acknowledged_for_one_stage(self):
        d = base(purchases=[{**buy("a", item="sword"), "acknowledged": {"gear_before_purchase": {"s1": "드랍으로 먼저 얻는다"}}}])
        combat = {"stages": [{"id": "s1", "player": {"items": ["sword"]}}, {"id": "s2", "player": {"items": []}}]}
        r = ec.validate(d, enemies={}, items=ITEMS, drop_tables={}, upgrades={}, crafting={}, combat=combat)
        common.apply_acknowledged("economy", d, r)
        self.assertEqual(self.gear(r), [])
        self.assertEqual([a["code"] for a in r["acknowledged"]], ["gear_before_purchase"])


class StageComparison(unittest.TestCase):
    """109: 단계끼리도 앞 단계보다 얼마나 센가를 낸다."""

    def test_stage_row_compares_with_the_previous_stage(self):
        r = run()
        self.assertIsNone(stage(r)["vs_previous"])
        self.assertEqual(stage(r, "s2")["vs_previous"], 1.5)

    def test_comparison_skips_a_stage_with_no_value(self):
        combat = {"stages": [{"id": "s1", "zone": 1}, {"id": "s2", "zone": 2}, {"id": "s3", "zone": 3}]}
        r = run([level("s1"), level("s3", enc("e3", {"c": 8}))], combat=combat)
        self.assertIsNone(stage(r, "s2")["vs_previous"])
        self.assertEqual(stage(r, "s3")["vs_previous"], 2)

    def test_table_shows_it(self):
        text = lv.table({}, run())
        self.assertIn("| 앞 단계 대비 |", text)
        self.assertIn("| ×1.5 |", text)


class MixedMeasures(unittest.TestCase):
    """111, 115: 표의 칸이 왜 다른지 말한다."""

    def test_stages_without_an_attack_rate_are_named(self):
        text = notes(run(kill_times={"s1": TIMES["s1"]}, kill_hits={"s2": HITS["s2"]}))
        self.assertIn("공격 속도가 없는 단계: s2", text)

    def test_no_such_note_when_every_stage_has_time(self):
        self.assertNotIn("공격 속도가 없는 단계", notes(run(kill_times=TIMES, kill_hits=HITS)))

    def test_no_such_note_when_no_stage_has_time(self):
        self.assertNotIn("공격 속도가 없는 단계", notes(run(kill_hits=HITS)))

    def test_stage_without_a_length_is_named(self):
        eco = {"stages": [{"id": "s1", "duration": 60, "kills": {"a": 5, "b": 1}}, {"id": "s2", "kills": {"c": 6}}]}
        self.assertIn("길이를 모르는 단계: s2", notes(run(kill_times=TIMES, economy=eco)))

    def test_stage_the_economy_does_not_list_is_named(self):
        eco = {"stages": [{"id": "s1", "duration": 60, "kills": {"a": 5, "b": 1}}]}
        self.assertIn("길이를 모르는 단계: s2", notes(run(kill_hits=HITS, economy=eco)))

    def test_stage_with_nothing_to_divide_is_not_named(self):
        eco = {"stages": [{"id": "s1", "duration": 60, "kills": {"a": 5, "b": 1}}, {"id": "s2", "kills": {"c": 6}}]}
        self.assertNotIn("처치 시간 ÷ 길이", notes(run(kill_times={"s1": TIMES["s1"]}, economy=eco)))

    def test_missing_lengths_are_not_blamed_on_the_unit(self):
        eco = {"economy": {"time_unit": "방"}, "stages": [{"id": "s1", "kills": {"a": 5, "b": 1}}, {"id": "s2", "kills": {"c": 6}}]}
        text = notes(run(kill_times=TIMES, economy=eco))
        self.assertIn("단계 길이(duration)가 없어", text)
        self.assertNotIn("time_unit", text)

    def test_unit_is_named_even_when_one_length_is_missing(self):
        eco = {"economy": {"time_unit": "방"}, "stages": [{"id": "s1", "duration": 60, "kills": {"a": 5, "b": 1}}, {"id": "s2", "kills": {"c": 6}}]}
        text = notes(run(kill_times=TIMES, economy=eco))
        self.assertIn("길이를 모르는 단계: s2", text)
        self.assertIn("time_unit이 초가 아니라", text)

    def test_no_economy_is_said_once(self):
        text = notes(run(kill_times=TIMES))
        self.assertIn("처치 시간 ÷ 길이: 재화 흐름을 함께 읽지 않아", text)
        self.assertNotIn("길이를 모르는 단계", text)

    def test_nothing_is_said_when_every_stage_has_a_length(self):
        text = notes(run(kill_times=TIMES, economy=ECONOMY))
        self.assertNotIn("길이를 모르는", text)
        self.assertNotIn("처치 시간 ÷ 길이", text)


class SingleMargin(MetaWorkspace):
    """112: 수 하나는 모든 등급의 값이라 등급별 기준이 아니다."""

    def margin_notes(self):
        return "\n".join(sm.run_config(self.config)[1]["margin_notes"])

    def test_single_number_is_pointed_out_with_its_value(self):
        self.edit(CONFIG, lambda d: d["survival"].__setitem__("even_margin", 0.5))
        self.assertIn("일반 적과 같은 기준(0.5)", self.margin_notes())

    def test_calibrated_config_is_left_alone(self):
        self.edit(CONFIG, lambda d: d.update(provenance={"kind": "measured", "source": "reports/calibrate.json"}))
        self.edit(CONFIG, lambda d: d["survival"].__setitem__("even_margin", 0.5))
        self.assertEqual(self.margin_notes(), "")

    def test_assumed_config_is_still_pointed_out(self):
        self.edit(CONFIG, lambda d: d.update(provenance={"kind": "assumed"}))
        self.edit(CONFIG, lambda d: d["survival"].__setitem__("even_margin", 0.5))
        self.assertIn("기준(0.5)", self.margin_notes())

    def test_a_rank_written_as_one_counts_as_chosen(self):
        self.edit(CONFIG, lambda d: d["survival"].__setitem__("even_margin", {"normal": 1, "elite": 1, "boss": 1}))
        self.assertEqual(self.margin_notes(), "")


class UsualEnemies(Project):
    """113: 평소에도 나오는 적의 처방은 어느 적에게나 나온다."""

    def test_enemy_from_a_later_zone_gets_it(self):
        text = warning(run(both(level("s1", enc(enemies={"a": 5, "b": 1, "c": 1})))), "enemy_not_in_stage")["message"]
        self.assertIn("평소에도 이 단계에 나오면", text)
        self.assertIn("조건부", text)

    def test_enemy_from_an_earlier_zone_gets_it_once(self):
        combat = {"stages": [{"id": "s1", "zone": 1}, {"id": "s2", "zone": 2, "enemies": ["c"]}]}
        text = warning(run(both(second=level("s2", enc("e2", {"c": 6, "a": 1}))), combat=combat), "enemy_not_in_stage")["message"]
        self.assertEqual(text.count("평소에도"), 1)

    def test_economy_gets_it_too(self):
        self.edit("data/economy.json", lambda d: d["stages"][0]["kills"].__setitem__("void_herald", 1))
        self.assertIn("평소에도 이 단계에 나오면", warning(self.report("economy"), "kill_not_in_stage")["message"])


class Particles(unittest.TestCase):
    """116: 끝소리를 알 수 없는 영문에는 두 조사를 함께 적는다."""

    def test_latin_ending_gets_both(self):
        self.assertEqual(common.josa("rot_queen", "은는"), "rot_queen은(는)")
        self.assertEqual(common.josa("buy_plating", "을를"), "buy_plating을(를)")
        self.assertEqual(common.josa("hatched_elite", "이가"), "hatched_elite이(가)")

    def test_known_endings_get_one(self):
        self.assertEqual(common.josa("보스", "은는"), "보스는")
        self.assertEqual(common.josa("단계", "이가"), "단계가")
        self.assertEqual(common.josa("층", "을를"), "층을")
        self.assertEqual(common.josa("zone_3", "을를"), "zone_3을")
        self.assertEqual(common.josa("zone_2", "을를"), "zone_2를")

    def test_closing_quotes_are_looked_past(self):
        self.assertEqual(common.josa("'aim_bolt_1'", "이가"), "'aim_bolt_1'이")
        self.assertEqual(common.josa("'iron'", "이가"), "'iron'이(가)")

    def test_no_message_writes_a_particle_by_hand_after_an_id(self):
        pattern = re.compile(r"\{[a-z_][^{}:]*\}(가|를|은|는) ")
        found = [f"{p.name}:{n}" for p in sorted(CODE_DIR.glob("*.py")) for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
                 if re.search(r'f"|f\'', line) and pattern.search(line)]
        self.assertEqual(found, [])


class OlderPython(unittest.TestCase):
    """f-문자열 안에서 같은 따옴표를 다시 쓰면 3.12 미만에서 문법 오류다. 3.12 이상에서만 토큰으로 확인할 수 있다."""

    @unittest.skipUnless(hasattr(tokenize, "FSTRING_START"), "3.12 미만은 이 파일을 불러오는 것으로 이미 확인된다")
    def test_no_f_string_reuses_its_own_quote(self):
        found = []
        for path in sorted(CODE_DIR.glob("*.py")):
            stack: list = []
            with path.open(encoding="utf-8") as fh:
                for token in tokenize.generate_tokens(fh.readline):
                    if token.type == tokenize.FSTRING_START:
                        quote = token.string.lstrip("rRfFbB")[0]
                        if stack and quote == stack[-1]:
                            found.append(f"{path.name}:{token.start[0]}")
                        stack.append(quote)
                    elif token.type == tokenize.FSTRING_END:
                        stack.pop()
                    elif token.type == tokenize.STRING and stack and token.string.lstrip("rRbBuU")[0] == stack[-1]:
                        found.append(f"{path.name}:{token.start[0]}")
        self.assertEqual(found, [])


class MessageDetails(Project):
    """117: 메시지 세부."""

    def test_broken_link_names_the_value_it_points_at(self):
        eco = {"stages": [{"id": "mid_game", "combat_stage": "zon_3", "kills": {"a": 9}}]}
        text = warning(run(economy=eco), "kills_not_linked")["message"]
        self.assertIn("combat_stage zon_3", text)
        self.assertNotIn("combat_stage를 적거나", text)

    def test_stage_with_no_link_keeps_the_old_advice(self):
        self.assertIn("combat_stage를 적거나", warning(run(economy={"stages": [{"id": "part_1", "kills": {"a": 9}}]}), "kills_not_linked")["message"])

    def test_stage_already_named_as_an_error_is_not_named_again(self):
        eco = {"stages": [{"id": "s1", "kills": {"a": 5, "b": 1}}, {"id": "s2", "combat_stage": "s_2x", "kills": {"c": 6}}]}
        self.assertNotIn("이어지지 않은 재화 흐름 단계", notes(run(economy=eco)))

    def test_acknowledged_line_does_not_repeat_its_place(self):
        self.edit("data/economy.json", lambda d: d["stages"].append({"id": "mid_game", "combat_stage": "zon_3", "duration": 1, "kills": {"void_herald": 1}}))
        self.edit("data/levels.json", lambda d: d["levels"][0].__setitem__("acknowledged", {"kills_not_linked": {"mid_game": "다음 구역"}}))
        out = self.check()[1]
        self.assertIn("mid_game: 다음 구역", out)
        self.assertNotIn("mid_game(mid_game)", out)

    def test_kill_check_names_the_economy_stage_that_went_astray(self):
        eco = {"stages": [{"id": "s1", "kills": {"a": 5, "b": 1}}, {"id": "mid_game", "combat_stage": "zon_3", "kills": {"c": 6}}]}
        self.assertIn("이어지지 않은 재화 흐름 단계: mid_game", notes(run(economy=eco)))

    def test_acknowledged_line_names_its_target(self):
        self.edit("data/economy.json", lambda d: d["stages"][0].update(acknowledged={"kill_not_in_stage": {"void_herald": "조건부"}},
                                                                     kills={**d["stages"][0]["kills"], "void_herald": 1}))
        self.assertIn("zone_1(void_herald): 조건부", self.check()[1])

    def test_stage_whose_encounters_all_failed_is_not_called_empty(self):
        r = run(both(level("s1", enc("x", {"a": 0}))))
        self.assertEqual((r["stages_without_levels"], r["stages_unread"]), ([], ["s1"]))
        self.assertIn("stages", r["unchecked_kinds"])
        self.assertIn("형식 오류로 조우를 세지 못한 전투 단계 s1", printed(r))

    def test_stage_of_a_failed_level_is_not_called_empty(self):
        r = run(both(second=level("s2", enc("e2", {"c": 6}), status="nope")))
        self.assertEqual((r["stages_without_levels"], r["stages_unread"]), ([], ["s2"]))

    def test_stage_with_no_encounters_stays_empty(self):
        r = run(both(level("s1", encounters=[])))
        self.assertEqual((r["stages_without_levels"], r["stages_unread"]), (["s1"], []))

    def test_json_with_a_byte_order_mark_is_read(self):
        path = self.root / "data/economy.json"
        path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
        self.assertNotEqual(self.check()[0], 2)


class HookDetails(Project):
    """117: 편집 훅의 건너뜀 안내."""

    def hook(self, rel):
        code, out, _ = claude.post_edit(json.dumps({"tool_input": {"file_path": str(self.root / rel)}}), self.root)
        return code, json.loads(out)["hookSpecificOutput"]["additionalContext"] if out else ""

    def test_the_note_is_not_counted_as_a_warning_and_uses_a_project_path(self):
        self.write("data/levels.json", '{"level": []}')
        self.edit("data/playtests.json", lambda d: d["playtests"][-1].pop("greybox"))   # 레벨 구성을 못 읽으면 그레이박스 기록은 미확인이다
        code, text = self.hook("data/levels.json")
        self.assertEqual(code, 0)
        self.assertIn("경고 0개", text)
        self.assertIn("data/levels.json: 레벨 구성 형식이 아니라", text)
        self.assertNotIn(str(self.root), text)

    def test_a_levels_file_at_the_project_root_is_seen(self):
        self.write("levels.json", '{"level": []}')
        self.assertIn("건너뛰었습니다", self.hook("levels.json")[1])

    def test_a_root_document_named_levels_stays_out(self):
        self.write("levels.md", "# 메모\n")
        with mock.patch.object(claude, "_run", side_effect=AssertionError("검사하면 안 됩니다")):
            self.assertEqual(self.hook("levels.md"), (0, ""))

    def test_another_root_file_stays_out(self):
        self.write("data/levels.json", "{oops")
        self.write("notes.json", "{}")
        self.assertEqual(self.hook("notes.json"), (0, ""))


class Docs(unittest.TestCase):
    def setUp(self):
        self.skill = level_guide()   # 할 일은 SKILL.md와 game-shapes.md에 있다
        self.fmt = level_format()
        self.economy = (ROOT / "skills/economy-flow/SKILL.md").read_text(encoding="utf-8")
        self.economy_fmt = (ROOT / "skills/economy-flow/references/economy-format.md").read_text(encoding="utf-8")
        self.combat = (ROOT / "skills/combat-balance/SKILL.md").read_text(encoding="utf-8")
        self.studio = (STUDIO / "SKILL.md").read_text(encoding="utf-8")
        self.page = (STUDIO / "assets/viewer.html").read_text(encoding="utf-8")

    def test_comment_rule_is_written_the_same_way(self):  # 107
        self.assertIn("두 키가 없고 주석이 있는 JSON", self.fmt)
        self.assertIn("두 키가 없고 주석이 있는 JSON", self.studio)

    def test_stage_end_purchases_are_documented(self):  # 108
        self.assertIn("`purchase_timing`", self.economy_fmt)
        self.assertIn("purchase_timing", self.economy)

    def test_stage_unit_of_a_round_game_is_decided_by_the_kit(self):  # 109
        self.assertIn("기준 장비가 라운드마다 바뀌면", self.skill)
        self.assertIn("기준 장비가 라운드마다 바뀌면", self.combat)

    def test_several_economy_stages_on_one_combat_stage_are_documented(self):  # 109
        self.assertIn("재화 흐름 단계 여럿", self.fmt)

    def test_round_size_has_one_rule(self):  # 110
        self.assertIn("그 라운드의 적 전체", self.skill)
        self.assertNotIn("웨이브가 이어지는 게임", self.skill)

    def test_length_of_a_round_is_explained(self):  # 110
        self.assertIn("처치 속도로 정해지면", self.skill)

    def test_stage_kit_is_in_the_source_table(self):  # 114
        self.assertIn("단계의 기준 장비", self.skill)

    def test_gear_warning_is_documented_and_labelled(self):  # 114
        self.assertIn("`gear_before_purchase`", self.economy_fmt)
        self.assertRegex(self.page, r'gear_before_purchase: "')

    def test_level_doc_points_to_the_purchase_timing(self):  # 108
        self.assertIn("purchase_timing", self.skill)

    def test_gear_check_says_what_it_does_not_see(self):  # 114
        self.assertIn("합성으로 얻는 장비는 보지 않는다", self.economy_fmt)

    def test_viewer_names_the_acknowledged_target(self):  # 117
        self.assertIn("it.part", self.page)

    def test_cells_rule_reads_the_same(self):  # 115
        self.assertNotIn("칸이 모두 비면", self.fmt)

    def test_viewer_shows_the_new_values(self):
        body = self.page[self.page.index("function renderLevels"):self.page.index("function renderPlaytests")]
        self.assertIn("앞 단계 대비", body)
        self.assertIn("purchase_timing", self.page)


if __name__ == "__main__":
    unittest.main()
