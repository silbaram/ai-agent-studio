"""뒤로 넘겼던 scope-guard 낮은 이슈: 212, 217~223, 243."""
import json
import unittest

from _studio import ROOT, run_cli
from studio_data import scope
from test_scope import HookCase

CMD = "python3 .claude/skills/studio-data/scripts/studio.py"


class ShellFalsePositives(HookCase):
    """217번: 범위 오류가 있어도 글을 찾거나 찍기만 하는 명령과 도움말은 막지 않는다. 진짜 보관은 그대로 막는다."""

    def setUp(self):
        super().setUp()
        self.change()   # change_without_system으로 FAIL

    def test_reading_and_help_pass(self):
        for command in ('grep -rn "openspec archive" docs', "grep -rn 'openspec archive' docs | head -5",
                        'git commit -m "docs: openspec archive 안내"', 'git commit -m "a; openspec archive add-tempo"',
                        'git log --grep "openspec archive"', "openspec archive --help", "openspec archive add-tempo -h",
                        "npx @fission-ai/openspec archive --help", "echo mv x openspec/changes/a", 'printf "%s" "mv openspec/changes/a b"',
                        'echo "openspec archive add-tempo" 2>&1 | head'):
            with self.subTest(command):
                self.assert_silent(self.run_hook("Bash", command=command))

    def test_real_archives_stay_blocked(self):
        for command in ("npx openspec archive add-tempo", "mv openspec/changes/add-tempo openspec/changes/archive/a",
                        "Move-Item openspec/changes/add-tempo openspec/changes/archive/a", "move-item openspec\\changes\\add-tempo x",
                        "a && openspec archive add-tempo", "git commit -m x && openspec archive add-tempo", "openspec archive --help; openspec archive add-tempo",
                        'bash -c "openspec archive add-tempo"', 'bash -c "openspec archive add-tempo --help"', "eval 'openspec archive add-tempo'",
                        'echo "openspec archive add-tempo" | sh', "printf 'mv openspec/changes/add-tempo x' | bash",
                        "echo $(openspec archive add-tempo)", "echo `openspec archive add-tempo`", 'git commit -m "$(openspec archive add-tempo)"',
                        "grep x <(openspec archive add-tempo)", 'GIT_PAGER="openspec archive add-tempo" git log', "git -c x=y commit -m 'openspec archive a'",
                        'git mv "openspec/changes/add-tempo" "openspec/changes/archive/a"', "openspec archive add-tempo -- --help",
                        'echo "openspec archive add-tempo',
                        "openspec \\\narchive add-tempo", "openspec archive add-tempo # --help", 'echo "a\\" ; openspec archive add-tempo ; "', "OPENSPEC archive add-tempo", "mv --help openspec/changes/add-tempo x"):
            with self.subTest(command):
                self.assert_blocked(self.run_hook("Bash", command=command), "change_without_system")

    def test_a_good_scope_still_lets_everything_through(self):
        (self.root / "openspec/changes/add-tempo/.openspec.yaml").unlink()
        self.linked()
        self.assert_silent(self.run_hook("Bash", command="openspec archive add-tempo --yes"))


