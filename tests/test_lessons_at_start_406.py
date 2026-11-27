"""406: 같은 실수가 두 번째로 났는데 세션이 lessons.md를 읽지 않고 에이전트 자체 메모리에 적었다.
보고 쪽 연결(telling-the-user.md)만으로는 그 문서를 열지 않으면 닿지 않는다.
세션을 시작할 때 훅이 한 줄로 알리고, lessons.md는 자체 메모리가 대신하지 못한다고 적는다."""
import json
import tempfile
import unittest
from pathlib import Path

from _studio import ROOT, run_cli
from studio_data import claude

LESSONS = ROOT / "skills/studio-data/references/lessons.md"


def context(out):
    data = json.loads(out)["hookSpecificOutput"]
    assert data["hookEventName"] == "SessionStart"
    return data["additionalContext"]


class StartHook(unittest.TestCase):
    def test_setup_runs_it_on_startup_too(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(run_cli("setup", "claude", root)[0], 0)
            groups = json.loads((root / ".claude/settings.json").read_text(encoding="utf-8"))["hooks"]["SessionStart"]
        self.assertIn("startup", groups[0]["matcher"].split("|"))

    def test_every_start_says_where_lessons_go(self):
        for source in ("startup", "compact", "clear", "resume"):
            with self.subTest(source):
                code, out, err = claude.session_start(json.dumps({"session_id": "s1", "source": source}))
                self.assertEqual((code, err), (0, ""))
                line = context(out)
                self.assertIn("lessons.md", line)
                self.assertIn("두 번째", line)
                self.assertIn("전에도", line)
                self.assertIn("메모리", line)      # 자체 메모리로 대신하지 않는다

    def test_the_path_points_at_the_real_page(self):
        line = context(claude.session_start(json.dumps({"session_id": "s1", "source": "startup"}), ROOT)[1])
        self.assertIn(f"`{LESSONS.resolve().as_posix()}`", line)

    def test_bad_input_still_says_it(self):
        for text in ("not json", json.dumps({"source": "startup"})):
            with self.subTest(text):
                code, out, err = claude.session_start(text)
                self.assertEqual((code, err), (0, ""))
                self.assertIn("lessons.md", context(out))

    def test_path_is_absolute_even_inside_the_project_1(self):
        # Read는 절대 경로만 받고, Windows에서는 셸이 프로젝트 밖에서 시작한다
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = root / ".claude/skills/studio-data/scripts/studio.py"
            ref = claude.lessons_reference(script)
            self.assertTrue(Path(ref).is_absolute(), ref)
            self.assertTrue(ref.endswith(".claude/skills/studio-data/references/lessons.md"), ref)

    def test_message_names_the_page_2(self):
        line = context(claude.session_start(json.dumps({"source": "startup"}))[1])
        self.assertIn("(배운 것 한 줄)", line)
        self.assertIn("# 배운 것 한 줄", LESSONS.read_text(encoding="utf-8"))

    def test_the_copied_rule_points_at_its_source_4(self):
        source = (ROOT / "skills/studio-data/scripts/studio_data/claude.py").read_text(encoding="utf-8")
        i = source.index("에이전트 자체 메모리에 적는 것으로 대신하지 않는다")
        self.assertIn("lessons.md '자리'", source[i - 400:i + 300])


class Page(unittest.TestCase):
    def test_own_memory_does_not_replace_the_rule_file(self):
        text = LESSONS.read_text(encoding="utf-8")
        self.assertRegex(text, r"자체 메모리.{0,80}대신하지 못한다")

    def test_hook_is_documented(self):
        text = (ROOT / "skills/studio-data/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("SessionStart(시작·압축·지움·이어 열기)", text)
        self.assertIn("lessons.md", text)

    def test_scope_says_the_start_line_is_unconfirmed_3(self):
        text = (ROOT / "skills/studio-data/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("시작 알림도 실제 세션에서 확인했다", text)   # 411 A18: 406 실사용 시험 통과


if __name__ == "__main__":
    unittest.main()
