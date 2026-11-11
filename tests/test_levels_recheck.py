"""레벨 구성 재검증(이슈 91~106) 테스트: 고친 스킬을 다시 설치해 시험한 뒤 나온 문제를 고친 동작. 표준 라이브러리 unittest만 사용한다."""
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from _studio import ROOT, SAMPLE, STUDIO, claude, common, datasets, levels as lv, meta_sim as sm, run_cli, viewer, level_guide, level_format
from test_levels import BUDGET, both, enc, level, row, run
from test_levels_field import ASSUMED, ECONOMY, ENEMY_CURVE, MEASURED, TIMES, differ, notes, printed, stage, stage_cells
from test_meta_combat import CONFIG, Workspace as MetaWorkspace

HITS = {"s1": {"a": 2, "b": 5}, "s2": {"c": 3}}
ROOMS = {"economy": {"time_unit": "방"}, "stages": ECONOMY["stages"]}


def warning(result, code):
    return next(w for w in result["warnings"] if w["code"] == code)


class Project(unittest.TestCase):
    """표본 프로젝트의 복사본. test_levels.Workspace를 상속하면 그 테스트가 다시 돌아서 따로 둔다."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "game"
        shutil.copytree(SAMPLE, self.root)

    def write(self, rel, text):
        (self.root / rel).write_text(text, encoding="utf-8")

    def edit(self, rel, fn):
        p = self.root / rel
        d = json.loads(p.read_text(encoding="utf-8"))
        fn(d)
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")

    def check(self, *args):
        return run_cli("check", self.root, *args)

    def report(self, kind):
        return next(d for d in datasets.collect([self.root]) if d["kind"] == kind)["report"]


class ConditionalMargins(MetaWorkspace):
    """91: 정예·보스가 단계를 정하는데 등급별 기준을 잡지 않았으면 알린다."""

    def margin_notes(self):
        return "\n".join(sm.run_config(self.config)[1]["margin_notes"])

    def test_boss_judged_with_the_default_is_pointed_out(self):
        self.edit(CONFIG, lambda d: d["survival"].pop("even_margin"))
        text = self.margin_notes()
        self.assertIn("보스", text)
        self.assertIn("even_margin", text)

    def test_rank_left_out_of_the_table_is_pointed_out(self):
        self.edit(CONFIG, lambda d: d["survival"].__setitem__("even_margin", {"normal": 1.0, "elite": 0.4}))
        self.assertIn("보스", self.margin_notes())

    def test_ranks_with_their_own_margin_say_nothing(self):
        self.assertEqual(self.margin_notes(), "")

    def test_boss_inside_the_combat_targets_is_said_so(self):
        self.edit(CONFIG, lambda d: d["survival"].pop("even_margin"))
        self.edit("data/combat.json", lambda d: d["combat"]["targets"].__setitem__("boss", {"hits_to_kill": [1, 100000]}))
        self.assertIn("전투 목표 안에", self.margin_notes())

    def test_boss_outside_the_combat_targets_is_not_excused(self):
        self.edit(CONFIG, lambda d: d["survival"].pop("even_margin"))
        self.edit("data/combat.json", lambda d: d["combat"]["targets"].__setitem__("boss", {"hits_to_kill": [1, 1]}))
        self.assertNotIn("전투 목표 안에", self.margin_notes())

    def test_boss_with_no_targets_is_not_called_inside(self):
        self.edit(CONFIG, lambda d: d["survival"].pop("even_margin"))
        self.edit("data/combat.json", lambda d: d["combat"]["targets"].pop("boss", None))
        self.assertNotIn("전투 목표 안에", self.margin_notes())

    def test_the_stage_kit_decides_the_targets_not_the_kit_without_upgrades(self):
        self.edit(CONFIG, lambda d: d["survival"].pop("even_margin"))
        cfg, r = sm.run_config(self.config)
        row_ = next(x for x in cfg["_combat"]["checked"] if x["rank"] == "boss")
        self.edit("data/combat.json", lambda d: d["combat"]["targets"].__setitem__("boss", {"hits_to_kill": [row_["hits_to_kill"], row_["hits_to_kill"]]}))
        self.assertIn("전투 목표 안에", self.margin_notes())

    def test_it_is_printed_with_the_overview(self):
        self.edit(CONFIG, lambda d: d["survival"].pop("even_margin"))
        code, out = run_cli("simulate", self.config)
        self.assertEqual(code, 0)
        self.assertIn("참고: ", out)
        self.assertIn("even_margin", out)


class BrokenLevelsFile(Project):
    """93: 읽지 못한 levels.json은 건너뛰지 않는다. 건너뛰기는 내용이 있는 다른 형식일 때만 한다."""

    def test_syntax_error_is_a_read_failure(self):
        self.write("data/levels.json", "{oops")
        code, out = self.check()
        self.assertEqual(code, 2)
        self.assertIn("UNREADABLE", out)
        self.assertNotIn("건너뛰었습니다", out)

    def test_values_with_no_content_are_read_failures(self):
        for text in ("[]", "null", '"text"', "3"):
            self.write("data/levels.json", text)
            self.assertEqual(self.check()[0], 2, text)

    def test_a_list_of_game_levels_is_still_skipped(self):
        self.write("data/levels.json", '[{"map": "a.tmx"}]')
        code, out = self.check()
        self.assertEqual(code, 0)
        self.assertIn("건너뛰었습니다", out)

    def test_json_with_comments_is_still_skipped_with_the_right_reason(self):
        self.write("data/levels.json", '{ // 맵 목록\n "world": 1 }')
        code, out = self.check()
        self.assertEqual(code, 0)
        self.assertIn("주석이 있는 JSON", out)

    def test_an_object_with_other_keys_is_still_skipped(self):
        self.write("data/levels.json", '{"maps": []}')
        self.assertEqual(self.check()[0], 0)

    def test_the_viewer_shows_it_as_a_failure(self):
        self.write("data/levels.json", "{oops")
        snap = viewer.snapshot([self.root])
        self.assertEqual(snap["notices"], [])
        self.assertFalse(next(d for d in snap["datasets"] if d["name"] == "levels.json")["ok"])


class TurnBased(unittest.TestCase):
    """95: 공격 속도가 없는 게임은 처치 시간 대신 타수를 낸다. 칸이 비면 이유를 말한다."""

    def setUp(self):
        self.r = run(kill_hits=HITS, economy=ROOMS)

    def test_stage_counts_hits_when_there_is_no_time(self):
        self.assertEqual((stage(self.r)["kill_time"], stage(self.r)["kill_hits"], stage(self.r)["hits_per_unit"]), (None, 15, 0.25))

    def test_encounter_counts_hits_when_there_is_no_time(self):
        self.assertEqual((row(self.r)["kill_time"], row(self.r)["kill_hits"]), (None, 15))

    def test_time_wins_when_there_is_both(self):
        r = run(kill_times=TIMES, kill_hits=HITS, economy=ECONOMY)
        self.assertEqual((stage(r)["kill_time"], stage(r)["kill_hits"], stage(r)["hits_per_unit"]), (16, None, None))
        self.assertEqual((row(r)["kill_time"], row(r)["kill_hits"]), (16, None))

    def test_table_shows_the_unit(self):
        cells = stage_cells(self.r)
        self.assertIn("| 15타 |", cells)
        self.assertIn("| 0.25타/방 |", cells)
        self.assertIn("| 15타 |", lv.table({}, self.r).splitlines()[2])

    def test_check_shows_the_unit(self):
        line = next(x for x in printed(self.r).splitlines() if x.startswith("단계 s1"))
        self.assertIn("단일 대상 처치 타수 15타 / 길이 60방 = 0.25타/방", line)

    def test_partial_hits_are_marked(self):
        r = run(kill_hits={"s1": {"a": 2}, "s2": {"c": 3}}, economy=ROOMS)
        cells = stage_cells(r)
        self.assertIn("10타 이상 (b 제외)", cells)
        self.assertIn("0.17타/방 이상", cells)

    def test_note_says_why_it_is_hits(self):
        self.assertIn("공격 속도가 없어 타수로", notes(self.r))

    def test_no_such_note_with_time(self):
        self.assertNotIn("타수로", notes(run(kill_times=TIMES, kill_hits=HITS, economy=ECONOMY)))

    def test_no_such_note_when_only_some_stages_lack_time(self):
        self.assertNotIn("타수로", notes(run(kill_times={"s1": TIMES["s1"]}, kill_hits={"s2": HITS["s2"]})))

    def test_no_such_note_without_any_combat_values(self):
        self.assertNotIn("타수로", notes(run()))

    def test_length_gap_is_explained(self):
        eco = {"economy": {}, "stages": [{"id": "s1", "kills": {"a": 5, "b": 1}}, {"id": "s2", "kills": {"c": 6}}]}
        self.assertIn("단계 길이(duration)가 없어", notes(run(kill_times=TIMES, economy=eco)))

    def test_unit_gap_is_explained(self):
        self.assertIn("time_unit이 초가 아니라", notes(run(kill_times=TIMES, economy=ROOMS)))

    def test_no_length_note_without_an_economy(self):
        self.assertNotIn("단계 길이", notes(run(kill_times=TIMES)))

    def test_group_size_gap_without_a_curve(self):
        self.assertIn("적 곡선이 없어", notes(run()))

    def test_group_size_gap_with_another_basis(self):
        self.assertIn("구역(zone) 기준이 아니라", notes(run(enemy_curve={**ENEMY_CURVE, "by": "floor"})))

    def test_group_size_gap_without_a_zone(self):
        combat = {"stages": [{"id": "s1"}, {"id": "s2"}]}
        self.assertIn("전투 단계에 zone이 없어", notes(run(combat=combat, enemy_curve=ENEMY_CURVE)))

    def test_nothing_is_said_when_the_values_are_there(self):
        text = notes(run(kill_times=TIMES, economy=ECONOMY, enemy_curve=ENEMY_CURVE))
        for word in ("타수로", "단계 길이", "time_unit", "적 곡선", "zone"):
            self.assertNotIn(word, text)

    def test_no_group_size_note_without_a_budget(self):
        self.assertNotIn("적 곡선", notes(run(budget=None)))


class TurnBasedProject(Project):
    def test_hits_reach_the_project_report(self):
        self.edit("data/combat.json", lambda d: d["combat"]["stats"]["player"].pop("attack_rate"))
        s = self.report("levels")["stages"][0]
        self.assertIsNone(s["kill_time"])
        self.assertIsNotNone(s["kill_hits"])

    def test_the_sample_needs_no_gap_note(self):
        text = "\n".join(self.report("levels")["notes"])
        for word in ("타수로", "단계 길이", "time_unit", "적 곡선"):
            self.assertNotIn(word, text)


class ConditionalEnemies(Project):
    """97: 플레이어 행동으로만 나오는 적의 처방을 메시지가 말한다."""

    def test_level_warning_offers_acknowledged(self):
        self.assertIn("acknowledged", warning(run(both(level("s1", enc(enemies={"a": 5, "b": 1, "c": 1}))), economy=None), "enemy_not_in_stage")["message"])

    def test_warning_with_no_earlier_zone_still_offers_it(self):
        combat = {"stages": [{"id": "s1", "enemies": ["a"]}, {"id": "s2", "zone": 2}]}
        self.assertIn("조건부", warning(run(combat=combat), "enemy_not_in_stage")["message"])

    def test_economy_warning_offers_it_too(self):
        self.edit("data/economy.json", lambda d: d["stages"][0]["kills"].__setitem__("void_herald", 1))
        self.assertIn("조건부", warning(self.report("economy"), "kill_not_in_stage")["message"])


class StagesWithoutLevels(unittest.TestCase):
    """98: 처치 수 대조의 분모는 전투 단계다. 레벨이 없는 단계도 표에 나온다."""

    def test_stage_with_no_level_counts_against_the_total(self):
        text = notes(run([level("s1")], economy=ECONOMY))
        self.assertIn("처치 수 대조: 1/2 단계", text)
        self.assertIn("조우가 없는 단계: s2", text)

    def test_stage_with_a_cut_level_counts_the_same(self):
        self.assertIn("조우가 없는 단계: s2", notes(run([level("s1"), level("s2", status="cut")], economy=ECONOMY)))

    def test_stage_with_no_level_has_a_row(self):
        s = stage(run([level("s1")], economy=ECONOMY), "s2")
        self.assertEqual((s["position"], s["threat"], s["kills"], s["duration"]), (2, None, None, 30))

    def test_row_order_follows_the_stages(self):
        self.assertEqual([s["id"] for s in run([level("s2", enc("e2", {"c": 6}))])["stages"]], ["s1", "s2"])

    def test_cut_stage_has_no_row(self):
        self.assertNotIn("old", [s["id"] for s in run()["stages"]])

    def test_lost_stage_is_named_as_an_error(self):
        text = notes(run(both(second=level("zz", enc("e2", {"c": 6}))), economy=ECONOMY))
        self.assertIn("0/2 단계", text)
        self.assertIn("오류로 못 본 단계: s1, s2", text)
        self.assertNotIn("조우가 없는 단계", text)

    def test_failed_level_is_an_error_not_an_empty_stage(self):
        text = notes(run(both(second=level("s2", enc("e2", {"c": 6}), status="nope")), economy=ECONOMY))
        self.assertIn("오류로 못 본 단계: s2", text)
        self.assertNotIn("조우가 없는 단계", text)

    def test_without_combat_the_levels_are_the_total(self):
        self.assertIn("처치 수 대조: 2/2 단계", notes(run(combat=None, economy=ECONOMY)))


class PartialCounts(unittest.TestCase):
    """99: 빠진 적이나 조우가 있는 값은 완전한 값처럼 내지 않는다."""

    def test_unknown_enemy_gives_no_encounter_time(self):
        r = run(both(level("s1", enc(enemies={"a": 5, "ghost": 2}))), kill_times=TIMES, kill_hits=HITS)
        self.assertEqual((row(r)["kill_time"], row(r)["kill_hits"]), (None, None))

    def test_cut_enemy_is_left_out_without_hiding_the_time(self):
        self.assertEqual(row(run(both(level("s1", enc(enemies={"a": 5, "gone": 2}))), kill_times=TIMES))["kill_time"], 10)

    def test_level_kills_are_marked_when_an_encounter_failed(self):
        r = run(both(level("s1", enc("x", {"a": 5}), enc("y", {"b": 0}))))
        self.assertTrue(r["levels"][0]["kills_partial"])
        self.assertIn("처치 a 5 (일부)", printed(r))

    def test_level_kills_are_marked_when_an_enemy_is_unknown(self):
        self.assertTrue(run(both(level("s1", enc(enemies={"a": 5, "ghost": 2}))))["levels"][0]["kills_partial"])

    def test_whole_level_is_not_marked(self):
        r = run()
        self.assertFalse(r["levels"][0]["kills_partial"])
        self.assertNotIn("(일부)", printed(r))


class KillsAdvice(unittest.TestCase):
    """100: 고칠 쪽을 말하는 규칙. 측정값이 앞서고, 그 밖에는 조우가 처치 수의 원본이다."""

    def economy(self, source, **kills):
        return {"stages": [{"id": "s1", "kills": kills or {"a": 50, "b": 1}, "provenance": source}]}

    def test_both_assumed_follow_the_source_of_truth(self):
        self.assertIn("조우가 처치 수의 원본", differ(run(economy=self.economy(ASSUMED))))

    def test_computed_economy_follows_the_same_rule(self):
        eco = self.economy({"kind": "computed", "source": "x"})
        self.assertIn("조우가 처치 수의 원본", differ(run(economy=eco)))

    def test_both_measured_ask_to_recheck(self):
        self.assertIn("둘 다 측정값", differ(run(both(level("s1", provenance=MEASURED)), economy=self.economy(MEASURED))))

    def test_measured_economy_names_only_the_encounters_to_change(self):
        lvl = level("s1", enc("x", {"a": 3, "b": 1}, provenance=MEASURED), enc("y", {"a": 2}))
        text = differ(run(both(lvl), economy=self.economy(MEASURED)))
        self.assertIn("측정값이 아닌 조우(y)", text)
        self.assertNotIn("(x", text)

    def test_measured_economy_needs_no_names_when_no_encounter_is_measured(self):
        text = differ(run(economy=self.economy(MEASURED)))
        self.assertIn("조우의 횟수를 고칩니다", text)
        self.assertNotIn("측정값이 아닌", text)

    def test_measurement_on_only_part_of_one_side_picks_no_side(self):
        lvl = level("s1", enc("x", {"a": 3, "b": 1}, provenance=MEASURED), enc("y", {"a": 2}))
        text = differ(run(both(lvl), economy=self.economy(ASSUMED)))
        self.assertIn("일부만", text)
        self.assertNotIn("원본", text)

    def test_stage_without_a_source_takes_the_economy_source(self):
        eco = {"economy": {"provenance": MEASURED}, "stages": [{"id": "s1", "kills": {"a": 50, "b": 1}}]}
        self.assertIn("재화 흐름 측정", differ(run(economy=eco)))

    def test_stage_source_wins_over_the_economy_source(self):
        eco = {"economy": {"provenance": MEASURED}, "stages": [{"id": "s1", "kills": {"a": 50, "b": 1}, "provenance": ASSUMED}]}
        self.assertIn("재화 흐름 가정", differ(run(economy=eco)))


class FreeOrder(unittest.TestCase):
    """102: 곡선도 함께 내려간 단계는 의도를 이미 적은 것이다."""

    def run_with(self, values):
        return run([level("s1", enc("big", {"a": 5, "b": 1})), level("s2", enc("small", {"c": 1}))],
                   budget={**BUDGET, "curve": {"growth": "table", "values": values}})

    def test_falling_curve_makes_no_drop_note(self):
        self.assertNotIn("줄었습니다", notes(self.run_with({"s1": 80, "s2": 20})))

    def test_rising_curve_keeps_the_drop_note(self):
        self.assertIn("줄었습니다", notes(self.run_with({"s1": 80, "s2": 120})))

    def test_flat_curve_keeps_the_drop_note(self):
        self.assertIn("줄었습니다", notes(self.run_with({"s1": 80, "s2": 80})))

    def test_curve_value_is_in_the_stage_row(self):
        self.assertEqual(stage(self.run_with({"s1": 80, "s2": 20}), "s2")["curve"], 20)


class CurvePoints(unittest.TestCase):
    """103: 남는 곡선 값의 오타 추정과 확인."""

    def table(self, **values):
        return {**BUDGET, "curve": {"growth": "table", "values": {"s1": 80, "s2": 120, **values}}}

    def test_stage_that_already_has_a_value_is_not_guessed(self):
        self.assertNotIn("오타", warning(run(budget=self.table(s3=160)), "curve_unused_point")["message"])

    def test_stage_with_no_value_is_guessed(self):
        budget = {**BUDGET, "curve": {"growth": "table", "values": {"s1": 80, "s22": 120}}}
        self.assertIn("'s2'의 오타", warning(run(budget=budget), "curve_unused_point")["message"])

    def test_cut_stage_is_not_guessed(self):
        budget = self.table(olde=160)
        self.assertNotIn("오타", warning(run(budget=budget), "curve_unused_point")["message"])

    def test_it_can_be_acknowledged_in_any_level(self):
        levels = both(second=level("s2", enc("e2", {"c": 6}), acknowledged={"curve_unused_point": {"s3": "다음 단계를 미리 적었다"}}))
        data = {"levels": levels, "threat_budget": self.table(s3=160)}
        r = run(levels, budget=self.table(s3=160))
        self.assertEqual((warning(r, "curve_unused_point")["owner"], warning(r, "curve_unused_point")["part"]), ("s2", "s3"))
        common.apply_acknowledged("levels", data, r)
        self.assertEqual([w["code"] for w in r["warnings"]], [])
        self.assertEqual([w["code"] for w in r["acknowledged"]], ["curve_unused_point"])

    def test_no_active_level_still_warns(self):
        r = run([level("s1", status="cut")], budget=self.table(s3=160))
        self.assertNotIn("owner", warning(r, "curve_unused_point"))


class StageMessages(Project):
    """104: 재화 흐름과 판 안 성장의 unknown_stage도 레벨과 같은 규칙으로 안내한다."""

    def error(self, kind):
        return next(e for e in self.report(kind)["errors"] if e["code"] == "unknown_stage")["message"]

    def test_economy_guesses_the_stage_with_no_link(self):
        self.edit("data/combat.json", lambda d: d["stages"][2].__setitem__("id", "zone_mid"))
        text = self.error("economy")
        self.assertIn("없는 단계입니다: zone_3.", text)
        self.assertIn("'zone_mid'의 오타", text)
        self.assertIn("재화 흐름과 이어지지 않은 전투 단계: zone_mid", text)

    def test_economy_does_not_call_a_linked_stage_a_typo(self):
        self.edit("data/economy.json", lambda d: d["stages"].append({"id": "extra", "combat_stage": "zone_9", "duration": 10}))
        text = self.error("economy")
        self.assertNotIn("오타", text)
        self.assertIn("이름이 비슷한 단계: zone_", text)

    def test_growth_guesses_the_stage_with_no_level(self):
        self.edit("data/combat.json", lambda d: d["stages"][2].__setitem__("id", "zone_mid"))
        text = self.error("growth")
        self.assertIn("없는 단계입니다: zone_3.", text)
        self.assertIn("'zone_mid'의 오타", text)
        self.assertIn("level_at이 없는 전투 단계: zone_mid", text)

    def test_growth_does_not_call_a_stage_with_a_level_a_typo(self):
        self.edit("data/growth.json", lambda d: d["growth"]["level_at"].__setitem__("zone_9", 9))
        text = self.error("growth")
        self.assertNotIn("오타", text)
        self.assertIn("이름이 비슷한 단계: zone_", text)


class LinkedKills(unittest.TestCase):
    """104: 재화 흐름 단계를 그 단계의 id로 말한다."""

    def test_unlinked_kills_name_the_economy_stage(self):
        r = run(economy={"stages": [{"id": "part_1", "combat_stage": "mid", "kills": {"a": 9}}]})
        w = warning(r, "kills_not_linked")
        self.assertEqual((w["where"], w["part"]), ("part_1", "part_1"))
        self.assertIn("재화 흐름 단계 part_1의", w["message"])

    def test_each_stage_of_a_broken_link_gets_its_own_warning(self):
        r = run(economy={"stages": [{"id": "p1", "combat_stage": "mid", "kills": {"a": 9}}, {"id": "p2", "combat_stage": "mid", "kills": {"a": 9}}]})
        self.assertEqual([w["part"] for w in r["warnings"] if w["code"] == "kills_not_linked"], ["p1", "p2"])

    def test_stage_with_a_broken_link_is_not_called_silent(self):
        eco = {"stages": [{"id": "s1", "kills": {"a": 5, "b": 1}}, {"id": "s2", "combat_stage": "s_2x", "kills": {"c": 6}}]}
        text = notes(run(economy=eco))
        self.assertIn("오류로 못 본 단계: s2", text)
        self.assertNotIn("재화 흐름에 처치 수가 없는 단계", text)

    def test_broken_link_counts_as_an_error_even_with_no_level(self):
        eco = {"stages": [{"id": "s1", "kills": {"a": 5, "b": 1}}, {"id": "s2", "combat_stage": "s_2x", "kills": {"c": 6}}]}
        text = notes(run([level("s1")], economy=eco))
        self.assertIn("오류로 못 본 단계: s2", text)
        self.assertNotIn("조우가 없는 단계", text)

    def test_without_combat_a_link_cannot_be_called_broken(self):
        eco = {"stages": [{"id": "s1", "combat_stage": "elsewhere", "kills": {"a": 5, "b": 1}}]}
        text = notes(run([level("s1")], combat=None, economy=eco))
        self.assertIn("재화 흐름에 처치 수가 없는 단계: s1", text)
        self.assertNotIn("오류로", text)


class Particles(Project):
    """105: 숫자와 id로 끝나는 말의 조사."""

    def test_budget_number_takes_the_right_particle(self):
        self.edit("data/budget.json", lambda d: d["budget"].__setitem__("tolerance", 0))
        self.edit("data/enemies.json", lambda d: d["enemies"][0].update(id=d["enemies"][0]["id"], stats={"max_hp": 7}))
        self.assertNotRegex(" ".join(w["message"] for w in self.report("budget")["warnings"]), r"[013678]가 ")

    def test_purchase_id_takes_the_right_particle(self):
        self.assertEqual(common.josa("ripen_weapon_3", "을를"), "ripen_weapon_3을")
        self.edit("data/economy.json", lambda d: d["purchases"][0].update(id="buy_3", target=[99999, 100000]))
        text = next(w for w in self.report("economy")["warnings"] if w["code"] == "target_out_of_range")["message"]
        self.assertTrue(text.startswith("buy_3을 "), text)


class DropsAcrossGaps(unittest.TestCase):
    """빈 단계 행이 앞 단계 비교를 끊지 않는다."""

    COMBAT = {"stages": [{"id": "s1", "zone": 1}, {"id": "s2", "zone": 2}, {"id": "s3", "zone": 3}]}

    def test_stage_with_no_level_does_not_hide_a_drop(self):
        r = run([level("s1", enc("big", {"a": 5, "b": 1})), level("s3", enc("small", {"c": 1}))], combat=self.COMBAT)
        self.assertIn("단계 s3의 위협도 합이 앞 단계 s1보다 줄었습니다", notes(r))

    def test_failed_stage_does_not_hide_a_drop(self):
        levels = [level("s1", enc("big", {"a": 5, "b": 1})), level("s2", enc("bad", {"c": 0})), level("s3", enc("small", {"c": 1}))]
        self.assertIn("앞 단계 s1보다 줄었습니다", notes(run(levels, combat=self.COMBAT)))


class HookNotices(Project):
    """편집 훅도 건너뛴 파일을 알린다. 건드리지 않은 파일로 다른 편집을 시끄럽게 하지는 않는다."""

    def edit_hook(self, rel):
        code, out, _ = claude.post_edit(json.dumps({"tool_input": {"file_path": str(self.root / rel)}}), self.root)
        self.assertEqual(code, 0)
        return json.loads(out)["hookSpecificOutput"]["additionalContext"] if out else ""

    def test_editing_the_skipped_file_says_so(self):
        self.write("data/levels.json", '{"level": []}')
        self.assertIn("건너뛰었습니다", self.edit_hook("data/levels.json"))

    def test_editing_another_file_says_nothing_about_it(self):
        self.write("data/levels.json", '{"level": []}')
        self.assertNotIn("건너뛰었습니다", self.edit_hook("data/items.json"))


class EconomyAcknowledgement(Project):
    """kill_not_in_stage는 적마다 확인한다."""

    def setUp(self):
        super().setUp()
        self.edit("data/economy.json", lambda d: d["stages"][0]["kills"].update(void_herald=1, void_spawn=1))

    def acknowledge(self, reason):
        self.edit("data/economy.json", lambda d: d["stages"][0].__setitem__("acknowledged", {"kill_not_in_stage": reason}))
        r = self.report("economy")
        return sorted(w["part"] for w in r["warnings"] if w["code"] == "kill_not_in_stage"), sorted(w["part"] for w in r["acknowledged"] if w["code"] == "kill_not_in_stage")

    def test_each_enemy_gets_its_own_warning(self):
        r = self.report("economy")
        self.assertEqual(sorted(w["part"] for w in r["warnings"] if w["code"] == "kill_not_in_stage"), ["void_herald", "void_spawn"])

    def test_one_enemy_can_be_acknowledged(self):
        self.assertEqual(self.acknowledge({"void_herald": "조건부"}), (["void_spawn"], ["void_herald"]))

    def test_a_plain_reason_covers_the_stage(self):
        self.assertEqual(self.acknowledge("조건부"), ([], ["void_herald", "void_spawn"]))


class CommentsInStrings(Project):
    """문자열 안의 //는 주석이 아니다."""

    def test_broken_file_with_a_url_is_a_read_failure(self):
        self.write("data/levels.json", '{"levelz": [], "note": "https://example.com"')
        self.assertEqual(self.check()[0], 2)

    def test_real_comment_next_to_a_url_is_still_skipped(self):
        self.write("data/levels.json", '{ // 맵 목록\n "url": "https://example.com" }')
        self.assertEqual(self.check()[0], 0)

    def test_block_comment_is_still_skipped(self):
        self.write("data/levels.json", '{ /* 맵 */ "world": 1 }')
        self.assertEqual(self.check()[0], 0)

    def test_escaped_quote_does_not_end_the_string(self):
        self.write("data/levels.json", '{"note": "a\\"b https://x.y"')
        self.assertEqual(self.check()[0], 2)


