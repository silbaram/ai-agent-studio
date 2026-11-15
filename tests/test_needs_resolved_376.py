"""376: 플레이 전에 푼 '다음 시험 전에 풀 것'은 판정의 needs_resolved에 적고, check가 풀 것이 아니라 풀어 둔 것으로 보인다.
374: 플레이 도중 질문 뜻을 물을 때 줄 글을 플레이 전에 정해 둔다. 표준 라이브러리 unittest만 사용한다."""
import unittest

from _studio import ROOT, run_cli
from test_verdict_field import codes, judge, printed, stamp, three, verdict
from test_verdict_issues_357 import Project

WHERE = "parry_tempo.learn_timing"
DONE = "사용자 결정(2026-11-15): 4장 미만 판은 뺀다. 가설 test에 적었다"
SKILL = ROOT / "skills/playtest-verdict/SKILL.md"
RECORD = ROOT / "skills/playtest-verdict/references/playtest-record.md"
CHANGES = ROOT / "skills/playtest-verdict/references/changes.md"
JUDGE = ROOT / "skills/studio-data/assets/claude/studio-judge.md"
VIEWER = ROOT / "skills/studio-data/assets/viewer.html"


def read(path):
    return path.read_text(encoding="utf-8")


def cut(result="unknown", **over):
    return verdict(result, criteria="00000000", status="cut", cut_reason="2026-11-15 기준을 고쳐 다시 시험", **over)


def step(text, start, end):
    return text[text.index(start):text.index(end)]


class NeedsResolved(unittest.TestCase):
    def test_a_resolved_cut_need_is_shown_as_done(self):
        out = printed(judge(three(), [cut(next_needs="고른 카드가 적은 판을 어떻게 볼지", needs_resolved=DONE)]))
        self.assertNotIn(f"다음 시험 전에 풀 것({WHERE})", out)
        self.assertIn(f"풀어 둠({WHERE}): {DONE}", out)
        self.assertIn("고른 카드가 적은 판을 어떻게 볼지", out)   # 무엇을 풀었는지도 보인다
        self.assertIn("(지난 판정)", out)

    def test_a_resolved_active_need_is_shown_as_done(self):
        v = verdict("unknown", criteria=stamp(), next_needs="로그 지표를 더한다", needs_resolved=DONE)
        r = judge(three(), [v])
        self.assertEqual(r["errors"], [])
        out = printed(r)
        self.assertNotIn(f"다음 시험 전에 풀 것({WHERE})", out)
        self.assertIn(f"풀어 둠({WHERE}): {DONE}", out)
        self.assertEqual(r["next_needs"][WHERE]["resolved"], DONE)

    def test_newer_unresolved_needs_still_show(self):
        old = cut(next_needs="옛 할 일", needs_resolved=DONE)
        r = judge(three(), [old, cut(next_needs="새 할 일")])
        out = printed(r)
        self.assertIn(f"다음 시험 전에 풀 것({WHERE}): 새 할 일 (지난 판정)", out)
        self.assertNotIn("풀어 둠", out)

    def test_an_unknown_without_needs_keeps_the_resolved_line(self):
        """할 일이 없는 더 새 모름은 옛 할 일을 지우지 않는다(375). 풀어 둔 표시도 그대로 남는다."""
        r = judge(three(), [cut(next_needs="옛 할 일", needs_resolved=DONE), verdict("unknown", criteria=stamp())])
        self.assertIn(f"풀어 둠({WHERE}): {DONE}", printed(r))

    def test_a_decided_verdict_still_clears_it(self):
        r = judge(three(), [cut(next_needs="옛 할 일", needs_resolved=DONE), verdict("holds", criteria=stamp())])
        self.assertNotIn(WHERE, r["next_needs"])

    def test_it_needs_a_need_and_text(self):
        for bad in ({"needs_resolved": DONE}, {"next_needs": "할 일", "needs_resolved": ""}, {"next_needs": "할 일", "needs_resolved": 1}):
            with self.subTest(bad=bad):
                errors = judge(three(), [verdict("unknown", criteria=stamp(), **bad)])["errors"]
                self.assertIn("schema", codes(errors))
                self.assertTrue(any("needs_resolved" in e["message"] for e in errors), errors)

    def test_keep_unknown_still_shows_the_resolved_note(self):
        """검토 3: 모름으로 둔 판정에 푼 할 일이 있으면 '모름으로 둠' 줄에 함께 보인다(말없이 가려지지 않는다)."""
        v = verdict("unknown", criteria=stamp(), next_needs="옛 할 일", needs_resolved=DONE, keep_unknown="사용자 결정(2026-11-15): 모름으로 둔다")
        out = printed(judge(three(), [v]))
        self.assertIn(f"모름으로 둠({WHERE}): 사용자 결정(2026-11-15): 모름으로 둔다 · 풀어 둠: {DONE}", out)

    def test_the_judge_context_keeps_both_texts(self):
        """판정 에이전트는 무엇을 풀어야 했고 어떻게 풀었다고 적었는지 둘 다 보고 실제로 풀었는지 따진다."""
        with Project(three(), [cut(next_needs="옛 할 일", needs_resolved=DONE)]) as root:
            code, out = run_cli("hypothesis", WHERE, root)
        self.assertEqual(code, 0, out)
        self.assertIn(f"check: 풀어 둠({WHERE}): {DONE}", out)
        self.assertIn('"needs_resolved"', out)


