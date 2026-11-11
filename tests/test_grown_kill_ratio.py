"""성장 반영 처치 시간 비율(238, 283번): 단계 표에 판 안 성장 빌드마다의 처치 시간 ÷ 길이를 함께 낸다. 경고의 조건은 그대로다.
표준 라이브러리 unittest만 사용한다."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from _studio import ROOT, SAMPLE, datasets, levels as lv, run_cli
from test_levels import both, enc, level, run
from test_levels_field import ECONOMY, TIMES


def grown(scale: dict, metric: str = "time_to_kill", base: dict = TIMES) -> dict:
    """빌드마다 기준 처치 시간에 배율을 곱한 값 {빌드: {단계: {적: {지표: 값}}}}."""
    return {b: {sid: {e: {metric: t * k} for e, t in foes.items()} for sid, foes in base.items()} for b, k in scale.items()}


def stage(r, sid="s1"):
    return next(s for s in r["stages"] if s["id"] == sid)


class StageRow(unittest.TestCase):
    def over(self, **extra):
        return run(both(level("s1", enc(repeat=10, enemy_repeat={"b": 1}))), kill_times=TIMES, economy=ECONOMY, **extra)

    def test_without_growth_there_is_no_value(self):
        self.assertIsNone(stage(self.over())["grown_ratio"])

    def test_the_range_over_builds_is_given(self):
        s = stage(self.over(grown_kills=grown({"blade": 0.5, "wall": 0.8})))
        self.assertEqual(s["kill_ratio"], 1.77)
        self.assertEqual(s["grown_ratio"], {"by_build": {"blade": 0.88, "wall": 1.41}, "unknown": []})   # 최소·최대와 그 빌드는 by_build에서 낸다
        self.assertEqual(lv._spread(s["grown_ratio"]), (0.88, 1.41, "blade", "wall"))

    def test_the_warning_is_kept_and_names_the_growth_range(self):
        r = self.over(grown_kills=grown({"blade": 0.5, "wall": 0.5}))
        found = [w for w in r["warnings"] if w["code"] == "kill_time_over_length"]
        self.assertEqual(len(found), 1)   # 성장으로 1배 아래가 되어도 경고는 그대로다. 빌드 가정에 판정을 맡기지 않는다
        self.assertIn("판 안 성장을 넣으면 0.88배", found[0]["message"])
        self.assertIn("빌드 2개", found[0]["message"])

    def test_growth_that_changes_nothing_does_not_claim_more(self):
        found = [w for w in self.over(grown_kills=grown({"blade": 1.0}))["warnings"] if w["code"] == "kill_time_over_length"]
        msg = found[0]["message"]
        self.assertIn("들어설 때는 기준 장비와 같습니다", msg)
        self.assertIn("단계 안 레벨업은 넣지 않은 값", msg)   # 첫 단계도 단계 안에서 레벨업한다. 성장이 못 메운다고 단정하지 않는다
        self.assertNotIn("줄지 않습니다", msg)

    def test_the_growth_value_says_it_leaves_out_level_ups_inside_the_stage(self):
        found = [w for w in self.over(grown_kills=grown({"blade": 0.5}))["warnings"] if w["code"] == "kill_time_over_length"]
        self.assertIn("단계 안 레벨업은 넣지 않은 값", found[0]["message"])

    def test_without_growth_the_warning_does_not_mention_it(self):
        found = [w for w in self.over()["warnings"] if w["code"] == "kill_time_over_length"]
        self.assertNotIn("판 안 성장을 넣으면", found[0]["message"])

    def test_a_stage_the_growth_does_not_cover_has_no_value(self):
        data = grown({"blade": 0.5})
        del data["blade"]["s1"]
        self.assertIsNone(stage(self.over(grown_kills=data))["grown_ratio"])

    def test_an_enemy_unknown_to_a_build_is_named(self):
        data = grown({"blade": 0.5})
        del data["blade"]["s1"]["b"]
        s = stage(self.over(grown_kills=data))
        self.assertEqual(s["grown_ratio"]["unknown"], ["b"])
        self.assertEqual(lv._grown_text(s), "0.83배 이상 (b 제외)")

    def test_an_enemy_the_base_column_already_names_is_not_repeated(self):
        times = {"s1": {"a": 2.0}, "s2": {"c": 3.0}}
        r = run(both(level("s1", enc(repeat=10, enemy_repeat={"b": 1}))), kill_times=times, economy=ECONOMY, grown_kills=grown({"blade": 0.5}, base=times))
        s = stage(r)
        self.assertEqual(s["kill_time_unknown"], ["b"])
        self.assertTrue(lv._grown_text(s).endswith("배 이상"))

    def test_hits_are_used_when_the_stage_counts_hits(self):
        r = run(both(level("s1", enc(repeat=10, enemy_repeat={"b": 1}))), kill_hits=TIMES, economy=ECONOMY,
                grown_kills=grown({"blade": 0.5}, "hits_to_kill"))
        s = stage(r)
        self.assertIsNotNone(s["hits_per_unit"])
        self.assertEqual(s["grown_ratio"]["by_build"]["blade"], round(s["kill_hits"] * 0.5 / s["duration"], 2))
        self.assertIn("타/", lv._grown_text(s))


class Text(unittest.TestCase):
    ROW = {"kill_ratio": 1.2, "time_unit": "초", "kill_time_unknown": []}

    def test_one_build_or_equal_values_show_one_number(self):
        g = {"by_build": {"a": 0.9, "b": 0.9}, "unknown": []}
        self.assertEqual(lv._grown_text(dict(self.ROW, grown_ratio=g)), "0.90배")

    def test_a_range_names_the_low_and_high_builds_341(self):
        g = {"by_build": {"a": 0.5, "b": 0.9}, "unknown": []}
        self.assertEqual(lv._grown_text(dict(self.ROW, grown_ratio=g)), "0.50(a)~0.90(b)배")

    def test_no_value_is_a_dash(self):
        self.assertEqual(lv._grown_text(dict(self.ROW, grown_ratio=None)), "–")


class Project(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "game"
        shutil.copytree(SAMPLE, self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def report(self):
        return next(d["report"] for d in datasets.collect([self.root]) if d["kind"] == "levels")

    def test_the_sample_stages_get_the_growth_range(self):
        rows = {s["id"]: s for s in self.report()["stages"]}
        self.assertEqual(lv._spread(rows["zone_1"]["grown_ratio"])[0], rows["zone_1"]["kill_ratio"])   # 첫 단계는 레벨 1이라 성장이 없다
        z2 = rows["zone_2"]
        low, high, _, _ = lv._spread(z2["grown_ratio"])
        self.assertEqual(len(z2["grown_ratio"]["by_build"]), 3)
        self.assertLess(high, z2["kill_ratio"])
        self.assertLessEqual(low, high)

    def test_the_table_has_the_column(self):
        code, out = run_cli("check", self.root, "--table", "levels")
        self.assertEqual(code, 0)
        head = next(x for x in out.splitlines() if x.startswith("| 단계 |"))
        self.assertIn("성장 반영(들어설 때 레벨)", head)
        row = next(x for x in out.splitlines() if x.startswith("| zone_2 |"))
        self.assertRegex(row, r"\| 0\.\d\d\(\w+\)~0\.\d\d\(\w+\)배 \|")

    def test_without_growth_the_column_is_left_out(self):
        (self.root / "data/growth.json").unlink()
        self.assertIsNone(self.report()["stages"][1]["grown_ratio"])
        out = run_cli("check", self.root, "--table", "levels")[1]
        self.assertNotIn("성장 반영", next(x for x in out.splitlines() if x.startswith("| 단계 |")))

    def test_the_check_line_names_it(self):
        out = run_cli("check", self.root / "data")[1]
        line = next(x for x in out.splitlines() if x.startswith("단계 zone_2") and "위협도 합" in x)
        self.assertIn("성장 반영", line)

    def test_a_broken_growth_file_leaves_it_out(self):
        (self.root / "data/growth.json").write_text(json.dumps({"growth": {}, "choices": [], "builds": []}), encoding="utf-8")
        self.assertIsNone(self.report()["stages"][1]["grown_ratio"])

    def growth(self, change):
        path = self.root / "data/growth.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        change(data)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def test_a_growth_file_with_errors_is_not_used(self):
        self.growth(lambda d: d["choices"][0].update(max_picks=0))   # 그 선택지만 빼고 계산하면 성장이 작게 나온다
        growth_report = next(d["report"] for d in datasets.collect([self.root]) if d["kind"] == "growth")
        self.assertTrue(growth_report["errors"] and growth_report["builds"])
        r = self.report()
        self.assertTrue(all(s["grown_ratio"] is None for s in r["stages"]))
        self.assertTrue(any("성장 반영" in n and "growth.json" in n and "오류" in n for n in r["notes"]), r["notes"])

    def test_a_stage_the_growth_leaves_out_is_explained(self):
        self.growth(lambda d: d["growth"]["level_at"].update(zone_3=None))
        r = self.report()
        self.assertIsNone(r["stages"][2]["grown_ratio"])
        self.assertIsNotNone(r["stages"][1]["grown_ratio"])
        self.assertTrue(any("성장 반영" in n and "zone_3" in n and "level_at" in n for n in r["notes"]), r["notes"])

    def test_the_sample_has_no_growth_note(self):
        self.assertFalse(any("성장 반영" in n for n in self.report()["notes"]))


SHIM = r"""
class Node { constructor(tag){this.tag=tag;this.children=[];this.attrs={};this.className="";this._text=null;this.dataset={};this.style={};
  this.classList={add(){},remove(){},toggle(){}};} append(...c){this.children.push(...c)} setAttribute(k,v){this.attrs[k]=v} addEventListener(){}
  replaceChildren(...c){this.children=c} get textContent(){return this._text ?? this.children.map(c=>c.textContent).join("")} set textContent(v){this._text=String(v);this.children=[]} }
