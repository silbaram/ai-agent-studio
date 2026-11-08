"""회색 상자 2차와 9판 판정(2026-11-08) 현장 시험의 이슈 254~265 테스트. 표준 라이브러리 unittest만 사용한다."""
import copy
import io
import json
import re
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from _studio import ROOT, SAMPLE, STUDIO, common, concepts as cc, crafting as cr, playtests as pt, run_cli
from test_crafting import data as craft_data, track, validate as craft_validate

CONCEPTS = json.loads((SAMPLE / "design/concepts.json").read_text(encoding="utf-8"))
PLAYTESTS = json.loads((SAMPLE / "data/playtests.json").read_text(encoding="utf-8"))


def codes(entries):
    return [e["code"] for e in entries]


def approved(data):
    return next(c for c in data["concepts"] if c["status"] == "approved")


def hyp(data, hid="learn_timing"):
    return next(h for h in approved(data)["brief"]["hypotheses"] if h["id"] == hid)


def stamp(data=None, hid="learn_timing"):
    return cc.criteria_stamp(hyp(data or CONCEPTS, hid))


def session(sid="pt_a", players=("self",), runs=15, **over):
    s = {"id": sid, "date": "2026-11-08", "concept": "parry_tempo", "build": "abc1234", "players": list(players), "runs": runs,
         "observations": [{"hypothesis": "learn_timing", "value": "피격률 40% → 15%", "n": runs}]}
    s.update(over)
    return s


def verdict(result="holds", sessions=("pt_a", "pt_b", "pt_c"), status="proposed", **over):
    v = {"concept": "parry_tempo", "hypothesis": "learn_timing", "result": result, "sessions": list(sessions),
         "reason": "피격률이 줄었다", "status": status}
    v.update(over)
    return v


def judge(sessions, verdicts, concepts=None, root=None):
    return pt.validate({"playtests": sessions, "verdicts": verdicts}, cc.hypothesis_index(concepts or CONCEPTS), root=root)


def three(**over):
    return [session(f"pt_{c}", players=(c,), runs=5, **over) for c in "abc"]


def printed(result):
    buf = io.StringIO()
    with redirect_stdout(buf):
        pt.print_extra(result)
    return buf.getvalue()


class EnhancePerTarget(unittest.TestCase):
    """254번: 강화가 다음 티어를 넘는 아이템마다 경고하고, 확인은 대상(아이템)별로 받는다."""

    def test_without_a_per_item_ack_one_warning_names_them_all_254(self):
        r = craft_validate(craft_data(enhance=[track([{"cost": 1, "bonus_pct": 1.5}])]))   # a1, a2 둘 다 넘는다
        self.assertEqual(codes(r["warnings"]), ["enhance_overtakes_tier"])   # 아이템이 많아도 강화 하나에 경고 하나(검토 4)
        self.assertIn("a1, a2", r["warnings"][0]["message"])
        self.assertIn('{"enhance_overtakes_tier": {"a1": 이유}}', r["warnings"][0]["message"])

    def test_a_per_item_ack_splits_the_warning_254(self):
        d = craft_data(enhance=[track([{"cost": 1, "bonus_pct": 1.5}], acknowledged={"enhance_overtakes_tier": {"a2": "이유"}})])
        r = craft_validate(d)
        self.assertEqual([w.get("part") for w in r["warnings"]], ["a1", "a2"])
        self.assertTrue(all(w["where"] == "plus" for w in r["warnings"]))

    def test_one_item_can_be_acknowledged_alone_254(self):
        d = craft_data(enhance=[track([{"cost": 1, "bonus_pct": 1.5}], acknowledged={"enhance_overtakes_tier": {"a1": "사용자가 2026-11-07에 정함"}})])
        r = craft_validate(d)
        common.apply_acknowledged("crafting", d, r)
        self.assertEqual([w.get("part") for w in r["warnings"]], ["a2"])
        self.assertEqual([a.get("part") for a in r["acknowledged"]], ["a1"])

    def test_a_plain_reason_still_covers_every_item_254(self):
        d = craft_data(enhance=[track([{"cost": 1, "bonus_pct": 1.5}], acknowledged={"enhance_overtakes_tier": "둘 다 의도"})])
        r = craft_validate(d)
        common.apply_acknowledged("crafting", d, r)
        self.assertEqual((r["warnings"], len(r["acknowledged"])), ([], 1))   # 묶인 경고 하나를 덮는다


