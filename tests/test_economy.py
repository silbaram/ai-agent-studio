"""재화 흐름(economy) 테스트: 단계별 수입, 구매 시점, 판 사이 재화의 판 수, 가격 출처, 남는 재화. 표준 라이브러리 unittest만 사용한다."""
import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from _studio import SAMPLE, economy as ec, run_cli

ENEMIES = {"slime": {"id": "slime", "reward": 3}, "ghost": {"id": "ghost"}, "gone": {"id": "gone", "reward": 9, "status": "cut"}}
ITEMS = {"sword": {"id": "sword", "price": 100, "rarity": "rare"},
         "cap": {"id": "cap", "price": 10, "rarity": "common"}, "boot": {"id": "boot", "price": 30, "rarity": "common"},
         "free": {"id": "free", "rarity": "common", "status": "cut"}, "rock": {"id": "rock"}}
DROPS = {"chest": {"entries": [{"item": "sword", "weight": 1}, {"rarity": "common", "weight": 1}]}}
UPGRADES = {"w1": {"id": "w1", "cost": 25}, "w2": {"id": "w2", "cost": 10}}
CRAFTING = {"crafting": {}, "enhance": [{"id": "plus", "items": ["sword"], "levels": [{"cost": 100}, {"cost": 200, "success": 0.5}]}],
            "recipes": [{"id": "forge", "inputs": [{"item": "cap"}], "output": {"item": "boot"}, "cost": 40, "success": 0.8}]}


def base(**over):
    d = {"economy": {"currencies": {"gold": {"name": "골드"}, "soul": {"name": "영혼", "carry": True}},
                     "kill_reward": "gold", "sell": {"currency": "gold", "ratio": 0.5},
                     "prices": {"items": "gold", "enhance": "gold", "recipes": "gold", "upgrades": "soul"}},
         "stages": [{"id": "s1", "duration": 100, "income": {"gold": 100}},
                    {"id": "s2", "duration": 100, "income": {"gold": 200}}],
         "purchases": []}
    for k, v in over.items():
        if k in ("currencies", "kill_reward", "sell", "prices", "leftover_max", "time_unit"):
            d["economy"][k] = v
        else:
            d[k] = v
    return copy.deepcopy(d)


def codes(entries):
    return [e["code"] for e in entries]


def validate(d, enemies=ENEMIES, items=ITEMS, drops=DROPS, upgrades=UPGRADES, crafting=CRAFTING):
    return ec.validate(d, enemies=enemies, items=items, drop_tables=drops, upgrades=upgrades, crafting=crafting)


def buy(pid, **price):
    return {"id": pid, "price": price}


class Income(unittest.TestCase):
    def test_kills_drops_and_flat_income(self):
        d = base(stages=[{"id": "s1", "duration": 50, "kills": {"slime": 10}, "drops": {"chest": 2}, "income": {"gold": 10}}])
        r = validate(d)
        self.assertEqual(r["errors"], [])
        s = r["stages"][0]
        # 처치 10 × 3 = 30, 드랍 상자당 판매 기대값 (0.5 × 100 + 0.5 × 평균(10, 30)) × 0.5 = 30 → 2개 60, 기타 10
        self.assertEqual(s["income"], {"gold": 100})
        self.assertEqual(s["sources"]["gold"], {"kills": 30, "drops": 60, "other": 10})
        self.assertEqual(s["rate"], {"gold": 2})

    def test_cumulative_income(self):
        r = validate(base())
        self.assertEqual([s["cumulative"]["gold"] for s in r["stages"]], [100, 300])

    def test_enemy_without_reward_is_warned(self):
        r = validate(base(stages=[{"id": "s1", "duration": 10, "kills": {"ghost": 5}}]))
        self.assertEqual(codes(r["warnings"]), ["reward_missing"])


