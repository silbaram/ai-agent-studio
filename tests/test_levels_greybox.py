"""그레이박스 확인 목록(L3) 테스트: 레벨마다 그래픽 없이 확인할 항목과 플레이 기록의 연결. 표준 라이브러리 unittest만 사용한다."""
import json
import unittest

from _studio import ROOT, SAMPLE, STUDIO, common, levels as lv, playtests as pt
from test_levels import BUDGET, COMBAT, ENEMIES, THREAT, both, codes, enc, level, row, run
from test_levels_field import notes, printed
from test_levels_recheck import Project, warning


def item(iid="g1", check="대장간까지 몇 초 걸리는가", **over):
    return {"id": iid, "check": check, **over}


def log(*records):
    return {"g1": [{"session": "pt_1", "date": "2026-11-01", **r} for r in records]}


def boxed(*items, greybox_log=None, **over):
    return run(both(level("s1", enc(), greybox=list(items), **over)), greybox_log=greybox_log)


def rows(result, lid="s1"):
    return next(x for x in result["levels"] if x["id"] == lid)["greybox"]


class Items(unittest.TestCase):
    def test_a_level_may_list_checks(self):
        r = boxed(item(), item("g2", encounter="e1", expect=[10, 20]))
        self.assertEqual(r["errors"], [])
        self.assertEqual([x["id"] for x in rows(r)], ["g1", "g2"])
        self.assertEqual((rows(r)[1]["encounter"], rows(r)[1]["expect"]), ("e1", [10, 20]))

    def test_no_list_is_fine(self):
        r = run()
        self.assertEqual(r["errors"], [])
        self.assertEqual(rows(r), [])

    def test_bad_shapes_are_errors(self):
        for bad in ("글", [1], [{"id": "g1"}], [item(check="")], [item(expect=[5, 1])], [item(expect="10")], [item(oops=1)], [{"check": "id 없음"}]):
            r = run(both(level("s1", enc(), greybox=bad)))
            self.assertIn("schema", codes(r["errors"]), bad)

    def test_ids_are_unique_across_the_file(self):
        r = run(both(level("s1", enc(), greybox=[item()]), level("s2", enc("e2", {"c": 6}), greybox=[item()])))
        self.assertIn("duplicate_id", codes(r["errors"]))

    def test_the_encounter_has_to_be_in_this_level(self):
        r = boxed(item(encounter="e11"))
        self.assertIn("e1", next(e["message"] for e in r["errors"] if e["code"] == "unknown_encounter"))

    def test_an_encounter_with_a_format_error_still_counts_as_there(self):
        r = run(both(level("s1", enc(), enc("e3", repeat=0), greybox=[item(encounter="e3")])))
        self.assertNotIn("unknown_encounter", codes(r["errors"]))

    def test_a_cut_level_is_left_out(self):
        r = run(both(level("s1", enc()), level("s2", enc("e2", {"c": 6}))) + [level("old", enc("e9"), combat_stage="s1", status="cut", greybox=[item()])])
        self.assertNotIn("그레이박스", notes(r))


class Judgement(unittest.TestCase):
    def status(self, it, *records):
        return rows(boxed(it, greybox_log=log(*records) if records else {}))[0]["status"]

    def test_no_record_is_no_record(self):
        self.assertEqual(self.status(item()), "none")

    def test_a_value_in_range_passes(self):
        self.assertEqual(self.status(item(expect=[10, 20]), {"value": 15}), "passed")

    def test_a_value_out_of_range_fails(self):
        self.assertEqual(self.status(item(expect=[10, 20]), {"value": 25}), "failed")

    def test_an_open_range_works(self):
        self.assertEqual(self.status(item(expect=[None, 20]), {"value": 5}), "passed")

    def test_a_written_verdict_decides_without_a_range(self):
        self.assertEqual(self.status(item(), {"passed": True}), "passed")
        self.assertEqual(self.status(item(), {"passed": False}), "failed")

    def test_the_number_beats_the_written_verdict(self):
        self.assertEqual(self.status(item(expect=[10, 20]), {"value": 25, "passed": True}), "failed")

    def test_a_value_without_a_range_has_no_verdict(self):
        self.assertEqual(self.status(item(), {"value": 25}), "open")

    def test_the_last_record_counts(self):
        self.assertEqual(self.status(item(expect=[10, 20]), {"value": 25}, {"value": 15}), "passed")

    def test_the_row_keeps_the_record(self):
        r = rows(boxed(item(expect=[10, 20]), greybox_log=log({"value": 15, "n": 4})))[0]
        self.assertEqual((r["value"], r["session"], r["n"]), (15, "pt_1", 4))


