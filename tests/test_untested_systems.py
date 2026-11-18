"""가설이 닿지 않는 MVP 시스템: 시스템의 hypotheses가 브리프의 가설을 가리키고, 아무 가설도 시험하지 않는 MVP 시스템을 경고한다."""
import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from _studio import ROOT, SAMPLE, common, run_cli, systems as sy

HYPS = [{"id": "greed_pays", "claim": "c", "failure_signal": "f", "test": "t"}, {"id": "ripening_read", "claim": "c", "failure_signal": "f", "test": "t"}]
BRIEF = {"pillars": [{"name": "욕심이 곧 성장", "test": "t"}], "mvp": ["보석 숙성 3단계"], "out_of_scope": ["멀티플레이"], "hypotheses": HYPS}
CONCEPTS = [{"id": "gems", "status": "approved", "brief": BRIEF}]


def system(sid="ripening", scope="mvp", **over):
    return {"id": sid, "scope": scope, "pillars": ["욕심이 곧 성장"], "mvp": ["보석 숙성 3단계"], "rules": [{"id": "r1", "text": "보석은 익는다"}], **over}


def run(*entries, concepts=CONCEPTS):
    data = {"systems": list(entries)}
    r = sy.validate(data, concepts=concepts)
    common.apply_acknowledged("systems", data, r)
    return r


def codes(rows):
    return [x["code"] for x in rows]


class Links(unittest.TestCase):
    def test_a_system_names_the_hypotheses_that_test_it(self):
        r = run(system(hypotheses=["greed_pays"]))
        self.assertEqual((r["errors"], r["warnings"]), ([], []))
        self.assertEqual(r["rows"][0]["hypotheses"], ["greed_pays"])

    def test_a_hypothesis_missing_from_the_brief_is_an_error(self):
        r = run(system(hypotheses=["greed_pay"]))
        e = next(x for x in r["errors"] if x["code"] == "unknown_hypothesis")
        self.assertIn("greed_pays", e["message"])   # 비슷한 id를 알린다

    def test_hypotheses_must_be_a_list_of_ids(self):
        for bad in ("greed_pays", [1], [""]):
            self.assertIn("schema", codes(run(system(hypotheses=bad))["errors"]), bad)

    def test_a_repeated_hypothesis_is_a_duplicate_item(self):
        self.assertIn("duplicate_item", codes(run(system(hypotheses=["greed_pays", "greed_pays"]))["warnings"]))


class Untested(unittest.TestCase):
    def test_an_mvp_system_no_hypothesis_tests_is_a_warning(self):
        w = next(x for x in run(system())["warnings"] if x["code"] == "system_untested")
        self.assertEqual((w["where"], w.get("owner")), ("ripening", "ripening"))
        self.assertIn("SKILL.md", w["message"])

    def test_foundation_later_and_out_systems_are_not_asked(self):
        r = run(system(hypotheses=["greed_pays"], depends_on=["body"]), system("body", foundation=True, pillars=[], mvp=[]),
                system("hud", "later", mvp=[]), system("net", "out", pillars=[], mvp=[], out_of_scope=["멀티플레이"]))
        self.assertNotIn("system_untested", codes(r["warnings"]))

    def test_a_brief_without_hypothesis_ids_asks_nothing(self):
        brief = {**BRIEF, "hypotheses": [{"claim": "c", "failure_signal": "f", "test": "t"}]}
        self.assertNotIn("system_untested", codes(run(system(), concepts=[{"id": "gems", "status": "approved", "brief": brief}])["warnings"]))

    def test_without_concepts_nothing_is_asked(self):
        self.assertNotIn("system_untested", codes(run(system(), concepts=None)["warnings"]))

    def test_going_untested_on_purpose_is_acknowledged_and_listed(self):
        r = run(system(hypotheses=["greed_pays"]), system("unlocks", acknowledged={"system_untested": "장르에서 흔한 해금이라 시험하지 않는다 [결정: 사용자 2026-11-18]"}))
        self.assertNotIn("system_untested", codes(r["warnings"]))
        self.assertEqual(r["untested"], [{"id": "unlocks", "reason": "장르에서 흔한 해금이라 시험하지 않는다 [결정: 사용자 2026-11-18]"}])
        out = io.StringIO()
        with redirect_stdout(out):
            sy.print_extra(r)
        self.assertIn("가설 없이 만드는 MVP 시스템: unlocks", out.getvalue())

    def test_an_unacknowledged_one_is_listed_without_a_reason(self):
        r = run(system())
        self.assertEqual(r["untested"], [{"id": "ripening", "reason": None}])

    def test_the_table_shows_the_hypotheses(self):
        text = sy.table({}, run(system(hypotheses=["greed_pays", "ripening_read"])))
        self.assertIn("| 가설 |", text.splitlines()[0])
        self.assertIn("greed_pays, ripening_read", text)


