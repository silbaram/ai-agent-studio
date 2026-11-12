"""뒤로 넘긴 설계 층 이슈(190, 200, 233, 290) 테스트. 표준 라이브러리 unittest만 사용한다."""
import copy
import io
import json
import re
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from _studio import ROOT, SAMPLE, STUDIO, common, concepts as cc, economy as ec, growth as gr, run_cli, systems as sy
from test_growth import COMBAT, ENEMIES, data as growth_data, validate as growth_validate

BRIEF = {"pillars": [{"name": "욕심이 곧 성장", "test": "t"}, {"name": "숙성이 읽힌다", "test": "t"}], "mvp": ["보석 숙성 3단계", "조준 무기"], "out_of_scope": ["멀티플레이"]}
CONCEPTS = [{"id": "gems", "status": "approved", "brief": BRIEF}]


def system(sid="ripening", scope="mvp", **over):
    return {"id": sid, "scope": scope, "pillars": ["욕심이 곧 성장", "숙성이 읽힌다"], "mvp": ["보석 숙성 3단계", "조준 무기"] if scope == "mvp" else [],
            "rules": [{"id": "r1", "text": "보석은 3단계로 익는다"}], **over}


def net():
    return system("net", "out", pillars=[], out_of_scope=["멀티플레이"])


def run(*entries):
    return sy.validate({"systems": list(entries)}, concepts=CONCEPTS)


def codes(rows):
    return [x["code"] for x in rows]


def order(result):
    return {x["id"]: x["order"] for x in result["rows"]}


def printed(fn, result):
    out = io.StringIO()
    with redirect_stdout(out):
        fn(result)
    return out.getvalue()


class OrderSkipsWhatIsNotBuilt(unittest.TestCase):
    """190: 범위 밖·삭제된 시스템에 기대는 시스템은 단계가 없고, 나중 시스템은 MVP 뒤에 따로 센다."""

    def test_a_dependency_only_on_an_out_system_has_no_stage(self):
        r = run(system("a"), system("hud", "later", depends_on=["net"]), net())
        self.assertIsNone(order(r)["hud"])
        self.assertIn("scope_dependency", codes(r["errors"]))   # 알리는 것은 기존 오류다

    def test_an_mvp_system_on_an_out_system_has_no_stage(self):
        r = run(system("a", depends_on=["net"]), net())
        self.assertIsNone(order(r)["a"])

    def test_a_dependency_on_a_cut_system_has_no_stage(self):
        r = run(system("a", depends_on=["old"]), system("old", status="cut"))
        self.assertIsNone(order(r)["a"])
        self.assertIn("cut_referenced", codes(r["warnings"]))
        self.assertNotIn("dependency_cycle", codes(r["errors"]))

    def test_what_leans_on_an_unplaced_system_has_no_stage_either(self):
        r = run(system("a", depends_on=["old"]), system("b", depends_on=["a"]), system("old", status="cut"), system("c"))
        self.assertEqual(order(r), {"a": None, "b": None, "c": 1})
        self.assertNotIn("dependency_cycle", codes(r["errors"]))

    def test_an_unknown_dependency_has_no_stage(self):
        r = run(system("a", depends_on=["ghost"]))
        self.assertIsNone(order(r)["a"])
        self.assertIn("unknown_system", codes(r["errors"]))

    def test_an_mvp_system_on_a_later_one_has_no_stage(self):
        r = run(system("a", depends_on=["hud"]), system("hud", "later"))
        self.assertEqual(order(r), {"a": None, "hud": 1})
        self.assertIn("scope_dependency", codes(r["errors"]))

    def test_later_stages_start_after_every_mvp_stage(self):
        r = run(system("a"), system("b", depends_on=["a"]), system("hud", "later"), system("map", "later", depends_on=["hud"]))
        self.assertEqual(order(r), {"a": 1, "b": 2, "hud": 3, "map": 4})

    def test_the_printout_says_why_a_system_has_no_stage(self):
        text = printed(sy.print_extra, run(system("a", depends_on=["old"]), system("old", status="cut")))
        self.assertIn("단계 없음", text)
        self.assertIn("old", text)

    def test_the_format_doc_says_so(self):
        doc = (ROOT / "skills/system-design/references/systems-format.md").read_text(encoding="utf-8")
        calc = doc[doc.index("\n## 계산\n"):doc.index("\n## 검사\n")]
        self.assertIn("삭제", calc)
        self.assertIn("범위 밖", calc)


