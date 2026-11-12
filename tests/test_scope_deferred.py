"""뒤로 넘겼던 scope-guard 이슈: 207, 210, 211, 243(나머지), 244, 252(나머지)."""
import json
import os
import shutil
import time
import unittest

from _studio import ROOT, run_cli
from studio_data import scope
from test_scope import HookCase


def asks(result) -> str | None:
    """훅이 묻는 이유. 묻지 않으면 None."""
    code, out, err = result
    if code != 0 or not out:
        return None
    decision = json.loads(out)["hookSpecificOutput"]
    return decision["permissionDecisionReason"] if decision["permissionDecision"] == "ask" else None


class Case(HookCase):
    def notes(self):
        return self.report()["notes"]

    def note_with(self, label):
        return [n for n in self.notes() if n.startswith(label)]

    def change_rule(self, sid="tempo", text="완전히 다른 규칙"):
        data = self.design()
        self.system(data, sid)["rules"][0]["text"] = text
        self.save(data)

    def close(self, name="add-tempo", day="2026-11-05"):
        target = self.root / "openspec/changes/archive" / f"{day}-{name}"
        shutil.move(str(self.root / "openspec/changes" / name), str(target))
        return target


class ClosedThenChanged(Case):
    """207번: 닫은 뒤에 규칙이 바뀌면 참고로 알린다."""

    def test_a_rule_changed_after_closing_is_a_note(self):
        self.linked()
        self.close()
        self.change_rule()
        report = self.report()
        self.assertEqual(report["errors"], [])
        found = self.note_with("닫은 뒤 바뀐 규칙")
        self.assertEqual(len(found), 1, report["notes"])
        self.assertIn("tempo", found[0])
        self.assertIn("2026-11-05-add-tempo", found[0])
        self.assertIn("새 변경", found[0])
        code, out = run_cli("scope", self.root)
        self.assertEqual(code, 0, out)
        self.assertIn("참고: 닫은 뒤 바뀐 규칙", out)
        code, out = run_cli("scope", self.root, "--json")
        self.assertTrue(any(n.startswith("닫은 뒤 바뀐 규칙") for n in json.loads(out)["notes"]))

    def test_unchanged_rules_say_nothing(self):
        self.linked()
        self.close()
        self.assertEqual(self.note_with("닫은 뒤 바뀐 규칙"), [])

    def test_the_newest_closed_change_counts(self):
        self.linked()
        self.close(day="2026-11-01")
        self.change_rule()
        self.linked()   # 바뀐 규칙으로 다시 쓰고 닫았다
        self.close(day="2026-11-06")
        self.assertEqual(self.note_with("닫은 뒤 바뀐 규칙"), [])

    def test_an_open_change_for_that_system_is_the_fix(self):
        self.linked()
        self.close()
        self.change_rule()
        self.linked("fix-tempo")
        self.assertEqual(self.note_with("닫은 뒤 바뀐 규칙"), [])

    def test_a_note_does_not_block(self):
        self.linked()
        self.close()
        self.change_rule()
        self.assert_silent(self.write("game/player.gd"))


class ArchiveGatesOneChange(Case):
    """210번: 한 변경을 닫는 명령은 설계 오류와 그 변경의 오류만 본다."""

    def setUp(self):
        super().setUp()
        self.linked("add-tempo")
        self.change("bad-change")   # change_without_system

    def test_closing_the_good_change_passes(self):
        for command in ("openspec archive add-tempo --yes", "npx @fission-ai/openspec archive add-tempo -y --skip-specs",
                        "mv openspec/changes/add-tempo openspec/changes/archive/2026-11-12-add-tempo",
                        'mv "/x/openspec/changes/add-tempo/" "/x/openspec/changes/archive/2026-11-12-add-tempo"'):
            with self.subTest(command):
                self.assert_silent(self.run_hook("Bash", command=command))

    def test_closing_the_bad_change_is_blocked(self):
        for command in ("openspec archive bad-change --yes", "mv openspec/changes/bad-change openspec/changes/archive/a"):
            with self.subTest(command):
                self.assert_blocked(self.run_hook("Bash", command=command), "change_without_system")

    def test_an_unclear_target_still_sees_the_whole_project(self):
        for command in ("openspec archive", "openspec archive add-tempo bad-change", "cd openspec/changes && mv add-tempo archive/a",
                        'bash -c "openspec archive add-tempo"', "openspec archive add-tempo && openspec archive bad-change",
                        "openspec archive nope", "mv -t openspec/changes/archive openspec/changes/add-tempo", "openspec archive $(echo add-tempo)",
                        "openspec archive add-tempo --unknown"):
            with self.subTest(command):
                self.assert_blocked(self.run_hook("Bash", command=command), "change_without_system")

    def test_game_files_still_see_the_whole_project(self):
        self.assert_blocked(self.write("game/player.gd"), "change_without_system")

    def test_design_errors_still_block_closing(self):
        (self.root / "openspec/changes/bad-change").rename(self.root / "openspec/changes/archive/x")
        (self.root / "design/systems.json").write_text("{", encoding="utf-8")
        self.assert_blocked(self.run_hook("Bash", command="openspec archive add-tempo --yes"), "design_unreadable")


