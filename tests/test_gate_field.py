"""게이트 통과 길(2026-11-09) 현장 시험의 이슈 300~304 테스트. 표준 라이브러리 unittest만 사용한다."""
import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from _studio import calibrate as cal, changes_section, common, datasets, ROOT, run_cli, STUDIO
from test_balance_field import row, printed as cal_printed
from test_calibrate import Workspace
from test_verdict_field import judge, printed, stamp, three, verdict, codes

STAGE = {"id": "zone_1", "duration": 300, "kills": {"crawler": 250, "elite": 2}, "income": {"seed": 15},
         "status": "proposed", "provenance": {"kind": "assumed"}}


def measured(path, source="data/playtests.json#pt_a"):
    return {"kind": "measured", "source": source}


class FieldProvenance(unittest.TestCase):
    """303번: 항목 안의 값마다 출처를 따로 적고, 모든 값이 가정이 아니게 되면 게이트에서 뺀다."""

    def entry(self, fields):
        e = copy.deepcopy(STAGE)
        e["provenance"]["fields"] = fields
        return e

    def test_one_measured_field_is_partial_303(self):
        e = self.entry({"kills.crawler": measured("kills.crawler")})
        errors: list = []
        self.assertTrue(common.check_common(e, "zone_1", errors))
        self.assertEqual(errors, [])
        self.assertEqual(common.field_coverage(e), (1, 4))
        s = common.summary_counts([e])
        self.assertEqual(s["unverified"], ["zone_1(필드 1/4)"])
        self.assertEqual(s["provenance_counts"]["assumed"], 1)

    def test_only_numbers_outside_meta_count_303(self):
        e = self.entry({"kills.crawler": measured("kills.crawler")})
        e.update({"combat_stage": "zone_1", "_seed": 3, "acknowledged": {"x": "이유"}})   # 글, 메모 칸, 메타 칸은 수치 칸이 아니다
        self.assertEqual(common.field_coverage(e), (1, 4))

    def test_a_path_must_end_at_a_field_boundary_303(self):
        errors: list = []
        common.check_common(self.entry({"kills.craw": measured("x")}), "zone_1", errors)   # kills.crawler의 앞부분일 뿐이다
        self.assertEqual([e["code"] for e in errors], ["provenance"])

    def test_every_field_covered_leaves_the_gate_303(self):
        e = self.entry({"duration": {"kind": "computed", "source": "game/config.js"}, "kills": measured("kills"),
                        "income.seed": measured("income.seed")})
        s = common.summary_counts([e])
        self.assertEqual(s["unverified"], [])
        self.assertEqual(s["provenance_counts"]["measured"], 1)   # 측정이 하나라도 있으면 측정으로 센다

    def test_an_assumed_field_still_counts_as_assumed_303(self):
        e = self.entry({"duration": {"kind": "assumed"}, "kills": measured("kills"), "income": measured("income")})
        self.assertEqual(common.summary_counts([e])["unverified"], ["zone_1(필드 3/4)"])

    def test_bad_fields_are_errors_303(self):
        for bad in ([], {"kills.crawler": "measured"}, {"kills.crawler": {"kind": "measured"}}, {"kills.ghost": measured("x")},
                    {"name": measured("x")}, {"": measured("x")}):
            with self.subTest(bad=bad):
                errors: list = []
                common.check_common(self.entry(bad), "zone_1", errors)
                self.assertEqual([e["code"] for e in errors], ["provenance"])

    def test_the_kind_is_normalized_303(self):
        e = self.entry({"kills.crawler": {"kind": "측정", "source": "data/playtests.json#pt_a"}})
        common.check_common(e, "zone_1", [])
        self.assertEqual(e["provenance"]["fields"]["kills.crawler"]["kind"], "measured")

    def test_entry_level_kind_still_wins_303(self):
        e = copy.deepcopy(STAGE)
        e["provenance"] = {"kind": "measured", "source": "data/playtests.json#pt_a"}
        self.assertEqual(common.summary_counts([e])["unverified"], [])

    def test_settings_without_numbers_explain_where_fields_go_review_5(self):
        errors: list = []
        common.check_common({"provenance": {"kind": "assumed", "fields": {"duration": measured("x")}}}, "economy", errors)
        self.assertIn("목록의 항목", errors[0]["message"])

    def test_the_viewer_reads_field_sources_review_3(self):
        html = (STUDIO / "assets/viewer.html").read_text(encoding="utf-8")
        self.assertIn("function fieldCoverage", html)
        self.assertIn("필드 ", html)

    def test_the_gate_shows_partial_entries_303(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        sample = STUDIO / "assets/sample-project"
        for rel in ("data/economy.json", "data/items.json", "data/upgrades.json", "data/enemies.json", "data/crafting.json", "data/combat.json"):
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text((sample / rel).read_text(encoding="utf-8"), encoding="utf-8")
        p = root / "data/economy.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        d["stages"][0]["provenance"]["fields"] = {"kills.slime": measured("kills.slime")}
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        code, out = run_cli("check", str(root), "--fail-on-assumed")
        self.assertIn("zone_1(필드 1/", out)


class LevelGate(unittest.TestCase):
    """검토 2: 레벨에 값마다 출처를 일부 적어도 그 레벨의 조우를 게이트에 따로 올리지 않는다."""

    def test_a_partial_level_hides_its_encounters_review_2(self):
        from _studio import levels as lv
        data = {"levels": [{"id": "l1", "combat_stage": "s1", "provenance": {"kind": "assumed", "fields": {"encounters.0.repeat": measured("x")}},
                            "encounters": [{"id": "e1", "enemies": {"slime": 1}, "repeat": 2, "provenance": {"kind": "assumed"}}]}]}
        r = lv.validate(data, enemies={"slime": {"id": "slime", "rank": "normal", "stats": {"hp": 10, "damage": 1}}})
        self.assertEqual([u for u in r["unverified"] if u.startswith("l1")], ["l1(필드 1/2)"])


class DeviationPerHypothesis(unittest.TestCase):
    """301번: 절차 이탈에 가설을 적으면 그 가설의 판정에만 센다."""

    def notes(self, *hyps):
        return [{"kind": "deviation", "text": "표본을 줄였다", **({"hypotheses": list(hyps)} if hyps else {})}]

    def test_a_deviation_counts_only_for_its_hypotheses_301(self):
        sessions = three(notes=self.notes("tempo_choice"))
        r = judge(sessions, [verdict(criteria=stamp())])
        self.assertEqual(r["verdicts"]["parry_tempo.learn_timing"]["deviations"], 0)
        r = judge(three(notes=self.notes("learn_timing")), [verdict(criteria=stamp())])
        self.assertEqual(r["verdicts"]["parry_tempo.learn_timing"]["deviations"], 3)

    def test_without_hypotheses_it_counts_for_all_301(self):
        r = judge(three(notes=self.notes()), [verdict(criteria=stamp())])
        self.assertEqual(r["verdicts"]["parry_tempo.learn_timing"]["deviations"], 3)

    def test_an_unknown_hypothesis_is_named_301(self):
        r = judge([dict(three()[0], notes=self.notes("learn_timng"))], [])
        self.assertEqual(codes(r["errors"]), ["unknown_hypothesis"])

    def test_malformed_notes_still_drop_the_session_review_1(self):
        bad = dict(three()[0], notes=[{"kind": "vibe", "text": ""}])
        r = judge([bad], [verdict(sessions=("pt_a",), criteria=stamp())])
        self.assertIn("schema", codes(r["errors"]))
        self.assertEqual(r["count"], 0)   # 형식이 틀린 세션은 판정 근거로 쓰지 않는다

    def test_shape_301(self):
        for bad in ([], "learn_timing", [""]):
            with self.subTest(bad=bad):
                s = dict(three()[0], notes=[{"kind": "deviation", "text": "x", "hypotheses": bad}])
                self.assertEqual(codes(judge([s], [])["errors"]), ["schema"])


class MixedConditions(Workspace):
    """302번: 시험 조건을 섞어 계산했으면, 조건마다 같은 쪽으로 다를 때만 고칠 곳(⚠)을 가리킨다."""

    def grouped(self, a, b):
        s = self.run_session(runs=20, groups=[
            {"upgrades": [], "variant": {"_setting": "1"}, "runs": 10, "stage_stats": [{"stage": "zone_2", "entered": 10, "cleared": 8, "level": a}]},
            {"upgrades": [], "variant": {"_setting": "2"}, "runs": 10, "stage_stats": [{"stage": "zone_2", "entered": 10, "cleared": 8, "level": b}]}])
        s.pop("upgrades")
        return s

    def test_conditions_pulling_apart_are_a_hint_302(self):
        self.sessions(self.grouped(2, 8))   # 가정 4: 한쪽은 낮고 한쪽은 높다. 합치면 5로 다르다
        r = cal.calibrate(self.root)
        level = row(r, "level", "zone_2")
        self.assertTrue(level["off"])
        self.assertTrue(level["mixed"])
        text = cal_printed(r)
        self.assertIn("조건마다 다름, 참고", text)
        self.assertIn("조건마다 달라 참고로 둔 1건 제외", text)
        self.assertNotIn("⚠ growth.json growth.level_at.zone_2", text)

    def test_conditions_agreeing_keep_the_mark_302(self):
        self.sessions(self.grouped(6, 7))   # 둘 다 가정 4보다 높다
        r = cal.calibrate(self.root)
        self.assertFalse(row(r, "level", "zone_2")["mixed"])
        self.assertIn("⚠ growth.json growth.level_at.zone_2", cal_printed(r))

    def test_a_value_from_one_condition_only_is_a_hint_302(self):
        s = self.grouped(6, 7)
        del s["groups"][1]["stage_stats"][0]["level"]   # 레벨은 한 조건에서만 잼
        self.sessions(s)
        self.assertTrue(row(cal.calibrate(self.root), "level", "zone_2")["mixed"])

    def test_hints_inside_each_condition_stay_hints_302(self):
        s = self.run_session(runs=8, groups=[
            {"upgrades": [], "variant": {"_setting": "1"}, "runs": 4, "stage_stats": [{"stage": "zone_2", "entered": 4, "cleared": 1, "kills": {"frost_wolf": 70}}]},
            {"upgrades": [], "variant": {"_setting": "2"}, "runs": 4, "stage_stats": [{"stage": "zone_2", "entered": 4, "cleared": 1, "kills": {"frost_wolf": 80}}]}])
        s.pop("upgrades")
        self.sessions(s)   # 두 조건 모두 같은 쪽으로 다르지만, 조건마다 넘긴 판 1판이라 참고다
        self.assertTrue(row(cal.calibrate(self.root), "kills", "zone_2", "frost_wolf")["mixed"])

    def test_one_condition_filtered_is_not_mixed_302(self):
        self.sessions(self.grouped(2, 8))
        self.assertFalse(row(cal.calibrate(self.root, variant={"_setting": "2"}), "level", "zone_2")["mixed"])

    def test_a_survival_fit_on_mixed_conditions_says_so_302(self):
        s = self.run_session(runs=400, groups=[
            {"upgrades": [], "variant": {"_setting": "1"}, "runs": 200, "stage_stats": [{"stage": "zone_3", "entered": 200, "cleared": 2, "level": 9}]},
            {"upgrades": [], "variant": {"_setting": "2"}, "runs": 200, "stage_stats": [{"stage": "zone_3", "entered": 200, "cleared": 4, "level": 9}]}])
        s.pop("upgrades")
        self.sessions(s)
        r = cal.calibrate(self.config)
        self.assertTrue(r["survival"]["fit"]["significant"])
        self.assertTrue(r["survival"]["fit"]["mixed"])
        self.assertIn("조건 섞임, 참고", cal_printed(r))
        self.assertIn("제안 값으로", cal_printed(r))
        self.assertRegex(cal_printed(r), r"제안 값으로 \d+% \(참고\)")   # 단계 줄만 읽어도 참고인 줄 안다(검토 4)


RUNS = """run,stage,cleared,duration,kills.slime
1,zone_1,1,300,190
2,zone_1,0,120,80
"""


class RunlogTimed(unittest.TestCase):
    """304번: runlog --timed로 시간 제한 단계를 적는다."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "runs.csv"
        self.path.write_text(RUNS, encoding="utf-8")

    def test_timed_stages_are_marked_304(self):
        stats = cal.summarize_runs(self.path, timed=["zone_1"])["groups"][0]["stage_stats"][0]
        self.assertTrue(stats["timed"])

    def test_an_unknown_stage_is_an_error_304(self):
        with self.assertRaises(cal.ConfigError) as ctx:
            cal.summarize_runs(self.path, timed=["zone_9"])
        self.assertIn("zone_9", str(ctx.exception))

    def test_the_command_line_takes_it_304(self):
        code, out = run_cli("runlog", str(self.path), "--timed", "zone_1")
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out)["groups"][0]["stage_stats"][0]["timed"])


class Docs(unittest.TestCase):
    """300번·303번·304번 문서."""

    def read(self, rel):
        return (ROOT / rel).read_text(encoding="utf-8")

    def test_undecided_reductions_are_reverted_300(self):
        self.assertIn("사용자가 정하지 않은", changes_section("표본을 줄이자는 말이 나올 때"))

    def test_field_provenance_is_documented_303(self):
        for rel in ("skills/numeric-provenance/SKILL.md", "skills/playtest-verdict/SKILL.md"):
            with self.subTest(rel=rel):
                self.assertIn("provenance.fields", self.read(rel))

    def test_timed_is_part_of_recording_304(self):
        self.assertIn("--timed", self.read("skills/playtest-verdict/references/calibration.md"))
        self.assertIn("--timed", self.read("skills/playtest-verdict/SKILL.md"))

    def test_deviation_hypotheses_documented_301(self):
        self.assertIn("hypotheses", self.read("skills/playtest-verdict/references/playtest-record.md"))


if __name__ == "__main__":
    unittest.main()
