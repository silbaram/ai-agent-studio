"""시스템 설계(S1) 테스트: 시스템의 규칙과 의존 관계를 브리프의 필러·범위에 잇는다. 표준 라이브러리 unittest만 사용한다."""
import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from _studio import ROOT, SAMPLE, STUDIO, common, datasets, run_cli, systems as sy

BRIEF = {"pillars": [{"name": "욕심이 곧 성장", "test": "t"}, {"name": "숙성이 읽힌다", "test": "t"}], "mvp": ["보석 숙성 3단계", "조준 무기"], "out_of_scope": ["멀티플레이"]}
CONCEPTS = [{"id": "gems", "status": "approved", "brief": BRIEF}, {"id": "other", "status": "proposed"}]


def system(sid="ripening", scope="mvp", **over):
    return {"id": sid, "scope": scope, "pillars": ["욕심이 곧 성장", "숙성이 읽힌다"], "mvp": ["보석 숙성 3단계", "조준 무기"], "rules": [{"id": "r1", "text": "보석은 3단계로 익는다"}], **over}


def run(*entries, concepts=CONCEPTS, **top):
    return sy.validate({"systems": list(entries) or [system()], **top}, concepts=concepts)


def codes(rows):
    return [x["code"] for x in rows]


def warning(result, code):
    return next(w for w in result["warnings"] if w["code"] == code)


def row(result, sid="ripening"):
    return next(x for x in result["rows"] if x["id"] == sid)


class Shape(unittest.TestCase):
    def test_a_good_system_passes_clean(self):
        r = run()
        self.assertEqual((r["errors"], r["warnings"], r["unchecked"]), ([], [], 0))

    def test_bad_shapes_are_errors(self):
        for bad in (system(scope="soon"), system(pillars="글"), system(pillars=[1]), system(mvp="글"), system(depends_on="글"), system(rules="글"), system(rules=[{"id": "r1"}]), system(rules=[{"text": "id 없음"}]),
                    system(oops=1), {"id": "x"}):
            self.assertIn("schema", codes(run(bad)["errors"]), bad)

    def test_a_typo_in_a_rule_is_an_error(self):
        self.assertIn("schema", codes(run(system(rules=[{"id": "r1", "text": "a", "txet": "b"}]))["errors"]))

    def test_rule_ids_do_not_repeat_within_a_system(self):
        self.assertIn("duplicate_id", codes(run(system(rules=[{"id": "r1", "text": "a"}, {"id": "r1", "text": "b"}]))["errors"]))

    def test_a_typo_at_the_top_of_the_file_is_an_error(self):
        self.assertIn("concept", next(e["message"] for e in sy.validate({"systems": [system()], "concpt": "gems"}, concepts=CONCEPTS)["errors"] if e["code"] == "schema"))

    def test_ids_do_not_repeat(self):
        self.assertIn("duplicate_id", codes(run(system(), system())["errors"]))

    def test_systems_of_another_shape_are_an_error(self):
        self.assertIn("schema", codes(sy.validate({"systems": 5}, concepts=CONCEPTS)["errors"]))


class Concept(unittest.TestCase):
    def test_the_single_approved_concept_is_used(self):
        self.assertEqual(run()["concept"], "gems")

    def test_a_written_concept_wins(self):
        two = [*CONCEPTS, {"id": "more", "status": "approved", "brief": BRIEF}]
        self.assertEqual(run(concepts=two, concept="more")["concept"], "more")

    def test_two_approved_concepts_need_a_choice(self):
        two = [*CONCEPTS, {"id": "more", "status": "approved", "brief": BRIEF}]
        self.assertIn("concept", next(e["message"] for e in run(concepts=two)["errors"]))

    def test_an_unknown_concept_is_an_error_with_a_hint(self):
        self.assertIn("gems", next(e["message"] for e in run(concept="gem")["errors"] if e["code"] == "unknown_concept"))

    def test_a_cut_concept_is_reported(self):
        r = run(concepts=[{"id": "gems", "status": "cut", "brief": BRIEF}], concept="gems")
        self.assertEqual(warning(r, "cut_referenced")["where"], "concept")

    def test_a_concept_without_a_brief_is_an_error(self):
        self.assertIn("brief_missing", codes(run(concept="other")["errors"]))

    def test_without_concepts_the_links_are_unchecked(self):
        r = run(concepts=None)
        self.assertEqual(r["errors"], [])
        self.assertIn("concepts", r["unchecked_kinds"])