class Reporting(unittest.TestCase):
    def test_a_failure_is_a_warning_on_the_item(self):
        w = warning(boxed(item(expect=[10, 20]), greybox_log=log({"value": 25})), "greybox_failed")
        self.assertEqual((w["owner"], w["part"]), ("s1", "g1"))
        self.assertIn("25", w["message"])
        self.assertIn("10~20", w["message"])
        self.assertIn("pt_1", w["message"])

    def test_a_failed_verdict_without_a_value_is_a_warning_too(self):
        self.assertIn("pt_1", warning(boxed(item(), greybox_log=log({"passed": False})), "greybox_failed")["message"])

    def test_the_note_counts_each_state(self):
        r = boxed(item(expect=[10, 20]), item("g2"), item("g3"), greybox_log={**log({"value": 15}), "g2": [{"session": "pt_1", "date": "2026-11-01", "value": 3}]})
        text = notes(r)
        self.assertIn("그레이박스 확인: 3개 · 통과 1", text)
        self.assertIn("판정 없음 1", text)
        self.assertIn("기록 없음 1", text)

    def test_levels_without_a_list_are_named(self):
        self.assertIn("항목이 없는 레벨: s2", notes(boxed(item())))

    def test_a_game_without_lists_hears_nothing(self):
        self.assertNotIn("그레이박스", notes(run()))

    def test_without_play_records_the_note_says_so(self):
        self.assertIn("플레이 기록을 함께 읽지 않았습니다", notes(boxed(item())))

    def test_unpassed_items_hold_the_final_gate(self):
        r = boxed(item(), item("g2", expect=[1, 2]), greybox_log={"g2": [{"session": "pt_1", "date": "2026-11-01", "value": 1}]})
        self.assertIn("그레이박스 s1.g1(기록 없음)", r["unverified"])
        self.assertNotIn("s1.g2", " ".join(r["unverified"]))

    def test_the_table_lists_the_checks(self):
        text = lv.table({}, boxed(item(encounter="e1", expect=[10, 20]), greybox_log=log({"value": 15})))
        self.assertIn("| 레벨 | 확인 | 조우 | 기대 | 기록 | 판정 |", text)
        self.assertIn("| s1 | g1: 대장간까지 몇 초 걸리는가 | e1 | 10~20 | 15 (pt_1) | 통과 |", text)

    def test_a_pipe_in_a_check_stays_in_its_cell(self):
        line = next(x for x in lv.table({}, boxed(item(check="왼쪽 | 오른쪽"))).splitlines() if "왼쪽" in x)
        self.assertEqual(line.count("|") - line.count("\\|"), 7)

    def test_no_lists_no_table(self):
        self.assertNotIn("| 레벨 | 확인 |", lv.table({}, run()))

    def test_an_acknowledged_failure_goes_away(self):
        data = {"levels": both(level("s1", enc(), greybox=[item(expect=[10, 20])], acknowledged={"greybox_failed": {"g1": "다음 빌드에서 고친다"}})), "threat_budget": BUDGET}
        r = lv.validate(data, enemies=ENEMIES, threat=THREAT, combat=COMBAT, greybox_log=log({"value": 25}))
        common.apply_acknowledged("levels", data, r)
        self.assertNotIn("greybox_failed", codes(r["warnings"]))


class Sessions(unittest.TestCase):
    def session(self, **over):
        return {"id": "pt_1", "date": "2026-11-01", "concept": "c", "build": "b", "players": ["a"], "runs": 3, **over}

    def validate(self, refs=None, **over):
        return pt.validate({"playtests": [self.session(**over)], "verdicts": []}, {"c": {"approved": True, "hypotheses": []}}, refs=refs)

    def test_a_session_may_record_checks(self):
        r = self.validate(greybox=[{"check": "g1", "value": 15, "n": 3}, {"check": "g2", "passed": True, "note": "메모"}], refs={"greybox": {"g1", "g2"}})
        self.assertEqual(r["errors"], [])

    def test_bad_records_are_errors(self):
        for bad in ("글", [1], [{"value": 1}], [{"check": "g1"}], [{"check": "g1", "value": "많이"}], [{"check": "g1", "passed": "yes"}],
                    [{"check": "g1", "value": 1, "n": -1}], [{"check": "g1", "value": 1, "n": 0}], [{"check": "g1", "value": 1, "oops": 1}]):
            self.assertIn("schema", codes(self.validate(greybox=bad)["errors"]), bad)

    def test_a_session_of_only_checks_is_not_empty(self):
        self.assertNotIn("session_without_observations", codes(self.validate(greybox=[{"check": "g1", "value": 1}], refs={"greybox": {"g1"}})["warnings"]))

    def test_an_unknown_check_is_a_warning_with_a_hint(self):
        w = warning(self.validate(greybox=[{"check": "g2", "value": 1}], refs={"greybox": {"g1", "g22"}}), "unknown_reference")
        self.assertIn("g22", w["message"])
        self.assertIn("levels.json", w["message"])
        self.assertNotIn("calibrate", w["message"])

    def test_a_stage_reference_keeps_its_own_advice(self):
        w = warning(self.validate(stage_stats=[{"stage": "zone_9", "entered": 1, "cleared": 1}], refs={"stages": {"zone_1"}}), "unknown_reference")
        self.assertIn("calibrate", w["message"])

    def test_without_levels_the_reference_is_unchecked(self):
        self.assertIn("greybox", self.validate(greybox=[{"check": "g1", "value": 1}])["unchecked_refs"])


