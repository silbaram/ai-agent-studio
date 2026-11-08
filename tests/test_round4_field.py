"""레벨업 체감 4차(2026-11-08) 현장 시험의 이슈 283~299 테스트. 표준 라이브러리 unittest만 사용한다."""
import copy
import io
import unittest
from contextlib import redirect_stdout

from _studio import ROOT, STUDIO, concepts as cc, growth as gr
from test_growth import CHOICES, COMBAT, ENEMIES, codes, data, validate
from test_verdict_field import CONCEPTS, hyp, judge, printed, stamp, three, verdict


def shown(fn, result):
    buf = io.StringIO()
    with redirect_stdout(buf):
        fn(result)
    return buf.getvalue()


def effect(r, sid, choice):
    return next(x for x in r["pick_effects"] if x["stage"] == sid and x["choice"] == choice)


class PickEffects(unittest.TestCase):
    """283번·284번: 선택을 몇 번 해야 단계 적의 처치·버팀이 바뀌는지 보이고, 첫 선택이 아무것도 바꾸지 못하면 경고한다."""

    def nick(self, **over):
        d = data(choices=copy.deepcopy(CHOICES) + [{"id": "nick", "stats": {"attack": 1}, **over}])
        return validate(d)

    def test_a_pick_below_the_breakpoint_is_warned_283(self):
        r = self.nick()   # 공격 10 → 11은 slime(체력 60) 6타 그대로, 12에서 5타
        warned = [w for w in r["warnings"] if w["code"] == "pick_no_effect"]
        self.assertEqual([w["where"] for w in warned], ["nick"])   # 첫 단계 s1만. s2는 앞 단계의 성장을 넣지 않은 값이라 표에만 둔다
        self.assertEqual(effect(r, "s2", "nick")["first"], {"slime": 2})
        self.assertIn("slime 2번째", warned[0]["message"])
        self.assertEqual(effect(r, "s1", "nick")["first"], {"slime": 2})

    def test_a_pick_that_changes_something_is_quiet_283(self):
        r = validate(data())
        self.assertNotIn("pick_no_effect", codes(r["warnings"]))
        self.assertEqual(effect(r, "s1", "sharpen")["first"], {"slime": 1})
        self.assertEqual(effect(r, "s1", "vigor")["first"], {"slime": 1})     # 버티는 타수가 는다

    def test_no_effect_inside_the_stage_says_so_283(self):
        r = self.nick(stats={"attack": 0.1}, max_picks=3)   # 3번을 골라도 10.3: 6타
        e = effect(r, "s1", "nick")
        self.assertEqual(e["first"], {"slime": None})
        self.assertEqual(e["window"], 2)                       # s1 레벨 4 → s2 레벨 6
        msg = next(w["message"] for w in r["warnings"] if w["code"] == "pick_no_effect")
        self.assertIn("레벨업 2번 안에서", msg)

    def test_picks_stop_at_max_picks_283(self):
        r = self.nick(max_picks=1)   # 한 번만 고를 수 있으면 2번째(5타)는 오지 않는다
        e = effect(r, "s1", "nick")
        self.assertEqual((e["first"], e["hits_to_kill"]["slime"]), ({"slime": None}, [6, 6]))

    def test_the_first_stage_is_counted_even_at_level_one_284(self):
        r = validate(data(level_at={"s1": 1, "s2": 6}))
        self.assertEqual(effect(r, "s1", "sharpen")["window"], 5)

    def test_the_table_lists_the_hits_284(self):
        d = data(choices=copy.deepcopy(CHOICES) + [{"id": "nick", "stats": {"attack": 1}}])
        r = validate(d)
        text = gr.table(d, r)
        self.assertIn("| 단계 | 선택지 | 단계 안 레벨업 | 적 | 처치 타수 | 버티는 타수 | 처음 바뀌는 선택 |", text)
        self.assertIn("| s1 | nick | 2 | slime | 6 → 6 → 5 |", text)

    def test_normal_enemies_decide_when_a_stage_has_them_283(self):
        enemies = dict(ENEMIES, boss={"id": "boss", "rank": "boss", "stats": {"hp": 1000, "damage": 10}})
        combat = copy.deepcopy(COMBAT)
        for s in combat["stages"]:
            s["enemies"] = ["slime", "boss"]
        d = data(choices=copy.deepcopy(CHOICES) + [{"id": "nick", "stats": {"attack": 1}}])
        r = validate(d, combat=combat, enemies=enemies)   # 보스는 1000/11로 타수가 줄지만, 무리를 이루는 일반 적은 그대로다
        self.assertIn("pick_no_effect", codes(r["warnings"]))

    def test_chance_stats_are_not_judged_by_their_expected_value_283(self):
        combat = copy.deepcopy(COMBAT)
        combat["combat"]["stats"]["player"]["crit_chance"] = "crit"
        d = data(choices=copy.deepcopy(CHOICES) + [{"id": "luck", "stats": {"crit": 0.02}}])
        r = validate(d, combat=combat)   # 기대 피해 10.2는 6타 그대로지만, 실제로는 판마다 조금씩 효과가 난다
        self.assertNotIn("pick_no_effect", codes(r["warnings"]))
        self.assertFalse(any(x["choice"] == "luck" for x in r["pick_effects"]))

    def test_off_combat_choices_are_left_to_their_own_warning_283(self):
        d = data(choices=copy.deepcopy(CHOICES) + [{"id": "magnet", "stats": {"pickup": 1}}])
        r = validate(d)
        self.assertNotIn("pick_no_effect", codes(r["warnings"]))
        self.assertIn("stat_not_in_combat", codes(r["warnings"]))


