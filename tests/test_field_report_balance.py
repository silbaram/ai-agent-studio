"""밸런스 스킬(B1~B5a)을 게임 프로젝트에 설치해 써 본 시험 보고(2026-11-03)에서 나온 문제의 회귀 테스트.

각 테스트 이름 끝의 번호는 시험 보고의 문제 번호다. 표준 라이브러리 unittest만 사용한다.
"""
import copy
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from _studio import ROOT, SAMPLE, STUDIO, budget as bg, cli, combat as cb, common, crafting as cr, economy as ec, enemies as ve
from _studio import growth as gr, items as vi, meta_sim, run_cli
import test_budget as tb
import test_combat as tc
import test_crafting as tcr
import test_economy as te
import test_growth as tg
import test_meta_combat as tmc


def codes(entries):
    return [e["code"] for e in entries]


def evalidate(d, **kw):
    """재화 흐름 검사에 전투 계산·메타 설정까지 넘긴다(test_economy.validate는 그 둘을 넘기지 않는다)."""
    refs = dict(enemies=te.ENEMIES, items=te.ITEMS, drop_tables=te.DROPS, upgrades=te.UPGRADES, crafting=te.CRAFTING)
    refs.update(kw)
    return ec.validate(d, **refs)


def sample_copy(test):
    tmp = tempfile.TemporaryDirectory()
    test.addCleanup(tmp.cleanup)
    root = Path(tmp.name) / "game"
    shutil.copytree(SAMPLE, root)
    return root


# ---------- A. 조용히 통과하거나 틀린 결과 ----------
class CombatRoles(unittest.TestCase):
    def test_role_stat_name_typo_is_warned_26(self):
        d = tc.data()
        d["combat"]["stats"]["player"]["attack_rate"] = "attack_sped"
        d["combat"]["stats"]["enemy"]["defense"] = "armr"
        r = tc.validate(d)
        w = {x["where"]: x["message"] for x in r["warnings"] if x["code"] == "stat_not_found"}
        self.assertEqual(sorted(w), ["combat.stats.enemy.defense", "combat.stats.player.attack_rate"])
        self.assertIn("'attack_speed'의 오타", w["combat.stats.player.attack_rate"])
        self.assertIn("'armor'의 오타", w["combat.stats.enemy.defense"])

    def test_role_without_any_value_is_listed_not_warned_26(self):
        r = tc.validate(tc.data())   # 치명 확률·적 공격 속도는 연결만 하고 값이 있는 데이터가 없다
        self.assertEqual(r["warnings"], [])
        self.assertEqual(r["empty_roles"], {"player": ["crit_chance"], "enemy": ["attack_rate"]})

    def test_stats_no_role_uses_are_listed_26(self):
        st = tc.stage()
        st["player"]["base"]["luck"] = 3
        r = tc.validate(tc.data(stages=[st]))
        self.assertEqual(r["unmapped_stats"]["player"], ["luck"])


class CombatZeroDamage(unittest.TestCase):
    def test_zero_damage_does_not_blame_attack_rate_29(self):
        d = tc.data(defense={"form": "flat", "min_damage": 0}, stages=[tc.stage(enemies=["golem"])],
                    targets={"elite": {"hits_to_kill": [1, 50]}})
        self.assertEqual(codes(tc.validate(d)["warnings"]), ["zero_damage"])

    def test_enemy_that_cannot_hurt_the_player_is_warned_29(self):
        st = tc.stage()
        st["player"]["base"]["armor"] = 50
        d = tc.data(defense={"form": "flat", "min_damage": 0}, stages=[st], targets={"normal": {"hits_to_die": [3, None]}})
        r = tc.validate(d)
        self.assertEqual(codes(r["warnings"]), ["zero_damage"])
        self.assertIn("slime", r["warnings"][0]["message"])


class RowAcknowledgement(unittest.TestCase):
    def setUp(self):
        self.targets = {"normal": {"hits_to_kill": [5, 9]}, "elite": {"hits_to_kill": [1, 2]}}

    def test_acknowledgement_can_name_one_enemy_30(self):
        st = tc.stage(enemies=["slime", "golem"], acknowledged={"target_out_of_range": {"slime": "일부러 약하게"}})
        d = tc.data(stages=[st], targets=self.targets)
        r = tc.validate(d)
        common.apply_acknowledged("combat", d, r)
        self.assertEqual([w["where"] for w in r["warnings"]], ["s1.golem"])
        self.assertEqual([(a["where"], a["reason"]) for a in r["acknowledged"]], [("s1.slime", "일부러 약하게")])

    def test_enemy_acknowledgement_needs_reasons_30(self):
        st = tc.stage(acknowledged={"target_out_of_range": {"slime": " "}})
        d = tc.data(stages=[st], targets=self.targets)
        r = tc.validate(d)
        common.apply_acknowledged("combat", d, r)
        self.assertIn("schema", codes(r["errors"]))


