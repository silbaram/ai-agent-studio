"""375: 버팀·틀림 판정은 cut으로 돌린 뒤에도 지난 판정의 '다음 시험 전에 풀 것'을 지운다. 표준 라이브러리 unittest만 사용한다."""
import unittest

from _studio import ROOT, run_cli
from test_verdict_field import judge, printed, stamp, three, verdict
from test_verdict_issues_357 import Project

LINE = "다음 시험 전에 풀 것(parry_tempo.learn_timing)"


def cut(result, **over):
    return verdict(result, criteria="00000000", status="cut", cut_reason="2026-11-15 기준을 고쳐 다시 시험", **over)


class DecidedClearsEvenWhenCut(unittest.TestCase):
    def test_a_cut_refuted_hides_the_older_needs(self):
        """옛 모름(할 일 있음) 뒤에 틀림이 나와 둘 다 cut이 되면, 옛 할 일은 이미 지나간 기준의 것이다."""
        for result in ("refuted", "holds"):
            with self.subTest(result=result):
                r = judge(three(), [cut("unknown", next_needs="3명이 4판씩"), cut(result)])
                self.assertNotIn(LINE, printed(r))
                self.assertNotIn("parry_tempo.learn_timing", r["next_needs"])

    def test_newer_needs_replace_the_older(self):
        r = judge(three(), [cut("unknown", next_needs="3명이 4판씩"), cut("unknown", next_needs="로그 지표를 더한다")])
        out = printed(r)
        self.assertIn(f"{LINE}: 로그 지표를 더한다 (지난 판정)", out)
        self.assertNotIn("3명이 4판씩", out)

    def test_needs_after_a_decided_cut_show_again(self):
        r = judge(three(), [cut("refuted"), cut("unknown", next_needs="로그 지표를 더한다")])
        self.assertIn(f"{LINE}: 로그 지표를 더한다 (지난 판정)", printed(r))

    def test_an_unknown_without_needs_keeps_the_older_needs_cut_or_not(self):
        """할 일이 없는 모름은 아직 풀리지 않은 옛 할 일을 지우지 않는다. 그 판정이 cut이든 아니든 같다."""
        old = cut("unknown", next_needs="로그 지표를 더한다")
        for newer in (cut("unknown"), verdict("unknown", criteria=stamp())):
            with self.subTest(status=newer["status"]):
                self.assertIn(f"{LINE}: 로그 지표를 더한다 (지난 판정)", printed(judge(three(), [old, newer])))

    def test_an_active_unknown_still_wins_over_cuts(self):
        r = judge(three(), [cut("unknown", next_needs="옛 할 일"), verdict("unknown", criteria=stamp(), next_needs="새 할 일")])
        out = printed(r)
        self.assertIn(f"{LINE}: 새 할 일", out)
        self.assertNotIn("옛 할 일", out)

    def test_the_judge_context_drops_the_stale_needs(self):
        """판정 에이전트가 보는 hypothesis 출력의 check: 줄에도 옛 할 일이 나오지 않는다."""
        verdicts = [cut("unknown", next_needs="3명이 4판씩"), cut("refuted")]
        with Project(three(), verdicts) as root:
            code, out = run_cli("hypothesis", "parry_tempo.learn_timing", root)
        self.assertEqual(code, 0, out)
        self.assertNotIn("check: 다음 시험 전에 풀 것", out)


class Docs(unittest.TestCase):
    def test_record_format_says_a_cut_decided_verdict_clears_it(self):
        text = (ROOT / "skills/playtest-verdict/references/playtest-record.md").read_text(encoding="utf-8")
        row = next(l for l in text.splitlines() if l.startswith("| `next_needs` |"))
        for word in ("`cut`으로 돌린 뒤에도", "더 새 판정"):
            self.assertIn(word, row, word)


if __name__ == "__main__":
    unittest.main()
