"""완성 단계(2026-11-22): 판정 데이터 지문(data), 봇 회귀 뒤 이어 감(carried), 새 스킬 production-milestones. 표준 라이브러리 unittest만 사용한다."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from _studio import ROOT, cli, concepts as cc, playtests as pt, run_cli
from test_verdict_field import CONCEPTS, approved, codes, hyp, printed, stamp, three, verdict

WHERE = "parry_tempo.learn_timing"
SKILL = ROOT / "skills/production-milestones"
RECORD = ROOT / "skills/playtest-verdict/references/playtest-record.md"


def read(path):
    return Path(path).read_text(encoding="utf-8")


class Game:
    """임시 게임 프로젝트: 견본 컨셉, 게임 데이터 파일, 플레이 기록."""

    def __init__(self, verdicts=(), files=None, concepts=None, sessions=None):
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        (self.root / "design").mkdir()
        (self.root / "data").mkdir()
        self.concepts = copy.deepcopy(concepts or CONCEPTS)
        self.write_concepts()
        for rel, body in (files if files is not None else {"data/cards.json": {"items": [{"id": "strike", "dmg": 6}]}}).items():
            self.put(rel, body)
        self.record(list(verdicts), sessions)

    def put(self, rel, body):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body if isinstance(body, str) else json.dumps(body, ensure_ascii=False), encoding="utf-8")

    def write_concepts(self):
        self.put("design/concepts.json", self.concepts)

    def record(self, verdicts, sessions=None):
        self.put("data/playtests.json", {"playtests": sessions or three(), "verdicts": verdicts})

    def stamp(self, depends_on=None):
        return cc.data_stamp(self.root, depends_on)

    def played(self, extra=()):
        """플레이한 세션: 기록할 때의 게임 데이터 지문을 적는다."""
        return [dict(x, data=cc.data_digests(self.root, extra)) for x in three()]

    def report(self):
        index = cc.hypothesis_index(self.concepts, root=self.root)
        data = json.loads(read(self.root / "data/playtests.json"))
        return pt.validate(data, index, root=self.root)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.dir.cleanup()


def holds(**over):
    return verdict("holds", criteria=stamp(), status="approved", **over)


class DataStamp(unittest.TestCase):
    """판정할 때의 게임 데이터 지문. 값이 바뀌어야 바뀐다."""

    def test_only_values_change_the_stamp(self):
        with Game() as g:
            first = g.stamp()
            self.assertRegex(first, r"^[0-9a-f]{8}$")
            g.put("data/cards.json", '{\n  "_note": "새 메모",\n  "items": [ {"dmg": 6, "id": "strike", "note": "메모",'
                                     ' "provenance": {"kind": "measured", "source": "data/playtests.json#pt_a"}, "acknowledged": {"x": "이유"}} ]\n}')
            self.assertEqual(g.stamp(), first)   # 띄어쓰기, 키 순서, 메모, 출처, 확인은 값이 아니다
            g.put("data/cards.json", {"items": [{"id": "strike", "dmg": 7}]})
            self.assertNotEqual(g.stamp(), first)

    def test_adding_content_changes_it(self):
        with Game() as g:
            first = g.stamp()
            g.put("data/enemies.json", {"enemies": [{"id": "toad", "hp": 30}]})
            self.assertNotEqual(g.stamp(), first)

    def test_play_records_are_not_game_data(self):
        with Game() as g:
            first = g.stamp()
            g.record([holds()])
            self.assertEqual(g.stamp(), first)

    def test_csv_provenance_columns_are_not_values(self):
        with Game(files={"data/items.csv": "id,stat.atk,provenance_kind\nsword,5,assumed\n"}) as g:
            first = g.stamp()
            g.put("data/items.csv", "id,stat.atk,provenance_kind\r\nsword,5,measured\r\n")
            self.assertEqual(g.stamp(), first)
            g.put("data/items.csv", "id,stat.atk,provenance_kind\nsword,6,measured\n")
            self.assertNotEqual(g.stamp(), first)

    def test_no_game_data_has_no_stamp(self):
        with Game(files={}) as g:
            self.assertIsNone(g.stamp())

    def test_depends_on_narrows_the_files(self):
        with Game(files={"data/cards.json": {"items": [{"id": "a"}]}, "data/enemies.json": {"enemies": [{"id": "e"}]}}) as g:
            first = g.stamp(["data/cards.json"])
            g.put("data/enemies.json", {"enemies": [{"id": "e", "hp": 3}]})
            self.assertEqual(g.stamp(["data/cards.json"]), first)
            self.assertNotEqual(g.stamp(), cc.data_stamp(g.root, ["data/cards.json"]))

    def test_depends_on_can_name_rule_code(self):
        """규칙 코드도 적을 수 있다. 이름을 적은 파일은 바이트로 본다."""
        with Game(files={"data/cards.json": {"items": []}, "game/src/rules.ts": "export const DRAW = 5\n"}) as g:
            deps = ["data/cards.json", "game/src/rules.ts"]
            first = g.stamp(deps)
            g.put("game/src/rules.ts", "export const DRAW = 4\n")
            self.assertNotEqual(g.stamp(deps), first)


class DataGate(unittest.TestCase):
    """버팀 판정에 데이터 지문이 없거나 판정 뒤 데이터가 바뀌면 게이트를 넘지 못한다."""

    def test_a_current_stamp_passes(self):
        with Game() as g:
            g.record([holds(data=g.stamp())], g.played())
            r = g.report()
        self.assertEqual(r["errors"], [])
        self.assertNotIn(WHERE, r["unverified"])
        self.assertNotIn("verdict_data_changed", codes(r["warnings"]))

    def test_changed_data_blocks_the_gate(self):
        with Game() as g:
            g.record([holds(data=g.stamp())], g.played())
            g.put("data/cards.json", {"items": [{"id": "strike", "dmg": 6}, {"id": "bash", "dmg": 9}]})
            now = g.stamp()
            r = g.report()
        self.assertIn(WHERE, r["unverified"])
        self.assertEqual(r["unverified_reasons"][WHERE], "데이터 바뀜")
        w = next(w for w in r["warnings"] if w["code"] == "verdict_data_changed")
        self.assertIn(now, w["message"])
        self.assertIn("production-milestones", w["message"])

    def test_a_missing_stamp_blocks_the_gate(self):
        with Game() as g:
            g.record([holds()])
            now = g.stamp()
            r = g.report()
        self.assertIn(WHERE, r["unverified"])
        self.assertEqual(r["unverified_reasons"][WHERE], "데이터 지문 없음")
        w = next(w for w in r["warnings"] if w["code"] == "verdict_data_missing")
        self.assertIn(now, w["message"])
        self.assertIn("git diff", w["message"])   # 판정 뒤 데이터를 바꾸지 않았는지 확인하는 법

    def test_projects_without_game_data_are_not_asked(self):
        with Game(files={}) as g:
            g.record([holds()])
            r = g.report()
        self.assertNotIn(WHERE, r["unverified"])
        self.assertFalse({"verdict_data_missing", "verdict_data_changed"} & set(codes(r["warnings"])))

    def test_unknown_and_refuted_are_not_stamped(self):
        with Game() as g:
            g.record([verdict("unknown", criteria=stamp(), status="approved")])
            unknown = g.report()
            g.record([verdict("refuted", criteria=stamp(), status="approved")])
            refuted = g.report()
        for r in (unknown, refuted):
            self.assertFalse({"verdict_data_missing", "verdict_data_changed"} & set(codes(r["warnings"])))

    def test_the_stamp_shape_is_checked(self):
        with Game() as g:
            g.record([holds(data="xyz")])
            r = g.report()
        self.assertIn("schema", codes(r["errors"]))

    def test_criteria_and_data_reasons_are_joined(self):
        with Game() as g:
            g.record([verdict("holds", status="approved")])
            r = g.report()
        self.assertEqual(r["unverified_reasons"][WHERE], "지문 없음, 데이터 지문 없음")

    def test_depends_on_keeps_unrelated_changes_out(self):
        with Game(files={"data/cards.json": {"items": [{"id": "a"}]}, "data/sound.json": {"volume": 1}}) as g:
            hyp(g.concepts)["depends_on"] = ["data/cards.json"]
            g.write_concepts()
            g.record([verdict("holds", criteria=stamp(g.concepts), status="approved", data=g.stamp(["data/cards.json"]))], g.played())
            g.put("data/sound.json", {"volume": 0.5})
            r = g.report()
        self.assertEqual(r["errors"], [])
        self.assertNotIn(WHERE, r["unverified"])

    def test_a_prototype_verdict_with_a_main_recheck_is_left_to_it(self):
        """본 게임으로 넘어간 뒤 지금 데이터는 다시 확인 가설(<id>_main)의 판정이 본다. 원래 가설의 판정은 시험판 빌드의 기록이다."""
        with Game() as g:
            main = copy.deepcopy(hyp(g.concepts))
            main["id"] = "learn_timing_main"
            approved(g.concepts)["brief"]["hypotheses"].append(main)
            g.write_concepts()
            g.record([holds(data="0000abcd")])
            r = g.report()
        self.assertNotIn("verdict_data_changed", codes(r["warnings"]))
        self.assertNotEqual(r["unverified_reasons"].get(WHERE), "데이터 바뀜")

    def test_check_shows_the_gate_reason(self):
        with Game() as g:
            g.record([holds(data="0000abcd")])
            code, out = run_cli("check", g.root, "--fail-on-assumed")
        self.assertEqual(code, 1, out)
        self.assertIn(f"{WHERE}(플레이 때 지문 없음, 데이터 바뀜)", out)   # 둘 다 걸리면 둘 다 보인다


class DependsOn(unittest.TestCase):
    def test_it_is_a_list_of_project_files(self):
        for bad in ("data/cards.json", [], [1], ["../outside.json"], ["data/none.json"]):
            with self.subTest(bad=bad), Game() as g:
                hyp(g.concepts)["depends_on"] = bad
                r = cc.validate(g.concepts, root=g.root)
                self.assertTrue(any("depends_on" in e["message"] for e in r["errors"]), r["errors"])

    def test_a_good_list_passes(self):
        with Game() as g:
            hyp(g.concepts)["depends_on"] = ["data/cards.json"]
            r = cc.validate(g.concepts, root=g.root)
        self.assertFalse(any("depends_on" in e["message"] for e in r["errors"]), r["errors"])

    def test_it_is_not_a_criterion(self):
        """기대는 파일을 고쳐도 판정 기준은 그대로다. 좁히면 지문이 달라져 데이터 쪽이 알린다."""
        h = copy.deepcopy(hyp(CONCEPTS))
        before = cc.criteria_stamp(h)
        h["depends_on"] = ["data/cards.json"]
        self.assertEqual(cc.criteria_stamp(h), before)


def carried_pair(g, origin_data, **over):
    """사람이 플레이한 판정(cut)과, 봇 회귀 뒤 이어 간 판정."""
    origin = verdict("holds", criteria=stamp(), status="cut", data=origin_data, cut_reason="2026-11-30 콘텐츠를 더해 이어 감")
    carry = {"from": origin_data, "regression": "playtests/regression_1/result.json"}
    carry.update(over.pop("carried", {}))
    return [origin, holds(data=g.stamp(), carried=carry, **over)]


class Carried(unittest.TestCase):
    """낡은 버팀 판정은 같은 시드·같은 봇의 회귀 결과를 보고 사용자가 이어 가기로 정할 수 있다. 근거는 사람이 플레이한 판정 그대로다."""

    def setUp(self):
        self.game = Game()
        self.origin_data = self.game.stamp()
        self.sessions = self.game.played()   # 사람은 앞 데이터에서 플레이했다
        self.game.put("data/cards.json", {"items": [{"id": "strike", "dmg": 6}, {"id": "bash", "dmg": 9}]})
        self.game.put("playtests/regression_1/result.json", {"before": 12.8, "after": 12.1})

    def tearDown(self):
        self.game.dir.cleanup()

    def report(self, verdicts):
        self.game.record(verdicts, self.sessions)
        return self.game.report()

    def test_a_carried_verdict_passes(self):
        r = self.report(carried_pair(self.game, self.origin_data))
        self.assertEqual(r["errors"], [])
        self.assertNotIn(WHERE, r["unverified"])
        self.assertIn("이어 감", printed(r))

    def test_it_must_come_from_a_played_verdict(self):
        r = self.report(carried_pair(self.game, self.origin_data, carried={"from": "0000abcd"}))
        self.assertIn("carried_from_unknown", codes(r["errors"]))

    def test_a_carried_verdict_is_not_an_origin(self):
        """두 번째 이어 감도 사람이 플레이한 판정의 지문에서 잰다(회귀가 조금씩 쌓여 멀어지지 않게)."""
        pair = carried_pair(self.game, self.origin_data)
        middle = dict(pair[1], status="cut", cut_reason="2026-12-02 콘텐츠를 더 더함", data="1111abcd")
        r = self.report([pair[0], middle, holds(data=self.game.stamp(), carried={"from": "1111abcd", "regression": "playtests/regression_1/result.json"})])
        self.assertIn("carried_from_unknown", codes(r["errors"]))
        r = self.report([pair[0], middle, holds(data=self.game.stamp(), carried={"from": self.origin_data, "regression": "playtests/regression_1/result.json"})])
        self.assertEqual(r["errors"], [])

    def test_the_regression_file_must_exist(self):
        r = self.report(carried_pair(self.game, self.origin_data, carried={"regression": "playtests/none.json"}))
        self.assertIn("carried_regression_missing", codes(r["errors"]))

    def test_it_keeps_the_played_evidence(self):
        r = self.report(carried_pair(self.game, self.origin_data, sessions=["pt_a", "pt_b"]))
        self.assertIn("carried_evidence_differs", codes(r["errors"]))

    def test_only_holds_is_carried(self):
        pair = carried_pair(self.game, self.origin_data)
        pair[1]["result"] = "unknown"
        r = self.report(pair)
        self.assertTrue(any("carried" in e["message"] for e in r["errors"] if e["code"] == "schema"), r["errors"])

    def test_the_carried_shape_is_checked(self):
        for bad in ("abc", {"from": "zz"}, {"from": self.origin_data}, {"from": self.origin_data, "regression": ""}):
            with self.subTest(bad=bad):
                pair = carried_pair(self.game, self.origin_data)
                pair[1]["carried"] = bad
                r = self.report(pair)
                self.assertIn("schema", codes(r["errors"]))

    def test_two_played_verdicts_on_the_same_data(self):
        """검토 6: 같은 데이터에서 사람이 판정한 것이 둘이면 어느 쪽에서든 이어 갈 수 있다."""
        older = verdict("holds", sessions=["pt_a", "pt_b"], criteria=stamp(), status="cut", data=self.origin_data, cut_reason="세션을 더해 다시 판정")
        pair = carried_pair(self.game, self.origin_data)
        r = self.report([pair[0], older, pair[1]])
        self.assertEqual(r["errors"], [])

    def test_carried_sessions_must_be_played_on_the_origin_data(self):
        self.sessions = [dict(x, data={"data/cards.json": "0000abcd"}) for x in self.sessions]
        r = self.report(carried_pair(self.game, self.origin_data))
        self.assertIn("verdict_data_not_played", codes(r["errors"]))

    def test_carrying_does_not_skip_the_data_check(self):
        """이어 간 판정도 그 뒤 데이터가 또 바뀌면 낡는다."""
        pair = carried_pair(self.game, self.origin_data)
        self.game.put("data/cards.json", {"items": [{"id": "strike", "dmg": 5}]})
        r = self.report(pair)
        self.assertEqual(r["unverified_reasons"][WHERE], "데이터 바뀜")


class PlayedData(unittest.TestCase):
    """검토 1: 판정의 데이터 지문은 사람이 플레이한 때의 데이터여야 한다. 세션이 기록할 때의 지문을 남긴다."""

    def test_a_verdict_stamped_after_a_data_edit_is_an_error(self):
        with Game() as g:
            sessions = g.played()
            g.put("data/cards.json", {"items": [{"id": "strike", "dmg": 9}]})   # 플레이한 뒤, 판정 전에 고침
            g.record([holds(data=g.stamp())], sessions)
            r = g.report()
        self.assertIn("verdict_data_not_played", codes(r["errors"]))

    def test_sessions_without_a_stamp_keep_the_verdict_out_of_the_gate(self):
        with Game() as g:
            g.record([holds(data=g.stamp())])
            r = g.report()
        self.assertEqual(r["unverified_reasons"][WHERE], "플레이 때 지문 없음")
        self.assertIn("session_data_missing", codes(r["warnings"]))

    def test_the_latest_session_decides(self):
        """세션 사이에 데이터가 바뀌었으면 판정의 지문은 마지막 세션의 데이터다."""
        with Game() as g:
            early = g.played()[:2]
            g.put("data/cards.json", {"items": [{"id": "strike", "dmg": 7}]})
            late = [dict(three()[2], data=cc.data_digests(g.root), date="2026-11-09")]
            g.record([holds(data=g.stamp())], early + late)
            r = g.report()
        self.assertEqual(r["errors"], [])
        self.assertNotIn(WHERE, r["unverified"])

    def test_depends_on_reads_its_files_from_the_session(self):
        with Game(files={"data/cards.json": {"items": []}, "game/rules.ts": "const A = 1\n"}) as g:
            deps = ["data/cards.json", "game/rules.ts"]
            hyp(g.concepts)["depends_on"] = deps
            g.write_concepts()
            g.record([verdict("holds", criteria=stamp(g.concepts), status="approved", data=g.stamp(deps))], g.played(deps))
            ok = g.report()
            g.record([verdict("holds", criteria=stamp(g.concepts), status="approved", data=g.stamp(deps))], g.played())   # 세션에 규칙 파일이 없다
            short = g.report()
        self.assertEqual(ok["errors"], [])
        self.assertIn("verdict_data_not_played", codes(short["errors"]))

    def test_the_session_stamp_shape_is_checked(self):
        for bad in ("abcd1234", {"data/cards.json": "zz"}, {"": "abcd1234"}):
            with self.subTest(bad=bad), Game() as g:
                g.record([], [dict(x, data=bad) for x in three()])
                self.assertIn("schema", codes(g.report()["errors"]))

    def test_check_prints_what_a_session_records(self):
        with Game(files={"data/cards.json": {"items": []}, "game/rules.ts": "x\n"}) as g:
            hyp(g.concepts)["depends_on"] = ["data/cards.json", "game/rules.ts"]
            g.write_concepts()
            code, out = run_cli("check", g.root)
            want = cc.data_digests(g.root, ["game/rules.ts"])
        self.assertIn("세션에 적을 게임 데이터 지문: " + json.dumps(want, ensure_ascii=False, sort_keys=True), out)


class StudioFilesAreNotGameData(unittest.TestCase):
    """검토 2: data/에 둔 컨셉·시스템 설계·플레이 기록은 게임 데이터가 아니다."""

    def test_design_files_in_data_are_left_out(self):
        with Game() as g:
            first = g.stamp()
            g.put("data/concepts.json", g.concepts)
            g.put("data/systems.json", {"concept": "parry_tempo", "systems": [{"id": "s", "scope": "mvp"}]})
            g.put("data/old_playtests.json", {"playtests": [], "verdicts": []})
            self.assertEqual(g.stamp(), first)

    def test_a_game_file_named_systems_is_game_data(self):
        with Game() as g:
            first = g.stamp()
            g.put("data/systems.json", {"systems": {"gravity": 9.8}})   # 엔진 설정(이 도구의 형식이 아니다)
            self.assertNotEqual(g.stamp(), first)


class DependsOnPaths(unittest.TestCase):
    """검토 3: 검사가 받아들인 경로 그대로 지문을 낸다."""

    def test_backslash_and_dot_paths_see_the_file(self):
        for rel in ("data\\cards.json", "./data/cards.json", "data//cards.json"):
            with self.subTest(rel=rel), Game() as g:
                first = g.stamp([rel])
                self.assertEqual(first, g.stamp(["data/cards.json"]))
                g.put("data/cards.json", {"items": [{"id": "strike", "dmg": 8}]})
                self.assertNotEqual(g.stamp([rel]), first)

    def test_a_bad_list_shows_no_stamp_in_hypothesis(self):
        """검토 5: 틀린 depends_on이면 hypothesis가 지문을 보이지 않는다(판정 에이전트가 옮겨 적지 않게)."""
        with Game() as g:
            hyp(g.concepts)["depends_on"] = "data/cards.json"
            g.write_concepts()
            code, out = run_cli("hypothesis", WHERE, g.root)
        line = next(l for l in out.splitlines() if l.startswith("데이터 지문(지금)"))
        self.assertNotRegex(line, r"[0-9a-f]{8}")
        self.assertIn("depends_on", line)


class Outputs(unittest.TestCase):
    def test_hypothesis_shows_the_current_stamp_and_files(self):
        with Game() as g:
            g.record([holds()])
            code, out = run_cli("hypothesis", WHERE, g.root)
            now = g.stamp()
        self.assertEqual(code, 0, out)
        self.assertIn(f"데이터 지문(지금): {now} (data/cards.json)", out)

    def test_check_prints_data_stamps_with_the_criteria(self):
        with Game() as g:
            code, out = run_cli("check", g.root)
            now = g.stamp()
        self.assertIn(f"버팀으로 판정할 때 적을 데이터 지문: {WHERE} {now}", out)


class StampLineShowsCheckedHypotheses(unittest.TestCase):
    """394: 지문 줄은 지문을 보는 가설만 보인다. <id>_main이 있는 원래 가설은 지금 데이터를 _main 판정이 본다."""

    def setUp(self):
        self.game = Game()
        main = copy.deepcopy(hyp(self.game.concepts))
        main["id"] = "learn_timing_main"
        approved(self.game.concepts)["brief"]["hypotheses"].append(main)
        self.game.write_concepts()

    def tearDown(self):
        self.game.dir.cleanup()

    def test_check_leaves_out_the_original(self):
        code, out = run_cli("check", self.game.root)
        line = next(l for l in out.splitlines() if l.startswith("버팀으로 판정할 때 적을 데이터 지문:"))
        self.assertIn("parry_tempo.learn_timing_main", line)
        self.assertNotIn("parry_tempo.learn_timing ", line + " ")
        self.assertIn("parry_tempo.tempo_choice", line)

    def test_hypothesis_says_the_original_is_not_stamped(self):
        code, out = run_cli("hypothesis", WHERE, self.game.root)
        line = next(l for l in out.splitlines() if l.startswith("데이터 지문(지금)"))
        self.assertNotRegex(line, r"[0-9a-f]{8}")
        self.assertIn("learn_timing_main", line)


    def test_one_rule_decides_all_three(self):
        """394 검토 2: 지문 줄, 게이트, hypothesis가 같은 함수(concepts.rechecked)로 원래 가설을 뺀다."""
        from unittest import mock
        self.game.record([holds(data="0000abcd")], self.game.played())
        with mock.patch.object(cc, "rechecked", return_value=False):
            code, out = run_cli("check", self.game.root)
            r = self.game.report()
            hcode, hout = run_cli("hypothesis", WHERE, self.game.root)
        line = next(l for l in out.splitlines() if l.startswith("버팀으로 판정할 때 적을 데이터 지문:"))
        self.assertIn("parry_tempo.learn_timing ", line + " ")
        self.assertIn("verdict_data_changed", codes(r["warnings"]))
        self.assertRegex(next(l for l in hout.splitlines() if l.startswith("데이터 지문(지금)")), r"[0-9a-f]{8}")

    def test_rechecked(self):
        self.assertTrue(cc.rechecked({"a", "a_main"}, "a"))
        self.assertFalse(cc.rechecked({"a"}, "a"))
        self.assertFalse(cc.rechecked({"a_main"}, "a_main"))


class Docs(unittest.TestCase):
    def test_the_judge_leaves_data_out_when_not_stamped(self):
        """394 검토 1: hypothesis가 '보지 않음'이면 판정 에이전트는 data를 넣지 않는다."""
        text = read(ROOT / "skills/studio-data/assets/claude/studio-judge.md")
        self.assertIn("보지 않음", text)

    def test_the_skill_is_installed_like_the_others(self):
        text = read(SKILL / "SKILL.md")
        head = text.split("---")[1]
        self.assertIn("name: production-milestones", head)
        self.assertIn("\nlicense: MIT\n", head)
        self.assertTrue(head.split("description:")[1].strip().strip('"').startswith("Guides"))
        self.assertEqual(read(SKILL / "LICENSE"), read(ROOT / "LICENSE"))
        self.assertTrue((SKILL / "agents/openai.yaml").is_file())
        self.assertLess(len(text.encode("utf-8")), 20000)

    def test_the_skill_has_three_milestones_and_the_release_gate(self):
        text = read(SKILL / "SKILL.md")
        for word in ("알파", "베타", "출시 후보", "콘텐츠 동결"):
            self.assertIn(word, text)
        for ref in ("content-growth.md", "release-gate.md", "milestone-record.md"):
            self.assertTrue((SKILL / "references" / ref).is_file(), ref)
            self.assertIn(f"references/{ref}", text)

    def test_the_release_gate_has_free_and_sale_parts(self):
        text = read(SKILL / "references/release-gate.md")
        self.assertIn("## 무료 공개", text)
        self.assertIn("## 판매할 때 더하는 것", text)
        self.assertIn("[?]", text)   # 확인하지 못한 줄은 통과가 아니다

    def test_content_growth_never_lets_bots_decide_alone(self):
        text = read(SKILL / "references/content-growth.md")
        self.assertIn("같은 시드", text)
        self.assertIn("carried", text)
        self.assertIn("사람이 마지막으로 플레이한", text)

    def test_production_handoff_points_to_it(self):
        text = read(ROOT / "skills/production-handoff/SKILL.md")
        step = text[text.index("### 8. 넘어가기 판정을 적는다"):]
        self.assertIn("(../production-milestones/SKILL.md)", step[:step.index("- **되돌아가기:**")])

    def test_the_record_format_names_the_new_fields_and_codes(self):
        text = read(RECORD)
        verdicts = text[text.index("## 판정 (`verdicts`)"):text.index("### 구조화한 자기 보고")]
        self.assertIn("| `data` |", verdicts)
        self.assertIn("| `carried` |", verdicts)
        codes_table = text[text.index("## 검사 내용"):]
        for code in ("verdict_data_missing", "verdict_data_changed", "carried_from_unknown", "carried_regression_missing", "carried_evidence_differs"):
            self.assertIn(f"`{code}`", codes_table)

    def test_depends_on_is_documented_with_the_other_hypothesis_fields(self):
        text = read(ROOT / "skills/concept-exploration/references/brief.md")
        self.assertIn("`depends_on`", text)

    def test_the_file_set_and_exceptions_live_in_one_place(self):
        """검토 7: 지문이 보는 파일은 기록 형식의 data 줄에만, 경고의 예외는 검사 표에만 적는다."""
        row = next(l for l in read(ROOT / "skills/concept-exploration/references/brief.md").splitlines() if l.startswith("| `depends_on`"))
        self.assertNotIn("바로 아래", row)
        self.assertNotIn("JSON·CSV", read(SKILL / "SKILL.md"))
        text = read(RECORD)
        data_row = next(l for l in text.splitlines() if l.startswith("| `data` |"))
        self.assertNotIn("선택하지 않은 컨셉", data_row)
        missing_row = next(l for l in text.splitlines() if l.startswith("| `verdict_data_missing` |"))
        self.assertIn("_main", missing_row)
        self.assertIn("| `verdict_data_not_played` |", text)
        self.assertIn("| `session_data_missing` |", text)
        session_rows = text[text.index("## 세션 (`playtests`)"):text.index("## 판정 (`verdicts`)")]
        self.assertIn("| `data` |", session_rows)

    def test_backfill_starts_from_the_earliest_session(self):
        """검토 4: 지문을 나중에 적을 때는 가장 이른 근거 세션의 커밋부터 본다."""
        text = read(SKILL / "references/content-growth.md")
        part = text[text.index("## 지문 없는 판정"):text.index("## 낡은 판정 풀기")]
        self.assertIn("가장 이른", part)
        self.assertNotIn("가장 늦은", part)
        self.assertIn("세션", part)

    def test_counts_name_a_way_for_game_specific_files(self):
        """검토 8: check가 개수를 보이지 않는 게임 고유 파일은 게임 쪽 스크립트로 센다."""
        text = read(SKILL / "SKILL.md")
        step = text[text.index("### 2. 콘텐츠를 늘린다"):text.index("### 3.")]
        self.assertIn("게임 쪽 스크립트", step)

    def test_readme_and_roadmap(self):
        self.assertIn("production-milestones", read(ROOT / "README.md"))
        arch = read(ROOT / "docs/architecture.md")
        roadmap = arch[arch.index("## 로드맵"):arch.index("### 3단계")]
        self.assertIn("production-milestones", roadmap)
        art = next(l for l in roadmap.splitlines() if "art-handoff" in l)
        self.assertNotIn("현장 시험 전", art)
        self.assertTrue((ROOT / "docs/research/release-2026-11.md").is_file())


if __name__ == "__main__":
    unittest.main()