class Project_(Project):
    def test_sample_links_levels_and_sessions(self):
        r = self.report("levels")
        statuses = [x["status"] for lvl in r["levels"] for x in lvl["greybox"]]
        self.assertTrue(statuses)
        self.assertEqual(set(statuses), {"passed"})
        self.assertIn("그레이박스 확인", "\n".join(r["notes"]))

    def test_a_later_session_decides(self):
        self.edit("data/playtests.json", lambda d: d["playtests"].append({"id": "pt_later", "date": "2027-01-01", "concept": d["playtests"][0]["concept"], "build": "x", "players": ["a"], "runs": 1,
                                                                         "greybox": [{"check": "crypt_forge_buy", "value": 999}]}))
        self.assertIn("greybox_failed", codes(self.report("levels")["warnings"]))

    def extra_session(self, date, *records):
        self.edit("data/playtests.json", lambda d: d["playtests"].append({"id": "pt_extra", "date": date, "concept": d["playtests"][0]["concept"], "build": "x", "players": ["a"], "runs": 1,
                                                                          "greybox": list(records)}))

    def test_an_older_session_written_last_does_not_decide(self):
        self.extra_session("2020-01-01", {"check": "crypt_forge_buy", "value": 999})
        self.assertNotIn("greybox_failed", codes(self.report("levels")["warnings"]))

    def test_a_record_without_a_result_is_not_read(self):
        self.extra_session("2027-01-01", {"check": "crypt_forge_buy"})
        self.assertEqual(next(x for lvl in self.report("levels")["levels"] for x in lvl["greybox"])["status"], "passed")

    def test_a_session_citing_an_unknown_check_is_a_warning_in_the_project(self):
        self.extra_session("2027-01-01", {"check": "crypt_forge_bye", "value": 1})
        self.assertIn("crypt_forge_buy", warning(self.report("playtests"), "unknown_reference")["message"])

    def test_a_text_value_does_not_stop_the_level_check(self):
        self.edit("data/playtests.json", lambda d: d["playtests"][-1]["greybox"].__setitem__(0, {"check": "crypt_forge_buy", "value": "많이", "passed": True}))
        self.assertEqual(self.check()[0], 1)
        self.assertEqual(next(x for lvl in self.report("levels")["levels"] for x in lvl["greybox"])["status"], "passed")

    def test_a_bad_count_is_not_carried(self):
        self.edit("data/playtests.json", lambda d: d["playtests"][-1]["greybox"].__setitem__(0, {"check": "crypt_forge_buy", "value": 285, "n": "많이"}))
        self.assertIsNone(next(x for lvl in self.report("levels")["levels"] for x in lvl["greybox"])["n"])

    def test_playtests_of_the_wrong_shape_do_not_stop_the_level_check(self):
        self.edit("data/playtests.json", lambda d: d.__setitem__("playtests", 5))
        self.assertIn("playtests", self.check()[1])
        self.assertIn("levels", [d["kind"] for d in __import__("_studio").datasets.collect([self.root]) if d["ok"]])

    def test_the_gate_names_unchecked_items_for_what_they_are(self):
        self.edit("data/levels.json", lambda d: d["levels"][2].__setitem__("greybox", [item("altar_x")]))
        line = next(x for x in self.check("--fail-on-assumed")[1].splitlines() if "altar_x" in x)
        self.assertIn("그레이박스 altar.altar_x(기록 없음)", line)
        self.assertIn("통과하지 않은 그레이박스", line)

    def test_a_broken_session_is_not_read(self):
        self.edit("data/playtests.json", lambda d: d["playtests"][-1].__setitem__("greybox", "글"))
        self.assertEqual({x["status"] for lvl in self.report("levels")["levels"] for x in lvl["greybox"]}, {"none"})

    def test_the_viewer_shows_the_list(self):
        html = (STUDIO / "assets/viewer.html").read_text(encoding="utf-8")
        self.assertIn("info.greybox", html)
        self.assertIn("e.greybox", html[html.index("function renderPlaytests"):])
        self.assertIn("greybox_failed:", html)
        self.assertIn("unknown_encounter:", html)

    def test_the_docs_cover_it(self):
        fmt = (ROOT / "skills/level-design/references/levels-format.md").read_text(encoding="utf-8")
        skill = (ROOT / "skills/level-design/SKILL.md").read_text(encoding="utf-8")
        record = (ROOT / "skills/playtest-verdict/references/playtest-record.md").read_text(encoding="utf-8")
        arch = (ROOT / "docs/architecture.md").read_text(encoding="utf-8")
        for word in ("`greybox`", "`greybox_failed`", "`unknown_encounter`", "`expect`"):
            self.assertIn(word, fmt)
        self.assertIn("### 6. 그레이박스", skill)
        self.assertIn("`greybox`", record)
        self.assertIn("`greybox`", (ROOT / "skills/playtest-verdict/SKILL.md").read_text(encoding="utf-8"))
        tools = skill[skill.index("## 도구"):skill.index("## 절차")]
        self.assertIn("그레이박스", tools)
        self.assertIn("| L3 | **그레이박스 확인 목록.** 레벨마다 그래픽 없이 확인할 항목과 플레이 기록 연결 (`level-design`) | 1차 완료 |", arch)


if __name__ == "__main__":
    unittest.main()
