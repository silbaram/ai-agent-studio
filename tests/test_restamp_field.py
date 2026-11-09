"""지문 바꾸기 현장 시험(2026-11-09)의 이슈 314~317 테스트. 표준 라이브러리 unittest만 사용한다."""
import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from _studio import ROOT, STUDIO, common, concepts as cc, datasets as ds, provenance as pv, run_cli
from test_verdict_field import CONCEPTS, PLAYTESTS, hyp

DECIDED = "[결정: 사용자 2026-11-09]"
SAMPLE = STUDIO / "assets/sample-project"


def untagged(text: str, bare: bool = True) -> list:
    return pv.check_text(text, "x", bare_numbers=bare).untagged


def entry(r: dict, path: str) -> str | None:
    return next((u for u in r["unverified"] if u == path or u.startswith(path + "(")), None)


def codes(r: dict, code: str) -> list:
    return [w for w in r["warnings"] if w["code"] == code]


class DotList314(unittest.TestCase):
    """314번: 가운뎃점으로 이은 수 목록(0.5·1·2배)은 범위처럼 수 하나다. 뒤의 태그 하나로 통과한다."""

    def test_a_dot_list_takes_one_tag_314(self):
        r = pv.check_text(f"설정 순서를 바꾼다(예: 0.5·1·2배 {DECIDED}, 1·2·0.5배 {DECIDED})", "x", bare_numbers=True)
        self.assertEqual(r.untagged, [])
        self.assertEqual([t.value for t in r.tags], ["0.5·1·2배", "1·2·0.5배"])

    def test_an_untagged_list_is_shown_whole_314(self):
        self.assertEqual(untagged("설정 0.5·1·2배 순서로 돈다"), ["0.5·1·2배"])
        self.assertEqual(untagged("봇은 4~9%에 머문다"), ["4~9%"])   # 범위도 앞 수까지 보인다
        self.assertEqual(untagged("빌드 cfg721feeb5·3판"), ["3판"])   # 낱말에 붙은 숫자는 목록의 앞 수가 아니다

    def test_a_comma_still_separates_values_314(self):
        self.assertEqual(untagged(f"0.5배, 2배 {DECIDED}"), ["0.5배"])

    def test_a_list_value_is_compared_across_fields_314(self):
        data = copy.deepcopy(CONCEPTS)
        h = hyp(data)
        h["failure_signal"] = h["failure_signal"] + f" 설정 0.5·1·2배 {DECIDED} 순서다"
        h["test"] = h["test"] + " 설정 0.5·1·2배 [가정] 순서다"
        w = codes(cc.validate(data), "criteria_tag_mismatch")
        self.assertEqual([x["part"] for x in w], ["0.5·1·2배"])

    def test_gate_entries_separate_values_with_commas_314(self):
        data = copy.deepcopy(CONCEPTS)
        hyp(data)["test"] = "설정 0.5·1·2배 [가정] 순서, 구간 60초 [가정]"
        got = entry(cc.validate(data), "parry_tempo.brief.hypotheses[0].test")
        self.assertIn("가정: 0.5·1·2배, 60초", got)


