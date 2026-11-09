"""[결정] 현장 시험(2026-11-09)의 이슈 309~313 테스트. 표준 라이브러리 unittest만 사용한다."""
import copy
import hashlib
import json
import re
import shutil
import tempfile
import unicodedata
import unittest
from pathlib import Path

from _studio import ROOT, STUDIO, common, concepts as cc, provenance as pv, run_cli
from test_verdict_field import CONCEPTS, PLAYTESTS, approved, hyp, judge, printed, three, verdict

DECIDED = "[결정: 사용자 2026-11-09]"
SAMPLE = STUDIO / "assets/sample-project"


def old_stamp(h: dict, form: str) -> str:
    """이 고침 전에 기록한 판정의 지문. tag_kind: 가정·결정 태그를 [가정]으로 맞춘 꼴(PR #34), nfc: 그 전 꼴."""
    def norm(v):
        if isinstance(v, str):
            v = unicodedata.normalize("NFC", v)
            return re.sub(r"\[(?:가정|assumed|결정|decided)(?:\s*[:：][^\]]*)?\]", "[가정]", v) if form == "tag_kind" else v
        if isinstance(v, dict):
            return {k: norm(x) for k, x in v.items()}
        if isinstance(v, list):
            return [norm(x) for x in v]
        return v
    fields = {k: norm(h.get(k)) for k in cc.CRITERIA_KEYS}
    if "builds" in h:
        fields["builds"] = norm(h["builds"])
    return hashlib.sha256(json.dumps(fields, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:8]


def entry(r: dict, path: str) -> str | None:
    """게이트 목록에서 그 칸의 항목(남은 값 표시 포함)."""
    return next((u for u in r["unverified"] if u == path or u.startswith(path + "(")), None)


def codes(r: dict, code: str) -> list:
    return [w for w in r["warnings"] if w["code"] == code]


class TestValues309(unittest.TestCase):
    """309번: test 칸의 시험 설계 값도 사용자가 정하는 잣대다. 같은 값이 두 칸에 있으면 태그를 맞춘다."""

    def test_a_value_decided_in_one_field_and_assumed_in_another_warns_309(self):
        data = copy.deepcopy(CONCEPTS)
        h = hyp(data)
        h["failure_signal"] = f"5판 {DECIDED} 동안 같은 패턴에 맞는 비율이 줄지 않는다"
        h["test"] = "그레이박스 적 1종 [가정], 3명 [가정]에게 5판 [가정]씩"
        w = codes(cc.validate(data), "criteria_tag_mismatch")
        self.assertEqual(len(w), 1)
        self.assertIn("5판", w[0]["message"])
        self.assertIn("failure_signal", w[0]["message"])
        self.assertIn("test", w[0]["message"])
        self.assertEqual(w[0]["part"], "5판")

    def test_the_same_tag_in_both_fields_is_quiet_309(self):
        data = copy.deepcopy(CONCEPTS)
        h = hyp(data)
        h["failure_signal"] = f"5판 {DECIDED} 동안 같은 패턴에 맞는 비율이 줄지 않는다"
        h["test"] = f"그레이박스 적 1종 [가정], 3명 [가정]에게 5판 {DECIDED}씩"
        self.assertIn("5판 [가정]", h["claim"])   # 주장의 같은 값도 본다
        self.assertEqual(len(codes(cc.validate(data), "criteria_tag_mismatch")), 1)
        h["claim"] = h["claim"].replace("5판 [가정]", f"5판 {DECIDED}")
        proto = approved(data)["brief"]["prototype"]
        proto["success_criteria"] = proto["success_criteria"].replace("5판 [가정]", f"5판 {DECIDED}")   # 성공 기준의 같은 값도 본다
        self.assertEqual(codes(cc.validate(data), "criteria_tag_mismatch"), [])

    def test_two_tags_in_one_field_are_not_compared_309(self):   # 한 문장 안의 같은 수치는 다른 뜻일 수 있다(문턱 50%와 피해 비율 50%)
        data = copy.deepcopy(CONCEPTS)
        h = hyp(data)
        h["failure_signal"] = f"사망의 50% {DECIDED} 이상이 받은 피해의 50% [가정] 이상을 정예에게서 받는다"
        self.assertEqual(codes(cc.validate(data), "criteria_tag_mismatch"), [])

    def test_a_mismatch_can_be_acknowledged_309(self):
        data = copy.deepcopy(CONCEPTS)
        h = hyp(data)
        h["failure_signal"] = f"5판 {DECIDED} 동안 같은 패턴에 맞는 비율이 줄지 않는다"
        h["test"] = "그레이박스 적 1종 [가정], 3명 [가정]에게 5판 [가정]씩"
        approved(data)["acknowledged"] = {"criteria_tag_mismatch": {"5판": "test의 5판은 사람마다 판 수다"}}
        r = cc.validate(data)
        common.apply_acknowledged("concepts", data, r)
        self.assertEqual(codes(r, "criteria_tag_mismatch"), [])
        self.assertEqual([a["code"] for a in r["acknowledged"]], ["criteria_tag_mismatch"])

    def test_test_values_are_documented_as_yardsticks_309(self):
        rule = (ROOT / "skills/numeric-provenance/SKILL.md").read_text(encoding="utf-8")
        brief = (ROOT / "skills/concept-exploration/references/brief.md").read_text(encoding="utf-8")
        for text in (rule, brief):
            self.assertIn("시험 설계 값", text)
        self.assertIn("어디까지인지 묻는다", brief)


class GateDetail310(unittest.TestCase):
    """310번: 게이트 줄은 칸 안에 남은 가정 값을 함께 보인다."""

    def setUp(self):
        self.data = copy.deepcopy(CONCEPTS)
        hyp(self.data)["test"] = "구간 60초 [가정], 수확 3개 [가정] 미만 구간은 뺀다. 공격 강화만 센다 [가정]"

    def test_the_gate_entry_names_the_assumed_values_310(self):
        got = entry(cc.validate(self.data), "parry_tempo.brief.hypotheses[0].test")
        self.assertIsNotNone(got)
        for part in ("가정:", "60초", "3개", "강화만 센다"):
            self.assertIn(part, got)

    def test_tag_values_read_the_number_right_before_the_tag_310(self):
        r = pv.check_text("상관 -0.2 [가정]보다, 0.5배 [가정], 봇은 4~9% [계산: a.txt], 공격 강화만 센다 [가정]", "x", bare_numbers=True)
        self.assertEqual([(t.value, t.near) for t in r.tags],
                         [("-0.2", "-0.2"), ("0.5배", "0.5배"), ("4~9%", "4~9%"), ("", "…강화만 센다")])

    def test_the_cli_gate_line_shows_them_310(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        p = Path(tmp.name) / "concepts.json"
        p.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")
        code, out = run_cli("check", p, "--fail-on-assumed")
        self.assertEqual(code, 1)
        line = next(x for x in out.splitlines() if x.startswith("gate:") and "hypotheses[0].test" in x)
        self.assertIn("60초", line)


class VerdictText311(unittest.TestCase):
    """311번: 판정 글에 옮겨 적은 잣대 태그는 브리프와 어긋날 수 있어 보여 줄 때 뺀다. 출처는 브리프에 있다."""

    def test_next_needs_are_shown_without_yardstick_tags_311(self):
        v = verdict(result="unknown", criteria=cc.criteria_stamp(hyp(CONCEPTS)),
                    next_needs="부화가 있던 판의 사망 6건 [가정]이 필요한데 0건이다(근거 [측정: pt_a])")
        out = printed(judge(three(), [v]))
        self.assertIn("사망 6건이 필요한데", out)
        self.assertNotIn("[가정]", out)
        self.assertIn("[측정: pt_a]", out)   # 기록의 근거 표시는 그대로 둔다

    def test_the_viewer_strips_them_too_311(self):
        html = (STUDIO / "assets/viewer.html").read_text(encoding="utf-8")
        self.assertIn("withoutYardstickTags(v.next_needs)", html)

    def test_verdict_text_rule_is_documented_311(self):
        text = (ROOT / "skills/playtest-verdict/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("잣대 태그 없이", text)


class UntaggedCriteria312(unittest.TestCase):
    """312번: 판정 기준 칸(claim, failure_signal, test, 성공 기준)의 태그 없는 수치는 경고하고 게이트에서 막는다.
    지문은 출처 태그를 지운 문장으로 계산해 태그를 더하거나 바꿔도 그대로다."""

    def test_untagged_numbers_in_test_and_claim_warn_312(self):
        data = copy.deepcopy(CONCEPTS)
        h = hyp(data)
        h["claim"] = "공격 예고가 보이면 플레이어는 5판 안에 패링 타이밍을 개선한다"
        h["test"] = "설정마다 2판, 모두 6판"
        w = [x["message"] for x in codes(cc.validate(data), "untagged_number")]
        self.assertTrue(any(m.startswith("brief.hypotheses[0].test:") and "6판" in m for m in w), w)
        self.assertTrue(any(m.startswith("brief.hypotheses[0].claim:") and "5판" in m for m in w), w)

    def test_untagged_numbers_in_criteria_hold_the_gate_312(self):
        data = copy.deepcopy(CONCEPTS)
        hyp(data)["test"] = "설정마다 2판, 모두 6판"
        got = entry(cc.validate(data), "parry_tempo.brief.hypotheses[0].test")
        self.assertIsNotNone(got)
        self.assertIn("태그 없음:", got)
        self.assertIn("6판", got)

    def test_deleting_a_tag_does_not_pass_the_gate_312(self):
        data = copy.deepcopy(CONCEPTS)
        h = hyp(data)
        h["failure_signal"] = h["failure_signal"].replace(" [가정]", "")
        self.assertIsNotNone(entry(cc.validate(data), "parry_tempo.brief.hypotheses[0].failure_signal"))

    def test_numbers_outside_the_criteria_do_not_hold_the_gate_312(self):
        data = copy.deepcopy(CONCEPTS)
        approved(data)["brief"]["loop"]["moment"] = "30초 동안 세 번 막는다"
        self.assertIsNone(entry(cc.validate(data), "parry_tempo.brief.loop.moment"))

    def test_tags_do_not_change_the_stamp_312(self):
        h = {"id": "h", "claim": "x", "failure_signal": "상관 -0.2 [가정]보다 크다", "test": "설정마다 2판, 모두 6판"}
        before = cc.criteria_stamp(h)
        for field, old, new in (("test", "6판", f"6판 {DECIDED}"), ("failure_signal", "[가정]", "[측정: pt_a]"),
                                ("failure_signal", " [가정]", ""), ("test", "2판", "2판 [assumed]")):
            with self.subTest(new=new):
                changed = dict(h, **{field: h[field].replace(old, new)})
                self.assertNotEqual(changed[field], h[field])
                self.assertEqual(cc.criteria_stamp(changed), before)
        self.assertNotEqual(cc.criteria_stamp(dict(h, test="설정마다 2판, 모두 7판")), before)

    def test_stamps_recorded_in_older_forms_still_match_312(self):
        data = copy.deepcopy(CONCEPTS)
        h = hyp(data)
        h["failure_signal"] = h["failure_signal"].replace("[가정]", "[가정: 기획 의도]")
        idx = cc.hypothesis_index(data)
        for form in ("tag_kind", "nfc"):
            with self.subTest(form=form):
                old = old_stamp(h, form)
                self.assertNotEqual(old, cc.criteria_stamp(h))
                v = {"concept": "parry_tempo", "hypothesis": "learn_timing", "criteria": old}
                warnings: list = []
                restamp: dict = {}
                self.assertEqual(cc_check(v, idx, warnings, restamp), "ok")
                self.assertEqual(warnings, [])
                self.assertEqual(restamp, {"w": {"from": old, "to": cc.criteria_stamp(h)}})

    def test_a_restamped_verdict_survives_a_new_tag_312(self):   # 실제 경우: 태그가 없던 6판에 사용자의 결정을 적는다
        data = copy.deepcopy(CONCEPTS)
        h = hyp(data)
        h["test"] = "설정마다 2판, 모두 6판 [가정]"
        v = {"concept": "parry_tempo", "hypothesis": "learn_timing", "criteria": cc.criteria_stamp(h)}
        h["test"] = f"설정마다 2판 {DECIDED}, 모두 6판 {DECIDED}"
        restamp: dict = {}
        self.assertEqual(cc_check(v, cc.hypothesis_index(data), [], restamp), "ok")
        self.assertEqual(restamp, {})

    def test_an_old_stamp_with_a_new_tag_is_changed_312(self):   # 그래서 예전 꼴 지문은 태그를 더하기 전에 바꿔 둔다
        data = copy.deepcopy(CONCEPTS)
        h = hyp(data)
        h["test"] = "설정마다 2판, 모두 6판"
        v = {"concept": "parry_tempo", "hypothesis": "learn_timing", "criteria": old_stamp(h, "tag_kind")}
        h["test"] = f"설정마다 2판, 모두 6판 {DECIDED}"
        self.assertEqual(cc_check(v, cc.hypothesis_index(data), [], {}), "changed")

    def test_the_check_prints_a_restamp_note_312(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name) / "p"
        shutil.copytree(SAMPLE, root)
        concepts = json.loads((root / "design/concepts.json").read_text(encoding="utf-8"))
        h = hyp(concepts)
        plays = json.loads((root / "data/playtests.json").read_text(encoding="utf-8"))
        v = next(x for x in plays["verdicts"] if x["hypothesis"] == "learn_timing")
        v["criteria"] = old_stamp(h, "tag_kind")
        (root / "data/playtests.json").write_text(json.dumps(plays, ensure_ascii=False), encoding="utf-8")
        _, out = run_cli("check", root)
        line = next(x for x in out.splitlines() if "예전 꼴" in x)
        self.assertIn(cc.criteria_stamp(h), line)
        self.assertIn("parry_tempo.learn_timing", line)

    def test_the_sample_is_current_312(self):
        r = cc.validate(copy.deepcopy(CONCEPTS))
        self.assertEqual(codes(r, "untagged_number"), [])
        stamps = {v["hypothesis"]: v["criteria"] for v in PLAYTESTS["verdicts"]}
        self.assertEqual(stamps["learn_timing"], cc.criteria_stamp(hyp(CONCEPTS)))
        self.assertEqual(stamps["tempo_choice"], cc.criteria_stamp(hyp(CONCEPTS, "tempo_choice")))


def cc_check(v, idx, warnings, restamp):
    from _studio import playtests as pt
    return pt._check_criteria(v, "w", idx, warnings, restamp)


class DecidedHint313(unittest.TestCase):
    """313번: 태그를 안내하는 문구가 [결정]도 말한다."""

    def test_the_untagged_warning_names_decided_313(self):
        r = pv.check_text("5판 동안 본다", "x.md")
        self.assertEqual(len(r.findings), 1)
        self.assertIn("[결정: 누가 날짜]", r.findings[0].message)

    def test_the_warning_lists_distinct_numbers_313(self):   # 같은 수치가 되풀이돼도 뒤의 다른 수치를 가리지 않는다
        r = pv.check_text("앞 30초, 뒤 30초, 30초 창, 30초 전, 30초 뒤, 모두 6판", "x.md")
        self.assertIn("30초, 6판", r.findings[0].message)

    def test_the_table_error_names_decided_313(self):
        r = pv.check_text("| 값 | 출처 |\n|---|---|\n| 5판 | |", "x.md")
        self.assertTrue(any(f.level == "error" and "[결정: 누가 날짜]" in f.message for f in r.findings), r.findings)


class ReviewFixes(unittest.TestCase):
    """309~313번 검토에서 나온 것."""

    def test_ordinals_are_not_numbers(self):   # "5판째 뒤"는 순서다. 조정값이 아니라 태그도 게이트도 없다
        r = pv.check_text("사용자가 5판째 뒤에 줄였다. 3번째 설정, 2회째 판", "x.md")
        self.assertEqual(r.findings, [])
        self.assertEqual(len(pv.check_text("5판 동안 본다", "x.md").findings), 1)

    def test_the_judge_writes_thresholds_without_yardstick_tags(self):
        text = (STUDIO / "assets/claude/studio-judge.md").read_text(encoding="utf-8")
        self.assertIn("잣대 태그 없이", text)

    def test_success_criteria_is_compared_too(self):
        data = copy.deepcopy(CONCEPTS)
        h = hyp(data)
        for k in ("claim", "failure_signal", "test"):
            h[k] = h[k].replace("5판 [가정]", f"5판 {DECIDED}")
        proto = approved(data)["brief"]["prototype"]
        self.assertIn("5판 [가정]", proto["success_criteria"])
        w = codes(cc.validate(data), "criteria_tag_mismatch")
        self.assertEqual(len(w), 1)
        self.assertIn("success_criteria", w[0]["message"])
        proto["success_criteria"] = proto["success_criteria"].replace("5판 [가정]", f"5판 {DECIDED}")
        self.assertEqual(codes(cc.validate(data), "criteria_tag_mismatch"), [])

    def test_unitless_numbers_in_test_hold_the_gate(self):   # 지문이 태그를 보지 않으니 태그를 지운 -0.2도 게이트가 본다
        data = copy.deepcopy(CONCEPTS)
        hyp(data)["test"] = "봇 기준선의 상관이 -0.2보다 작은지 본다"
        r = cc.validate(data)
        self.assertIn("-0.2", entry(r, "parry_tempo.brief.hypotheses[0].test"))
        self.assertTrue(any("-0.2" in w["message"] for w in codes(r, "untagged_number")))

    def test_the_viewer_strips_tags_from_the_reason(self):
        html = (STUDIO / "assets/viewer.html").read_text(encoding="utf-8")
        self.assertIn("withoutYardstickTags(v.reason)", html)

    def test_spacing_around_a_new_tag_keeps_the_stamp(self):
        h = {"id": "h", "claim": "x", "failure_signal": "상관 -0.2 [가정]보다 크다", "test": "모두 6판씩 한다"}
        before = cc.criteria_stamp(h)
        for test in (f"모두 6판 {DECIDED} 씩 한다", f"모두 6판{DECIDED}씩 한다", f"모두 6판 {DECIDED}씩  한다"):
            with self.subTest(test=test):
                self.assertEqual(cc.criteria_stamp(dict(h, test=test)), before)

    def test_a_leading_tag_shows_the_words_after_it(self):
        data = copy.deepcopy(CONCEPTS)
        hyp(data)["test"] = "[가정] 그레이박스 적 하나로 본다"
        got = entry(cc.validate(data), "parry_tempo.brief.hypotheses[0].test")
        self.assertIn("그레이박스", got)
        self.assertNotIn("가정: )", got)

    def test_the_restamp_line_has_no_fallback_particle(self):
        r = judge(three(), [verdict(result="unknown", criteria=old_stamp(hyp(CONCEPTS), "nfc"))])
        self.assertEqual(len(r["restamp"]), 1)
        r["restamp"] = {"parry_tempo.learn_timing": {"from": "6873e71b", "to": "06ae225b"}}   # 글자로 끝나는 지문(실제 기록의 것)
        line = next(x for x in printed(r).splitlines() if "예전 꼴" in x)
        self.assertIn("6873e71b", line)
        self.assertNotIn("(는)", line)
        self.assertNotIn("(이)", line)


if __name__ == "__main__":
    unittest.main()
