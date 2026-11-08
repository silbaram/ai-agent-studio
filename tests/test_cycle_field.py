"""실제 한 사이클(회색 상자 구현, 플레이, 판정) 현장 시험의 이슈 225~236 테스트. 표준 라이브러리 unittest만 사용한다."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from _studio import ROOT, SAMPLE, STUDIO, calibrate as cal, common, concepts as cc, levels as lv, meta_sim as sm, playtests as pt, run_cli
from test_levels import COMBAT, ENEMIES, THREAT, both, enc, level, run
from test_levels_field import ECONOMY, TIMES
from test_scope import HookCase, Project
from studio_data import scope

CONCEPTS = json.loads((SAMPLE / "design/concepts.json").read_text(encoding="utf-8"))


def codes(entries):
    return [e["code"] for e in entries]


def approved(data):
    return next(c for c in data["concepts"] if c["status"] == "approved")


def session(sid="pt_a", players=("self",), runs=5, **over):
    s = {"id": sid, "date": "2026-11-07", "concept": "parry_tempo", "build": "abc1234", "players": list(players), "runs": runs,
         "observations": [{"hypothesis": "learn_timing", "value": "피격률 40% → 15%", "n": runs}]}
    s.update(over)
    return s


def verdict(result="holds", sessions=("pt_a",)):
    return {"concept": "parry_tempo", "hypothesis": "learn_timing", "result": result, "sessions": list(sessions),
            "reason": "피격률이 줄었다", "status": "proposed"}


def judge(sessions, verdicts, concepts=None):
    return pt.validate({"playtests": sessions, "verdicts": verdicts}, cc.hypothesis_index(concepts or CONCEPTS))


class HypothesisIds(unittest.TestCase):
    """227번: 판정은 가설 id로 가리키므로 승인한 브리프의 가설에 id가 없으면 플레이 전에 알린다."""

    def test_an_approved_hypothesis_without_id_is_warned_227(self):
        data = copy.deepcopy(CONCEPTS)
        del approved(data)["brief"]["hypotheses"][0]["id"]
        r = cc.validate(data)
        self.assertEqual((codes(r["errors"]), codes(r["warnings"])), ([], ["hypothesis_id_missing"]))
        self.assertIn("brief.hypotheses[0]", r["warnings"][0]["message"])

    def test_a_proposed_concept_is_not_asked_227(self):
        data = copy.deepcopy(CONCEPTS)
        c = approved(data)
        c["status"] = "proposed"
        del c["brief"]["hypotheses"][0]["id"]
        self.assertNotIn("hypothesis_id_missing", codes(cc.validate(data)["warnings"]))


class HypothesisSample(unittest.TestCase):
    """236번: 가설마다 최소 표본을 숫자로 적고, 확정 판정이 그보다 적은 표본에 기대면 막는다."""

    def test_the_sample_project_states_its_samples_236(self):
        r = cc.validate(copy.deepcopy(CONCEPTS))
        self.assertEqual((r["errors"], r["warnings"]), ([], []))
        self.assertEqual(cc.hypothesis_index(CONCEPTS)["parry_tempo"]["samples"]["learn_timing"], {"players": 3, "runs": 15})

    def test_a_hypothesis_without_sample_is_warned_236(self):
        data = copy.deepcopy(CONCEPTS)
        del approved(data)["brief"]["hypotheses"][1]["sample"]
        r = cc.validate(data)
        self.assertEqual(codes(r["warnings"]), ["hypothesis_sample_missing"])
        self.assertIn("tempo_choice", r["warnings"][0]["message"])

    def test_a_sample_is_positive_whole_counts_236(self):
        for bad in ({}, {"players": 0}, {"runs": 1.5}, {"runs": True}, {"people": 3}, [3], "3명"):
            with self.subTest(bad):
                data = copy.deepcopy(CONCEPTS)
                approved(data)["brief"]["hypotheses"][0]["sample"] = bad
                self.assertEqual(codes(cc.validate(data)["errors"]), ["schema"])

    def test_a_decided_verdict_below_the_sample_is_an_error_236(self):
        r = judge([session()], [verdict()])
        self.assertEqual(codes(r["errors"]), ["verdict_sample_short"])
        self.assertIn("1명 · 5판", r["errors"][0]["message"])
        self.assertIn("3명 · 15판", r["errors"][0]["message"])

    def test_unknown_below_the_sample_is_the_right_answer_236(self):
        self.assertEqual(judge([session()], [verdict("unknown")])["errors"], [])

    def test_sessions_add_up_to_the_sample_236(self):
        a = session("pt_a", players=("self", "friend_a"), runs=10)
        b = session("pt_b", players=("friend_b", "self"), runs=5)
        self.assertEqual(judge([a, b], [verdict(sessions=("pt_a", "pt_b"))])["errors"], [])
        self.assertEqual(codes(judge([a, b], [verdict(sessions=("pt_a",))])["errors"]), ["verdict_sample_short"])

    def test_one_run_short_is_short_236(self):
        s = session(players=("self", "friend_a", "friend_b"), runs=14)
        self.assertEqual(codes(judge([s], [verdict()])["errors"]), ["verdict_sample_short"])
        s = session(players=("self", "friend_a"), runs=15)
        self.assertEqual(codes(judge([s], [verdict()])["errors"]), ["verdict_sample_short"])

    def test_sessions_that_did_not_observe_the_hypothesis_do_not_count_236(self):
        observed = session("pt_a")
        other = session("pt_b", players=("friend_a", "friend_b"), runs=15, observations=[{"hypothesis": "tempo_choice", "value": "회피 55%"}])
        r = judge([observed, other], [verdict(sessions=("pt_a", "pt_b"))])
        self.assertEqual(codes(r["errors"]), ["verdict_sample_short"])
        self.assertIn("1명 · 5판", r["errors"][0]["message"])
        self.assertEqual(r["verdicts"]["parry_tempo.learn_timing"]["sample"], {"sessions": 1, "runs": 5, "players": 1})   # 출력도 게이트와 같은 표본

    def test_a_hypothesis_without_sample_is_not_gated_236(self):
        data = copy.deepcopy(CONCEPTS)
        del approved(data)["brief"]["hypotheses"][0]["sample"]
        self.assertEqual(judge([session()], [verdict()], data)["errors"], [])


class RunLogVariant(unittest.TestCase):
    """228번: 시험 설정처럼 강화가 아닌 조건으로도 판을 나눠 모은다."""

    CSV = "run,stage,cleared,player,_setting\nr1,zone_1,0,self,0.5\nr2,zone_1,1,self,1\nr3,zone_1,0,self,1\n"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "runs.csv"
        self.path.write_text(self.CSV, encoding="utf-8")

    def test_runs_are_split_by_the_named_column_228(self):
        groups = cal.summarize_runs(self.path, group_by="_setting")["groups"]
        self.assertEqual([g["variant"] for g in groups], [{"_setting": "0.5"}, {"_setting": "1"}])
        self.assertEqual([g["stage_stats"][0]["entered"] for g in groups], [1, 2])

    def test_without_the_option_runs_stay_together_228(self):
        groups = cal.summarize_runs(self.path)["groups"]
        self.assertEqual(len(groups), 1)
        self.assertNotIn("variant", groups[0])

    def test_a_missing_column_is_refused_228(self):
        with self.assertRaisesRegex(sm.ConfigError, "_mode"):
            cal.summarize_runs(self.path, group_by="_mode")

    def test_the_value_stays_the_same_within_a_run_228(self):
        self.path.write_text("run,stage,cleared,_setting\nr1,zone_1,1,0.5\nr1,zone_2,0,1\n", encoding="utf-8")
        with self.assertRaisesRegex(sm.ConfigError, "_setting"):
            cal.summarize_runs(self.path, group_by="_setting")

    def test_a_blank_value_is_refused_at_the_log_228(self):
        self.path.write_text("run,stage,cleared,_setting\nr1,zone_1,1,\nr2,zone_1,0,1\n", encoding="utf-8")
        with self.assertRaisesRegex(sm.ConfigError, "2번째 줄.*_setting"):
            cal.summarize_runs(self.path, group_by="_setting")

    def test_command_takes_the_option_228(self):
        code, out = run_cli("runlog", self.path, "--group-by", "_setting")
        self.assertEqual(code, 0)
        self.assertEqual(len(json.loads(out)["groups"]), 2)

    def test_a_session_keeps_the_variant_228(self):
        groups = cal.summarize_runs(self.path, group_by="_setting")["groups"]
        s = session(runs=3, groups=groups)
        self.assertEqual(judge([s], [])["errors"], [])
        for bad in ([], {"_setting": ["1"]}, {"": "1"}, "0.5"):
            with self.subTest(bad):
                broken = copy.deepcopy(s)
                broken["groups"][0]["variant"] = bad
                self.assertEqual(codes(judge([broken], [])["errors"]), ["schema"])


class RuleReferences(Project):
    """232번: 명세가 이어지지 않은 시스템의 규칙을 가리키면 그 시스템의 규칙이 바뀌어도 모른다."""

    SPEC = "## ADDED Requirements\n\n### Requirement: 템포\n템포는 `combat_input.parry_window`가 맞을 때 오른다(SHALL).\n"

    def test_a_rule_of_an_unlinked_system_is_an_error_232(self):
        self.linked("add-tempo", "tempo", spec=self.SPEC)
        errors = self.report()["errors"]
        self.assertEqual(codes(errors), ["rule_of_unlinked_system"])
        self.assertIn("combat_input.parry_window", errors[0]["message"])
        self.assertIn("--link add-tempo combat_input tempo", errors[0]["message"])

    def test_linking_the_system_clears_it_232(self):
        self.linked("add-tempo", "tempo", "combat_input", spec=self.SPEC)
        self.assertEqual(self.codes(), [])

    def test_the_proposal_counts_too_232(self):
        self.linked("add-tempo", "tempo", proposal="## Why\n\n`combat_input.dodge_cost`를 바꾼다.\n")
        self.assertEqual(self.codes(), ["rule_of_unlinked_system"])

    def test_file_names_paths_and_unknown_rules_are_not_rule_references_232(self):
        spec = "참고: `tempo.json`, design/combat_input.parry_window, `combat_input.nope`, combat_input.parry_window.md\n"
        self.linked("add-tempo", "tempo", spec=spec)
        self.assertEqual(self.codes(), [])

    def test_a_rule_of_a_system_not_built_now_says_to_take_it_out_232(self):
        self.set_system("meta_unlocks", status="cut")
        self.linked("add-tempo", "tempo", proposal="## Why\n\n`meta_unlocks.unlock_soul`은 건드리지 않는다.\n")
        errors = self.report()["errors"]
        self.assertEqual(codes(errors), ["rule_of_unlinked_system"])
        self.assertNotIn("--link", errors[0]["message"])
        self.assertIn("design.md", errors[0]["message"])

    def test_ids_may_start_with_a_digit_or_underscore_232(self):
        data = self.design()
        twin = dict(self.system(data, "meta_unlocks"), id="2d_move", rules=[{"id": "_dash", "text": "대시한다"}])
        data["systems"].append(twin)
        self.save(data)
        self.assertEqual(scope.check(self.root)["errors"], [])
        self.linked("add-tempo", "tempo", spec="`2d_move._dash`를 따른다(SHALL).\n")
        self.assertEqual(self.codes(), ["rule_of_unlinked_system"])

    def test_each_measured_file_is_read_once_232(self):
        self.linked("add-tempo", "tempo", spec=self.SPEC, proposal="## Why\n\n이유\n")
        reads = []
        real = Path.read_text

        def counting(path, *a, **k):
            reads.append(path.name)
            return real(path, *a, **k)
        with mock.patch.object(Path, "read_text", counting):
            scope.check(self.root)
        self.assertEqual(reads.count("spec.md"), 1)
        self.assertEqual(reads.count("proposal.md"), 1)

    def test_removed_requirements_are_not_measured_232(self):
        self.linked("add-tempo", "tempo", spec="## REMOVED Requirements\n\n### Requirement: 옛 규칙\n`combat_input.parry_window`\n")
        self.assertEqual(self.codes(), [])


class KillTimeOverLength(unittest.TestCase):
    """230번: 단일 대상 처치 시간이 단계 길이를 넘으면 무엇이 메우는지 확인하게 한다."""

    def over(self):
        return run(both(level("s1", enc(repeat=10, enemy_repeat={"b": 1}))), kill_times=TIMES, economy=ECONOMY)

    def test_a_stage_slower_than_its_length_is_warned_230(self):
        found = [w for w in self.over()["warnings"] if w["code"] == "kill_time_over_length"]
        self.assertEqual([w["where"] for w in found], ["s1"])
        self.assertIn("1.77배", found[0]["message"])

    def test_a_stage_within_its_length_is_quiet_230(self):
        self.assertNotIn("kill_time_over_length", codes(run(kill_times=TIMES, economy=ECONOMY)["warnings"]))

    def test_no_ratio_no_warning_230(self):
        eco = {**ECONOMY, "economy": {"time_unit": "방"}}
        r = run(both(level("s1", enc(repeat=10, enemy_repeat={"b": 1}))), kill_times=TIMES, economy=eco)
        self.assertNotIn("kill_time_over_length", codes(r["warnings"]))

    def test_it_is_acknowledged_on_a_level_of_the_stage_230(self):
        levels = both(level("s1", enc(repeat=10, enemy_repeat={"b": 1}),
                            acknowledged={"kill_time_over_length": "범위 공격이 무리를 쓸어 담는다"}))
        data = {"levels": levels}
        r = lv.validate(data, enemies=ENEMIES, threat=THREAT, combat=COMBAT, kill_times=TIMES, economy=ECONOMY)
        common.apply_acknowledged("levels", data, r)
        self.assertNotIn("kill_time_over_length", codes(r["warnings"]))
        self.assertIn("kill_time_over_length", codes(r["acknowledged"]))


class Docs(unittest.TestCase):
    """225, 226, 229, 231, 234, 235번: 도구가 아니라 절차로 푸는 것."""

    def read(self, rel):
        return (ROOT / rel).read_text(encoding="utf-8")

    def test_openspec_setup_says_how_to_write_korean_requirements_226(self):
        self.assertIn("(SHALL)", self.read("skills/scope-guard/references/openspec-setup.md"))

    def test_openspec_setup_says_named_steps_in_one_request_go_on_225_231(self):
        text = self.read("skills/scope-guard/references/openspec-setup.md")
        self.assertIn("/opsx:apply", text)
        self.assertIn("한 요청", text)

    def test_brief_doc_asks_for_direction_confounders_and_sample_235_236(self):
        text = self.read("skills/concept-exploration/references/brief.md")
        for word in ("반대 방향", "섞이는", '"sample"', "지표"):
            self.assertIn(word, text, word)

    def test_prototype_scope_is_the_source_of_the_prototype_229(self):
        text = self.read("skills/concept-exploration/references/brief.md")
        self.assertIn("next_test", text)
        self.assertIn("prototype.scope", text)

    def test_computed_observations_leave_an_output_file_for_the_judge_234(self):
        skill = self.read("skills/playtest-verdict/SKILL.md")
        judge_doc = (STUDIO / "assets/claude/studio-judge.md").read_text(encoding="utf-8")
        self.assertIn("결과 파일", skill)
        self.assertIn("결과 파일", judge_doc)
        self.assertIn("--group-by", self.read("skills/playtest-verdict/references/calibration.md"))

    def test_new_codes_are_explained_where_they_are_met(self):
        self.assertIn("rule_of_unlinked_system", self.read("skills/scope-guard/SKILL.md"))
        self.assertIn("kill_time_over_length", self.read("skills/level-design/SKILL.md"))
        record = self.read("skills/playtest-verdict/references/playtest-record.md")
        self.assertIn("verdict_sample_short", record)
        self.assertIn("variant", record)


if __name__ == "__main__":
    unittest.main()


# ---------- 현장 시험 237~242 ----------
class LinkKeepsStamps(Project):
    """237번: 다른 오류가 알려 준 --link가 design_changed를 지우면 안 된다. 지문을 새로 찍는 것은 --refresh로만."""

    def change_rule(self):
        data = self.design()
        self.system(data, "tempo")["rules"][0]["text"] = "완전히 다른 규칙"
        self.save(data)

    def test_adding_a_system_keeps_the_old_stamp_237(self):
        self.linked("add-tempo", "tempo")
        self.change_rule()
        code, out = run_cli("scope", self.root, "--link", "add-tempo", "tempo", "combat_input")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.codes(), ["design_changed"])
        self.assertIn("--refresh", out)

    def test_refresh_settles_a_changed_rule_237(self):
        self.linked("add-tempo", "tempo")
        self.change_rule()
        self.assertIn("--refresh", self.report()["errors"][0]["message"])
        self.assertEqual(run_cli("scope", self.root, "--link", "add-tempo", "tempo", "--refresh")[0], 0)
        self.assertEqual(self.codes(), [])

    def test_a_new_system_gets_todays_stamp_237(self):
        self.linked("add-tempo", "tempo")
        run_cli("scope", self.root, "--link", "add-tempo", "tempo", "combat_input")
        meta = (self.root / "openspec/changes/add-tempo/.openspec.yaml").read_text(encoding="utf-8")
        self.assertIn(f"combat_input: {scope.stamp(self.system(self.design(), 'combat_input'))}", meta)
        self.assertEqual(self.codes(), [])

    def test_dropping_and_adding_back_keeps_the_old_stamp_237(self):
        self.linked("add-tempo", "tempo", "room_flow")
        self.change_rule()
        run_cli("scope", self.root, "--link", "add-tempo", "room_flow")
        meta = (self.root / "openspec/changes/add-tempo/.openspec.yaml").read_text(encoding="utf-8")
        self.assertIn("x-studio-dropped: {tempo: ", meta)
        code, out = run_cli("scope", self.root, "--link", "add-tempo", "room_flow", "tempo")
        self.assertIn("--refresh", out)
        self.assertEqual(self.codes(), ["design_changed"])
        self.assertNotIn("x-studio-dropped", (self.root / "openspec/changes/add-tempo/.openspec.yaml").read_text(encoding="utf-8"))
        run_cli("scope", self.root, "--link", "add-tempo", "room_flow", "tempo", "--refresh")
        self.assertEqual(self.codes(), [])

    def test_refresh_needs_link_237(self):
        self.assertEqual(run_cli("scope", self.root, "--refresh")[0], 2)


class SourceFiles(unittest.TestCase):
    """240번: 기록 파일 경로가 실제로 있는지, 계산한 관찰값이 결과 파일을 가리키는지 프로젝트 검사에서 본다."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "playtests/pt_a").mkdir(parents=True)
        for name in ("runs.csv", "summary.txt"):
            (self.root / "playtests/pt_a" / name).write_text("1단계 33%\n", encoding="utf-8")   # 결과 파일에 옮긴 값이 있어야 한다(264번)

    def check(self, logs=("playtests/pt_a/runs.csv",), **over):
        s = session(logs=list(logs), **over)
        return pt.validate({"playtests": [s], "verdicts": []}, cc.hypothesis_index(CONCEPTS), root=self.root)

    def obs(self, **o):
        return [{"hypothesis": "learn_timing", "value": "1단계 33%", "note": "[계산: game/summarize.py]", **o}]

    def test_existing_files_pass_240(self):
        self.assertEqual(self.check(observations=self.obs(source="playtests/pt_a/summary.txt"))["warnings"], [])

    def test_a_missing_file_is_warned_240(self):
        r = self.check(observations=self.obs(source="playtests/pt_a/nope.txt"), logs=["playtests/pt_a/gone.csv"])
        self.assertEqual(codes(r["warnings"]), ["source_missing", "source_missing"])
        self.assertIn("gone.csv", " ".join(w["message"] for w in r["warnings"]))

    def test_words_are_not_paths_240(self):
        r = self.check(observations=[{"hypothesis": "learn_timing", "value": "v", "source": "본인 메모"}])
        self.assertEqual(r["warnings"], [])

    def test_a_computed_value_needs_an_output_file_240(self):
        for o in (self.obs(source="playtests/pt_a/runs.csv"), self.obs()):
            with self.subTest(o):
                self.assertEqual(codes(self.check(observations=o)["warnings"]), ["computed_without_output"])

    def test_without_a_root_paths_are_not_read_240(self):
        s = session(logs=["playtests/pt_a/gone.csv"])
        self.assertEqual(pt.validate({"playtests": [s], "verdicts": []}, cc.hypothesis_index(CONCEPTS))["warnings"], [])

    def test_the_project_check_finds_them_240(self):
        (self.root / "data").mkdir()
        (self.root / "design").mkdir()
        (self.root / "design/concepts.json").write_text(json.dumps(CONCEPTS, ensure_ascii=False), encoding="utf-8")
        s = session(logs=["playtests/pt_a/gone.csv"])
        (self.root / "data/playtests.json").write_text(json.dumps({"playtests": [s], "verdicts": []}, ensure_ascii=False), encoding="utf-8")
        code, out = run_cli("check", self.root)
        self.assertIn("source_missing", out)