class NothingComputed(unittest.TestCase):
    def test_empty_combat_is_incomplete_28(self):
        r = tc.validate(tc.data(stages=[]))
        self.assertEqual((r["unchecked"], r["unchecked_kinds"]), (1, ["nothing"]))

    def test_growth_with_everything_cut_is_incomplete_not_a_warning_28(self):
        r = tg.validate(tg.data(builds=[{"id": "blade", "priority": ["sharpen"], "status": "cut"}]))
        self.assertEqual(r["warnings"], [])
        self.assertEqual((r["unchecked"], r["unchecked_kinds"]), (1, ["nothing"]))

    def test_empty_economy_is_incomplete_28(self):
        r = te.validate(te.base(stages=[]))
        self.assertEqual((r["unchecked"], r["unchecked_kinds"]), (1, ["nothing"]))

    def test_crafting_value_check_without_budget_is_incomplete_28(self):
        recipes = [{"id": "r1", "inputs": [{"item": "a1", "count": 2}], "output": {"item": "b1"}}]
        r = tcr.validate(tcr.data(recipes=recipes), budget=None)
        self.assertIn("value", r["unchecked_kinds"])
        self.assertNotIn("value", tcr.validate(tcr.data(), budget=None)["unchecked_kinds"])   # 비교할 강화·합성이 없으면 세지 않는다
        self.assertGreaterEqual(r["unchecked"], 1)

    def test_crafting_value_check_can_be_turned_off_28(self):
        r = tcr.validate(tcr.data(crafting={"value_check": False}), budget=None)
        self.assertEqual((r["unchecked"], r["value_skipped"]), (0, "disabled"))
        self.assertIn("schema", codes(tcr.validate(tcr.data(crafting={"value_check": "no"}))["errors"]))

    def test_check_line_is_incomplete_when_nothing_was_computed_28(self):
        root = sample_copy(self)
        g = json.loads((root / "data/growth.json").read_text(encoding="utf-8"))
        for b in g["builds"]:
            b["status"] = "cut"
        (root / "data/growth.json").write_text(json.dumps(g), encoding="utf-8")
        code, out = run_cli("check", root)
        self.assertIn("→ INCOMPLETE", out)


class GrowthLevels(unittest.TestCase):
    def test_active_stage_missing_from_level_at_is_warned_31(self):
        r = tg.validate(tg.data(level_at={"s1": 4}))
        self.assertEqual(codes(r["warnings"]), ["level_missing"])
        self.assertIn("s2", r["warnings"][0]["message"])

    def test_null_level_leaves_a_stage_out_on_purpose_31(self):
        r = tg.validate(tg.data(level_at={"s1": 4, "s2": None}))
        self.assertEqual(r["warnings"], [])
        self.assertEqual(list(r["builds"]["blade"]["stages"]), ["s1"])

    def test_build_can_have_its_own_levels_32(self):
        builds = [{"id": "blade", "priority": ["sharpen", "vigor"]},
                  {"id": "fast", "priority": ["sharpen", "vigor"], "level_at": {"s1": 6}}]
        r = tg.validate(tg.data(builds=builds))
        self.assertEqual(tg.stage(r, "fast", "s1")["level"], 6)
        self.assertEqual(tg.stage(r, "fast", "s1")["picks"], {"sharpen": 2, "vigor": 3})
        bad = [{"id": "b", "priority": ["vigor"], "level_at": {"nope": 2}}]
        self.assertIn("unknown_stage", codes(tg.validate(tg.data(builds=bad))["errors"]))


class OffCombatBuilds(unittest.TestCase):
    def builds(self, ack):
        magnet = {"id": "magnet", "stats": {"pickup": 30}}
        if ack:
            magnet["acknowledged"] = {"stat_not_in_combat": "줍기 반경. 전투 밖 효과"}
        builds = [{"id": "blade", "priority": ["sharpen", "vigor"]}, {"id": "harvester", "priority": ["magnet", "vigor"]}]
        return tg.validate(tg.data(choices=tg.CHOICES + [magnet], builds=builds))

    def test_acknowledged_off_combat_build_is_not_called_pointless_32(self):
        r = self.builds(ack=True)
        self.assertNotIn("build_dominated", codes(r["warnings"]))
        self.assertEqual([x["build"] for x in r["combat_only_dominated"]], ["harvester"])

    def test_unacknowledged_off_combat_picks_are_named_32(self):
        r = self.builds(ack=False)
        w = next(x for x in r["warnings"] if x["code"] == "build_dominated")
        self.assertIn("전투 밖", w["message"])
        self.assertIn("magnet", w["message"])


class EconomyBlockedCurrency(unittest.TestCase):
    def test_unchecked_purchase_hides_leftover_of_its_currency_33(self):
        d = te.base(purchases=[te.buy("p1", enhance="plus", level=1), te.buy("p2", amount=10, currency="gold")], leftover_max=0.1)
        r = te.validate(d, crafting=None)
        self.assertNotIn("currency_piles_up", codes(r["warnings"]))
        self.assertNotIn("gold", r["leftover"])
        p2 = next(p for p in r["purchases"] if p["id"] == "p2")
        self.assertEqual((p2["at"], p2["blocked"]), (None, "p1"))

    def test_price_currency_typo_names_the_currency_and_keeps_the_rest_40(self):
        d = te.base(prices={"items": "gold", "upgrades": "souls"}, purchases=[te.buy("x", amount=50, currency="gold"), te.buy("u", upgrade="w1")])
        r = te.validate(d)
        self.assertEqual([(e["code"], e["where"]) for e in r["errors"]], [("schema", "economy.prices.upgrades")])
        self.assertIn("'soul'의 오타", r["errors"][0]["message"])
        self.assertEqual(len(r["stages"]), 2)
        self.assertIsNotNone(next(p for p in r["purchases"] if p["id"] == "x")["at"])

    def test_purchase_dropped_for_an_error_does_not_cascade_41(self):
        ups = {"w1": {"id": "w1", "cost": 25}, "w2": {"id": "w2", "cost": 10, "requires": ["w1"]}}
        bad = {"id": "a", "price": {"upgrade": "w1"}, "after": "s1"}       # 판 사이 재화에 after → 형식 오류
        d = te.base(purchases=[bad, dict(te.buy("b", upgrade="w2"), target=[1, 1])])
        d["stages"][0]["income"]["soul"] = 5
        r = te.validate(d, upgrades=ups)
        self.assertEqual(codes(r["errors"]), ["schema"])
        self.assertEqual(r["warnings"], [])                                 # requirement_missing·목표 이탈 없음
        b = next(p for p in r["purchases"] if p["id"] == "b")
        self.assertEqual((b["runs"], b["blocked"]), (None, "a"))


