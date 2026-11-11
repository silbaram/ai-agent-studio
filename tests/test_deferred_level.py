"""미뤄 둔 레벨 구성 이슈(132·133·148·154·166·169·171~178) 테스트. 표준 라이브러리 unittest만 사용한다."""
import unittest

from _studio import ROOT, common, level_format, level_guide, levels as lv, section
from test_levels import BUDGET, COMBAT, ENEMIES, THREAT, both, codes, enc, level, run
from test_levels_field import notes
from test_levels_greybox import boxed, item, log, rows

PLAYTEST = ROOT / "skills/playtest-verdict"
ECONOMY_FORMAT = ROOT / "skills/economy-flow/references/economy-format.md"


class SplitKills(unittest.TestCase):
    """132: 재화 흐름 단계 여럿이 한 전투 단계를 가리키면 합만 맞춰 본 것을 참고 줄로 알린다."""
    SPLIT = {"stages": [{"id": "x", "combat_stage": "s1", "kills": {"a": 3, "b": 1}}, {"id": "y", "combat_stage": "s1", "kills": {"a": 2}},
                        {"id": "s2", "kills": {"c": 6}}]}

    def test_a_sum_over_several_economy_stages_is_named(self):
        r = run(economy=self.SPLIT)
        self.assertEqual(r["warnings"], [])
        self.assertIn("처치 수는 합으로만 맞춰 봤습니다: s1(x, y)", notes(r))

    def test_one_economy_stage_per_combat_stage_says_nothing(self):
        r = run(economy={"stages": [{"id": "s1", "kills": {"a": 5, "b": 1}}, {"id": "s2", "kills": {"c": 6}}]})
        self.assertNotIn("합으로만", notes(r))

    def test_a_stage_without_kills_is_part_of_the_split(self):   # 132번의 재현. 처치를 한 단계에 몰아도 나눈 값은 직접 정한 것이 아니다
        eco = {"stages": [{"id": "x", "combat_stage": "s1", "kills": {"a": 5, "b": 1}}, {"id": "y", "combat_stage": "s1", "duration": 30}, {"id": "s2", "kills": {"c": 6}}]}
        self.assertIn("s1(x, y)", notes(run(economy=eco)))


class CopyOut(unittest.TestCase):
    """154: 옮길 처치 수에 재화 흐름에 없는 단계를 표시한다."""

    def lines(self, economy):
        text = lv.table({}, run(economy=economy))
        return [x for x in text.split("재화 흐름 kills로 옮길 값", 1)[1].splitlines() if x.startswith("- ")]

    def test_a_stage_the_economy_does_not_have_is_marked(self):
        got = self.lines({"stages": [{"id": "s1", "kills": {"a": 5, "b": 1}}]})
        self.assertNotIn("재화 흐름에 없음", next(x for x in got if x.startswith("- s1")))
        self.assertIn("(재화 흐름에 없음)", next(x for x in got if x.startswith("- s2")))

    def test_without_an_economy_nothing_is_marked(self):
        self.assertFalse(any("재화 흐름에 없음" in x for x in self.lines(None)))

    def test_the_stage_select_shape_says_not_to_read_it(self):
        text = section(ROOT / "skills/level-design/references/game-shapes.md", "스테이지 선택형")
        self.assertIn("재화 흐름에 없음", text)


class BareLevels(unittest.TestCase):
    """172: 항목이 형식 오류로 빠진 레벨은 항목이 없는 레벨이 아니다."""

    def test_a_level_whose_only_item_is_broken_is_not_bare(self):
        r = run(both(level("s1", enc(), greybox=[item(check="")]), level("s2", enc("e2", {"c": 6}), greybox=[item("g2")])))
        self.assertIn("schema", codes(r["errors"]))
        self.assertNotIn("항목이 없는 레벨", notes(r))

    def test_a_level_without_a_list_is_still_named(self):
        self.assertIn("항목이 없는 레벨: s2", notes(boxed(item())))

    def test_only_broken_items_do_not_ask_for_a_list(self):
        r = run(both(level("s1", enc(), greybox=[item(check="")])), played_stages={"s1": 1})
        self.assertNotIn("그레이박스 확인 항목이 없습니다", notes(r))


