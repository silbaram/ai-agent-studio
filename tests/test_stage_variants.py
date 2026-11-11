"""전투 계산의 변형 단계(variant_of): 무기나 직업마다 따로 보는 단계는 처치·버팀만 계산하고 다른 검사의 단계 순서에 들지 않는다.
표준 라이브러리 unittest만 사용한다."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from _studio import ROOT, SAMPLE, datasets, meta_sim as sm, run_cli


class Variants(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "p"
        shutil.copytree(SAMPLE, self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def combat(self, fn):
        path = self.root / "data/combat.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        fn(data)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def add_variant(self, sid="zone_1_mage", of="zone_1", at=1):
        def fn(d):
            base = next(s for s in d["stages"] if s["id"] == of) if of in {s["id"] for s in d["stages"]} else d["stages"][0]
            d["stages"].insert(at, dict(base, id=sid, variant_of=of, name="마법사만"))
        self.combat(fn)

    def reports(self):
        return {d["kind"]: d["report"] for d in datasets.collect([self.root]) if d.get("report")}

    def test_the_variant_is_computed(self):
        self.add_variant()
        rows = self.reports()["combat"]["rows"]
        self.assertTrue(any(r["stage"] == "zone_1_mage" for r in rows))
        self.assertEqual(self.reports()["combat"]["errors"], [])

    def test_it_does_not_move_the_stage_order_or_break_the_check(self):
        self.add_variant()
        r = self.reports()
        stages = {s["id"]: s for s in r["levels"]["stages"]}
        self.assertNotIn("zone_1_mage", stages)
        self.assertEqual(stages["zone_2"]["position"], 2)   # 끼운 단계 때문에 위협도 예산의 순서가 밀리지 않는다
        self.assertNotIn("level_missing", [w["code"] for w in r["growth"]["warnings"]])
        code, out = run_cli("check", self.root)
        self.assertEqual(code, 0)
        self.assertTrue(out.rstrip().endswith("→ PASS"), out[-400:])

    def test_the_meta_simulator_skips_it(self):
        self.add_variant()
        path = self.root / "data/meta_combat.json"
        cfg = sm.attach(sm.load_config(path), path.parent)
        self.assertNotIn("zone_1_mage", cfg["_combat"]["stages"])

    def test_it_must_name_a_stage_of_this_file(self):
        self.add_variant(of="zone_9")
        errors = self.reports()["combat"]["errors"]
        self.assertIn("unknown_stage", [e["code"] for e in errors])
        self.assertIn("zone_9", " ".join(e["message"] for e in errors))

    def test_a_variant_of_a_variant_is_an_error(self):
        self.add_variant()
        self.add_variant(sid="zone_1_mage_2", of="zone_1_mage", at=2)
        self.assertIn("unknown_stage", [e["code"] for e in self.reports()["combat"]["errors"]])

    def test_the_value_must_be_text(self):
        self.combat(lambda d: d["stages"][0].__setitem__("variant_of", 3))
        self.assertIn("schema", [e["code"] for e in self.reports()["combat"]["errors"]])

    def test_a_level_cannot_link_to_a_variant(self):
        self.add_variant()
        path = self.root / "data/levels.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["levels"][0]["combat_stage"] = "zone_1_mage"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        errors = self.reports()["levels"]["errors"]
        self.assertTrue(any(e["code"] == "unknown_stage" and "zone_1" in e["message"] and "변형" in e["message"] for e in errors), errors)

    def test_an_economy_stage_cannot_link_to_a_variant(self):
        self.add_variant()
        path = self.root / "data/economy.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["stages"][0]["combat_stage"] = "zone_1_mage"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        errors = self.reports()["economy"]["errors"]
        self.assertTrue(any(e["code"] == "unknown_stage" and "변형" in e["message"] for e in errors), errors)


class Docs(unittest.TestCase):
    def test_the_format_and_skill_name_the_key(self):
        fmt = (ROOT / "skills/combat-balance/references/combat-format.md").read_text(encoding="utf-8")
        self.assertIn("`variant_of`", fmt)
        skill = (ROOT / "skills/combat-balance/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("variant_of", skill)


if __name__ == "__main__":
    unittest.main()