class SuggestionsUnavailable(unittest.TestCase):
    def test_stage_left_out_of_suggestions_is_named_44(self):
        combat = tc.data(stages=[tc.stage(), tc.stage("s2", player={"base": {"max_hp": 100, "attack": 10}, "items": ["nope"]})])
        s = cb.marginal_costs(combat, items=tc.ITEMS, upgrades=tc.UPGRADES, enemies=tc.ENEMIES)
        self.assertIn("s1", s["player"])
        self.assertEqual(list(s["unavailable"]), ["s2"])

    def test_broken_combat_settings_are_named_44(self):
        combat = tc.data(defense={"form": "ration"})
        s = cb.marginal_costs(combat, items=tc.ITEMS, upgrades=tc.UPGRADES, enemies=tc.ENEMIES)
        self.assertEqual(list(s["unavailable"]), ["combat"])
        r = tb.validate(suggestions=s)
        self.assertEqual(list(r["suggestions_missing"]), ["combat"])

    def test_check_prints_the_missing_suggestions_44(self):
        root = sample_copy(self)
        c = json.loads((root / "data/combat.json").read_text(encoding="utf-8"))
        c["combat"]["defense"]["form"] = "ration"
        (root / "data/combat.json").write_text(json.dumps(c), encoding="utf-8")
        code, out = run_cli("check", root)
        self.assertIn("원가 제안 미확인", out)


class UniqueEffect(unittest.TestCase):
    def item(self, flag):
        return {"items": [{"id": "x", "slot": "weapon", "tier": 1, "unique_effect": flag, "stats": {"attack": 1}}]}

    def test_unique_effect_must_be_a_boolean_27(self):
        self.assertIn("schema", codes(vi.validate(self.item("false"))["errors"]))
        self.assertEqual(vi.validate(self.item(False))["errors"], [])

    def test_draft_set_reads_json_literals_27(self):
        root = sample_copy(self)
        code, out = run_cli("draft", root, "--archetype", "blade", "--at", "2", "--id", "new_blade",
                            "--set", "unique_effect=true", "--set", "name=null")
        self.assertEqual(code, 0)
        entry = json.loads(out[out.index("{"):])
        self.assertIs(entry["unique_effect"], True)
        self.assertIsNone(entry["name"])


# ---------- B. 빠진 검사 ----------
class PurchasePlan(unittest.TestCase):
    def test_same_upgrade_twice_is_warned_34(self):
        d = te.base(purchases=[te.buy("a", upgrade="w1"), te.buy("b", upgrade="w1")])
        d["stages"][0]["income"]["soul"] = 50
        r = te.validate(d)
        self.assertEqual([(w["code"], w["where"]) for w in r["warnings"]], [("duplicate_purchase", "b")])

    def test_enhancement_steps_must_follow_each_other_34(self):
        gaps = lambda d: [w["where"] for w in te.validate(d)["warnings"] if w["code"] == "enhance_gap"]  # noqa: E731
        again = te.base(purchases=[te.buy("e1", enhance="plus", level=1), te.buy("e2", enhance="plus", level=2, **{"from": 0})])
        self.assertEqual(gaps(again), ["e2"])
        skip = te.base(purchases=[te.buy("e2", enhance="plus", level=2, **{"from": 1})])
        self.assertEqual(gaps(skip), ["e2"])
        ok = te.base(purchases=[te.buy("e1", enhance="plus", level=1), te.buy("e2", enhance="plus", level=2, **{"from": 1})])
        self.assertEqual(gaps(ok), [])


class DraftChecks(unittest.TestCase):
    def test_draft_follows_the_target_file_rules_42(self):
        for kwargs in ({"at": 2.5}, {"at": 0}, {"at": 2, "entry_id": "Bad Id"}):
            with self.subTest(kwargs), self.assertRaises(ValueError):
                bg.draft(tb.data(), "blade", **kwargs)
        with self.assertRaises(ValueError):
            bg.draft(tb.data(), "brute", 0)

    def test_draft_refuses_an_existing_id_42(self):
        with self.assertRaises(ValueError):
            bg.draft(tb.data(), "blade", 2, entry_id="sword", existing={"sword"})
        root = sample_copy(self)
        items = json.loads((root / "data/items.json").read_text(encoding="utf-8"))
        code, _ = run_cli("draft", root, "--archetype", "blade", "--at", "2", "--id", items["items"][0]["id"])
        self.assertEqual(code, 2)


