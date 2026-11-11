"""이미 만들고 있는 게임(187, 168번): 후보 칸 없이 브리프만 적은 컨셉과 컨셉 없이 적은 그레이박스 세션. 표준 라이브러리 unittest만 사용한다."""
import copy
import unittest

from _studio import ROOT, concepts as cc, playtests as pt
from test_concepts import APPROVED, concept, codes
from test_playtests import session, validate, verdict


def existing(**over):
    c = {"id": "my_game", "name": "이미 만든 게임", "status": "approved", "existing_game": True, "brief": copy.deepcopy(APPROVED["brief"])}
    c.update(over)
    return c


class ExistingConcept(unittest.TestCase):
    def test_a_brief_without_candidate_fields_passes(self):
        r = cc.validate({"concepts": [existing()]})
        self.assertEqual((r["errors"], r["warnings"]), ([], []))
        self.assertEqual(r["approved"], ["my_game"])

    def test_without_the_key_the_candidate_fields_are_still_required(self):
        c = existing()
        del c["existing_game"]
        r = cc.validate({"concepts": [c]})
        self.assertEqual(codes(r["errors"]).count("missing_field"), 6)
        self.assertIn("existing_game", r["errors"][0]["message"])

    def test_the_key_must_be_true_or_false(self):
        r = cc.validate({"concepts": [existing(existing_game="yes")]})
        self.assertEqual(codes(r["errors"]), ["schema"])   # 잘못 적은 값 하나만 알린다. 후보 칸 오류를 줄줄이 내지 않는다
        self.assertEqual(r["approved"], [])

    def test_the_hint_names_the_section(self):
        c = existing()
        del c["existing_game"]
        self.assertIn("existing-game.md의 '순서'", cc.validate({"concepts": [c]})["errors"][0]["message"])

    def test_two_existing_games_are_warned(self):
        r = cc.validate({"concepts": [existing(), existing(id="other", status="proposed", brief=None)]})
        self.assertEqual([w["where"] for w in r["warnings"] if w["code"] == "existing_game_many"], ["other"])

    def test_a_cut_existing_concept_is_not_counted(self):
        r = cc.validate({"concepts": [existing(), existing(id="old", status="cut")]})
        self.assertNotIn("existing_game_many", codes(r["warnings"]))

    def test_only_the_name_is_required(self):
        for field in cc.REQUIRED_TEXT[1:] + ("signature", "next_test"):
            with self.subTest(field):
                self.assertNotIn(field, " ".join(e["message"] for e in cc.validate({"concepts": [existing()]})["errors"]))

    def test_the_name_and_brief_are_still_required(self):
        c = existing()
        del c["name"]
        self.assertIn("missing_field", codes(cc.validate({"concepts": [c]})["errors"]))
        c = existing()
        del c["brief"]
        self.assertIn("brief_missing", codes(cc.validate({"concepts": [c]})["errors"]))

    def test_it_is_left_out_of_the_structure_comparison(self):
        r = cc.validate({"concepts": [existing(), concept("a"), concept("b", decision="route")]})
        self.assertEqual(r["errors"], [])
        self.assertNotIn("next_test_missing", [w["code"] for w in r["warnings"] if w["where"] == "my_game"])
        self.assertNotIn("my_game", str(r["duplicates"]))

    def test_a_written_signature_is_still_checked(self):
        r = cc.validate({"concepts": [existing(signature={"decision": "timing"})]})
        self.assertIn("signature_too_small", codes(r["errors"]))

    def test_the_table_marks_the_existing_game(self):
        data = {"concepts": [existing()]}
        row = next(x for x in cc.table(data, cc.validate(data)).splitlines() if "my_game" in x)
        self.assertIn("선택 · 기존 게임", row)

    def test_the_viewer_marks_the_existing_game(self):
        viewer = (ROOT / "skills/studio-data/assets/viewer.html").read_text(encoding="utf-8")
        self.assertIn('e.existing_game === true ? "기존 게임"', viewer)
        self.assertIn("existing_game_many:", viewer)

    def test_with_a_signature_it_is_compared(self):
        sig = concept("a")["signature"]
        r = cc.validate({"concepts": [existing(signature=dict(sig, space="x")), concept("a", space="x")]})
        self.assertIn("my_game", str(r["duplicates"]))


class SessionWithoutConcept(unittest.TestCase):
    GREY = {"greybox": [{"check": "g1", "passed": True}]}

    def grey(self, **over):
        s = session(**self.GREY)
        del s["concept"], s["observations"]
        s.update(over)
        return s

    def test_a_greybox_only_session_needs_no_concept(self):
        r = validate([self.grey()], [])
        self.assertEqual(r["errors"], [])

    def test_it_is_not_counted_as_unchecked_without_concept_data(self):
        r = pt.validate({"playtests": [self.grey()], "verdicts": []}, None)
        self.assertEqual((r["errors"], r["unchecked"], r["unchecked_reason"]), ([], len(r["unchecked_refs"]), None))   # 단계 기록의 참조는 프로젝트 검사에서 본다

    def test_observations_events_and_hypothesis_notes_still_need_it(self):
        for over in ({"observations": [{"hypothesis": "learn_timing", "value": "x"}]}, {"events": {"parry": 3}},
                     {"notes": [{"kind": "deviation", "text": "t", "hypotheses": ["learn_timing"]}]}):
            with self.subTest(over):
                r = validate([self.grey(**over)], [])
                self.assertIn("concept", " ".join(e["message"] for e in r["errors"]))

    def test_an_empty_concept_is_still_an_error(self):
        self.assertIn("schema", codes(validate([self.grey(concept="")], [])["errors"]))

    def test_a_project_with_it_passes(self):
        import json, shutil, tempfile
        from pathlib import Path
        from _studio import SAMPLE, run_cli
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "p"
            shutil.copytree(SAMPLE, root)
            path = root / "data/playtests.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["playtests"].append({"id": "pt_grey", "date": "2026-11-11", "build": "abc", "players": ["self"], "runs": 1,
                                      "stage_stats": [{"stage": "zone_1", "entered": 1, "cleared": 1}]})
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            code, out = run_cli("check", root)
        self.assertEqual(code, 0, out)
        self.assertTrue(out.rstrip().endswith("→ PASS"), out[-500:])

    def test_a_verdict_cannot_cite_it(self):
        r = validate([self.grey(id="pt_g"), session()], [verdict(sessions=["pt_a", "pt_g"])])
        err = next(e for e in r["errors"] if e["code"] == "session_concept_mismatch")
        self.assertIn("컨셉 없이", err["message"])


class Docs(unittest.TestCase):
    def test_the_concept_skill_routes_an_existing_game(self):
        skill = (ROOT / "skills/concept-exploration/SKILL.md").read_text(encoding="utf-8")
        ref = ROOT / "skills/concept-exploration/references/existing-game.md"
        self.assertIn("references/existing-game.md", skill)
        text = ref.read_text(encoding="utf-8")
        self.assertIn("existing_game", text)
        self.assertIn("사용자", text)
        self.assertIn("## 순서", text)
        self.assertNotIn("existing_game`을 지운다", text)   # signature를 적으면 키를 두고도 비교된다

    def test_the_record_format_names_the_key(self):
        self.assertIn("existing_game", (ROOT / "skills/concept-exploration/references/concept-record.md").read_text(encoding="utf-8"))

    def test_system_design_points_there(self):
        self.assertIn("existing-game.md", (ROOT / "skills/system-design/SKILL.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
