"""컨셉 기록 검사기 테스트. 표준 라이브러리 unittest만 사용한다."""
import copy
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from _studio import SAMPLE as SAMPLE_DIR, concepts as cc, run_cli as studio_cli

SAMPLE_PATH = SAMPLE_DIR / "design/concepts.json"
SAMPLE = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
APPROVED = next(c for c in SAMPLE["concepts"] if c["status"] == "approved")
AXES = ("decision", "information", "commitment", "risk_reward", "space", "pressure", "progression")


def concept(cid, status="proposed", **sig):
    signature = {"decision": "timing", "information": "full", "commitment": "reversible", "risk_reward": "none"}
    signature.update(sig)
    return {
        "id": cid, "name": cid, "pitch": "p", "core_verb": "v", "decision": "d", "state_read": "s",
        "skill_expression": "e", "risk": "r", "signature": signature, "status": status, "next_test": "t",
    }


def codes(entries):
    return [e["code"] for e in entries]


def run(*concepts):
    return cc.validate({"concepts": list(concepts)})


class Sample(unittest.TestCase):
    def test_sample_passes_without_warnings(self):
        r = cc.validate(copy.deepcopy(SAMPLE))
        self.assertEqual((r["errors"], r["warnings"]), ([], []))
        self.assertEqual(r["approved"], ["parry_tempo"])
        self.assertEqual(r["status_counts"]["cut"], 2)

    def test_reviving_the_cut_reskin_is_flagged_as_duplicate(self):
        data = copy.deepcopy(SAMPLE)
        next(c for c in data["concepts"] if c["id"] == "rhythm_shield")["status"] = "proposed"
        data_r = cc.validate(data)
        self.assertIn(("near_duplicate", "rhythm_shield"), [(w["code"], w["where"]) for w in data_r["warnings"]])

    def test_table_has_no_score_column_and_lists_every_concept(self):
        r = cc.validate(copy.deepcopy(SAMPLE))
        table = cc.table(SAMPLE, r)
        header = table.splitlines()[0]
        self.assertNotIn("점수", header)
        self.assertEqual(len(table.splitlines()), 2 + len(SAMPLE["concepts"]))
        self.assertTrue(table.splitlines()[2].startswith("| parry_tempo |"))


class Records(unittest.TestCase):
    def test_required_fields(self):
        c = concept("a")
        del c["skill_expression"]
        c["risk"] = "  "
        self.assertEqual(codes(run(c)["errors"]), ["missing_field", "missing_field"])

    def test_signature_rules(self):
        small = concept("a")
        small["signature"] = {"decision": "timing", "information": "full"}
        bad = concept("b")
        bad["signature"]["space"] = 3
        self.assertEqual(codes(run(small, bad)["errors"]), ["signature_missing_axis", "signature_too_small", "schema"])

    def test_bad_status_and_duplicate_id(self):
        r = run(concept("a", status="maybe"), concept("b"), concept("b"))
        self.assertEqual(sorted(codes(r["errors"])), ["duplicate_id", "schema"])

    def test_stress_results_need_evidence_unless_unknown(self):
        c = concept("a")
        c["stress"] = [{"policy": "idle", "result": "unknown"}, {"policy": "spam", "result": "loses"},
                       {"policy": "kite", "result": "bad"}]
        self.assertEqual(sorted(codes(run(c)["errors"])), ["evidence_missing", "schema"])

    def test_hard_reject_needs_type_reason_and_evidence(self):
        c = concept("a", status="cut")
        c["hard_reject"] = {"type": "boring", "reason": "낯설다", "evidence": "느낌"}
        self.assertEqual(codes(run(c)["errors"]), ["reject_unsupported"])
        c["hard_reject"] = {"type": "no_recurring_decision", "reason": "결정 없음"}
        self.assertEqual(codes(run(c)["errors"]), ["reject_unsupported"])
        c["hard_reject"]["evidence"] = "규칙상 선택지가 하나"
        self.assertEqual(run(c)["errors"], [])

    def test_rejected_concept_should_be_cut(self):
        c = concept("a")
        c["hard_reject"] = {"type": "forced_failure", "reason": "x", "evidence": "y"}
        self.assertIn("rejected_but_active", codes(run(c)["warnings"]))

    def test_origin_must_exist(self):
        child = concept("child")
        child["origin"] = "ghost"
        self.assertEqual(codes(run(child)["errors"]), ["unknown_origin"])
        child["origin"] = "parent"
        self.assertEqual(run(concept("parent", decision="route", information="hidden"), child)["errors"], [])
        child["origin"] = "root"
        self.assertEqual(run(child)["errors"], [])

    def test_cost_shape(self):
        c = concept("a")
        c["cost"] = {"level": "huge", "reason": "x"}
        self.assertEqual(codes(run(c)["errors"]), ["schema"])