# ---------- C. 메시지와 문서 ----------
class Messages(unittest.TestCase):
    def test_missing_multiplier_field_is_named_not_none_43(self):
        d = tb.data()
        d["archetypes"][2]["fields"] = {}
        with self.assertRaises(ValueError) as ctx:
            bg.draft(d, "brute", 2)
        self.assertNotIn("None", str(ctx.exception))
        self.assertIn("rank", str(ctx.exception))
        d = tb.data()
        d["budget"]["enemies"]["multiplier"]["field"] = "rnk"
        w = next(x for x in tb.validate(d)["warnings"] if x["code"] == "multiplier_missing")
        self.assertNotIn("None", w["message"])
        self.assertIn("'rank'의 오타", w["message"])

    def test_match_condition_is_written_plainly_with_a_hint_43(self):
        r = tcr.validate(tcr.data(enhance=[tcr.track([{"cost": 1}], applies_to={"slot": "wepon"})]))
        msg = next(e["message"] for e in r["errors"] if e["code"] == "match_empty")
        self.assertNotIn("{'", msg)
        self.assertIn("slot=wepon", msg)
        self.assertIn("'weapon'의 오타", msg)

    def test_recipe_table_writes_match_slots_plainly_43(self):
        d = tcr.data(recipes=[{"id": "merge", "inputs": [{"match": {"tier": 1, "slot": "weapon"}, "count": 2}],
                               "output": {"match": {"tier": 2, "slot": "weapon"}}}])
        out = cr.table(d, tcr.validate(d))
        self.assertNotIn("{'", out)
        self.assertIn("2× [tier=1, slot=weapon 아무거나]", out)

    def test_random_loop_names_the_recipe_that_returns_43(self):
        d = tcr.data(recipes=[
            {"id": "merge", "inputs": [{"match": {"tier": 1, "slot": "weapon"}, "count": 2}], "output": {"match": {"tier": 2, "slot": "weapon"}}},
            {"id": "split_b1", "inputs": [{"item": "b1"}], "output": {"item": "a1", "count": 3}},
            {"id": "split_b2", "inputs": [{"item": "b2"}], "output": {"item": "a2", "count": 3}}])
        msg = next(e["message"] for e in tcr.validate(d)["errors"] if e["code"] == "value_loop")
        self.assertIn("split_b1", msg)

    def test_float_noise_and_percent_hint_43(self):
        st = tc.stage()
        st["player"]["base"]["crit_chance"] = 0.1 + 0.2 + 0.9     # 1.2000000000000002
        msg = next(e["message"] for e in tc.validate(tc.data(stages=[st]))["errors"] if e["code"] == "bad_stat")
        self.assertIn("1.2(", msg)
        self.assertNotIn("100으로 나눔", msg)
        st["player"]["base"]["crit_chance"] = 5
        msg = next(e["message"] for e in tc.validate(tc.data(stages=[st]))["errors"] if e["code"] == "bad_stat")
        self.assertIn("100으로 나눔", msg)

    def test_korean_particles_43(self):
        self.assertEqual(common.josa("아이템", "을를"), "아이템을")
        self.assertEqual(common.josa("적", "을를"), "적을")
        self.assertEqual(common.josa("3~5판", "을를"), "3~5판을")
        self.assertEqual(common.josa("10초", "을를"), "10초를")
        self.assertEqual(common.josa("3", "이가"), "3이")
        self.assertEqual(common.josa("2", "이가"), "2가")
        d = tb.data()
        d["budget"]["enemies"]["multiplier"]["values"] = {"normal": 1}
        w = next(x for x in tb.validate(d)["warnings"] if x["code"] == "multiplier_missing")
        self.assertNotIn("적를", w["message"])
        d = te.base(purchases=[dict(te.buy("u", upgrade="w1"), target=[1, 2])])
        d["stages"][0]["income"]["soul"] = 5                      # 25 ÷ 5 → 5번째 판
        w = next(x for x in te.validate(d)["warnings"] if x["code"] == "target_out_of_range")
        self.assertIn("1~2판을", w["message"])

    def test_unchecked_counts_are_not_shown_as_zero_43(self):
        root = sample_copy(self)
        code, out = run_cli("check", root / "data/crafting.json")
        self.assertIn("얻을 수 없는 아이템 –", out)
        self.assertNotIn("대상 0개", out)

    def test_cumulative_income_after_a_dropped_stage_is_not_shown_43(self):
        d = te.base(stages=[{"id": "s1", "duration": 100, "income": {"gold": 100}}, {"id": "s2", "duration": 0},
                            {"id": "s3", "duration": 100, "income": {"gold": 50}}])
        r = te.validate(d)
        self.assertEqual([(s["id"], s["cumulative"]) for s in r["stages"]], [("s1", {"gold": 100}), ("s3", None)])


