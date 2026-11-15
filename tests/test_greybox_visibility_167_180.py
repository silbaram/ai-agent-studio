"""167·179·180번: 그레이박스 판정이 말없이 바뀌는 곳을 보이게 한다. 표준 라이브러리 unittest만 사용한다.
167: 항목을 지우면 게이트에서 빠진다는 것과 그 기록이 무엇이었는지 알린다.
179: 플레이 기록 파일을 읽지 못하면 '기록 없음'이 아니라 '기록 읽지 못함'이다.
180: 범위 안 값과 passed: false의 충돌, 앞 실패 뒤의 판정 없음, 플레이 뒤 바뀐 기대 범위."""
import unittest

from _studio import ROOT, common, levels as lv, playtests as pt
from test_levels import BUDGET, COMBAT, ENEMIES, THREAT, both, codes, enc, level
from test_levels_field import printed
from test_levels_greybox import boxed, item, log, rows
from test_levels_recheck import Project, warning

FORMAT = ROOT / "skills/level-design/references/levels-format.md"
RECORD = ROOT / "skills/playtest-verdict/references/playtest-record.md"


def read(path):
    return path.read_text(encoding="utf-8")


def two(first, last):
    """같은 항목의 기록 둘(앞 세션 pt_1, 마지막 세션 pt_2)."""
    return {"g1": [{"session": "pt_1", "date": "2026-11-01", **first}, {"session": "pt_2", "date": "2026-11-02", **last}]}


class RecordConflict180(unittest.TestCase):
    def test_a_value_and_a_written_verdict_that_disagree_warn(self):
        for rec, status in (({"value": 15, "passed": False}, "passed"), ({"value": 25, "passed": True}, "failed")):
            with self.subTest(rec=rec):
                r = boxed(item(expect=[10, 20]), greybox_log=log(rec))
                self.assertEqual(rows(r)[0]["status"], status)   # 수가 적어 둔 판정보다 앞선다(그대로)
                message = warning(r, "greybox_record_conflict")["message"]
                self.assertIn("passed", message)
                self.assertIn("10~20", message)

    def test_agreeing_records_do_not_warn(self):
        for rec in ({"value": 15, "passed": True}, {"value": 25, "passed": False}, {"value": 15}, {"passed": False}):
            with self.subTest(rec=rec):
                self.assertNotIn("greybox_record_conflict", codes(boxed(item(expect=[10, 20]), greybox_log=log(rec))["warnings"]))

    def test_without_expect_there_is_nothing_to_disagree_with(self):
        self.assertNotIn("greybox_record_conflict", codes(boxed(item(), greybox_log=log({"value": 15, "passed": False}))["warnings"]))


class EarlierFailure180(unittest.TestCase):
    def test_an_open_last_record_names_the_earlier_failure(self):
        r = boxed(item(), greybox_log=two({"passed": False}, {"value": 12}))
        self.assertEqual(rows(r)[0]["status"], "open")
        line = next(n for n in r["notes"] if "앞 기록" in n)
        for word in ("g1", "pt_1", "실패", "expect"):
            self.assertIn(word, line, word)

    def test_no_note_when_nothing_failed_before(self):
        r = boxed(item(), greybox_log=two({"passed": True}, {"value": 12}))
        self.assertFalse([n for n in r["notes"] if "앞 기록" in n])


class ExpectAtPlay180(unittest.TestCase):
    def test_a_range_changed_after_play_that_flips_the_verdict_warns(self):
        r = boxed(item(expect=[10, 30]), greybox_log=log({"value": 25, "expect": [10, 20]}))
        self.assertEqual(rows(r)[0]["status"], "passed")   # 판정은 지금 범위로 낸다
        message = warning(r, "greybox_expect_changed")["message"]
        for word in ("10~20", "10~30", "실패", "note"):
            self.assertIn(word, message, word)

    def test_a_change_that_does_not_flip_the_verdict_is_quiet(self):
        for rec in ({"value": 15, "expect": [10, 20]}, {"value": 25, "expect": [10, 30]}, {"passed": True, "expect": [1, 2]}):
            with self.subTest(rec=rec):
                self.assertNotIn("greybox_expect_changed", codes(boxed(item(expect=[10, 30]), greybox_log=log(rec))["warnings"]))

    def test_dropping_the_range_after_play_also_warns(self):
        r = boxed(item(), greybox_log=log({"value": 25, "expect": [10, 20]}))
        self.assertIn("greybox_expect_changed", codes(r["warnings"]))

    def test_it_can_be_acknowledged_per_item(self):
        data = {"levels": both(level("s1", enc(), greybox=[item(expect=[10, 30])],
                                     acknowledged={"greybox_expect_changed": {"g1": "2026-11-03 사용자 결정: 측정 오차를 보고 넓힘"}})),
                "threat_budget": BUDGET}
        r = lv.validate(data, enemies=ENEMIES, threat=THREAT, combat=COMBAT, greybox_log=log({"value": 25, "expect": [10, 20]}))
        common.apply_acknowledged("levels", data, r)
        self.assertNotIn("greybox_expect_changed", codes(r["warnings"]))
        self.assertIn("greybox_expect_changed", common.LEVEL_ACK_CODES)

    def test_the_session_record_takes_an_expect(self):
        session = {"id": "pt_20261101_1", "date": "2026-11-01", "build": "b", "players": ["a"], "runs": 1,
                   "greybox": [{"check": "g1", "value": 25, "n": 1, "expect": [10, 20]}]}
        ok = pt.validate({"playtests": [session], "verdicts": []})
        self.assertEqual([e for e in ok["errors"] if e["code"] == "schema"], [])
        for bad in ("10~20", [20, 10], [1]):
            with self.subTest(bad=bad):
                session["greybox"][0]["expect"] = bad
                errors = pt.validate({"playtests": [session], "verdicts": []})["errors"]
                self.assertTrue(any(e["code"] == "schema" and "expect" in e["message"] for e in errors), errors)


