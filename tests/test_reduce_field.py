"""문서 덜어내기 현장 시험(2026-11-10, 복사본)의 이슈 331~334 테스트. 표준 라이브러리 unittest만 사용한다.

사용자가 "6판으로 줄이자"고 하자 새 세션이 잃는 것과 결과를 봤는지 묻기 전에 브리프를 고쳤고(331), 지난 판정 처리를
검사 메시지에서만 알았고(332), 이미 결과를 본 지난 세션이 줄인 표본을 혼자 채웠고(333), 세션 기록 전의 축소를 어디
남길지 몰랐다(334)."""
import copy
import unittest

from _studio import ROOT, STUDIO, changes_section
from test_verdict_field import CONCEPTS, codes, hyp, judge, session, stamp, three, verdict

CODE = "verdict_session_before_reduction"
SECTION = "표본을 줄이자는 말이 나올 때"


def reduced(date="2026-11-10", before=True):
    data = copy.deepcopy(CONCEPTS)
    hyp(data)["sample"] = {"players": 3, "runs": 15,
                           "reduced_from": {"runs": 25, "after_run": 4, "before_results": before, "date": date}}
    return data


class OlderSessionsDoNotFillAReducedSample(unittest.TestCase):
    """333. 줄인 날보다 먼저 기록한 세션은 줄이기 전에 결과가 나와 있었다. 줄인 표본을 그것으로 채우면 결과를 보고 멈춘 것과 같다."""

    def test_older_sessions_filling_the_reduced_sample_are_an_error(self):
        data = reduced()
        r = judge(three(), [verdict(criteria=stamp(data))], concepts=data)   # 세션은 2026-11-08, 줄인 날은 2026-11-10
        self.assertEqual(codes(r["errors"]), [CODE])
        msg = r["errors"][0]["message"]
        for words in ("pt_a", "2026-11-10", "모름"):
            self.assertIn(words, msg)

    def test_sessions_from_the_reduction_day_on_are_fine(self):   # 그날 플레이하다 줄였다(levelup_felt의 경우)
        data = reduced(date="2026-11-08")
        self.assertEqual(judge(three(), [verdict(criteria=stamp(data))], concepts=data)["errors"], [])

    def test_only_the_older_sessions_are_named(self):
        data = reduced()
        sessions = three()[:2] + [session("pt_new", players=("c",), runs=5, date="2026-11-11")]
        r = judge(sessions, [verdict(sessions=("pt_a", "pt_b", "pt_new"), criteria=stamp(data))], concepts=data)
        self.assertEqual(codes(r["errors"]), [CODE])
        self.assertNotIn("pt_new", r["errors"][0]["message"])

    def test_meeting_the_original_sample_is_fine(self):   # 줄이기 전 표본도 채웠으면 줄인 것이 판정을 바꾸지 않았다
        data = reduced()
        sessions = [session(f"pt_{c}", players=(c,), runs=9) for c in "abc"]   # 27판 >= 줄이기 전 25판
        self.assertEqual(judge(sessions, [verdict(criteria=stamp(data))], concepts=data)["errors"], [])

    def test_unknown_and_cut_verdicts_are_not_blocked(self):
        data = reduced()
        self.assertEqual(judge(three(), [verdict("unknown", criteria=stamp(data))], concepts=data)["errors"], [])
        self.assertEqual(judge(three(), [verdict(criteria=stamp(data), status="cut")], concepts=data)["errors"], [])

    def test_it_is_documented_and_labelled(self):
        record = (ROOT / "skills/playtest-verdict/references/playtest-record.md").read_text(encoding="utf-8")
        self.assertIn(f"| `{CODE}` | 오류 |", record)
        self.assertIn(f"{CODE}:", (STUDIO / "assets/viewer.html").read_text(encoding="utf-8"))


class TheSectionSaysSo(unittest.TestCase):
    def part(self) -> str:
        return changes_section(SECTION)

    def test_a_request_is_not_the_decision_331(self):
        part = self.part()
        self.assertIn("결정이 아니다", part)
        self.assertIn("요약 값을 봤는지", part)
        self.assertIn("답을 받기 전에는 고치지 않는다", part)

    def test_old_verdicts_point_to_the_retest_step_332(self):
        part = self.part()
        self.assertIn("](#다시-시험할-때)", part)   # 같은 파일 안의 링크는 test_doc_slimming이 확인한다
        self.assertIn("`cut`", part)
        self.assertIn("`criteria_history`", part)

    def test_seen_sessions_do_not_fill_it_333(self):
        part = self.part()
        self.assertIn("줄인 날보다 먼저 기록한 세션", part)
        self.assertIn(f"`{CODE}`", part)

    def test_where_the_note_goes_and_who_saw_334(self):
        part = self.part()
        self.assertIn("세션 기록이 아직 없으면", part)
        self.assertIn("누구라도", part)


class ReviewFixes(unittest.TestCase):
    """331~334 수정의 검토에서 나온 것."""

    def part(self) -> str:
        return changes_section(SECTION)

    def item(self, words: str) -> str:
        return next(line for line in self.part().splitlines() if line[:1].isdigit() and words in line)

    def test_same_day_sessions_before_the_reduction_are_named(self):   # 날짜만 보는 검사기가 가리지 못하는 경우
        part = self.part()
        self.assertIn("같은 날", part)
        self.assertIn("줄이기 전에 마친 세션", part)

    def test_the_seen_case_is_its_own_step(self):
        edit = self.item("브리프부터 고친다")
        seen = self.item("`before_results`를 `false`")
        self.assertNotEqual(edit, seen)
        self.assertNotIn("`false`", edit)

    def test_the_sample_short_message_points_to_the_section(self):
        r = judge(three()[:1], [verdict(sessions=("pt_a",), criteria=stamp())])
        msg = next(e["message"] for e in r["errors"] if e["code"] == "verdict_sample_short")
        self.assertIn(f"references/changes.md '{SECTION}'", msg)

    def test_the_brief_sample_row_points_to_the_section(self):
        brief = (ROOT / "skills/concept-exploration/references/brief.md").read_text(encoding="utf-8")
        row = next(line for line in brief.splitlines() if line.startswith("| `sample` |"))
        self.assertIn("changes.md#표본을-줄이자는-말이-나올-때", row)


if __name__ == "__main__":
    unittest.main()
