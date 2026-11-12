"""갈래(136, 145번)와 다른 장르 시험 8의 작은 이슈(353~356번). 표준 라이브러리 unittest만 사용한다."""
import json
import shutil
import subprocess
import unittest

from _studio import ROOT, SAMPLE, datasets, levels as lv
from test_grown_kill_ratio import SHIM

ENEMIES = {"a": {"id": "a", "rank": "normal", "zone": 1, "stats": {"hp": 10}}}
THREAT = {"a": 10.0}
COMBAT = {"stages": [{"id": "s1", "zone": 1}, {"id": "b1", "zone": 2}, {"id": "b2", "zone": 2}, {"id": "b3", "zone": 2}, {"id": "s5", "zone": 3}]}
BUDGET = {"curve": {"growth": "linear", "base": 80, "rate": 40}, "roles": {"room": 1}, "tolerance": 0.5, "provenance": {"kind": "assumed"}}
SIZES = {"s1": 8, "b1": 16, "b2": 10, "b3": 12, "s5": 14}   # 위협도 = 크기 × 10


def level(lid, n=None, **enc):
    return {"id": lid, "encounters": [{"id": f"{lid}_e", "role": "room", "enemies": {"a": SIZES[lid] if n is None else n}, **enc}],
            "provenance": {"kind": "assumed"}}


def run(branches=None, levels=None, pacing=None, **extra):
    data = {"levels": levels or [level(k) for k in SIZES], "threat_budget": BUDGET}
    if branches is not None:
        data["branches"] = branches
    if pacing is not None:
        data["pacing"] = pacing
    return lv.validate(data, enemies=ENEMIES, threat=THREAT, combat=extra.pop("combat", COMBAT), **extra)


def stage(r, sid):
    return next(s for s in r["stages"] if s["id"] == sid)


ALL = [{"stages": ["b1", "b2", "b3"]}]


class Branches(unittest.TestCase):
    def test_without_branches_the_stages_are_one_line(self):
        r = run()
        self.assertEqual(stage(r, "b2")["vs_previous"], round(100 / 160, 4))
        self.assertEqual(stage(r, "s5")["vs_previous"], round(140 / 120, 4))

    def test_a_branch_stage_is_compared_with_the_stage_before_the_branch(self):
        r = run(ALL)
        self.assertEqual(r["errors"], [])
        self.assertEqual(stage(r, "b2")["vs_previous"], round(100 / 80, 4))
        self.assertEqual(stage(r, "b3")["vs_previous"], round(120 / 80, 4))

    def test_the_stage_after_the_branch_is_compared_with_its_strongest_stage(self):
        self.assertEqual(stage(run(ALL), "s5")["vs_previous"], round(140 / 160, 4))

    def test_branch_stages_share_a_position(self):
        r = run(ALL)
        self.assertEqual([stage(r, k)["position"] for k in ("s1", "b1", "b2", "b3", "s5")], [1, 2, 2, 2, 3])
        self.assertEqual(stage(r, "b2")["branch"], ["b1", "b2", "b3"])
        table = lv.table({}, r)
        self.assertIn("| b2 | 2 (갈래 b1·b2·b3) |", table)

    def test_take_all_counts_every_stage_in_the_run(self):
        self.assertEqual(run(ALL)["run_threat"], 600)

    def test_take_one_gives_a_range(self):
        r = run([{"stages": ["b1", "b2", "b3"], "take": "one"}])
        self.assertIsNone(r["run_threat"])
        self.assertEqual(r["run_threat_range"], [320, 380])   # 80 + 100~160 + 140

    def test_no_drop_note_inside_a_branch(self):
        notes = " ".join(run(ALL)["notes"])
        self.assertNotIn("b2의 위협도 합이", notes)   # b2(100) < b1(160)이지만 순서가 정해져 있지 않다
        self.assertIn("s5의 위협도 합이", notes)       # s5(140) < 가장 센 갈래 b1(160)

    def test_bad_branches_are_errors(self):
        cases = {"one stage": [{"stages": ["b1"]}], "unknown": [{"stages": ["b1", "zz"]}], "not next to each other": [{"stages": ["b1", "b3"]}],
                 "overlap": [{"stages": ["b1", "b2"]}, {"stages": ["b2", "b3"]}], "bad take": [{"stages": ["b1", "b2"], "take": "some"}],
                 "not a list": {"stages": ["b1", "b2"]}}
        for name, value in cases.items():
            with self.subTest(name):
                errors = run(value)["errors"]
                self.assertTrue(errors, name)
                self.assertFalse(any("알 수 없는 키" in e["message"] for e in errors), errors)

    def test_reward_spans_do_not_cross_branch_stages(self):
        levels = [level("s1", reward="부두 보급"), level("b1"), level("b2"), level("b3"), level("s5", reward="등불")]
        pacing = {"carry_levels": True, "max_reward_load": 100}
        crossing = lambda r: [s for s in r["pacing"]["spans"] if s["kind"] == "reward" and s["level"] != s["to_level"]]   # noqa: E731
        self.assertTrue(crossing(run(levels=levels, pacing=pacing)))
        self.assertEqual(crossing(run(ALL, levels=levels, pacing=pacing)), [])

    def test_adjacent_groups_compare_with_the_strongest_stage_of_the_group_before(self):
        r = run([{"stages": ["b1", "b2"]}, {"stages": ["b3", "s5"]}])
        self.assertEqual(r["errors"], [])
        self.assertEqual(stage(r, "b3")["vs_previous"], round(120 / 160, 4))
        self.assertEqual(stage(r, "s5")["vs_previous"], round(140 / 160, 4))
        self.assertIn("b3의 위협도 합이", " ".join(r["notes"]))

    def test_the_order_note_uses_the_branch_positions(self):
        combat = {"stages": COMBAT["stages"][:4] + [{"id": "gone", "zone": 2, "status": "cut"}] + COMBAT["stages"][4:]}
        levels = [level(k) for k in ("s1", "b1", "b2", "b3")] + [level("s5", n=40)]   # 예산을 넘겨 순서 안내가 경고에 붙게 한다
        msg = next(w["message"] for w in run(ALL, levels=levels, combat=combat)["warnings"] if w["code"] == "over_budget" and w["where"].startswith("s5"))
        self.assertIn("(4 → 3)", msg)

    def test_branch_errors_are_in_the_checks_table(self):
        text = (ROOT / "skills/level-design/references/levels-format.md").read_text(encoding="utf-8")
        rows = [x for x in text.splitlines() if x.startswith("| `unknown_stage` |") or x.startswith("| `schema`")]
        self.assertTrue(any("branches" in x for x in rows), rows)

    @unittest.skipUnless(shutil.which("node"), "node가 없습니다")
    def test_the_viewer_shows_branches_variants_and_the_range(self):
        combat = {"stages": COMBAT["stages"] + [{"id": "s1_mage", "zone": 1, "variant_of": "s1"}]}
        r = run([{"stages": ["b1", "b2", "b3"], "take": "one"}], combat=combat, kill_hits={"s1": {"a": 2.0}, "s1_mage": {"a": 3.0}},
                economy={"economy": {}, "stages": [{"id": k, "duration": 60, "kills": {"a": SIZES[k]}} for k in SIZES]})
        html = (ROOT / "skills/studio-data/assets/viewer.html").read_text(encoding="utf-8")
        script = html.split("<script>", 1)[1].split("/* ---------- 시작 ---------- */", 1)[0]
        probe = ('const ds = JSON.parse(require("fs").readFileSync(0, "utf8")); const all = [];'
                 'const walk = (n) => { if (!n) return; all.push(n.textContent); }; renderLevels(ds, {all: [], byEntry: {}}).forEach(walk);'
                 'console.log(JSON.stringify(all.join("\\n")));')
        payload = json.dumps({"kind": "levels", "data": {"levels": [level(k) for k in SIZES]}, "report": r}, ensure_ascii=False)
        text = json.loads(subprocess.run(["node", "-e", SHIM + script + probe], input=payload, capture_output=True, text=True, encoding="utf-8", check=True).stdout)
        self.assertIn("2 (갈래 b1·b2·b3)", text)
        self.assertIn("s1_mage 24타", text)
        self.assertIn("판 전체 위협도 320~380", text)

    def test_docs_name_the_key(self):
        text = (ROOT / "skills/level-design/references/levels-format.md").read_text(encoding="utf-8")
        self.assertIn("`branches`", text)
        shapes = (ROOT / "skills/level-design/references/game-shapes.md").read_text(encoding="utf-8")
        self.assertIn("branches", shapes)


