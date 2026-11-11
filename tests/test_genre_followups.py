"""다른 장르 시험 2 뒤(346~349번): 레벨로 자라는 적(level_of), 단계마다 다른 전투 목표, 내림, 모르는 키. 표준 라이브러리 unittest만 사용한다."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from _studio import ROOT, SAMPLE, combat as cb, datasets, enemies as en, meta_sim as sm, run_cli
from test_grown_kill_ratio import SHIM


class Project(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "p"
        shutil.copytree(SAMPLE, self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def change(self, rel, fn):
        path = self.root / rel
        data = json.loads(path.read_text(encoding="utf-8"))
        fn(data)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def reports(self):
        return {d["kind"]: d["report"] for d in datasets.collect([self.root]) if d.get("report")}


class LeveledEnemies(Project):
    """346번: 같은 적이 레벨마다 다른 스탯으로 나온다. 레벨 1 기본치와 레벨당 상승치에서 계산한다."""

    def leveled(self, **row):
        def fn(d):
            slime = next(e for e in d["enemies"] if e["id"] == "slime")
            slime["growth"] = {"hp": 5, "damage": 2}
            d["enemies"].append({"id": "slime_l3", "level_of": "slime", "level": 3, **row})
        self.change("data/enemies.json", fn)

    def test_stats_come_from_the_base_and_growth(self):
        self.leveled()
        entries = datasets.collect([self.root])
        got = datasets.indexes(entries)["enemies"]["slime_l3"]
        self.assertEqual(got["stats"], {"hp": 40, "damage": 8, "speed": 1.0})   # 30 + 5×2, 4 + 2×2
        self.assertEqual((got["rank"], got["zone"]), ("normal", 1))   # 적지 않은 칸은 기본 적에서 받는다
        r = self.reports()["enemies"]
        self.assertEqual(r["errors"], [])
        self.assertIn("slime_l3", r["scores"])
        self.assertEqual(r["leveled"]["slime_l3"], {"of": "slime", "level": 3, "stats": {"hp": 40, "damage": 8, "speed": 1.0}})

    def test_written_fields_override_the_base(self):
        self.leveled(zone=2)
        self.assertEqual(datasets.indexes(datasets.collect([self.root]))["enemies"]["slime_l3"]["zone"], 2)

    def test_combat_uses_the_leveled_stats(self):
        self.leveled()
        self.change("data/combat.json", lambda d: d["stages"][0].update(enemies=["slime", "slime_l3"], zone=None))
        rows = {r["enemy"]: r for r in self.reports()["combat"]["rows"] if r["stage"] == "zone_1"}
        self.assertGreater(rows["slime_l3"]["hits_to_kill"], rows["slime"]["hits_to_kill"])

    def test_bad_rows_are_errors(self):
        cases = {"unknown_enemy": ({"level_of": "nope", "level": 2}, "level_of"),
                 "schema": ({"level_of": "slime", "level": 0}, "level은")}
        for code, (row, words) in cases.items():
            with self.subTest(code):
                raw = [{"id": "slime", "rank": "normal", "zone": 1, "stats": {"hp": 30}, "growth": {"hp": 5}}, {"id": "x", **row}]
                errors = en.validate({"enemies": raw})["errors"]
                self.assertEqual([(e["code"], e["where"]) for e in errors], [(code, "x")], errors)
                self.assertIn(words, errors[0]["message"])

    def test_a_row_cannot_also_write_stats(self):
        raw = [{"id": "slime", "rank": "normal", "zone": 1, "stats": {"hp": 30}, "growth": {"hp": 5}},
               {"id": "x", "level_of": "slime", "level": 2, "stats": {"hp": 1}}]
        errors = en.validate({"enemies": raw})["errors"]
        self.assertEqual([e["code"] for e in errors], ["schema"])
        self.assertIn("stats를 적지 않습니다", errors[0]["message"])

    def test_the_base_needs_growth(self):
        raw = [{"id": "slime", "rank": "normal", "zone": 1, "stats": {"hp": 30}}, {"id": "x", "level_of": "slime", "level": 2}]
        errors = en.validate({"enemies": raw})["errors"]
        self.assertTrue(any(e["code"] == "schema" and "growth" in e["message"] for e in errors), errors)

    def test_a_leveled_row_cannot_be_a_base(self):
        raw = [{"id": "slime", "rank": "normal", "zone": 1, "stats": {"hp": 30}, "growth": {"hp": 5}},
               {"id": "a", "level_of": "slime", "level": 2}, {"id": "b", "level_of": "a", "level": 3}]
        self.assertIn("unknown_enemy", [e["code"] for e in en.validate({"enemies": raw})["errors"]])

    @unittest.skipUnless(shutil.which("node"), "node가 없습니다")
    def test_the_viewer_lists_the_leveled_row_with_its_stats(self):
        self.leveled()
        ds = next(d for d in datasets.collect([self.root]) if d["kind"] == "enemies")
        html = (ROOT / "skills/studio-data/assets/viewer.html").read_text(encoding="utf-8")
        script = html.split("<script>", 1)[1].split("/* ---------- 시작 ---------- */", 1)[0]
        probe = 'const ds = JSON.parse(require("fs").readFileSync(0, "utf8")); console.log(JSON.stringify(KINDS.enemies.entries(ds).find((e) => e.id === "slime_l3")));'
        out = subprocess.run(["node", "-e", SHIM + script + probe], input=json.dumps({"data": ds["data"], "report": ds["report"]}, ensure_ascii=False),
                             capture_output=True, text=True, encoding="utf-8", check=True).stdout
        row = json.loads(out)
        self.assertEqual((row["stats"]["hp"], row["rank"], row["zone"], row["level_of"]), (40, "normal", 1, "slime"))
        self.assertNotIn("growth", row)

    def test_a_broken_leveled_row_leaves_references_unchecked(self):
        def fn(d):
            d["enemies"].append({"id": "slime_l3", "level_of": "slime", "level": 3})   # slime에 growth가 없다
        self.change("data/enemies.json", fn)
        self.change("data/combat.json", lambda d: d["stages"][0].update(enemies=["slime", "slime_l3"], zone=None))
        r = self.reports()
        self.assertIn("schema", [e["code"] for e in r["enemies"]["errors"]])
        self.assertNotIn("unknown_enemy", [e["code"] for e in r["combat"]["errors"]])   # 원인은 적 데이터에 있다. 없는 적으로 연쇄 보고하지 않는다
        self.assertIn("enemies", r["combat"]["unchecked_kinds"])

    def test_only_the_listed_fields_are_inherited(self):
        def fn(d):
            slime = next(e for e in d["enemies"] if e["id"] == "slime")
            slime.update(growth={"hp": 5}, intent="튜토리얼용", effect="느림", acknowledged={"x": "y"}, behavior="charge")
            d["enemies"].append({"id": "slime_l3", "level_of": "slime", "level": 3})
        self.change("data/enemies.json", fn)
        got = datasets.indexes(datasets.collect([self.root]))["enemies"]["slime_l3"]
        for key in ("intent", "effect", "acknowledged", "behavior"):
            self.assertNotIn(key, got)
        for key in ("name", "rank", "zone", "reward", "drop_table", "status", "provenance"):
            self.assertIn(key, got)

    def test_a_growth_stat_must_be_a_base_stat(self):
        raw = [{"id": "slime", "rank": "normal", "zone": 1, "stats": {"hp": 30, "damage": 4}, "growth": {"hp": 5, "dmage": 2}},
               {"id": "slime_l3", "level_of": "slime", "level": 3}]
        r = en.validate({"enemies": raw})
        self.assertEqual([(e["code"], e["where"]) for e in r["errors"]], [("schema", "slime")])
        self.assertIn("dmage", r["errors"][0]["message"])
        self.assertNotIn("slime_l3", r["scores"])   # 기본 적의 오류 하나로 알린다. 계산하지 못한 행을 따로 다시 알리지 않는다

    def test_a_row_blocked_by_its_base_leaves_references_unchecked(self):
        def fn(d):
            slime = next(e for e in d["enemies"] if e["id"] == "slime")
            slime["growth"] = {"dmage": 2}
            d["enemies"].append({"id": "slime_l3", "level_of": "slime", "level": 3})
        self.change("data/enemies.json", fn)
        self.change("data/combat.json", lambda d: d["stages"][0].update(enemies=["slime", "slime_l3"], zone=None))
        r = self.reports()
        self.assertNotIn("unknown_enemy", [e["code"] for e in r["combat"]["errors"]])
        self.assertIn("enemies", r["combat"]["unchecked_kinds"])

    def test_a_csv_file_can_hold_leveled_rows(self):
        folder = Path(self.tmp.name) / "csv"
        folder.mkdir()
        (folder / "enemies.csv").write_text(
            "id,name,rank,zone,level,level_of,stat.hp,stat.damage,growth.hp,growth.damage\n"
            "slime,슬라임,normal,1,,,30,4,5,2\n"
            "slime_l3,,,2,3,slime,,,,\n", encoding="utf-8")
        report = next(d["report"] for d in datasets.collect([folder]) if d["kind"] == "enemies")
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["leveled"]["slime_l3"]["stats"], {"hp": 40, "damage": 8})

    def test_the_project_still_passes(self):
        self.leveled()
        code, out = run_cli("check", self.root)
        self.assertEqual(code, 0)
        self.assertTrue(out.rstrip().endswith("→ PASS"), out[-300:])


class TemplateEnemies(Project):
    """350번: 틀로만 쓰는 기본 적(template)은 적으로 세지 않고 level_of의 기본으로만 쓴다."""

    def templated(self, **extra):
        def fn(d):
            d["enemies"].append({"id": "wraith", "template": True, "rank": "elite", "stats": {"hp": 100, "damage": 1}, "growth": {"hp": 10}, **extra})
            d["enemies"].append({"id": "wraith_l3", "level_of": "wraith", "level": 3, "zone": 2})
        self.change("data/enemies.json", fn)

    def test_a_template_is_not_an_enemy(self):
        self.templated()
        r = self.reports()["enemies"]
        self.assertEqual(r["errors"], [])
        self.assertNotIn("wraith", r["scores"])
        self.assertIn("wraith_l3", r["scores"])
        self.assertEqual(r["templates"], ["wraith"])
        index = datasets.indexes(datasets.collect([self.root]))["enemies"]
        self.assertNotIn("wraith", index)
        self.assertEqual((index["wraith_l3"]["stats"]["hp"], index["wraith_l3"]["rank"]), (120, "elite"))

    def test_a_template_does_not_move_the_zone_means(self):
        before = self.reports()["enemies"]["zone_rank_mean_threat"]
        self.change("data/enemies.json", lambda d: d["enemies"].append(
            {"id": "ghost", "template": True, "rank": "boss", "zone": 1, "stats": {"hp": 1}, "growth": {"hp": 1}}))   # 구역을 적어도 세지 않는다
        self.assertEqual(self.reports()["enemies"]["zone_rank_mean_threat"], before)

    def test_template_rows_are_checked(self):
        base = {"rank": "normal", "zone": 1, "stats": {"hp": 30}, "growth": {"hp": 5}}
        cases = {"no growth": ([{"id": "a", "template": True, "rank": "normal", "stats": {"hp": 1}}], "growth"),
                 "not true": ([{"id": "a", "template": "yes", **base}], "template"),
                 "with level_of": ([dict(base, id="a"), {"id": "b", "template": True, "level_of": "a", "level": 2}], "template"),
                 "same id": ([dict(base, id="a"), {"id": "a", "template": True, "stats": {"hp": 1}, "growth": {"hp": 1}}], "중복")}
        for name, (raw, words) in cases.items():
            with self.subTest(name):
                errors = en.validate({"enemies": raw})["errors"]
                self.assertTrue(any(words in e["message"] for e in errors), errors)

    def test_a_csv_template_column(self):
        folder = Path(self.tmp.name) / "csv"
        folder.mkdir()
        (folder / "enemies.csv").write_text(
            "id,rank,zone,template,level,level_of,stat.hp,growth.hp\n"
            "slime,normal,,true,,,30,5\n"
            "slime_l2,,1,,2,slime,,\n", encoding="utf-8")
        report = next(d["report"] for d in datasets.collect([folder]) if d["kind"] == "enemies")
        self.assertEqual((report["errors"], report["templates"], list(report["scores"])), ([], ["slime"], ["slime_l2"]))

    @unittest.skipUnless(shutil.which("node"), "node가 없습니다")
    def test_the_viewer_marks_only_the_template(self):
        self.templated(intent="틀 메모")
        ds = next(d for d in datasets.collect([self.root]) if d["kind"] == "enemies")
        html = (ROOT / "skills/studio-data/assets/viewer.html").read_text(encoding="utf-8")
        script = html.split("<script>", 1)[1].split("/* ---------- 시작 ---------- */", 1)[0]
        probe = ('const ds = JSON.parse(require("fs").readFileSync(0, "utf8")); const all = KINDS.enemies.entries(ds);'
                 'console.log(JSON.stringify([all.find((e) => e.id === "wraith"), all.find((e) => e.id === "wraith_l3")]));')
        out = subprocess.run(["node", "-e", SHIM + script + probe], input=json.dumps({"data": ds["data"], "report": ds["report"]}, ensure_ascii=False),
                             capture_output=True, text=True, encoding="utf-8", check=True).stdout
        tpl, row = json.loads(out)
        self.assertTrue(tpl["template"])
        self.assertNotIn("template", row)   # 실제 적에 틀 표시가 붙지 않는다
        self.assertNotIn("intent", row)
        self.assertEqual((row["rank"], row["stats"]["hp"]), ("elite", 120))

    def test_the_viewer_inherits_the_same_fields_as_the_checker(self):
        html = (ROOT / "skills/studio-data/assets/viewer.html").read_text(encoding="utf-8")
        line = next(x for x in html.splitlines() if "const ENEMY_INHERITED" in x)
        self.assertEqual(tuple(json.loads(line.split("=", 1)[1].split(";")[0])), en.INHERITED)

    def test_a_direct_reference_to_a_template_is_explained(self):
        self.templated()
        self.change("data/combat.json", lambda d: d["stages"][0].update(enemies=["slime", "wraith"], zone=None))
        self.change("data/levels.json", lambda d: d["levels"][0]["encounters"][0]["enemies"].__setitem__("wraith", 1))
        self.change("data/economy.json", lambda d: d["stages"][0]["kills"].__setitem__("wraith", 1))
        r = self.reports()
        for kind in ("combat", "levels", "economy"):
            with self.subTest(kind):
                found = [e for e in r[kind]["errors"] if e["code"] == "unknown_enemy"]
                self.assertTrue(found, r[kind]["errors"])
                self.assertIn("틀", found[0]["message"])
                self.assertIn("wraith_l3", found[0]["message"])
                self.assertNotIn("없는 id", found[0]["message"])

    def test_a_template_field_typo_is_reported_once_at_the_template(self):
        self.templated(rank="boss2")
        def more(d):
            d["enemies"].append({"id": "wraith_l4", "level_of": "wraith", "level": 4, "zone": 2})
        self.change("data/enemies.json", more)
        errors = [e for e in self.reports()["enemies"]["errors"] if "rank" in e["message"]]
        self.assertEqual([e["where"] for e in errors], ["wraith"], errors)


class StageTargets(Project):
    """347번: 변형 단계처럼 처치가 원래 느린 기준 장비는 그 단계에 목표를 따로 적는다."""

    def test_a_stage_target_overrides_the_rank_target(self):
        self.change("data/combat.json", lambda d: d["stages"][0].__setitem__("targets", {"normal": {"hits_to_kill": [1, 1]}}))
        warnings = self.reports()["combat"]["warnings"]
        hit = [w for w in warnings if w["code"] == "target_out_of_range"]
        self.assertTrue(any(w["where"].startswith("zone_1.") and "1~1" in w["message"] for w in hit), hit)
        self.assertFalse(any(w["where"].startswith("zone_2.") and "1~1" in w["message"] for w in hit))

    def test_other_metrics_of_the_rank_are_kept(self):
        rank = cb.rank_targets({"normal": {"hits_to_kill": [1, 4], "hits_to_die": [10, None]}}, {"normal": {"hits_to_kill": [2, 6]}}, "normal")
        self.assertEqual(rank, {"hits_to_kill": [2, 6], "hits_to_die": [10, None]})

    def test_the_meta_simulator_reads_the_stage_target(self):
        prep = {"settings": {"targets": {}}, "stages": {"zone_1": {"targets": {"boss": {"hits_to_kill": [6, 12]}}}}}
        row, checked = {"enemy": "lord", "rank": "boss"}, [{"stage": "zone_1", "enemy": "lord", "out_of_range": []}]
        self.assertTrue(sm._inside_targets("zone_1", row, prep, checked))
        self.assertFalse(sm._inside_targets("zone_2", row, dict(prep, stages={"zone_2": {}}), [dict(checked[0], stage="zone_2")]))

    def test_a_bad_stage_target_is_an_error(self):
        self.change("data/combat.json", lambda d: d["stages"][0].__setitem__("targets", {"normal": {"hits": [1, 2]}}))
        self.assertIn("schema", [e["code"] for e in self.reports()["combat"]["errors"]])


class Docs(unittest.TestCase):
    def test_leveled_enemies_are_documented(self):
        text = (ROOT / "skills/progression-economy/references/data-format.md").read_text(encoding="utf-8")
        self.assertIn("`level_of`", text)
        self.assertIn("`growth`", text)
        self.assertIn("`template`", text)

    def test_stage_targets_are_documented(self):
        text = (ROOT / "skills/combat-balance/references/combat-format.md").read_text(encoding="utf-8")
        row = next(x for x in text.splitlines() if x.startswith("| `targets` |") and "단계" in x)
        self.assertIn("등급", row)

    def test_rounding_is_a_known_limit(self):
        skill = (ROOT / "skills/combat-balance/SKILL.md").read_text(encoding="utf-8")
        limits = skill[skill.index("## 한계"):]
        self.assertIn("내림", limits)

    def test_unknown_keys_are_explained_once(self):
        text = (ROOT / "skills/studio-data/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("모르는 키", text)
        self.assertIn("게임 고유", text)

    def test_the_viewer_shows_the_base_enemy(self):
        viewer = (ROOT / "skills/studio-data/assets/viewer.html").read_text(encoding="utf-8")
        self.assertIn("leveled", viewer)


if __name__ == "__main__":
    unittest.main()