class CriteriaStamp(unittest.TestCase):
    """256번(245번): 판정에 기준 지문을 남기고, 판정 뒤에 가설 기준이 바뀌면 알린다."""

    def test_the_stamp_follows_the_criteria_256(self):
        data = copy.deepcopy(CONCEPTS)
        before = stamp(data)
        self.assertRegex(before, r"^[0-9a-f]{8}$")
        hyp(data)["notes"] = "기준이 아닌 칸"
        self.assertEqual(stamp(data), before)
        for key, value in (("claim", "다른 주장"), ("failure_signal", "다른 신호 [가정]"), ("test", "다른 방법"), ("sample", {"players": 1, "runs": 9})):
            with self.subTest(key):
                changed = copy.deepcopy(CONCEPTS)
                hyp(changed)[key] = value
                self.assertNotEqual(stamp(changed), before)

    def test_unicode_form_and_key_order_are_not_changes_256(self):
        import unicodedata
        data = copy.deepcopy(CONCEPTS)
        h = hyp(data)
        h["failure_signal"] = unicodedata.normalize("NFD", h["failure_signal"])
        h["sample"] = dict(reversed(list(h["sample"].items())))
        self.assertNotEqual(h["failure_signal"], hyp(CONCEPTS)["failure_signal"])
        self.assertEqual(stamp(data), stamp())

    def test_a_verdict_without_a_stamp_is_told_the_stamp_256(self):
        r = judge(three(), [verdict()])
        self.assertEqual(codes(r["warnings"]), ["verdict_criteria_missing"])
        self.assertIn(f'"criteria": "{stamp()}"', r["warnings"][0]["message"])

    def test_a_current_stamp_is_quiet_256(self):
        r = judge(three(), [verdict(criteria=stamp())])
        self.assertEqual((r["errors"], r["warnings"]), ([], []))

    def test_criteria_changed_after_the_verdict_256(self):
        data = copy.deepcopy(CONCEPTS)
        old = stamp(data)
        hyp(data)["failure_signal"] = "3판 [가정] 동안 피격률이 줄지 않는다"
        r = judge(three(), [verdict(status="approved", criteria=old)], concepts=data)
        self.assertEqual(codes(r["warnings"]), ["verdict_criteria_changed"])
        self.assertIn(stamp(data), r["warnings"][0]["message"])
        self.assertIn("parry_tempo.learn_timing", r["unverified"])   # 바뀐 기준의 확정 판정은 게이트를 넘지 못한다

    def test_a_cut_verdict_keeps_its_old_stamp_256(self):
        r = judge(three(), [verdict(status="cut", criteria="00000000"), verdict(criteria=stamp())])
        self.assertEqual(r["warnings"], [])

    def test_a_stamp_is_eight_hex_256(self):
        for bad in ("abc", "ABCDEF12", 12345678, ""):
            with self.subTest(bad):
                self.assertEqual(codes(judge(three(), [verdict(criteria=bad)])["errors"]), ["schema"])

    def test_the_sample_project_is_stamped_256(self):
        r = pt.validate(copy.deepcopy(PLAYTESTS), cc.hypothesis_index(CONCEPTS))
        self.assertEqual((r["errors"], r["warnings"]), ([], []))


