"""이슈 297(판정 기준 이력 칸) 테스트. 고치기 전 기준을 가설의 criteria_history에 남기고 검사기가 그 지문을 맞춰 본다.
표준 라이브러리 unittest만 사용한다."""
import copy
import json
import unittest

from _studio import changes_section, common, concepts as cc, ROOT, STUDIO
from test_scope import Project
from test_verdict_field import CONCEPTS, approved, hyp, judge, printed, stamp, three, verdict

OLD_TEST = "그레이박스 적 1종 [가정], 패턴 3개 [가정], 3명 [가정]에게 5판 [가정]씩 한다"
OLDER_SIGNAL = "5판 [가정] 동안 같은 패턴에 맞는 비율이 줄지 않는다"


def with_history(*entries):
    data = copy.deepcopy(CONCEPTS)
    hyp(data)["criteria_history"] = list(entries)
    return data


def entry(before: dict, base: dict | None = None, **over) -> dict:
    """base(지금 가설)에 before를 덮어 그때 지문을 계산한 이력 항목."""
    h = dict(base or hyp(CONCEPTS))
    for k, v in before.items():
        if v is None:
            h.pop(k, None)
        else:
            h[k] = v
    e = {"date": "2026-11-09", "stamp": cc.criteria_stamp(h), "before": before, "why": "문장을 다듬음(뜻이 같음, 사용자 2026-11-09 확인)"}
    e.update(over)
    return e


def codes(r: dict, level: str = "errors") -> list:
    return [x["code"] for x in r[level]]


class HistoryChain(unittest.TestCase):
    """이력의 고치기 전 값으로 계산한 지문이 적힌 지문과 맞아야 한다. 맞지 않으면 판정 에이전트를 속이므로 오류다."""

    def test_a_true_entry_passes(self):
        r = cc.validate(with_history(entry({"test": OLD_TEST})))
        self.assertEqual([e for e in r["errors"] if "criteria_history" in e["message"] or e["code"] == "criteria_history_mismatch"], [])

    def test_a_two_step_chain_passes(self):
        newer = entry({"test": OLD_TEST})
        older = entry({"failure_signal": OLDER_SIGNAL}, base={**hyp(CONCEPTS), "test": OLD_TEST}, date="2026-11-08")
        r = cc.validate(with_history(older, newer))
        self.assertNotIn("criteria_history_mismatch", codes(r))

    def test_a_wrong_old_text_is_an_error(self):
        bad = entry({"test": OLD_TEST})
        bad["before"] = {"test": OLD_TEST + " 더"}
        r = cc.validate(with_history(bad))
        self.assertIn("criteria_history_mismatch", codes(r))

    def test_an_unrecorded_later_change_says_to_add_an_entry(self):   # 이력 뒤에 또 고치고 적지 않으면 마지막 항목이 맞지 않는다
        data = with_history(entry({"test": OLD_TEST}))
        hyp(data)["failure_signal"] = OLDER_SIGNAL + " 다시"
        msg = next(e["message"] for e in cc.validate(data)["errors"] if e["code"] == "criteria_history_mismatch")
        self.assertIn("이력 끝에 더합니다", msg)

    def test_entries_out_of_order_are_an_error(self):
        newer = entry({"test": OLD_TEST})
        older = entry({"failure_signal": OLDER_SIGNAL}, base={**hyp(CONCEPTS), "test": OLD_TEST})
        self.assertIn("criteria_history_mismatch", codes(cc.validate(with_history(newer, older))))   # 오래된 것이 앞이다

    def test_an_entry_that_changes_nothing_is_an_error(self):
        same = entry({"test": hyp(CONCEPTS)["test"].replace("[가정]", "[가정: 메모]")})   # 태그만 다르면 지문이 같다
        self.assertIn("criteria_history_mismatch", codes(cc.validate(with_history(same))))

    def test_a_field_that_did_not_exist_is_null(self):
        data = copy.deepcopy(CONCEPTS)
        h = hyp(data)
        h["builds"] = ["abc1234"]
        h["criteria_history"] = [entry({"builds": None}, base=h, why="세는 빌드를 정함(사용자 확인)")]
        self.assertNotIn("criteria_history_mismatch", codes(cc.validate(data)))

    def test_a_legacy_form_stamp_is_accepted(self):
        old_h = {**hyp(CONCEPTS), "test": OLD_TEST}
        legacy = cc.criteria_stamp(old_h, "nfc")
        self.assertNotEqual(legacy, cc.criteria_stamp(old_h))
        r = cc.validate(with_history(entry({"test": OLD_TEST}, stamp=legacy)))
        self.assertNotIn("criteria_history_mismatch", codes(r))

    def test_old_text_does_not_hold_the_gate(self):   # 이력의 예전 문장은 지난 기록이다. 태그·수치 검사와 게이트에 넣지 않는다
        r = cc.validate(with_history(entry({"test": OLD_TEST})))
        self.assertFalse([u for u in r["unverified"] if "criteria_history" in u])
        self.assertFalse([w for w in r["warnings"] if "criteria_history" in w["message"]])

    def test_the_history_does_not_change_the_stamp(self):
        before = stamp()
        self.assertEqual(stamp(with_history(entry({"test": OLD_TEST}))), before)


