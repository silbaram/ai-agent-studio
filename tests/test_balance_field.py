"""회색 상자 20판으로 밸런스 가정값을 대 본 현장 시험(2026-11-08)의 이슈 276~282 테스트. 표준 라이브러리 unittest만 사용한다."""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from _studio import ROOT, calibrate as cal, cli, datasets, run_cli
from test_calibrate import CONFIG, Workspace, session, validate, codes


def row(r, kind, stage, item=None):
    return next((x for x in r["compare"] if x["kind"] == kind and x["stage"] == stage and x.get("item") == item), None)


def printed(r):
    buf = io.StringIO()
    with redirect_stdout(buf):
        cal.print_report(r)
    return buf.getvalue()


class TimedStage(Workspace):
    """276번: 시간이 다 되면 끝나는 단계의 길이는 비교하지 않는다."""

    def test_a_timed_stage_has_no_length_row_276(self):
        self.sessions(self.run_session(stage_stats=[{"stage": "zone_2", "entered": 10, "cleared": 4, "level": 4, "duration": 360, "timed": True}]))
        r = cal.calibrate(self.root)
        self.assertIsNone(row(r, "duration", "zone_2"))
        self.assertTrue(any("zone_2" in n and "시간이 다 되면 끝나는" in n for n in r["notes"]))

    def test_an_untimed_stage_is_still_compared_276(self):
        self.sessions(self.run_session(stage_stats=[{"stage": "zone_2", "entered": 10, "cleared": 4, "duration": 350}]))
        r = cal.calibrate(self.root)
        self.assertIsNotNone(row(r, "duration", "zone_2"))
        self.assertFalse(any("timed" in n for n in r["notes"]))

    def test_lengths_equal_to_the_assumption_ask_for_timed_276(self):
        self.sessions(self.run_session(stage_stats=[{"stage": "zone_2", "entered": 10, "cleared": 4, "duration": 360}]))
        r = cal.calibrate(self.root)
        self.assertIsNotNone(row(r, "duration", "zone_2"))   # 짐작으로 빼지 않는다
        self.assertTrue(any("zone_2" in n and '"timed": true' in n for n in r["notes"]))

    def test_timed_must_be_true_or_false_276(self):
        bad = session(stage_stats=[{"stage": "a", "entered": 10, "cleared": 6, "timed": "yes"}])
        self.assertIn("schema", codes(validate(bad)["errors"]))


