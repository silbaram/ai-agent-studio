"""편집 뒤 훅의 출력 줄이기(294번): 한 세션에서 이미 보인 경고는 개수로만 보인다. 표준 라이브러리 unittest만 사용한다."""
import json
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from _studio import ROOT, SAMPLE, claude, run_cli


class HookOutput(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "game"
        shutil.copytree(SAMPLE, self.root)
        patch = mock.patch.object(claude, "STATE_DIR", Path(self.tmp.name) / "state")
        patch.start()
        self.addCleanup(patch.stop)
        self.drop_next_test("greed_rooms", "blood_ammo")

    def tearDown(self):
        self.tmp.cleanup()

    def concepts(self, change):
        path = self.root / "design/concepts.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        change({c["id"]: c for c in data["concepts"]})
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def drop_next_test(self, *ids):
        self.concepts(lambda by: [by[i].pop("next_test", None) for i in ids])

    def hook(self, rel="design/concepts.json", session="s1", **extra):
        payload = {"tool_name": "Edit", "tool_input": {"file_path": str(self.root / rel)}, "cwd": str(self.root), **extra}
        if session:
            payload["session_id"] = session
        code, out, err = claude.post_edit(json.dumps(payload), project=self.root)
        return code, (json.loads(out)["hookSpecificOutput"]["additionalContext"] if out else ""), err

    def test_without_a_session_every_edit_shows_everything(self):
        for _ in range(2):
            self.assertEqual(self.hook(session=None)[1].count("[next_test_missing]"), 2)

    def test_the_first_edit_of_a_session_shows_everything(self):
        self.assertEqual(self.hook()[1].count("[next_test_missing]"), 2)

    def test_an_unchanged_list_is_one_line(self):
        self.hook()
        code, text, _ = self.hook()
        self.assertEqual(code, 0)
        self.assertNotIn("[next_test_missing]", text)
        self.assertIn("경고 2개", text)
        self.assertIn("지난 편집과 같습니다", text)
        self.assertIn("concepts.json 2", text)
        self.assertIn("studio.py check .", text)

    def test_a_new_warning_is_shown_and_the_rest_counted(self):
        self.hook()
        self.drop_next_test("echo_route")
        text = self.hook()[1]
        self.assertEqual(text.count("[next_test_missing]"), 1)
        self.assertIn("echo_route", text)
        self.assertIn("새 경고 1개", text)
        self.assertIn("이미 보인 경고 2개", text)

    def test_a_resolved_warning_is_named(self):
        self.hook()
        self.concepts(lambda by: by["greed_rooms"].update(next_test="t"))
        text = self.hook()[1]
        self.assertIn("풀린 경고 1개", text)
        self.assertIn("greed_rooms", text)
        self.assertNotIn("blood_ammo:", text.split("풀린 경고")[0])

    def test_resolving_everything_says_so(self):
        self.hook()
        self.concepts(lambda by: [by[i].update(next_test="t") for i in ("greed_rooms", "blood_ammo")])
        text = self.hook()[1]
        self.assertIn("풀린 경고 2개", text)
        self.assertIn("경고 0개", text)

    def test_another_session_starts_over(self):
        self.hook()
        self.assertEqual(self.hook(session="s2")[1].count("[next_test_missing]"), 2)

    def test_errors_are_always_shown_in_full(self):
        self.hook()
        self.concepts(lambda by: by["greed_rooms"].update(pitch=""))
        code, _, err = self.hook()
        self.assertEqual(code, 2)
        self.assertIn("[missing_field] greed_rooms", err)
        self.assertNotIn("[next_test_missing] blood_ammo", err)   # 이미 보인 경고. greed_rooms는 형식 오류로 빠져 풀린 경고로 나온다
        self.assertIn("이미 보인 경고 1개", err)

    def test_a_document_has_its_own_list(self):
        self.hook()
        (self.root / "design/plan.md").write_text("부화는 6초로 한다.\n", encoding="utf-8")
        self.assertIn("6초", self.hook("design/plan.md")[1])
        self.assertNotIn("6초", self.hook("design/plan.md")[1])

    def test_an_unwritable_state_falls_back_to_everything(self):
        claude.STATE_DIR.parent.mkdir(parents=True, exist_ok=True)
        claude.STATE_DIR.write_text("not a folder", encoding="utf-8")
        for _ in range(2):
            self.assertEqual(self.hook()[1].count("[next_test_missing]"), 2)

    def test_a_broken_state_file_starts_over(self):
        self.hook()
        for f in claude.STATE_DIR.iterdir():
            f.write_text("{", encoding="utf-8")
        self.assertEqual(self.hook()[1].count("[next_test_missing]"), 2)

    def test_a_subagent_sees_everything_on_its_first_edit(self):
        self.hook()
        extra = {"agent_id": "a1", "agent_type": "general-purpose"}
        self.assertEqual(self.hook(**extra)[1].count("[next_test_missing]"), 2)
        self.assertNotIn("[next_test_missing]", self.hook(**extra)[1])

    def test_compacting_or_clearing_starts_over(self):
        for source in ("compact", "clear", "resume"):
            with self.subTest(source):
                self.hook()
                self.hook(agent_id="a1")
                self.assertEqual(claude.session_start(json.dumps({"session_id": "s1", "source": source}), self.root), (0, "", ""))
                self.assertEqual(self.hook()[1].count("[next_test_missing]"), 2)
                self.assertEqual(self.hook(agent_id="a1")[1].count("[next_test_missing]"), 2)

    def test_starting_another_session_keeps_this_one(self):
        self.hook()
        claude.session_start(json.dumps({"session_id": "s2", "source": "startup"}), self.root)
        self.assertNotIn("[next_test_missing]", self.hook()[1])

    def test_no_temporary_file_is_left(self):
        self.hook()
        self.hook()
        self.assertEqual([f.suffix for f in claude.STATE_DIR.iterdir()], [".json"])

    @unittest.skipUnless(hasattr(os, "getuid"), "POSIX 권한")
    def test_the_state_folder_is_private(self):
        self.hook()
        self.assertEqual(claude.STATE_DIR.stat().st_mode & 0o077, 0)

    def test_old_state_files_are_removed(self):
        claude.STATE_DIR.mkdir(parents=True)
        old = claude.STATE_DIR / "old.json"
        old.write_text("{}", encoding="utf-8")
        stamp = time.time() - 8 * 86400
        os.utime(old, (stamp, stamp))
        self.hook()
        self.assertFalse(old.exists())


class Diff(unittest.TestCase):
    A = "levels.json: [kill_time_long] zone_2: 처치 시간이 단계 길이의 1.78배입니다."
    B = "levels.json: [kill_time_long] zone_2: 처치 시간이 단계 길이의 1.6배입니다."
    C = "economy.json: [unused] gold: 쓰지 않는 재화입니다."

    def test_a_changed_value_is_one_changed_line(self):
        lines = claude._warning_lines([self.B, self.C], claude._diff([self.A, self.C], [self.B, self.C]), "check .")
        self.assertIn("바뀐 경고 1개:", lines)
        self.assertIn(self.B, lines)
        self.assertNotIn(self.A, lines)
        self.assertFalse(any(x.startswith(("새 경고", "풀린 경고")) for x in lines))

    def test_a_repeated_line_is_counted(self):
        new, changed, gone = claude._diff([self.C], [self.C, self.C])
        self.assertEqual((new, changed, gone), ([self.C], [], []))
        self.assertEqual(claude._diff([self.C, self.C], [self.C]), ([], [], [self.C]))

    def test_the_rest_is_counted_by_file(self):
        lines = claude._warning_lines([self.A, self.C], claude._diff([self.A], [self.A, self.C]), "check .")
        self.assertIn("(levels.json 1)", lines[-1])


class SessionStartHook(unittest.TestCase):
    def test_setup_registers_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(run_cli("setup", "claude", root)[0], 0)
            run_cli("setup", "claude", root)
            groups = json.loads((root / ".claude/settings.json").read_text(encoding="utf-8"))["hooks"]["SessionStart"]
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["matcher"], "compact|clear|resume")
        self.assertIn("hook session-start", groups[0]["hooks"][0]["command"])

    def test_bad_input_is_ignored(self):
        self.assertEqual(claude.session_start("not json"), (0, "", ""))
        self.assertEqual(claude.session_start(json.dumps({"source": "compact"})), (0, "", ""))


class Docs(unittest.TestCase):
    def test_the_hook_section_explains_the_short_output(self):
        text = (ROOT / "skills/studio-data/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("이미 보인 경고", text)
        self.assertIn("session_id", text)
        self.assertIn("SessionStart", text)
        self.assertIn("경고 줄이기는 실제 세션에서 확인하지 않았다", text)


if __name__ == "__main__":
    unittest.main()
