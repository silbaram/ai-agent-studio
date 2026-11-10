"""스킬 문서 덜어내기(2026-11-10) 테스트. 표준 라이브러리 unittest만 사용한다.

playtest-verdict의 드문 순서(기준·컨셉을 바꿀 때)를 references/changes.md로 옮겼다. SKILL.md는 늘 밟는 흐름과
"이럴 때 → 읽을 절" 표만 둔다. 옮긴 절을 가리키는 링크와 검사 메시지가 실제 절을 가리키는지 본다."""
import re
import unittest

from _studio import CHANGES, ROOT, STUDIO, changes_section

SKILL = ROOT / "skills/playtest-verdict/SKILL.md"
SECTIONS = ("표본을 줄이자는 말이 나올 때", "판정한 가설의 문장을 고칠 때", "이력을 나중에 남길 때",
            "다시 시험할 때", "컨셉을 되돌릴 때", "다른 시스템이 바뀌어 지난 기록과 합치지 않을 때")


def slug(heading: str) -> str:   # GitHub 제목 앵커: 소문자, 공백은 하이픈, 글자·숫자·하이픈·밑줄 밖은 뺀다
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def headings() -> set:
    return {line[3:] for line in CHANGES.read_text(encoding="utf-8").splitlines() if line.startswith("## ")}


class Moved(unittest.TestCase):
    def test_every_moved_section_is_in_changes(self):
        self.assertEqual(set(SECTIONS), headings())

    def test_the_skill_keeps_only_the_pointer_table(self):
        skill = SKILL.read_text(encoding="utf-8")
        for title in SECTIONS:
            with self.subTest(title=title):
                self.assertIn(f"](references/changes.md#{slug(title)})", skill)   # 표에서 가리킨다
                self.assertNotIn(f"**{title}.**", skill)                            # 본문은 옮겼다
        self.assertNotIn("git show <커밋>^", skill)   # 옮긴 절의 본문이 SKILL.md에 다시 들어오지 않았다

    def test_the_skill_is_lighter(self):   # 옮기기 전 27,717바이트. 다시 불어나면 알린다
        self.assertLess(len(SKILL.read_bytes()), 20000)


class Links(unittest.TestCase):
    def test_every_link_into_changes_resolves(self):
        anchors = {slug(h) for h in headings()}
        found = 0
        for md in (ROOT / "skills").rglob("*.md"):
            for anchor in re.findall(r"changes\.md#([^)\s]+)", md.read_text(encoding="utf-8")):
                found += 1
                with self.subTest(file=str(md.relative_to(ROOT)), anchor=anchor):
                    self.assertIn(anchor, anchors)
        self.assertGreater(found, 5)

    def test_links_inside_changes_resolve(self):   # 같은 파일 안의 링크(](#…))도 제목이 바뀌면 깨진다
        anchors = {slug(h) for h in headings()}
        inner = re.findall(r"\]\(#([^)\s]+)\)", CHANGES.read_text(encoding="utf-8"))
        self.assertTrue(inner)
        for anchor in inner:
            with self.subTest(anchor=anchor):
                self.assertIn(anchor, anchors)

    def test_checker_messages_name_real_sections(self):
        titles = headings()
        named = 0
        for py in (STUDIO / "scripts/studio_data").glob("*.py"):
            text = py.read_text(encoding="utf-8")
            for m in re.finditer(r"references/changes\.md[^\n]{0,4}'([^']+)'", text):
                named += 1
                with self.subTest(file=py.name, title=m.group(1)):
                    self.assertIn(m.group(1), titles)
        self.assertGreaterEqual(named, 2)

    def test_a_section_reads_to_its_end(self):   # 테스트 도우미가 다음 절을 끌어오지 않는다
        part = changes_section("판정한 가설의 문장을 고칠 때")
        self.assertIn("3. 뜻이 바뀌면", part)
        self.assertNotIn("## 이력을 나중에 남길 때", part)


class ReviewFixes(unittest.TestCase):
    """덜어내기 검토에서 나온 것."""

    def skill(self) -> str:
        return SKILL.read_text(encoding="utf-8")

    def step(self, n: int) -> str:
        text = self.skill()
        start = text.index(f"### {n}.")
        return text[start:text.index("\n#", start + 4)]

    def test_step_1_still_stops_a_mid_test_reduction(self):   # 플레이 도중에 나오는 말이라 흐름 안에서 가리킨다
        part = self.step(1)
        self.assertIn("바로 고치지 않는다", part)
        self.assertIn("changes.md#표본을-줄이자는-말이-나올-때", part)

    def test_step_2_asks_for_the_raw_logs(self):
        self.assertIn("`logs`", self.step(2))

    def test_the_pointer_table_is_its_own_section_after_the_steps(self):
        text = self.skill()
        head = "## 기준이나 컨셉을 바꿀 때"
        self.assertIn(head, text)
        self.assertLess(text.index("### 6."), text.index(head))
        self.assertLess(text.index(head), text.index("## 보고"))
        between = text[text.index("### 3."):text.index("### 4.")]
        self.assertNotIn("\n### ", between[4:])   # 3단계와 4단계 사이에 번호 없는 절이 없다
        self.assertIn("changes.md#판정한-가설의-문장을-고칠-때", self.step(3))   # 지문 경고가 나는 단계에서 가리킨다

    def test_no_verification_environment_in_the_verdict_docs(self):   # 확인한 환경은 그 기능을 맡은 스킬 한 곳에 둔다
        for path in (SKILL, CHANGES):
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertNotIn("acceptEdits", text)
                self.assertNotRegex(text, r"Claude Code 2\.\d")
        self.assertIn("scope-guard/SKILL.md#한계", changes_section("컨셉을 되돌릴 때"))
        self.assertIn("studio-data/SKILL.md#claude-code-연결", self.skill())

    def test_every_concept_code_is_in_the_record_table(self):
        code = (STUDIO / "scripts/studio_data/concepts.py").read_text(encoding="utf-8")
        doc = (ROOT / "skills/concept-exploration/references/concept-record.md").read_text(encoding="utf-8")
        missing = sorted(c for c in set(re.findall(r'"code": "([a-z_]+)"', code)) if f"`{c}`" not in doc)
        self.assertEqual(missing, [])

    def test_the_brief_rule_keeps_why_it_asks(self):
        brief = (ROOT / "skills/concept-exploration/references/brief.md").read_text(encoding="utf-8")
        rule = next(line for line in brief.splitlines() if line.startswith("- **세는 빌드는 이름으로 가리킨다.**"))
        self.assertIn("지문이 바뀌", rule)
        self.assertIn("게이트를 넘지 못한다", rule)


if __name__ == "__main__":
    unittest.main()
