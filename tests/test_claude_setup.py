"""Claude Code 연결(setup·hook) 테스트: 판정 에이전트 설치, 훅 병합, 판정 에이전트 쓰기 차단, 데이터 자동 검사.

훅은 Claude Code가 표준 입력으로 주는 JSON을 받는다. 실제 Claude Code 세션에서 돌린 것은 아니다.
"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from _studio import SAMPLE, claude, run_cli

INSTALLED = ".claude/skills/studio-data/scripts/studio.py"


class Setup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.settings = self.root / ".claude/settings.json"
        self.agent = self.root / ".claude/agents/studio-judge.md"

    def tearDown(self):
        self.tmp.cleanup()

    def setup(self):
        return run_cli("setup", "claude", self.root)

    def hooks(self):
        return json.loads(self.settings.read_text(encoding="utf-8"))["hooks"]

    def test_writes_judge_agent_and_both_hooks(self):
        code, out = self.setup()
        self.assertEqual(code, 0, out)
        text = self.agent.read_text(encoding="utf-8")
        self.assertIn("name: studio-judge", text)
        self.assertNotIn("Write", text.split("---")[1])
        hooks = self.hooks()
        self.assertIn("hook post-edit", hooks["PostToolUse"][0]["hooks"][0]["command"])
        self.assertIn("hook judge-guard", hooks["PreToolUse"][0]["hooks"][0]["command"])

    def test_rerun_replaces_its_own_hooks_and_keeps_the_users(self):
        self.settings.parent.mkdir(parents=True)
        user_hook = {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo mine"}]}
        self.settings.write_text(json.dumps({"model": "x", "hooks": {"PreToolUse": [user_hook]}}), encoding="utf-8")
        self.setup()
        self.setup()
        data = json.loads(self.settings.read_text(encoding="utf-8"))
        self.assertEqual(data["model"], "x")
        pre = data["hooks"]["PreToolUse"]
        self.assertEqual(pre[0], user_hook)
        self.assertEqual(sum("judge-guard" in h["command"] for g in pre for h in g["hooks"]), 1)
        self.assertEqual(len(data["hooks"]["PostToolUse"]), 1)

    def test_broken_settings_is_not_overwritten(self):
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text("{ not json", encoding="utf-8")
        code, _ = self.setup()
        self.assertEqual(code, 2)
        self.assertEqual(self.settings.read_text(encoding="utf-8"), "{ not json")
        self.assertFalse(self.agent.exists())

    def test_an_agent_file_it_did_not_write_is_not_overwritten(self):
        self.agent.parent.mkdir(parents=True)
        self.agent.write_text("---\nname: studio-judge\n---\n내가 쓴 것\n", encoding="utf-8")
        code, _ = self.setup()
        self.assertEqual(code, 2)
        self.assertIn("내가 쓴 것", self.agent.read_text(encoding="utf-8"))

    def test_installed_copy_is_referenced_through_the_project_dir(self):
        self.assertEqual(claude.script_reference(self.root, self.root / INSTALLED), '"$CLAUDE_PROJECT_DIR/' + INSTALLED + '"')


def guard(tool, agent="studio-judge", **tool_input):
    payload = {"tool_name": tool, "tool_input": tool_input, "hook_event_name": "PreToolUse"}
    if agent:
        payload["agent_type"] = agent
    return claude.judge_guard(json.dumps(payload))


class JudgeGuard(unittest.TestCase):
    def test_judge_cannot_write_files(self):
        for tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
            with self.subTest(tool):
                code, msg = guard(tool, file_path="data/playtests.json")
                self.assertEqual(code, 2)
                self.assertIn("판정 에이전트", msg)

    def test_judge_can_run_check_and_provenance_only(self):
        ok = ["python3 .claude/skills/studio-data/scripts/studio.py check .",
              "python3 .claude/skills/studio-data/scripts/studio.py check . --fail-on-assumed --json",
              "py .claude\\skills\\studio-data\\scripts\\studio.py provenance design/ --check-paths"]
        for cmd in ok:
            with self.subTest(cmd):
                self.assertEqual(guard("Bash", command=cmd)[0], 0)
        blocked = ["python3 .claude/skills/studio-data/scripts/studio.py check . --out reports/x.json",
                   "python3 .claude/skills/studio-data/scripts/studio.py check . && rm -rf data",
                   "python3 .claude/skills/studio-data/scripts/studio.py simulate data/meta.json",
                   "python3 .claude/skills/studio-data/scripts/studio.py setup claude .",
                   "echo x > data/playtests.json",
                   "python3 -c 'open(\"a\",\"w\")'",
                   "python3 .claude/skills/studio-data/scripts/studio.py check $(rm -rf data)"]
        for cmd in blocked:
            with self.subTest(cmd):
                self.assertEqual(guard("Bash", command=cmd)[0], 2)

    def test_other_agents_and_read_tools_are_not_touched(self):
        self.assertEqual(guard("Write", agent=None, file_path="a")[0], 0)
        self.assertEqual(guard("Write", agent="general-purpose", file_path="a")[0], 0)
        self.assertEqual(guard("Read", file_path="a")[0], 0)

    def test_unreadable_input_does_not_break_the_session(self):
        self.assertEqual(claude.judge_guard("not json")[0], 0)


class PostEdit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "game"
        shutil.copytree(SAMPLE, self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, rel):
        payload = {"tool_name": "Edit", "tool_input": {"file_path": str(self.root / rel)}, "cwd": str(self.root)}
        return claude.post_edit(json.dumps(payload), project=self.root)

    def test_clean_data_edit_is_silent(self):
        self.assertEqual(self.run_hook("data/items.json"), (0, "", ""))

    def test_data_error_is_shown_to_the_agent(self):
        items = json.loads((self.root / "data/items.json").read_text(encoding="utf-8"))
        items["items"][0]["status"] = "maybe"
        (self.root / "data/items.json").write_text(json.dumps(items), encoding="utf-8")
        code, out, err = self.run_hook("data/items.json")
        self.assertEqual(code, 2)
        self.assertIn("schema", err)

    def test_warning_is_added_as_context_without_blocking(self):
        (self.root / "design/plan.md").write_text("부화는 6초로 한다.\n", encoding="utf-8")
        code, out, err = self.run_hook("design/plan.md")
        self.assertEqual(code, 0)
        ctx = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(ctx["hookEventName"], "PostToolUse")
        self.assertIn("6초", ctx["additionalContext"])

    def test_files_outside_design_and_data_are_ignored(self):
        (self.root / "src").mkdir()
        (self.root / "src/main.gd").write_text("x", encoding="utf-8")
        self.assertEqual(self.run_hook("src/main.gd"), (0, "", ""))
        self.assertEqual(claude.post_edit("not json", project=self.root), (0, "", ""))


if __name__ == "__main__":
    unittest.main()