class SameConcept(HookCase):
    """219번: 컨셉 키가 없으면 승인된 컨셉 하나에 잇는다. 같은 컨셉을 적는 것은 바꾼 것이 아니다."""

    def setUp(self):
        super().setUp()
        data = self.design()
        del data["concept"]
        self.save(data)
        self.data = data

    def test_writing_the_implied_concept_does_not_ask(self):
        self.assert_silent(self.write("design/systems.json", json.dumps({**self.data, "concept": "parry_tempo"}, ensure_ascii=False)))

    def test_writing_another_concept_still_asks(self):
        code, out, err = self.write("design/systems.json", json.dumps({**self.data, "concept": "greed_rooms"}, ensure_ascii=False))
        self.assertIn("greed_rooms", json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"])

    def test_with_two_approved_concepts_nothing_is_implied(self):
        concepts = self.design("design/concepts.json")
        next(x for x in concepts["concepts"] if x["id"] == "greed_rooms")["status"] = "approved"
        self.save(concepts, "design/concepts.json")
        code, out, err = self.write("design/systems.json", json.dumps({**self.data, "concept": "parry_tempo"}, ensure_ascii=False))
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"], "ask")


class Messages(HookCase):
    """220번, 212번: 메시지가 skip_specs와 설치 경로를, 바뀐 규칙을 보는 법을 말한다."""

    def test_change_without_system_names_skip_specs_and_the_installed_path(self):
        self.change()
        message = self.report()["errors"][0]["message"]
        self.assertIn("skip_specs: true", message)
        self.assertIn(f"{CMD} scope --link add-tempo", message)

    def test_a_change_with_specs_is_not_told_to_skip_them(self):
        self.change(spec="### Requirement: 템포\n")
        self.assertNotIn("skip_specs", self.report()["errors"][0]["message"])

    def test_the_hook_names_the_installed_path(self):
        self.change()
        message = self.write("game/player.gd")[2]
        self.assertIn(f"{CMD} scope", message)
        self.assertNotIn(" studio.py scope", message.replace(CMD, ""))

    def test_the_meta_guard_names_the_installed_path(self):
        self.linked()
        self.assertIn(f"{CMD} scope --link", self.write("openspec/changes/add-tempo/.openspec.yaml", "schema: spec-driven\n")[2])

    def test_design_changed_says_how_to_see_the_rule_212(self):
        self.linked()
        self.set_system("tempo", rules=[{"id": "tempo_up", "text": "다른 규칙"}, {"id": "tempo_down", "text": "맞으면 템포가 한 단계 내려간다"}])
        message = self.report()["errors"][0]["message"]
        self.assertIn("git diff design/systems.json", message)
        self.assertIn(f"{CMD} scope --link add-tempo tempo --refresh", message)


class EmptyChangeFolder(HookCase):
    """222번: 파일이 하나도 없는 변경 폴더는 막지 않고 알린다."""

    def test_an_empty_folder_is_a_note_not_an_error(self):
        (self.root / "openspec/changes/left-over/specs").mkdir(parents=True)
        report = self.report()
        self.assertEqual((report["errors"], report["changes"]), ([], []))
        self.assertEqual(len(report["notes"]), 1)
        self.assertIn("빈 변경 폴더: left-over", report["notes"][0])
        self.assert_silent(self.write("game/player.gd"))
        code, out = run_cli("scope", self.root)
        self.assertEqual(code, 0, out)
        self.assertIn("빈 변경 폴더: left-over", out)

    def test_a_folder_with_any_file_is_still_a_change(self):
        folder = self.root / "openspec/changes/left-over"
        folder.mkdir()
        (folder / "proposal.md").write_text("템포\n", encoding="utf-8")
        self.assertEqual(self.codes(), ["change_without_system"])


class PathCase(HookCase):
    """223번: 대소문자를 가리지 않는 파일 시스템에서 다른 대소문자로 지나가지 못한다."""

    def test_a_scope_file_in_other_case_asks(self):
        (self.root / "Design").mkdir()
        data = self.design()
        (self.root / "Design/systems.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        data["systems"].append({**self.system(data, "codex"), "id": "pvp", "scope": "mvp"})
        code, out, err = self.write("Design/systems.json", json.dumps(data, ensure_ascii=False))
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"], "ask")

    def test_the_hook_settings_in_other_case_ask(self):
        code, out, err = self.write(".Claude/settings.json")
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"], "ask")

    def test_the_change_meta_in_other_case_is_guarded(self):
        self.linked()
        self.assert_blocked(self.write("OpenSpec/changes/add-tempo/.openspec.yaml", "x-studio-systems: {tempo: 00000000}\n"), "scope --link")

    def test_a_main_spec_in_other_case_is_measured(self):
        self.assert_blocked(self.write("OpenSpec/Specs/rank/spec.md", "멀티플레이를 넣는다\n"), "멀티플레이")


class LinkAddsSystems(HookCase):
    """243번: 다시 이으면서 더한 시스템을 알린다."""

    def test_relinking_names_what_it_added(self):
        self.linked()
        code, out = run_cli("scope", self.root, "--link", "add-tempo", "tempo", "room_flow")
        self.assertEqual(code, 0, out)
        self.assertIn("더한 시스템: room_flow", out)
        self.assertIn("프로토타입 범위", out)

    def test_the_first_link_does_not_repeat_it(self):
        self.change()
        code, out = run_cli("scope", self.root, "--link", "add-tempo", "tempo")
        self.assertNotIn("더한 시스템", out)


class Docs(unittest.TestCase):
    """218번, 221번: 문서로 푸는 것."""

    def read(self, rel):
        return (ROOT / rel).read_text(encoding="utf-8")

    def test_scope_pass_is_not_validate_221(self):
        self.assertIn("`openspec validate --strict`로 함께 본다", self.read("skills/scope-guard/SKILL.md"))

    def test_the_setup_guide_shows_a_requirement_citing_a_rule_218(self):
        text = self.read("skills/scope-guard/references/openspec-setup.md")
        self.assertRegex(text, r"#### Scenario:[^\n]*\n(?:[^\n]*\n){0,3}[^\n]*`[a-z_]+\.[a-z_]+`")

    def test_the_skill_stays_small(self):
        self.assertLess(len(self.read("skills/scope-guard/SKILL.md").encode("utf-8")), 20000)


if __name__ == "__main__":
    unittest.main()