class InstalledDocs(unittest.TestCase):
    def test_combat_limits_do_not_contradict_run_growth_45(self):
        text = (ROOT / "skills/combat-balance/SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("런 안의 레벨업은 아직 없다", text)

    def test_skill_docs_do_not_point_at_repository_only_files_45(self):
        for md in (ROOT / "skills").rglob("*.md"):
            for n, line in enumerate(md.read_text(encoding="utf-8").splitlines(), start=1):
                if "docs/" in line and "github.com" not in line:
                    self.fail(f"{md}:{n}: 설치본에 없는 저장소 문서를 가리킵니다")
        guide = (ROOT / "skills/combat-balance/references/formula-guide.md").read_text(encoding="utf-8")
        self.assertIn("| 게임", guide)      # 상한 표를 설치본에서 볼 수 있다


class TableFilter(unittest.TestCase):
    def test_table_can_choose_kinds_46(self):
        root = sample_copy(self)
        code, out = run_cli("check", root, "--table", "combat")
        self.assertIn("| 단계 | 적 | 등급 |", out)
        self.assertNotIn("| 빌드 | 단계 | 레벨 |", out)
        code, out = run_cli("check", root, "--table")
        self.assertIn("| 빌드 | 단계 | 레벨 |", out)

    def test_unknown_table_kind_is_a_usage_error_46(self):
        root = sample_copy(self)
        code, _ = run_cli("check", root, "--table", "combt")
        self.assertEqual(code, 2)


class ViewerOutput(unittest.TestCase):
    def test_ready_line_reaches_a_pipe_right_away_47(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        proc = subprocess.Popen([sys.executable, str(STUDIO / "scripts/studio.py"), "view", tmp.name, "--no-browser", "--port", "0"],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.addCleanup(proc.stdout.close)
        self.addCleanup(proc.wait)
        self.addCleanup(proc.kill)
        got = []
        reader = threading.Thread(target=lambda: got.append(proc.stdout.readline()), daemon=True)
        reader.start()
        reader.join(10)
        self.assertTrue(got and got[0].decode("utf-8").startswith("데이터 뷰어: http://"), got)


class ViewerLabels(unittest.TestCase):
    def test_every_issue_code_has_a_viewer_label_43(self):
        src = "\n".join(p.read_text(encoding="utf-8") for p in (STUDIO / "scripts/studio_data").glob("*.py"))
        found = (set(re.findall(r'_err\((?:errors|warnings)[^,]*, "([a-z_]+)"', src)) | set(re.findall(r'add_issue\((?:warnings|errors), "([a-z_]+)"', src))
                 | set(re.findall(r'"code": "([a-z_]+)"', src)))
        html = (STUDIO / "assets/viewer.html").read_text(encoding="utf-8")
        labels = html[html.index("  code: {"):html.index("  unchecked: {")]
        self.assertGreater(len(found), 60)
        self.assertEqual(sorted(c for c in found if f"{c}:" not in labels), [])


# ---------- D. 스킬 사이의 구조 ----------
class SharedWeights(unittest.TestCase):
    ITEMS = {"stat_weights": {"attack": 1.0, "armor": 0.1},
             "items": [{"id": "a", "slot": "weapon", "tier": 1, "stats": {"attack": 10}},
                       {"id": "b", "slot": "weapon", "tier": 2, "stats": {"armor": 10}}]}

    def test_budget_costs_are_the_item_weights_35(self):
        r = vi.validate(copy.deepcopy(self.ITEMS), weights={"attack": 1.0, "armor": 1.5})
        self.assertEqual(r["scores"]["b"], 15)
        self.assertEqual(r["weights_source"], "budget")
        self.assertEqual(codes(r["warnings"]), ["weights_ignored"])

    def test_proportional_weights_are_fine_35(self):
        r = vi.validate(copy.deepcopy(self.ITEMS), weights={"attack": 2.0, "armor": 0.2})
        self.assertNotIn("weights_ignored", codes(r["warnings"]))

    def test_enemy_threat_uses_budget_costs_35(self):
        data = {"threat_weights": {"hp": 1.0, "damage": 1.0},
                "enemies": [{"id": "s", "zone": 1, "rank": "normal", "stats": {"hp": 10, "damage": 2}}]}
        r = ve.validate(data, weights={"hp": 0.1, "damage": 1.0})
        self.assertEqual(r["weights_source"], "budget")
        self.assertEqual(codes(r["warnings"]), ["weights_ignored"])

    def test_project_check_uses_budget_costs_35(self):
        root = sample_copy(self)
        code, out = run_cli("check", root, "--json")
        reports = {d["kind"]: d["report"] for d in json.loads(out)["datasets"] if d.get("report")}
        self.assertEqual((reports["items"]["weights_source"], reports["enemies"]["weights_source"]), ("budget", "budget"))


class ItemChoices(unittest.TestCase):
    ITEMS = {"charm": {"id": "charm", "stats": {"attack": 2}}}

    def test_choice_can_grant_an_item_36(self):
        choices = [{"id": "take_charm", "item": "charm", "max_picks": 1}, {"id": "vigor", "stats": {"max_hp": 15}}]
        r = gr.validate(tg.data(choices=choices, builds=[{"id": "b", "priority": ["take_charm", "vigor"]}]),
                        combat=tg.COMBAT, items=self.ITEMS, upgrades={}, enemies=tg.ENEMIES)
        self.assertEqual(r["errors"], [])
        self.assertEqual(tg.stage(r, "b", "s1")["bonus"], {"attack": 2, "max_hp": 30})

    def test_choice_item_must_exist_36(self):
        choices = [{"id": "take", "item": "nope"}]
        r = gr.validate(tg.data(choices=choices, builds=[{"id": "b", "priority": ["take"]}]),
                        combat=tg.COMBAT, items=self.ITEMS, upgrades={}, enemies=tg.ENEMIES)
        self.assertIn("unknown_item", codes(r["errors"]))

    def test_choice_items_count_as_obtainable_36(self):
        r = cr.validate(tcr.data(), items=tcr.ITEMS, drop_tables=tcr.COMMON_ONLY, budget=tcr.BUDGET,
                        extra_sources={"b1": "레벨업 선택지 take_b1"})
        self.assertIn("b1", r["obtainable"])
        self.assertIn("b2", r["unobtainable"])


class EnhancedLoadout(unittest.TestCase):
    CRAFTING = {"crafting": {}, "enhance": [{"id": "plus", "items": ["sword"],
                                             "levels": [{"cost": 10, "bonus_pct": 0.2}, {"cost": 20, "bonus_pct": 0.3}]}], "recipes": []}

    def run_stage(self, entry, crafting=CRAFTING):
        st = tc.stage(player={"base": {"max_hp": 100, "attack": 10, "attack_speed": 1.0}, "items": [entry]})
        return cb.validate(tc.data(stages=[st]), items=tc.ITEMS, upgrades=tc.UPGRADES, enemies=tc.ENEMIES, crafting=crafting)

    def test_loadout_item_can_be_enhanced_37(self):
        r = self.run_stage({"item": "sword", "enhance": "plus", "level": 2})
        self.assertEqual(r["errors"], [])
        self.assertAlmostEqual(r["stages"]["s1"]["player"]["attack"], 10 + 5 * 1.5)

    def test_enhancement_references_are_checked_37(self):
        for entry, code in (({"item": "sword", "enhance": "nope", "level": 1}, "unknown_enhance"),
                            ({"item": "sword", "enhance": "plus", "level": 3}, "schema"),
                            ({"item": "vest", "enhance": "plus", "level": 1}, "schema")):
            with self.subTest(entry):
                self.assertIn(code, codes(self.run_stage(entry)["errors"]))

    def test_without_crafting_data_it_is_unchecked_37(self):
        r = self.run_stage({"item": "sword", "enhance": "plus", "level": 1}, crafting=None)
        self.assertEqual(r["errors"], [])
        self.assertIn("crafting", r["unchecked_kinds"])


class MetaLink(unittest.TestCase):
    def meta(self):
        return meta_sim.normalize({"seed": 1, "trials": 10, "max_runs": 5, "rooms": 10,
                                   "difficulty": {"base": 1, "rate": 1}, "player": {"base_power": 1}, "survival": {"slope": 1},
                                   "currency": {"per_room": 5}, "purchase_policy": "listed_order",
                                   "upgrades": [{"id": "w2", "cost": 10}, {"id": "w1", "cost": 25}]})

    def test_meta_income_and_order_are_compared_38(self):
        d = te.base(purchases=[te.buy("a", upgrade="w1"), te.buy("b", upgrade="w2")])
        d["economy"]["currencies"]["soul"]["meta_config"] = "meta.json"
        d["stages"][0]["income"]["soul"] = 20
        r = evalidate(d, meta={"soul": self.meta()})
        self.assertEqual(sorted(codes(r["warnings"])), ["meta_income_differs", "meta_order_differs"])

    def test_matching_meta_is_quiet_38(self):
        d = te.base(purchases=[te.buy("b", upgrade="w2"), te.buy("a", upgrade="w1")])
        d["economy"]["currencies"]["soul"]["meta_config"] = "meta.json"
        d["stages"][0]["income"]["soul"] = 50
        self.assertEqual(evalidate(d, meta={"soul": self.meta()})["warnings"], [])

    def test_broken_meta_link_is_an_error_38(self):
        root = sample_copy(self)
        e = json.loads((root / "data/economy.json").read_text(encoding="utf-8"))
        carry = next(k for k, v in e["economy"]["currencies"].items() if v.get("carry"))
        e["economy"]["currencies"][carry]["meta_config"] = "nope.json"
        (root / "data/economy.json").write_text(json.dumps(e), encoding="utf-8")
        code, out = run_cli("check", root)
        self.assertEqual(code, 1)
        self.assertIn("nope.json", out)


class StageLink(unittest.TestCase):
    COMBAT = {"stages": [{"id": "c1", "enemies": ["ghost"]}, {"id": "c2", "enemies": ["slime"], "status": "cut"}]}

    def test_economy_stage_can_point_at_a_combat_stage_39(self):
        d = te.base()
        d["stages"][0].update({"combat_stage": "c9"})
        self.assertIn("unknown_stage", codes(evalidate(d, combat=self.COMBAT)["errors"]))

    def test_kills_of_enemies_outside_the_linked_stage_are_warned_39(self):
        d = te.base()
        d["stages"][0].update({"combat_stage": "c1", "kills": {"slime": 2}})
        r = evalidate(d, combat=self.COMBAT)
        self.assertEqual(codes(r["warnings"]), ["kill_not_in_stage"])

    def test_growth_doc_uses_entry_levels_like_combat_39(self):
        text = (ROOT / "skills/run-growth/references/growth-format.md").read_text(encoding="utf-8")
        self.assertIn("들어설 때", text)


class ReviewFindings(unittest.TestCase):
    """이번 수정의 코드 검토에서 나온 문제의 회귀 테스트."""

    def link_meta(self, root, edit_meta):
        e = json.loads((root / "data/economy.json").read_text(encoding="utf-8"))
        e["economy"]["currencies"]["soul"]["meta_config"] = "meta.json"
        (root / "data/economy.json").write_text(json.dumps(e), encoding="utf-8")
        m = json.loads((root / "data/meta.json").read_text(encoding="utf-8"))
        edit_meta(m)
        (root / "data/meta.json").write_text(json.dumps(m), encoding="utf-8")

    def test_odd_meta_config_is_reported_on_the_link_not_the_economy_file(self):
        root = sample_copy(self)
        self.link_meta(root, lambda m: m["player"].__setitem__("power_per_room", {"x": 1}))
        code, out = run_cli("check", root, "--json")
        econ = next(d for d in json.loads(out)["datasets"] if d["kind"] == "economy")
        self.assertTrue(econ["ok"])
        self.assertEqual([e["where"] for e in econ["report"]["errors"]], ["economy.currencies.soul"])
        self.assertTrue(econ["report"]["stages"])

    def test_cut_prerequisite_in_the_plan_does_not_count_as_bought(self):
        ups = {"w1": {"id": "w1", "cost": 25, "status": "cut"}, "w2": {"id": "w2", "cost": 10, "requires": ["w1"]}}
        d = te.base(purchases=[te.buy("a", upgrade="w1"), te.buy("b", upgrade="w2")])
        d["stages"][0]["income"]["soul"] = 50
        self.assertEqual(sorted(codes(evalidate(d, upgrades=ups)["warnings"])), ["cut_referenced", "requirement_missing"])

    def test_table_flag_before_the_path_still_works(self):
        root = sample_copy(self)
        code, out = run_cli("check", "--table", root)
        self.assertEqual(code, 0)
        self.assertIn("| 빌드 | 단계 | 레벨 |", out)
        code, out = run_cli("check", "--table", "combat", root)
        self.assertIn("| 단계 | 적 | 등급 |", out)
        self.assertNotIn("| 빌드 | 단계 | 레벨 |", out)
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(["check", "--table"]), 2)        # 경로가 없으면 사용법 오류
        self.assertIn("검사할 프로젝트", err.getvalue())

    def test_currency_typo_blocks_only_the_currency_it_most_likely_meant(self):
        d = te.base(purchases=[te.buy("x", amount=10, currency="gld"), te.buy("u", upgrade="w1")])
        d["stages"][0]["income"]["soul"] = 50
        r = te.validate(d)
        u = next(p for p in r["purchases"] if p["id"] == "u")
        self.assertEqual((u["runs"], u["blocked"]), (1, None))
        self.assertNotIn("gold", r["leftover"])
        d = te.base(prices={"items": "gold", "upgrades": "souls"}, purchases=[te.buy("u", upgrade="w1"), te.buy("x", amount=50, currency="gold")])
        r = te.validate(d)
        self.assertIn("gold", r["leftover"])                    # 'souls'는 soul의 오타로 보고 soul만 막는다

    def test_stat_without_a_budget_cost_keeps_its_weight(self):
        data = {"stat_weights": {"attack": 1.0, "pickup": 50.0}, "items": [{"id": "a", "slot": "w", "tier": 1, "stats": {"attack": 1, "pickup": 1}}]}
        r = vi.validate(data, weights={"attack": 2.0})
        self.assertEqual(r["scores"]["a"], 2 + 100)             # 원가 단위로 바꾼 옛 가중치(50 × 2)
        self.assertEqual(r["warnings"], [])

    def test_linked_stage_enemies_follow_the_combat_rule(self):
        enemies = dict(te.ENEMIES, slime=dict(te.ENEMIES["slime"], zone=1), gone=dict(te.ENEMIES["gone"], zone=1))
        d = te.base()
        d["stages"][0].update({"combat_stage": "c1", "kills": {"slime": 1, "gone": 1}})
        r = evalidate(d, enemies=enemies, combat={"stages": [{"id": "c1", "zone": 1}]})
        w = next(x for x in r["warnings"] if x["code"] == "kill_not_in_stage")
        self.assertIn("gone", w["message"])                     # 전투 계산은 구역의 삭제된 적을 빼고 계산한다
        self.assertNotIn("slime", w["message"])

    def test_meta_config_is_read_once_until_it_changes(self):
        from _studio import datasets, meta_sim
        root = sample_copy(self)
        self.link_meta(root, lambda m: None)
        calls = []
        original = meta_sim.normalize
        meta_sim.normalize = lambda *a, **k: calls.append(1) or original(*a, **k)
        self.addCleanup(setattr, meta_sim, "normalize", original)
        datasets.collect([root])
        datasets.collect([root])
        self.assertEqual(len(calls), 1)
        self.link_meta(root, lambda m: m["currency"].__setitem__("per_room", 3))
        datasets.collect([root])
        self.assertEqual(len(calls), 2)


# ---------- B5b 시험 보고(48~56) ----------
ZONED = {"crawler": {"id": "crawler", "rank": "normal", "zone": 1, "stats": {"hp": 30, "damage": 5}},
         "swarmer": {"id": "swarmer", "rank": "normal", "zone": 2, "stats": {"hp": 40, "damage": 6}}}


class ZoneRule(unittest.TestCase):
    def foes(self, **over):
        st = tc.stage("s2", zone=2, **over)
        st.pop("enemies")
        return [r["enemy"] for r in tc.validate(tc.data(stages=[st]), enemies=ZONED)["rows"]]

    def test_zone_keeps_its_first_seen_meaning_by_default_48(self):
        self.assertEqual(self.foes(), ["swarmer"])

    def test_up_to_includes_enemies_that_keep_appearing_48(self):
        self.assertEqual(self.foes(zone_rule="up_to"), ["crawler", "swarmer"])
        st = tc.stage("s2", zone=2, zone_rule="all")
        st.pop("enemies")
        self.assertIn("schema", codes(tc.validate(tc.data(stages=[st]), enemies=ZONED)["errors"]))

    def test_economy_hint_names_the_zone_rule_48(self):
        d = te.base()
        d["stages"][0].update({"combat_stage": "c2", "kills": {"crawler": 10}})
        r = evalidate(d, enemies=dict(te.ENEMIES, **{k: dict(v, reward=1) for k, v in ZONED.items()}), combat={"stages": [{"id": "c2", "zone": 2}]})
        w = next(x for x in r["warnings"] if x["code"] == "kill_not_in_stage")
        self.assertIn("zone_rule", w["message"])


class RankMargins(unittest.TestCase):
    ROWS = [dict(tmc.row(4, 4.0, 4, 4.0), rank="normal", enemy="a"), dict(tmc.row(100, 100.0, 5, 5.0), rank="boss", enemy="boss")]

    def test_each_rank_is_measured_against_its_own_reference_49(self):
        self.assertEqual(meta_sim.stage_margin(self.ROWS), 0.05)                                   # 기준 1: 보스가 정한다
        self.assertAlmostEqual(meta_sim.stage_margin(self.ROWS, {"normal": 1.0, "boss": 0.1}), 0.5)  # 보스 0.05 ÷ 0.1
        self.assertAlmostEqual(meta_sim.stage_margin(self.ROWS, {"normal": 2.0, "boss": 0.01}), 0.5)  # 이제 일반 적이 정한다

    def test_rank_references_are_checked_49(self):
        raw = json.loads((SAMPLE / tmc.CONFIG).read_text(encoding="utf-8"))
        raw["survival"]["even_margin"] = {"normal": 1, "bos": 0.1}
        with self.assertRaisesRegex(meta_sim.ConfigError, "'boss'의 오타"):
            meta_sim.normalize(raw, (SAMPLE / tmc.CONFIG).parent)


class SimulatorFieldTest(tmc.Workspace):
    def test_overview_names_the_enemy_that_decides_the_stage_49(self):
        cfg, r = self.run_cfg(survival={"slope": 3.0, "even_margin": {"normal": 1.0, "elite": 0.3, "boss": 0.1}})
        first = r["survival_by_stage"][0]
        self.assertIn(first["decided_by"], ("slime", "skeleton_archer", "grave_knight", "bone_lord"))
        self.assertIn("rank", first)

    def test_unknown_keys_are_refused_with_a_hint_50(self):
        for change, hint in ((lambda d: d["survival"].__setitem__("even_margn", 0.3), "even_margin"),
                             (lambda d: d.__setitem__("milestone", d.pop("milestones")), "milestones"),
                             (lambda d: d["milestones"][0].__setitem__("clear_room", 1), "clear_room"),
                             (lambda d: d.__setitem__("growth_flie", d.pop("growth_file")), "growth_file")):
            raw = json.loads(self.config.read_text(encoding="utf-8"))
            change(raw)
            with self.subTest(hint), self.assertRaisesRegex(meta_sim.ConfigError, hint):
                meta_sim.normalize(raw, self.config.parent)
        raw = json.loads((self.root / "data/meta.json").read_text(encoding="utf-8"))
        raw["survial"] = raw.pop("survival")
        with self.assertRaisesRegex(meta_sim.ConfigError, "'survival'의 오타"):
            meta_sim.normalize(raw, self.config.parent)

    def test_build_without_growth_file_says_so_56(self):
        raw = json.loads(self.config.read_text(encoding="utf-8"))
        raw.pop("growth_file")
        with self.assertRaisesRegex(meta_sim.ConfigError, "growth_file이 필요"):
            meta_sim.normalize(raw, self.config.parent)

    def test_stat_effects_give_off_combat_upgrades_a_value_52(self):
        self.edit("data/upgrades.json", lambda d: d["upgrades"].insert(0, {"id": "greed", "cost": 5, "stats": {"soul_gain": 1}}))
        self.edit("data/economy.json", lambda d: d["purchases"].insert(5, {"id": "meta_greed", "price": {"upgrade": "greed"}}))
        cfg, plain = meta_sim.run_config(self.config)
        self.assertIn("greed", plain["upgrades_without_combat_effect"])
        cfg, rich = self.run_cfg(stat_effects={"soul_gain": {"income_pct": 1.0}})
        self.assertNotIn("greed", rich["upgrades_without_combat_effect"])
        self.assertLess(rich["upgrades"]["weapon_2"]["median"], plain["upgrades"]["weapon_2"]["median"])

    def test_level_effect_adds_level_ups_52(self):
        self.edit("data/upgrades.json", lambda d: d["upgrades"].insert(0, {"id": "wisdom", "cost": 5, "stats": {"wisdom": 1}}))
        self.edit("data/economy.json", lambda d: d["purchases"].insert(5, {"id": "meta_wisdom", "price": {"upgrade": "wisdom"}}))
        cfg, plain = meta_sim.run_config(self.config)
        cfg, rich = self.run_cfg(stat_effects={"wisdom": {"levels": 3}})
        self.assertGreater(rich["survival_by_stage"][0]["margin_all"], plain["survival_by_stage"][0]["margin_all"])

    def test_stat_effects_are_checked_52(self):
        for effects in ({"soul_gain": {"income": 1}}, {"soul_gain": {"income_pct": "x"}}):
            raw = json.loads(self.config.read_text(encoding="utf-8"))
            raw["stat_effects"] = effects
            with self.subTest(effects), self.assertRaises(meta_sim.ConfigError):
                meta_sim.normalize(raw, self.config.parent)
        raw = json.loads(self.config.read_text(encoding="utf-8"))
        raw.pop("growth_file"), raw.pop("build")
        raw["stat_effects"] = {"wisdom": {"levels": 1}}
        with self.assertRaisesRegex(meta_sim.ConfigError, "growth_file"):
            meta_sim.normalize(raw, self.config.parent)

    def test_result_records_every_input_file_53(self):
        cfg, r = meta_sim.run_config(self.config)
        names = {Path(x["path"]).name: x["sha256"] for x in r["inputs"]}
        for f in ("combat.json", "growth.json", "economy.json", "items.json", "enemies.json", "upgrades.json"):
            self.assertIn(f, names)
            self.assertEqual(len(names[f]), 64)

    def test_check_flags_an_upgrade_that_breaks_combat_stats_54(self):
        self.edit("data/upgrades.json", lambda d: d["upgrades"].append({"id": "lucky", "cost": 1, "stats": {"crit_chance": 2}}))
        code, out = run_cli("check", self.root, "--json")
        r = next(d["report"] for d in json.loads(out)["datasets"] if d["kind"] == "combat")
        self.assertEqual([(e["code"], e["where"]) for e in r["errors"]], [("bad_stat", "upgrades:lucky")])

    def test_stage_left_out_on_purpose_is_not_called_a_typo_55(self):
        with self.assertRaises(meta_sim.ConfigError) as ctx:
            self.run_cfg(stages=["zone_1", "zone_3"])
        self.assertIn("stages", str(ctx.exception))
        self.assertNotIn("오타", str(ctx.exception))

    def test_docs_explain_how_to_start_the_survival_curve_51(self):
        text = (ROOT / "skills/progression-economy/references/meta-model.md").read_text(encoding="utf-8")
        section = text[text.index("### 생존 곡선의 처음 값"):]
        for word in ("margin_none", "decided_by", "even_margin", "slope", "B5c"):
            self.assertIn(word, section)


class SimulatorReview(tmc.Workspace):
    """48~56번 수정의 코드 검토에서 나온 문제의 회귀 테스트."""

    def test_overview_has_the_no_upgrade_margin_with_growth(self):
        cfg, r = meta_sim.run_config(self.config)
        for s in r["survival_by_stage"]:
            self.assertIn("margin_growth", s)
            self.assertGreaterEqual(s["p_growth"], s["p_none"])
            self.assertLessEqual(s["p_growth"], s["p_all"])
        self.assertGreater(r["survival_by_stage"][2]["margin_growth"], r["survival_by_stage"][2]["margin_none"])
        text = (ROOT / "skills/progression-economy/references/meta-model.md").read_text(encoding="utf-8")
        self.assertIn("margin_growth", text[text.index("### 생존 곡선의 처음 값"):])

    def test_stat_effect_names_must_be_upgrade_stats(self):
        raw = json.loads(self.config.read_text(encoding="utf-8"))
        raw["stat_effects"] = {"relic_slotz": {"income_pct": 5.0}}
        with self.assertRaisesRegex(meta_sim.ConfigError, "'relic_slots'의 오타"):
            meta_sim.normalize(raw, self.config.parent)

    def test_stat_effects_cannot_reuse_a_combat_stat(self):
        with self.assertRaisesRegex(meta_sim.ConfigError, "attack"):
            self.run_cfg(stat_effects={"attack": {"levels": 1}})

    def test_up_to_needs_numeric_zones(self):
        st = tc.stage("s2", zone="2", zone_rule="up_to")
        st.pop("enemies")
        r = tc.validate(tc.data(stages=[st]), enemies=ZONED)
        self.assertIn("schema", codes(r["errors"]))


if __name__ == "__main__":
    unittest.main()