class Project(unittest.TestCase):
    def test_the_sample_links_every_mvp_system(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name) / "game"
        shutil.copytree(SAMPLE, root)
        code, out = run_cli("check", root)
        self.assertIn("가설 없이 만드는 MVP 시스템: meta_unlocks, room_flow.", out)   # 예시는 확인으로 남기는 길을 보인다
        self.assertNotIn("확인 안 함", out)
        data = json.loads((root / "design/systems.json").read_text(encoding="utf-8"))
        self.assertTrue(any(s.get("hypotheses") for s in data["systems"]))

    def test_the_viewer_has_a_hypotheses_column(self):
        self.assertIn('"가설"', (ROOT / "skills/studio-data/assets/viewer.html").read_text(encoding="utf-8").split("function renderSystems", 1)[1].split("function ", 1)[0])

    def test_the_docs_tell_how_to_link_and_when_to_acknowledge(self):
        fmt = (ROOT / "skills/system-design/references/systems-format.md").read_text(encoding="utf-8")
        skill = (ROOT / "skills/system-design/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("| `hypotheses` |", fmt)
        self.assertIn("| `system_untested` |", fmt)
        self.assertIn("| `unknown_hypothesis` |", fmt)
        self.assertIn("`system_untested`", skill)
        record = (ROOT / "skills/production-handoff/references/production-record.md").read_text(encoding="utf-8")
        self.assertIn("가설 없이 만드는 MVP 시스템", record)



class ReviewFixes(unittest.TestCase):
    @staticmethod
    def handoff_step6():
        text = (ROOT / "skills/production-handoff/SKILL.md").read_text(encoding="utf-8")
        return text.split("### 6. 가져갈 것과 버릴 것을 적는다", 1)[1].split("### 7.", 1)[0]

    def test_step6_lists_systems_only_kept_unknown_hypotheses_reach(self):
        step = self.handoff_step6()
        self.assertIn("가설 없이 만드는 MVP 시스템", step)
        self.assertIn("keep_unknown", step)
        record = (ROOT / "skills/production-handoff/references/production-record.md").read_text(encoding="utf-8")
        self.assertIn("모름으로 둔 가설에만 닿는", record)

    def test_step6_says_to_settle_unacknowledged_systems_first(self):
        self.assertIn("system-design/SKILL.md#6-경고를-처리한다", self.handoff_step6())
        record = (ROOT / "skills/production-handoff/references/production-record.md").read_text(encoding="utf-8")
        row = next(l for l in record.splitlines() if l.startswith("| 가설 없이 만드는 MVP 시스템 |"))
        self.assertNotIn("먼저 정한다", row)   # 규칙은 SKILL.md 6단계 한 곳에

    def test_adding_a_hypothesis_links_it_to_systems(self):
        brief = (ROOT / "skills/concept-exploration/references/brief.md").read_text(encoding="utf-8")
        rule = next(l for l in brief.splitlines() if l.startswith("- **가설을 더하면 같은 편집에서 맞춘다.**"))
        self.assertIn("`hypotheses`", rule)
        self.assertIn("system_untested", rule)

    def test_sample_acknowledgements_carry_the_users_decision(self):
        data = json.loads((SAMPLE / "design/systems.json").read_text(encoding="utf-8"))
        reasons = [s["acknowledged"]["system_untested"] for s in data["systems"] if "system_untested" in s.get("acknowledged", {})]
        self.assertTrue(reasons)
        for r in reasons:
            self.assertRegex(r, r"\[결정: 사용자 \d{4}-\d{2}-\d{2}\]")

    def test_the_table_reads_hypotheses_like_the_other_columns(self):
        src = (ROOT / "skills/studio-data/scripts/studio_data/systems.py").read_text(encoding="utf-8")
        self.assertNotIn('x.get("hypotheses", [])', src)


class LinkCriterion(unittest.TestCase):
    """383: 잇는 기준은 가설의 주장이 그 시스템에 대한 것인가이고, 형식 문서 한 곳에만 있다."""
    @staticmethod
    def field_row():
        fmt = (ROOT / "skills/system-design/references/systems-format.md").read_text(encoding="utf-8")
        return next(l for l in fmt.splitlines() if l.startswith("| `hypotheses` |"))

    def test_the_field_row_links_by_the_claim_not_by_passing_through(self):
        row = self.field_row()
        self.assertIn("`claim`", row)
        self.assertNotIn("거쳐야 결과가 나오면", row)
        self.assertIn("재는 데만", row)   # 결과를 재는 데만 쓰이는 시스템은 적지 않는다

    def test_no_system_kind_is_excluded_by_name(self):
        row = self.field_row()   # 화면이나 진행도 주장이 그것에 달려 있으면 잇는다(예시 enemy_cues, my-tactics campaign)
        self.assertNotIn("값을 보여 주는 화면", row)
        self.assertNotIn("판을 이어 가는 진행", row)

    def test_the_criterion_is_what_the_claim_depends_on_not_its_words(self):
        row = self.field_row()
        self.assertIn("달려 있으면", row)
        self.assertIn("낱말", row)   # 주장 문장에 시스템의 낱말이 나오는지로 가리지 않는다
        self.assertNotIn("경험을 말하면", row)

    def test_skill_points_to_the_field_row(self):
        skill = (ROOT / "skills/system-design/SKILL.md").read_text(encoding="utf-8")
        step3 = next(l for l in skill.splitlines() if l.startswith("- `hypotheses`:"))
        step6 = next(l for l in skill.splitlines() if l.startswith("- `system_untested`:"))
        for line in (step3, step6):
            self.assertIn("references/systems-format.md#systems", line)
            self.assertNotIn("claim", line)   # 기준 문장은 형식 문서에만

    def test_the_warning_says_the_same_criterion(self):
        msg = sy.UNTESTED
        self.assertNotIn("이 시스템을 쓰는 가설", msg)
        self.assertIn("systems-format.md", msg)

if __name__ == "__main__":
    unittest.main()