class Purchases(unittest.TestCase):
    def test_purchase_times_in_plan_order(self):
        d = base(purchases=[buy("p1", amount=50, currency="gold"), buy("p2", amount=150, currency="gold"),
                            buy("p3", amount=1000, currency="gold")])
        r = validate(d)
        times = {p["id"]: p["at"] for p in r["purchases"]}
        self.assertEqual((times["p1"], times["p2"], times["p3"]), (50, 150, None))   # 100 + 2 × (t − 100) = 200 → 150
        self.assertEqual(codes(r["warnings"]), ["unaffordable"])
        self.assertEqual(r["leftover"]["gold"], {"amount": 100, "share": round(100 / 300, 4)})

    def test_carry_currency_is_counted_in_runs(self):
        d = base(stages=[{"id": "s1", "duration": 10, "income": {"soul": 5}}, {"id": "s2", "duration": 10, "income": {"soul": 5}}],
                 purchases=[buy("m1", upgrade="w1"), buy("m2", upgrade="w2")])
        r = validate(d)
        self.assertEqual([p["runs"] for p in r["purchases"]], [3, 4])   # 판당 10: 25 → 3판, 누적 35 → 4판

    def test_price_sources(self):
        d = base(purchases=[buy("i", item="sword"), buy("e", enhance="plus", level=2), buy("r", recipe="forge"), buy("u", upgrade="w1")])
        prices = {p["id"]: (p["price"], p["currency"]) for p in validate(d)["purchases"]}
        self.assertEqual(prices["i"], (100, "gold"))
        self.assertEqual(prices["e"], (500, "gold"))     # 100 + 200 / 0.5
        self.assertEqual(prices["r"], (50, "gold"))      # 40 / 0.8
        self.assertEqual(prices["u"], (25, "soul"))

    def test_enhancement_from_a_level_counts_only_the_extra_cost(self):
        d = base(purchases=[buy("e2", enhance="plus", level=2, **{"from": 1})])
        self.assertEqual(validate(d)["purchases"][0]["price"], 400)   # (100 + 400) − 100
        bad = base(purchases=[buy("e", enhance="plus", level=1, **{"from": 1})])
        self.assertEqual(codes(validate(bad)["errors"]), ["schema"])

    def test_bad_price_references(self):
        cases = [(buy("x", item="nope"), "unknown_item"), (buy("x", upgrade="nope"), "unknown_upgrade"),
                 (buy("x", enhance="plus", level=3), "schema"), (buy("x", recipe="nope"), "unknown_recipe"),
                 (buy("x", item="rock"), "price_missing"), (buy("x", amount=10, currency="ruby"), "schema")]
        for p, code in cases:
            with self.subTest(p):
                self.assertEqual(codes(validate(base(purchases=[p]))["errors"]), [code])

    def test_purchase_target_out_of_range(self):
        p = dict(buy("p1", amount=50, currency="gold"), target=[0, 40])
        r = validate(base(purchases=[p]))
        self.assertEqual(codes(r["warnings"]), ["target_out_of_range"])
        self.assertEqual(r["purchases"][0]["out_of_range"], True)

    def test_leftover_above_the_limit_is_warned(self):
        d = base(purchases=[buy("p1", amount=200, currency="gold")], leftover_max=0.2)
        r = validate(d)
        self.assertEqual(codes(r["warnings"]), ["currency_piles_up"])


class ReviewFindings(unittest.TestCase):
    """코드 검토에서 나온 문제의 회귀 테스트."""

    def test_purchase_waits_for_the_stage_that_offers_it(self):
        d = base(purchases=[dict(buy("late", amount=10, currency="gold"), after="s2"), buy("next", amount=10, currency="gold")])
        r = validate(d)
        self.assertEqual([p["at"] for p in r["purchases"]], [100, 100])   # s2가 시작하는 100에, 다음 구매도 그 뒤
        self.assertEqual(codes(validate(base(purchases=[dict(buy("x", amount=1, currency="gold"), after="nope")]))["errors"]), ["unknown_stage"])
        carry = base(purchases=[dict(buy("m", upgrade="w1"), after="s2")])
        self.assertEqual(codes(validate(carry)["errors"]), ["schema"])

    def test_upgrade_before_its_prerequisite_is_warned(self):
        ups = dict(UPGRADES, w2=dict(UPGRADES["w2"], requires=["w1"]))
        d = base(stages=[{"id": "s1", "duration": 10, "income": {"soul": 50}}], purchases=[buy("b", upgrade="w2"), buy("a", upgrade="w1")])
        r = validate(d, upgrades=ups)
        self.assertEqual(codes(r["warnings"]), ["requirement_missing"])
        d["purchases"].reverse()
        self.assertEqual(validate(d, upgrades=ups)["warnings"], [])

    def test_cut_price_sources_are_warned_and_not_bought(self):
        items = dict(ITEMS, old={"id": "old", "price": 40, "status": "cut"})
        r = validate(base(purchases=[buy("o", item="old"), buy("p", amount=50, currency="gold")]), items=items)
        self.assertEqual(codes(r["warnings"]), ["cut_referenced"])
        self.assertEqual([p["id"] for p in r["purchases"]], ["p"])
        self.assertEqual(r["purchases"][0]["at"], 50)                     # 삭제된 것에 돈을 쓰지 않았다

    def test_empty_rarity_pool_names_the_rarity(self):
        drops = {"chest": {"entries": [{"rarity": "epic", "weight": 1}]}}
        r = validate(base(stages=[{"id": "s1", "duration": 10, "drops": {"chest": 1}}]), drops=drops)
        self.assertEqual(codes(r["errors"]), ["rarity_empty"])
        self.assertIn("epic", r["errors"][0]["message"])

    def test_cut_item_in_a_drop_table_adds_no_value(self):
        items = dict(ITEMS, old={"id": "old", "price": 1000, "status": "cut"})
        drops = {"chest": {"entries": [{"item": "sword", "weight": 1}, {"item": "old", "weight": 1}]}}
        r = validate(base(stages=[{"id": "s1", "duration": 10, "drops": {"chest": 1}}]), items=items, drops=drops)
        self.assertEqual(r["stages"][0]["sources"]["gold"]["drops"], 50)   # sword 100 × 0.5만

    def test_sell_value_is_computed_once_per_table(self):
        calls = []
        original = ec.sell_value
        ec.sell_value = lambda *a, **k: calls.append(1) or original(*a, **k)
        try:
            stages = [{"id": f"s{i}", "duration": 10, "drops": {"chest": 1}} for i in range(4)]
            validate(base(stages=stages))
        finally:
            ec.sell_value = original
        self.assertEqual(len(calls), 1)

    def test_malformed_target_is_reported_even_when_unaffordable(self):
        p = dict(buy("big", amount=9999, currency="gold"), target=["soon"])
        self.assertIn("schema", codes(validate(base(purchases=[p]))["errors"]))
        p = dict(buy("ok", amount=10, currency="gold"), target=[50, 10])
        self.assertIn("schema", codes(validate(base(purchases=[p]))["errors"]))

    def test_invalid_crafting_source_is_named_not_priced(self):
        crafting = copy.deepcopy(CRAFTING)
        crafting["enhance"][0]["levels"][1] = {"cost": 200, "success": 0.5, "on_fail": "destroy"}   # replace_cost 없음
        crafting["recipes"][0]["success"] = 0
        d = base(purchases=[buy("e", enhance="plus", level=2), buy("r", recipe="forge")])
        r = validate(d, crafting=crafting)
        self.assertEqual(codes(r["errors"]), ["price_source_invalid", "price_source_invalid"])
        self.assertEqual(r["purchases"], [])


