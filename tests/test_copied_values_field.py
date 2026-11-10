"""옮겨 적은 게임 수치 정리 현장 시험(2026-11-09)의 이슈 318~320 테스트. 표준 라이브러리 unittest만 사용한다."""
import copy
import unittest

from _studio import changes_section, concepts as cc, ROOT
from test_verdict_field import CONCEPTS, hyp, judge, stamp, three, verdict

BRIEF = ROOT / "skills/concept-exploration/references/brief.md"
RECORD = ROOT / "skills/playtest-verdict/references/playtest-record.md"


def read(path) -> str:
    return path.read_text(encoding="utf-8")


def changed_message() -> str:
    data = copy.deepcopy(CONCEPTS)
    old = stamp(data)
    hyp(data)["test"] = hyp(data)["test"] + " 빌드는 tune-parry 변경이다"
    r = judge(three(), [verdict(status="approved", criteria=old)], concepts=data)
    return next(w["message"] for w in r["warnings"] if w["code"] == "verdict_criteria_changed")


SECTION = "판정한 가설의 문장을 고칠 때"


class AskFirst318(unittest.TestCase):
    """318번: 판정이 있는 가설의 판정 기준 문장은 고치기 전에 사용자와 확인하고, 문장과 criteria를 한 번에 바꾼다.
    순서와 예의 원본은 playtest-verdict SKILL.md 한 곳이고 나머지는 그곳을 가리킨다."""

    def test_the_gate_note_asks_before_editing_318(self):
        note = cc.ASSUMED_CRITERIA_NOTE
        self.assertIn("고치기 전에", note)
        self.assertLess(note.index("고치기 전에"), note.index("criteria"))
        self.assertIn("한 번에", note)

    def test_the_verdict_skill_holds_the_order_318(self):
        part = changes_section(SECTION)   # 순서의 원본은 playtest-verdict references/changes.md다
        for phrase in ("고치기 전에 바꿀 문장을 보이고", "한 번에", "옮겨 적은 빌드의 게임 수치", "다시 시험할 때"):
            self.assertIn(phrase, part)

    def test_the_brief_rule_points_there_318(self):
        brief = read(BRIEF)
        self.assertIn(SECTION, brief)
        self.assertIn("고치기 전에", brief)


class ChangedMessage319(unittest.TestCase):
    """319번: 기준이 바뀐 판정의 경고는 뜻이 바뀌었는지부터 가리게 하고, 뜻이 같은 고침의 예에 옮겨 적은 수치를 지운 것을 든다.
    이미 정한 경우(사용자가 같은 뜻이라고 했다, 다시 시험하려고 바꿨다)는 다시 묻지 않는다."""

    def test_the_warning_asks_about_meaning_before_cut_319(self):
        msg = changed_message()
        self.assertLess(msg.index("사용자와"), msg.index("cut"))
        self.assertIn("옮겨 적은", msg)
        self.assertNotIn("맞춤법 등", msg)

    def test_a_decision_already_made_is_not_asked_again_319(self):
        msg = changed_message()
        self.assertIn("이미 확인했으면", msg)
        self.assertIn("묻지 않고", msg)

    def test_the_stamp_takes_no_particle_319(self):
        data = copy.deepcopy(CONCEPTS)
        hyp(data)["test"] = hyp(data)["test"] + " 빌드는 tune-parry 변경이다"
        self.assertIn(f"(지금 지문: {stamp(data)})", changed_message())

    def test_the_record_row_points_to_the_skill_319(self):
        row = next(line for line in read(RECORD).splitlines() if line.startswith("| `verdict_criteria_changed`"))
        self.assertIn(SECTION, row)
        self.assertIn("다시 시험", row)


class PointAtBuild320(unittest.TestCase):
    """320번: 세는 빌드는 데이터 파일의 지금 값이 아니라 빌드 id나 변경 이름으로 가리킨다(데이터 파일은 다음 조정에서 바뀐다)."""

    def test_the_brief_rule_names_the_build_not_the_file_320(self):
        self.assertIn("데이터 파일을 가리키지도 않는다", read(BRIEF))

    def test_the_gate_note_names_the_build_320(self):
        self.assertIn("빌드 id", cc.ASSUMED_CRITERIA_NOTE)


class ReviewFixes(unittest.TestCase):
    """318~320 수정의 검토에서 나온 것."""

    def test_the_gate_note_stays_short(self):
        self.assertLessEqual(cc.ASSUMED_CRITERIA_NOTE.count("니다."), 4)
        self.assertIn("brief.md", cc.ASSUMED_CRITERIA_NOTE)   # 자세한 순서는 문서에 둔다

    def test_the_restamp_line_takes_no_particle_after_the_stamp(self):
        source = (ROOT / "skills/studio-data/scripts/studio_data/playtests.py").read_text(encoding="utf-8")
        self.assertNotIn("{x['to']}로", source)
        self.assertNotIn("{current}로", source)


if __name__ == "__main__":
    unittest.main()
