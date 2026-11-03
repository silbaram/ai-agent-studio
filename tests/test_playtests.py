"""플레이 기록·가설 판정 검사기(playtests) 테스트. 표준 라이브러리 unittest만 사용한다."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from _studio import datasets, SAMPLE, concepts as cc, playtests as pt, provenance as cp, run_cli


def sample(rel):
    return json.loads((SAMPLE / rel).read_text(encoding="utf-8"))


def ctx():
    return cc.hypothesis_index(sample("design/concepts.json"))


def codes(entries):
    return [e["code"] for e in entries]


def session(sid="pt_a", **over):
    s = {"id": sid, "date": "2026-11-05", "concept": "parry_tempo", "build": "abc1234", "players": ["self"], "runs": 5,
         "observations": [{"hypothesis": "learn_timing", "value": "같은 패턴 피격률 5판 동안 40% → 15%", "n": 5}]}
    s.update(over)
    return s


def verdict(**over):
    v = {"concept": "parry_tempo", "hypothesis": "learn_timing", "result": "holds", "sessions": ["pt_a"],
         "reason": "피격률이 줄었다", "status": "approved"}
    v.update(over)
    return v


def validate(sessions, verdicts, concepts=None):
    return pt.validate({"playtests": sessions, "verdicts": verdicts}, ctx() if concepts is None else concepts)


class Sample(unittest.TestCase):
    def test_sample_playtests_have_no_errors_or_warnings(self):
        r = pt.validate(sample("data/playtests.json"), ctx())
        self.assertEqual((r["errors"], r["warnings"]), ([], []))
        self.assertEqual(r["unchecked"], len(r["unchecked_refs"]))    # 컨셉 참조는 확인했다. 단계 기록의 참조는 프로젝트 검사에서 본다
        full = next(d["report"] for d in datasets.collect([SAMPLE]) if d["kind"] == "playtests")
        self.assertEqual((full["errors"], full["warnings"], full["unchecked"]), ([], [], 0))

    def test_sample_gate_lists_hypotheses_without_a_confirmed_verdict(self):
        r = pt.validate(sample("data/playtests.json"), ctx())
        self.assertEqual(r["unverified"], ["parry_tempo.tempo_choice"])


class Evidence(unittest.TestCase):
    def test_holds_or_refuted_without_sessions_is_an_error(self):
        for result in ("holds", "refuted"):
            with self.subTest(result):
                r = validate([session()], [verdict(result=result, sessions=[])])
                self.assertEqual(codes(r["errors"]), ["verdict_without_evidence"])

    def test_unknown_needs_no_sessions_but_needs_a_reason(self):
        r = validate([], [verdict(result="unknown", sessions=[], reason="표본 부족: 1명 1판")])
        self.assertEqual(r["errors"], [])
        r = validate([], [verdict(result="unknown", sessions=[], reason=" ")])
        self.assertEqual(codes(r["errors"]), ["schema"])

    def test_cited_session_must_exist(self):
        r = validate([session()], [verdict(sessions=["pt_nope"])])
        self.assertEqual(codes(r["errors"]), ["unknown_session"])

    def test_cited_session_must_observe_that_hypothesis(self):
        s = session(observations=[{"hypothesis": "tempo_choice", "value": "회피 55%"}])
        r = validate([s], [verdict()])
        self.assertEqual(codes(r["errors"]), ["observation_missing"])

    def test_cited_session_must_be_for_the_same_concept(self):
        s = session(concept="greed_rooms", observations=[])
        r = validate([s], [verdict()])
        self.assertIn("session_concept_mismatch", codes(r["errors"]))

    def test_session_without_observations_is_a_warning(self):
        r = validate([session(observations=[])], [])
        self.assertEqual(codes(r["warnings"]), ["session_without_observations"])

    def test_sample_size_is_reported_not_judged(self):
        r = validate([session(players=["self", "friend_a"], runs=3), session("pt_b", players=["self"], runs=2)],
                     [verdict(sessions=["pt_a", "pt_b"])])
        self.assertEqual(r["verdicts"]["parry_tempo.learn_timing"]["sample"], {"sessions": 2, "runs": 5, "players": 2})


class References(unittest.TestCase):
    def test_unknown_concept_and_hypothesis_are_errors(self):
        r = validate([session(concept="nope", observations=[])], [])
        self.assertEqual(codes(r["errors"]), ["unknown_concept"])
        r = validate([session(observations=[{"hypothesis": "timing", "value": 1}])], [])
        self.assertEqual(codes(r["errors"]), ["unknown_hypothesis"])
        self.assertIn("learn_timing", r["errors"][0]["message"])

    def test_brief_hypotheses_without_ids_are_named_as_the_cause(self):
        data = sample("design/concepts.json")
        for c in data["concepts"]:
            for h in (c.get("brief") or {}).get("hypotheses", []):
                h.pop("id", None)
        r = validate([session()], [], cc.hypothesis_index(data))
        self.assertEqual(codes(r["errors"]), ["unknown_hypothesis"])
        self.assertIn("brief.hypotheses", r["errors"][0]["message"])

    def test_without_concepts_references_are_unchecked_not_passed(self):
        r = pt.validate({"playtests": [session()], "verdicts": [verdict()]}, None)
        self.assertEqual(r["errors"], [])
        self.assertGreater(r["unchecked"], 0)
        self.assertEqual(pt.validate({"playtests": [session()], "verdicts": []}, None)["unchecked"], 1)
        self.assertEqual(pt.validate({"playtests": [], "verdicts": [verdict(result="unknown", sessions=[])]}, None)["unchecked"], 1)

    def test_two_active_verdicts_for_one_hypothesis_is_an_error_but_cut_history_is_kept(self):
        r = validate([session()], [verdict(), verdict(result="unknown", sessions=[], reason="r")])
        self.assertEqual(codes(r["errors"]), ["duplicate_verdict"])
        r = validate([session()], [verdict(status="cut", result="unknown", sessions=[], reason="첫 판정"), verdict()])
        self.assertEqual(r["errors"], [])


class Gate(unittest.TestCase):
    def test_only_confirmed_holds_or_refuted_counts_as_decided(self):
        both = [verdict(), verdict(hypothesis="tempo_choice", result="refuted", status="approved")]
        s = session(observations=[{"hypothesis": "learn_timing", "value": "a"}, {"hypothesis": "tempo_choice", "value": "b"}])
        self.assertEqual(validate([s], both)["unverified"], [])
        proposed = [verdict(status="proposed"), both[1]]
        self.assertEqual(validate([s], proposed)["unverified"], ["parry_tempo.learn_timing"])
        unknown = [verdict(result="unknown"), both[1]]
        self.assertEqual(validate([s], unknown)["unverified"], ["parry_tempo.learn_timing"])

    def test_schema_errors(self):
        bad = [session(date="11/05"), session("pt_b", runs=0), session("pt_c", players=[]), session("pt_d", build=""),
               session("pt_e", notes=[{"kind": "feeling", "text": "좋다"}])]
        r = validate(bad, [])
        self.assertEqual(codes(r["errors"]), ["schema"] * 5)
        r = validate([session()], [verdict(result="maybe")])
        self.assertEqual(codes(r["errors"]), ["schema"])


class BriefHypothesisIds(unittest.TestCase):
    def test_hypothesis_ids_must_be_valid_and_unique(self):
        data = sample("design/concepts.json")
        c = next(x for x in data["concepts"] if x["status"] == "approved")
        c["brief"]["hypotheses"][1]["id"] = c["brief"]["hypotheses"][0]["id"]
        self.assertIn("schema", codes(cc.validate(data)["errors"]))
        c["brief"]["hypotheses"][1]["id"] = "Bad-Id"
        self.assertIn("schema", codes(cc.validate(data)["errors"]))


class CommandLine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "game"
        shutil.copytree(SAMPLE, self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_playtests_alone_is_incomplete_not_pass(self):
        code, out = run_cli("check", self.root / "data/playtests.json")
        self.assertEqual(code, 0)
        self.assertIn("INCOMPLETE", out)
        code, _ = run_cli("check", self.root / "data/playtests.json", "--strict")
        self.assertEqual(code, 1)

    def test_broken_concepts_file_leaves_references_unchecked_without_cascade(self):
        (self.root / "design/concepts.json").write_text(json.dumps({"concepts": {"oops": 1}}), encoding="utf-8")
        code, out = run_cli("check", self.root, "--json")
        report = next(d["report"] for d in json.loads(out)["datasets"] if d["kind"] == "playtests")
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["unchecked_reason"], "concepts_unreadable")

    def test_project_check_prints_verdicts_and_gate(self):
        code, out = run_cli("check", self.root)
        self.assertEqual(code, 0)
        self.assertIn("parry_tempo.learn_timing: 버팀", out)
        code, out = run_cli("check", self.root, "--fail-on-assumed")
        self.assertEqual(code, 1)
        self.assertIn("parry_tempo.tempo_choice", out)


class MeasuredSource(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        shutil.copy(SAMPLE / "data/playtests.json", self.dir / "playtests.json")

    def tearDown(self):
        self.tmp.cleanup()

    def errors(self, text):
        r = cp.check_text(text, "doc.md", [self.dir], check_paths=True)
        return [f.message for f in r.findings if f.level == "error"]

    def test_measured_source_must_name_a_recorded_session(self):
        sid = sample("data/playtests.json")["playtests"][0]["id"]
        self.assertEqual(self.errors(f"피격률 15% [측정: playtests.json#{sid}]\n"), [])
        msgs = self.errors("피격률 15% [측정: playtests.json#pt_19990101_9]\n")
        self.assertEqual(len(msgs), 1)
        self.assertIn("pt_19990101_9", msgs[0])


if __name__ == "__main__":
    unittest.main()