class SmallFixes(unittest.TestCase):
    ECONOMY = {"economy": {"time_unit": "단계"}, "stages": [{"id": k, "duration": 1} for k in SIZES]}

    def test_hits_per_unit_is_left_out_for_a_count_unit_353(self):
        hits = {k: {"a": 2.0} for k in SIZES}
        r = run(kill_hits=hits, economy=self.ECONOMY)
        self.assertIsNone(stage(r, "s1")["hits_per_unit"])
        self.assertTrue(any("단계" in n and "길이" in n for n in r["notes"]), r["notes"])

    def test_variant_stages_are_shown_354(self):
        combat = {"stages": COMBAT["stages"] + [{"id": "s1_mage", "zone": 1, "variant_of": "s1"}]}
        hits = {"s1": {"a": 2.0}, "s1_mage": {"a": 3.0}}
        r = run(kill_hits=hits, combat=combat, economy={"economy": {}, "stages": [{"id": k, "duration": 60, "kills": {"a": SIZES[k]}} for k in SIZES]})
        self.assertEqual(stage(r, "s1")["variants"], {"s1_mage": 24.0})
        self.assertIn("s1_mage 24타", lv.table({}, r))

    def test_no_kill_reward_means_no_kill_check_355(self):
        notes = run(economy=self.ECONOMY)["notes"]
        self.assertTrue(any("처치 보상" in n and "대조하지 않" in n for n in notes), notes)
        self.assertFalse(any(n.startswith("처치 수 대조: 0/") for n in notes))

    def test_leftover_shows_the_last_stage_income_356(self):
        import shutil, tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "p"
            shutil.copytree(SAMPLE, root)
            plain = next(d["report"] for d in datasets.collect([root]) if d["kind"] == "economy")
            self.assertTrue(all("last_income" not in v for v in plain["leftover"].values()))   # 단계 중에 사는 게임은 마지막 단계의 수입도 쓸 수 있다
            path = root / "data/economy.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["economy"]["purchase_timing"] = "stage_end"
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            eco = next(d["report"] for d in datasets.collect([root]) if d["kind"] == "economy")
        last = eco["stages"][-1]
        self.assertTrue(eco["leftover"])
        for k, left in eco["leftover"].items():
            with self.subTest(k):
                self.assertEqual(left["last_stage"], last["id"])
                self.assertEqual(left["before_last"], round(left["amount"] - last.get("income", {}).get(k, 0), 4))

if __name__ == "__main__":
    unittest.main()
