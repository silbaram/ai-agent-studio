"""되돌리기 3차(깨짐 규칙 빌드 9판, 2026-11-08) 현장 시험의 이슈 266~275 테스트. 표준 라이브러리 unittest만 사용한다."""
import copy
import unittest

from _studio import changes_section, ROOT, STUDIO
from test_verdict_field import CONCEPTS, codes, hyp, judge, printed, stamp, three, verdict


def events_concepts(need=6):
    data = copy.deepcopy(CONCEPTS)
    hyp(data)["sample"] = {"players": 3, "runs": 15, "events": {"missed_parry": need}}
    return data


class UncountedEvents(unittest.TestCase):
    """268번: 근거 세션이 모두 사건을 세지 않았으면 0건이 아니라 미집계로 보인다."""

    def test_no_session_counted_reads_uncounted_268(self):
        data = events_concepts()
        r = judge(three(), [verdict("unknown", criteria=stamp(data))], concepts=data)
        self.assertIn("사건 missed_parry 미집계/6(세지 않은 세션 3개)", printed(r))
        self.assertNotIn("missed_parry 0/6", printed(r))

    def test_a_counted_zero_still_reads_zero_268(self):
        data = events_concepts()
        r = judge(three(events={"missed_parry": 0}), [verdict("unknown", criteria=stamp(data))], concepts=data)
        self.assertIn("사건 missed_parry 0/6", printed(r))

    def test_some_counted_keeps_the_partial_sum_268(self):
        data = events_concepts()
        sessions = three(events={"missed_parry": 2})
        del sessions[0]["events"]
        r = judge(sessions, [verdict("unknown", criteria=stamp(data))], concepts=data)
        self.assertIn("사건 missed_parry 4/6(세지 않은 세션 1개)", printed(r))

    def test_the_holds_error_says_uncounted_too_268(self):
        data = events_concepts()
        r = judge(three(), [verdict(criteria=stamp(data))], concepts=data)
        self.assertEqual(codes(r["errors"]), ["verdict_events_short"])
        self.assertIn("missed_parry 미집계/6", r["errors"][0]["message"])

    def test_without_evidence_sessions_nothing_is_uncounted_review_5(self):
        data = events_concepts()
        r = judge([], [verdict("unknown", sessions=(), criteria=stamp(data))], concepts=data)
        self.assertIn("사건 missed_parry 0/6", printed(r))
        self.assertNotIn("미집계", printed(r))


class RetestCut(unittest.TestCase):
    """269번: 다시 시험하려고 기준을 바꿨으면 지난 판정을 바로 cut으로 둔다고 알린다."""

    def test_the_changed_criteria_message_names_the_retest_269(self):
        r = judge(three(), [verdict(criteria="00000000")])
        self.assertEqual(codes(r["warnings"]), ["verdict_criteria_changed"])
        msg = r["warnings"][0]["message"]
        self.assertIn("다시 시험", msg)
        self.assertIn("지금 cut", msg)

    def test_a_cut_verdict_waits_quietly_for_the_retest_269(self):
        r = judge(three(), [verdict("refuted", criteria="00000000", status="cut")])
        self.assertEqual((r["errors"], r["warnings"]), ([], []))