class Docs(unittest.TestCase):
    def test_record_format_defines_the_field(self):
        row = next(l for l in read(RECORD).splitlines() if l.startswith("| `needs_resolved` |"))
        for word in ("`next_needs`", "풀어 둠", "판정 에이전트"):
            self.assertIn(word, row, word)

    def test_step_one_says_to_resolve_before_play(self):
        one = step(read(SKILL), "### 1. 플레이 전", "### 2. 플레이한 뒤")
        self.assertIn("`needs_resolved`", one)

    def test_retest_step_points_to_it(self):
        self.assertIn("needs_resolved", read(CHANGES))
        self.assertNotIn("다시 시험하기 전에 풀었는지 본다", read(CHANGES))

    def test_viewer_shows_it(self):
        self.assertIn("v.needs_resolved", read(VIEWER))


class QuestionHelp374(unittest.TestCase):
    def test_step_one_fixes_the_explanation_before_play(self):
        """검토 6: 화면 확인 목록 밖의 문단이라, 화면을 못 봐도 건너뛰지 않는다."""
        one = step(read(SKILL), "### 1. 플레이 전", "### 2. 플레이한 뒤")
        para = next(p for p in one.split("\n\n") if "설명 글" in p)
        self.assertFalse(para.lstrip().startswith("- "), para)
        self.assertNotIn("설명 글", next(l for l in one.splitlines() if l.startswith("- **질문 문장:**")))
        for word in ("플레이 전에", "답하는 법", "몇 번째 판", "`notes`"):   # 이탈 정의는 기록 형식 한 곳(367)
            self.assertIn(word, para, word)

    def test_guidance_beyond_the_text_is_a_deviation(self):
        """검토 2: 정한 글 밖의 안내는 기록 형식의 deviation 정의에 든다."""
        row = next(l for l in read(RECORD).splitlines() if l.startswith("| `notes` |"))
        self.assertIn("설명 글 밖의 안내", row)

    def test_step_two_asks_about_resolved_needs_too(self):
        """검토 1: 플레이 뒤에 적은 needs_resolved가 2단계의 질문을 건너뛰게 하지 않는다."""
        two = step(read(SKILL), "### 2. 플레이한 뒤", "### 3. 판정한다")
        para = next(p for p in two.split("\n\n") if p.startswith("기록하기 전에"))
        self.assertIn("풀어 둠", para)

    def test_gate_sentence_keeps_its_subject(self):
        """검토 4: gate 줄이 가리키는 것은 잣대다(지난 판정의 할 일은 gate 줄에 없다)."""
        self.assertIn("잣대는 `check . --fail-on-assumed`의 컨셉 gate 줄", read(SKILL))

    def test_unknown_plan_stays_for_runs_without_the_judge(self):
        """검토 7: 판정 에이전트가 없는 환경도 모름이면 부족한 것을 다음 세션 계획으로 남긴다."""
        self.assertIn("`unknown`이면 무엇이 부족했는지", read(SKILL))

    def test_judge_writes_decisions_as_the_users(self):
        line = next(l for l in read(JUDGE).splitlines() if l.startswith("부족한 것:"))
        self.assertIn("사용자가 정한다", line)

    def test_judge_checks_resolved_needs_against_the_record(self):
        self.assertIn("`needs_resolved`", read(JUDGE))


if __name__ == "__main__":
    unittest.main()
