"""확인할 때의 값(148, 166번): 이유에 적은 '(확인 값 N)'보다 경고의 값이 나빠지면 확인이 풀린다. 표준 라이브러리 unittest만 사용한다."""
import json
import unittest

from _studio import ROOT, STUDIO, common, levels as lv
import test_combat as tc
import test_economy as te
from test_grown_kill_ratio import StageRow
from test_levels import BUDGET, COMBAT, ENEMIES, THREAT, both, enc, level, run
from test_levels_field import ECONOMY
from test_levels_pacing import paced
from test_levels_recheck import Project, warning


def settle(measure, reason, worse="up", bound=2, label=None, code="reward_drought", part="e3~e2"):
    """가짜 경고 하나를 레벨 s1의 확인으로 덮어 본다."""
    w = {"code": code, "where": "s1.e3", "owner": "s1", "part": part, "message": "부담이 큽니다.", **common.measured(measure, worse, bound, label)}
    data = {"levels": [{"id": "s1", "acknowledged": {code: {part: reason}}}]}
    report = {"errors": [], "warnings": [w]}
    common.apply_acknowledged("levels", data, report)
    return report


def revived(report):
    return [w for w in report["warnings"] if "확인할 때 값" in w["message"]]


class Pinned(unittest.TestCase):
    def test_a_worse_value_turns_back_into_a_warning(self):
        r = settle(4, "의도한 구간 (확인 값 3)")
        self.assertEqual(r["acknowledged"], [])
        self.assertIn("확인할 때 값 3보다 나빠졌습니다(지금 4)", revived(r)[0]["message"])
        self.assertEqual(r["ack_notes"], [])   # 확인은 제 경고를 찾았으므로 쓰이지 않은 확인이 아니다

    def test_the_same_or_a_better_value_stays_acknowledged(self):
        for now in (3, 2.5):
            with self.subTest(now):
                r = settle(now, "의도한 구간 (확인 값 3)")
                self.assertEqual(r["warnings"], [])
                self.assertEqual(len(r["acknowledged"]), 1)

    def test_values_are_compared_at_the_written_precision(self):
        self.assertEqual(settle(58.6312, "의도 (확인 값 58.63)")["warnings"], [])
        self.assertTrue(revived(settle(58.64, "의도 (확인 값 58.63)")))

    def test_a_lower_bound_is_worse_downwards(self):
        self.assertTrue(revived(settle(60, "의도 (확인 값 70)", worse="down", bound=80)))
        self.assertEqual(settle(75, "의도 (확인 값 70)", worse="down", bound=80)["warnings"], [])

    def test_a_value_on_the_other_side_of_the_bound_is_not_the_one_acknowledged(self):
        r = settle(5, "의도 (확인 값 1)", worse="up", bound=3)   # 아래로 벗어난 것을 확인했는데 이제 위로 벗어난다
        self.assertIn("확인할 때 값 1은 지금처럼 위로 벗어난 값이 아니었습니다(지금 5)", r["warnings"][0]["message"])

    def test_a_value_on_the_bound_is_on_the_warned_side(self):
        self.assertEqual(settle(120, "사용자 결정 (확인 값 120)", bound=120)["warnings"], [])   # 백분율을 반올림하면 값이 경계와 같아질 수 있다
        self.assertEqual(settle(80, "의도 (확인 값 80)", worse="down", bound=80)["warnings"], [])
        self.assertIn("확인할 때 값 120보다 나빠졌습니다", settle(121, "의도 (확인 값 120)", bound=120)["warnings"][0]["message"])

    def test_the_revived_message_reads_naturally(self):
        message = revived(settle(4, "의도한 구간 (확인 값 3)"))[0]["message"]
        self.assertNotIn("'를", message)
        self.assertIn("확인 이유의 확인 값을 지금 값으로 고칩니다", message)

    def test_a_label_picks_the_value_of_that_measure(self):
        reason = "의도 (확인 값 버티는 타수 9) (확인 값 처치 타수 4)"
        self.assertTrue(revived(settle(5, reason, bound=3, label="처치 타수")))
        self.assertEqual(settle(4, reason, bound=3, label="처치 타수")["warnings"], [])
        self.assertEqual(settle(4, "의도 (확인 값 4)", bound=3, label="처치 타수")["warnings"], [])   # 이름 없는 값은 어느 지표에나 쓴다

    def test_without_a_value_the_acknowledgement_holds_and_a_note_says_how_to_pin_it(self):
        r = settle(4, "의도한 구간")
        self.assertEqual(r["warnings"], [])
        note = " ".join(r["ack_notes"])
        self.assertIn("값 없이 확인한 경고", note)
        self.assertIn("(확인 값 4)", note)

    def test_a_note_names_the_label_for_a_labelled_measure(self):
        self.assertIn("(확인 값 처치 타수 4)", " ".join(settle(4, "의도", bound=3, label="처치 타수")["ack_notes"]))

    def test_a_warning_without_a_value_ignores_the_marker(self):
        data = {"levels": [{"id": "s1", "acknowledged": {"time_outside_stage": {"s1": "의도 (확인 값 3)"}}}]}
        report = {"errors": [], "warnings": [{"code": "time_outside_stage", "where": "s1", "owner": "s1", "part": "s1", "message": "m"}]}
        common.apply_acknowledged("levels", data, report)
        self.assertEqual((report["warnings"], len(report["acknowledged"]), report["ack_notes"]), ([], 1, []))