class FewClearedRuns(Workspace):
    """277번: 넘긴 판이 적으면 처치·수입·길이 비교를 참고로 낮추고, 들어간 판 전체의 처치 속도를 비교한다."""

    def test_one_cleared_run_of_nine_is_only_a_hint_277(self):
        self.sessions(self.run_session(stage_stats=[{"stage": "zone_2", "entered": 9, "cleared": 1, "duration": 360, "kills": {"frost_wolf": 70}}]))
        r = cal.calibrate(self.root)
        kills = row(r, "kills", "zone_2", "frost_wolf")
        self.assertTrue(kills["off"])
        self.assertTrue(kills["few"])
        self.assertEqual(kills["entered"], 9)
        text = printed(r)
        self.assertIn("넘긴 판 1/9판, 참고", text)
        self.assertNotIn("⚠ economy.json stages.zone_2.kills.frost_wolf", text)

    def test_hints_are_not_counted_as_off_277(self):
        self.sessions(self.run_session(stage_stats=[{"stage": "zone_2", "entered": 9, "cleared": 1, "duration": 360, "kills": {"frost_wolf": 70}}]))
        self.assertRegex(printed(cal.calibrate(self.root)), r"건 중 0건이 20% 넘게 다름\(넘긴 판이 적어 참고로 둔 4건 제외\)")   # 처치 4종이 모두 다르다

    def test_three_of_nine_is_still_a_hint_277(self):
        self.sessions(self.run_session(stage_stats=[{"stage": "zone_2", "entered": 9, "cleared": 3, "kills": {"frost_wolf": 70}}]))
        self.assertTrue(row(cal.calibrate(self.root), "kills", "zone_2", "frost_wolf")["few"])   # 회색 상자의 9판 중 3판

    def test_all_failed_groups_stay_in_the_denominator_review_1(self):
        s = self.run_session(runs=10, groups=[
            {"upgrades": [], "variant": {"_setting": "1"}, "runs": 4, "stage_stats": [{"stage": "zone_2", "entered": 4, "cleared": 3, "duration": 350, "kills": {"frost_wolf": 70}}]},
            {"upgrades": [], "variant": {"_setting": "2"}, "runs": 6, "stage_stats": [{"stage": "zone_2", "entered": 6, "cleared": 0}]}])
        s.pop("upgrades")
        self.sessions(s)
        r = cal.calibrate(self.root)
        kills = row(r, "kills", "zone_2", "frost_wolf")
        self.assertEqual((kills["n"], kills["entered"], kills["few"]), (3, 10, True))   # 모두 실패한 묶음은 처치를 적을 수 없다
        self.assertEqual(row(r, "duration", "zone_2")["entered"], 10)

    def test_off_only_leaves_hints_out_review_3(self):
        self.sessions(self.run_session(stage_stats=[{"stage": "zone_2", "entered": 9, "cleared": 1, "level": 6, "duration": 360, "kills": {"frost_wolf": 70}}]))
        buf = io.StringIO()
        with redirect_stdout(buf):
            cal.print_report(cal.calibrate(self.root), off_only=True)
        self.assertIn("단계 zone_2 레벨", buf.getvalue())          # 4 → 6, 들어간 판 기준이라 참고가 아니다
        self.assertNotIn("참고(", buf.getvalue().replace("참고: ", ""))
        self.assertNotIn("넘긴 판 1/9판", buf.getvalue())

    def test_entered_counts_only_records_with_a_length_277(self):
        self.sessions(self.run_session("m1", stage_stats=[{"stage": "zone_2", "entered": 10, "cleared": 6, "duration": 350}]),
                      self.run_session("m2", runs=40, stage_stats=[{"stage": "zone_2", "entered": 40, "cleared": 4, "level": 4}]))
        length = row(cal.calibrate(self.root), "duration", "zone_2")
        self.assertEqual((length["entered"], length["few"]), (10, False))

    def test_enough_cleared_runs_are_not_a_hint_277(self):
        self.sessions(self.run_session(stage_stats=[{"stage": "zone_2", "entered": 10, "cleared": 5, "duration": 360, "kills": {"frost_wolf": 70}}]))
        r = cal.calibrate(self.root)
        self.assertFalse(row(r, "kills", "zone_2", "frost_wolf")["few"])
        self.assertIn("⚠ economy.json stages.zone_2.kills.frost_wolf", printed(r))

    def test_only_runs_that_recorded_the_value_count_as_entered_277(self):
        self.sessions(self.run_session("m1", stage_stats=[{"stage": "zone_2", "entered": 10, "cleared": 6, "kills": {"frost_wolf": 35}}]),
                      self.run_session("m2", runs=40, stage_stats=[{"stage": "zone_2", "entered": 40, "cleared": 4, "level": 4}]))
        kills = row(cal.calibrate(self.root), "kills", "zone_2", "frost_wolf")
        self.assertEqual((kills["n"], kills["entered"], kills["few"]), (6, 10, False))   # 처치를 적지 않은 m2의 40판은 세지 않는다

    def test_two_cleared_runs_are_too_few_even_when_all_cleared_277(self):
        self.sessions(self.run_session(runs=2, stage_stats=[{"stage": "zone_2", "entered": 2, "cleared": 2, "duration": 360}]))
        self.assertTrue(row(cal.calibrate(self.root), "duration", "zone_2")["few"])

    def test_kill_rate_of_all_entered_runs_is_compared_277(self):
        self.sessions(self.run_session(stage_stats=[{"stage": "zone_2", "entered": 10, "cleared": 1, "kill_rate": {"frost_wolf": 0.2}}]))
        r = cal.calibrate(self.root)
        rate = row(r, "kill_rate", "zone_2", "frost_wolf")
        self.assertAlmostEqual(rate["assumed"], round(35 / 360, 4))   # 재화 흐름: 360초에 35마리
        self.assertEqual((rate["measured"], rate["n"], rate["off"], rate["few"]), (0.2, 10, True, False))
        self.assertIn("길이 1당 처치(frost_wolf)", printed(r))

    def test_kill_rates_are_pooled_by_played_length_review_4(self):
        s = self.run_session(runs=6, groups=[
            {"upgrades": [], "variant": {"_setting": "1"}, "runs": 3, "stage_stats": [{"stage": "zone_2", "entered": 3, "cleared": 3, "kill_rate": {"frost_wolf": 0.6}, "played_length": 900}]},
            {"upgrades": [], "variant": {"_setting": "2"}, "runs": 3, "stage_stats": [{"stage": "zone_2", "entered": 3, "cleared": 0, "kill_rate": {"frost_wolf": 0.2}, "played_length": 300}]}])
        s.pop("upgrades")
        self.sessions(s)
        self.assertEqual(row(cal.calibrate(self.root), "kill_rate", "zone_2", "frost_wolf")["measured"], 0.5)   # 600마리 ÷ 1200초

    def test_runlog_writes_the_played_length_review_4(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "runs.csv"
        path.write_text(RUNS, encoding="utf-8")
        self.assertEqual(cal.summarize_runs(path)["groups"][0]["stage_stats"][0]["played_length"], 900)

    def test_played_length_shape_review_4(self):
        for bad in (0, -1, "x"):
            with self.subTest(bad=bad):
                s = session(stage_stats=[{"stage": "a", "entered": 10, "cleared": 6, "kill_rate": {"e1": 0.1}, "played_length": bad}])
                self.assertIn("schema", codes(validate(s)["errors"]))

    def test_kill_rate_enemies_are_checked_against_the_data_277(self):
        s = session(stage_stats=[{"stage": "a", "entered": 10, "cleared": 6, "kill_rate": {"e9": 0.1}}])
        r = validate(s)
        self.assertEqual(codes(r["warnings"]), ["unknown_reference"])
        self.assertIn("e9", r["warnings"][0]["message"])

    def test_kill_rate_shape_277(self):
        for bad in ({"e1": -1}, 3, {"e1": "x"}):
            with self.subTest(bad=bad):
                s = session(stage_stats=[{"stage": "a", "entered": 10, "cleared": 6, "kill_rate": bad}])
                self.assertIn("schema", codes(validate(s)["errors"]))


class EndLevel(Workspace):
    """278번: 단계를 끝낼 때의 레벨을 다음 단계의 level_at과 비교한다."""

    def test_end_level_meets_the_next_stage_278(self):
        self.sessions(self.run_session(stage_stats=[{"stage": "zone_1", "entered": 10, "cleared": 4, "level": 1, "level_end": 6}]))
        r = cal.calibrate(self.root)
        end = row(r, "level_end", "zone_1")
        self.assertEqual((end["assumed"], end["measured"], end["n"], end["off"]), (4, 6, 4, True))   # level_at.zone_2 = 4, 넘긴 판으로 가중
        self.assertEqual(end["where"], "growth.json growth.level_at.zone_2")
        self.assertIn("끝 레벨", printed(r))

    def test_one_surviving_run_is_a_hint_review_2(self):
        self.sessions(self.run_session(stage_stats=[{"stage": "zone_1", "entered": 3, "cleared": 1, "level": 1, "level_end": 4}]))
        r = cal.calibrate(self.root)
        end = row(r, "level_end", "zone_1")
        self.assertTrue(end["few"])
        self.assertIn("넘긴 판 1/3판, 참고", printed(r))

    def test_survivors_are_the_right_runs_for_end_level_review_2(self):
        # 다음 단계에 들어선 판은 넘긴 판뿐이라, 넘긴 판이 절반보다 적어도 치우친 값이 아니다. 판이 적을 때만 참고다
        self.sessions(self.run_session(runs=30, stage_stats=[{"stage": "zone_1", "entered": 30, "cleared": 5, "level": 1, "level_end": 6}]))
        self.assertFalse(row(cal.calibrate(self.root), "level_end", "zone_1")["few"])

    def test_the_last_stage_has_nothing_to_meet_278(self):
        self.sessions(self.run_session(stage_stats=[{"stage": "zone_3", "entered": 10, "cleared": 4, "level": 9, "level_end": 14}]))
        r = cal.calibrate(self.root)
        self.assertIsNone(row(r, "level_end", "zone_3"))
        self.assertTrue(any("zone_3" in n and "끝 레벨" in n for n in r["notes"]))

    def test_end_level_shape_278(self):
        s = session(stage_stats=[{"stage": "a", "entered": 10, "cleared": 6, "level_end": 0}])
        self.assertIn("schema", codes(validate(s)["errors"]))


RUNS = """run,player,stage,cleared,level,level_end,duration,kills.slime,_setting
1,self,zone_1,1,1,7,300,198,1
2,self,zone_1,0,1,4,120,80,1
3,self,zone_1,1,1,5,300,190,2
4,self,zone_1,0,1,3,180,90,2
"""


class RunLogColumns(unittest.TestCase):
    """276번·277번·278번: runlog가 끝 레벨, 처치 속도, 시간으로 끝난 단계를 모은다."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "runs.csv"

    def summarize(self, text=RUNS, group_by=None):
        self.path.write_text(text, encoding="utf-8")
        return cal.summarize_runs(self.path, group_by)

    def test_end_level_is_the_mean_of_cleared_runs_278(self):
        stats = self.summarize()["groups"][0]["stage_stats"][0]
        self.assertEqual(stats["level_end"], 6)          # 넘긴 판 7과 5

    def test_kill_rate_counts_every_entered_run_277(self):
        stats = self.summarize()["groups"][0]["stage_stats"][0]
        self.assertEqual(stats["kill_rate"], {"slime": round((198 + 80 + 190 + 90) / (300 + 120 + 300 + 180), 4)})

    def test_runlog_does_not_guess_a_timed_stage_276(self):
        # 넘긴 판의 길이가 같아도 시간 제한 단계라고 짐작하지 않는다(합성 기록, 정수로 찍은 길이도 같아진다)
        self.assertNotIn("timed", self.summarize()["groups"][0]["stage_stats"][0])

    def test_the_output_passes_the_record_check_278(self):
        out = self.summarize(group_by="_setting")
        s = session(runs=out["runs"], groups=[{**g, "stage_stats": [{**x, "stage": "a"} for x in g["stage_stats"]]} for g in out["groups"]])
        s.pop("upgrades"), s.pop("stage_stats")
        self.assertEqual(validate(s)["errors"], [])


class VariantFilter(Workspace):
    """280번: 시험 조건(variant)별로 보정한다."""

    def grouped(self):
        s = self.run_session(runs=20, groups=[
            {"upgrades": [], "variant": {"_setting": "1"}, "runs": 10, "stage_stats": [{"stage": "zone_2", "entered": 10, "cleared": 5, "level": 4}]},
            {"upgrades": [], "variant": {"_setting": "2"}, "runs": 10, "stage_stats": [{"stage": "zone_2", "entered": 10, "cleared": 5, "level": 8}]}])
        s.pop("upgrades")   # groups를 쓰면 묶음마다 적는다
        return s

    def test_only_the_chosen_condition_is_used_280(self):
        self.sessions(self.grouped())
        r = cal.calibrate(self.root, variant={"_setting": "1"})
        self.assertEqual(row(r, "level", "zone_2")["measured"], 4)
        self.assertTrue(any("_setting=1" in n for n in r["notes"]))
        self.assertFalse(any("합쳐 계산했습니다(_setting" in n for n in r["notes"]))

    def test_without_a_filter_conditions_are_merged_280(self):
        self.sessions(self.grouped())
        r = cal.calibrate(self.root)
        self.assertEqual(row(r, "level", "zone_2")["measured"], 6)
        self.assertTrue(any("합쳐 계산했습니다(_setting" in n for n in r["notes"]))

    def test_numbers_and_text_match_280(self):
        s = self.grouped()
        s["groups"][0]["variant"] = {"_setting": 1}
        self.sessions(s)
        self.assertEqual(row(cal.calibrate(self.root, variant={"_setting": "1"}), "level", "zone_2")["measured"], 4)

    def test_number_forms_match_review_5(self):
        for written, asked in ((1.0, "1"), ("1", "1.0"), (0.5, ".5")):
            with self.subTest(written=written, asked=asked):
                s = self.grouped()
                s["groups"][0]["variant"] = {"_setting": written}
                self.sessions(s)
                self.assertEqual(row(cal.calibrate(self.root, variant={"_setting": asked}), "level", "zone_2")["measured"], 4)

    def test_text_values_still_match_as_text_review_5(self):
        s = self.grouped()
        s["groups"][0]["variant"] = {"_setting": "hard"}
        self.sessions(s)
        self.assertEqual(row(cal.calibrate(self.root, variant={"_setting": "hard"}), "level", "zone_2")["measured"], 4)
        with self.assertRaises(cal.ConfigError):
            cal.calibrate(self.root, variant={"_setting": "Hard"})

    def test_a_repeated_column_is_refused_review_6(self):
        self.sessions(self.grouped())
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            code = cli.main(["calibrate", str(self.root), "--variant", "_setting=1", "--variant", "_setting=2"])
        self.assertEqual(code, 2)
        self.assertIn("_setting", err.getvalue())
        self.assertIn("두 번", err.getvalue())

    def test_no_matching_group_is_an_error_280(self):
        self.sessions(self.grouped())
        with self.assertRaises(cal.ConfigError) as ctx:
            cal.calibrate(self.root, variant={"_setting": "0.5"})
        self.assertIn("_setting=0.5", str(ctx.exception))
        self.assertIn("1, 2", str(ctx.exception))

    def test_the_command_line_takes_the_filter_280(self):
        self.sessions(self.grouped())
        code, out = run_cli("calibrate", str(self.root), "--variant", "_setting=2")
        self.assertEqual(code, 0)
        self.assertIn("측정 8", out)
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            code = cli.main(["calibrate", str(self.root), "--variant", "_setting"])
        self.assertEqual(code, 2)
        self.assertIn("열=값", err.getvalue())


class SurvivalWarnings(Workspace):
    """279번: 한 단계로 맞춘 등급 값이 다른 단계에도 쓰이는 것과, 지금 값과 크게 다른 제안을 알린다."""

    def fitted(self, cleared):
        self.sessions(self.run_session(runs=200, stage_stats=[{"stage": "zone_1", "entered": 200, "cleared": cleared, "level": 1}]))
        return cal.calibrate(self.config)

    def test_other_stages_of_the_rank_are_named_279(self):
        r = self.fitted(40)
        self.assertTrue(r["survival"]["fit"]["even_margin"]["fitted"]["boss"])
        note = next(n for n in r["notes"] if "기록이 없는 단계" in n)
        self.assertIn("boss", note)
        self.assertIn("zone_2", note)
        self.assertNotIn("zone_1", note.split("기록이 없는 단계")[1])

    def test_a_large_change_points_at_the_model_279(self):
        r = self.fitted(4)   # boss 0.12 → 약 0.63
        self.assertTrue(any("배입니다" in n and "kill_time_over_length" in n for n in r["notes"]))

    def test_a_modest_change_is_quiet_279(self):
        r = self.fitted(40)  # boss 0.12 → 약 0.27
        self.assertFalse(any("배입니다" in n for n in r["notes"]))


class FitWarningUnits(unittest.TestCase):
    """279번: 맞춘 등급이 있는 단계만 적고, 작아지는 제안도 알린다."""

    def warnings(self, now, new):
        rows = {"zone_1": [{"rank": "boss"}], "zone_2": [{"rank": "normal"}], "zone_3": [{"rank": "boss"}]}
        result = {"even_margin": {"fitted": {"boss": True, "normal": False}, "current": {"normal": 1.0, "boss": now},
                                  "suggested": {"normal": 1.0, "boss": new}}}
        with mock.patch.object(cal.mm, "stage_rows", return_value=rows):
            return cal._fit_warnings({}, [{"stage": "zone_1"}], result)

    def test_only_stages_with_the_rank_are_named_279(self):
        note = self.warnings(0.12, 0.2)[0]
        self.assertIn("(zone_3)", note)          # zone_2에는 boss가 없다

    def test_a_shrinking_suggestion_is_told_too_279(self):
        self.assertTrue(any("0.25배" in n for n in self.warnings(0.4, 0.1)))
        self.assertFalse(any("배입니다" in n for n in self.warnings(0.4, 0.2)))


class GreyboxWithoutItems(unittest.TestCase):
    """281번: 확인 항목이 없는 레벨의 단계를 플레이한 기록이 있으면 알린다."""

    def check(self, playtests):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "data").mkdir()
        levels = {"levels": [{"id": "l1", "combat_stage": "zone_1", "encounters": [{"id": "e1", "enemies": {"slime": 1}}]}]}
        (root / "data/levels.json").write_text(json.dumps(levels), encoding="utf-8")
        if playtests is not None:
            (root / "data/playtests.json").write_text(json.dumps(playtests), encoding="utf-8")
        entries = datasets.collect([root])
        return next(e for e in entries if e.get("kind") == "levels")["report"]["notes"]

    def test_played_stage_without_items_is_noted_281(self):
        notes = self.check({"playtests": [session(stage_stats=[{"stage": "zone_1", "entered": 4, "cleared": 1}])]})
        note = next(n for n in notes if "그레이박스 확인 항목이 없습니다" in n)
        self.assertIn("l1", note)
        self.assertIn("zone_1", note)

    def test_without_play_records_it_stays_quiet_281(self):
        self.assertFalse(any("그레이박스" in n for n in self.check(None)))

    def test_a_stage_nobody_entered_stays_quiet_281(self):
        notes = self.check({"playtests": [session(stage_stats=[{"stage": "zone_1", "entered": 0, "cleared": 0}])]})
        self.assertFalse(any("그레이박스" in n for n in notes))

    def test_records_of_another_stage_stay_quiet_281(self):
        notes = self.check({"playtests": [session(stage_stats=[{"stage": "zone_9", "entered": 4, "cleared": 1}])]})
        self.assertFalse(any("그레이박스" in n for n in notes))


class Docs(unittest.TestCase):
    """276번~282번 문서."""

    def read(self, rel):
        return (ROOT / rel).read_text(encoding="utf-8")

    def test_calibration_doc_names_the_new_fields(self):
        text = self.read("skills/playtest-verdict/references/calibration.md")
        for word in ("`level_end`", "`kill_rate`", "`timed`", "--variant", "넘긴 판이 적", "기록이 없는 단계"):
            with self.subTest(word=word):
                self.assertIn(word, text)

    def test_values_runlog_does_not_gather_282(self):
        text = self.read("skills/playtest-verdict/references/calibration.md")
        self.assertRegex(text, r"runlog가 모으지 않는 값[^\n]*\[계산")

    def test_the_viewer_shows_end_level_and_timed_278(self):
        html = (ROOT / "skills/studio-data/assets/viewer.html").read_text(encoding="utf-8")
        self.assertIn("x.level_end", html)
        self.assertIn("x.timed === true", html)

    def test_level_design_mentions_the_greybox_note_281(self):
        self.assertIn("그레이박스 확인 항목이 없습니다", self.read("skills/level-design/SKILL.md"))


if __name__ == "__main__":
    unittest.main()
