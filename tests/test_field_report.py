"""게임 프로젝트에 설치해 써 본 시험 보고에서 나온 문제의 회귀 테스트.

각 테스트 이름 끝의 번호는 시험 보고의 문제 번호다. 표준 라이브러리 unittest만 사용한다.
"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from _studio import ROOT, SAMPLE, concepts as cc, enemies as ve, items as vi, meta_sim, provenance as cp
from _studio import run_cli, upgrades as vu

FULL_SIG = {"decision": "timing", "information": "full", "commitment": "reversible", "risk_reward": "none"}


def concept(cid, status="proposed", **sig):
    signature = dict(FULL_SIG)
    signature.update(sig)
    return {"id": cid, "name": cid, "pitch": "p", "core_verb": "v", "decision": "d", "state_read": "s",
            "skill_expression": "e", "risk": "r", "signature": signature, "status": status, "next_test": "t"}


def codes(entries):
    return [e["code"] for e in entries]


def approved_with(**brief_overrides):
    sample = json.loads((SAMPLE / "design/concepts.json").read_text(encoding="utf-8"))
    c = next(x for x in sample["concepts"] if x["status"] == "approved")
    c = json.loads(json.dumps(c))
    for k, v in brief_overrides.items():
        c["brief"][k] = v
    return c


class Workspace(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rel, content):
        path = self.dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content if isinstance(content, str) else json.dumps(content, ensure_ascii=False), encoding="utf-8")
        return path


# ---------- 1, 2, 21: 설치 환경에서 그대로 실패하는 명령 ----------
class InstalledCommands(unittest.TestCase):
    def test_skill_docs_do_not_use_repository_relative_python_command_1_2_21(self):
        offenders = []
        for path in list((ROOT / "skills").rglob("*.md")) + [ROOT / "skills/studio-data/assets/viewer.html"]:
            for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if "python skills/" in line or "python .claude/" in line:
                    offenders.append(f"{path.relative_to(ROOT)}:{no}")
        self.assertEqual(offenders, [], "스킬 문서는 python3와 설치 위치(.claude/skills/…) 기준으로 적는다")

    def test_every_skill_points_to_the_install_path_note_1_2(self):
        for name in ("concept-exploration", "numeric-provenance", "progression-economy"):
            text = (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn(".agents/skills/", text, name)
            self.assertIn("../studio-data/SKILL.md#실행", text, name)


# ---------- 10, 15, 19, 9: 검사하지 않았는데 통과처럼 보이는 결과 ----------
class NoSilentPass(Workspace):
    def test_provenance_without_markdown_is_not_a_pass_10(self):
        self.write("design/concepts.json", {"concepts": []})
        code, out = run_cli("provenance", self.dir / "design")
        self.assertEqual(code, 2)
        self.assertNotIn("PASS", out)
        code, out = run_cli("provenance", self.dir / "design", "--json")
        self.assertEqual((code, json.loads(out)["status"]), (2, "no_files"))

    def test_unchecked_drop_tables_make_the_verdict_incomplete_15(self):
        shutil.copy(SAMPLE / "data/enemies.json", self.write("data/enemies.json", "{}"))
        code, out = run_cli("check", self.dir / "data")
        self.assertEqual(code, 0)
        self.assertIn("→ INCOMPLETE", out)
        self.assertNotIn("→ PASS", out)
        self.assertIn("통과로 보고하지 않습니다", out)
        self.assertEqual(run_cli("check", self.dir / "data", "--strict")[0], 1)
        code, out = run_cli("check", self.dir / "data", "--json")
        self.assertEqual(json.loads(out)["status"], "incomplete")

    def test_with_items_the_same_enemies_pass_15(self):
        shutil.copytree(SAMPLE / "data", self.dir / "data")
        code, out = run_cli("check", self.dir / "data/enemies.json", self.dir / "data/items.json")
        self.assertEqual(code, 0)
        self.assertIn("→ PASS", out)

    def test_broken_items_file_is_named_as_the_reason_19(self):
        shutil.copy(SAMPLE / "data/enemies.json", self.write("data/enemies.json", "{}"))
        self.write("data/items.json", "{ broken")
        code, out = run_cli("check", self.dir / "data")
        self.assertEqual(code, 2)
        self.assertIn("아이템 파일을 읽지 못함", out)
        self.assertNotIn("같이 넘기세요", out)
        self.assertNotIn("unknown_drop_table", out)

    def test_enemy_validator_does_not_error_on_tables_that_may_be_in_the_broken_file_19(self):
        data = {"enemies": [{"id": "a", "rank": "normal", "zone": 1, "stats": {}, "drop_table": "elsewhere"}]}
        r = ve.validate(data, {"chest": {}}, items_unreadable=True)
        self.assertEqual((r["errors"], r["drop_table_not_checked"], r["drop_table_unchecked_reason"]), ([], ["a"], "items_unreadable"))
        r = ve.validate(data, {"chest": {}})
        self.assertEqual(codes(r["errors"]), ["unknown_drop_table"])

    def test_concepts_file_without_concepts_key_is_reported_not_skipped_9(self):
        self.write("design/concepts.json", {"constraints": {"platform": "PC"}})
        code, out = run_cli("check", self.dir)
        self.assertEqual(code, 2)
        self.assertNotIn("찾지 못했습니다", out)
        self.assertIn('"concepts": []', out)

    def test_unrelated_json_is_still_skipped_9(self):
        self.write("design/notes.json", {"todo": []})
        self.write("design/concepts.json", {"concepts": []})
        code, out = run_cli("check", self.dir)
        self.assertEqual(code, 0)
        self.assertNotIn("notes.json", out)


# ---------- 3, 4, 5, 6, 7: 컨셉 검사기 ----------
class ConceptAxes(unittest.TestCase):
    def test_typo_axes_are_caught_instead_of_passing_3(self):
        c = concept("a")
        c["signature"] = {"decison": "timing", "informaton": "full", "comitment": "reversible", "risk": "none"}
        r = cc.validate({"concepts": [c]})
        self.assertIn("signature_missing_axis", codes(r["errors"]))
        unknown = [w for w in r["warnings"] if w["code"] == "unknown_axis"]
        self.assertEqual(len(unknown), 4)
        self.assertIn("'decision'의 오타", unknown[0]["message"])

    def test_known_optional_axes_and_declared_extra_axes_are_fine_3(self):
        c = concept("a", space="arena", tempo="fast")
        r = cc.validate({"concepts": [c]})
        self.assertEqual(codes(r["warnings"]), ["unknown_axis"])
        r = cc.validate({"constraints": {"extra_axes": ["tempo"]}, "concepts": [c]})
        self.assertEqual((r["errors"], r["warnings"]), ([], []))

    def test_unknown_policy_needs_a_definition_4(self):
        c = concept("a")
        c["stress"] = [{"policy": "saf_only", "result": "unknown"}]
        w = cc.validate({"concepts": [c]})["warnings"]
        self.assertEqual(codes(w), ["unknown_policy"])
        self.assertIn("safe_only", w[0]["message"])
        c["stress"] = [{"policy": "spin", "definition": "빛을 계속 돌린다", "result": "unknown"},
                       {"policy": "kite", "result": "unknown"}]
        self.assertEqual(cc.validate({"concepts": [c]})["warnings"], [])

    def test_fixed_axis_is_not_reported_as_collapse_5(self):
        cs = [concept("a", decision="timing", progression="both"), concept("b", decision="route", progression="both"),
              concept("c", decision="build", progression="both")]
        for c in cs:
            c["signature"]["information"] = {"a": "full", "b": "partial", "c": "hidden"}[c["id"]]
            c["signature"]["commitment"] = {"a": "reversible", "b": "costly", "c": "permanent"}[c["id"]]
            c["signature"]["risk_reward"] = {"a": "none", "b": "greed", "c": "wager"}[c["id"]]
        r = cc.validate({"concepts": cs})
        self.assertEqual([(w["code"], w["where"]) for w in r["warnings"]], [("axis_collapse", "progression")])
        r = cc.validate({"constraints": {"fixed_axes": {"progression": "both"}}, "concepts": cs})
        self.assertEqual(r["warnings"], [])
        self.assertEqual(r["fixed_axes"], {"progression": "both"})

    def test_fixed_axis_is_left_out_of_duplicate_comparison_5(self):
        a = concept("a", progression="both")
        b = concept("b", progression="both", risk_reward="greed")
        self.assertEqual(codes(cc.validate({"concepts": [a, b]})["warnings"]), ["near_duplicate"])  # 4/5 같음
        r = cc.validate({"constraints": {"fixed_axes": {"progression": "both"}}, "concepts": [a, b]})
        self.assertEqual(r["warnings"], [])  # 고정 축을 빼면 3/4

    def test_fixed_axis_mismatch_and_shape_5(self):
        r = cc.validate({"constraints": {"fixed_axes": {"progression": "both"}}, "concepts": [concept("a", progression="meta")]})
        self.assertEqual(codes(r["warnings"]), ["fixed_axis_mismatch"])
        r = cc.validate({"constraints": {"fixed_axes": ["progression"]}, "concepts": []})
        self.assertEqual([(e["code"], e["where"]) for e in r["errors"]], [("schema", "constraints")])

    def test_fixed_axis_counts_as_required_but_not_as_comparable_5(self):
        c = concept("a", space="arena")
        del c["signature"]["risk_reward"]
        r = cc.validate({"constraints": {"fixed_axes": {"risk_reward": "none"}}, "concepts": [c]})
        self.assertEqual(r["errors"], [])
        del c["signature"]["space"]
        r = cc.validate({"constraints": {"fixed_axes": {"risk_reward": "none"}}, "concepts": [c]})
        self.assertEqual(codes(r["errors"]), ["signature_too_small"])

    def test_variant_and_origin_get_a_replacement_hint_6(self):
        a = concept("orig", space="arena", pressure="enemies")
        b = concept("variant", space="arena", pressure="enemies", information="partial")
        b["origin"] = "orig"
        w = cc.validate({"concepts": [b, a]})["warnings"]
        self.assertEqual([(x["code"], x["where"]) for x in w], [("near_duplicate", "variant")])
        self.assertIn("원본을 cut", w[0]["message"])
        a["status"] = "cut"
        self.assertEqual(cc.validate({"concepts": [a, b]})["warnings"], [])

    def test_table_can_show_only_the_shortlist_7(self):
        data = {"concepts": [concept("a", decision="timing"), concept("b", decision="route"), concept("c", decision="build")]}
        r = cc.validate(data)
        rows = cc.table(data, r, ["c", "a", "zzz"]).splitlines()
        self.assertEqual([row.split("|")[1].strip() for row in rows[2:4]], ["c", "a"])
        self.assertIn("zzz", rows[-1])
        self.assertNotIn("| b |", "\n".join(rows))

    def test_ids_option_on_the_command_line_7(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "concepts.json"
        path.write_text(json.dumps({"concepts": [concept("a", decision="timing"), concept("b", decision="route")]}), encoding="utf-8")
        _, out = run_cli("check", path, "--table", "--ids", "b")
        self.assertIn("| b |", out)
        self.assertNotIn("| a |", out)


# ---------- 11, 12, 13: 수치 출처 ----------
class BriefNumbers(unittest.TestCase):
    def test_untagged_threshold_in_failure_signal_is_warned_11(self):
        c = approved_with(hypotheses=[{"id": "h1", "claim": "c", "failure_signal": "80% 이상이 같은 선택을 한다", "test": "3명 [가정]에게 5판 [가정]", "sample": {"players": 3, "runs": 15}}])
        r = cc.validate({"concepts": [c]})
        self.assertEqual(codes(r["warnings"]), ["untagged_number"])
        self.assertIn("80%", r["warnings"][0]["message"])
        self.assertEqual(r["unverified"][0], "parry_tempo.brief.hypotheses[0].failure_signal(태그 없음: 80%)")   # 출처가 빈 값이라 게이트도 막는다(312번)

    def test_tagged_thresholds_are_counted_for_the_gate_11(self):
        c = approved_with()
        r = cc.validate({"concepts": [c]})
        self.assertEqual(r["warnings"], [])
        self.assertEqual(len(r["unverified"]), 5)   # 가설 둘의 신호, 첫 가설의 주장·확인 방법(312번), 성공 기준

    def test_numbers_outside_criteria_are_not_warned_but_bad_tags_are_errors_11(self):
        c = approved_with(mvp=["보스 1명", "적 3종"])
        self.assertEqual(cc.validate({"concepts": [c]})["warnings"], [])
        c = approved_with(mvp=["보스 1명 [계산]"])
        self.assertEqual(codes(cc.validate({"concepts": [c]})["errors"]), ["provenance"])


class MarkdownNumbers(unittest.TestCase):
    def findings(self, text):
        return [(f.level, f.message) for f in cp.check_text(text).findings]

    def test_body_number_without_tag_is_a_warning_12(self):
        f = self.findings("보석 경험치 배율은 5배, 부화는 6초로 한다.\n")
        self.assertEqual([lv for lv, _ in f], ["warning"])
        self.assertIn("5배", f[0][1])
        self.assertIn("6초", f[0][1])

    def test_tagged_lines_headings_and_code_are_not_warned_12(self):
        text = "부화는 6초 [가정]로 한다.\n## 1분 구간\n`3초`\n```\n6초\n```\n그냥 문장이다.\n"
        self.assertEqual(self.findings(text), [])

    def test_header_variant_is_reported_instead_of_silently_skipped_12(self):
        text = "| 항목 | 값 | 출처 (근거) |\n|---|---|---|\n| 부화 | 6 | |\n"
        f = self.findings(text)
        self.assertEqual([lv for lv, _ in f], ["warning"])
        self.assertIn("출처 (근거)", f[0][1])
        self.assertEqual(self.findings("| 자원 | 값 |\n|---|---|\n| 금 | 1 |\n"), [])

    def test_tag_name_typo_is_named_13(self):
        text = "| 항목 | 값 | 출처 |\n|---|---|---|\n| 부화 | 6 | [게산: x.py] |\n"
        f = self.findings(text)
        self.assertEqual([lv for lv, _ in f], ["error"])
        self.assertIn("'계산'의 오타", f[0][1])
        self.assertIn("'computed'의 오타", self.findings("값 3 [computd: a.py]\n")[0][1])
        self.assertEqual(self.findings("[참고: 위 표] 문장이다.\n"), [])

    def test_measured_example_points_to_a_playtest_13(self):
        msg = self.findings("값 [측정:  ]\n")[0][1]
        self.assertIn("playtest", msg)
        self.assertNotIn("sim/", msg)


# ---------- 14, 16: 데이터 검사기 ----------
class DataWarnings(unittest.TestCase):
    def items(self):
        return {"items": [
            {"id": "sword", "slot": "weapon", "tier": 1, "stats": {"attack": 10}},
            {"id": "scythe", "slot": "weapon", "tier": 2, "stats": {"attack": 3}, "unique_effect": True, "intent": "흡혈 빌드"},
            {"id": "axe", "slot": "weapon", "tier": 2, "stats": {"attack": 30}},
        ]}

    def test_unique_effect_items_are_not_tier_compared_14(self):
        r = vi.validate(self.items())
        self.assertEqual(r["warnings"], [])
        self.assertEqual(r["dominance_not_assessed"], ["scythe"])
        data = self.items()
        del data["items"][1]["unique_effect"]
        self.assertIn("tier_inversion", codes(vi.validate(data)["warnings"]))

    def test_acknowledged_warning_moves_out_of_the_warning_count_14(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        data = self.items()
        del data["items"][1]["unique_effect"]
        path = Path(tmp.name) / "items.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(run_cli("check", path, "--strict")[0], 1)
        data["items"][1]["acknowledged"] = {"tier_inversion": "흡혈 효과로 보상하는 의도"}
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        code, out = run_cli("check", path, "--strict")
        self.assertEqual(code, 1)  # dominated는 확인하지 않았으므로 남는다
        self.assertIn("warning [dominated] scythe", out)
        data["items"][1]["acknowledged"]["dominated"] = "시작 아이템보다 약한 것이 의도"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        code, out = run_cli("check", path, "--strict")
        self.assertEqual(code, 0)
        self.assertIn("확인한 경고 [tier_inversion] scythe: 흡혈 효과로 보상하는 의도", out)
        self.assertIn("경고 0 · 확인한 경고 2", out)

    def test_acknowledged_needs_reasons_and_cannot_hide_errors_14(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "items.json"
        data = self.items()
        data["items"][0]["acknowledged"] = {"tier_inversion": ""}
        data["items"][2]["tier"] = 0
        data["items"][2]["acknowledged"] = {"schema": "무시"}
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        code, out = run_cli("check", path, "--json")
        report = json.loads(out)["datasets"][0]["report"]
        self.assertEqual(code, 1)
        self.assertEqual(sorted((e["code"], e["where"]) for e in report["errors"]),
                         [("schema", "axe"), ("schema", "sword")])
        self.assertEqual(report["acknowledged"], [])

    def test_requirement_with_schema_error_is_not_called_missing_16(self):
        r = vu.validate({"upgrades": [{"id": "ripen_1", "cost": -5, "power": 1},
                                      {"id": "ripen_2", "cost": 10, "power": 1, "requires": ["ripen_1"]}]})
        self.assertEqual(codes(r["errors"]), ["schema"])
        self.assertEqual(codes(r["warnings"]), ["requirement_unchecked"])
        r = vu.validate({"upgrades": [{"id": "ripen_2", "cost": 10, "power": 1, "requires": ["ripen_1"]}]})
        self.assertEqual(codes(r["errors"]), ["unknown_requirement"])

    def test_drop_entry_with_schema_error_item_is_not_called_missing_16(self):
        data = {"items": [{"id": "gem", "slot": "relic", "tier": 0, "stats": {}}],
                "drop_tables": {"chest": {"entries": [{"item": "gem", "weight": 1}]}}}
        r = vi.validate(data)
        self.assertEqual(codes(r["errors"]), ["schema"])
        self.assertEqual(codes(r["warnings"]), ["item_unchecked"])


# ---------- 17: 구매 정책 비교 ----------
class PolicyComparison(Workspace):
    def setUp(self):
        super().setUp()
        shutil.copytree(SAMPLE / "data", self.dir / "data")
        meta = json.loads((self.dir / "data/meta.json").read_text(encoding="utf-8"))
        meta["trials"] = 40
        meta["max_runs"] = 30
        self.config = self.write("data/meta.json", meta)

    def test_policy_override_does_not_touch_the_file_17(self):
        before = self.config.read_bytes()
        code, out = run_cli("simulate", self.config, "--policy", "cheapest_first", "--json")
        result = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual((result["purchase_policy"], result["policy_override"]), ("cheapest_first", "cheapest_first"))
        self.assertEqual(self.config.read_bytes(), before)
        cfg, plain = meta_sim.run_config(self.config)
        self.assertEqual(plain["config_sha256"], result["config_sha256"])
        self.assertNotIn("policy_override", plain)

    def test_compare_policies_runs_each_policy_17(self):
        out_path = self.dir / "reports/policies.json"
        code, out = run_cli("simulate", self.config, "--compare-policies", "--out", out_path, "--csv", self.dir / "reports/c.csv")
        self.assertEqual(code, 0)
        for policy in meta_sim.POLICIES:
            self.assertIn(policy, out)
        saved = json.loads(out_path.read_text(encoding="utf-8"))
        self.assertEqual(sorted(saved["results"]), sorted(meta_sim.POLICIES))
        self.assertEqual({r["purchase_policy"] for r in saved["results"].values()}, set(meta_sim.POLICIES))
        header = (self.dir / "reports/c.csv").read_text(encoding="utf-8").splitlines()[0]
        self.assertTrue(header.startswith("policy,run"))

    def test_policy_options_are_exclusive_17(self):
        with self.assertRaises(SystemExit):
            run_cli("simulate", self.config, "--policy", "listed_order", "--compare-policies")


# ---------- 22: 뷰어 표시 ----------
class ViewerLabels(unittest.TestCase):
    def test_new_codes_and_passive_slot_have_labels_22(self):
        html = (ROOT / "skills/studio-data/assets/viewer.html").read_text(encoding="utf-8")
        for code in ("signature_missing_axis", "unknown_axis", "fixed_axis_mismatch", "unknown_policy",
                     "untagged_number", "item_unchecked", "requirement_unchecked"):
            self.assertIn(f"{code}:", html)
        self.assertIn('passive: "패시브"', html)
        self.assertIn("Noto Sans CJK KR", html)


if __name__ == "__main__":
    unittest.main()