class PickEffectReview(unittest.TestCase):
    """검토 3·4: 경고 문구와 단계가 하나뿐인 시험판."""

    def test_a_stage_without_normal_enemies_says_all_enemies_review_3(self):
        enemies = {"boss": {"id": "boss", "rank": "boss", "stats": {"hp": 60, "damage": 10}}}
        combat = copy.deepcopy(COMBAT)
        for s in combat["stages"]:
            s["enemies"] = ["boss"]
        d = data(choices=copy.deepcopy(CHOICES) + [{"id": "nick", "stats": {"attack": 1}}])
        msg = next(w["message"] for w in validate(d, combat=combat, enemies=enemies)["warnings"] if w["code"] == "pick_no_effect")
        self.assertIn("모든 적의", msg)
        self.assertNotIn("일반 적", msg)

    def test_a_single_stage_looks_up_to_max_picks_review_4(self):
        combat = copy.deepcopy(COMBAT)
        combat["stages"] = combat["stages"][:1]
        d = data(level_at={"s1": 1}, choices=copy.deepcopy(CHOICES) + [{"id": "nick", "stats": {"attack": 1}, "max_picks": 4}])
        r = validate(d, combat=combat)
        e = effect(r, "s1", "nick")
        self.assertIsNone(e["window"])                     # 다음 단계가 없어 단계 안 레벨업 수를 모른다
        self.assertEqual(e["first"], {"slime": 2})         # 4번까지 본다
        self.assertIn("| s1 | nick | – | slime | 6 → 6 → 5 → 5 → 5 |", gr.table(d, r))

    def test_a_single_stage_without_max_picks_has_a_default_limit_review_4(self):
        combat = copy.deepcopy(COMBAT)
        combat["stages"] = combat["stages"][:1]
        d = data(level_at={"s1": 1}, choices=copy.deepcopy(CHOICES) + [{"id": "nick", "stats": {"attack": 0.01}}])
        msg = next(w["message"] for w in validate(d, combat=combat)["warnings"] if w["code"] == "pick_no_effect")
        self.assertIn(f"선택 {gr.SINGLE_STAGE_PICKS}번 안에서 없음", msg)