class Brief(unittest.TestCase):
    def approved(self, **changes):
        c = copy.deepcopy(APPROVED)
        for k, v in changes.items():
            if v is None:
                del c["brief"][k]
            else:
                c["brief"][k] = v
        return c

    def test_complete_brief_passes(self):
        self.assertEqual(run(self.approved())["errors"], [])

    def test_approved_without_brief(self):
        c = copy.deepcopy(APPROVED)
        del c["brief"]
        self.assertEqual(codes(run(c)["errors"]), ["brief_missing"])

    def test_proposed_concept_does_not_need_brief(self):
        c = copy.deepcopy(APPROVED)
        c["status"] = "proposed"
        del c["brief"]
        self.assertEqual(run(c)["errors"], [])

    def test_incomplete_parts(self):
        cases = {
            "pillar without test": {"pillars": [{"name": "a", "test": "x"}, {"name": "b"}]},
            "one pillar": {"pillars": [{"name": "a", "test": "x"}]},
            "no anti pillars": {"anti_pillars": []},
            "loop without meta": {"loop": {"moment": "a", "run": "b"}},
            "hypothesis without failure signal": {"hypotheses": [{"claim": "a", "test": "c"}]},
            "zero day prototype": {"prototype": {"kind": "graybox", "scope": "a", "duration_days": 0, "success_criteria": "b"}},
            "eight mvp items": {"mvp": [str(i) for i in range(8)]},
            "no out of scope": {"out_of_scope": []},
            "no experience": {"experience": None},
        }
        for label, change in cases.items():
            with self.subTest(label):
                r = run(self.approved(**change))
                self.assertEqual(codes(r["errors"]), ["brief_incomplete"], label)

    def test_seven_mvp_items_is_the_limit(self):
        self.assertEqual(run(self.approved(mvp=[str(i) for i in range(7)]))["errors"], [])


class Structure(unittest.TestCase):
    def test_near_duplicate_threshold(self):
        full = dict(space="rooms", pressure="enemies", progression="both")
        a = concept("a", **full)
        six_same = concept("b", **dict(full, progression="meta"))
        five_same = concept("c", **dict(full, progression="meta", space="arena"))
        self.assertEqual([(w["code"], w["where"]) for w in run(a, six_same)["warnings"]], [("near_duplicate", "b")])
        self.assertEqual(run(a, five_same)["warnings"], [])

    def test_comparison_ignores_case_and_spacing(self):
        a = concept("a")
        b = concept("b", decision=" Timing ")
        self.assertEqual(codes(run(a, b)["warnings"]), ["near_duplicate"])

    def test_cut_concepts_are_not_compared(self):
        self.assertEqual(run(concept("a"), concept("b", status="cut"))["warnings"], [])

    def test_too_few_shared_axes_are_not_compared(self):
        a = {"decision": "timing", "information": "full", "commitment": "reversible", "risk_reward": "none"}
        b = {"decision": "timing", "information": "full", "commitment": "reversible", "space": "rooms"}
        ca, cb = concept("a"), concept("b")
        ca["signature"], cb["signature"] = a, b
        self.assertEqual(run(ca, cb)["warnings"], [])

    def test_axis_collapse_needs_three_active_concepts(self):
        trio = [concept("a", decision="timing", information="full", commitment="reversible", risk_reward="none"),
                concept("b", decision="route", information="hidden", commitment="permanent", risk_reward="none"),
                concept("c", decision="build", information="partial", commitment="costly", risk_reward="none")]
        r = run(*trio)
        self.assertEqual([(w["code"], w["where"]) for w in r["warnings"]], [("axis_collapse", "risk_reward")])
        self.assertEqual(run(*trio[:2])["warnings"], [])
        trio[2]["status"] = "cut"
        self.assertEqual(run(*trio)["warnings"], [])

    def test_axis_written_by_only_two_of_three_is_not_collapse(self):
        trio = [concept("a", decision="timing", information="full", commitment="reversible", risk_reward="none", space="rooms"),
                concept("b", decision="route", information="hidden", commitment="permanent", risk_reward="greed", space="rooms"),
                concept("c", decision="build", information="partial", commitment="costly", risk_reward="wager")]
        self.assertEqual(run(*trio)["warnings"], [])

    def test_dominant_policy_and_next_test_warnings_skip_cut(self):
        c = concept("a")
        c["stress"] = [{"policy": "corner", "result": "dominates", "evidence": "구석이 안전"}]
        del c["next_test"]
        self.assertEqual(sorted(codes(run(c)["warnings"])), ["dominant_policy", "next_test_missing"])
        c["status"] = "cut"
        self.assertEqual(run(c)["warnings"], [])


class CommandLine(unittest.TestCase):
    def run_cli(self, *args):
        return studio_cli("check", *args)

    def test_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "concepts.json"
            path.write_text(json.dumps({"concepts": [concept("a"), concept("b")]}), encoding="utf-8")
            self.assertEqual(self.run_cli(str(path))[0], 0)
            self.assertEqual(self.run_cli(str(path), "--strict")[0], 1)
            path.write_text(json.dumps({"concepts": [{"id": "a"}]}), encoding="utf-8")
            self.assertEqual(self.run_cli(str(path))[0], 1)
            path.write_text(json.dumps({"notes": "기획 메모"}), encoding="utf-8")
            self.assertEqual(self.run_cli(str(path))[0], 2)
            self.assertEqual(self.run_cli(str(Path(tmp) / "missing.json"))[0], 2)

    def test_table_and_json_output(self):
        code, out = self.run_cli(str(SAMPLE_PATH), "--table")
        self.assertEqual(code, 0)
        self.assertIn("| parry_tempo | 패링 템포 | 선택 |", out)
        code, out = self.run_cli(str(SAMPLE_PATH), "--json")
        data = json.loads(out)
        self.assertEqual((code, data["status"], data["datasets"][0]["report"]["count"]), (0, "pass", 8))


if __name__ == "__main__":
    unittest.main()