class NameOnlyOutOfScope(unittest.TestCase):
    """200: 이름만 범위 밖인 시스템도 알린다. 중복은 duplicate_item이 이미 알린다."""

    def test_a_name_only_out_of_scope_system_is_claimed(self):
        for scope in ("mvp", "later"):
            r = run(system("a"), system("b", scope, name="멀티플레이 로비"))
            self.assertEqual([e["where"] for e in r["errors"] if e["code"] == "out_of_scope_claimed"], ["b"], scope)

    def test_an_out_system_named_after_an_item_but_pointing_at_none_is_told_which(self):
        r = run(system("a"), system("lobby", "out", pillars=[], name="멀티플레이 로비"))
        w = next(x for x in r["warnings"] if x["code"] == "scope_mismatch")
        self.assertIn("멀티플레이", w["message"])
        self.assertIn("out_of_scope", w["message"])

    def test_case_does_not_hide_the_name(self):
        brief = {**BRIEF, "out_of_scope": ["PvP 대전"]}
        r = sy.validate({"systems": [system("a"), system("b", "later", name="pvp 대전 모드")]}, concepts=[{"id": "gems", "status": "approved", "brief": brief}])
        self.assertIn("out_of_scope_claimed", codes(r["errors"]))

    def test_duplicates_in_each_list_warn(self):
        for key, value in (("pillars", ["욕심이 곧 성장", "욕심이 곧 성장", "숙성이 읽힌다"]), ("mvp", ["조준 무기", "보석 숙성 3단계", "조준 무기"])):
            self.assertIn("duplicate_item", codes(run(system(**{key: value}))["warnings"]), key)
        self.assertIn("duplicate_item", codes(run(system("a"), system("b", depends_on=["a", "a"]))["warnings"]))


# ---------- 233: 경험치 곡선 ----------
def xp_economy(per_stage=(0, 60, 90), currency="xp", **cur):
    return {"economy": {"currencies": {currency: {"name": "경험치", **cur}}},
            "stages": [{"id": sid, "duration": 60, "income": {currency: amount}} for sid, amount in zip(("s1", "s2", "s3"), per_stage)]}


def with_xp(xp, **over):
    d = growth_data(**over)
    d["growth"]["xp"] = xp
    return d


def grow(d, economy=None):
    report = ec.validate(economy) if economy is not None else None
    return gr.validate(d, combat=COMBAT, items={}, upgrades={}, enemies=ENEMIES, economy=economy, economy_report=report)