class RecordedSample(unittest.TestCase):
    """241번: 표본 게이트는 단계 기록이 있으면 손으로 쓴 판 수·사람 수가 아니라 기록을 센다."""

    CSV = "run,stage,cleared,player\nr1,zone_1,0,self\nr2,zone_1,0,self\n"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "runs.csv"
        self.path.write_text(self.CSV, encoding="utf-8")

    def logged(self, runs=15, **over):
        body = cal.summarize_runs(self.path)
        return session(runs=runs, players=("self", "friend_a", "friend_b"), groups=body["groups"], **over)

    def test_runlog_names_the_players_of_each_group_241(self):
        self.assertEqual(cal.summarize_runs(self.path)["groups"][0]["players"], ["self"])

    def test_more_runs_or_players_than_the_records_is_warned_241(self):
        r = judge([self.logged()], [])
        self.assertEqual(codes(r["warnings"]), ["session_beyond_records"])
        self.assertIn("2", r["warnings"][0]["message"])

    def test_extra_players_alone_are_warned_241(self):
        r = judge([self.logged(runs=2)], [])
        self.assertEqual(codes(r["warnings"]), ["session_beyond_records"])
        self.assertIn("friend_a, friend_b", r["warnings"][0]["message"])

    def test_the_gate_counts_the_records_241(self):
        r = judge([self.logged()], [verdict()])
        self.assertEqual(codes(r["errors"]), ["verdict_sample_short"])
        self.assertEqual(r["verdicts"]["parry_tempo.learn_timing"]["sample"], {"sessions": 1, "runs": 2, "players": 1})

    def test_acknowledging_trusts_the_session_again_241(self):
        s = self.logged(acknowledged={"session_beyond_records": "기록은 두 판만 남았고 나머지는 손으로 셌다"})
        r = judge([s], [verdict()])
        self.assertEqual(r["errors"], [])
        self.assertEqual(r["verdicts"]["parry_tempo.learn_timing"]["sample"]["runs"], 15)

    def test_group_players_are_names_241(self):
        s = self.logged()
        s["groups"][0]["players"] = ["", 3]
        self.assertEqual(codes(judge([s], [])["errors"]), ["schema"])


