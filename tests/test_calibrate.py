"""플레이 기록으로 가정값을 보정하는 calibrate(B5c) 테스트: 단계 기록 검사, 가정값 비교, 통과율 비교, 생존 곡선 제안.
표준 라이브러리 unittest만 사용한다."""
import io
import json
import math
import os
import random
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from _studio import SAMPLE, STUDIO, calibrate as cal, cli, common, datasets, meta_sim as sm, playtests as pt, run_cli

CONFIG = "data/meta_combat.json"


def codes(entries):
    return [e["code"] for e in entries]


def session(**over):
    s = {"id": "s1", "date": "2026-11-05", "concept": "c", "build": "abc", "players": ["p"], "runs": 10, "upgrades": [],
         "stage_stats": [{"stage": "a", "entered": 10, "cleared": 6}, {"stage": "b", "entered": 6, "cleared": 2}]}
    s.update(over)
    return s


REFS = {"stages": {"a", "b"}, "upgrades": {"u1"}, "enemies": {"e1"}, "builds": {"blade"}, "currencies": {"gold"}}


def validate(s, refs=REFS):
    return pt.validate({"playtests": [s]}, {"c": {"approved": False, "hypotheses": []}}, refs=refs)


class StageRecords(unittest.TestCase):
    def test_good_record_is_quiet(self):
        s = session(growth_build="blade", stage_stats=[{"stage": "a", "entered": 10, "cleared": 6, "level": 1, "duration": 300,
                                                       "kills": {"e1": 20}, "income": {"gold": 5}}])
        r = validate(s)
        self.assertEqual((r["errors"], r["warnings"], r["unchecked"]), ([], [], 0))

    def test_bad_shapes(self):
        ok = {"stage": "a", "entered": 10, "cleared": 6}
        for bad in ([dict(ok, cleared=11)], [dict(ok, entered=11, cleared=6)], [dict(ok, level=0)], [dict(ok, duration=0)],
                    [dict(ok, kills={"e1": -1})], [dict(ok, income=3)], [dict(ok, entered=1.5)], [ok, ok], "x", [{"stage": "a"}]):
            with self.subTest(bad):
                self.assertIn("schema", codes(validate(session(stage_stats=bad))["errors"]))
        self.assertIn("schema", codes(validate(session(upgrades="u1"))["errors"]))
        self.assertIn("schema", codes(validate(session(growth_build=3))["errors"]))

    def test_old_records_keep_working_when_data_moves_on(self):
        s = session(upgrades=["u9"], growth_build="bladee", stage_stats=[{"stage": "aa", "entered": 10, "cleared": 6, "kills": {"e2": 1}, "income": {"gol": 1}}])
        r = validate(s)
        self.assertEqual(r["errors"], [])
        self.assertEqual(codes(r["warnings"]), ["unknown_reference"] * 5)
        text = " ".join(w["message"] for w in r["warnings"])
        self.assertIn("'a'의 오타", text)
        self.assertIn("'blade'의 오타", text)

    def test_more_runs_entering_than_cleared_before_is_warned(self):
        s = session(stage_stats=[{"stage": "a", "entered": 10, "cleared": 4}, {"stage": "b", "entered": 6, "cleared": 2}])
        self.assertEqual(codes(validate(s)["warnings"]), ["stage_counts_mismatch"])

    def test_stage_record_is_an_observation(self):
        self.assertNotIn("session_without_observations", codes(validate(session())["warnings"]))

    def test_missing_reference_data_is_unchecked(self):
        r = validate(session(), refs=dict(REFS, stages=None))
        self.assertEqual(r["unchecked"], 1)
        self.assertEqual(r["unchecked_refs"], ["stages"])
        self.assertEqual(validate(session(), refs=None)["unchecked"], 1)   # 참조를 넘기지 않으면 단계를 확인하지 못했다


class Interval(unittest.TestCase):
    def test_wilson(self):
        lo, hi = cal.wilson(5, 10)
        self.assertAlmostEqual(lo, 0.2366, places=3)
        self.assertAlmostEqual(hi, 0.7634, places=3)
        self.assertEqual(cal.wilson(0, 10)[0], 0.0)
        self.assertEqual(cal.wilson(10, 10)[1], 1.0)


def rows(margin, rank="boss"):
    """여유가 margin인 적 하나의 행(타수 기준)."""
    return [{"enemy": "e", "rank": rank, "hits_to_kill": 100, "time_to_kill": None, "hits_to_die": margin * 100, "time_to_die": None}]


def survival(slope=1.0, even=1.0):
    return {"slope": slope, "even_margin": even, "floor": 0.0, "ceiling": 1.0}


def synthetic(slope, even, margins, n=4000, rank="boss", skill=0.0):
    truth = survival(slope, even)
    out = []
    for m in margins:
        p = cal.predicted(rows(m, rank), truth, skill, 0.0)
        out.append({"rows": rows(m, rank), "entered": n, "cleared": round(p * n)})
    return out