class HistoryFormat(unittest.TestCase):
    def errors_for(self, e) -> list:   # 형식 오류는 criteria_history_invalid다(사슬 오류 criteria_history_mismatch와 따로 본다)
        return [x["message"] for x in cc.validate(with_history(e))["errors"] if x["code"] == "criteria_history_invalid"]

    def test_each_field_is_required(self):
        good = entry({"test": OLD_TEST})
        for key in ("date", "stamp", "before", "why"):
            with self.subTest(key=key):
                self.assertTrue(self.errors_for({k: v for k, v in good.items() if k != key}))

    def test_bad_values_are_errors(self):
        good = entry({"test": OLD_TEST})
        for key, value in (("date", "11월 9일"), ("stamp", "xyz"), ("before", {}), ("before", {"pillars": "x"}), ("why", " ")):
            with self.subTest(key=key, value=value):
                self.assertTrue(self.errors_for({**good, key: value}))

    def test_history_must_be_a_list(self):
        data = copy.deepcopy(CONCEPTS)
        hyp(data)["criteria_history"] = {"date": "2026-11-09"}
        self.assertTrue(any(e["code"] == "criteria_history_invalid" and "배열" in e["message"] for e in cc.validate(data)["errors"]))

    def test_a_date_not_on_the_calendar_is_an_error(self):
        self.assertTrue(self.errors_for({**entry({"test": OLD_TEST}), "date": "2026-11-31"}))


class VerdictSide(unittest.TestCase):
    """기준이 바뀐 판정의 경고는 그때 기준이 이력에 있는지 알린다. 판정 에이전트는 이력에서 고치기 전 문장을 읽는다."""

    def test_a_verdict_on_a_recorded_stamp_points_to_the_history(self):
        e = entry({"test": OLD_TEST})
        r = judge(three(), [verdict(status="approved", criteria=e["stamp"])], concepts=with_history(e))
        msg = next(w["message"] for w in r["warnings"] if w["code"] == "verdict_criteria_changed")
        self.assertIn("criteria_history", msg)
        self.assertIn("2026-11-09", msg)
        self.assertIn("test", msg)

    def test_a_verdict_on_an_unrecorded_stamp_asks_for_the_history(self):
        data = copy.deepcopy(CONCEPTS)
        old = stamp(data)
        hyp(data)["test"] = OLD_TEST
        r = judge(three(), [verdict(status="approved", criteria=old)], concepts=data)
        msg = next(w["message"] for w in r["warnings"] if w["code"] == "verdict_criteria_changed")
        self.assertIn("criteria_history에 남깁니다", msg)

    def test_the_concepts_check_lists_hypotheses_with_history(self):
        r = cc.validate(with_history(entry({"test": OLD_TEST})))
        out = printed_concepts(r)
        self.assertIn("기준 이력: parry_tempo.learn_timing 1번(2026-11-09 test)", out)

    def test_two_entries_show_the_last_one(self):
        newer = entry({"test": OLD_TEST})
        older = entry({"failure_signal": OLDER_SIGNAL}, base={**hyp(CONCEPTS), "test": OLD_TEST}, date="2026-11-08")
        out = printed_concepts(cc.validate(with_history(older, newer)))
        self.assertIn("parry_tempo.learn_timing 2번(마지막 2026-11-09 test)", out)

    def test_the_index_carries_the_history(self):
        e = entry({"test": OLD_TEST})
        idx = cc.hypothesis_index(with_history(e))
        self.assertEqual(idx["parry_tempo"]["history"]["learn_timing"], [{"stamp": e["stamp"], "date": "2026-11-09", "fields": ["test"], "after_results": False}])


