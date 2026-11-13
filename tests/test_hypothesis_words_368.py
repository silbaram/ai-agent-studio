"""368: 가설과 플레이 중 질문의 말이 시험판 화면의 규칙을 가리키게 한다. 표준 라이브러리 unittest만 사용한다."""
import re
import unittest

from _studio import ROOT

SKILLS = ROOT / "skills"
BRIEF = SKILLS / "concept-exploration/references/brief.md"
GUIDE = SKILLS / "playtest-verdict/SKILL.md"
CHANGES = SKILLS / "playtest-verdict/references/changes.md"
BRIEF_LINK = "../concept-exploration/references/brief.md#가설-hypotheses-1개-이상"
STEP_ONE_LINK = "../../playtest-verdict/SKILL.md#1-플레이-전-가설에-id와-최소-표본을-단다"
CHANGES_LINK = "references/changes.md#판정한-가설의-문장을-고칠-때"


def slug(heading: str) -> str:   # GitHub 제목 앵커
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def anchors(path, prefix):
    return {slug(l[len(prefix):]) for l in path.read_text(encoding="utf-8").splitlines() if l.startswith(prefix)}


def step_one():
    text = GUIDE.read_text(encoding="utf-8")
    m = re.search(r"^### 1\. 플레이 전.*?\n(.*?)(?=^### |^## |\Z)", text, re.S | re.M)
    return m.group(1)


def brief_bullet():
    return next(l for l in BRIEF.read_text(encoding="utf-8").splitlines() if l.startswith("- **지표를 정의한다.**"))


class HypothesisWords(unittest.TestCase):
    def test_claim_and_question_words_name_rules_the_prototype_will_show(self):
        """브리프는 시험판보다 먼저 쓰므로 '보일' 규칙 이름으로 쓰고, 확인은 플레이 전 단계가 한다."""
        line = brief_bullet()
        for word in ("`claim`", "플레이 중 묻는 질문", "그 이름으로 보일 규칙", "`test`에 그대로", "시험판은 이 문장을 그대로", STEP_ONE_LINK):
            self.assertIn(word, line, word)

    def test_feeling_questions_keep_the_feeling(self):
        line = brief_bullet()
        self.assertIn("느낌은 그대로", line)
        self.assertNotIn("긴장감", line)

    def test_metric_and_claim_measure_the_same_thing(self):
        self.assertIn("좁히", brief_bullet())

    def test_example_is_genre_neutral(self):
        line = brief_bullet()
        for word in ("계열", "카드"):
            self.assertNotIn(word, line, word)

    def test_rule_stays_in_one_place(self):
        """말을 고치는 규칙은 brief.md에만 있고, 다른 스킬 문서는 가리키기만 한다."""
        for phrase in ("그 이름으로 보일 규칙", "느낌은 그대로"):
            hits = [p.relative_to(SKILLS).as_posix() for p in SKILLS.rglob("*.md") if phrase in p.read_text(encoding="utf-8")]
            self.assertEqual(hits, ["concept-exploration/references/brief.md"], phrase)


class PrePlayScreenCheck(unittest.TestCase):
    def para(self):
        return next(p for p in step_one().split("\n\n") if "화면" in p)

    def test_step_one_compares_screen_question_with_test(self):
        para = self.para()
        for word in ("플레이 전에", "시험판", "`test`에 적힌 문장", "그 이름으로 보이는지", "고친다", BRIEF_LINK):
            self.assertIn(word, para, word)

    def test_fallback_when_screen_cannot_be_opened(self):
        para = self.para()
        self.assertIn("코드를 읽", para)
        self.assertIn("확인하지 못했다고", para)

    def test_judged_hypothesis_points_to_changes(self):
        self.assertIn(CHANGES_LINK, self.para())

    def test_link_anchors_exist(self):
        self.assertIn(BRIEF_LINK.split("#")[1], anchors(BRIEF, "## "))
        self.assertIn(STEP_ONE_LINK.split("#")[1], anchors(GUIDE, "### "))
        self.assertIn(CHANGES_LINK.split("#")[1], anchors(CHANGES, "## "))


if __name__ == "__main__":
    unittest.main()
