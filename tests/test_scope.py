"""범위 이탈 검사(scope-guard) 테스트: OpenSpec 변경을 브리프와 시스템 설계에 대어 보고, 훅으로 막는다.

훅은 Claude Code가 표준 입력으로 주는 JSON을 받는다.
"""
import json
import shutil
import tempfile
import unicodedata
import unittest
from pathlib import Path
from unittest import mock

from _studio import ROOT, SAMPLE, claude, run_cli
from studio_data import scope


class Project(unittest.TestCase):
    """샘플 설계에 OpenSpec 폴더를 더한 게임 프로젝트."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "game"
        shutil.copytree(SAMPLE / "design", self.root / "design")
        (self.root / "openspec/changes/archive").mkdir(parents=True)
        (self.root / "openspec/specs").mkdir()

    def change(self, name="add-tempo", meta="", spec=None, proposal=None):
        folder = self.root / "openspec/changes" / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / ".openspec.yaml").write_text(f"schema: spec-driven\ncreated: 2026-11-05\n{meta}", encoding="utf-8")
        if spec is not None:
            (folder / "specs/tempo").mkdir(parents=True, exist_ok=True)
            (folder / "specs/tempo/spec.md").write_text(spec, encoding="utf-8")
        if proposal is not None:
            (folder / "proposal.md").write_text(proposal, encoding="utf-8")
        return folder

    def linked(self, name="add-tempo", *ids, **over):
        self.change(name, **over)
        code, out = run_cli("scope", self.root, "--link", name, *(ids or ["tempo"]))
        self.assertEqual(code, 0, out)

    def design(self, path="design/systems.json"):
        return json.loads((self.root / path).read_text(encoding="utf-8"))

    def save(self, data, path="design/systems.json"):
        (self.root / path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def system(self, data, sid):
        return next(s for s in data["systems"] if s["id"] == sid)

    def set_system(self, sid, **over):
        data = self.design()
        self.system(data, sid).update(over)
        self.save(data)

    def report(self):
        return scope.check(self.root)

    def codes(self):
        return [e["code"] for e in self.report()["errors"]]


class Declaration(Project):
    def test_a_linked_change_passes(self):
        self.linked()
        self.assertEqual(self.codes(), [])

    def test_no_change_passes(self):
        self.assertEqual(self.report()["errors"], [])

    def test_a_change_must_name_its_systems(self):
        self.change()
        self.assertEqual(self.codes(), ["change_without_system"])

    def test_an_empty_declaration_is_no_declaration(self):
        self.change(meta="x-studio-systems: {}\n")
        self.assertEqual(self.codes(), ["change_without_system"])

    def test_a_change_without_behavior_needs_no_system(self):
        self.change(meta="skip_specs: true\n")
        self.assertEqual(self.codes(), [])

    def test_skip_specs_is_no_way_around_with_specs_present(self):
        self.change(meta="skip_specs: true\n", spec="온라인 협동을 넣는다\n")
        self.assertEqual(self.codes(), ["change_without_system"])

    def test_skip_specs_false_still_needs_a_system(self):
        self.change(meta="skip_specs: false\n")
        self.assertEqual(self.codes(), ["change_without_system"])

    def test_a_folder_without_metadata_counts_as_undeclared(self):
        (self.root / "openspec/changes/old-change").mkdir()
        self.assertEqual(self.codes(), ["change_without_system"])

    def test_a_hand_written_form_is_an_error_not_a_pass(self):
        for meta in ("x-studio-systems: [tempo]\n", "x-studio-systems: tempo\n", "x-studio-systems:\n  - tempo\n", "x-studio-systems: {tempo}\n", "x-studio-systems: (tempo: 12345678)\n"):
            self.change(meta=meta)
            self.assertEqual(self.codes(), ["change_unreadable"], meta)

    def test_archived_changes_are_history(self):
        folder = self.root / "openspec/changes/archive/2026-11-05-old"
        folder.mkdir()
        (folder / ".openspec.yaml").write_text("schema: spec-driven\n", encoding="utf-8")
        self.assertEqual(self.codes(), [])

    def test_a_loose_file_in_changes_is_not_a_change(self):
        (self.root / "openspec/changes/notes.txt").write_text("메모", encoding="utf-8")
        self.assertEqual(self.codes(), [])


class Systems(Project):
    def test_a_system_that_is_gone_is_an_error(self):
        self.change(meta="x-studio-systems: {tempa: 12345678}\n")
        found = self.report()["errors"]
        self.assertEqual([e["code"] for e in found], ["unknown_system"])
        self.assertIn("'tempo'의 오타인가요?", found[0]["message"])

    def test_a_system_out_of_scope_is_an_error(self):
        self.linked()
        self.set_system("tempo", scope="out", out_of_scope=["도감"], mvp=[], pillars=[], depends_on=[])
        self.assertIn("system_not_in_mvp", self.codes())

    def test_a_later_system_is_an_error(self):
        self.linked()
        data = self.design()
        for sid in ("tempo",):
            self.system(data, sid).update(scope="later", mvp=[])
        self.save(data)
        self.assertIn("system_not_in_mvp", self.codes())

    def test_a_cut_system_is_an_error(self):
        self.linked()
        self.set_system("tempo", status="cut")
        self.assertIn("system_not_in_mvp", self.codes())


class Stamp(Project):
    def test_a_changed_rule_needs_another_look(self):
        self.linked()
        data = self.design()
        self.system(data, "tempo")["rules"][0]["text"] = "완전히 다른 규칙"
        self.save(data)
        found = self.report()["errors"]
        self.assertEqual([e["code"] for e in found], ["design_changed"])
        self.assertIn("tempo", found[0]["message"])

    def test_a_new_rule_counts(self):
        self.linked()
        data = self.design()
        self.system(data, "tempo")["rules"].append({"id": "extra", "text": "새 규칙"})
        self.save(data)
        self.assertEqual(self.codes(), ["design_changed"])

    def test_a_removed_rule_counts(self):
        self.linked()
        data = self.design()
        self.system(data, "tempo")["rules"].pop()
        self.save(data)
        self.assertEqual(self.codes(), ["design_changed"])

    def test_only_the_named_systems_count(self):
        self.linked()
        data = self.design()
        self.system(data, "room_flow")["rules"][0]["text"] = "완전히 다른 규칙"
        self.save(data)
        self.assertEqual(self.codes(), [])

    def test_order_and_notes_of_rules_do_not_count(self):
        self.linked()
        data = self.design()
        s = self.system(data, "tempo")
        s["rules"].reverse()
        s["rules"][0]["note"] = "메모"
        s["note"] = "시스템 메모"
        self.save(data)
        self.assertEqual(self.codes(), [])

    def test_case_is_part_of_a_rule(self):
        data = self.design()
        self.system(data, "tempo")["rules"][0]["text"] = "A키를 누르면 패링한다"
        self.save(data)
        self.linked()
        data = self.design()
        self.system(data, "tempo")["rules"][0]["text"] = "a키를 누르면 패링한다"
        self.save(data)
        self.assertEqual(self.codes(), ["design_changed"])

    def test_the_unicode_form_of_a_rule_is_not_a_change(self):
        self.linked()
        data = self.design()
        rule = self.system(data, "tempo")["rules"][0]
        rule["text"] = unicodedata.normalize("NFD", rule["text"])
        self.save(data)
        self.assertEqual(self.codes(), [])

    def test_the_message_gives_the_whole_command(self):
        self.linked("add-tempo", "tempo", "room_flow")
        data = self.design()
        self.system(data, "tempo")["rules"][0]["text"] = "완전히 다른 규칙"
        self.save(data)
        self.assertIn("--link add-tempo room_flow tempo", self.report()["errors"][0]["message"])

    def test_linking_again_settles_it(self):
        self.linked()
        data = self.design()
        self.system(data, "tempo")["rules"][0]["text"] = "완전히 다른 규칙"
        self.save(data)
        self.assertEqual(run_cli("scope", self.root, "--link", "add-tempo", "tempo")[0], 0)
        self.assertEqual(self.codes(), [])


class OutOfScopeText(Project):
    def test_a_spec_naming_an_out_of_scope_item_is_an_error(self):
        self.linked(spec="## ADDED Requirements\n\n### Requirement: 함께 하기\n멀티플레이를 지원해야 한다(SHALL).\n")
        found = self.report()["errors"]
        self.assertEqual([e["code"] for e in found], ["out_of_scope_in_spec"])
        self.assertIn("멀티플레이", found[0]["message"])
        self.assertIn("spec.md:4", found[0]["where"])

    def test_case_and_unicode_form_do_not_hide_it(self):
        data = self.design("design/concepts.json")
        data["concepts"][0]["brief"]["out_of_scope"].append("Online Rank")
        self.save(data, "design/concepts.json")
        self.linked(spec="ONLINE RANK를 붙인다\n")
        self.assertEqual(self.codes(), ["out_of_scope_in_spec"])
        self.linked(spec=unicodedata.normalize("NFD", "멀티플레이를 붙인다\n"))
        self.assertEqual(self.codes(), ["out_of_scope_in_spec"])

    def test_a_part_of_another_word_is_not_the_item(self):
        self.linked(spec="플레이 히스토리를 저장한다\n")
        self.assertEqual(self.codes(), [])

    def test_a_latin_item_needs_whole_words(self):
        data = self.design("design/concepts.json")
        data["concepts"][0]["brief"]["out_of_scope"].append("story")
        self.save(data, "design/concepts.json")
        for text in ("save the history\n", "open the storybook\n"):
            self.linked(spec=text)
            self.assertEqual(self.codes(), [], text)
        self.linked(spec="the story mode\n")
        self.assertEqual(self.codes(), ["out_of_scope_in_spec"])

    def test_a_hangul_item_may_run_into_latin(self):
        self.linked(spec="멀티플레이mode를 넣는다\n")
        self.assertEqual(self.codes(), ["out_of_scope_in_spec"])

    def test_an_item_is_text_not_a_pattern(self):
        data = self.design("design/concepts.json")
        data["concepts"][0]["brief"]["out_of_scope"] += ["c++", "유료(시즌)"]
        self.save(data, "design/concepts.json")
        self.linked(spec="유료(시즌)를 넣는다\n")
        self.assertEqual(self.codes(), ["out_of_scope_in_spec"])
        self.linked(spec="유료시즌을 넣는다\n")
        self.assertEqual(self.codes(), [])

    def test_a_particle_after_the_item_is_still_the_item(self):
        self.linked(spec="스토리를 넣는다\n")
        self.assertEqual(self.codes(), ["out_of_scope_in_spec"])

    def test_a_brief_in_the_data_folder_is_read(self):
        (self.root / "data").mkdir()
        self.linked(spec="멀티플레이를 붙인다\n")
        (self.root / "design/concepts.json").rename(self.root / "data/concepts.json")
        self.assertEqual(self.codes(), ["out_of_scope_in_spec"])

    def test_a_task_naming_an_out_of_scope_item_is_an_error(self):
        folder = self.change()
        (folder / "tasks.md").write_text("- [ ] 1.1 멀티플레이 서버를 붙인다\n", encoding="utf-8")
        run_cli("scope", self.root, "--link", "add-tempo", "tempo")
        found = self.report()["errors"]
        self.assertEqual([e["code"] for e in found], ["out_of_scope_in_spec"])
        self.assertIn("tasks.md:1", found[0]["where"])

    def test_a_proposal_naming_an_out_of_scope_item_is_an_error(self):
        self.linked(proposal="## What Changes\n- 멀티플레이를 넣는다\n")
        self.assertEqual(self.codes(), ["out_of_scope_in_spec"])

    def test_a_design_note_may_list_non_goals(self):
        folder = self.change()
        (folder / "design.md").write_text("## Non-Goals\n- 멀티플레이\n", encoding="utf-8")
        run_cli("scope", self.root, "--link", "add-tempo", "tempo")
        self.assertEqual(self.codes(), [])

    def test_skip_specs_changes_are_measured_too(self):
        folder = self.change(meta="skip_specs: true\n")
        (folder / "tasks.md").write_text("- [ ] 멀티플레이 서버\n", encoding="utf-8")
        self.assertEqual(self.codes(), ["out_of_scope_in_spec"])

    def test_removing_an_out_of_scope_requirement_is_the_point(self):
        text = "## REMOVED Requirements\n\n### Requirement: 멀티플레이\n**Reason**: 범위 밖\n\n## ADDED Requirements\n\n### Requirement: 혼자\n혼자 한다\n"
        self.linked(spec=text)
        self.assertEqual(self.codes(), [])
        self.linked(spec=text.replace("혼자 한다", "멀티플레이를 한다"))
        self.assertEqual(self.codes(), ["out_of_scope_in_spec"])

    def test_a_blank_item_matches_nothing(self):
        self.assertEqual(scope._found_items("패링\n", [" ", ""]), [])

    def test_a_clean_spec_passes(self):
        self.linked(spec="패링에 성공하면 템포가 오른다\n")
        self.assertEqual(self.codes(), [])

    def test_without_a_brief_there_is_nothing_to_measure_against(self):
        self.linked(spec="멀티플레이를 붙인다\n")
        (self.root / "design/concepts.json").unlink()
        found = self.report()["errors"]
        self.assertEqual([e["code"] for e in found], ["design_unreadable"])
        self.assertIn("브리프", found[0]["message"])


class BrokenDesign(Project):
    """설계를 믿을 수 없으면 범위도 믿을 수 없다. 조용히 열리면 안 된다."""

    def test_an_unreadable_design_is_an_error(self):
        self.linked()
        (self.root / "design/systems.json").write_text("{", encoding="utf-8")
        self.assertEqual(self.codes(), ["design_unreadable"])

    def test_a_design_with_errors_is_an_error(self):
        self.linked()
        self.set_system("tempo", scope="soon")
        self.assertEqual(self.codes(), ["design_invalid"])

    def test_a_broken_shape_is_an_error_not_a_crash(self):
        self.linked()
        for body in ('{"concept": "parry_tempo", "systems": null}', '{"concept": "parry_tempo", "systems": 5}', '{"concept": "parry_tempo", "systems": {"a": 1}}',
                     '{"concept": "parry_tempo", "systems": [{"name": "x"}]}', '{"concept": "parry_tempo", "systems": ["tutorial"]}'):
            (self.root / "design/systems.json").write_text(body, encoding="utf-8")
            self.assertEqual(self.codes(), ["design_invalid"], body)

    def test_a_brief_with_errors_is_an_error(self):
        self.linked()
        data = self.design("design/concepts.json")
        data["concepts"][0]["brief"]["out_of_scope"].append(" ")
        self.save(data, "design/concepts.json")
        found = self.report()["errors"]
        self.assertEqual([(e["code"], e["where"]) for e in found], [("design_invalid", "concepts.json")])

    def test_broken_concepts_are_an_error(self):
        self.linked()
        (self.root / "design/concepts.json").write_text("{", encoding="utf-8")
        found = self.report()["errors"]
        self.assertEqual([(e["code"], e["where"]) for e in found], [("design_unreadable", "concepts.json")])


class Command(Project):
    def test_pass_and_fail(self):
        self.linked()
        code, out = run_cli("scope", self.root)
        self.assertEqual(code, 0, out)
        self.assertIn("변경 1개 · 오류 0 → PASS", out)
        self.change("add-other")
        code, out = run_cli("scope", self.root)
        self.assertEqual(code, 1, out)
        self.assertIn("[change_without_system]", out)
        self.assertIn("→ FAIL", out)

    def test_nothing_to_measure_is_not_a_pass(self):
        code, out = run_cli("scope", self.root)
        self.assertEqual(code, 0, out)
        self.assertIn("잴 변경 없음", out)
        self.assertNotIn("PASS", out)

    def test_json(self):
        self.change()
        code, out = run_cli("scope", self.root, "--json")
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["errors"][0]["code"], "change_without_system")

    def test_no_openspec_folder_is_a_usage_error(self):
        shutil.rmtree(self.root / "openspec")
        self.assertEqual(run_cli("scope", self.root)[0], 2)

    def test_no_system_design_is_a_usage_error(self):
        (self.root / "design/systems.json").unlink()
        self.assertEqual(run_cli("scope", self.root)[0], 2)

    def test_a_missing_project_is_a_usage_error(self):
        self.assertEqual(run_cli("scope", self.root / "none")[0], 2)

    def test_link_writes_and_keeps_the_rest(self):
        folder = self.change(meta="goal: 템포\n")
        code, out = run_cli("scope", self.root, "--link", "add-tempo", "tempo", "room_flow")
        self.assertEqual(code, 0, out)
        text = (folder / ".openspec.yaml").read_text(encoding="utf-8")
        self.assertIn("schema: spec-driven\n", text)
        self.assertIn("goal: 템포\n", text)
        self.assertRegex(text, r"x-studio-systems: \{room_flow: [0-9a-f]{8}, tempo: [0-9a-f]{8}\}\n")

    def test_link_replaces_its_own_line(self):
        folder = self.change()
        run_cli("scope", self.root, "--link", "add-tempo", "tempo")
        run_cli("scope", self.root, "--link", "add-tempo", "room_flow")
        text = (folder / ".openspec.yaml").read_text(encoding="utf-8")
        self.assertEqual(text.count("x-studio-systems"), 1)
        self.assertIn("room_flow", text)
        self.assertNotIn("tempo:", text)

    def test_link_says_what_it_dropped(self):
        self.change()
        run_cli("scope", self.root, "--link", "add-tempo", "tempo", "room_flow")
        code, out = run_cli("scope", self.root, "--link", "add-tempo", "tempo")
        self.assertEqual(code, 0)
        self.assertIn("뺀 시스템: room_flow", out)

    def test_link_replaces_a_hand_written_list(self):
        folder = self.change(meta="x-studio-systems:\n  - tempo\n  - room_flow\ngoal: 템포\n")
        self.assertEqual(run_cli("scope", self.root, "--link", "add-tempo", "tempo")[0], 0)
        text = (folder / ".openspec.yaml").read_text(encoding="utf-8")
        self.assertNotIn("- room_flow", text)
        self.assertIn("goal: 템포\n", text)
        self.assertEqual(self.codes(), [])

    def test_link_adds_a_line_break_if_the_file_has_none(self):
        folder = self.change()
        (folder / ".openspec.yaml").write_text("schema: spec-driven", encoding="utf-8")
        run_cli("scope", self.root, "--link", "add-tempo", "tempo")
        self.assertIn("schema: spec-driven\nx-studio-systems", (folder / ".openspec.yaml").read_text(encoding="utf-8"))

    def test_link_refuses_what_it_would_refuse_later(self):
        folder = self.change()
        before = (folder / ".openspec.yaml").read_text(encoding="utf-8")
        for sid in ("codex", "nothing_here"):
            code, out = run_cli("scope", self.root, "--link", "add-tempo", sid)
            self.assertEqual(code, 1, sid)
            self.assertEqual((folder / ".openspec.yaml").read_text(encoding="utf-8"), before)

    def test_link_needs_a_change_and_a_system(self):
        self.assertEqual(run_cli("scope", self.root, "--link", "no-such-change", "tempo")[0], 2)
        self.change()
        self.assertEqual(run_cli("scope", self.root, "--link", "add-tempo")[0], 2)

    def test_link_keeps_out_of_the_tree(self):
        self.assertEqual(run_cli("scope", self.root, "--link", "../../design", "tempo")[0], 2)
        self.assertEqual(run_cli("scope", self.root, "--link", "archive", "tempo")[0], 2)

    def test_link_refuses_an_archived_change(self):
        folder = self.root / "openspec/changes/archive/2026-11-05-old"
        folder.mkdir()
        (folder / ".openspec.yaml").write_text("schema: spec-driven\n", encoding="utf-8")
        self.assertEqual(run_cli("scope", self.root, "--link", "archive/2026-11-05-old", "tempo")[0], 2)
        self.assertNotIn("x-studio", (folder / ".openspec.yaml").read_text(encoding="utf-8"))

    def test_link_needs_the_metadata_file(self):
        (self.root / "openspec/changes/old-change").mkdir()
        self.assertEqual(run_cli("scope", self.root, "--link", "old-change", "tempo")[0], 2)

    def test_link_refuses_a_design_with_errors(self):
        folder = self.change()
        self.set_system("room_flow", scope="soon")
        self.assertEqual(run_cli("scope", self.root, "--link", "add-tempo", "tempo")[0], 1)
        self.assertNotIn("x-studio", (folder / ".openspec.yaml").read_text(encoding="utf-8"))

    def test_link_reports_a_file_it_cannot_decode(self):
        folder = self.change()
        (folder / ".openspec.yaml").write_bytes(b"schema: \xff\n")
        self.assertEqual(run_cli("scope", self.root, "--link", "add-tempo", "tempo")[0], 2)

    def test_link_refuses_an_unreadable_design(self):
        self.change()
        (self.root / "design/systems.json").write_text("{", encoding="utf-8")
        self.assertEqual(run_cli("scope", self.root, "--link", "add-tempo", "tempo")[0], 1)

    def test_link_says_the_design_is_the_problem(self):
        self.change()
        self.set_system("room_flow", scope="soon")
        code, lines = scope.link(self.root, "add-tempo", ["tempo"])
        self.assertEqual(code, 1)
        self.assertIn("[design_invalid]", lines[0])


class HookCase(Project):
    def run_hook(self, tool, **tool_input):
        return claude.scope_guard(json.dumps({"tool_name": tool, "tool_input": tool_input}), self.root)

    def write(self, rel, content="x"):
        return self.run_hook("Write", file_path=str(self.root / rel), content=content)

    def assert_blocked(self, result, code):
        self.assertEqual(result[0], 2, result)
        self.assertIn(code, result[2])

    def assert_silent(self, result):
        self.assertEqual(result, (0, "", ""))


class Hook(HookCase):
    def test_a_bad_change_blocks_building(self):
        self.change()
        self.assert_blocked(self.write("game/player.gd"), "change_without_system")

    def test_a_good_change_does_not(self):
        self.linked()
        self.assert_silent(self.write("game/player.gd"))

    def test_no_change_does_not(self):
        self.assert_silent(self.write("game/player.gd"))

    def test_every_write_tool_counts(self):
        self.change()
        self.assert_blocked(self.run_hook("Edit", file_path="game/player.gd", old_string="a", new_string="b"), "change_without_system")
        self.assert_blocked(self.run_hook("MultiEdit", file_path="game/player.gd", edits=[]), "change_without_system")
        self.assert_blocked(self.run_hook("NotebookEdit", notebook_path="game/a.ipynb"), "change_without_system")

    def test_planning_files_stay_open_so_the_change_can_be_fixed(self):
        self.change()
        for rel in ("openspec/changes/add-tempo/proposal.md", "openspec/config.yaml", "data/items.json", "docs/a.txt", "reports/a.txt", ".claude/notes.txt", ".claude/skills/other/SKILL.md", "notes.md", "game/notes.md"):
            self.assert_silent(self.write(rel))

    def test_turning_the_guard_off_asks(self):
        self.change()
        for rel in (".claude/settings.json", ".claude/settings.local.json", ".claude/skills/studio-data/scripts/studio.py", ".claude/skills/scope-guard/SKILL.md"):
            code, out, err = self.write(rel)
            self.assertEqual((code, err), (0, ""), rel)
            self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"], "ask", rel)

    def test_a_new_main_spec_cannot_name_an_out_of_scope_item(self):
        self.assert_blocked(self.write("openspec/specs/rank/spec.md", "멀티플레이를 넣는다\n"), "멀티플레이")

    def test_an_edit_of_a_main_spec_cannot_add_one(self):
        path = self.root / "openspec/specs/tempo/spec.md"
        path.parent.mkdir()
        path.write_text("보석 수확\n", encoding="utf-8")
        self.assert_blocked(self.run_hook("Edit", file_path=str(path), old_string="보석 수확", new_string="멀티플레이"), "멀티플레이")

    def test_an_old_line_of_a_main_spec_does_not_block_other_edits(self):
        path = self.root / "openspec/specs/tempo/spec.md"
        path.parent.mkdir()
        path.write_text("멀티플레이\n보석 수확\n", encoding="utf-8")
        self.assert_silent(self.run_hook("Edit", file_path=str(path), old_string="보석 수확", new_string="보석 줍기"))

    def test_the_content_of_a_game_file_is_not_read(self):
        self.linked()
        self.assert_silent(self.write("game/modes.gd", "# 멀티플레이는 없다\n"))

    def test_an_odd_edit_of_a_main_spec_is_left_to_the_tool(self):
        path = self.root / "openspec/specs/tempo/spec.md"
        self.assert_silent(self.run_hook("Edit", file_path=str(path), old_string="a", new_string="b"))
        path.parent.mkdir()
        path.write_bytes(b"\xff\n")
        self.assert_silent(self.run_hook("Edit", file_path=str(path), old_string="a", new_string="b"))
        path.write_text("보석\n", encoding="utf-8")
        self.assert_silent(self.run_hook("Edit", file_path=str(path)))

    def test_a_clean_main_spec_passes(self):
        self.assert_silent(self.write("openspec/specs/rank/spec.md", "패링을 넣는다\n"))

    def test_a_game_file_with_a_design_name_is_a_game_file(self):
        self.change()
        self.assert_blocked(self.write("game/systems.json"), "change_without_system")
        self.assert_blocked(self.write("game/concepts.json"), "change_without_system")

    def test_reading_is_not_building(self):
        self.change()
        self.assert_silent(self.run_hook("Read", file_path="game/player.gd"))

    def test_the_main_specs_are_guarded(self):
        self.change()
        self.assert_blocked(self.write("openspec/specs/tempo/spec.md"), "change_without_system")

    def test_files_outside_the_project_are_not_ours(self):
        self.change()
        self.assert_silent(self.write("../elsewhere/player.gd"))

    def test_a_project_without_openspec_is_left_alone(self):
        self.change()
        shutil.rmtree(self.root / "openspec")
        self.assert_silent(self.write("game/player.gd"))

    def test_a_project_without_system_design_is_left_alone(self):
        self.change()
        (self.root / "design/systems.json").unlink()
        self.assert_silent(self.write("game/player.gd"))

    def test_a_broken_design_closes_the_gate(self):
        self.linked()
        (self.root / "design/systems.json").write_text("{", encoding="utf-8")
        self.assert_blocked(self.write("game/player.gd"), "design_unreadable")

    def test_a_broken_shape_closes_the_gate(self):
        self.linked()
        (self.root / "design/systems.json").write_text('{"concept": "parry_tempo", "systems": null}', encoding="utf-8")
        self.assert_blocked(self.write("game/player.gd"), "design_invalid")

    def test_a_crash_closes_the_gate(self):
        with mock.patch.object(scope, "check", side_effect=RuntimeError("터짐")):
            self.assert_blocked(self.write("game/player.gd"), "터짐")

    def test_archive_is_guarded(self):
        self.change()
        for command in ("openspec archive add-tempo --yes", "npx @fission-ai/openspec archive add-tempo", "cd x && openspec.cmd archive add-tempo",
                        "npx -y @fission-ai/openspec@latest archive add-tempo", "openspec --no-color archive add-tempo", 'bash -c "openspec archive add-tempo"'):
            self.assert_blocked(self.run_hook("Bash", command=command), "change_without_system")

    def test_moving_a_change_into_the_archive_is_guarded(self):
        self.change()
        for command in ('mv "/x/openspec/changes/add-tempo" "/x/openspec/changes/archive/2026-11-05-add-tempo"', "mv openspec/changes/add-tempo openspec/changes/archive/a",
                        "git mv openspec/changes/add-tempo openspec/changes/archive/a", "cd openspec/changes && mv add-tempo archive/a", "Move-Item openspec\\changes\\add-tempo openspec\\changes\\archive\\a"):
            self.assert_blocked(self.run_hook("Bash", command=command), "change_without_system")

    def test_a_good_archive_passes(self):
        self.linked()
        self.assert_silent(self.run_hook("Bash", command="openspec archive add-tempo --yes"))

    def test_moving_a_change_away_is_guarded(self):
        self.change()
        self.assert_blocked(self.run_hook("Bash", command="mv openspec/changes/add-tempo ../parked"), "change_without_system")

    def test_other_commands_pass(self):
        self.change()
        for command in ("openspec list --json", "openspec list --archived", "openspec validate add-tempo --strict", "ls archive", "git commit -m 'openspec notes'",
                        "mv game/a.gd game/b.gd", "rm -rf openspec/changes/add-tempo"):
            self.assert_silent(self.run_hook("Bash", command=command))

    def test_the_message_says_how_to_fix_it(self):
        self.change()
        message = self.write("game/player.gd")[2]
        self.assertIn("studio.py scope", message)
        self.assertIn("--link", message)

    def test_bad_input_does_not_break_the_session(self):
        for text in ("", "[]", "{", '{"tool_name": "Write"}', '{"tool_name": "Write", "tool_input": []}', '{"tool_name": "Write", "tool_input": {"file_path": 5}}',
                     '{"tool_name": "Bash", "tool_input": {"command": 5}}'):
            self.assertEqual(claude.scope_guard(text, self.root), (0, "", ""), text)

    def test_the_project_folder_is_not_a_file(self):
        self.assert_silent(self.write("."))


class Widening(HookCase):
    """범위를 넓히는 편집은 사람이 정한다. 막지 않고 사용자에게 묻는다."""

    def assert_asks(self, result, *words):
        code, out, err = result
        self.assertEqual((code, err), (0, ""), result)
        decision = json.loads(out)["hookSpecificOutput"]
        self.assertEqual((decision["hookEventName"], decision["permissionDecision"]), ("PreToolUse", "ask"))
        for word in words:
            self.assertIn(word, decision["permissionDecisionReason"])

    def rewrite(self, data, path="design/systems.json"):
        return self.write(path, json.dumps(data, ensure_ascii=False))

    def test_a_new_mvp_item_asks(self):
        data = self.design("design/concepts.json")
        data["concepts"][0]["brief"]["mvp"].append("온라인 협동")
        self.assert_asks(self.rewrite(data, "design/concepts.json"), "온라인 협동")

    def test_lifting_an_out_of_scope_item_asks(self):
        data = self.design("design/concepts.json")
        data["concepts"][0]["brief"]["out_of_scope"].remove("멀티플레이")
        self.assert_asks(self.rewrite(data, "design/concepts.json"), "멀티플레이")

    def test_narrowing_does_not_ask(self):
        data = self.design("design/concepts.json")
        data["concepts"][0]["brief"]["mvp"].pop()
        data["concepts"][0]["brief"]["out_of_scope"].append("순위표")
        self.assert_silent(self.rewrite(data, "design/concepts.json"))

    def test_the_concept_in_use_counts_even_before_approval(self):
        data = self.design("design/concepts.json")
        data["concepts"][0]["status"] = "proposed"
        self.save(data, "design/concepts.json")
        data["concepts"][0]["brief"]["out_of_scope"].remove("멀티플레이")
        self.assert_asks(self.rewrite(data, "design/concepts.json"), "멀티플레이")

    def test_a_broken_system_design_does_not_stop_the_question(self):
        data = self.design("design/concepts.json")
        data["concepts"][0]["brief"]["mvp"].append("온라인 협동")
        for text in ("{", "[]"):
            (self.root / "design/systems.json").write_text(text, encoding="utf-8")
            self.assert_asks(self.rewrite(data, "design/concepts.json"), "온라인 협동")

    def test_a_brief_in_the_data_folder_counts(self):
        (self.root / "data").mkdir()
        (self.root / "design/concepts.json").rename(self.root / "data/concepts.json")
        data = self.design("data/concepts.json")
        data["concepts"][0]["brief"]["mvp"].append("온라인 협동")
        self.assert_asks(self.rewrite(data, "data/concepts.json"), "온라인 협동")

    def test_a_proposed_concept_is_still_a_draft(self):
        data = self.design("design/concepts.json")
        draft = next(x for x in data["concepts"] if x["status"] == "proposed")
        draft["brief"] = {"mvp": ["온라인 협동"]}
        self.assert_silent(self.rewrite(data, "design/concepts.json"))

    def test_approving_another_concept_asks(self):
        data = self.design("design/concepts.json")
        draft = next(x for x in data["concepts"] if x["status"] == "proposed")
        draft["status"] = "approved"
        self.assert_asks(self.rewrite(data, "design/concepts.json"), draft["id"])

    def test_a_new_mvp_system_asks(self):
        data = self.design()
        data["systems"].append({"id": "online_coop", "name": "협동", "scope": "mvp", "foundation": True, "rules": [{"id": "a", "text": "b"}]})
        self.assert_asks(self.rewrite(data), "online_coop")

    def test_a_new_later_system_does_not_ask(self):
        data = self.design()
        data["systems"].append({"id": "online_coop", "name": "협동", "scope": "later", "rules": []})
        self.assert_silent(self.rewrite(data))

    def test_moving_a_system_into_the_mvp_asks(self):
        data = self.design()
        self.system(data, "codex")["scope"] = "mvp"
        self.assert_asks(self.rewrite(data), "codex")

    def test_reviving_a_cut_system_asks(self):
        self.set_system("tempo", status="cut")
        data = self.design()
        self.system(data, "tempo")["status"] = "approved"
        self.assert_asks(self.rewrite(data), "tempo")

    def test_changing_the_concept_asks(self):
        data = self.design()
        data["concept"] = "greed_rooms"
        self.assert_asks(self.rewrite(data), "greed_rooms")

    def test_changing_a_rule_does_not_ask(self):
        data = self.design()
        self.system(data, "tempo")["rules"][0]["text"] = "다른 규칙"
        self.assert_silent(self.rewrite(data))

    def test_edit_is_applied_before_comparing(self):
        path = self.root / "design/systems.json"
        text = path.read_text(encoding="utf-8")
        old = '"id": "codex",'
        at = text.index(old)
        scope_at = text.index('"scope": "out"', at)
        result = self.run_hook("Edit", file_path=str(path), old_string=text[at:scope_at + 14], new_string=text[at:scope_at] + '"scope": "mvp"')
        self.assert_asks(result, "codex")

    def test_multi_edit_is_applied_in_order(self):
        path = self.root / "design/systems.json"
        text = path.read_text(encoding="utf-8")
        at = text.index('"id": "codex",')
        scope_at = text.index('"scope": "out"', at)
        block = text[at:scope_at + 14]
        edits = [{"old_string": block, "new_string": block.replace('"scope": "out"', '"scope": "later"')},
                 {"old_string": block.replace('"scope": "out"', '"scope": "later"'), "new_string": block.replace('"scope": "out"', '"scope": "mvp"')}]
        self.assert_asks(self.run_hook("MultiEdit", file_path=str(path), edits=edits), "codex")

    def test_replace_all_counts(self):
        self.set_system("meta_unlocks", scope="out", out_of_scope=["도감"], mvp=[], pillars=[], depends_on=[])
        path = self.root / "design/systems.json"
        result = self.run_hook("Edit", file_path=str(path), old_string='"scope": "out"', new_string='"scope": "mvp"', replace_all=True)
        self.assert_asks(result, "codex", "meta_unlocks")

    def test_a_failing_edit_is_left_to_the_tool(self):
        path = self.root / "design/systems.json"
        self.assert_silent(self.run_hook("Edit", file_path=str(path), old_string="없는 글", new_string='"scope": "mvp"'))

    def test_an_edit_of_an_unknown_shape_is_left_to_the_tool(self):
        path = str(self.root / "design/systems.json")
        self.assert_silent(self.run_hook("Edit", file_path=path))
        self.assert_silent(self.run_hook("Edit", file_path=path, old_string="a", new_string=5))
        self.assert_silent(self.run_hook("MultiEdit", file_path=path, edits=5))
        self.assert_silent(self.run_hook("MultiEdit", file_path=path, edits=[5]))
        self.assert_silent(self.run_hook("Write", file_path=path, content=5))

    def test_a_byte_order_mark_does_not_hide_it(self):
        data = self.design()
        self.system(data, "codex")["scope"] = "mvp"
        self.assert_asks(self.write("design/systems.json", "\ufeff" + json.dumps(data, ensure_ascii=False)), "codex")

    def test_content_it_cannot_read_asks(self):
        for text in ("{", "[]"):
            self.assert_asks(self.write("design/systems.json", text), "읽을 수 없")

    def test_a_broken_file_cannot_be_a_stepping_stone(self):
        (self.root / "design/systems.json").write_text("{", encoding="utf-8")
        self.assert_asks(self.write("design/systems.json", "{}"), "읽을 수 없")

    def test_undecodable_bytes_ask(self):
        (self.root / "design/systems.json").write_bytes(b"\xff{")
        self.assert_asks(self.run_hook("Edit", file_path=str(self.root / "design/systems.json"), old_string="a", new_string="b"), "읽을 수 없")

    def test_taking_back_approval_asks(self):
        data = self.design("design/concepts.json")
        data["concepts"][0]["status"] = "proposed"
        self.assert_asks(self.rewrite(data, "design/concepts.json"), "parry_tempo")

    def test_shapes_that_are_not_a_design_do_not_crash(self):
        for text in ('{"systems": 5}', '{"systems": [5]}', '{"concepts": [5]}', '{"concepts": [{"status": "approved", "brief": 5}]}', '{"concepts": [{"status": "approved", "brief": {"mvp": 5}}]}'):
            self.assertEqual(self.write("design/systems.json", text)[0], 0, text)
            self.assertEqual(self.write("design/concepts.json", text)[0], 0, text)

    def test_the_first_brief_does_not_ask(self):
        (self.root / "design/concepts.json").unlink()
        self.assert_silent(self.write("design/concepts.json", '{"concepts": [{"id": "a", "status": "approved", "brief": {"mvp": ["b"]}}]}'))
        self.assert_silent(self.run_hook("Edit", file_path=str(self.root / "design/concepts.json"), old_string="a", new_string="b"))

    def test_the_first_design_does_not_ask(self):
        (self.root / "design/systems.json").unlink()
        self.assert_silent(self.write("design/systems.json", '{"systems": [{"id": "a", "scope": "mvp"}]}'))

    def test_before_openspec_the_design_is_free(self):
        shutil.rmtree(self.root / "openspec")
        data = self.design()
        self.system(data, "codex")["scope"] = "mvp"
        self.assert_silent(self.rewrite(data))

    def test_design_files_are_not_blocked_by_a_bad_change(self):
        self.change()
        data = self.design()
        self.system(data, "tempo")["rules"][0]["text"] = "다른 규칙"
        self.assert_silent(self.rewrite(data))


class Setup(Project):
    def test_setup_installs_the_guard_once(self):
        for _ in range(2):
            self.assertEqual(run_cli("setup", "claude", self.root)[0], 0)
        settings = json.loads((self.root / ".claude/settings.json").read_text(encoding="utf-8"))
        commands = [h["command"] for g in settings["hooks"]["PreToolUse"] for h in g["hooks"]]
        self.assertEqual(sum(" hook scope-guard" in x for x in commands), 1)
        self.assertEqual(sum(" hook judge-guard" in x for x in commands), 1)

    def test_the_guard_watches_writes_and_commands(self):
        run_cli("setup", "claude", self.root)
        settings = json.loads((self.root / ".claude/settings.json").read_text(encoding="utf-8"))
        group = next(g for g in settings["hooks"]["PreToolUse"] if " hook scope-guard" in g["hooks"][0]["command"])
        for tool in ("Write", "Edit", "MultiEdit", "NotebookEdit", "Bash"):
            self.assertIn(tool, group["matcher"])

    def test_the_hook_command_runs(self):
        self.change()
        import io
        import sys
        payload = json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(self.root / "game/a.gd")}, "cwd": str(self.root)})
        stdin = io.TextIOWrapper(io.BytesIO(payload.encode("utf-8")), encoding="utf-8")
        with mock.patch.object(sys, "stdin", stdin), mock.patch.dict("os.environ", {"CLAUDE_PROJECT_DIR": str(self.root)}):
            self.assertEqual(run_cli("hook", "scope-guard")[0], 2)


class Docs(unittest.TestCase):
    def test_the_skill_is_registered(self):
        skill = (ROOT / "skills/scope-guard/SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(skill.startswith("---\nname: scope-guard\n"))
        self.assertTrue((ROOT / "skills/scope-guard/agents/openai.yaml").exists())
        self.assertIn("[scope-guard](skills/scope-guard/SKILL.md)", (ROOT / "README.md").read_text(encoding="utf-8"))

    def test_every_code_is_explained(self):
        skill = (ROOT / "skills/scope-guard/SKILL.md").read_text(encoding="utf-8")
        for code in ("change_without_system", "change_unreadable", "unknown_system", "system_not_in_mvp", "design_changed", "out_of_scope_in_spec", "design_unreadable", "design_invalid"):
            self.assertIn(f"`{code}`", skill)

    def test_the_setup_guide_has_the_config(self):
        text = (ROOT / "skills/scope-guard/references/openspec-setup.md").read_text(encoding="utf-8")
        for word in ("openspec init", "--language ko", "OPENSPEC_TELEMETRY", "context:", "scope --link"):
            self.assertIn(word, text)

    def test_the_decision_is_recorded(self):
        text = (ROOT / "docs/architecture.md").read_text(encoding="utf-8")
        self.assertNotIn("spec-kit 또는 OpenSpec", text)
        self.assertNotIn("뼈대 도구 선택(spec-kit / OpenSpec)", text)


if __name__ == "__main__":
    unittest.main()