class OtherLevelEncounter(unittest.TestCase):
    """173: 다른 레벨의 조우를 가리키면 그 레벨을 말한다."""

    def test_the_owning_level_is_named(self):
        r = boxed(item(encounter="e2"))
        msg = next(e["message"] for e in r["errors"] if e["code"] == "unknown_encounter")
        self.assertIn("레벨 s2의 조우입니다", msg)
        self.assertNotIn("e1", msg)

    def test_a_typo_still_gets_a_suggestion(self):
        r = boxed(item(encounter="e11"))
        self.assertIn("e1", next(e["message"] for e in r["errors"] if e["code"] == "unknown_encounter"))


class Rounding(unittest.TestCase):
    """175: 범위는 보이는 수로 견준다."""

    def test_float_noise_at_the_edge_is_inside(self):
        self.assertFalse(common.out_of_range(0.1 * 3, [0, 0.3]))
        self.assertFalse(common.out_of_range(0.3, [0.1 * 3, None]))
        self.assertTrue(common.out_of_range(0.31, [0, 0.3]))

    def test_a_greybox_value_at_the_edge_passes(self):
        self.assertEqual(rows(boxed(item(expect=[0, 0.3]), greybox_log=log({"value": 0.1 * 3})))[0]["status"], "passed")


class TargetOnlyAck(unittest.TestCase):
    """177b: greybox_failed는 항목마다 확인한다. 문자열 한 줄은 아무 실패도 덮지 않는다."""

    def validate(self, ack):
        data = {"levels": both(level("s1", enc(), greybox=[item(expect=[10, 20])], acknowledged={"greybox_failed": ack})), "threat_budget": BUDGET}
        r = lv.validate(data, enemies=ENEMIES, threat=THREAT, combat=COMBAT, greybox_log=log({"value": 25}))
        common.apply_acknowledged("levels", data, r)
        return r

    def test_a_string_does_not_hide_the_failure(self):
        r = self.validate("한 줄로 덮음")
        self.assertIn("greybox_failed", codes(r["warnings"]))
        msg = next(e["message"] for e in r["errors"] if e["code"] == "schema" and e["where"] == "s1")
        self.assertIn("{항목 id: 이유}", msg)

    def test_the_target_form_still_works(self):
        r = self.validate({"g1": "다음 빌드에서 고친다"})
        self.assertNotIn("greybox_failed", codes(r["warnings"]))
        self.assertEqual(r["errors"], [])

    def test_other_codes_keep_the_string_form(self):
        self.assertEqual(common.ack_reason({"acknowledged": {"kill_time_over_length": "범위 무기"}}, "kill_time_over_length", "s1"), "범위 무기")


class Docs(unittest.TestCase):
    def test_133_a_mid_stage_buy_outside_the_base_gear_is_not_reported(self):
        row = next(x for x in ECONOMY_FORMAT.read_text(encoding="utf-8").splitlines() if x.startswith("| `gear_before_purchase`"))
        self.assertIn("기준 장비에 없어도", row)

    def test_148_166_an_ack_keeps_its_value(self):
        row = next(x for x in level_format().splitlines() if x.startswith("| `status`, `provenance`, `acknowledged`"))
        self.assertIn("확인할 때의 값", row)
        self.assertIn("새 세션", row)

    def test_169_171_greybox_guidance(self):
        text = level_guide()
        self.assertIn("폭은 사용자에게 묻", text)
        self.assertIn("표에 근거가 없으면", text)
        self.assertIn("구간이 시작하는 레벨", section(ROOT / "skills/level-design/SKILL.md", "절차").split("### 6.", 1)[1])

    def test_176_the_empty_session_row_matches_the_code(self):
        row = next(x for x in (PLAYTEST / "references/playtest-record.md").read_text(encoding="utf-8").splitlines() if x.startswith("| `session_without_observations`"))
        for word in ("관찰값", "단계 기록", "groups", "greybox"):
            self.assertIn(word, row)

    def test_178_the_check_table_is_not_called_the_end(self):
        for path in (ROOT / "skills/level-design/SKILL.md", PLAYTEST / "SKILL.md"):
            self.assertNotIn("끝의 확인 표", path.read_text(encoding="utf-8"), path)

    def test_177b_the_rule_is_in_the_code_table(self):
        row = next(x for x in level_format().splitlines() if x.startswith("| `greybox_failed`"))
        self.assertIn("문자열", row)


if __name__ == "__main__":
    unittest.main()