class SampleEvents(unittest.TestCase):
    """257번·259번·261번(247번): 사건 수 표본을 받고, 판정 줄에 표본 기준을 함께 보인다."""

    def events_concepts(self, need=6):
        data = copy.deepcopy(CONCEPTS)
        hyp(data)["sample"] = {"players": 3, "runs": 15, "events": {"missed_parry": need}}
        return data

    def test_events_are_part_of_the_sample_257(self):
        data = self.events_concepts()
        self.assertEqual(cc.validate(data)["errors"], [])
        self.assertEqual(cc.hypothesis_index(data)["parry_tempo"]["samples"]["learn_timing"]["events"], {"missed_parry": 6})

    def test_bad_events_are_errors_257(self):
        for bad in ({}, {"Missed": 3}, {"missed": 0}, {"missed": 1.5}, ["missed"]):
            with self.subTest(bad):
                data = copy.deepcopy(CONCEPTS)
                hyp(data)["sample"] = {"runs": 9, "events": bad}
                self.assertEqual(codes(cc.validate(data)["errors"]), ["schema"])

    def test_a_wrong_sample_key_is_named_247(self):
        data = copy.deepcopy(CONCEPTS)
        hyp(data)["sample"] = {"player": 3, "runs": 15}
        r = cc.validate(data)
        self.assertEqual(codes(r["errors"]), ["schema"])
        self.assertIn("player", r["errors"][0]["message"])
        self.assertIn("'players'의 오타", r["errors"][0]["message"])   # 비슷한 이름

    def test_session_events_are_counts_257(self):
        for bad in ({"missed_parry": -1}, {"missed_parry": 1.5}, {"Missed": 1}, [1]):
            with self.subTest(bad):
                self.assertEqual(codes(judge([session(events=bad)], [])["errors"]), ["schema"])

    def test_holds_needs_the_events_257(self):
        r = judge(three(events={"missed_parry": 1}), [verdict(criteria=stamp(self.events_concepts()))], concepts=self.events_concepts())
        self.assertEqual(codes(r["errors"]), ["verdict_events_short"])
        self.assertIn("missed_parry 3/6", r["errors"][0]["message"])

    def test_enough_events_pass_257(self):
        data = self.events_concepts()
        r = judge(three(events={"missed_parry": 2}), [verdict(criteria=stamp(data))], concepts=data)
        self.assertEqual((r["errors"], r["warnings"]), ([], []))

    def test_an_uncounted_session_does_not_count_257(self):
        data = self.events_concepts()
        sessions = three(events={"missed_parry": 2})   # 세 세션이면 6건, 하나를 세지 않으면 4건
        del sessions[2]["events"]
        r = judge(sessions, [verdict(criteria=stamp(data))], concepts=data)
        self.assertEqual(codes(r["errors"]), ["verdict_events_short"])
        self.assertIn("missed_parry 4/6(세지 않은 세션 1개)", r["errors"][0]["message"])

    def test_refuted_may_rest_on_another_part_257(self):
        data = self.events_concepts()
        r = judge(three(events={"missed_parry": 1}), [verdict("refuted", criteria=stamp(data))], concepts=data)
        self.assertEqual(r["errors"], [])
        self.assertIn("사건 missed_parry 3/6", printed(r))

    def test_the_verdict_line_shows_the_sample_261(self):
        data = self.events_concepts()
        r = judge(three(events={"missed_parry": 1})[:2], [verdict("unknown", sessions=("pt_a", "pt_b"), criteria=stamp(data))], concepts=data)
        line = printed(r)
        self.assertIn("관찰한 근거 세션 2 · 10/15판 · 2/3명 · 사건 missed_parry 2/6", line)

    def test_without_a_sample_the_line_is_unchanged_261(self):
        data = copy.deepcopy(CONCEPTS)
        del hyp(data)["sample"]
        r = judge(three(), [verdict(criteria=stamp(data))], concepts=data)
        self.assertIn("관찰한 근거 세션 3 · 15판 · 3명", printed(r))


class Deviations(unittest.TestCase):
    """263번: 시험 절차를 어긴 일은 메모의 deviation으로 적고, 판정 줄에 보인다."""

    def test_a_deviation_note_is_accepted_and_shown_263(self):
        dev = {"kind": "deviation", "text": "설정 순서를 바꾸지 않았다"}
        sessions = three()
        sessions[0]["notes"] = [dev]
        sessions[1]["notes"] = [dev, {"kind": "deviation", "text": "중간 결과를 본 뒤 플레이했다"}]
        r = judge(sessions, [verdict(criteria=stamp())])
        self.assertEqual(r["errors"], [])
        self.assertIn("절차 이탈 3건", printed(r))

    def test_other_kinds_are_still_errors_263(self):
        r = judge([session(notes=[{"kind": "deviaton", "text": "x"}])], [])
        self.assertEqual(codes(r["errors"]), ["schema"])
        self.assertIn("deviation", r["errors"][0]["message"])


