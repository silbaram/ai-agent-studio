"""397: 보고가 지금 위치와 가설을 사용자에게 쉬운 말로 말한다.
문서만 바꾼 이슈라 문서의 연결과 틀을 본다. 표준 라이브러리 unittest만 사용한다."""
import re
import unittest

from _studio import ROOT

SKILLS = ROOT / "skills"
GUIDE = SKILLS / "studio-data/references/telling-the-user.md"
LINK = "studio-data/references/telling-the-user.md"


def read(path):
    return path.read_text(encoding="utf-8")


def section(text, title):
    start = text.index(title)
    rest = text[start + len(title):]
    nxt = re.search(r"^## ", rest, re.M)
    return rest[:nxt.start()] if nxt else rest


class TellingTheUser(unittest.TestCase):
    def test_guide_has_the_line_the_card_and_decisions(self):
        text = read(GUIDE)
        for heading in ("## 지금 위치 줄", "## 가설 카드", "## 정할 것"):
            self.assertIn(heading, text)
        card = section(text, "## 가설 카드")
        for when in ("약속서", "플레이 전", "판정 뒤"):
            self.assertIn(when, card)
        for line in ("무엇을 확인하나", "할 일", "맞음", "틀림", "틀리면", "지금 정할 것"):
            self.assertIn(line, card)

    def test_card_keeps_the_brief_as_the_source(self):
        card = section(read(GUIDE), "## 가설 카드")
        self.assertIn("원본은 약속서", card)
        self.assertIn("지어내지 않는다", card)

    def test_every_design_skill_is_placed_on_the_line(self):
        stages = section(read(GUIDE), "## 지금 위치 줄")
        for folder in sorted(p.name for p in SKILLS.iterdir() if (p / "SKILL.md").is_file()):
            if folder == "studio-data":
                continue
            self.assertIn(f"`{folder}`", stages, f"{folder} is not on the stage table")

    def test_every_report_opens_with_the_line_and_the_decision_shape(self):
        # review findings 5 and 6: the first bullet itself, and it covers decisions too
        for doc in sorted(SKILLS.glob("*/SKILL.md")):
            text = read(doc)
            if "## 보고" not in text:
                continue
            first = next(line for line in section(text, "## 보고").splitlines() if line.startswith("- "))
            self.assertIn(LINK, first, f"{doc.parent.name}: first report bullet does not point at the page")
            self.assertIn("지금 위치", first, doc.parent.name)
            self.assertIn("정할 것", first, doc.parent.name)

    def test_quoted_brief_sentences_keep_their_tags(self):
        # review finding 1: a whole quote keeps [가정] and says it in plain words
        card = section(read(GUIDE), "## 가설 카드")
        self.assertIn("인용 안의 태그", card)
        self.assertIn("AI가 제안만 한 값", card)

    def test_first_moment_is_an_existing_step(self):
        # review finding 3
        card = section(read(GUIDE), "## 가설 카드")
        self.assertIn("8단계", card)
        self.assertNotIn("받아들이기 전", card)

    def test_preplay_step_points_at_script_definitions(self):
        # review finding 2: the moved paragraph is still reachable before play
        text = read(SKILLS / "playtest-verdict/SKILL.md")
        step1 = text[text.index("### 1. 플레이 전"):text.index("### 2. 플레이한 뒤")]
        self.assertIn("references/playtest-record.md#세션-playtests", step1)
        self.assertIn("정의", step1)

    def test_user_guide_only_links_the_card(self):
        # review finding 4: one rule in one place
        guide = read(ROOT / "docs/guide.md")
        self.assertIn(LINK, guide)
        self.assertNotIn("무엇을 확인하나", guide)

    def test_cards_are_shown_at_the_three_moments(self):
        concept = section(read(SKILLS / "concept-exploration/SKILL.md"), "## 보고")
        self.assertIn("가설 카드", concept)
        verdict = section(read(SKILLS / "playtest-verdict/SKILL.md"), "## 보고")
        self.assertIn("가설 카드(플레이 전)", verdict)
        self.assertIn("가설 카드(판정 뒤)", verdict)

    def test_links_from_the_guide_resolve(self):
        for target in re.findall(r"\]\(([^)#:]+)(?:#[^)]*)?\)", read(GUIDE)):
            self.assertTrue((GUIDE.parent / target).exists(), target)

    def test_studio_data_and_user_guide_point_here(self):
        self.assertIn("references/telling-the-user.md", read(SKILLS / "studio-data/SKILL.md"))
        self.assertIn(LINK, read(ROOT / "docs/guide.md"))


if __name__ == "__main__":
    unittest.main()