class BriefLinks(unittest.TestCase):
    def test_an_unknown_pillar_is_an_error_with_a_hint(self):
        self.assertIn("욕심이 곧 성장", next(e["message"] for e in run(system(pillars=["욕심이 곧 성장함"]))["errors"] if e["code"] == "unknown_pillar"))

    def test_an_unknown_mvp_item_is_an_error(self):
        self.assertIn("unknown_mvp", codes(run(system(mvp=["없는 항목"]))["errors"]))

    def test_an_unknown_out_of_scope_item_is_an_error(self):
        self.assertIn("unknown_out_of_scope", codes(run(system("net", "out", mvp=[], pillars=[], out_of_scope=["멀티"]), system())["errors"]))

    def test_a_system_without_a_pillar_is_a_warning(self):
        self.assertEqual(warning(run(system(), system("x", "later", pillars=[], mvp=[])), "system_without_pillar")["where"], "x")

    def test_an_out_system_needs_no_pillar(self):
        self.assertNotIn("system_without_pillar", codes(run(system(), system("net", "out", pillars=[], mvp=[], out_of_scope=["멀티플레이"]))["warnings"]))

    def test_a_pillar_nobody_serves_is_a_warning(self):
        self.assertIn("숙성이 읽힌다", warning(run(system(pillars=["욕심이 곧 성장"])), "pillar_unserved")["message"])

    def test_a_later_system_does_not_serve_a_pillar_for_the_mvp(self):
        r = run(system(pillars=["욕심이 곧 성장"]), system("hud", "later", pillars=["숙성이 읽힌다"], mvp=[]))
        self.assertIn("숙성이 읽힌다", warning(r, "pillar_unserved")["message"])

    def test_an_mvp_item_nobody_serves_is_a_warning(self):
        self.assertIn("조준 무기", warning(run(system(mvp=["보석 숙성 3단계"])), "mvp_unserved")["message"])

    def test_a_cut_system_serves_nothing(self):
        self.assertIn("pillar_unserved", codes(run(system(status="cut"))["warnings"]))


class BrokenEntries(unittest.TestCase):
    """형식 오류로 빠진 시스템 하나가 거짓 오류를 줄줄이 내지 않는다."""

    def result(self):
        return run(system("base", scope="soon"), system("top", depends_on=["base"], pillars=["숙성이 읽힌다"], mvp=["조준 무기"]))

    def test_a_dependency_on_a_broken_system_is_not_unknown(self):
        self.assertNotIn("unknown_system", codes(self.result()["errors"]))

    def test_coverage_is_not_guessed(self):
        self.assertEqual([k for k in codes(self.result()["warnings"]) if k.endswith("_unserved")], [])

    def test_a_system_with_a_bad_status_counts_too(self):
        r = run(system("base", status="oops"), system("top", depends_on=["base"]))
        self.assertNotIn("unknown_system", codes(r["errors"]))

    def test_a_real_unknown_system_still_errors(self):
        self.assertIn("unknown_system", codes(run(system("base", scope="soon"), system("top", depends_on=["nope"]))["errors"]))


class Acknowledging(unittest.TestCase):
    def apply(self, *entries):
        data = {"systems": list(entries)}
        r = sy.validate(data, concepts=CONCEPTS)
        common.apply_acknowledged("systems", data, r)
        return r

    def test_an_unserved_pillar_can_be_acknowledged_on_any_system(self):
        r = self.apply(system("a", pillars=["욕심이 곧 성장"]), system("b", pillars=["욕심이 곧 성장"], acknowledged={"pillar_unserved": {"숙성이 읽힌다": "다음 마일스톤"}}))
        self.assertNotIn("pillar_unserved", codes(r["warnings"]))

    def test_an_unserved_mvp_item_can_be_acknowledged(self):
        r = self.apply(system(mvp=["보석 숙성 3단계"], acknowledged={"mvp_unserved": {"조준 무기": "다음 마일스톤"}}))
        self.assertNotIn("mvp_unserved", codes(r["warnings"]))

    def test_the_warning_is_owned_by_the_first_system_otherwise(self):
        self.assertEqual(warning(run(system("a", pillars=["욕심이 곧 성장"])), "pillar_unserved")["owner"], "a")

    def test_an_unused_acknowledgement_is_named(self):
        r = self.apply(system(acknowledged={"pillar_unservd": "오타"}))
        self.assertIn("쓰이지 않은 확인", "\n".join(r["ack_notes"]))


