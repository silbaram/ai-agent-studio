"""저장소 라이선스(MIT, 2026-11-22 사용자 결정): LICENSE 파일, README 안내, 결정 대기에서 빠짐. 표준 라이브러리 unittest만 사용한다."""
import unittest

from _studio import ROOT


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


class License(unittest.TestCase):
    def test_license_file_is_mit_with_the_holder(self):
        text = read("LICENSE")
        self.assertTrue(text.startswith("MIT License\n"))
        self.assertIn("Copyright (c) 2026 silbaram", text)
        self.assertIn('THE SOFTWARE IS PROVIDED "AS IS"', text)

    def test_readme_names_the_license(self):
        self.assertIn("[MIT 라이선스](LICENSE)", read("README.md"))

    def test_every_installed_skill_carries_the_notice(self):
        # npx skills add --copy는 스킬 폴더만 옮긴다. MIT는 사본에 저작권 표시와 허락 문장을 남기라고 한다
        root = read("LICENSE")
        for skill in sorted(p for p in (ROOT / "skills").iterdir() if (p / "SKILL.md").is_file()):
            with self.subTest(skill.name):
                self.assertEqual((skill / "LICENSE").read_text(encoding="utf-8"), root)
                head = (skill / "SKILL.md").read_text(encoding="utf-8").split("---")[1]
                self.assertIn("\nlicense: MIT\n", head)

    def test_third_party_says_what_can_be_brought_in(self):
        text = read("THIRD_PARTY.md")
        self.assertIn("[MIT](LICENSE)", text.split("\n\n")[1])
        self.assertIn("함께 배포할 수 있는", text)

    def test_waiting_section_has_only_waiting_decisions(self):
        text = read("docs/architecture.md")
        waiting = text[text.index("\n## 결정 대기\n"):]
        self.assertNotIn("하기로 했다", waiting)   # 정한 것은 로드맵이나 경위에 있다
        self.assertIn("없음", waiting)

    def test_license_is_no_longer_waiting_for_a_decision(self):
        text = read("docs/architecture.md")
        waiting = text[text.index("\n## 결정 대기\n"):]
        waiting = waiting[:waiting.find("\n## ", 1)] if "\n## " in waiting[1:] else waiting
        self.assertNotIn("- 라이선스", waiting)


if __name__ == "__main__":
    unittest.main()
