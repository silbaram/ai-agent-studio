"""컨셉 되돌리기 다시 시험(2026-11-09)의 이슈 324~327 테스트. 표준 라이브러리 unittest만 사용한다."""
import copy
import io
import unittest
from contextlib import redirect_stdout

from _studio import ROOT, changes_section, concepts as cc
from test_verdict_field import CONCEPTS, approved, hyp, judge, printed, stamp, three, verdict

SECTION = "컨셉을 되돌릴 때"


def read(path) -> str:
    return path.read_text(encoding="utf-8")


def section() -> str:
    return changes_section(SECTION)


def reverted() -> dict:
    data = copy.deepcopy(CONCEPTS)
    approved(data)["status"] = "proposed"
    return data


def message(r: dict, code: str) -> str:
    return next(w["message"] for w in r["warnings"] if w["code"] == code)


class NotChosen324(unittest.TestCase):
    """324번: 선택하지 않은(되돌린) 컨셉의 판정 경고는 게이트를 넘지 못한다고 하지 않는다."""

    def test_a_missing_stamp_on_a_reverted_concept_324(self):
        msg = message(judge(three(), [verdict(status="approved")], concepts=reverted()), "verdict_criteria_missing")
        self.assertIn("게이트에 들지 않습니다", msg)
        self.assertNotIn("확정해도 게이트(--fail-on-assumed)를 넘지 못합니다. 판정", msg)

    def test_a_changed_criteria_on_a_reverted_concept_324(self):
        old = stamp()   # 되돌리기 전에 찍은 지문
        data = reverted()
        hyp_ = next(h for h in data["concepts"][0]["brief"]["hypotheses"] if h["id"] == "learn_timing")
        hyp_["failure_signal"] = "3판 [가정] 동안 피격률이 줄지 않는다"
        msg = message(judge(three(), [verdict(status="approved", criteria=old)], concepts=data), "verdict_criteria_changed")
        self.assertIn("게이트에 들지 않습니다", msg)
        self.assertNotIn("확정 판정이어도 게이트를 넘지 못합니다", msg)

    def test_a_cut_concept_counts_as_not_chosen_324(self):   # 되돌리기의 다른 갈래: hard_reject와 함께 cut
        data = reverted()
        c = data["concepts"][0]
        c["status"] = "cut"
        c["hard_reject"] = {"type": "dominant_simple_policy", "reason": "r", "evidence": "e"}
        msg = message(judge(three(), [verdict(status="approved")], concepts=data), "verdict_criteria_missing")
        self.assertIn("게이트에 들지 않습니다", msg)

    def test_a_chosen_concept_keeps_the_gate_text_324(self):
        msg = message(judge(three(), [verdict(status="approved")]), "verdict_criteria_missing")
        self.assertIn("넘지 못합니다", msg)
        self.assertNotIn("게이트에 들지 않습니다", msg)


class ArchiveYes325(unittest.TestCase):
    """325번: 확인 창이 없는 실행에서 변경을 닫을 때는 --yes를 붙인다. --yes는 남은 작업 확인도 건너뛰니 먼저 알린다."""

    def test_the_revert_section_names_yes_325(self):
        part = section()
        self.assertIn("--yes", part)
        self.assertIn("끝나지 않은 작업", part)

    def test_scope_guard_names_yes_325(self):
        line = next(x for x in read(ROOT / "skills/scope-guard/SKILL.md").splitlines() if "--skip-specs" in x)
        self.assertIn("--yes", line)
        self.assertIn("끝나지 않은 작업", line)


class NoChosenConcept326(unittest.TestCase):
    """326번: 선택한 컨셉이 없고 판정까지 한(되돌린) 컨셉이 있으면, 게이트의 다른 데이터 항목은 지난 시험의 기록이라고 알린다.
    판정이 없는 컨셉(승인 전에 설계하는 중)에는 알리지 않는다."""

    NOTE = "선택(approved)한 컨셉이 없습니다"

    def test_a_reverted_concept_with_verdicts_gets_a_note_326(self):
        r = judge(three(), [verdict(status="approved")], concepts=reverted())
        self.assertEqual(r["reverted"], ["parry_tempo"])
        out = printed(r)
        self.assertIn(self.NOTE, out)
        self.assertIn("parry_tempo", out)
        self.assertIn("지난 시험의 기록", out)

    def test_no_note_while_a_concept_is_chosen_326(self):
        r = judge(three(), [verdict(status="approved")])
        self.assertEqual(r["reverted"], [])
        self.assertNotIn(self.NOTE, printed(r))

    def test_no_note_for_a_concept_designed_before_approval_326(self):   # 브리프가 있어도 판정이 없으면 되돌린 것이 아니다
        r = judge(three(), [], concepts=reverted())
        self.assertNotIn(self.NOTE, printed(r))

    def test_the_concepts_check_does_not_guess_326(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            cc.print_extra(cc.validate(reverted()))
        self.assertNotIn(self.NOTE, buf.getvalue())

    def test_the_revert_section_says_so_326(self):
        self.assertIn("할 일이 아니다", section())


class Reselect327(unittest.TestCase):
    """327번: 되돌아와 다시 고를 때는 남은 후보를 모두 보이고, 좁힐지는 사용자에게 묻는다."""

    def test_the_revert_section_says_how_to_show_candidates_327(self):
        part = section()
        for phrase in ("모두 보이고", "좁힐지는 사용자에게 묻는다", "재미 순위"):
            self.assertIn(phrase, part)

    def test_the_selection_step_points_back_327(self):
        text = read(ROOT / "skills/concept-exploration/SKILL.md")
        step7 = text[text.index("### 7. 후보 제시와 선택"):text.index("### 8.")]
        self.assertIn("컨셉을 되돌릴 때", step7)
        self.assertNotIn("모두 보이고", step7)   # 원본은 playtest-verdict 한 곳이다


if __name__ == "__main__":
    unittest.main()