const document={createElement:(t)=>new Node(t),createTextNode:(s)=>{const n=new Node("#text");n._text=String(s);return n},getElementById:()=>new Node("div"),querySelector:()=>null};
"""
STAGE_TABLE = r"""
const ds = JSON.parse(require("fs").readFileSync(0, "utf8"));
const tables = []; const walk = (n) => { if (!n || !n.children) return; if (n.tag === "table") tables.push(n); n.children.forEach(walk); };
renderLevels(ds, {all: [], byEntry: {}}).forEach(walk);
const rows = (t) => { const r = []; const w = (n) => { if (n.tag === "tr") r.push(n.children.map((c) => c.textContent)); else (n.children || []).forEach(w); }; w(t); return r; };
console.log(JSON.stringify(tables.map(rows).find((t) => t[0] && t[0][0] === "단계" && t[0][1] === "순서")));
"""


def viewer_stage_table(ds: dict) -> list:
    """뷰어의 레벨 구성 탭을 node에서 그려 단계 표의 칸을 읽는다. 브라우저 대신 아주 작은 DOM을 쓴다."""
    html = (ROOT / "skills/studio-data/assets/viewer.html").read_text(encoding="utf-8")
    script = html.split("<script>", 1)[1].split("/* ---------- 시작 ---------- */", 1)[0]
    payload = json.dumps({"kind": ds["kind"], "data": ds["data"], "report": ds["report"]}, ensure_ascii=False)
    done = subprocess.run(["node", "-e", SHIM + script + STAGE_TABLE], input=payload, capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(done.stdout)


def check_stage_table(text: str) -> list:
    lines = text.splitlines()
    start = next(i for i, x in enumerate(lines) if x.startswith("| 단계 | 순서 |"))
    rows = [x for x in lines[start:] if x.startswith("|")]
    rows = rows[:next((i for i, x in enumerate(rows) if i and not x.startswith(("| zone", "|---"))), len(rows))]
    return [[c.strip() for c in x.strip("|").split("|")] for x in rows if not x.startswith("|---")]


@unittest.skipUnless(shutil.which("node"), "node가 없습니다")
class ViewerCells(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "game"
        shutil.copytree(SAMPLE, self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def same_as_check(self):
        ds = next(d for d in datasets.collect([self.root]) if d["kind"] == "levels")
        shown = viewer_stage_table(ds)
        self.assertEqual(shown, check_stage_table(lv.table(ds["data"], ds["report"])))
        return shown

    def test_the_viewer_cells_match_the_check_table(self):
        shown = self.same_as_check()
        self.assertIn("성장 반영(들어설 때 레벨)", shown[0])
        self.assertRegex(shown[2][7], r"^0\.\d\d\(\w+\)~0\.\d\d\(\w+\)배$")
        self.assertIn("성장 반영(나갈 때 레벨)", shown[0])

    def test_without_growth_the_viewer_has_no_column(self):
        (self.root / "data/growth.json").unlink()
        self.assertNotIn("성장 반영(들어설 때 레벨)", self.same_as_check()[0])

    def test_a_lower_bound_and_hits_read_the_same_in_both(self):
        ds = next(d for d in datasets.collect([self.root]) if d["kind"] == "levels")
        cases = [{"grown_ratio": {"by_build": {"a": 0.7, "b": 0.5, "c": 0.7}, "unknown": ["x"]}},
                 {"grown_ratio": {"by_build": {"a": 0.5, "b": 0.5}, "unknown": ["x"]}, "kill_time_unknown": ["x"]},
                 {"grown_ratio": {"by_build": {"a": 1.25, "b": 1.0, "c": 1.0}, "unknown": []}, "kill_ratio": None, "kill_time": None, "kill_hits": 9.0, "hits_per_unit": 1.5}]
        for over in cases:
            with self.subTest(over):
                ds["report"]["stages"][1].update(over)
                self.assertEqual(viewer_stage_table(ds)[2][7], lv._grown_text(ds["report"]["stages"][1]))


class ViewerAndDocs(unittest.TestCase):

    def test_the_format_doc_explains_it(self):
        text = (ROOT / "skills/level-design/references/levels-format.md").read_text(encoding="utf-8")
        self.assertIn("성장 반영", text)
        self.assertIn("들어설 때", text)

    def test_the_skill_reads_it(self):
        text = (ROOT / "skills/level-design/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("성장 반영", text)
        self.assertIn("플레이어 스탯이 바뀌면 이 값도 바뀐다", text)   # 기준 장비 칸이 무엇에 따라 바뀌는지는 그대로 둔다


if __name__ == "__main__":
    unittest.main()