def printed_concepts(report) -> str:
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    with redirect_stdout(buf):
        cc.print_extra(report)
    return buf.getvalue()


class ReviewFixes(unittest.TestCase):
    """297번 구현의 검토에서 나온 것."""

    def test_a_reverted_concept_history_is_checked_too(self):
        bad = entry({"test": OLD_TEST})
        bad["before"] = {"test": OLD_TEST + " 더"}
        data = with_history(bad)
        approved(data)["status"] = "proposed"
        self.assertIn("criteria_history_mismatch", codes(cc.validate(data)))

    def test_a_broken_chain_is_not_quoted_to_the_judge(self):
        bad = entry({"test": OLD_TEST})
        bad["before"] = {"test": OLD_TEST + " 더"}
        data = with_history(bad)
        self.assertNotIn("learn_timing", cc.hypothesis_index(data)["parry_tempo"]["history"])
        r = judge(three(), [verdict(status="approved", criteria=bad["stamp"])], concepts=data)
        msg = next(w["message"] for w in r["warnings"] if w["code"] == "verdict_criteria_changed")
        self.assertNotIn("그때 기준은", msg)

    def test_only_the_history_field_is_skipped(self):
        data = copy.deepcopy(CONCEPTS)
        hyp(data)["criteria_history_note"] = "구간 30초 [가정]"
        r = cc.validate(data)
        self.assertTrue(any(u.startswith("parry_tempo.brief.hypotheses[0].criteria_history_note") for u in r["unverified"]))


class ScopeIgnoresRecords(Project):
    """기록의 오류(판정 기준 이력, 브리프 출처)는 범위를 흔들지 않는다. 범위 훅이 게임 편집과 archive를 막지 않는다."""

    def edit_concepts(self, change):
        path = self.root / "design/concepts.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        change(next(c for c in data["concepts"] if c["status"] == "approved"))
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return cc.validate(data, root=self.root)

    def tempo(self, c):
        return next(h for h in c["brief"]["hypotheses"] if h["id"] == "tempo_choice")

    def test_a_history_mismatch_does_not_block_scope(self):
        self.linked()
        r = self.edit_concepts(lambda c: self.tempo(c)["criteria_history"][0]["before"].update(test="다른 문장"))
        self.assertIn("criteria_history_mismatch", codes(r))
        self.assertNotIn("design_invalid", self.codes())

    def test_a_history_format_error_does_not_block_scope(self):
        self.linked()
        r = self.edit_concepts(lambda c: self.tempo(c)["criteria_history"][0].update(date="어제"))
        self.assertIn("criteria_history_invalid", codes(r))
        self.assertNotIn("design_invalid", self.codes())

    def test_a_wrong_brief_source_does_not_block_scope(self):
        self.linked()
        r = self.edit_concepts(lambda c: c["brief"]["loop"].update(moment="30초 [측정: data/nowhere.json#pt_x] 동안 막는다"))
        self.assertIn("provenance", codes(r))
        self.assertNotIn("design_invalid", self.codes())

    def test_a_brief_error_still_blocks_scope(self):
        self.linked()
        self.edit_concepts(lambda c: c["brief"].update(mvp=[]))
        self.assertIn("design_invalid", self.codes())


class Docs(unittest.TestCase):
    def read(self, rel: str) -> str:
        return (ROOT / rel).read_text(encoding="utf-8")

    def test_the_brief_documents_the_field(self):
        self.assertIn("`criteria_history`", self.read("skills/concept-exploration/references/brief.md"))
        record = self.read("skills/concept-exploration/references/concept-record.md")
        self.assertIn("`criteria_history_mismatch`", record)
        self.assertIn("`criteria_history_invalid`", record)

    def test_the_restamp_order_writes_the_history(self):
        part = changes_section("판정한 가설의 문장을 고칠 때")
        self.assertIn("criteria_history", part)

    def test_the_judge_reads_the_history(self):
        self.assertIn("criteria_history", (STUDIO / "assets/claude/studio-judge.md").read_text(encoding="utf-8"))

    def test_the_viewer_labels_the_new_code(self):
        html = (STUDIO / "assets/viewer.html").read_text(encoding="utf-8")
        self.assertIn("criteria_history_mismatch:", html)
        self.assertIn("criteria_history_invalid:", html)

    def test_scope_guard_says_records_do_not_block(self):
        self.assertIn("criteria_history", self.read("skills/scope-guard/SKILL.md"))


if __name__ == "__main__":
    unittest.main()