class Scope(unittest.TestCase):
    def test_an_mvp_system_outside_the_brief_is_a_warning(self):
        self.assertEqual(warning(run(system(), system("extra", mvp=[])), "scope_mismatch")["where"], "extra")

    def test_a_later_system_claiming_an_mvp_item_is_a_warning(self):
        self.assertIn("scope_mismatch", codes(run(system(), system("x", "later", mvp=["조준 무기"]))["warnings"]))

    def test_an_mvp_system_claiming_out_of_scope_is_a_warning(self):
        self.assertIn("scope_mismatch", codes(run(system(out_of_scope=["멀티플레이"]))["warnings"]))

    def test_an_out_system_has_to_name_its_item(self):
        self.assertIn("scope_mismatch", codes(run(system(), system("net", "out", pillars=[], mvp=[]))["warnings"]))

    def test_an_mvp_system_on_a_later_one_is_a_warning(self):
        r = run(system(depends_on=["hud"]), system("hud", "later", mvp=[]))
        self.assertIn("hud", warning(r, "scope_dependency")["message"])

    def test_a_later_system_on_an_out_one_is_a_warning(self):
        r = run(system(), system("hud", "later", mvp=[], depends_on=["net"]), system("net", "out", pillars=[], mvp=[], out_of_scope=["멀티플레이"]))
        self.assertEqual(warning(r, "scope_dependency")["where"], "hud")

    def test_a_system_on_one_of_its_own_scope_is_fine(self):
        self.assertNotIn("scope_dependency", codes(run(system("a"), system("b", depends_on=["a"]))["warnings"]))

    def test_a_later_system_on_an_mvp_one_is_fine(self):
        self.assertNotIn("scope_dependency", codes(run(system(), system("hud", "later", mvp=[], depends_on=["ripening"]))["warnings"]))


class Dependencies(unittest.TestCase):
    def test_an_unknown_system_is_an_error_with_a_hint(self):
        self.assertIn("ripening", next(e["message"] for e in run(system(), system("x", depends_on=["ripenin"]))["errors"] if e["code"] == "unknown_system"))

    def test_a_cut_system_is_reported_as_cut(self):
        r = run(system(depends_on=["old"]), system("old", status="cut"))
        self.assertIn("cut_referenced", codes(r["warnings"]))

    def test_a_system_cannot_depend_on_itself(self):
        self.assertIn("dependency_cycle", codes(run(system(depends_on=["ripening"]))["warnings"]))

    def test_a_cycle_is_a_warning_naming_its_members(self):
        text = warning(run(system("a", depends_on=["b"]), system("b", depends_on=["a"])), "dependency_cycle")["message"]
        self.assertIn("a", text)
        self.assertIn("b", text)

    def test_what_hangs_off_a_cycle_has_no_order_and_is_not_named_as_the_cycle(self):
        r = run(system("a", depends_on=["b"]), system("b", depends_on=["a"]), system("c", depends_on=["a"]))
        self.assertEqual(warning(r, "dependency_cycle")["part"], "a~b")
        self.assertIsNone(row(r, "c")["order"])

    def test_the_build_order_follows_the_dependencies(self):
        r = run(system("c", depends_on=["b"]), system("b", depends_on=["a"]), system("a"))
        self.assertEqual([(x["id"], x["order"]) for x in r["rows"]], [("a", 1), ("b", 2), ("c", 3)])

    def test_independent_systems_share_a_step(self):
        r = run(system("b"), system("a"))
        self.assertEqual([(x["id"], x["order"]) for x in r["rows"]], [("a", 1), ("b", 1)])

    def test_out_systems_are_not_built(self):
        self.assertIsNone(row(run(system(), system("net", "out", pillars=[], mvp=[], out_of_scope=["멀티플레이"])), "net")["order"])

    def test_a_dependency_on_an_out_system_does_not_block_the_order(self):
        r = run(system(), system("hud", "later", mvp=[], depends_on=["net"]), system("net", "out", pillars=[], mvp=[], out_of_scope=["멀티플레이"]))
        self.assertEqual(row(r, "hud")["order"], 1)

    def test_mvp_comes_before_later_within_a_step(self):
        r = run(system("a", "later", mvp=[]), system("b"))
        self.assertEqual([x["id"] for x in r["rows"]], ["b", "a"])


class Rules(unittest.TestCase):
    def test_a_built_system_without_rules_is_a_warning(self):
        self.assertEqual(warning(run(system(rules=[])), "system_without_rules")["where"], "ripening")

    def test_an_out_system_needs_no_rules(self):
        self.assertNotIn("system_without_rules", codes(run(system(), system("net", "out", pillars=[], mvp=[], out_of_scope=["멀티플레이"], rules=[]))["warnings"]))

    def test_design_decisions_do_not_hold_the_number_gate(self):
        self.assertEqual(run()["unverified"], [])