class Schema(unittest.TestCase):
    def test_bad_shapes(self):
        cases = [base(stages=[{"id": "s1", "duration": 0}]), base(stages=[{"id": "s1", "duration": 10, "income": {"ruby": 1}}]),
                 base(stages=[{"id": "s1", "duration": 10, "kills": {"slime": -1}}]), base(kill_reward="ruby"),
                 base(sell={"currency": "gold", "ratio": 2})]
        for d in cases:
            with self.subTest(d["stages"]):
                self.assertIn("schema", codes(validate(d)["errors"]))

    def test_price_source_without_currency_mapping(self):
        d = base(purchases=[buy("i", item="sword")])
        del d["economy"]["prices"]["items"]
        self.assertEqual(codes(validate(d)["errors"]), ["schema"])

    def test_unknown_enemy_and_table(self):
        d = base(stages=[{"id": "s1", "duration": 10, "kills": {"nope": 1}, "drops": {"nope_table": 1}}])
        self.assertEqual(sorted(codes(validate(d)["errors"])), ["unknown_drop_table", "unknown_enemy"])


class Unchecked(unittest.TestCase):
    def test_missing_data_is_unchecked_not_passed(self):
        d = base(stages=[{"id": "s1", "duration": 10, "kills": {"slime": 1}}], purchases=[buy("i", item="sword")])
        r = ec.validate(d, enemies=None, items=None, drop_tables=None, upgrades=None, crafting=None)
        self.assertEqual(r["errors"], [])
        self.assertEqual(sorted(r["unchecked_kinds"]), ["enemies", "items"])
        self.assertGreater(r["unchecked"], 0)


class CommandLine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "game"
        shutil.copytree(SAMPLE, self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_sample_economy_has_no_errors_or_warnings(self):
        code, out = run_cli("check", self.root, "--json")
        r = next(d["report"] for d in json.loads(out)["datasets"] if d["kind"] == "economy")
        self.assertEqual((r["errors"], r["warnings"], r["unchecked"]), ([], [], 0))
        self.assertTrue(r["stages"] and r["purchases"])

    def test_economy_file_alone_is_incomplete(self):
        code, out = run_cli("check", self.root / "data/economy.json")
        self.assertIn("INCOMPLETE", out)

    def test_table(self):
        code, out = run_cli("check", self.root, "--table")
        self.assertIn("| 단계 | 길이 |", out)
        self.assertIn("| 구매 | 재화 | 가격 |", out)


if __name__ == "__main__":
    unittest.main()