class IdenticalBuilds(unittest.TestCase):
    """285번: 두 빌드가 한 단계에서 같은 스탯이 되면 참고 줄로 알린다."""

    def capped(self):
        choices = [dict(ch, max_picks=1) for ch in copy.deepcopy(CHOICES)]
        builds = [{"id": "blade", "priority": ["sharpen", "vigor", "plating"]}, {"id": "wall", "priority": ["plating", "vigor", "sharpen"]}]
        return validate(data(choices=choices, builds=builds))   # 레벨 4 = 레벨업 3번에 선택지 셋을 다 고른다

    def test_builds_that_pick_everything_are_noted_285(self):
        r = self.capped()
        same = [x for x in r["identical_builds"] if x["stage"] == "s1"]
        self.assertEqual(same[0]["builds"], ["blade", "wall"])
        self.assertEqual((same[0]["max_picks"], same[0]["levelups"]), (3, 3))
        self.assertIn("같은 스탯이 된 빌드: s1에서 blade, wall", shown(gr.print_extra, r))

    def test_an_uncapped_choice_has_no_total_285(self):
        builds = [{"id": "blade", "priority": ["sharpen", "vigor"]}, {"id": "twin", "priority": ["sharpen", "vigor"]}]
        r = validate(data(builds=builds))   # vigor에는 max_picks가 없다
        same = next(x for x in r["identical_builds"] if x["stage"] == "s1")
        self.assertIsNone(same["max_picks"])
        self.assertIn("max_picks가 없는 전투 선택지가 있음", shown(gr.print_extra, r))

    def test_a_first_stage_before_any_pick_is_quiet_285(self):
        builds = [{"id": "blade", "priority": ["sharpen", "vigor"]}, {"id": "wall", "priority": ["plating", "vigor"]}]
        r = validate(data(builds=builds, level_at={"s1": 1, "s2": 6}))   # 레벨 1에는 아직 고른 것이 없다
        self.assertFalse(any(x["stage"] == "s1" for x in r["identical_builds"]))

    def test_different_builds_are_quiet_285(self):
        builds = [{"id": "blade", "priority": ["sharpen", "vigor"]}, {"id": "wall", "priority": ["plating", "vigor"]}]
        self.assertEqual(validate(data(builds=builds))["identical_builds"], [])


def with_hyp(**over):
    data = copy.deepcopy(CONCEPTS)
    hyp(data).update(over)
    return data


class HypothesisBuilds(unittest.TestCase):
    """292번: 가설이 세는 빌드를 적으면, 다른 빌드의 세션으로 버팀·틀림을 내지 못한다."""

    def test_a_session_of_another_build_is_an_error_292(self):
        data = with_hyp(builds=["cfgnew"])
        r = judge(three(), [verdict(criteria=stamp(data))], concepts=data)
        self.assertEqual(codes(r["errors"]), ["verdict_session_wrong_build"])
        self.assertIn("cfgnew", r["errors"][0]["message"])

    def test_game_build_or_commit_may_match_292(self):
        data = with_hyp(builds=["cfgnew"])
        r = judge(three(game_build="cfgnew"), [verdict(criteria=stamp(data))], concepts=data)
        self.assertEqual(r["errors"], [])
        data = with_hyp(builds=["abc1234"])   # 세션의 build(커밋)
        self.assertEqual(judge(three(), [verdict(criteria=stamp(data))], concepts=data)["errors"], [])

    def test_unknown_is_not_blocked_292(self):
        data = with_hyp(builds=["cfgnew"])
        self.assertEqual(judge(three(), [verdict("unknown", criteria=stamp(data))], concepts=data)["errors"], [])

    def test_builds_are_part_of_the_criteria_review_1(self):
        self.assertNotEqual(stamp(with_hyp(builds=["cfgA"])), stamp(with_hyp(builds=["cfgA", "cfgB"])))
        self.assertEqual(stamp(with_hyp()), stamp())   # builds가 없는 가설의 지문은 그대로다(지난 판정이 흔들리지 않는다)

    def test_the_line_names_game_builds_review_6(self):
        sessions = three()
        sessions[0]["game_build"], sessions[1]["game_build"] = "cfgA", "cfgB"
        r = judge(sessions, [verdict(criteria=stamp())])
        self.assertIn("빌드 3개(cfgA, cfgB, abc1234)", printed(r))

    def test_shapes_292(self):
        for bad in ([], "cfg", [""], [1]):
            with self.subTest(bad=bad):
                self.assertIn("schema", codes(cc.validate(with_hyp(builds=bad))["errors"]))
        self.assertIn("schema", codes(judge([dict(three()[0], game_build="")], [])["errors"]))