class Fit(unittest.TestCase):
    def test_recovers_slope_and_reference(self):
        f = cal.fit(synthetic(3.0, 0.2, [0.1, 0.15, 0.2, 0.3, 0.5]), survival(1.0, 1.0), 0.0, 0.0)
        self.assertAlmostEqual(f["slope"]["suggested"], 3.0, delta=0.3)
        self.assertAlmostEqual(f["even_margin"]["suggested"]["boss"], 0.2, delta=0.02)
        self.assertGreater(f["log_likelihood"]["suggested"], f["log_likelihood"]["current"])

    def test_each_rank_gets_its_own_reference(self):
        points = synthetic(2.0, 0.1, [0.05, 0.1, 0.2]) + synthetic(2.0, 1.5, [0.8, 1.5, 3.0], rank="normal")
        f = cal.fit(points, survival(2.0, {"normal": 1.0, "boss": 1.0}), 0.0, 0.0)
        self.assertAlmostEqual(f["even_margin"]["suggested"]["boss"], 0.1, delta=0.015)
        self.assertAlmostEqual(f["even_margin"]["suggested"]["normal"], 1.5, delta=0.2)

    def test_too_few_points_keep_the_slope(self):
        f = cal.fit(synthetic(3.0, 0.2, [0.15, 0.3]), survival(1.5, 1.0), 0.0, 0.0)
        self.assertEqual(f["slope"]["suggested"], 1.5)
        self.assertFalse(f["slope"]["fitted"])
        self.assertTrue(f["even_margin"]["fitted"]["boss"])

    def test_everyone_clearing_says_nothing_about_the_reference(self):
        points = [{"rows": rows(0.5), "entered": 50, "cleared": 50}, {"rows": rows(0.8), "entered": 50, "cleared": 50}]
        f = cal.fit(points, survival(2.0, 0.3), 0.0, 0.0)
        self.assertEqual(f["even_margin"]["suggested"], 0.3)      # 제안하지 않고 지금 값을 둔다
        self.assertTrue(any("boss" in n and "모두 넘겼" in n for n in f["notes"]))
        failed = [{"rows": rows(0.5), "entered": 50, "cleared": 0}]
        self.assertTrue(any("모두 실패했" in n for n in cal.fit(failed, survival(2.0, 0.3), 0.0, 0.0)["notes"]))

    def test_everyone_clearing_under_a_ceiling_is_not_fitted_either(self):
        # 천장이 있으면 찾는 범위 끝에 닿지 않고도 가능도가 평평해져 엉뚱한 값을 고를 수 있다
        points = [{"rows": rows(0.5), "entered": 50, "cleared": 50}, {"rows": rows(0.8), "entered": 50, "cleared": 50}]
        f = cal.fit(points, dict(survival(2.0, 0.9), ceiling=0.95), 0.0, 0.0)
        self.assertEqual(f["even_margin"]["suggested"], 0.9)

    def test_value_at_the_edge_of_the_search_is_not_suggested(self):
        # slope가 작아 어떤 기준으로도 이 통과율에 닿지 못한다: 찾는 범위의 끝에 닿는다
        points = [{"rows": rows(1.0), "entered": 1000, "cleared": 1}, {"rows": rows(1.2), "entered": 1000, "cleared": 2}]
        f = cal.fit(points, survival(0.1, 1.0), 0.0, 0.0)
        self.assertFalse(f["even_margin"]["fitted"]["boss"])
        self.assertEqual(f["even_margin"]["suggested"], 1.0)
        self.assertTrue(any("끝에 닿" in n for n in f["notes"]))

    def test_skill_spread_is_part_of_the_prediction(self):
        s = survival(2.0, 1.0)
        self.assertAlmostEqual(cal.predicted(rows(1.0), s, 0.0, 2.0), 0.5, places=6)   # 대칭이면 절반
        self.assertLess(cal.predicted(rows(3.0), s, 0.0, 2.0), cal.predicted(rows(3.0), s, 0.0, 0.0))