class ProposedResult(unittest.TestCase):
    """275번: 사용자가 제안과 다른 결과로 확정하면 proposed_result에 에이전트가 낸 결과를 남긴다. 낮추는 것만 받는다."""

    def test_lowering_to_unknown_is_accepted_and_shown_275(self):
        r = judge(three(), [verdict("unknown", status="approved", criteria=stamp(), proposed_result="holds")])
        self.assertEqual((r["errors"], r["warnings"]), ([], []))
        self.assertIn("parry_tempo.learn_timing: 모름 (확정, 판정 에이전트는 버팀)", printed(r))
        self.assertEqual(r["verdicts"]["parry_tempo.learn_timing"]["proposed_result"], "holds")

    def test_a_proposed_override_reads_once_review_4(self):
        r = judge(three(), [verdict("unknown", status="proposed", criteria=stamp(), proposed_result="holds")])
        self.assertIn("parry_tempo.learn_timing: 모름 (제안, 판정 에이전트는 버팀) · ", printed(r))
        self.assertNotIn("제안, 제안", printed(r))

    def test_lowering_a_refutation_is_accepted_275(self):
        r = judge(three(), [verdict("unknown", status="approved", criteria=stamp(), proposed_result="refuted")])
        self.assertEqual(r["errors"], [])
        self.assertIn("모름 (확정, 판정 에이전트는 틀림)", printed(r))

    def test_the_same_result_reads_as_before_275(self):
        r = judge(three(), [verdict(status="approved", criteria=stamp(), proposed_result="holds")])
        self.assertEqual(r["errors"], [])
        self.assertIn("parry_tempo.learn_timing: 버팀 (확정) · ", printed(r))

    def test_without_the_field_the_line_is_unchanged_275(self):
        r = judge(three(), [verdict(status="approved", criteria=stamp())])
        self.assertIsNone(r["verdicts"]["parry_tempo.learn_timing"]["proposed_result"])
        self.assertIn("parry_tempo.learn_timing: 버팀 (확정) · ", printed(r))

    def test_raising_or_flipping_needs_a_new_judgement_275(self):
        for proposed, result in (("unknown", "holds"), ("unknown", "refuted"), ("holds", "refuted"), ("refuted", "holds")):
            with self.subTest(proposed=proposed, result=result):
                r = judge(three(), [verdict(result, status="approved", criteria=stamp(), proposed_result=proposed)])
                self.assertEqual(codes(r["errors"]), ["verdict_overrides_proposal"])
                self.assertIn("다시 판정", r["errors"][0]["message"])

    def test_a_bad_value_is_a_schema_error_275(self):
        for bad in ("held", "", 1, None):
            with self.subTest(bad=bad):
                r = judge(three(), [verdict("unknown", criteria=stamp(), proposed_result=bad)])
                self.assertEqual(codes(r["errors"]), ["schema"])
                self.assertIn("proposed_result", r["errors"][0]["message"])

    def test_a_cut_verdict_is_not_held_to_the_rule_275(self):
        r = judge(three(), [verdict("holds", status="cut", criteria=stamp(), proposed_result="unknown"), verdict("unknown", criteria=stamp())])
        self.assertEqual(r["errors"], [])

    def test_the_viewer_shows_the_proposal_275(self):
        html = (STUDIO / "assets/viewer.html").read_text(encoding="utf-8")
        self.assertIn("proposed_result", html)
        self.assertIn('"판정 에이전트는 "', html)   # 상태 칸의 "판정 제안"과 겹치지 않는 말(검토 3)
        self.assertRegex(html, r'verdict_overrides_proposal: "')


class Docs(unittest.TestCase):
    """266번·267번·271번·272번·273번·274번: 문서로 고친 것. 270번은 에이전트 실수라 고치지 않는다."""

    def read(self, rel):
        return (ROOT / rel).read_text(encoding="utf-8")

    def retest(self):
        return changes_section("다시 시험할 때")

    def test_close_the_open_change_first_266(self):
        part = self.retest()
        self.assertIn("열린 변경", part)
        self.assertIn("design_changed", part)

    def test_old_verdicts_are_cut_when_the_criteria_change_269(self):
        self.assertRegex(self.retest(), r"지난 판정[^\n]*`cut`")
        self.assertRegex(self.read("skills/playtest-verdict/references/playtest-record.md"), r"`verdict_criteria_changed`[^\n]*다시 시험")

    def test_a_prototype_change_is_not_merged_into_main_specs_267(self):
        text = self.read("skills/scope-guard/SKILL.md")
        self.assertIn("--skip-specs", text)
        self.assertIn("Archive without syncing", text)

    def test_shrinking_the_sample_mid_test_271(self):
        text = changes_section("표본을 줄이자는 말이 나올 때")
        self.assertIn("표본을 줄", text)
        self.assertRegex(text, r"표본을 줄[^\n]*deviation")

    def test_a_rule_that_moves_the_metric_by_itself_272(self):
        self.assertIn("기준선", self.retest())
        self.assertIn("기준선", self.read("skills/concept-exploration/references/brief.md"))
        self.assertIn("기준선", self.read("skills/studio-data/assets/claude/studio-judge.md"))

    def test_judging_without_the_agent_has_the_same_rule_review_1(self):
        rec = self.read("skills/playtest-verdict/references/playtest-record.md")
        table = rec[rec.index("| result | 조건 |"):rec.index("## 검사 내용")]
        row = next(line for line in table.splitlines() if line.startswith("| `unknown` |"))
        self.assertIn("다른 까닭", row)   # Codex는 이 표로 판정한다
        self.assertIn("기준선", table)

    def test_the_judge_rules_do_not_pull_apart_review_2(self):
        judge_doc = self.read("skills/studio-data/assets/claude/studio-judge.md")
        rule = next(line for line in judge_doc.splitlines() if line.startswith("- **판정 기준을 바꾸지 않는다.**"))
        self.assertIn("5단계", rule)
        self.assertIn("문턱대로", rule)

    def test_a_setting_without_a_value_273(self):
        self.assertIn("값이 나오지 않", self.read("skills/concept-exploration/references/brief.md"))

    def test_events_are_re_estimated_after_a_rule_change_274(self):
        part = self.retest()
        self.assertIn("sample.events", part)
        self.assertIn("다시 어림", part)

    def test_the_override_is_documented_275(self):
        rec = self.read("skills/playtest-verdict/references/playtest-record.md")
        self.assertIn("`proposed_result`", rec)
        self.assertIn("`verdict_overrides_proposal`", rec)
        self.assertIn("proposed_result", self.read("skills/playtest-verdict/SKILL.md"))


if __name__ == "__main__":
    unittest.main()