class SameSentence315(unittest.TestCase):
    """315번: 수치 뒤 태그는 같은 문장 안에서만 찾는다. 경고와 게이트 줄은 보이지 않은 값의 개수를 알린다."""

    def test_a_tag_in_the_next_sentence_does_not_pass_an_earlier_number_315(self):
        self.assertEqual(untagged("판이 끝나기 30초 전 안의 레벨업은 빈칸이다. 세는 레벨업은 공격 강화만이다 [가정]."), ["30초"])
        self.assertEqual(untagged("(판이 끝나기 30초 전은 빈칸). 공격 강화만 센다 [가정]"), ["30초"])
        self.assertEqual(untagged("판이 끝나기 30초 전은 빈칸이다.) 공격 강화만 센다 [가정]"), ["30초"])

    def test_a_tag_in_the_same_sentence_still_passes_315(self):
        self.assertEqual(untagged("판이 끝나기 30초 전은 빈칸이다 [가정]. 공격 강화만 센다."), [])
        self.assertEqual(untagged("문턱 0.25 [가정]보다 작다. 6판 [가정]."), [])   # 소수점은 문장 끝이 아니다
        self.assertEqual(untagged("구간 30초를 game/summarize.py로 잰다 [가정]"), [])   # 파일 이름의 점도 아니다

    def test_the_warning_counts_values_it_does_not_show_315(self):
        r = pv.check_text("1판, 2판, 3판, 4판, 5판, 6판, 7판", "x")
        self.assertEqual(len(r.findings), 1)
        self.assertIn("5판 외 2개", r.findings[0].message)
        self.assertEqual(r.findings[0].values, ["1판", "2판", "3판", "4판", "5판", "6판", "7판"])

    def test_concept_warnings_carry_the_full_list_315(self):
        data = copy.deepcopy(CONCEPTS)
        hyp(data)["test"] = "1판, 2판, 3판, 4판, 5판, 6판, 7판"
        r = cc.validate(data)
        w = next(x for x in codes(r, "untagged_number") if x["message"].startswith("brief.hypotheses[0].test:"))
        self.assertEqual(len(w["values"]), 7)
        self.assertIn("1판, 2판, 3판, 4판, 5판 외 2개", entry(r, "parry_tempo.brief.hypotheses[0].test"))   # 경고와 같은 수를 보인다

    def test_the_json_output_keeps_the_list_315(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        data = copy.deepcopy(CONCEPTS)
        hyp(data)["test"] = "1판, 2판, 3판, 4판, 5판, 6판, 7판"
        p = Path(tmp.name) / "concepts.json"
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        _, out = run_cli("check", p, "--json")
        warnings = json.loads(out)["datasets"][0]["report"]["warnings"]
        self.assertIn(7, [len(w.get("values", [])) for w in warnings if w["code"] == "untagged_number"])


class GameValues316(unittest.TestCase):
    """316번: 판정 기준 문장에 옮겨 적은 빌드의 게임 수치는 게이트를 늘 막는다. 빌드 이름으로 가리키라고 알린다."""

    def test_plus_signed_numbers_count_in_criteria_316(self):
        self.assertEqual(untagged("sharp_bolt 피해 +10, quick_draw 초당 발사 +0.3"), ["+10", "+0.3"])
        self.assertEqual(untagged("sharp_bolt 피해 +10", bare=False), [])   # 판정 기준이 아닌 문장은 보지 않는다
        self.assertEqual(untagged("레벨 1+10 v2+3"), [])

    def test_assumed_values_in_criteria_get_a_gate_note_316(self):
        data = copy.deepcopy(CONCEPTS)
        hyp(data)["test"] = "tune-levelup-power 수치(sharp_bolt 피해 +10 [가정], 1번 [가정])로 센다"
        r = cc.validate(data)
        self.assertTrue(r["gate_notes"])
        note = r["gate_notes"][0]
        for part in ("빌드 id", "builds", "criteria"):
            self.assertIn(part, note)

    def test_no_note_without_assumed_criteria_316(self):
        data = copy.deepcopy(CONCEPTS)
        for h in data["concepts"][0]["brief"]["hypotheses"]:
            for k in ("claim", "failure_signal", "test"):
                h[k] = h[k].replace("[가정]", DECIDED)
        proto = data["concepts"][0]["brief"]["prototype"]
        proto["success_criteria"] = proto["success_criteria"].replace("[가정]", DECIDED)
        data["concepts"][0]["brief"]["loop"]["moment"] = "30초 [가정] 동안 세 번 막는다"   # 판정 기준이 아닌 칸의 가정은 이 길이 아니다
        r = cc.validate(data)
        self.assertIsNotNone(entry(r, "parry_tempo.brief.loop.moment"))
        self.assertEqual(r["gate_notes"], [])

    def test_the_cli_prints_the_note_under_the_gate_316(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        data = copy.deepcopy(CONCEPTS)
        hyp(data)["test"] = "tune-levelup-power 수치(sharp_bolt 피해 +10 [가정])로 센다"
        p = Path(tmp.name) / "concepts.json"
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        _, gated = run_cli("check", p, "--fail-on-assumed")
        _, plain = run_cli("check", p)
        self.assertTrue(any(x.startswith("참고:") and "빌드 id" in x for x in gated.splitlines()))
        self.assertFalse(any("빌드 id" in x for x in plain.splitlines()))   # 게이트를 보지 않을 때는 말하지 않는다

    def test_builds_are_named_not_copied_in_the_docs_316(self):
        brief = (ROOT / "skills/concept-exploration/references/brief.md").read_text(encoding="utf-8")
        rule = (ROOT / "skills/numeric-provenance/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("게임 수치를 `test`에 옮겨 적지 않는다", brief)
        self.assertIn("빌드 id", rule)


class BriefSources317(unittest.TestCase):
    """317번: check는 브리프의 [계산]·[측정] 출처도 md의 --check-paths와 같이 확인한다(파일, 플레이 기록의 세션 id)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "design").mkdir()
        (self.root / "data").mkdir()
        (self.root / "data/playtests.json").write_text(json.dumps(PLAYTESTS, ensure_ascii=False), encoding="utf-8")

    def write(self, source: str) -> Path:
        data = copy.deepcopy(CONCEPTS)
        hyp(data)["test"] = hyp(data)["test"] + f" 지난 기록은 9판 [측정: {source}]이다"
        p = self.root / "design/concepts.json"
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return p

    def report(self, path: Path) -> dict:
        return next(d for d in ds.collect([path]) if d["kind"] == "concepts")["report"]

    def test_an_unknown_session_is_an_error_317(self):
        r = self.report(self.write("data/playtests.json#pt_29991231_9"))
        self.assertTrue(any("pt_29991231_9" in e["message"] for e in r["errors"]), r["errors"])

    def test_a_missing_file_is_an_error_317(self):
        r = self.report(self.write("data/nowhere.json#pt_20261105_1"))
        self.assertTrue(any("data/nowhere.json" in e["message"] for e in r["errors"]), r["errors"])

    def test_a_recorded_session_passes_317(self):
        r = self.report(self.write("data/playtests.json#pt_20261105_1"))
        self.assertEqual([e for e in r["errors"] if e["code"] == "provenance"], [])

    def test_a_source_that_is_not_a_path_is_not_checked_317(self):
        r = self.report(self.write("2차 플레이 메모"))
        self.assertEqual([e for e in r["errors"] if e["code"] == "provenance"], [])

    def test_the_gate_fails_on_a_wrong_session_317(self):
        code, out = run_cli("check", self.write("data/playtests.json#pt_29991231_9"), "--fail-on-assumed")
        self.assertEqual(code, 1)
        self.assertIn("pt_29991231_9", out)

    def test_the_sample_project_still_passes_317(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        copy_root = Path(tmp.name) / "sample"
        shutil.copytree(SAMPLE, copy_root)
        r = self.report(copy_root / "design/concepts.json")
        self.assertEqual([e for e in r["errors"] if e["code"] == "provenance"], [])

    def test_brief_sources_are_documented_317(self):
        rule = (ROOT / "skills/numeric-provenance/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("브리프의 `[계산]`·`[측정]` 출처", rule)


class ReviewFixes(unittest.TestCase):
    """314~317 수정의 검토에서 나온 것."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "data").mkdir()
        (self.root / "data/playtests.json").write_text(json.dumps(PLAYTESTS, ensure_ascii=False), encoding="utf-8")

    def sources(self, source: str) -> list:
        r = pv.check_text(f"9판 [측정: {source}]", "x", base_dirs=[self.root], check_paths=True)
        return [f.message for f in r.findings if f.level == "error"]

    def test_every_session_of_a_merged_source_is_checked(self):
        self.assertEqual(self.sources("data/playtests.json#pt_20261105_1, pt_20261112_1"), [])
        self.assertEqual(self.sources("data/playtests.json#pt_20261105_1·pt_20261112_1"), [])
        self.assertEqual(self.sources("data/playtests.json#pt_20261105_1; pt_20261112_1."), [])   # 문장부호는 id가 아니다
        missing = self.sources("data/playtests.json#pt_20261105_1 pt_29991231_9")
        self.assertEqual(len(missing), 1)
        self.assertIn("pt_29991231_9", missing[0])
        self.assertNotIn("pt_20261105_1", missing[0])

    def test_words_after_the_session_are_not_sessions(self):
        self.assertEqual(self.sources("data/playtests.json#pt_20261105_1 세션 요약"), [])
        self.assertEqual(self.sources("data/playtests.json#pt_20261105_1 summary"), [])
        self.assertTrue(self.sources("data/playtests.json#nowhere 세션 요약"))   # 첫 낱말은 늘 세션 id로 본다

    def test_signed_numbers_keep_their_unit(self):
        self.assertEqual(untagged("부화가 +3초 빨라지고 -0.5초 늦어진다"), ["+3초", "-0.5초"])
        self.assertEqual(untagged("부화가 -3초 빨라진다", bare=False), ["-3초"])
        self.assertEqual([t.value for t in pv.check_text("부화 +3초 [가정]", "x", bare_numbers=True).tags], ["+3초"])
        self.assertEqual(untagged("보스는 60-90초에 잡힌다", bare=False), ["60-90초"])   # 범위의 줄표는 부호가 아니다

    def test_an_acknowledgment_under_the_old_value_still_applies(self):
        data = copy.deepcopy(CONCEPTS)
        h = hyp(data)
        h["failure_signal"] = h["failure_signal"] + f" 설정 0.5·1·2배 {DECIDED}, 발사 +0.3 {DECIDED}"
        h["test"] = h["test"] + " 설정 0.5·1·2배 [가정], 발사 +0.3 [가정]"
        data["concepts"][0]["acknowledged"] = {"criteria_tag_mismatch": {"2배": "test의 순서는 예시다", "0.3": "test의 발사는 빌드 값이다"}}
        r = cc.validate(data)
        common.apply_acknowledged("concepts", data, r)
        self.assertEqual(codes(r, "criteria_tag_mismatch"), [])
        self.assertEqual(sorted(a["part"] for a in r["acknowledged"] if a["code"] == "criteria_tag_mismatch"), ["0.3", "2배"])
        notes = " ".join(r["ack_notes"])
        for part in ("'2배'", "'0.5·1·2배'", "'0.3'", "'+0.3'"):
            self.assertIn(part, notes)

    def test_the_new_value_wins_over_the_old_one(self):
        data = copy.deepcopy(CONCEPTS)
        h = hyp(data)
        h["failure_signal"] = h["failure_signal"] + f" 설정 0.5·1·2배 {DECIDED}"
        h["test"] = h["test"] + " 설정 0.5·1·2배 [가정]"
        data["concepts"][0]["acknowledged"] = {"criteria_tag_mismatch": {"0.5·1·2배": "예시다", "2배": "예전에 적은 것"}}
        r = cc.validate(data)
        self.assertEqual([w["part"] for w in codes(r, "criteria_tag_mismatch")], ["0.5·1·2배"])
        self.assertEqual(r.get("ack_notes", []), [])

    def test_abbreviations_do_not_end_a_sentence(self):
        self.assertEqual(untagged("구간 30초 e.g. 판 끝 [가정]"), [])
        self.assertEqual(untagged("구간 30초 vs. 60초 [가정]"), ["30초"])   # 줄임말 뒤에도 다음 수치 전까지다
        self.assertEqual(untagged("구간 30초(e.g. 판 끝) [가정]"), [])

    def test_a_closing_bracket_around_the_number_ends_the_search(self):
        self.assertEqual(untagged("(판 끝 30초 전은 빈칸) 공격 강화만 센다 [가정]"), ["30초"])
        self.assertEqual(untagged("（판 끝 30초 전은 빈칸）, 공격 강화만 센다 [가정]"), ["30초"])
        self.assertEqual(untagged(f"봇 9판(같은 시드) {DECIDED}"), [])   # 수치 뒤에 연 괄호는 그 안에서 닫힌다
        self.assertEqual(untagged(f"봇 9판(같은 시드. 순서는 바꿈) {DECIDED}"), [])
        self.assertEqual(untagged("[예: 30초 [가정]]"), [])
        self.assertEqual(untagged("[부화 6초](docs/x.md) [가정]", bare=False), [])   # md 링크의 대괄호는 경계가 아니다
        self.assertEqual(untagged("구간 30초 [가정 메모]"), [])   # 형식이 틀린 태그는 형식 오류로 따로 알린다

    def test_warnings_and_gate_lines_show_the_same_number_of_values(self):
        self.assertEqual(pv.few(["1판", "2판", "1판", "3판"]), "1판, 2판, 3판")
        self.assertEqual(pv.few([f"{n}판" for n in range(1, 8)]), "1판, 2판, 3판, 4판, 5판 외 2개")


if __name__ == "__main__":
    unittest.main()