class SpecsPointAtRules(Case):
    """211번: 이은 시스템의 규칙을 명세가 하나도 가리키지 않으면 알린다."""

    def test_a_spec_without_rule_ids_is_a_note(self):
        self.linked(spec="### Requirement: 템포\n템포가 오른다.\n")
        found = self.note_with("규칙을 가리키지 않는 명세")
        self.assertEqual(len(found), 1, self.notes())
        self.assertIn("tempo", found[0])
        self.assertIn("tempo.tempo_up", found[0])
        self.assertEqual(self.codes(), [])

    def test_a_spec_citing_a_rule_is_quiet(self):
        self.linked(spec="### Requirement: 템포\n`tempo.tempo_up`을 따른다.\n")
        self.assertEqual(self.note_with("규칙을 가리키지 않는 명세"), [])

    def test_each_linked_system_is_seen(self):
        self.linked("add-tempo", "tempo", "room_flow", spec="`tempo.tempo_up`을 따른다.\n")
        found = self.note_with("규칙을 가리키지 않는 명세")
        self.assertEqual(len(found), 1, self.notes())
        self.assertIn("room_flow", found[0])

    def test_a_change_without_specs_is_not_measured(self):
        self.linked(proposal="템포를 손본다.\n")
        self.assertEqual(self.note_with("규칙을 가리키지 않는 명세"), [])


class RelinkAsks(Case):
    """243번: 이미 이은 변경에 시스템을 더하는 --link는 훅이 묻는다."""

    def link_command(self, *args):
        return self.run_hook("Bash", command="python3 .claude/skills/studio-data/scripts/studio.py scope --link " + " ".join(args))

    def test_adding_a_system_asks(self):
        self.linked()
        reason = asks(self.link_command("add-tempo", "tempo", "room_flow"))
        self.assertIsNotNone(reason)
        self.assertIn("room_flow", reason)
        self.assertIn("prototype.scope", reason)

    def test_other_shapes_of_the_same_command_ask(self):
        self.linked()
        for command in ("cd game && py scripts/studio.py scope --link add-tempo room_flow tempo --refresh",
                        "python3 studio.py scope --refresh --link add-tempo tempo room_flow"):
            with self.subTest(command):
                self.assertIsNotNone(asks(self.run_hook("Bash", command=command)))

    def test_the_first_link_is_silent(self):
        self.change()
        self.assert_silent(self.link_command("add-tempo", "tempo", "room_flow"))

    def test_relinking_the_same_or_fewer_is_silent(self):
        self.linked("add-tempo", "tempo", "room_flow")
        for args in (("add-tempo", "tempo", "room_flow"), ("add-tempo", "tempo"), ("add-tempo", "room_flow", "tempo", "--refresh")):
            with self.subTest(args):
                self.assert_silent(self.link_command(*args))

    def test_unclear_commands_do_not_ask(self):
        self.linked()
        for command in ('python3 studio.py scope --link add-tempo "$X"', "python3 studio.py scope --link nope tempo room_flow",
                        "echo scope --link add-tempo room_flow", "python3 studio.py check --link add-tempo room_flow"):
            with self.subTest(command):
                self.assert_silent(self.run_hook("Bash", command=command))