class ReviewFixes(unittest.TestCase):
    def acked(self, reason, record, expect=(10, 30)):
        data = {"levels": both(level("s1", enc(), greybox=[item(expect=list(expect))], acknowledged={"greybox_expect_changed": reason})),
                "threat_budget": BUDGET}
        r = lv.validate(data, enemies=ENEMIES, threat=THREAT, combat=COMBAT, greybox_log=log(record))
        common.apply_acknowledged("levels", data, r)
        return r

    def test_1_new_greybox_codes_are_acknowledged_per_item_only(self):
        for code in ("greybox_expect_changed", "greybox_record_conflict"):
            with self.subTest(code=code):
                self.assertIn(code, common.TARGET_ONLY_ACK_CODES)
        r = self.acked("범위를 넓혔다", {"value": 25, "expect": [10, 20]})
        self.assertIn("greybox_expect_changed", codes(r["warnings"]))   # 글 한 줄은 덮지 않는다
        self.assertTrue(any(e["code"] == "schema" and "greybox_expect_changed" in e["message"] for e in r["errors"]), r["errors"])

    def test_2_a_further_widening_after_the_ack_comes_back(self):
        held = self.acked({"g1": "사용자 결정: 넓힘 (확인 값 25)"}, {"value": 25, "expect": [10, 20]})
        self.assertNotIn("greybox_expect_changed", codes(held["warnings"]))
        back = self.acked({"g1": "사용자 결정: 넓힘 (확인 값 25)"}, {"value": 35, "expect": [10, 20]}, expect=(10, 40))
        self.assertIn("greybox_expect_changed", codes(back["warnings"]))

    def test_3_an_earlier_failure_under_its_own_range_is_named(self):
        r = boxed(item(), greybox_log=two({"value": 25, "expect": [10, 20]}, {"value": 12}))
        self.assertTrue([n for n in r["notes"] if "앞 기록" in n and "pt_1" in n], r["notes"])

    def test_5_a_record_that_contradicts_itself_is_a_conflict_not_a_range_change(self):
        r = boxed(item(), greybox_log=log({"value": 25, "passed": True, "expect": [10, 20]}))
        self.assertIn("greybox_record_conflict", codes(r["warnings"]))
        self.assertNotIn("greybox_expect_changed", codes(r["warnings"]))


class Projects(Project):
    def fail_crypt(self, d):
        for s in d["playtests"]:
            for g in s.get("greybox") or []:
                if g["check"] == "crypt_forge_buy":
                    g["value"] = 999

    def test_167_deleting_an_item_says_it_leaves_the_gate(self):
        self.edit("data/playtests.json", self.fail_crypt)
        self.edit("data/levels.json", lambda d: [lv.__setitem__("greybox", [g for g in lv.get("greybox", []) if g["id"] != "crypt_forge_buy"])
                                                  for lv in d["levels"]])
        w = next(w for w in self.report("playtests")["warnings"] if w["code"] == "unknown_reference" and "crypt_forge_buy" in w["message"])
        self.assertIn("게이트에서 빠집니다", w["message"])
        self.assertIn("값 999", w["message"])

    def test_179_an_unreadable_record_file_is_not_no_record(self):
        self.write("data/playtests.json", "{ broken")
        r = self.report("levels")
        statuses = {x["status"] for lv in r["levels"] for x in lv["greybox"]}
        self.assertEqual(statuses, {"unread"})
        out = printed(r)
        self.assertIn("기록 읽지 못함", out)
        self.assertNotIn("기록 없음", out)

    def test_4_one_broken_record_file_among_readable_ones_does_not_blank_the_rest(self):
        (self.root / "old").mkdir()
        (self.root / "old/playtests.json").write_text("{ broken", encoding="utf-8")
        from _studio import datasets
        found = datasets.collect([self.root, self.root / "old"])
        r = next(d for d in found if d["ok"] and d["kind"] == "levels")["report"]
        statuses = {x["status"] for lv in r["levels"] for x in lv["greybox"]}
        self.assertNotIn("unread", statuses)
        self.assertIn("읽지 못한 플레이 기록 파일", "\n".join(r["notes"]))

    def test_6_the_sample_shows_the_expect_at_play(self):
        import json
        data = json.loads((self.root / "data/playtests.json").read_text(encoding="utf-8"))
        self.assertTrue(any("expect" in g for s in data["playtests"] for g in s.get("greybox") or []))

    def test_180_the_expect_at_play_reaches_the_level_check(self):
        def at_play(d):
            for s in d["playtests"]:
                for g in s.get("greybox") or []:
                    if g["check"] == "crypt_forge_buy":
                        g.update(value=340, expect=[270, 350])   # 플레이 때는 통과, 지금 범위 270~330으로는 실패
        self.edit("data/playtests.json", at_play)
        self.assertIn("greybox_expect_changed", codes(self.report("levels")["warnings"]))


class Docs(unittest.TestCase):
    def test_level_format_names_the_new_codes_and_label(self):
        text = read(FORMAT)
        for word in ("`greybox_record_conflict`", "`greybox_expect_changed`", "기록 읽지 못함", "앞 기록"):
            self.assertIn(word, text, word)

    def test_record_format_has_the_expect_field_and_the_deleted_item_rule(self):
        row = next(l for l in read(RECORD).splitlines() if l.startswith("| `greybox` |"))
        for word in ("`expect`", "게이트에서 빠"):
            self.assertIn(word, row, word)


if __name__ == "__main__":
    unittest.main()
