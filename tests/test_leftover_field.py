"""실제 사이클 수정분 현장 시험에서 미룬 이슈 238~253 테스트. 표준 라이브러리 unittest만 사용한다."""
import copy
import json
import unittest

from _studio import ROOT, SAMPLE, STUDIO, calibrate as cal, concepts as cc, meta_sim as sm, playtests as pt, provenance as cp, run_cli
from test_calibrate import Workspace
from test_levels import both, enc, level, run
from test_levels_field import ECONOMY
from test_scope import Project
from studio_data import scope

CONCEPTS = json.loads((SAMPLE / "design/concepts.json").read_text(encoding="utf-8"))


def codes(entries):
    return [e["code"] for e in entries]


class KillBoundUnknown(unittest.TestCase):
    """239번: 처치 시간을 모르는 적을 빼고 낸 하한이 1배 아래면 경고가 조용히 꺼진다. 참고 줄로 알린다."""

    PART = {"s1": {"a": 2.0}, "s2": {"c": 3.0}}   # s1의 b는 처치 시간을 모른다

    def test_a_lower_bound_under_one_is_noted_239(self):
        r = run(both(level("s1", enc(repeat=5))), kill_times=self.PART, economy=ECONOMY)
        self.assertNotIn("kill_time_over_length", codes(r["warnings"]))
        note = next((n for n in r["notes"] if "1배를 넘는지 모릅니다" in n), None)
        self.assertIsNotNone(note, r["notes"])
        self.assertIn("s1", note)
        self.assertIn("b", note)

    def test_a_known_ratio_under_one_says_nothing_239(self):
        r = run(both(level("s1", enc(repeat=5))), kill_times={"s1": {"a": 2.0, "b": 6.0}, "s2": {"c": 3.0}}, economy=ECONOMY)
        self.assertFalse(any("1배를 넘는지 모릅니다" in n for n in r["notes"]))


class NonGoalRules(Project):
    """243번: design.md의 Non-Goals에 적은 규칙을 명세가 쓰면 막고, 잇지 않은 규칙의 안내는 빼는 쪽을 먼저 말한다."""

    DESIGN = ("## Goals / Non-Goals\n\n**Goals:**\n- 템포를 만든다.\n\n**Non-Goals:**\n- 회피 비용(`combat_input.dodge_cost`)은 바꾸지 않는다.\n\n"
              "## Decisions\n\n- `combat_input.parry_window`를 따른다.\n")

    def with_design(self, name="add-tempo"):
        (self.root / "openspec/changes" / name / "design.md").write_text(self.DESIGN, encoding="utf-8")

    def test_a_non_goal_rule_in_the_spec_is_an_error_243(self):
        self.linked("add-tempo", "tempo", "combat_input", spec="회피는 `combat_input.dodge_cost`를 따른다(SHALL).\n")
        self.with_design()
        errors = scope.check(self.root)["errors"]
        self.assertEqual(codes(errors), ["rule_in_non_goals"])
        self.assertIn("combat_input.dodge_cost", errors[0]["message"])
        self.assertIn("Non-Goals", errors[0]["message"])

    def test_a_paragraph_after_the_list_is_not_a_non_goal_review_3(self):
        design = "**Non-Goals:**\n- 회피 비용은 바꾸지 않는다.\n\n결정: `combat_input.parry_window`를 따른다.\n"
        self.linked("add-tempo", "tempo", "combat_input", spec="패링은 `combat_input.parry_window`를 따른다(SHALL).\n")
        (self.root / "openspec/changes/add-tempo/design.md").write_text(design, encoding="utf-8")
        self.assertEqual(scope.check(self.root)["errors"], [])

    def test_a_non_goals_heading_takes_its_paragraphs_review_3(self):
        design = "## Non-Goals\n\n회피 비용(`combat_input.dodge_cost`)은 이번에 바꾸지 않는다.\n\n## Decisions\n"
        self.linked("add-tempo", "tempo", "combat_input", spec="회피는 `combat_input.dodge_cost`를 따른다(SHALL).\n")
        (self.root / "openspec/changes/add-tempo/design.md").write_text(design, encoding="utf-8")
        self.assertEqual(codes(scope.check(self.root)["errors"]), ["rule_in_non_goals"])

    def test_rules_outside_non_goals_are_fine_243(self):
        self.linked("add-tempo", "tempo", "combat_input", spec="패링은 `combat_input.parry_window`를 따른다(SHALL).\n")
        self.with_design()
        self.assertEqual(scope.check(self.root)["errors"], [])

    def test_the_unlinked_advice_leads_with_taking_the_line_out_243(self):
        self.linked("add-tempo", "tempo", spec="패링은 `combat_input.parry_window`를 따른다(SHALL).\n")
        message = scope.check(self.root)["errors"][0]["message"]
        self.assertLess(message.index("그 줄을 뺍니다"), message.index("--link"))
        self.assertIn("prototype.scope", message)


