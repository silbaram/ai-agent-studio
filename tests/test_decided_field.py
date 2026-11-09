"""게이트 길 재시험(2026-11-09)의 이슈 305~307 테스트. 표준 라이브러리 unittest만 사용한다."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from _studio import ROOT, STUDIO, calibrate as cal, common, concepts as cc, datasets, levels as lv, playtests as pt, provenance as pv, run_cli
from test_balance_field import row, printed as cal_printed
from test_calibrate import CONFIG, Workspace
from test_verdict_field import CONCEPTS, approved

STAGE = {"id": "zone_1", "duration": 300, "kills": {"crawler": 250, "elite": 2}, "income": {"seed": 15},
         "status": "proposed", "provenance": {"kind": "assumed"}}


class DecidedKind(unittest.TestCase):
    """306번: 사용자가 정한 기획 의도(목표, 문턱, 설계 입력)는 [결정]이고, 게이트가 막지 않는다."""

    def test_a_decided_entry_leaves_the_gate_306(self):
        e = dict(copy.deepcopy(STAGE), provenance={"kind": "decided", "source": "사용자 2026-11-09"})
        errors: list = []
        self.assertTrue(common.check_common(e, "zone_1", errors))
        s = common.summary_counts([e])
        self.assertEqual(s["unverified"], [])
        self.assertEqual(s["provenance_counts"]["decided"], 1)

    def test_the_korean_name_is_accepted_306(self):
        e = dict(copy.deepcopy(STAGE), provenance={"kind": "결정", "source": "사용자 2026-11-09"})
        common.check_common(e, "zone_1", [])
        self.assertEqual(e["provenance"]["kind"], "decided")

    def test_a_decision_names_who_and_when_306(self):
        for source in (None, "", "사용자"):
            with self.subTest(source=source):
                prov = {"kind": "decided"} if source is None else {"kind": "decided", "source": source}
                errors: list = []
                common.check_common(dict(copy.deepcopy(STAGE), provenance=prov), "zone_1", errors)
                self.assertEqual([e["code"] for e in errors], ["provenance"])
                self.assertIn("날짜", errors[0]["message"])

    def test_fields_may_be_decided_306(self):
        e = copy.deepcopy(STAGE)
        e["provenance"]["fields"] = {"duration": {"kind": "decided", "source": "사용자 2026-11-09"},
                                     "kills": {"kind": "measured", "source": "data/playtests.json#pt_a"},
                                     "income": {"kind": "decided", "source": "사용자 2026-11-09"}}
        common.check_common(e, "zone_1", [])
        self.assertEqual(common.summary_counts([e])["unverified"], [])
        self.assertEqual(common.effective_kind(e), "measured")

    def test_only_decisions_make_a_decided_entry_306(self):
        e = copy.deepcopy(STAGE)
        e["provenance"]["fields"] = {k: {"kind": "decided", "source": "사용자 2026-11-09"} for k in ("duration", "kills", "income")}
        self.assertEqual(common.effective_kind(e), "decided")

    def test_md_tags_accept_decided_306(self):
        r = pv.check_text("문턱 -0.2 [결정: 사용자 2026-11-09]보다 작다", "x.md", bare_numbers=True)
        self.assertEqual(r.counts["decided"], 1)
        self.assertEqual(r.counts["assumed"], 0)
        self.assertEqual([f.level for f in r.findings], [])

    def test_an_empty_decided_tag_asks_for_a_source_306(self):
        r = pv.check_text("문턱 -0.2 [결정]보다 작다", "x.md", bare_numbers=True)
        self.assertIn("출처가 없습니다", r.findings[0].message)
        self.assertIn("사용자 2026-11-09", r.findings[0].message)

    def test_md_tags_need_who_and_when_306(self):
        for tag in ("[결정]", "[결정: 사용자]"):
            with self.subTest(tag=tag):
                r = pv.check_text(f"문턱 -0.2 {tag}보다 작다", "x.md", bare_numbers=True)
                self.assertEqual([f.level for f in r.findings], ["error"])

    def test_a_decided_brief_threshold_passes_the_gate_306(self):
        data = copy.deepcopy(CONCEPTS)
        brief = approved(data)["brief"]
        for h in brief["hypotheses"]:
            for k in ("claim", "failure_signal", "test"):
                h[k] = h[k].replace("[가정]", "[결정: 사용자 2026-11-09]")
        brief["prototype"]["success_criteria"] = brief["prototype"]["success_criteria"].replace("[가정]", "[결정: 사용자 2026-11-09]")
        r = cc.validate(data)
        self.assertFalse(any(u.startswith(approved(data)["id"] + ".brief.hypotheses") for u in r["unverified"]))
        self.assertNotIn(approved(data)["id"] + ".brief.prototype.success_criteria", r["unverified"])

    def test_retagging_a_threshold_keeps_the_criteria_stamp_306(self):
        data = copy.deepcopy(CONCEPTS)
        h = approved(data)["brief"]["hypotheses"][0]
        before = cc.criteria_stamp(h)
        h["failure_signal"] = h["failure_signal"].replace("[가정]", "[결정: 사용자 2026-11-09]")
        self.assertIn("[결정", h["failure_signal"])
        self.assertEqual(cc.criteria_stamp(h), before)   # 지난 판정이 흔들리지 않는다
        h["failure_signal"] = h["failure_signal"].replace("[결정: 사용자 2026-11-09]", "[결정: 사용자 2026-11-09] 이상")
        self.assertNotEqual(cc.criteria_stamp(h), before)

    def test_counts_show_decided_only_when_present_306(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        p = Path(tmp.name) / "items.json"
        sample = json.loads((STUDIO / "assets/sample-project/data/items.json").read_text(encoding="utf-8"))
        p.write_text(json.dumps(sample, ensure_ascii=False), encoding="utf-8")
        _, out = run_cli("check", str(p))
        self.assertNotIn("결정 ", out)
        sample["items"][0]["provenance"] = {"kind": "decided", "source": "사용자 2026-11-09"}
        p.write_text(json.dumps(sample, ensure_ascii=False), encoding="utf-8")
        _, out = run_cli("check", str(p))
        self.assertIn("· 결정 1", out)


class StraddlingConditions(Workspace):
    """305번: 섞은 평균이 가정과 맞아도, 조건마다 가정의 양쪽으로 갈리면 참고로 둔다."""

    def grouped(self, *levels):
        s = self.run_session(runs=10 * len(levels), groups=[
            {"upgrades": [], "variant": {"_setting": str(n)}, "runs": 10, "stage_stats": [{"stage": "zone_2", "entered": 10, "cleared": 8, "level": lv}]}
            for n, lv in enumerate(levels)])
        s.pop("upgrades")
        return s

    def test_values_on_both_sides_are_a_hint_305(self):
        self.sessions(self.grouped(5, 3))   # 가정 4: 평균 4는 맞지만 5와 3으로 갈린다(차 2 > 4의 20%)
        r = cal.calibrate(self.root)
        level = row(r, "level", "zone_2")
        self.assertFalse(level["off"])
        self.assertTrue(level["mixed"])
        self.assertIn("조건마다 다름, 참고", cal_printed(r))

    def test_a_small_spread_is_quiet_305(self):
        self.sessions(self.grouped(4.2, 3.9))   # 양쪽이지만 차 0.3 < 0.8
        self.assertFalse(row(cal.calibrate(self.root), "level", "zone_2")["mixed"])

    def test_a_wide_spread_on_one_side_is_quiet_305(self):
        self.sessions(self.grouped(2.5, 3.9))   # 평균 3.2는 가정 4의 허용치 안, 차 1.4는 크지만 둘 다 가정 아래다
        self.assertFalse(row(cal.calibrate(self.root), "level", "zone_2")["mixed"])

    def test_one_side_only_is_quiet_305(self):
        self.sessions(self.grouped(4.5, 4.7))
        self.assertFalse(row(cal.calibrate(self.root), "level", "zone_2")["mixed"])


class SupplyCappedKills(Workspace):
    """307번: 넘긴 판의 처치 수가 레벨에 놓인 적 수와 같으면, 적이 나오는 수가 처치를 묶은 것이라고 알린다."""

    def placed(self):   # 레벨 구성 검사가 낸 그 단계의 처치 수(조우의 적 × 반복)
        report = next(e for e in datasets.collect([self.root]) if e.get("kind") == "levels")["report"]
        return next(st["kills"] for st in report["stages"] if st["id"] == "zone_2")

    def test_kills_equal_to_the_placed_count_are_noted_307(self):
        wolves = self.placed()["frost_wolf"]
        self.sessions(self.run_session(stage_stats=[{"stage": "zone_2", "entered": 10, "cleared": 8, "kills": {"frost_wolf": wolves}}]))
        r = cal.calibrate(self.root)
        note = next(n for n in r["notes"] if "레벨 구성에 놓인" in n)
        self.assertIn("frost_wolf", note)
        self.assertIn("kill_time_over_length", note)

    def test_fewer_kills_are_quiet_307(self):
        wolves = self.placed()["frost_wolf"]
        self.sessions(self.run_session(stage_stats=[{"stage": "zone_2", "entered": 10, "cleared": 8, "kills": {"frost_wolf": wolves - 5}}]))
        self.assertFalse(any("레벨 구성에 놓인" in n for n in cal.calibrate(self.root)["notes"]))


class ReviewFixes(Workspace):
    """305~307번 검토에서 나온 것."""

    def legacy_stamp(self, h):   # 이 고침 전의 지문(NFC만 맞춤). 이미 기록된 판정의 criteria다
        return hashlib.sha256(json.dumps({k: h.get(k) for k in cc.CRITERIA_KEYS}, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:8]

    def test_retagging_from_any_assumed_form_keeps_the_stamp(self):
        for old, new in (("[가정: 기획 의도]", "[결정: 사용자 2026-11-09]"), ("[assumed]", "[decided: user 2026-11-09]"),
                         ("[가정：메모]", "[결정：사용자 2026-11-09]"), ("[가정]", "[가정: 메모]")):
            with self.subTest(old=old):
                h = {"id": "h", "claim": "x", "failure_signal": f"상관 -0.2 {old}보다 크다", "test": "t"}
                before = cc.criteria_stamp(h)
                h["failure_signal"] = h["failure_signal"].replace(old, new)
                self.assertEqual(cc.criteria_stamp(h), before)

    def test_a_stamp_recorded_before_the_change_still_matches(self):
        data = copy.deepcopy(CONCEPTS)
        c = approved(data)
        h = c["brief"]["hypotheses"][0]
        h["failure_signal"] = h["failure_signal"].replace("[가정]", "[가정: 기획 의도]", 1)
        self.assertIn("[가정: 기획 의도]", h["failure_signal"])
        v = {"concept": c["id"], "hypothesis": h["id"], "criteria": self.legacy_stamp(h)}
        self.assertNotEqual(v["criteria"], cc.criteria_stamp(h))   # 메모 태그가 있으면 지문 계산이 바뀐다
        warnings: list = []
        self.assertEqual(pt._check_criteria(v, "w", cc.hypothesis_index(data), warnings), "ok")
        self.assertEqual(warnings, [])
        h["failure_signal"] = h["failure_signal"].replace("5판", "7판")   # 문턱을 바꾸면 예전 지문도 지금 지문도 맞지 않는다
        self.assertEqual(pt._check_criteria(v, "w", cc.hypothesis_index(data), []), "changed")

    def test_a_decided_source_is_not_a_path(self):
        r = pv.check_text("문턱 -0.2 [결정: 기획/사용자 2026-11-09]보다 작다", "x.md", base_dirs=[Path(self.tmp.name)], check_paths=True, bare_numbers=True)
        self.assertEqual([f.message for f in r.findings], [])
        r = pv.check_text("값 [측정: nowhere/x.json]", "x.md", base_dirs=[Path(self.tmp.name)], check_paths=True)
        self.assertEqual([f.level for f in r.findings], ["error"])   # 측정·계산의 경로는 그대로 본다

    def test_the_viewer_counts_decided(self):
        html = (STUDIO / "assets/viewer.html").read_text(encoding="utf-8")
        self.assertIn("결정 ${p.decided}", html)

    def test_level_warnings_name_a_decided_source(self):
        self.assertEqual(lv._source_text({"decided"}), "결정")

    def test_one_count_line_for_every_kind(self):
        pc = {"assumed": 1, "computed": 0, "measured": 2, "decided": 0, "unspecified": 0}
        self.assertEqual(common.provenance_text(pc), "가정 1 · 계산 0 · 측정 2 · 미지정 0")
        self.assertEqual(common.provenance_text(dict(pc, decided=3)), "가정 1 · 계산 0 · 측정 2 · 결정 3 · 미지정 0")
        self.assertEqual(common.provenance_text({"assumed": 0, "computed": 0, "measured": 0, "decided": 0}), "가정 0 · 계산 0 · 측정 0")

    def test_few_cleared_conditions_still_make_a_straddle(self):
        """4차 기록의 꼴: 조건마다 넘긴 판이 1~2판(모두 참고)이고 끝 레벨이 12, 10, 9로 가정 10의 양쪽이다.
        넘긴 판이 적은 조건을 빼면 참고가 사라져, 섞은 평균을 맞는 값으로 옮길 수 있다. 참고 쪽으로 기우는 것이 안전하다."""
        s = self.run_session(runs=4, groups=[
            {"upgrades": [], "variant": {"_setting": str(n)}, "runs": 2, "stage_stats": [{"stage": "zone_1", "entered": 2, "cleared": 2, "level_end": lv}]}
            for n, lv in enumerate((5, 3))])   # 가정은 다음 단계 zone_2의 level_at 4
        s.pop("upgrades")
        self.sessions(s)
        r = cal.calibrate(self.root)
        end = row(r, "level_end", "zone_1")
        self.assertFalse(end["off"])
        self.assertTrue(end["mixed"])
        self.assertIn("조건마다 다름, 참고", cal_printed(r))

    def test_a_partly_counted_stage_is_not_supply_capped(self):
        rows = [{"kind": "kills", "stage": "s", "item": "a", "measured": 5}]
        entry = lambda stages: [{"ok": True, "kind": "levels", "report": {"levels": [{"stage": "s", "kills": {"a": 5}, "kills_partial": True}], "stages": stages}}]  # noqa: E731
        self.assertEqual(cal._supply_capped(rows, entry([{"id": "s", "kills": None}])), [])   # 모르는 적이 있어 단계 합계를 내지 못함
        self.assertEqual(len(cal._supply_capped(rows, entry([{"id": "s", "kills": {"a": 5}}]))), 1)

    def test_a_decided_simulator_config_does_not_pass_the_gate(self):
        for name in ("meta.json", "meta_combat.json"):
            self.edit(f"data/{name}", lambda d: d.__setitem__("provenance", {"kind": "computed", "source": "reports/calibrate.json"}))
        self.edit(CONFIG, lambda d: d.__setitem__("provenance", {"kind": "decided", "source": "사용자 2026-11-09"}))
        self.assertIn("meta_combat.json", " ".join(datasets.unverified_configs([self.root])))
        code, out = run_cli("check", str(self.root), "--fail-on-assumed")
        self.assertIn("결정", next(line for line in out.splitlines() if "시뮬레이터 설정" in line))


class Docs(unittest.TestCase):
    def read(self, rel):
        return (ROOT / rel).read_text(encoding="utf-8")

    def test_decided_is_documented_306(self):
        for rel in ("skills/numeric-provenance/SKILL.md", "skills/playtest-verdict/SKILL.md", "skills/concept-exploration/references/brief.md", "docs/architecture.md"):
            with self.subTest(rel=rel):
                self.assertIn("[결정", self.read(rel))
        self.assertIn("스스로", self.read("skills/numeric-provenance/SKILL.md"))   # 에이전트가 자기 짐작에 결정을 달지 않는다

    def test_the_viewer_names_decided_306(self):
        html = (STUDIO / "assets/viewer.html").read_text(encoding="utf-8")
        self.assertRegex(html, r'decided: "결정"')


if __name__ == "__main__":
    unittest.main()