class CutReason(unittest.TestCase):
    """293번·297번: cut에 언제, 왜 지웠는지 적는다."""

    def test_cut_reason_is_accepted_on_a_cut_verdict_293(self):
        r = judge(three(), [verdict(status="cut", criteria=stamp(), cut_reason="2026-11-08 test의 빌드 문장을 고쳐 다시 시험"), verdict("unknown", criteria=stamp())])
        self.assertEqual(r["errors"], [])

    def test_cut_reason_only_belongs_to_cut_293(self):
        r = judge(three(), [verdict(criteria=stamp(), cut_reason="이유")])
        self.assertEqual(codes(r["errors"]), ["schema"])
        self.assertIn("cut_reason", r["errors"][0]["message"])

    def test_the_viewer_shows_it_293(self):
        self.assertIn("cut_reason", (STUDIO / "assets/viewer.html").read_text(encoding="utf-8"))


class NextNeeds(unittest.TestCase):
    """295번: 모름 판정이 남긴 '다음 시험 전에 풀 것'을 다시 시험할 때 보인다."""

    def test_a_decided_verdict_does_not_show_it_review_5(self):
        r = judge(three(), [verdict(criteria=stamp(), next_needs="남은 메모")])
        self.assertNotIn("다음 시험 전에 풀 것", printed(r))

    def test_an_active_unknown_verdict_shows_it_295(self):
        r = judge(three(), [verdict("unknown", criteria=stamp(), next_needs="규칙 효과를 떼는 지표")])
        self.assertIn("다음 시험 전에 풀 것(parry_tempo.learn_timing): 규칙 효과를 떼는 지표", printed(r))

    def test_a_cut_verdict_keeps_showing_it_until_a_new_one_295(self):
        old = verdict("unknown", criteria="00000000", status="cut", next_needs="규칙 효과를 떼는 지표")
        r = judge(three(), [old])
        self.assertIn("다음 시험 전에 풀 것(parry_tempo.learn_timing): 규칙 효과를 떼는 지표 (지난 판정)", printed(r))
        r = judge(three(), [old, verdict(criteria=stamp())])
        self.assertNotIn("다음 시험 전에 풀 것", printed(r))   # 새 판정이 나왔다

    def test_shape_295(self):
        self.assertEqual(codes(judge(three(), [verdict("unknown", criteria=stamp(), next_needs="")])["errors"]), ["schema"])


class ReducedSample(unittest.TestCase):
    """296번·299번: 표본을 줄였으면 언제 줄였는지 남기고, 결과를 본 뒤에 줄인 가설은 버팀·틀림으로 판정하지 않는다."""

    def reduced(self, before=True, **over):
        info = {"runs": 25, "after_run": 9, "before_results": before, "date": "2026-11-08", **over}
        return with_hyp(sample={"players": 3, "runs": 15, "reduced_from": info})

    def test_the_line_says_it_was_reduced_296(self):
        data = self.reduced()
        r = judge(three(), [verdict(criteria=stamp(data))], concepts=data)
        self.assertEqual(r["errors"], [])
        self.assertIn("15/15판 (25판에서 줄임, 9판째 뒤)", printed(r))

    def test_reducing_after_the_results_blocks_a_decision_299(self):
        data = self.reduced(before=False)
        r = judge(three(), [verdict("refuted", criteria=stamp(data))], concepts=data)
        self.assertEqual(codes(r["errors"]), ["verdict_sample_reduced_after_results"])
        self.assertIn("모름", r["errors"][0]["message"])
        r = judge(three(), [verdict("unknown", criteria=stamp(data))], concepts=data)
        self.assertEqual(r["errors"], [])

    def test_shapes_296(self):
        for bad in ({"runs": 25}, {"runs": 25, "after_run": 9, "before_results": "yes", "date": "2026-11-08"},
                    {"runs": 10, "after_run": 9, "before_results": True, "date": "2026-11-08"},      # 줄이지 않았다(15 → 10은 늘림 반대)
                    {"runs": 25, "after_run": -1, "before_results": True, "date": "2026-11-08"},
                    {"runs": 25, "after_run": 9, "before_results": True, "date": "11/08"}):
            with self.subTest(bad=bad):
                data = with_hyp(sample={"players": 3, "runs": 15, "reduced_from": bad})
                self.assertIn("schema", codes(cc.validate(data)["errors"]))

    def test_a_wrong_key_is_named_review_2(self):
        data = with_hyp(sample={"players": 3, "runs": 15, "reduced_from": {"runs": 25, "after_run": 9, "before_summary": True, "date": "2026-11-08"}})
        msg = cc.validate(data)["errors"][0]["message"]
        self.assertIn("알 수 없는 키 before_summary", msg)
        self.assertIn("'before_results'의 오타", msg)

    def test_it_is_part_of_the_criteria_296(self):
        self.assertNotEqual(stamp(self.reduced()), stamp(self.reduced(before=False)))