class Workspace(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "game"
        shutil.copytree(SAMPLE, self.root)
        self.config = self.root / CONFIG

    def tearDown(self):
        self.tmp.cleanup()

    def edit(self, rel, fn):
        p = self.root / rel
        d = json.loads(p.read_text(encoding="utf-8"))
        fn(d)
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")

    def sessions(self, *new):
        self.edit("data/playtests.json", lambda d: d.__setitem__("playtests", [x for x in d["playtests"] if "stage_stats" not in x and "groups" not in x] + list(new)))

    def run_session(self, sid="m1", **over):
        s = {"id": sid, "date": "2026-11-12", "concept": "parry_tempo", "build": "abc", "players": ["p"], "runs": 20, "upgrades": []}
        s.update(over)
        return s


class Comparison(Workspace):
    def row(self, r, kind, stage, item=None):
        return next(x for x in r["compare"] if x["kind"] == kind and x["stage"] == stage and x.get("item") == item)

    def test_assumed_values_are_compared_with_the_record(self):
        self.sessions(self.run_session(stage_stats=[{"stage": "zone_2", "entered": 20, "cleared": 10, "level": 6, "duration": 360,
                                                    "kills": {"frost_wolf": 70}, "income": {"soul": 12}}]))
        r = cal.calibrate(self.root)
        level = self.row(r, "level", "zone_2")
        self.assertEqual((level["assumed"], level["measured"], level["off"]), (4, 6, True))     # growth.level_at 4
        self.assertIn("growth.level_at", level["where"])
        self.assertFalse(self.row(r, "duration", "zone_2")["off"])
        self.assertTrue(self.row(r, "kills", "zone_2", "frost_wolf")["off"])                    # 가정 35, 측정 70
        self.assertEqual(self.row(r, "kills", "zone_2", "ice_mage")["measured"], 0)             # 기록에 없으면 0으로 잰다
        self.assertFalse(self.row(r, "income", "zone_2", "soul")["off"])

    def test_sessions_are_weighted_by_their_runs(self):
        self.sessions(self.run_session("m1", runs=30, stage_stats=[{"stage": "zone_2", "entered": 30, "cleared": 30, "level": 4, "duration": 300}]),
                      self.run_session("m2", runs=10, stage_stats=[{"stage": "zone_2", "entered": 10, "cleared": 10, "level": 8, "duration": 500}]))
        r = cal.calibrate(self.root)
        self.assertEqual(self.row(r, "level", "zone_2")["measured"], 5)
        self.assertEqual(self.row(r, "duration", "zone_2")["measured"], 350)
        self.assertEqual(self.row(r, "duration", "zone_2")["n"], 40)

    def test_runs_that_did_not_clear_say_nothing_about_a_full_stage(self):
        self.sessions(self.run_session(stage_stats=[{"stage": "zone_2", "entered": 10, "cleared": 0, "level": 4, "duration": 50}]))
        r = cal.calibrate(self.root)
        self.assertEqual([x["kind"] for x in r["compare"] if x["stage"] == "zone_2"], ["level"])

    def test_tolerance_decides_what_is_off(self):
        self.sessions(self.run_session(stage_stats=[{"stage": "zone_2", "entered": 10, "cleared": 5, "level": 5}]))
        self.assertTrue(self.row(cal.calibrate(self.root), "level", "zone_2")["off"])            # 4 → 5: 25%
        self.assertFalse(self.row(cal.calibrate(self.root, tolerance=0.3), "level", "zone_2")["off"])

    def test_economy_stages_are_matched_through_combat_stage(self):
        self.edit("data/economy.json", lambda d: d["stages"][1].__setitem__("id", "frozen_part"))
        self.edit("data/economy.json", lambda d: [p.pop("after", None) for p in d["purchases"]])
        self.sessions(self.run_session(stage_stats=[{"stage": "zone_2", "entered": 10, "cleared": 5, "duration": 360}]))
        self.assertEqual(self.row(cal.calibrate(self.root), "duration", "zone_2")["assumed"], 360)

    def test_folder_mode_has_no_survival_part(self):
        self.sessions(self.run_session(stage_stats=[{"stage": "zone_1", "entered": 10, "cleared": 5, "level": 1}]))
        r = cal.calibrate(self.root)
        self.assertIsNone(r["survival"])
        self.assertTrue(any("전투 계산 모델" in n for n in r["notes"]))


class StageSurvival(Workspace):
    def record(self, **over):
        return self.run_session(runs=40, stage_stats=[{"stage": "zone_3", "entered": 40, "cleared": 20, "level": 9}], **over)

    def stage(self, r):
        return next(x for x in r["survival"]["stages"] if x["stage"] == "zone_3")

    def test_prediction_is_compared_with_the_interval(self):
        self.sessions(self.record())
        s = self.stage(cal.calibrate(self.config))
        self.assertEqual((s["entered"], s["cleared"], s["rate"]), (40, 20, 0.5))
        self.assertLess(s["low"], 0.5)
        self.assertGreater(s["high"], 0.5)
        self.assertIn(s["verdict"], ("inside", "model_easier", "model_harder"))
        self.assertEqual(s["verdict"] == "inside", s["low"] <= s["predicted"] <= s["high"])

    def test_verdict_says_which_way_the_model_is_off(self):
        self.sessions(self.run_session(runs=400, stage_stats=[{"stage": "zone_3", "entered": 400, "cleared": 2, "level": 9}]))
        self.assertEqual(self.stage(cal.calibrate(self.config))["verdict"], "model_easier")     # 예측보다 훨씬 많이 진다
        self.sessions(self.run_session(runs=400, stage_stats=[{"stage": "zone_3", "entered": 400, "cleared": 399, "level": 1}]))
        self.assertEqual(self.stage(cal.calibrate(self.config))["verdict"], "model_harder")     # 예측보다 훨씬 많이 넘긴다

    def test_owned_upgrades_change_the_prediction(self):
        self.sessions(self.record())
        none = self.stage(cal.calibrate(self.config))["predicted"]
        self.sessions(self.record(upgrades=["weapon_1", "weapon_2", "vitality_1"]))
        self.assertGreater(self.stage(cal.calibrate(self.config))["predicted"], none)

    def test_measured_level_is_used(self):
        self.sessions(self.record())
        at9 = self.stage(cal.calibrate(self.config))["predicted"]
        self.sessions(self.run_session(runs=40, stage_stats=[{"stage": "zone_3", "entered": 40, "cleared": 20, "level": 16}]))
        self.assertGreater(self.stage(cal.calibrate(self.config))["predicted"], at9)

    def test_session_build_is_used(self):
        self.sessions(self.record(growth_build="blade"))
        blade = self.stage(cal.calibrate(self.config))["predicted"]
        self.sessions(self.record(growth_build="bulwark"))
        self.assertNotEqual(self.stage(cal.calibrate(self.config))["predicted"], blade)

    def test_session_without_upgrade_state_is_left_out_and_named(self):
        s = self.record()
        s.pop("upgrades")
        self.sessions(s, self.run_session("m2", stage_stats=[{"stage": "zone_1", "entered": 10, "cleared": 5}]))
        r = cal.calibrate(self.config)
        self.assertEqual([x["stage"] for x in r["survival"]["stages"]], ["zone_1"])
        self.assertTrue(any("m1" in n for n in r["notes"]))

    def test_session_with_old_references_is_left_out_and_named(self):
        self.sessions(self.record(upgrades=["gone_upgrade"]), self.run_session("m2", stage_stats=[{"stage": "zone_1", "entered": 10, "cleared": 5}]))
        r = cal.calibrate(self.config)
        self.assertEqual([x["stage"] for x in r["survival"]["stages"]], ["zone_1"])
        self.assertTrue(any("gone_upgrade" in n for n in r["notes"]))

    def test_suggestion_is_reported_with_the_stage_prediction(self):
        self.sessions(self.run_session("m1", stage_stats=[{"stage": "zone_1", "entered": 60, "cleared": 30, "level": 1},
                                                          {"stage": "zone_2", "entered": 30, "cleared": 12, "level": 4},
                                                          {"stage": "zone_3", "entered": 12, "cleared": 2, "level": 9}], runs=60))
        r = cal.calibrate(self.config)
        fit = r["survival"]["fit"]
        self.assertTrue(fit["slope"]["fitted"] or fit["even_margin"]["fitted"])
        self.assertGreaterEqual(fit["log_likelihood"]["suggested"], fit["log_likelihood"]["current"])
        self.assertIn("predicted_suggested", r["survival"]["stages"][0])


class CommandLine(Workspace):
    def test_sample_has_stage_records(self):
        code, out = run_cli("calibrate", self.config)
        self.assertEqual(code, 0)
        self.assertIn("단계 zone_1", out)
        self.assertIn("가정", out)

    def test_out_file_can_be_cited(self):
        out_path = self.root / "reports/calibrate.json"
        code, out = run_cli("calibrate", self.config, "--out", out_path)
        self.assertIn(f"[계산: {out_path}]", out)
        saved = json.loads(out_path.read_text(encoding="utf-8"))
        self.assertTrue(any(Path(x["path"]).name == "playtests.json" for x in saved["inputs"]))
        self.assertIn("evidence", saved)

    def test_abstract_config_is_refused(self):
        self.assertEqual(run_cli("calibrate", self.root / "data/meta.json")[0], 2)

    def test_no_stage_records_is_not_a_pass(self):
        self.sessions()
        self.assertEqual(run_cli("calibrate", self.config)[0], 2)

    def test_broken_playtest_file_is_refused(self):
        self.edit("data/playtests.json", lambda d: d["playtests"][-1]["stage_stats"][0].__setitem__("cleared", 10 ** 6))
        self.assertEqual(run_cli("calibrate", self.config)[0], 2)

    def test_sessions_can_be_chosen(self):
        self.sessions(self.run_session("m1", stage_stats=[{"stage": "zone_1", "entered": 10, "cleared": 5}]),
                      self.run_session("m2", stage_stats=[{"stage": "zone_2", "entered": 10, "cleared": 5}]))
        code, out = run_cli("calibrate", self.config, "--sessions", "m2", "--json")
        self.assertEqual([s["stage"] for s in json.loads(out)["survival"]["stages"]], ["zone_2"])
        self.assertEqual(run_cli("calibrate", self.config, "--sessions", "m9")[0], 2)
        self.assertEqual(run_cli("calibrate", self.config, "--sessions", "m2,m9")[0], 2)    # 하나라도 없으면 조용히 빼지 않는다


class ConfigProvenance(Workspace):
    def test_simulator_config_can_say_where_the_curve_came_from(self):
        code, out = run_cli("simulate", self.config)
        self.assertIn("가정", out.splitlines()[-1])
        self.edit(CONFIG, lambda d: d.__setitem__("provenance", {"kind": "computed", "source": "reports/calibrate.json"}))
        code, out = run_cli("simulate", self.config, "--json")
        self.assertEqual(json.loads(out)["provenance"]["kind"], "computed")
        code, out = run_cli("simulate", self.config)
        self.assertIn("reports/calibrate.json", out)

    def test_provenance_rules_apply(self):
        self.edit(CONFIG, lambda d: d.__setitem__("provenance", {"kind": "computed"}))
        self.assertEqual(run_cli("simulate", self.config)[0], 2)


class ReviewFindings(Workspace):
    """B5c 코드 검토에서 나온 문제의 회귀 테스트."""

    def test_number_reference_stays_for_ranks_the_fit_does_not_touch(self):
        easy = [{"enemy": "n", "rank": "normal", "hits_to_kill": 100, "time_to_kill": None, "hits_to_die": 40, "time_to_die": None}]
        points = [{"rows": rows(m) + easy, "entered": 400, "cleared": c} for m, c in ((0.2, 200), (0.1, 80), (0.15, 140))]
        f = cal.fit(points, survival(2.0, 0.3), 0.0, 0.0)
        suggested = f["even_margin"]["suggested"]
        self.assertEqual((suggested["normal"], suggested["elite"]), (0.3, 0.3))    # 1로 떨어지지 않는다
        self.assertLess(suggested["boss"], 0.3)

    def test_measured_levels_already_include_level_effects(self):
        self.edit("data/upgrades.json", lambda d: d["upgrades"].insert(0, {"id": "wisdom", "cost": 5, "stats": {"wisdom": 1}}))
        self.edit(CONFIG, lambda d: d.__setitem__("stat_effects", {"wisdom": {"levels": 5}}))
        cfg = sm.attach(sm.load_config(self.config), self.config.parent)
        seen = []
        original = sm.gr.simulate_trials
        sm.gr.simulate_trials = lambda ch, b, lv, *a: seen.append(lv) or original(ch, b, lv, *a)
        self.addCleanup(setattr, sm.gr, "simulate_trials", original)
        sm.stage_rows(cfg, ["wisdom"], {"zone_2": 5, "zone_3": 10})
        self.assertEqual(seen[-1], [6, 5, 10])         # 기록이 없는 단계만 설정 레벨 1 + 5

    def test_nothing_compared_is_not_a_pass(self):
        for f in ("growth", "economy", "meta", "meta_combat"):
            (self.root / f"data/{f}.json").unlink()
        self.assertEqual(run_cli("calibrate", self.root)[0], 2)

    def test_values_that_could_not_be_compared_are_named(self):
        self.sessions(self.run_session(stage_stats=[{"stage": "zone_1", "entered": 10, "cleared": 5, "level": 1, "duration": 300}]))
        self.edit("data/growth.json", lambda d: d["growth"]["level_at"].__setitem__("zone_1", 0))
        r = cal.calibrate(self.root)
        self.assertTrue(any("판 안 성장" in n and "레벨" in n for n in r["notes"]))
        (self.root / "data/economy.json").unlink()
        self.edit("data/growth.json", lambda d: d["growth"]["level_at"].__setitem__("zone_1", 1))
        r = cal.calibrate(self.root)
        self.assertTrue(any("재화 흐름" in n for n in r["notes"]))

    def test_economy_stage_that_failed_is_named(self):
        self.sessions(self.run_session(stage_stats=[{"stage": "zone_1", "entered": 10, "cleared": 5, "level": 1, "duration": 300}]))
        self.edit("data/economy.json", lambda d: d["stages"][0].__setitem__("duration", 0))
        r = cal.calibrate(self.root)
        self.assertTrue(any("zone_1" in n and "재화 흐름" in n for n in r["notes"]))

    def test_slope_is_fitted_without_a_rejected_reference(self):
        truth = synthetic(2.0, 1.0, [0.5, 0.7, 1.0, 1.4, 2.0], n=300, rank="normal")
        hopeless = {"rows": rows(1.0, "boss"), "entered": 20000, "cleared": 1}     # 어떤 기준으로도 닿지 못한다
        f = cal.fit(truth + [hopeless], survival(1.0, 1.0), 0.0, 0.0)
        self.assertFalse(f["even_margin"]["fitted"]["boss"])
        self.assertAlmostEqual(f["slope"]["suggested"], 2.0, delta=0.2)

    def test_edge_passed_on_the_way_is_not_an_edge(self):
        f = cal.fit(synthetic(3.0, 0.2, [0.05, 0.07, 0.1, 0.14]), survival(0.02, 1.0), 0.0, 0.0)
        self.assertTrue(f["even_margin"]["fitted"]["boss"])                         # 처음 slope에서는 끝에 닿아도 나중에 풀린다
        self.assertAlmostEqual(f["even_margin"]["suggested"]["boss"], 0.2, delta=0.03)

    def test_fit_recovers_from_a_start_where_nothing_moves(self):
        # 지금 값에서는 모든 예측이 0에 붙어 가능도가 평평하다. 다른 출발점이 없으면 움직이지 못한다
        f = cal.fit(synthetic(3.0, 0.2, [0.1, 0.15, 0.2, 0.3, 0.5]), survival(20.0, 1000.0), 0.0, 0.0)
        self.assertAlmostEqual(f["slope"]["suggested"], 3.0, delta=0.3)
        self.assertAlmostEqual(f["even_margin"]["suggested"]["boss"], 0.2, delta=0.02)

    def test_mixed_builds_and_concepts_are_named(self):
        self.sessions(self.run_session("m1", build="old", stage_stats=[{"stage": "zone_1", "entered": 10, "cleared": 5, "level": 1}]),
                      self.run_session("m2", build="new", stage_stats=[{"stage": "zone_1", "entered": 10, "cleared": 5, "level": 1}]))
        notes = cal.calibrate(self.root)["notes"]
        self.assertTrue(any("old" in n and "new" in n and "--sessions" in n for n in notes))
        notes = cal.calibrate(self.root, sessions=["m2"])["notes"]
        self.assertFalse(any("--sessions" in n for n in notes))

    def test_report_prints_margins_as_json(self):
        code, out = run_cli("calibrate", self.config)
        line = next(x for x in out.splitlines() if "even_margin" in x)
        self.assertNotIn("{'", line)
        json.loads(line.split(" → ")[1])

    def test_unknown_reference_says_what_is_left_out(self):
        r = pt.validate({"playtests": [session(upgrades=["u9"])]}, {"c": {"approved": False, "hypotheses": []}}, refs=REFS)
        self.assertIn("통과율 비교", r["warnings"][0]["message"])

    def test_data_file_is_not_a_simulator_config(self):
        with self.assertRaisesRegex(sm.ConfigError, "시뮬레이터 설정이 아닙니다"):
            cal.calibrate(self.root / "data/playtests.json")

    def test_config_typo_keeps_its_own_message(self):
        self.edit(CONFIG, lambda d: d.__setitem__("model", "combt"))
        with self.assertRaisesRegex(sm.ConfigError, "'combat'의 오타"):
            cal.calibrate(self.config)

    def test_data_is_scanned_once(self):
        calls = []
        original = cal.datasets.collect
        cal.datasets.collect = lambda t: calls.append(1) or original(t)
        self.addCleanup(setattr, cal.datasets, "collect", original)
        cal.calibrate(self.config)
        self.assertEqual(len(calls), 1)


# ---------- B5c 시험 보고(57~66) ----------
RUNS_CSV = """run,player,upgrades,stage,cleared,level,duration,kills.slime,income.soul
1,self,,zone_1,1,1,280,40,8
1,self,,zone_2,0,5,,,
2,self,,zone_1,0,1,,,
3,self,weapon_1;vitality_1,zone_1,1,1,260,44,10
3,self,weapon_1;vitality_1,zone_2,1,4,350,,12
3,self,weapon_1;vitality_1,zone_3,0,9,,,
4,friend,vitality_1;weapon_1,zone_1,1,1,300,36,6
4,friend,vitality_1;weapon_1,zone_2,0,6,60,,
"""


class NoiseCheck(unittest.TestCase):
    def consistent(self, n=40):
        """지금 곡선(slope 2, 기준 0.2)에서 나올 만한 기록: 예측에서 판 한두 개만 어긋난다."""
        truth = survival(2.0, 0.2)
        out = []
        for m, drift in ((0.1, 1), (0.15, -1), (0.2, 1), (0.3, -1), (0.5, 1)):
            p = cal.predicted(rows(m), truth, 0.0, 0.0)
            out.append({"rows": rows(m), "entered": n, "cleared": min(n, max(0, round(p * n) + drift))})
        return out, truth

    def test_records_that_fit_the_current_values_suggest_nothing_57(self):
        points, truth = self.consistent()
        f = cal.fit(points, truth, 0.0, 0.0)
        self.assertFalse(f["significant"])
        self.assertEqual((f["slope"]["suggested"], f["even_margin"]["suggested"]), (2.0, 0.2))
        self.assertTrue(any("구분되지" in n for n in f["notes"]))

    def test_gain_just_under_the_limit_is_still_noise_57(self):
        truth = survival(2.0, 0.2)
        points = []
        for m, drift in zip((0.1, 0.15, 0.2, 0.3, 0.5), (4, 3, 3, 2, 1)):      # 가능도 차이 4.4, 기준 5.99
            points.append({"rows": rows(m), "entered": 40, "cleared": round(cal.predicted(rows(m), truth, 0.0, 0.0) * 40) + drift})
        self.assertFalse(cal.fit(points, truth, 0.0, 0.0)["significant"])

    def test_clear_difference_is_still_suggested_with_a_range_57(self):
        f = cal.fit(synthetic(3.0, 0.2, [0.1, 0.15, 0.2, 0.3, 0.5], n=400), survival(1.0, 1.0), 0.0, 0.0)
        self.assertTrue(f["significant"])
        low, high = f["slope"]["range"]
        self.assertLess(low, f["slope"]["suggested"])
        self.assertGreater(high, f["slope"]["suggested"])
        low, high = f["even_margin"]["range"]["boss"]
        self.assertLess(low, f["even_margin"]["suggested"]["boss"])
        self.assertGreater(high, f["even_margin"]["suggested"]["boss"])

    def test_fewer_runs_give_a_wider_range_57(self):
        small = cal.fit(synthetic(3.0, 0.2, [0.1, 0.15, 0.2, 0.3, 0.5], n=100), survival(1.0, 1.0), 0.0, 0.0)
        large = cal.fit(synthetic(3.0, 0.2, [0.1, 0.15, 0.2, 0.3, 0.5], n=4000), survival(1.0, 1.0), 0.0, 0.0)
        width = lambda f: f["slope"]["range"][1] - f["slope"]["range"][0]  # noqa: E731
        self.assertGreater(width(small), width(large))


class Groups(unittest.TestCase):
    def grouped(self, **over):
        s = session(groups=[{"upgrades": [], "stage_stats": [{"stage": "a", "entered": 6, "cleared": 3}]},
                            {"upgrades": ["u1"], "growth_build": "blade", "stage_stats": [{"stage": "a", "entered": 4, "cleared": 4}]}])
        s.pop("stage_stats")
        s.pop("upgrades")
        s.update(over)
        return s

    def test_session_can_hold_several_upgrade_states_58(self):
        r = validate(self.grouped())
        self.assertEqual((r["errors"], r["warnings"]), ([], []))

    def test_group_rules_58(self):
        s = self.grouped()
        s["groups"][0]["stage_stats"][0]["cleared"] = 7
        self.assertIn("schema", codes(validate(s)["errors"]))
        self.assertIn("schema", codes(validate(self.grouped(stage_stats=[{"stage": "a", "entered": 1, "cleared": 1}]))["errors"]))
        self.assertIn("schema", codes(validate(self.grouped(upgrades=[]))["errors"]))
        self.assertIn("schema", codes(validate(self.grouped(runs=9))["errors"]))         # 묶음의 판을 합치면 세션 판 수보다 많다
        s = self.grouped()
        s["groups"][1].pop("upgrades")
        self.assertIn("schema", codes(validate(s)["errors"]))
        s = self.grouped()
        s["groups"][0]["stats"] = []
        self.assertIn("schema", codes(validate(s)["errors"]))

    def test_group_references_are_checked_58(self):
        s = self.grouped()
        s["groups"][1]["upgrades"] = ["u9"]
        self.assertEqual(codes(validate(s)["warnings"]), ["unknown_reference"])


class RunLog(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "runs.csv"
        self.path.write_text(RUNS_CSV, encoding="utf-8")

    def test_runs_are_grouped_by_upgrade_state_59(self):
        r = cal.summarize_runs(self.path)
        self.assertEqual(r["runs"], 4)
        self.assertEqual(r["players"], ["self", "friend"])
        self.assertEqual([g["upgrades"] for g in r["groups"]], [[], ["vitality_1", "weapon_1"]])
        first = r["groups"][0]["stage_stats"]
        self.assertEqual([(x["stage"], x["entered"], x["cleared"]) for x in first], [("zone_1", 2, 1), ("zone_2", 1, 0)])

    def test_means_use_the_right_runs_59(self):
        second = cal.summarize_runs(self.path)["groups"][1]["stage_stats"]
        z1, z2 = second[0], second[1]
        self.assertEqual((z1["duration"], z1["kills"], z1["income"]), (280, {"slime": 40}, {"soul": 8}))  # 넘긴 판의 평균
        self.assertEqual(z2["level"], 5)                                                                 # 들어간 판의 평균
        self.assertEqual(z2["duration"], 350)
        self.assertEqual(z1["source"], str(self.path))

    def test_bad_logs_are_refused_59(self):
        for bad, word in (("run,stage\n1,a\n", "cleared"), ("run,stage,cleared\n1,a,maybe\n", "maybe"),
                          ("run,stage,cleared\n1,a,1\n1,a,1\n", "두 번"), ("run,stage,cleared\n1,a,0\n1,b,1\n", "실패"),
                          ("run,stage,cleared,level\n1,a,1,x\n", "level")):
            self.path.write_text(bad, encoding="utf-8")
            with self.subTest(bad), self.assertRaisesRegex(sm.ConfigError, word):
                cal.summarize_runs(self.path)

    def test_command_prints_a_session_fragment_and_writes_nothing_59(self):
        before = sorted(p.name for p in Path(self.tmp.name).iterdir())
        code, out = run_cli("runlog", self.path)
        self.assertEqual(code, 0)
        body = json.loads(out)
        self.assertEqual(body["runs"], 4)
        self.assertEqual(body["logs"], [str(self.path)])
        self.assertEqual(sorted(p.name for p in Path(self.tmp.name).iterdir()), before)
        self.assertEqual(run_cli("runlog", Path(self.tmp.name) / "nope.csv")[0], 2)


class FieldReport(Workspace):
    def base(self, **over):
        return self.run_session(stage_stats=[{"stage": "zone_1", "entered": 20, "cleared": 10, "level": 1}], **over)

    def test_groups_are_used_with_their_own_upgrades_58(self):
        plain = self.run_session("m1", runs=80, upgrades=[], stage_stats=[{"stage": "zone_3", "entered": 80, "cleared": 40, "level": 9}])
        self.sessions(plain)
        none = next(x for x in cal.calibrate(self.config)["survival"]["stages"] if x["stage"] == "zone_3")["predicted"]
        grouped = self.run_session("m1", runs=80, groups=[{"upgrades": ["weapon_1", "weapon_2", "vitality_1"],
                                                           "stage_stats": [{"stage": "zone_3", "entered": 80, "cleared": 40, "level": 9}]}])
        grouped.pop("upgrades")
        self.sessions(grouped)
        r = cal.calibrate(self.config)
        self.assertGreater(next(x for x in r["survival"]["stages"] if x["stage"] == "zone_3")["predicted"], none)

    def test_run_log_fragment_fits_a_session_59(self):
        log = self.root / "runs.csv"
        log.write_text(RUNS_CSV, encoding="utf-8")
        code, out = run_cli("runlog", log)
        body = json.loads(out)
        s = dict(self.run_session(), **body)
        s.pop("upgrades")
        self.sessions(s)
        self.assertEqual(run_cli("check", self.root)[0], 0)
        self.assertEqual(run_cli("calibrate", self.config)[0], 0)

    def test_records_with_broken_run_counts_are_named_60(self):
        self.sessions(self.run_session(stage_stats=[{"stage": "zone_1", "entered": 20, "cleared": 5, "level": 1},
                                                    {"stage": "zone_2", "entered": 15, "cleared": 5, "level": 4}]))
        self.assertTrue(any("m1" in n and "판 수" in n for n in cal.calibrate(self.config)["notes"]))

    def test_config_without_any_usable_record_is_not_a_pass_61(self):
        s = self.base()
        s.pop("upgrades")
        self.sessions(s)
        self.assertEqual(run_cli("calibrate", self.config)[0], 2)
        self.assertEqual(run_cli("calibrate", self.root)[0], 0)      # 폴더로 넘기면 가정값 비교만 한다

    def test_config_without_growth_keeps_sessions_with_a_build_62(self):
        self.sessions(self.base(growth_build="blade"))
        raw = json.loads(self.config.read_text(encoding="utf-8"))
        raw.pop("growth_file")
        raw.pop("build")
        self.config.write_text(json.dumps(raw), encoding="utf-8")
        r = cal.calibrate(self.config)
        self.assertEqual([x["stage"] for x in r["survival"]["stages"]], ["zone_1"])
        self.assertTrue(any("판 안 성장" in n and "반영" in n for n in r["notes"]))

    def test_gate_names_simulator_configs_without_a_calibrated_source_63(self):
        code, out = run_cli("check", self.root, "--fail-on-assumed", "--json")
        self.assertIn("meta_combat.json", " ".join(json.loads(out)["unverified_configs"]))
        code, out = run_cli("check", self.root, "--fail-on-assumed")
        self.assertIn("gate: 시뮬레이터 설정", out)
        for name in ("meta.json", "meta_combat.json"):
            self.edit(f"data/{name}", lambda d: d.__setitem__("provenance", {"kind": "computed", "source": "reports/calibrate.json"}))
        code, out = run_cli("check", self.root, "--fail-on-assumed", "--json")
        self.assertEqual(json.loads(out)["unverified_configs"], [])

    def test_gate_alone_fails_on_an_assumed_config_63(self):
        w = self.root / "only"
        w.mkdir()
        shutil.copy(self.root / "data/upgrades.json", w / "upgrades.json")
        cfg = json.loads((self.root / "data/meta.json").read_text(encoding="utf-8"))
        (w / "meta.json").write_text(json.dumps(cfg), encoding="utf-8")
        u = json.loads((w / "upgrades.json").read_text(encoding="utf-8"))
        for x in u["upgrades"]:
            x["provenance"] = {"kind": "measured", "source": "data/playtests.json#x"}
        (w / "upgrades.json").write_text(json.dumps(u), encoding="utf-8")
        self.assertEqual(run_cli("check", w, "--fail-on-assumed")[0], 1)
        self.assertEqual(run_cli("check", w)[0], 0)                  # 게이트를 켰을 때만 본다

    def test_report_names_fitted_and_unconfirmed_ranks_64(self):
        code, out = run_cli("calibrate", self.config)
        self.assertIn("맞춘 등급: boss", out)
        self.assertIn("기록으로 확인되지 않은 등급", out)
        self.assertIn("normal", out[out.index("기록으로 확인되지 않은 등급"):])

    def test_docs_say_levels_go_first_65(self):
        text = (STUDIO.parent / "playtest-verdict/references/calibration.md").read_text(encoding="utf-8")
        self.assertIn("레벨을 먼저", text)

    def test_tolerance_must_not_be_negative_66(self):
        self.assertEqual(run_cli("calibrate", self.config, "--tolerance", "-1")[0], 2)

    def test_report_summarizes_and_can_show_only_the_differences_66(self):
        self.sessions(self.base(), self.run_session("m2", stage_stats=[{"stage": "zone_2", "entered": 20, "cleared": 10, "level": 50}]))
        code, out = run_cli("calibrate", self.root)
        self.assertIn("가정값 비교: 2건 중 1건", out)
        self.assertIn("단계 zone_1 레벨", out)
        code, out = run_cli("calibrate", self.root, "--off-only")
        self.assertNotIn("단계 zone_1 레벨", out)
        self.assertIn("단계 zone_2 레벨", out)


# ---------- 57~66 수정의 검토 ----------
class RunLogReview(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "runs.csv"

    def refused(self, text, word):
        self.path.write_text(text, encoding="utf-8")
        with self.assertRaisesRegex(sm.ConfigError, word):
            cal.summarize_runs(self.path)
        self.assertEqual(run_cli("runlog", self.path)[0], 2)

    def test_row_with_more_cells_than_columns_is_refused(self):
        self.refused("run,stage,cleared\n1,a,1\n2,a,1,extra\n", "3번째 줄.*칸")

    def test_row_with_fewer_cells_reads_blanks(self):
        self.path.write_text("run,stage,cleared,level\n1,a,1\n", encoding="utf-8")
        self.assertNotIn("level", cal.summarize_runs(self.path)["groups"][0]["stage_stats"][0])

    def test_csv_that_cannot_be_parsed_is_refused(self):
        self.refused("run,stage,cleared\n1," + "a" * 200000 + ",1\n", "읽지 못했습니다")

    def test_numbers_must_be_finite(self):
        for raw in ("inf", "-inf", "nan", "1e999"):
            with self.subTest(raw):
                self.refused(f"run,stage,cleared,level\n1,a,1,{raw}\n", "level")
                self.refused(f"run,stage,cleared,kills.e\n1,a,1,{raw}\n", "kills.e")

    def test_unknown_columns_are_refused_with_a_hint(self):
        self.refused("run,stage,cleared,duraton\n1,a,1,280\n", "duraton.*'duration'의 오타")
        self.refused("run,stage,cleared,kils.slime\n1,a,1,40\n", "kils.slime.*'kills'의 오타")
        self.refused("run,stage,cleared,kills.\n1,a,1,40\n", "kills\\.")
        self.refused("run,stage,cleared,\n1,a,1,40\n", "이름 없는 열")

    def test_columns_marked_as_unused_are_allowed(self):
        self.path.write_text("run,stage,cleared,_seed\n1,a,1,99\n", encoding="utf-8")
        self.assertEqual(cal.summarize_runs(self.path)["runs"], 1)

    def test_repeated_columns_are_refused(self):
        self.refused("run,stage,cleared,level,level\n1,a,1,2,3\n", "겹칩니다.*level")

    def test_line_numbers_count_blank_lines(self):
        self.refused("run,stage,cleared\n1,a,1\n\n\n2,a,maybe\n", "5번째 줄")

    def test_standard_output_is_only_json(self):
        self.path.write_text(RUNS_CSV, encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["runlog", str(self.path)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())["runs"], 4)
        self.assertIn("파일에 쓰지 않았습니다", err.getvalue())


class FiniteNumbers(unittest.TestCase):
    def test_is_number_refuses_what_is_not_finite(self):
        for v in (math.inf, -math.inf, math.nan):
            self.assertFalse(common.is_number(v))
        for v in (0, 1.5, -3, 10 ** 400):
            self.assertTrue(common.is_number(v))
        self.assertFalse(common.is_number(True))

    def test_records_with_infinity_are_schema_errors(self):
        for over in ({"level": math.inf}, {"duration": math.inf}, {"kills": {"e1": math.inf}}, {"income": {"gold": math.inf}}):
            with self.subTest(over):
                s = session(stage_stats=[dict({"stage": "a", "entered": 10, "cleared": 6}, **over)])
                self.assertIn("schema", codes(validate(s)["errors"]))


class GroupShapes(unittest.TestCase):
    def test_stage_that_is_not_text_is_a_schema_error(self):
        for stage in (["a"], {"id": "a"}, 3, None):
            with self.subTest(stage):
                s = session(groups=[{"upgrades": [], "stage_stats": [{"stage": stage, "entered": 1, "cleared": 1}]}])
                s.pop("stage_stats")
                s.pop("upgrades")
                self.assertIn("schema", codes(validate(s)["errors"]))

    def test_broken_stage_does_not_hide_the_other_counts(self):
        s = session(runs=3, groups=[{"upgrades": [], "stage_stats": [{"stage": "a", "entered": 2, "cleared": 1}, {"stage": ["b"], "entered": 1, "cleared": 1}]},
                                    {"upgrades": ["u1"], "stage_stats": [{"stage": "a", "entered": 2, "cleared": 1}]}])
        s.pop("stage_stats")
        s.pop("upgrades")
        self.assertTrue(any("합친 entered" in e["message"] for e in validate(s)["errors"]))


class FitWithoutFiniteMargins(unittest.TestCase):
    def harmless(self, rank="boss"):
        return [{"enemy": "e", "rank": rank, "hits_to_kill": 100, "time_to_kill": None, "hits_to_die": None, "time_to_die": None}]

    def unbeatable(self, rank="boss"):
        return [{"enemy": "e", "rank": rank, "hits_to_kill": None, "time_to_kill": None, "hits_to_die": 100, "time_to_die": None}]

    def test_rank_with_no_finite_margin_keeps_its_value(self):
        for got in (self.harmless(), self.unbeatable()):
            with self.subTest(got):
                f = cal.fit([{"rows": got, "entered": 10, "cleared": 5}], survival(2.0, {"boss": 0.2}), 0.0, 0.0)
                self.assertFalse(f["significant"])
                self.assertEqual(f["even_margin"]["suggested"], {"boss": 0.2})
                self.assertTrue(any("boss" in n and "0이거나 끝이 없" in n for n in f["notes"]))

    def test_other_ranks_are_still_fitted(self):
        points = synthetic(3.0, 0.2, [0.1, 0.15, 0.2, 0.3, 0.5], n=400, rank="normal")
        points.append({"rows": self.harmless(), "entered": 10, "cleared": 5})
        f = cal.fit(points, survival(1.0, {"normal": 1.0, "boss": 0.2}), 0.0, 0.0)
        self.assertTrue(f["even_margin"]["fitted"]["normal"])
        self.assertFalse(f["even_margin"]["fitted"]["boss"])
        self.assertEqual(f["even_margin"]["suggested"]["boss"], 0.2)


class ReviewOfFieldFixes(Workspace):
    def gate(self, *paths):
        code, out = run_cli("check", *(paths or (self.root,)), "--fail-on-assumed", "--json")
        return code, " ".join(json.loads(out)["unverified_configs"])

    def source(self, value):
        for name in ("meta.json", "meta_combat.json"):
            self.edit(f"data/{name}", lambda d: d.__setitem__("provenance", {"kind": "computed", "source": "reports/calibrate.json"}))
        self.edit(CONFIG, lambda d: d.__setitem__("provenance", value))

    def test_gate_uses_the_same_rule_as_the_simulator(self):
        for value in ({"kind": "computed"}, {"kind": "measured", "source": " "}, {"kind": "assumed", "source": "x"}, {"kind": "guess", "source": "x"}, "computed"):
            with self.subTest(value):
                self.source(value)
                self.assertIn("meta_combat.json", self.gate()[1])

    def test_gate_accepts_a_real_source_in_either_language(self):
        self.source({"kind": "측정", "source": "data/playtests.json#m1"})
        self.assertEqual(self.gate()[1], "")

    def test_provenance_kind_of_the_wrong_type_is_reported_not_raised(self):
        self.source({"kind": ["computed"], "source": "x"})
        self.assertIn("meta_combat.json", self.gate()[1])
        self.assertEqual(run_cli("simulate", self.config)[0], 2)
        self.edit("data/upgrades.json", lambda d: d["upgrades"][0].__setitem__("provenance", {"kind": ["computed"]}))
        report = next(x for x in datasets.collect([self.root]) if x["kind"] == "upgrades")["report"]
        self.assertIn("provenance", codes(report["errors"]))

    def test_gate_does_not_pass_a_config_it_cannot_read(self):
        self.source({"kind": "computed", "source": "reports/calibrate.json"})
        good = self.config.read_text(encoding="utf-8")
        for broken in (good[:-1], "\ufeff" + good):
            with self.subTest(broken[:5]):
                self.config.write_text(broken, encoding="utf-8")
                code, listed = self.gate()
                self.assertEqual(code, 1)
                self.assertIn("meta_combat.json", listed)

    def test_gate_leaves_other_broken_json_alone(self):
        self.source({"kind": "computed", "source": "reports/calibrate.json"})
        (self.root / "tsconfig.json").write_text("{ // 도구 설정\n}", encoding="utf-8")
        self.assertEqual(self.gate()[1], "")

    def test_gate_names_a_config_once_however_it_is_reached(self):
        self.assertEqual(len([x for x in datasets.unverified_configs([self.root, Path(os.path.relpath(self.root))]) if x.endswith("meta_combat.json")]), 1)

    def test_broken_counts_are_named_once_per_session(self):
        group = lambda ups: {"upgrades": ups, "stage_stats": [{"stage": "zone_1", "entered": 5, "cleared": 1, "level": 1}, {"stage": "zone_2", "entered": 3, "cleared": 1, "level": 4}]}  # noqa: E731
        s = self.run_session(groups=[group([]), group(["weapon_1"])])
        s.pop("upgrades")
        self.sessions(s)
        self.assertEqual(len([n for n in cal.calibrate(self.config)["notes"] if "이어지지" in n]), 1)

    def test_game_where_nothing_can_be_hurt_reports_no_suggestion(self):
        def harmless(d):
            for e in d["enemies"]:
                e["stats"]["damage"] = 0
        self.edit("data/enemies.json", harmless)
        self.sessions(self.run_session(stage_stats=[{"stage": "zone_1", "entered": 20, "cleared": 10, "level": 1}]))
        code, out = run_cli("calibrate", self.config)
        self.assertEqual(code, 0)
        self.assertIn("생존 곡선 제안 없음", out)

    def test_records_with_infinity_stop_calibrate(self):
        self.sessions(self.run_session(stage_stats=[{"stage": "zone_1", "entered": 20, "cleared": 10, "level": math.inf}]))
        self.assertEqual(run_cli("check", self.root)[0], 1)
        self.assertEqual(run_cli("calibrate", self.config)[0], 2)

    def test_group_with_a_broken_stage_is_reported_as_a_record_error(self):
        s = self.run_session(groups=[{"upgrades": [], "stage_stats": [{"stage": ["zone_1"], "entered": 1, "cleared": 1}]}])
        s.pop("upgrades")
        self.sessions(s)
        self.assertEqual(run_cli("check", self.root)[0], 1)
        with self.assertRaisesRegex(sm.ConfigError, "플레이 기록에 오류"):
            cal.calibrate(self.config)


if __name__ == "__main__":
    unittest.main()
