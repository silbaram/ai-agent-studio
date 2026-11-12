"""두 번째 게임 첫 실제 플레이와 my-roguelike 9판 채우기(2026-11-12)의 이슈 357~362 테스트. 표준 라이브러리 unittest만 사용한다."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from _studio import ROOT, STUDIO, claude, concepts as cc, run_cli
from test_retest_field import events_concepts
from test_verdict_field import CONCEPTS, codes, hyp, judge, printed, session, stamp, three, verdict

VERDICT = ROOT / "skills/playtest-verdict"
RECORD = VERDICT / "references/playtest-record.md"
CHANGES = VERDICT / "references/changes.md"
BRIEF = ROOT / "skills/concept-exploration/references/brief.md"
JUDGE = STUDIO / "assets/claude/studio-judge.md"


def read(path):
    return path.read_text(encoding="utf-8")


def never_seen(r):
    return [n for n in r.get("event_notes", []) if n["code"] == "event_never_seen"]


class KeepUnknown(unittest.TestCase):
    """357번: 사용자가 모름으로 두기로 정하면 적을 자리(keep_unknown)가 있고, 참고 줄이 같은 결정을 다시 요구하지 않는다."""

    def kept(self, text="사용자 결정(2026-11-12): 사망 쪽은 모름으로 둔다", **over):
        data = events_concepts()
        v = verdict("unknown", criteria=stamp(data), status="approved", next_needs="사건 6건이 필요한데 0건", keep_unknown=text, **over)
        return judge(three(events={"missed_parry": 0}), [v], concepts=data)

    def test_the_decision_silences_the_event_note_357(self):
        r = self.kept()
        self.assertEqual((r["errors"], r["warnings"], never_seen(r)), ([], [], []))

    def test_the_decision_replaces_the_next_needs_line_357(self):
        out = printed(self.kept())
        self.assertIn("모름으로 둠(parry_tempo.learn_timing): 사용자 결정(2026-11-12): 사망 쪽은 모름으로 둔다", out)
        self.assertNotIn("다음 시험 전에 풀 것", out)

    def test_without_the_decision_the_note_stays_357(self):
        data = events_concepts()
        r = judge(three(events={"missed_parry": 0}), [verdict("unknown", criteria=stamp(data))], concepts=data)
        self.assertEqual(len(never_seen(r)), 1)

    def test_only_an_unknown_verdict_can_keep_unknown_357(self):
        data = events_concepts()
        r = judge(three(), [verdict("holds", criteria=stamp(data), keep_unknown="사용자 결정")], concepts=data)
        self.assertIn("schema", codes(r["errors"]))

    def test_the_decision_is_text_357(self):
        for bad in ("", 1, True):
            with self.subTest(bad=bad):
                self.assertIn("schema", codes(self.kept(bad)["errors"]))

    def test_a_cut_decision_does_not_carry_over_357(self):
        """지난 판정(cut)의 결정은 새 판정에 이어지지 않는다. 새 판정마다 다시 정한다."""
        data = events_concepts()
        old = verdict("unknown", criteria=stamp(data), status="cut", cut_reason="2026-11-12 다시 판정", keep_unknown="사용자 결정")
        r = judge(three(events={"missed_parry": 0}), [old, verdict("unknown", criteria=stamp(data))], concepts=data)
        self.assertEqual(len(never_seen(r)), 1)

    def test_documented_357(self):
        self.assertIn("`keep_unknown`", read(RECORD))
        self.assertIn("keep_unknown", read(CHANGES))


class OneBuild(unittest.TestCase):
    """358번: 빌드 지문(game_build)을 한 세션에만 적어도, 커밋이 같으면 같은 빌드다."""

    def test_same_commit_with_and_without_game_build_is_one_build_358(self):
        sessions = three()
        sessions[2]["game_build"] = "cfg721feeb5"
        out = printed(judge(sessions, [verdict(criteria=stamp())]))
        self.assertNotIn("빌드 2개", out)
        self.assertNotIn("빌드 ", out.split("관찰한 근거")[1].split("\n")[0])

    def test_different_game_builds_still_show_358(self):
        sessions = three()
        sessions[0]["game_build"], sessions[1]["game_build"] = "cfgA", "cfgB"
        self.assertIn("빌드 3개(cfgA, cfgB, abc1234)", printed(judge(sessions, [verdict(criteria=stamp())])))   # 지문이 둘인 커밋의 지문 없는 세션은 따로 센다

    def test_different_commits_without_game_build_still_show_358(self):
        sessions = three()
        sessions[0]["build"] = "def5678"
        self.assertIn("빌드 2개(def5678, abc1234)", printed(judge(sessions, [verdict(criteria=stamp())])))


def changed_after_results(after=True):
    """test를 고친 이력이 하나 있는 컨셉. after가 None이면 after_results 칸을 두지 않는다."""
    data = copy.deepcopy(CONCEPTS)
    h = hyp(data)
    old_stamp, old_test = cc.criteria_stamp(h), h["test"]
    h["test"] = old_test + " 요약 값을 본 뒤에 한 판도 센다."
    entry = {"date": "2026-11-12", "stamp": old_stamp, "before": {"test": old_test}, "why": "사용자 결정(2026-11-12)"}
    if after is not None:
        entry["after_results"] = after
    h["criteria_history"] = [entry]
    return data


class AfterResults(unittest.TestCase):
    """361번: 결과를 본 뒤에 기준을 고쳤으면 이력에 적고, 그 기준으로 낸 판정 줄에 보인다. 막지는 않는다."""

    def test_the_verdict_line_names_the_change_361(self):
        data = changed_after_results()
        r = judge(three(), [verdict("refuted", criteria=stamp(data))], concepts=data)
        self.assertEqual(r["errors"], [])
        self.assertIn("결과 뒤 기준 고침 2026-11-12", printed(r))
        self.assertIn("결과 뒤 기준 고침 2026-11-12", r["verdicts"]["parry_tempo.learn_timing"]["sample_text"])   # 뷰어가 같은 글을 쓴다

    def test_an_ordinary_change_shows_nothing_361(self):
        for after in (None, False):
            with self.subTest(after=after):
                data = changed_after_results(after)
                self.assertNotIn("결과 뒤", printed(judge(three(), [verdict("refuted", criteria=stamp(data))], concepts=data)))

    def test_the_flag_is_a_boolean_361(self):
        r = cc.validate(changed_after_results("yes"))
        self.assertIn("criteria_history_invalid", codes(r["errors"]))
        self.assertEqual(cc.validate(changed_after_results())["errors"], [])

    def test_documented_361(self):
        self.assertIn("after_results", read(BRIEF))
        self.assertIn("after_results", read(CHANGES))


class Project:
    """임시 게임 프로젝트: 견본 컨셉과 플레이 기록."""

    def __init__(self, sessions, verdicts, concepts=None):
        self.dir = tempfile.TemporaryDirectory()
        root = Path(self.dir.name)
        (root / "design").mkdir()
        (root / "data").mkdir()
        (root / "design/concepts.json").write_text(json.dumps(concepts or CONCEPTS, ensure_ascii=False), encoding="utf-8")
        (root / "data/playtests.json").write_text(json.dumps({"playtests": sessions, "verdicts": verdicts}, ensure_ascii=False), encoding="utf-8")
        self.root = root

    def __enter__(self):
        return self.root

    def __exit__(self, *exc):
        self.dir.cleanup()


class HypothesisContext(unittest.TestCase):
    """362번: 가설 하나의 판정 자료만 모아 보이는 명령. 판정 에이전트가 기록 전체를 여러 번 읽지 않게 한다."""

    def setUp(self):
        data = changed_after_results()
        sessions = three()
        sessions[0]["observations"].append({"hypothesis": "other_hyp", "value": "다른 가설의 값", "n": 5})
        sessions[0]["notes"] = [{"kind": "deviation", "text": "설정 순서를 바꿈"},
                                {"kind": "observation", "hypotheses": ["other_hyp"], "text": "다른 가설의 메모"}]
        old = verdict("unknown", criteria="0000abcd", status="cut", reason="아주 긴 지난 판정 이유 " * 20,
                      cut_reason="2026-11-12 기준을 고쳐 다시 판정", next_needs="플레이 전에 사용자가 정한다")
        self.project = Project(sessions, [old, verdict("refuted", criteria=stamp(data))], data)
        self.root = self.project.__enter__()

    def tearDown(self):
        self.project.__exit__()

    def run_it(self, *extra):
        return run_cli("hypothesis", "parry_tempo.learn_timing", self.root, *extra)

    def test_it_shows_the_criteria_history_and_verdicts_362(self):
        code, out = self.run_it()
        self.assertEqual(code, 0, out)
        h = hyp(changed_after_results())
        for text in (h["claim"], h["failure_signal"], "요약 값을 본 뒤에 한 판도 센다", "2026-11-12", "결과 뒤",
                     "parry_tempo.learn_timing: 틀림 (제안)", "기준을 고쳐 다시 판정", "플레이 전에 사용자가 정한다", "피격률 40% → 15%"):
            self.assertIn(text, out)

    def test_it_leaves_out_other_hypotheses_and_old_reasons_362(self):
        _, out = self.run_it()
        self.assertNotIn("다른 가설의 값", out)
        self.assertNotIn("다른 가설의 메모", out)
        self.assertNotIn("아주 긴 지난 판정 이유", out)
        self.assertIn("설정 순서를 바꿈", out)   # 가설을 적지 않은 절차 이탈은 모든 가설에 든다

    def test_json_362(self):
        code, out = self.run_it("--json")
        self.assertEqual(code, 0)
        got = json.loads(out)
        self.assertEqual(got["where"], "parry_tempo.learn_timing")
        self.assertEqual([s["id"] for s in got["sessions"]], ["pt_a", "pt_b", "pt_c"])
        self.assertEqual([v["status"] for v in got["verdicts"]], ["cut", "proposed"])
        self.assertNotIn("reason", got["verdicts"][0])

    def test_an_unknown_target_names_the_choices_362(self):
        code, out = run_cli("hypothesis", "parry_tempo.nope", self.root)
        self.assertEqual(code, 2)
        code, out = run_cli("hypothesis", "nope", self.root)
        self.assertEqual(code, 2)

    def test_the_judge_may_run_it_362(self):
        self.assertTrue(claude._allowed_command("python3 .claude/skills/studio-data/scripts/studio.py hypothesis parry_tempo.learn_timing"))
        self.assertFalse(claude._allowed_command("python3 .claude/skills/studio-data/scripts/studio.py hypothesis x.y --out a.json"))

    def test_the_judge_reads_it_first_362(self):
        self.assertIn("studio.py hypothesis", read(JUDGE))
        self.assertIn("hypothesis <컨셉>.<가설>", read(VERDICT / "SKILL.md"))


class RecordSteps(unittest.TestCase):
    """359번·360번: 기록하기 전에 지난 판정이 남긴 플레이 전 결정을 확인한다. 새 제안을 받아들이지 않으면 지난 판정을 되돌린다."""

    def step(self, title):
        text = read(VERDICT / "SKILL.md")
        start = text.index(title)
        end = text.find("\n### ", start + 1)
        return text[start:end if end > 0 else None]

    def test_recording_checks_the_last_next_needs_359(self):
        text = self.step("### 2. 플레이한 뒤")
        self.assertIn("다음 시험 전에 풀 것", text)
        self.assertIn("deviation", text)

    def test_a_rejected_proposal_restores_the_last_verdict_360(self):
        text = self.step("### 3. 판정한다")
        self.assertIn("받아들이지 않으면", text)
        self.assertIn("cut_reason", text)


if __name__ == "__main__":
    unittest.main()


class ReviewFixes(unittest.TestCase):
    """357~362번 수정의 검토(2026-11-13) 9건."""

    def test_the_current_verdicts_evidence_is_shown_when_a_cut_entry_comes_last_1(self):
        data = changed_after_results()
        sessions = three() + [session("pt_old", date="2026-11-01")]
        old = verdict("unknown", sessions=("pt_old",), criteria="0000abcd", status="cut", cut_reason="2026-11-12 나중에 남긴 지난 판정")
        with Project(sessions, [verdict("refuted", criteria=stamp(data)), old], data) as root:
            got = json.loads(run_cli("hypothesis", "parry_tempo.learn_timing", root, "--json")[1])
        shown = {s["id"]: "observations" in s for s in got["sessions"]}
        self.assertEqual(shown, {"pt_a": True, "pt_b": True, "pt_c": True, "pt_old": True})   # 마지막 판정(pt_old)과 지금 판정의 근거 모두

    def test_a_session_only_an_older_verdict_used_is_a_header_line_1(self):
        sessions = three() + [session("pt_old", date="2026-11-01")]
        old = verdict("unknown", sessions=("pt_old",), criteria="0000abcd", status="cut", cut_reason="2026-11-12 다시 판정")
        with Project(sessions, [old, verdict("holds", criteria=stamp())]) as root:
            got = json.loads(run_cli("hypothesis", "parry_tempo.learn_timing", root, "--json")[1])
        self.assertTrue(next(s for s in got["sessions"] if s["id"] == "pt_old")["earlier"])

    def test_the_stamp_is_shown_for_a_concept_that_is_not_chosen_2(self):
        data = copy.deepcopy(CONCEPTS)
        want = stamp(data)
        next(x for x in data["concepts"] if x["status"] == "approved")["status"] = "proposed"
        with Project(three(), [], data) as root:
            code, out = run_cli("hypothesis", "parry_tempo.learn_timing", root)
        self.assertEqual(code, 0)
        self.assertIn(f"판정 기준 지문(지금): {want}", out)

    def test_the_after_results_tag_needs_a_session_from_before_the_change_3(self):
        data = changed_after_results()
        later = three(date="2026-11-13")
        self.assertNotIn("결과 뒤", printed(judge(later, [verdict("refuted", criteria=stamp(data))], concepts=data)))
        same_day = three(date="2026-11-12")
        self.assertIn("결과 뒤 기준 고침 2026-11-12", printed(judge(same_day, [verdict("refuted", criteria=stamp(data))], concepts=data)))

    def test_the_after_results_rule_lives_in_one_place_4(self):
        self.assertNotIn("본 뒤에 고쳤으면", read(BRIEF))
        self.assertIn("after_results", read(BRIEF))   # 칸 이름과 링크만 둔다

    def test_the_status_to_restore_is_in_the_cut_reason_5(self):
        text = read(VERDICT / "SKILL.md")
        self.assertNotIn("`cut` 전 값", text)
        self.assertIn("cut_reason에 그때 상태", text)

    def test_keep_unknown_drops_yardstick_tags_6(self):
        data = events_concepts()
        v = verdict("unknown", criteria=stamp(data), keep_unknown="사용자 결정(2026-11-12): 사건 6건 [가정]이 안 나와 모름으로 둔다")
        out = printed(judge(three(), [v], concepts=data))
        self.assertIn("사건 6건이 안 나와", out)
        self.assertNotIn("[가정]", out)

    def test_an_untagged_session_is_folded_in_only_when_its_commit_has_one_game_build_7(self):
        sessions = three()
        sessions[0]["game_build"], sessions[1]["game_build"] = "cfgA", "cfgB"
        self.assertIn("빌드 3개(cfgA, cfgB, abc1234)", printed(judge(sessions, [verdict(criteria=stamp())])))
        self.assertIn("같은 커밋", read(RECORD))

    def test_a_broken_concepts_file_is_not_called_missing_8(self):
        with Project(three(), []) as root:
            (root / "design/concepts.json").write_text("{ broken", encoding="utf-8")
            from _studio import cli
            import io
            from contextlib import redirect_stderr, redirect_stdout
            err = io.StringIO()
            with redirect_stdout(io.StringIO()), redirect_stderr(err):
                code = cli.main(["hypothesis", "parry_tempo.learn_timing", str(root)])
        self.assertEqual(code, 2)
        self.assertIn("읽지 못했습니다", err.getvalue())
        self.assertNotIn("찾지 못했습니다", err.getvalue())

    def test_the_choices_come_from_the_index_9(self):
        import io
        from contextlib import redirect_stderr, redirect_stdout
        from _studio import cli
        with Project(three(), []) as root:
            err = io.StringIO()
            with redirect_stdout(io.StringIO()), redirect_stderr(err):
                cli.main(["hypothesis", "parry_tempo.nope", str(root)])
        self.assertIn("parry_tempo.learn_timing", err.getvalue())