class UnknownRules(Project):
    """252번: 설계에 있는 시스템 뒤의 없는 규칙 id와 대문자 표기를 잡는다."""

    def test_an_unknown_rule_of_a_known_system_is_an_error_252(self):
        self.linked("add-tempo", "tempo", "combat_input", spec="`combat_input.parry_windw`를 따른다(SHALL).\n")
        errors = scope.check(self.root)["errors"]
        self.assertEqual(codes(errors), ["unknown_rule"])
        self.assertIn("'parry_window'의 오타", errors[0]["message"])

    def test_a_data_field_is_not_a_rule_typo_review_1(self):
        # 실제 규칙과 비슷하지 않은 이름은 데이터 칸(combat_input.max_hp)으로 보고 막지 않는다
        self.linked("add-tempo", "tempo", "combat_input", spec="`combat_input.max_hp`를 data에서 읽는다(SHALL).\n",
                    proposal="## Why\n\n`combat_input.input_buffer_ms` 값을 쓴다.\n")
        self.assertEqual(scope.check(self.root)["errors"], [])

    def test_file_names_are_not_rules_252(self):
        self.linked("add-tempo", "tempo", spec="참고: `tempo.json`, `combat_input.md`, `combat_input.csv`, design/combat_input.nope\n")
        self.assertEqual(scope.check(self.root)["errors"], [])

    def test_upper_case_still_points_at_the_rule_252(self):
        self.linked("add-tempo", "tempo", spec="`Combat_Input.parry_window`를 따른다(SHALL).\n")
        self.assertEqual(codes(scope.check(self.root)["errors"]), ["rule_of_unlinked_system"])


class BareCriteriaNumbers(unittest.TestCase):
    """246번: 판정 기준 문장에서는 단위 없는 소수·음수와 '건'도 수치로 본다."""

    def brief_warnings(self, signal):
        data = copy.deepcopy(CONCEPTS)
        c = next(x for x in data["concepts"] if x["status"] == "approved")
        c["brief"]["hypotheses"][0]["failure_signal"] = signal
        return [w for w in cc.validate(data)["warnings"] if w["code"] == "untagged_number"]

    def test_unitless_and_count_thresholds_need_tags_246(self):
        for signal, shown in (("상관이 -0.2보다 크다", "-0.2"), ("0.3 이상의 상관", "0.3"), ("사망 6건 이상", "6건"),
                              ("60초 구간 안의 상관이 0.2 [가정]보다 크다", "60초")):
            with self.subTest(signal):
                found = self.brief_warnings(signal)
                self.assertEqual(len(found), 1, found)
                self.assertIn(shown, found[0]["message"])

    def test_tagged_thresholds_pass_246(self):
        self.assertEqual(self.brief_warnings("60초 [가정] 구간 안의 상관이 -0.2 [가정]보다 크다, 사망 6건 [가정], 0.5배 [가정] 설정"), [])

    def test_a_tagged_range_is_one_number_review_2(self):
        for signal in ("상관이 0.2~0.3 [가정] 사이", "상관이 0.2–0.3 [가정] 사이", "상관이 0.2-0.3 [가정] 사이"):
            with self.subTest(signal):
                self.assertEqual(self.brief_warnings(signal), [])
        self.assertEqual(len(self.brief_warnings("상관이 0.2~0.3 사이")), 1)

    def test_plain_documents_keep_their_rule_246(self):
        r = cp.check_text("상관이 -0.2보다 크다\n", "doc.md")
        self.assertEqual(r.findings, [])
        r = cp.check_text("사망 6건 이상\n", "doc.md")
        self.assertEqual(len(r.findings), 1)   # '건'은 문서에서도 단위다