class Output(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "game"
        shutil.copytree(SAMPLE, self.root)

    def test_the_table_lays_out_the_order(self):
        text = sy.table({}, run(system("b", depends_on=["a"], name="보석 | 숙성"), system("a")))
        self.assertIn("| 순서 | 시스템 | 범위 | 필러 | MVP | 의존 | 규칙 |", text)
        self.assertIn("| 2 | 보석 \\| 숙성 (b) | MVP |", text)

    def test_the_report_prints_the_order(self):
        out = io.StringIO()
        with redirect_stdout(out):
            sy.print_extra(run(concepts=None))
        self.assertIn("컨셉", out.getvalue())

    def test_the_sample_passes(self):
        code, out = run_cli("check", self.root)
        self.assertEqual(code, 0, out)
        self.assertIn("시스템 설계", out)

    def test_the_project_reads_the_brief(self):
        p = self.root / "design/systems.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        d["systems"][0]["pillars"] = ["없는 필러"]
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        report = next(x for x in datasets.collect([self.root]) if x["kind"] == "systems")["report"]
        self.assertIn("unknown_pillar", codes(report["errors"]))

    def game_file(self, rel, text):
        (self.root / "design/systems.json").unlink()
        (self.root / rel).write_text(text, encoding="utf-8")
        return run_cli("check", self.root)

    def test_a_game_file_of_that_name_is_skipped_and_said_so(self):
        code, out = self.game_file("data/systems.json", '{"audio": 1}')
        self.assertEqual(code, 0, out)
        self.assertIn("시스템 설계 형식이 아니라 건너뛰었습니다", out)

    def test_an_engine_list_of_systems_is_a_game_file(self):
        for text in ('{"systems": ["physics", "audio"]}', '{"systems": {"physics": true}}', '{"systems": 5}', '{"systems": {}}'):
            code, out = self.game_file("data/systems.json", text) if (self.root / "design/systems.json").exists() else (None, None)
            if code is None:
                (self.root / "data/systems.json").write_text(text, encoding="utf-8")
                code, out = run_cli("check", self.root)
            self.assertEqual(code, 0, text)
            self.assertIn("건너뛰었습니다", out)

    def test_an_engine_key_in_another_file_is_ignored(self):
        code, out = self.game_file("data/engine.json", '{"systems": ["physics"]}')
        self.assertEqual(code, 0, out)

    def test_a_broken_file_of_that_name_is_a_read_failure(self):
        self.assertEqual(self.game_file("design/systems.json", '{ "systems": [')[0], 2)

    def test_an_empty_file_of_that_name_is_a_read_failure(self):
        self.assertEqual(self.game_file("design/systems.json", "{}")[0], 2)

    def test_the_levels_skip_note_is_unchanged(self):
        self.assertIn("레벨 구성 형식이 아니라", datasets.skipped_note("data/levels.json"))

    def test_the_lists_name_the_new_kind(self):
        tool = (ROOT / "skills/studio-data/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("`concepts`, `systems`, `items`", tool[tool.index("## 코드 구조"):])
        self.assertIn("시스템 설계 탭", tool)
        self.assertIn("시스템 설계", (ROOT / "README.md").read_text(encoding="utf-8").split("`view`는")[1][:120])
        self.assertIn("시스템 표", (STUDIO / "scripts/studio_data/cli.py").read_text(encoding="utf-8"))
        self.assertIn("concepts_unreadable:", (STUDIO / "assets/viewer.html").read_text(encoding="utf-8"))

    def test_it_is_registered_everywhere(self):
        self.assertIn("systems", common.DATASET_KINDS)
        page = (STUDIO / "assets/viewer.html").read_text(encoding="utf-8")
        self.assertRegex(page, r'const KIND_ORDER = \[[^\]]*"systems"')
        self.assertIn("renderSystems", page)
        for code in ("pillar_unserved", "mvp_unserved", "scope_mismatch", "scope_dependency", "dependency_cycle", "system_without_pillar", "system_without_rules", "unknown_pillar", "unknown_mvp", "unknown_out_of_scope", "unknown_system"):
            self.assertIn(f"{code}:", page)

    def test_the_skill_is_documented(self):
        skill = (ROOT / "skills/system-design/SKILL.md").read_text(encoding="utf-8")
        fmt = (ROOT / "skills/system-design/references/systems-format.md").read_text(encoding="utf-8")
        self.assertTrue(skill.startswith("---\nname: system-design\n"))
        self.assertTrue((ROOT / "skills/system-design/agents/openai.yaml").exists())
        for code in ("pillar_unserved", "mvp_unserved", "scope_mismatch", "scope_dependency", "dependency_cycle", "system_without_pillar", "system_without_rules"):
            self.assertIn(f"`{code}`", fmt)
        self.assertIn("system-design", (ROOT / "README.md").read_text(encoding="utf-8"))
        arch = (ROOT / "docs/architecture.md").read_text(encoding="utf-8")
        self.assertIn("| S1 | **시스템 설계.** 시스템의 규칙과 의존 관계를 브리프의 필러·범위에 연결 (`system-design`) | 1차 완료 |", arch)


if __name__ == "__main__":
    unittest.main()