class PlaytestFolderOpen(HookCase):
    """242번: 범위 오류가 있어도 플레이 기록과 결과 파일은 쓸 수 있다."""

    def test_playtest_files_stay_open_242(self):
        self.change()
        for rel in ("playtests/pt_a/harvest.csv", "playtests/pt_a/summary.txt"):
            self.assert_silent(self.write(rel))


class SampleLogs(unittest.TestCase):
    """240번: 샘플 기록이 가리키는 로그는 있어야 하고, runlog로 다시 모으면 기록과 같아야 한다."""

    def test_sample_run_logs_reproduce_the_sample_records_240(self):
        data = json.loads((SAMPLE / "data/playtests.json").read_text(encoding="utf-8"))
        checked = 0
        for s in data["playtests"]:
            for log in s.get("logs", []):
                self.assertTrue((SAMPLE / log).is_file(), log)
                if not log.endswith("runs.csv"):
                    continue
                groups = cal.summarize_runs(SAMPLE / log)["groups"]
                mine = s["groups"] if s.get("groups") else [s]
                got = [[{k: v for k, v in x.items() if k != "source"} for x in g["stage_stats"]] for g in groups]
                self.assertEqual(got, [h["stage_stats"] for h in mine], s["id"])
                checked += 1
        self.assertEqual(checked, 3)