class ValueInSource(unittest.TestCase):
    """264번: 계산한 관찰값의 수는 결과 파일에 그대로 있어야 한다."""

    SUMMARY = ("표본: 판 3개\n  1.0배: 0.029 (쓴 수확 61) — 0-60초 n=24 0.09 · 120-180초 n=8 제외\n"
               "  2.0배: -0.077 (쓴 수확 201)\n  부화 정예 사망: 2/5 = 40%\n")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "playtests/pt_a").mkdir(parents=True)
        (self.root / "playtests/pt_a/summary.txt").write_text(self.SUMMARY, encoding="utf-8")
        (self.root / "playtests/pt_a/runs.csv").write_text("run\nr1\n", encoding="utf-8")

    def check(self, value, note="[계산: game/summarize.py]", source="playtests/pt_a/summary.txt"):
        o = {"hypothesis": "learn_timing", "value": value, "note": note, "source": source}
        return judge([session(observations=[o], logs=["playtests/pt_a/runs.csv"])], [], root=self.root)

    def test_copied_numbers_pass_264(self):
        for value in ("1배 0.029 (쓴 수확 61), 2배 -0.077 (쓴 수확 201)", "0-60초 0.09, 120-180초 제외", "2/5 = 40%", 0.029,
                      "pt_20261108_1 합침: 1배 0.029"):   # 낱말에 붙은 수(세션 id)는 보지 않는다
            with self.subTest(value):
                self.assertEqual(self.check(value)["warnings"], [])

    def test_a_number_not_in_the_file_is_warned_264(self):
        r = self.check("1배 -0.253 (쓴 수확 61)")
        self.assertEqual(codes(r["warnings"]), ["value_not_in_source"])
        self.assertIn("-0.253", r["warnings"][0]["message"])
        self.assertNotIn("61,", r["warnings"][0]["message"])

    def test_a_rounded_number_is_warned_264(self):
        for value in ("1배 0.03", "1배 0.02", "2배 -0.07"):   # 글자로는 0.029, -0.077 안에 있어도 값이 다르다
            with self.subTest(value):
                self.assertEqual(codes(self.check(value)["warnings"]), ["value_not_in_source"])

    def test_only_computed_values_with_a_result_file_are_read_264(self):
        self.assertEqual(self.check("1배 -0.253", note=None)["warnings"], [])
        self.assertEqual(codes(self.check("1배 -0.253", source="playtests/pt_a/runs.csv")["warnings"]), ["computed_without_output"])
        self.assertEqual(codes(self.check("1배 -0.253", source="playtests/pt_a/gone.txt")["warnings"]), ["source_missing"])

    def test_without_a_root_files_are_not_read_264(self):
        o = {"hypothesis": "learn_timing", "value": "-0.253", "note": "[계산: x]", "source": "playtests/pt_a/summary.txt"}
        self.assertEqual(judge([session(observations=[o])], [])["warnings"], [])