class XpCurve(unittest.TestCase):
    """233: growth.json에 경험치 곡선을 두고, 재화 흐름의 경험치 수입으로 단계별 레벨을 다시 낸다."""

    LINEAR = {"curve": {"growth": "linear", "base": 10, "rate": 5}}   # 1→2 10, 2→3 15, 3→4 20, 4→5 25, 5→6 30

    def test_without_xp_nothing_changes(self):
        r = grow(growth_data())
        self.assertIsNone(r["xp"])

    def test_the_curve_is_shown_as_cumulative_thresholds(self):
        r = grow(with_xp(self.LINEAR))
        self.assertEqual(r["errors"], [])
        self.assertEqual(r["xp"]["to_reach"], {"2": 10, "3": 25, "4": 45, "5": 70, "6": 100})
        self.assertIn("경험치", printed(gr.print_extra, r))

    def test_exponential_and_table_curves(self):
        r = grow(with_xp({"curve": {"growth": "exponential", "base": 10, "rate": 1}}))
        self.assertEqual(r["xp"]["to_reach"]["4"], 70)      # 10 + 20 + 40
        r = grow(with_xp({"curve": {"growth": "table", "values": {"1": 5, "2": 5, "3": 10, "4": 10, "5": 20}}}))
        self.assertEqual((r["errors"], r["xp"]["to_reach"]["6"]), ([], 50))

    def test_bad_curves_are_errors(self):
        for bad in ({"curve": {"growth": "steep"}}, {"curve": {"growth": "linear", "base": 0, "rate": 1}}, {"curve": {"growth": "table", "values": {"1": 5, "3": 5}}},
                    {"curve": {"growth": "table", "values": {"one": 5}}}, {"curve": {"growth": "table", "values": {"1": 5, "2": 5}}},   # 레벨 6까지 닿지 않는다
                    {"curve": {"growth": "linear", "base": 10, "rate": -5}},   # 레벨 3부터 0 이하
                    {"curve": self.LINEAR["curve"], "tolerance": -1}, {"curve": self.LINEAR["curve"], "currency": 3}, {"curve": self.LINEAR["curve"], "oops": 1}, "곡선"):
            r = grow(with_xp(bad))
            self.assertIn("schema", codes(r["errors"]), bad)

    def test_matching_income_is_quiet(self):
        # s1에 들어설 때 0(레벨 1). s2에 들어설 때 s1 수입 0 → 레벨 1. 레벨이 맞도록 level_at을 준다
        r = grow(with_xp({**self.LINEAR, "currency": "xp"}, level_at={"s1": 1, "s2": 4}), xp_economy(per_stage=(45, 0)))
        self.assertEqual((r["errors"], codes(r["warnings"])), ([], []))
        self.assertEqual(r["xp"]["stages"], [{"stage": "s1", "xp": 0, "level": 1, "level_at": 1}, {"stage": "s2", "xp": 45, "level": 4, "level_at": 4}])

    def test_drift_beyond_the_tolerance_warns(self):
        d = with_xp({**self.LINEAR, "currency": "xp"}, level_at={"s1": 1, "s2": 6})
        r = grow(d, xp_economy(per_stage=(45, 0)))
        w = next(x for x in r["warnings"] if x["code"] == "xp_level_mismatch")
        self.assertIn("s2", w["message"])
        self.assertIn("4", w["message"])
        d["growth"]["xp"]["tolerance"] = 2
        self.assertNotIn("xp_level_mismatch", codes(grow(d, xp_economy(per_stage=(45, 0)))["warnings"]))

    def test_linked_economy_stages_are_followed(self):
        econ = xp_economy(per_stage=(25, 20))
        econ["stages"][0].update(id="a", combat_stage="s1")
        econ["stages"][1].update(id="b", combat_stage="s2")
        r = grow(with_xp({**self.LINEAR, "currency": "xp"}, level_at={"s1": 1, "s2": 3}), econ)
        self.assertEqual(r["xp"]["stages"][1], {"stage": "s2", "xp": 25, "level": 3, "level_at": 3})

    def test_an_unknown_or_carried_currency_is_an_error(self):
        r = grow(with_xp({**self.LINEAR, "currency": "exp"}), xp_economy())
        self.assertIn("xp", next(e["message"] for e in r["errors"] if e["where"] == "growth.xp"))
        r = grow(with_xp({**self.LINEAR, "currency": "xp"}), xp_economy(carry=True))
        self.assertIn("schema", codes(r["errors"]))

    def test_without_economy_the_curve_is_still_checked_and_the_reason_shown(self):
        r = grow(with_xp({**self.LINEAR, "currency": "xp"}))
        self.assertEqual((r["errors"], r["xp"]["stages"]), ([], []))
        self.assertIn("재화 흐름", printed(gr.print_extra, r))

    def test_an_unlinked_stage_is_not_compared(self):
        r = grow(with_xp({**self.LINEAR, "currency": "xp"}, level_at={"s1": 1, "s2": 9}), xp_economy(per_stage=(45,)))
        self.assertEqual([x["stage"] for x in r["xp"]["stages"]], ["s1"])
        self.assertNotIn("xp_level_mismatch", codes(r["warnings"]))

    def test_the_project_check_reads_the_economy(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            shutil.copytree(SAMPLE, tmp / "p")
            g = json.loads((tmp / "p/data/growth.json").read_text(encoding="utf-8"))
            g["growth"]["xp"] = {"curve": {"growth": "linear", "base": 10, "rate": 5}, "currency": "xp"}
            (tmp / "p/data/growth.json").write_text(json.dumps(g, ensure_ascii=False), encoding="utf-8")
            e = json.loads((tmp / "p/data/economy.json").read_text(encoding="utf-8"))
            e["economy"]["currencies"]["xp"] = {"name": "경험치"}
            for st, amount in zip(e["stages"], (45, 150, 300)):
                st.setdefault("income", {})["xp"] = amount
            (tmp / "p/data/economy.json").write_text(json.dumps(e, ensure_ascii=False), encoding="utf-8")
            _, out = run_cli("check", tmp / "p")
            self.assertIn("xp_level_mismatch", out)       # zone_3에 들어설 때 195 → 레벨 8, level_at 9
            self.assertNotIn("economy.currencies.xp", out)   # 경험치는 쓰는 재화가 아니다
        finally:
            shutil.rmtree(tmp)

    def test_the_codes_are_in_the_format_table(self):
        doc = (ROOT / "skills/run-growth/references/growth-format.md").read_text(encoding="utf-8")
        self.assertIn("| `xp_level_mismatch`", doc[doc.index("## 검사 내용"):])
        self.assertIn("`xp`", doc)

    def test_the_viewer_shows_the_curve(self):
        self.assertIn("r.xp", (STUDIO / "assets/viewer.html").read_text(encoding="utf-8"))


# ---------- 290: 가설 수와 성공 기준 ----------
def brief_concept(success, hyps=("a_timing", "b_route", "c_grind")):
    sample = json.loads((SAMPLE / "design/concepts.json").read_text(encoding="utf-8"))
    c = copy.deepcopy(next(x for x in sample["concepts"] if x["status"] == "approved"))
    base = c["brief"]["hypotheses"][0]
    c["brief"]["hypotheses"] = [{**base, "id": h} for h in hyps]
    c["brief"]["prototype"]["success_criteria"] = success
    return {"concepts": [c]}


def misses(success, **kw):
    r = cc.validate(brief_concept(success, **kw))
    return [w for w in r["warnings"] if w["code"] == "success_criteria_misses_hypothesis"]


class SuccessCriteriaCoversHypotheses(unittest.TestCase):
    """290: 가설을 더했는데 성공 기준이 예전 가설 수를 말하거나 새 가설을 빼면 알린다."""

    def test_a_stale_count_warns(self):
        for text in ("두 가설의 틀렸다는 신호가 모두 나오지 않는다", "2개 가설 모두 신호가 없다", "가설 두 개의 신호가 없다", "2개의 가설이 버틴다", "가설 둘 다 버틴다"):
            found = misses(text)
            self.assertEqual(len(found), 1, text)
            self.assertIn("3", found[0]["message"])

    def test_the_right_count_is_quiet(self):
        for text in ("세 가설의 틀렸다는 신호가 모두 나오지 않는다", "3개 가설 모두", "세 가설 중 두 가설 이상이 버틴다"):
            self.assertEqual(misses(text), [], text)

    def test_a_threshold_is_not_the_number_of_hypotheses(self):
        for text in ("가설 1개 이상이 버티면 다음 단계로 간다", "두 가설 이상이 버틴다", "가설 2개 넘게 버틴다", "가설 1개라도 틀리면 실패다", "가설 2개만 버텨도 된다"):
            self.assertEqual(misses(text), [], text)
        self.assertEqual(len(misses("가설 2개 중 1개 이상이 버틴다")), 1)   # '중' 앞은 전체 수다

    def test_words_that_start_like_a_count_are_not_counts(self):
        for text in ("가설 열거 순서대로 확인한다", "가설 셋업을 먼저 한다", "가설 둘째 줄을 본다", "가설 열린 결말"):
            self.assertEqual(misses(text), [], text)
        for text in ("가설 둘이 버틴다", "가설 둘을 본다", "가설 둘과 지표", "가설 둘 다"):
            self.assertEqual(len(misses(text)), 1, text)

    def test_labels_and_any_one_are_not_counts(self):
        for text in ("한 가설이라도 신호가 나오면 실패다", "가설 1과 가설 2의 신호가 없다", "모든 가설의 신호가 없다", "세 갈래로 평균한 값이 2턴 이상이다"):
            self.assertEqual(misses(text), [], text)

    def test_naming_some_ids_but_not_all_warns(self):
        found = misses("a_timing: 피격률이 준다. b_route: 갈래마다 걸린 턴이 다르다")
        self.assertEqual(len(found), 1)
        self.assertIn("c_grind", found[0]["message"])

    def test_naming_every_id_or_none_is_quiet(self):
        self.assertEqual(misses("a_timing, b_route, c_grind의 신호가 모두 나오지 않는다"), [])
        self.assertEqual(misses("피격률이 준다"), [])
        self.assertEqual(misses("a_timing_extra 지표가 준다"), [])   # 다른 낱말의 일부는 id가 아니다

    def test_one_hypothesis_is_not_checked_by_id(self):
        self.assertEqual(misses("a_timing의 신호가 없다", hyps=("a_timing",)), [])

    def test_it_can_be_acknowledged(self):
        d = brief_concept("두 가설의 신호가 없다")
        d["concepts"][0]["acknowledged"] = {"success_criteria_misses_hypothesis": "셋째 가설은 따로 본다"}
        r = cc.validate(d)
        common.apply_acknowledged("concepts", d, r)
        self.assertNotIn("success_criteria_misses_hypothesis", codes(r["warnings"]))

    def test_the_sample_is_quiet(self):
        r = cc.validate(json.loads((SAMPLE / "design/concepts.json").read_text(encoding="utf-8")))
        self.assertNotIn("success_criteria_misses_hypothesis", codes(r["warnings"]))

    def test_docs_point_at_the_check(self):
        brief = (ROOT / "skills/concept-exploration/references/brief.md").read_text(encoding="utf-8")
        line = next(x for x in brief.splitlines() if "가설을 더하면" in x)
        self.assertIn("success_criteria_misses_hypothesis", line)
        self.assertIn("prototype.scope", line)
        self.assertNotIn("검사기는 이것을 보지 않는다", line)
        record = (ROOT / "skills/concept-exploration/references/concept-record.md").read_text(encoding="utf-8")
        self.assertIn("| `success_criteria_misses_hypothesis` | 경고 |", record)


if __name__ == "__main__":
    unittest.main()