class SessionNamesAndBuilds(unittest.TestCase):
    """248번: 대소문자·공백만 다른 이름을 알리고, 빌드가 섞인 근거를 판정 줄에 보인다."""

    def session(self, sid, players, build="abc1234", date="2026-11-07"):
        return {"id": sid, "date": date, "concept": "parry_tempo", "build": build, "players": players, "runs": 5,
                "observations": [{"hypothesis": "learn_timing", "value": "피격률 40% → 15%"}]}

    def judge(self, sessions, verdicts=()):
        return pt.validate({"playtests": sessions, "verdicts": list(verdicts)}, cc.hypothesis_index(CONCEPTS))

    def test_a_name_differing_only_in_case_is_warned_248(self):
        r = self.judge([self.session("pt_a", ["self"]), self.session("pt_b", ["Self "], date="2026-11-08")])
        self.assertEqual(codes(r["warnings"]), ["player_name_variants"])
        self.assertEqual(r["warnings"][0]["where"], "pt_b")
        self.assertIn("self", r["warnings"][0]["message"])

    def test_a_variant_inside_one_session_says_so_review_6(self):
        r = self.judge([self.session("pt_a", ["self", "Self"])])
        self.assertEqual(codes(r["warnings"]), ["player_name_variants"])
        self.assertIn("같은 세션", r["warnings"][0]["message"])
        self.assertNotIn("앞 세션", r["warnings"][0]["message"])

    def test_the_same_name_or_other_names_are_quiet_248(self):
        self.assertEqual(self.judge([self.session("pt_a", ["self", "friend_a"]), self.session("pt_b", ["self"])])["warnings"], [])

    def test_mixed_builds_show_on_the_verdict_line_248(self):
        stamp = cc.hypothesis_index(CONCEPTS)["parry_tempo"]["criteria"]["learn_timing"]
        v = {"concept": "parry_tempo", "hypothesis": "learn_timing", "result": "unknown", "sessions": ["pt_a", "pt_b"],
             "reason": "표본이 모자란다", "criteria": stamp, "status": "proposed"}
        r = self.judge([self.session("pt_a", ["self"], build="f54beb1"), self.session("pt_b", ["self"], build="abc1234")], [v])
        self.assertIn("빌드 2개(f54beb1, abc1234)", r["verdicts"]["parry_tempo.learn_timing"]["sample_text"])
        r = self.judge([self.session("pt_a", ["self"]), self.session("pt_b", ["self"])], [v])
        self.assertNotIn("빌드", r["verdicts"]["parry_tempo.learn_timing"]["sample_text"])


class CalibrateNotes(Workspace):
    """249번: 시험 조건이 다른 묶음을 합친 사실을 말하고, 비교할 값이 없을 때 원인을 바로 짚는다."""

    def test_merged_variants_are_noted_249(self):
        groups = [{"upgrades": [], "variant": {"_setting": v}, "runs": 10, "players": ["p"],
                   "stage_stats": [{"stage": "zone_2", "entered": 10, "cleared": 5, "level": 4, "duration": 300}]} for v in ("0.5", "1")]
        s = self.run_session(groups=groups)
        del s["upgrades"]   # 묶음을 쓰면 강화는 묶음마다 적는다
        self.sessions(s)
        r = cal.calibrate(self.root)
        note = next((n for n in r["notes"] if "시험 조건" in n), None)
        self.assertIsNotNone(note, r["notes"])
        self.assertIn("_setting: 0.5, 1", note)
        self.assertNotIn("세션을 나눠", note)   # 한 번 모인 플레이는 세션 하나에 묶음으로 나눈다(검토 5)

    def test_nothing_to_compare_names_the_record_side_249(self):
        self.sessions(self.run_session(stage_stats=[{"stage": "zone_9", "entered": 10, "cleared": 0}]))
        with self.assertRaises(sm.ConfigError) as ctx:
            cal.calibrate(self.root / "data")
        self.assertNotIn("비교할 가정값이 없습니다", str(ctx.exception))
        self.assertIn("기록", str(ctx.exception))


class Docs(unittest.TestCase):
    """238번·244번·251번·253번: 문서로 푸는 것."""

    def read(self, rel):
        return (ROOT / rel).read_text(encoding="utf-8")

    def test_growth_covering_kill_time_names_the_gap_238(self):
        text = self.read("skills/level-design/SKILL.md")
        self.assertIn("남는 배수", text)
        self.assertIn("플레이 기록", text)

    def test_spec_edits_after_finished_tasks_244(self):
        for rel in ("skills/scope-guard/SKILL.md", "skills/scope-guard/references/openspec-setup.md"):
            with self.subTest(rel):
                self.assertIn("작업이 모두 끝난", self.read(rel))

    def test_the_user_picks_the_fix_and_prototypes_follow_251(self):
        text = self.read("skills/level-design/SKILL.md")
        self.assertIn("전·후", text)
        self.assertIn("프로토타입", text)

    def test_linking_more_systems_is_not_asked_review_4(self):
        self.assertRegex(self.read("skills/scope-guard/SKILL.md"), r"--link`?[^\n]*묻지 않는다")

    def test_strict_warnings_are_the_lines_to_read_253(self):
        self.assertIn("WARNING", self.read("skills/scope-guard/references/openspec-setup.md"))

    def test_the_new_codes_are_documented(self):
        rec = self.read("skills/playtest-verdict/references/playtest-record.md")
        self.assertIn("`player_name_variants`", rec)
        guard = self.read("skills/scope-guard/SKILL.md")
        for code in ("rule_in_non_goals", "unknown_rule"):
            with self.subTest(code):
                self.assertIn(f"`{code}`", guard)


if __name__ == "__main__":
    unittest.main()