class RefutedConcept(unittest.TestCase):
    """265번: 선택한 컨셉의 가설이 틀림으로 확정되면 알리고, 게이트를 넘지 못하게 한다."""

    def test_a_confirmed_refutation_is_warned_265(self):
        r = judge(three(), [verdict("refuted", status="approved", criteria=stamp())])
        self.assertEqual(codes(r["warnings"]), ["approved_concept_refuted"])
        self.assertEqual(r["warnings"][0]["where"], "parry_tempo.learn_timing")
        self.assertEqual(r["refuted"], ["parry_tempo.learn_timing"])

    def test_a_proposal_or_another_status_is_quiet_265(self):
        self.assertEqual(judge(three(), [verdict("refuted", criteria=stamp())])["warnings"], [])
        data = copy.deepcopy(CONCEPTS)
        approved(data)["status"] = "proposed"
        r = judge(three(), [verdict("refuted", status="approved", criteria=stamp())], concepts=data)
        self.assertEqual((r["warnings"], r["refuted"]), ([], []))

    def test_the_gate_fails_on_a_refuted_hypothesis_265(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for sub in ("design", "data"):
                (root / sub).mkdir()
            (root / "design/concepts.json").write_text(json.dumps(CONCEPTS, ensure_ascii=False), encoding="utf-8")
            book = copy.deepcopy(PLAYTESTS)
            v = next(x for x in book["verdicts"] if x["hypothesis"] == "learn_timing" and x.get("status") != "cut")
            v["result"] = "refuted"
            (root / "data/playtests.json").write_text(json.dumps(book, ensure_ascii=False), encoding="utf-8")
            code, out = run_cli("check", root / "data/playtests.json", root / "design/concepts.json", "--fail-on-assumed")
        self.assertEqual(code, 1)
        self.assertIn("gate: 틀림으로 확정된 가설(선택한 컨셉): parry_tempo.learn_timing", out)
        self.assertIn("approved_concept_refuted", out)


class ReviewFixes(unittest.TestCase):
    """254~265 수정분 검토 7건."""

    def events_concepts(self):
        data = copy.deepcopy(CONCEPTS)
        hyp(data)["sample"] = {"players": 3, "runs": 15, "events": {"missed_parry": 3}}
        return data

    def test_an_event_name_no_hypothesis_counts_is_warned_1(self):
        data = self.events_concepts()
        r = judge([session(events={"missed_pary": 4})], [], concepts=data)
        self.assertEqual(codes(r["warnings"]), ["unknown_event"])
        self.assertIn("'missed_parry'의 오타", r["warnings"][0]["message"])
        self.assertEqual(judge([session(events={"missed_parry": 4})], [], concepts=data)["warnings"], [])

    def test_events_without_any_event_sample_are_warned_1(self):
        r = judge([session(events={"missed_parry": 4})], [])
        self.assertEqual(codes(r["warnings"]), ["unknown_event"])

    def test_an_unstamped_decision_does_not_pass_the_gate_2(self):
        r = judge(three(), [verdict(status="approved")])
        self.assertEqual(codes(r["warnings"]), ["verdict_criteria_missing"])
        self.assertIn("parry_tempo.learn_timing", r["unverified"])
        self.assertIn("게이트", r["warnings"][0]["message"])
        r = judge(three(), [verdict(status="approved", criteria=stamp())])
        self.assertNotIn("parry_tempo.learn_timing", r["unverified"])

    def test_an_unstamped_refutation_is_still_told_2(self):
        r = judge(three(), [verdict("refuted", status="approved")])
        self.assertEqual(sorted(codes(r["warnings"])), ["approved_concept_refuted", "verdict_criteria_missing"])
        self.assertEqual(r["refuted"], ["parry_tempo.learn_timing"])

    def test_the_check_names_the_stamp_the_judge_reads_3(self):
        r = cc.validate(copy.deepcopy(CONCEPTS))
        self.assertEqual(r["criteria"]["parry_tempo.learn_timing"], stamp())
        code, out = run_cli("check", SAMPLE / "design/concepts.json")
        self.assertIn(f"판정 기준 지문: parry_tempo.learn_timing {stamp()}", out)
        code, out = run_cli("check", SAMPLE / "design/concepts.json", "--json")
        self.assertIn(stamp(), out)

    def test_the_judge_returns_the_stamp_3(self):
        judge_doc = (STUDIO / "assets/claude/studio-judge.md").read_text(encoding="utf-8")
        self.assertIn('"criteria"', judge_doc)
        self.assertIn("판정 기준 지문", judge_doc)

    def test_dates_and_exponents_are_not_split_5(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "playtests/pt_a").mkdir(parents=True)
            (root / "playtests/pt_a/summary.txt").write_text("상관 0.029 · 비율 1e-05 · 작은 값 0.00002\n", encoding="utf-8")
            for value in ("2026-11-08 세션 합침: 0.029", "1e-05", "2026-11-08T14:28:24Z 0.029", "2e-05"):   # 2e-05는 0.00002와 같은 값이다
                with self.subTest(value):
                    o = {"hypothesis": "learn_timing", "value": value, "note": "[계산: x]", "source": "playtests/pt_a/summary.txt"}
                    self.assertEqual(judge([session(observations=[o])], [], root=root)["warnings"], [])
            o = {"hypothesis": "learn_timing", "value": "3e-05", "note": "[계산: x]", "source": "playtests/pt_a/summary.txt"}
            self.assertEqual(codes(judge([session(observations=[o])], [], root=root)["warnings"]), ["value_not_in_source"])

    def test_a_result_file_is_read_once_6(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "playtests/pt_a").mkdir(parents=True)
            (root / "playtests/pt_a/summary.txt").write_text("0.029 61\n", encoding="utf-8")
            o = {"hypothesis": "learn_timing", "value": "0.029", "note": "[계산: x]", "source": "playtests/pt_a/summary.txt"}
            sessions = [session("pt_a", observations=[o, dict(o, value="61")]), session("pt_b", observations=[dict(o)])]
            real = Path.read_text
            with mock.patch.object(Path, "read_text", autospec=True, side_effect=real) as read:
                r = judge(sessions, [], root=root)
            self.assertEqual(r["warnings"], [])
            self.assertEqual(sum(1 for c in read.call_args_list if c.args[0].name == "summary.txt"), 1)

    def test_the_sample_text_is_made_once_7(self):
        data = copy.deepcopy(CONCEPTS)
        r = judge(three(), [verdict(criteria=stamp(data))], concepts=data)
        self.assertEqual(r["verdicts"]["parry_tempo.learn_timing"]["sample_text"], "세션 3 · 15/15판 · 3/3명")
        self.assertIn("관찰한 근거 세션 3 · 15/15판 · 3/3명", printed(r))
        html = (STUDIO / "assets/viewer.html").read_text(encoding="utf-8")
        self.assertIn("sample_text", html)
        self.assertNotIn("const against", html)


class Docs(unittest.TestCase):
    """255번·258번·259번·260번·262번·263번: 문서로 고친 것."""

    def read(self, rel):
        return (ROOT / rel).read_text(encoding="utf-8")

    def test_a_delegated_decision_is_written_down_255(self):
        text = self.read("skills/stat-budget/SKILL.md")
        self.assertIn("처리를 맡겼", text)
        self.assertIn("날짜", text)

    def test_result_files_print_their_definitions_258(self):
        for rel in ("skills/playtest-verdict/SKILL.md", "skills/studio-data/assets/claude/studio-judge.md"):
            with self.subTest(rel):
                self.assertIn("정의", self.read(rel))
                self.assertIn("test", self.read(rel))

    def test_event_thresholds_are_planned_259(self):
        text = self.read("skills/concept-exploration/references/brief.md")
        self.assertIn("events", text)
        self.assertIn("닿을", text)

    def test_cut_first_when_judging_again_260(self):
        text = self.read("skills/playtest-verdict/SKILL.md")
        self.assertRegex(text, r"지난 판정을 먼저 `cut`")

    def test_pooled_values_have_a_home_262(self):
        for rel in ("skills/playtest-verdict/SKILL.md", "skills/playtest-verdict/references/playtest-record.md"):
            with self.subTest(rel):
                self.assertIn("여러 세션", self.read(rel))

    def test_deviations_and_contamination_263(self):
        self.assertIn("deviation", self.read("skills/playtest-verdict/references/playtest-record.md"))
        self.assertIn("deviation", self.read("skills/studio-data/assets/claude/studio-judge.md"))
        self.assertIn("중간 결과", self.read("skills/concept-exploration/references/brief.md"))

    def test_the_viewer_names_the_new_note_kind_263(self):
        html = (STUDIO / "assets/viewer.html").read_text(encoding="utf-8")
        self.assertRegex(html, r'note: \{[^}]*deviation: "')

    def test_the_new_codes_are_documented_256(self):
        text = self.read("skills/playtest-verdict/references/playtest-record.md")
        for code in ("verdict_criteria_missing", "verdict_criteria_changed", "verdict_events_short", "value_not_in_source", "approved_concept_refuted", "unknown_event"):
            with self.subTest(code):
                self.assertIn(f"`{code}`", text)


if __name__ == "__main__":
    unittest.main()