class MetaLineGuard(HookCase):
    """237번: 지문 줄을 손으로 지우거나 고쳐 다시 이으면 바뀐 규칙이 새 지문으로 덮인다. 줄은 --link로만 쓴다."""

    META = "openspec/changes/add-tempo/.openspec.yaml"

    def test_editing_the_stamp_line_by_hand_is_blocked_237(self):
        self.linked("add-tempo", "tempo")
        text = (self.root / self.META).read_text(encoding="utf-8")
        line = next(x for x in text.splitlines() if x.startswith("x-studio-systems:"))
        self.assert_blocked(self.run_hook("Edit", file_path=str(self.root / self.META), old_string=line + "\n", new_string=""), "--link")
        self.assert_blocked(self.write(self.META, "schema: spec-driven\n"), "--link")
        self.assert_blocked(self.write(self.META, text.replace(line, "x-studio-systems: {tempo: 00000000}")), "--link")

    def test_other_keys_and_new_changes_stay_open_237(self):
        self.linked("add-tempo", "tempo")
        text = (self.root / self.META).read_text(encoding="utf-8")
        self.assert_silent(self.run_hook("Edit", file_path=str(self.root / self.META), old_string="created: 2026-11-05", new_string="created: 2026-11-06"))
        self.assert_silent(self.write("openspec/changes/add-other/.openspec.yaml", "schema: spec-driven\n"))
        self.assert_blocked(self.write("openspec/changes/add-other/.openspec.yaml", "x-studio-systems: {tempo: 1ad311e7}\n"), "--link")