class LaterDeciders(MetaWorkspace):
    """강화·성장 뒤에 단계를 정하는 적도 본다."""

    def test_rank_that_decides_only_later_is_pointed_out(self):
        early, late = {"enemy": "a", "rank": "normal"}, {"enemy": "b", "rank": "boss"}
        self.assertIn("s1: b", "\n".join(sm.margin_notes(1.0, [("s1", early), ("s1", late)], {"settings": {"targets": {}}, "stages": {}}, [])))

    def test_the_same_enemy_is_named_once(self):
        boss = {"enemy": "b", "rank": "boss"}
        self.assertEqual("\n".join(sm.margin_notes(1.0, [("s1", boss), ("s1", boss)], {"settings": {"targets": {}}, "stages": {}}, [])).count("s1: b"), 1)

    def test_every_case_of_a_stage_is_looked_at(self):
        with mock.patch.object(sm, "margin_notes", wraps=sm.margin_notes) as notes_call:
            _, r = sm.run_config(self.config)
        self.assertEqual(len(notes_call.call_args.args[1]), 3 * len(r["survival_by_stage"]))

    def test_policy_comparison_shows_the_note(self):
        self.edit(CONFIG, lambda d: d["survival"].pop("even_margin"))
        code, out = run_cli("simulate", self.config, "--compare-policies")
        self.assertEqual(code, 0)
        self.assertEqual(out.count("even_margin을 등급별로"), 1)