class SpecsAfterTasks(Case):
    """244번: 작업이 모두 끝난 뒤 명세를 고쳤으면 알리고, 닫기 전에 묻는다."""

    def setUp(self):
        super().setUp()
        self.folder = self.change(spec="`tempo.tempo_up`을 따른다.\n")
        code, out = run_cli("scope", self.root, "--link", "add-tempo", "tempo")
        self.assertEqual(code, 0, out)

    def tasks(self, text, age=100):
        path = self.folder / "tasks.md"
        path.write_text(text, encoding="utf-8")
        then = time.time() - age
        os.utime(path, (then, then))

    def test_a_spec_edited_after_all_tasks_is_a_note(self):
        self.tasks("## 1. 템포\n- [x] 1.1 올린다\n- [X] 1.2 내린다\n")
        found = self.note_with("작업이 끝난 뒤 고친 명세")
        self.assertEqual(len(found), 1, self.notes())
        self.assertIn("specs/tempo/spec.md", found[0])
        self.assertIn("/opsx:update", found[0])
        self.assertEqual(self.codes(), [])

    def test_closing_it_asks(self):
        self.tasks("- [x] 1.1 올린다\n")
        for command in ("openspec archive add-tempo --yes", "mv openspec/changes/add-tempo openspec/changes/archive/2026-11-12-add-tempo"):
            with self.subTest(command):
                reason = asks(self.run_hook("Bash", command=command))
                self.assertIsNotNone(reason)
                self.assertIn("add-tempo", reason)

    def test_closing_without_syncing_does_not_ask(self):
        self.tasks("- [x] 1.1 올린다\n")
        self.assert_silent(self.run_hook("Bash", command="openspec archive add-tempo --yes --skip-specs"))

    def test_open_tasks_or_no_tasks_say_nothing(self):
        for text in ("- [x] 1.1 올린다\n- [ ] 1.2 내린다\n", "할 일 없음\n"):
            with self.subTest(text):
                self.tasks(text)
                self.assertEqual(self.note_with("작업이 끝난 뒤 고친 명세"), [])
                self.assert_silent(self.run_hook("Bash", command="openspec archive add-tempo --yes"))

    def test_a_spec_older_than_the_tasks_says_nothing(self):
        self.tasks("- [x] 1.1 올린다\n", age=0)
        spec = self.folder / "specs/tempo/spec.md"
        then = time.time() - 100
        os.utime(spec, (then, then))
        self.assertEqual(self.note_with("작업이 끝난 뒤 고친 명세"), [])


class UnknownRuleIds(Case):
    """252번: 비슷한 규칙이 없는 id도 참고로 알린다. 대문자도 같은 규칙이다."""

    def test_an_unknown_id_without_a_close_rule_is_a_note(self):
        self.linked(spec="`tempo.tempo_up`을 따른다. `tempo.refund`로 돌려준다. `tempo.refund`\n")
        self.assertEqual(self.codes(), [])
        found = self.note_with("설계에 없는 규칙 id")
        self.assertEqual(len(found), 1, self.notes())
        self.assertIn("tempo.refund", found[0])
        self.assertIn("데이터", found[0])

    def test_a_close_typo_stays_an_error(self):
        self.linked(spec="`tempo.tempo_upp`을 따른다.\n")
        self.assertEqual(self.codes(), ["unknown_rule"])

    def test_file_names_are_not_rule_ids(self):
        self.linked(spec="`tempo.tempo_up`을 따른다. 수치는 data/tempo.json에 있다.\n")
        self.assertEqual(self.note_with("설계에 없는 규칙 id"), [])

    def test_upper_case_is_the_same_rule(self):
        self.linked(spec="TEMPO.TEMPO_UP을 따른다.\n")
        self.assertEqual((self.codes(), self.note_with("설계에 없는 규칙 id"), self.note_with("규칙을 가리키지 않는 명세")), ([], [], []))
        (self.root / "openspec/changes/add-tempo/specs/tempo/spec.md").write_text("TEMPO.TEMPO_UP과 COMBAT_INPUT.PARRY_WINDOW를 따른다.\n", encoding="utf-8")
        self.assertEqual(self.codes(), ["rule_of_unlinked_system"])


class Docs(unittest.TestCase):
    def read(self, rel):
        return (ROOT / rel).read_text(encoding="utf-8")

    def test_the_notes_are_explained(self):
        text = self.read("skills/scope-guard/SKILL.md")
        for label in ("닫은 뒤 바뀐 규칙", "규칙을 가리키지 않는 명세", "설계에 없는 규칙 id", "작업이 끝난 뒤 고친 명세"):
            with self.subTest(label):
                self.assertIn(f"`참고: {label}`", text)

    def test_the_old_limits_are_gone(self):
        text = self.read("skills/scope-guard/SKILL.md")
        for old in ("닫은 뒤에 규칙이 바뀌면 메인 스펙과 어긋나도 모른다", "명세가 규칙 id를 적었는지는 보지 않는다", "비슷한 규칙이 없으면 지나간다",
                    "작업이 모두 끝난 상태인지는 보지 않는다", "훅은 시스템을 더하는 `--link`를 묻지 않는다", "검사기는 이것을 보지 않는다"):
            with self.subTest(old):
                self.assertNotIn(old, text)
        self.assertIn("수정 시각", text)


if __name__ == "__main__":
    unittest.main()
