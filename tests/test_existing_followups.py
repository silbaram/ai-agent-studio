"""기존 게임 현장 시험 뒤(343~345번): 게임 코드에 있는 수치, 방어 무시 비율, 승인 전 브리프. 표준 라이브러리 unittest만 사용한다."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from _studio import ROOT, SAMPLE, combat as cb, concepts as cc, datasets


def section(path: Path, title: str) -> str:
    text = path.read_text(encoding="utf-8")
    start = text.index(f"\n## {title}\n")
    end = text.find("\n## ", start + 1)
    return text[start:end if end != -1 else len(text)]


class Pierce(unittest.TestCase):
    """344번: 상대 방어 중 무시하는 비율(armor_pierce)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "p"
        shutil.copytree(SAMPLE, self.root)
        self.armor(10)   # 예시 적에는 방어가 없다

    def tearDown(self):
        self.tmp.cleanup()

    def armor(self, value):
        self.change("data/enemies.json", lambda d: [e["stats"].__setitem__("armor", value) for e in d["enemies"]])

    def change(self, rel, fn):
        path = self.root / rel
        data = json.loads(path.read_text(encoding="utf-8"))
        fn(data)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def report(self):
        return next(d["report"] for d in datasets.collect([self.root]) if d["kind"] == "combat")

    def rows(self):
        return {(r["stage"], r["enemy"]): r for r in self.report()["rows"]}

    def pierce(self, side, value, stat="pierce"):
        def fn(d):
            d["combat"]["stats"][side]["armor_pierce"] = stat
            if side == "player":
                for s in d["stages"]:
                    s["player"]["base"][stat] = value
        self.change("data/combat.json", fn)
        if side == "enemy":
            self.change("data/enemies.json", lambda d: [e["stats"].__setitem__(stat, value) for e in d["enemies"]])

    def test_full_pierce_is_the_same_as_no_enemy_defense(self):
        self.pierce("player", 1.0)
        pierced = self.rows()
        shutil.rmtree(self.root)
        shutil.copytree(SAMPLE, self.root)
        self.armor(0)
        bare = self.rows()
        self.assertEqual({k: r["player_hit"] for k, r in pierced.items()}, {k: r["player_hit"] for k, r in bare.items()})

    def test_half_pierce_hits_harder_than_none(self):
        before = self.rows()
        self.pierce("player", 0.5)
        after = self.rows()
        armored = [k for k in before if after[k]["player_hit"] != before[k]["player_hit"]]
        self.assertTrue(armored)
        self.assertTrue(all(after[k]["player_hit"] > before[k]["player_hit"] for k in armored))
        self.assertEqual(self.report()["errors"], [])

    def test_enemies_can_pierce_too(self):
        before = self.rows()
        self.pierce("enemy", 0.5)
        after = self.rows()
        self.assertTrue(any(after[k]["enemy_hit"] > before[k]["enemy_hit"] for k in before))

    def test_a_value_outside_zero_to_one_is_an_error(self):
        self.pierce("player", 1.5)
        errors = self.report()["errors"]
        self.assertIn("bad_stat", [e["code"] for e in errors])
        self.assertIn("pierce", " ".join(e["message"] for e in errors))

    def test_only_positive_defense_is_pierced(self):
        self.assertEqual(cb._faced(10, 0.5), 5)
        self.assertEqual(cb._faced(-4, 0.5), -4)   # 약화로 음수가 된 방어를 줄이면 무시하는 쪽이 피해를 덜 준다
        self.assertEqual(cb._faced(10, 1.5), 0)    # 계산 중에 범위를 넘어도 방어를 음수로 만들지 않는다

    def costs(self):
        entries = datasets.collect([self.root])
        data = json.loads((self.root / "data/combat.json").read_text(encoding="utf-8"))
        return cb.marginal_costs(data, **datasets.indexes(entries))["player"]["zone_1"]

    def test_pierce_gets_a_stat_cost(self):
        self.pierce("player", 0.2)
        self.assertGreater(self.costs()["pierce"], 0)

    def test_a_stat_at_its_upper_bound_keeps_its_cost(self):
        self.change("data/combat.json", lambda d: d["stages"][0]["player"]["base"].__setitem__("crit_chance", 1.0))
        self.assertIn("crit_chance", self.costs())
        self.pierce("player", 1.0)
        self.assertIn("pierce", self.costs())

    def test_a_level_up_choice_with_pierce_is_counted(self):
        self.pierce("player", 0)
        entries = datasets.collect([self.root])
        data = json.loads((self.root / "data/combat.json").read_text(encoding="utf-8"))
        prep = cb.prepare(data, **datasets.indexes(entries))
        plain, _ = cb.evaluate(prep, "zone_1", {})
        pierced, _ = cb.evaluate(prep, "zone_1", {"pierce": 0.5})
        self.assertTrue(all(b["player_hit"] > a["player_hit"] for a, b in zip(plain, pierced)))

    def test_the_format_and_skill_document_it(self):
        fmt = (ROOT / "skills/combat-balance/references/combat-format.md").read_text(encoding="utf-8")
        self.assertIn("`armor_pierce`", fmt)
        limits = section(ROOT / "skills/combat-balance/SKILL.md", "한계")
        self.assertIn("지형", limits)
        self.assertIn("아군", (ROOT / "skills/combat-balance/SKILL.md").read_text(encoding="utf-8"))   # 아군 여럿이 직업마다 다른 게임
        self.assertIn('armor_pierce: "방어 무시"', (ROOT / "skills/studio-data/assets/viewer.html").read_text(encoding="utf-8"))


class GameNumbers(unittest.TestCase):
    """343번: 수치가 게임 코드에 있는 기존 게임."""

    def test_the_source_rule_lives_in_progression_economy(self):
        rule = (ROOT / "skills/progression-economy/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("file://", rule)
        self.assertIn("만들어 내지 않는다", rule)   # 게임 파일에서 생성하면 밸런스 스킬이 고친 값이 덮인다
        self.assertIn("테스트", rule)

    def test_the_existing_game_doc_points_there(self):
        doc = ROOT / "skills/concept-exploration/references/existing-game.md"
        text = section(doc, "수치가 게임 코드에 있을 때")
        self.assertIn("progression-economy", text)
        self.assertNotIn("만들어 내지 않는다", text)   # 한 규칙은 한 곳에만
        self.assertIn("수치가 게임 코드에 있을 때", section(doc, "순서"))


class ProposedBrief(unittest.TestCase):
    """345번: 승인 전 컨셉의 브리프."""

    def test_a_proposed_brief_is_not_checked(self):
        c = {"id": "g", "name": "x", "status": "proposed", "existing_game": True, "brief": {"mvp": list("abcdefghij")}}
        r = cc.validate({"concepts": [c]})
        self.assertEqual((r["errors"], r["warnings"]), ([], []))

    def test_the_record_format_says_so(self):
        text = (ROOT / "skills/concept-exploration/references/concept-record.md").read_text(encoding="utf-8")
        row = next(x for x in text.splitlines() if x.startswith("| `brief` |"))
        self.assertIn("proposed", row)
        self.assertIn("검사하지 않", row)


if __name__ == "__main__":
    unittest.main()