class TimeUnits(unittest.TestCase):
    def test_unit_is_read_without_case(self):
        for unit in ("Sec", "SECONDS", " s "):
            eco = {"economy": {"time_unit": unit}, "stages": ECONOMY["stages"]}
            r = run(kill_times=TIMES, economy=eco)
            self.assertEqual(stage(r)["kill_ratio"], 0.27, unit)
            self.assertNotIn("time_unit", notes(r))


class HitHeadings(unittest.TestCase):
    """타수만 있는 표는 열 이름도 타수다."""

    def test_table_names_hits_when_there_is_no_time(self):
        text = lv.table({}, run(kill_hits=HITS, economy=ROOMS))
        self.assertIn("| 처치 타수 |", text)
        self.assertIn("| 단일 대상 처치 타수 |", text)
        self.assertIn("| 타수 ÷ 길이 |", text)
        self.assertNotIn("처치 시간", text)

    def test_table_keeps_time_when_there_is_time(self):
        text = lv.table({}, run(kill_times=TIMES, kill_hits=HITS, economy=ECONOMY))
        self.assertIn("| 단일 대상 처치 시간(초) |", text)
        self.assertNotIn("처치 타수", text)

    def test_table_keeps_time_with_no_values(self):
        self.assertIn("| 처치 시간(초) |", lv.table({}, run()))

    def test_mixed_stages_keep_time_with_units_in_the_cells(self):
        r = run(kill_times={"s1": TIMES["s1"]}, kill_hits={"s2": HITS["s2"]})
        self.assertEqual(r["kill_measure"], "time")
        self.assertIn("| 18타 |", stage_cells(r, "s2"))

    def test_report_says_which_it_is(self):
        self.assertEqual(run(kill_hits=HITS)["kill_measure"], "hits")