class Levels(unittest.TestCase):
    def drought(self, reason=None):
        ack = {"acknowledged": {"reward_drought": {"e3~e2": reason}}} if reason else {}
        data = {"levels": list(both(level("s1", enc(reward="상자"), enc("e3", repeat=3), **ack))), "threat_budget": BUDGET, "pacing": {"max_reward_load": 2}}
        r = lv.validate(data, enemies=ENEMIES, threat=THREAT, combat=COMBAT)
        common.apply_acknowledged("levels", data, r)
        return r

    def test_a_reward_drought_that_grew_is_warned_again_148(self):
        load = warning(self.drought(), "reward_drought")["measure"]
        self.assertEqual(self.drought(f"의도한 구간 (확인 값 {common.num_text(load)})")["warnings"], [])
        self.assertTrue(revived(self.drought(f"의도한 구간 (확인 값 {common.num_text(load - 1)})")))

    def test_the_greybox_failure_that_got_worse_is_warned_again_166(self):
        def run(value, expect, acked):
            data = {"levels": both(level("s1", enc(), greybox=[{"id": "g1", "check": "대장간까지 몇 초", "expect": expect}],
                                         acknowledged={"greybox_failed": {"g1": f"의도 (확인 값 {acked})"}})), "threat_budget": BUDGET}
            r = lv.validate(data, enemies=ENEMIES, threat=THREAT, combat=COMBAT,
                            greybox_log={"g1": [{"session": "pt_1", "date": "2026-11-01", "value": value}]})
            common.apply_acknowledged("levels", data, r)
            return r
        self.assertEqual(run(71, [None, 60], 71)["warnings"], [])
        self.assertIn("확인할 때 값 71보다 나빠졌습니다(지금 999)", revived(run(999, [None, 60], 71))[0]["message"])
        self.assertTrue(revived(run(10, [30, None], 20)))   # 아래로 벗어나는 확인은 더 작아질 때 나쁘다
        self.assertEqual(run(25, [30, None], 20)["warnings"], [])

    def test_strong_runs_carry_their_length(self):
        r = paced(*both(level("s1", enc("hard", {"a": 12}, role="boss", repeat=4))), pacing={"max_strong_run": 2})
        w = warning(r, "strong_run")
        self.assertEqual((w["measure"], w["worse"], w["bound"]), (4, "up", 2))


class EveryMeasuredWarning(unittest.TestCase):
    """값을 붙인 경고마다 나빠지는 쪽과 경계가 맞는가."""

    def shape(self, w):
        return (w["worse"], w["bound"], w["measure"])

    def test_level_encounter_budget(self):
        over = warning(run(both(level("s1", enc(enemies={"a": 20})))), "over_budget")
        self.assertEqual(self.shape(over)[:2], ("up", 125))   # 허용 ±25%
        self.assertGreater(over["measure"], 125)
        under = warning(run(both(level("s1", enc(enemies={"a": 1})))), "under_budget")
        self.assertEqual(self.shape(under)[:2], ("down", 75))
        self.assertLess(under["measure"], 75)

    def test_kill_time_over_length(self):
        w = warning(StageRow().over(), "kill_time_over_length")
        self.assertEqual(self.shape(w), ("up", 1, 1.77))

    def test_time_gap(self):
        w = warning(run(both(level("s1", enc(at=0, duration=20), enc("e3", at=30, duration=30))), economy=ECONOMY), "time_gap")
        self.assertEqual(self.shape(w)[:2], ("up", 0))
        self.assertGreaterEqual(w["measure"], 10)

    def test_combat_target_names_its_metric(self):
        r = tc.validate(tc.data(targets={"normal": {"hits_to_kill": [1, 2]}}))
        w = warning(r, "target_out_of_range")
        self.assertEqual((w["worse"], w["bound"], w["measure_label"]), ("up", 2, "처치 타수"))
        low = warning(tc.validate(tc.data(targets={"normal": {"hits_to_kill": [50, None]}})), "target_out_of_range")
        self.assertEqual((low["worse"], low["bound"]), ("down", 50))

    def test_economy_purchase_target(self):
        r = te.validate(te.base(purchases=[dict(te.buy("p1", amount=50, currency="gold"), target=[0, 40])]))
        w = warning(r, "target_out_of_range")
        self.assertEqual(w["worse"], "up")
        self.assertEqual(w["bound"], 40)


class Budget(Project):
    def test_an_item_over_budget_is_warned_again_when_it_grows(self):
        def grow(attack, reason):
            def fn(d):
                d["items"][0]["stats"]["attack"] = attack
                d["items"][0]["acknowledged"] = {"over_budget": reason}
            self.edit("data/items.json", fn)
            return self.report("budget")
        r = grow(200, "사용자 결정(2026-11-12): 시작 무기를 세게 둔다")
        pct = next(a for a in r["acknowledged"] if a["code"] == "over_budget")["measure"]
        self.assertTrue(any("(확인 값" in n for n in r["ack_notes"]), r["ack_notes"])
        self.assertFalse(revived(grow(200, f"사용자 결정 (확인 값 {common.num_text(pct)})")))
        self.assertTrue(revived(grow(400, f"사용자 결정 (확인 값 {common.num_text(pct)})")))


class Docs(unittest.TestCase):
    def test_the_marker_is_documented_once(self):
        text = (STUDIO / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("(확인 값", text)
        others = [p for p in (ROOT / "skills").glob("*/SKILL.md") if p.parent.name != "studio-data" and "(확인 값" in p.read_text(encoding="utf-8")]
        self.assertEqual(others, [])


if __name__ == "__main__":
    unittest.main()