class Docs(unittest.TestCase):
    """286번·288번·289번·290번·291번·292번·294번·295번·296번·297번·298번·299번 문서. 287번은 스킬 밖이다."""

    def read(self, rel):
        return (ROOT / rel).read_text(encoding="utf-8")

    def test_implementation_continues_after_propose_286_291(self):
        text = self.read("skills/scope-guard/SKILL.md")
        self.assertIn("apply", text.split("## 절차")[1].split("## ")[0])
        self.assertIn("Write/Edit", text)

    def test_structured_self_report_288(self):
        rec = self.read("skills/playtest-verdict/references/playtest-record.md")
        self.assertIn("구조화한 자기 보고", rec)
        self.assertIn("자기 보고", self.read("skills/studio-data/assets/claude/studio-judge.md"))

    def test_baseline_on_side_289(self):
        self.assertIn("주장이 맞는 쪽", self.read("skills/concept-exploration/references/brief.md"))

    def test_adding_a_hypothesis_290(self):
        text = self.read("skills/concept-exploration/references/brief.md")
        self.assertRegex(text, r"가설을 더하면[^\n]*success_criteria")

    def test_another_system_changed_292_295(self):
        skill = self.read("skills/playtest-verdict/SKILL.md")
        self.assertIn("`builds`", skill)
        self.assertIn("세션 id", skill)

    def test_cut_in_the_next_edit_294(self):
        self.assertIn("바로 다음 편집", self.read("skills/playtest-verdict/SKILL.md"))

    def test_reduce_per_hypothesis_before_results_296_299(self):
        skill = self.read("skills/playtest-verdict/SKILL.md")
        self.assertIn("sample.reduced_from", skill)
        self.assertIn("가설마다", skill)
        self.assertIn("결과 파일을 열기 전에", skill)

    def test_old_criteria_go_into_cut_reason_297(self):
        self.assertIn("cut_reason", self.read("skills/playtest-verdict/references/playtest-record.md"))

    def test_judge_does_not_cd_298(self):
        self.assertIn("`cd`", self.read("skills/studio-data/assets/claude/studio-judge.md"))

    def test_new_codes_are_documented(self):
        rec = self.read("skills/playtest-verdict/references/playtest-record.md")
        for code in ("verdict_session_wrong_build", "verdict_sample_reduced_after_results"):
            with self.subTest(code=code):
                self.assertIn(f"`{code}`", rec)
        self.assertIn("`pick_no_effect`", self.read("skills/run-growth/SKILL.md"))
        html = (STUDIO / "assets/viewer.html").read_text(encoding="utf-8")
        for code in ("pick_no_effect", "verdict_session_wrong_build", "verdict_sample_reduced_after_results"):
            with self.subTest(code=code):
                self.assertRegex(html, code + r': "')


if __name__ == "__main__":
    unittest.main()