class ViewerScript(unittest.TestCase):
    """같은 이름의 상수 하나로 뷰어 전체가 멈춘다. 파이썬 테스트로는 보이지 않으므로 node가 있으면 문법을 확인한다."""

    @unittest.skipUnless(shutil.which("node"), "node가 없습니다")
    def test_the_page_script_parses(self):
        text = (STUDIO / "assets/viewer.html").read_text(encoding="utf-8")
        scripts = re.findall(r"<script[^>]*>(.*?)</script>", text, re.S)
        self.assertTrue(scripts)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "viewer.js"
            path.write_text("\n".join(scripts), encoding="utf-8")
            result = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


class Docs(unittest.TestCase):
    def setUp(self):
        self.skill = level_guide()   # 할 일은 SKILL.md와 game-shapes.md에 있다
        self.fmt = level_format()
        self.economy = (ROOT / "skills/economy-flow/SKILL.md").read_text(encoding="utf-8")
        self.page = (STUDIO / "assets/viewer.html").read_text(encoding="utf-8")
        self.levels_page = self.page[self.page.index("function renderLevels"):self.page.index("function renderPlaytests")]

    def test_occasional_elites_are_split_not_repeated(self):  # 92
        self.assertNotIn("가끔 얹히는", self.skill)
        self.assertIn("일부 횟수에만", self.skill)
        self.assertIn("일부 횟수에만", self.fmt)

    def test_grades_and_the_economy_route_meet(self):  # 94
        self.assertIn("대표 등급", self.skill)   # 스테이지 선택형은 game-shapes.md
        self.assertIn("대표 등급", self.economy)

    def test_turn_based_path_is_written(self):  # 95
        self.assertIn("턴제", self.skill)
        self.assertIn("구역 평균", self.skill)
        self.assertIn("kill_hits", self.levels_page)

    def test_curve_source_rule_is_written(self):  # 96
        self.assertIn("`computed`", self.fmt)

    def test_conditional_enemies_have_a_rule(self):  # 97
        self.assertIn("플레이어 행동으로만", self.skill)

    def test_mixed_source_is_explained(self):  # 100
        self.assertIn("섞임", self.fmt)

    def test_repeat_of_a_time_span_has_a_rule(self):  # 101
        self.assertIn("다시 차는 주기", self.skill)
        self.assertIn("다시 차는 주기", self.fmt)

    def test_free_order_games_are_told_what_not_to_read(self):  # 102
        self.assertIn("순서가 자유로운", self.skill)

    def test_acknowledging_unused_curve_points_is_documented(self):  # 103
        self.assertIn('{"curve_unused_point"', self.fmt)

    def test_run_total_is_described_as_it_appears(self):  # 106
        self.assertIn("판 전체 위협도 줄이 없으면", self.skill)

    def test_partial_level_kills_show_in_the_viewer(self):  # 99
        self.assertIn("kills_partial", self.levels_page)

    def test_viewer_names_hits_in_its_headings(self):
        self.assertIn("kill_measure", self.levels_page)

    def test_acknowledging_economy_kills_by_enemy_is_documented(self):
        fmt = (ROOT / "skills/economy-flow/references/economy-format.md").read_text(encoding="utf-8")
        self.assertIn('{"kill_not_in_stage": {적 id: 이유}}', fmt)

    def test_read_failures_are_documented(self):  # 93
        self.assertIn("문법이 깨진", self.fmt)


if __name__ == "__main__":
    unittest.main()
