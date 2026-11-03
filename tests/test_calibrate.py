"""플레이 기록으로 가정값을 보정하는 calibrate(B5c) 테스트: 단계 기록 검사, 가정값 비교, 통과율 비교, 생존 곡선 제안.
표준 라이브러리 unittest만 사용한다."""
import json
import math
import random
import shutil
import tempfile
import unittest
from pathlib import Path

from _studio import SAMPLE, calibrate as cal, meta_sim as sm, playtests as pt, run_cli

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
        self.edit("data/playtests.json", lambda d: d.__setitem__("playtests", [x for x in d["playtests"] if "stage_stats" not in x] + list(new)))

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


if __name__ == "__main__":
    unittest.main()