class PathLikeSources(SourceFiles):
    """240번 검토: URL, 말, 앵커, 판 번호는 파일 경로가 아니다. 같은 파일을 다르게 적어도 같은 파일이다."""

    def test_links_and_words_are_not_files_240(self):
        for source in ("https://youtu.be/abc", "본인/지인 메모", "data/playtests.json#pt_a", "game/summarize.py 출력", "v1.2"):
            with self.subTest(source):
                r = self.check(observations=[{"hypothesis": "learn_timing", "value": "v", "source": source}])
                self.assertEqual(r["warnings"], [])

    def test_the_same_log_written_differently_is_still_the_log_240(self):
        for source in ("./playtests/pt_a/runs.csv", "playtests\\pt_a\\runs.csv", " playtests/pt_a/runs.csv "):
            with self.subTest(source):
                self.assertIn("computed_without_output", codes(self.check(observations=self.obs(source=source))["warnings"]))


class StageSelectRuns(unittest.TestCase):
    """241번 검토: 판마다 다른 단계로 들어가는 게임도 판 수를 맞게 센다. 손으로 쓴 단계 기록은 기록으로 세지 않는다."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "runs.csv"
        self.path.write_text("run,stage,cleared,player\nr1,m1,1,self\nr2,m2,0,self\nr3,m3,1,friend_a\n", encoding="utf-8")

    def test_runlog_counts_the_runs_of_each_group_241(self):
        self.assertEqual(cal.summarize_runs(self.path)["groups"][0]["runs"], 3)

    def test_mission_select_runs_are_counted_whole_241(self):
        s = session(runs=3, players=("self", "friend_a"), groups=cal.summarize_runs(self.path)["groups"])
        r = judge([s], [verdict("unknown")])
        self.assertEqual(r["errors"], [])
        self.assertNotIn("session_beyond_records", codes(r["warnings"]))     # 단계를 골라 시작하는 로그의 stage_counts_mismatch는 원래 확인으로 끈다
        self.assertEqual(r["verdicts"]["parry_tempo.learn_timing"]["sample"], {"sessions": 1, "runs": 3, "players": 2})

    def test_group_runs_must_fit_the_session_241(self):
        groups = cal.summarize_runs(self.path)["groups"]
        self.assertEqual(codes(judge([session(runs=2, players=("self", "friend_a"), groups=copy.deepcopy(groups))], [])["errors"]), ["schema"])
        bad = copy.deepcopy(groups)
        bad[0]["runs"] = 0
        self.assertEqual(codes(judge([session(runs=3, players=("self", "friend_a"), groups=bad)], [])["errors"]), ["schema"])
        bad = copy.deepcopy(groups)
        bad[0]["runs"] = 1
        bad[0]["stage_stats"][0]["entered"] = 2
        self.assertIn("schema", codes(judge([session(runs=3, players=("self", "friend_a"), groups=bad)], [])["errors"]))   # entered가 묶음의 판 수를 넘는다

    def test_hand_written_stage_records_are_not_counted_as_logs_241(self):
        s = session(runs=15, stage_stats=[{"stage": "zone_1", "entered": 2, "cleared": 0}], upgrades=[])
        r = judge([s], [])
        self.assertEqual(r["warnings"], [])
        self.assertEqual(pt._counted(s), (15, {"self"}))
