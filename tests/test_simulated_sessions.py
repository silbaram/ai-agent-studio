"""사람이 하지 않은 플레이 세션(352번): 자동 플레이 봇의 세션은 표본에 세지 않고 버팀·틀림의 근거가 되지 못한다. 표준 라이브러리 unittest만 사용한다."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from _studio import ROOT, SAMPLE, calibrate as cal, datasets, playtests as pt, provenance as cp
from test_playtests import codes, session, validate, verdict


class Verdicts(unittest.TestCase):
    def test_a_simulated_session_cannot_back_a_decided_verdict(self):
        for result in ("holds", "refuted"):
            with self.subTest(result):
                r = validate([session(simulated=True)], [verdict(result=result)])
                self.assertIn("verdict_simulated_session", codes(r["errors"]))

    def test_it_can_be_cited_by_an_unknown_verdict(self):
        r = validate([session(simulated=True)], [verdict(result="unknown")])
        self.assertNotIn("verdict_simulated_session", codes(r["errors"]))

    def test_it_is_not_counted_in_the_sample(self):
        r = validate([session(simulated=True), session("pt_b", players=["friend_c"], runs=4)], [verdict(result="unknown", sessions=["pt_a", "pt_b"])])
        got = r["verdicts"]["parry_tempo.learn_timing"]
        self.assertEqual(got["sample"], {"sessions": 1, "runs": 4, "players": 1})
        self.assertIn("자동 플레이 세션 1개 뺌", got["sample_text"])

    def test_the_value_must_be_true_or_false(self):
        errors = validate([session(simulated="yes")], [])["errors"]
        self.assertTrue(any(e["code"] == "schema" and "simulated" in e["message"] and "true" in e["message"] for e in errors), errors)

    def test_one_cause_gives_one_error(self):
        r = validate([session(simulated=True)], [verdict()])
        self.assertEqual(codes(r["errors"]), ["verdict_simulated_session"])   # 표본·사건 부족을 따로 알리지 않는다

    def test_false_is_a_human_session(self):
        r = validate([session(simulated=False)], [verdict()])
        self.assertNotIn("verdict_simulated_session", codes(r["errors"]))


class OtherReaders(unittest.TestCase):
    """측정 태그, 그레이박스 확인, 단계 기록도 사람의 플레이만 쓴다."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        data = json.loads((SAMPLE / "data/playtests.json").read_text(encoding="utf-8"))
        data["playtests"].append({"id": "pt_bot", "date": "2026-11-12", "concept": "parry_tempo", "build": "abc", "players": ["bot"], "runs": 3,
                                  "simulated": True, "greybox": [{"check": "g_bot", "passed": True}],
                                  "stage_stats": [{"stage": "zone_9", "entered": 3, "cleared": 3}]})
        (self.dir / "playtests.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        self.entries = [{"ok": True, "kind": "playtests", "data": data}]

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_measured_tag_cannot_cite_a_simulated_session(self):
        r = cp.check_text("턴 차이 3 [측정: playtests.json#pt_bot]\n", "doc.md", [self.dir], check_paths=True)
        msgs = [f.message for f in r.findings if f.level == "error"]
        self.assertEqual(len(msgs), 1, msgs)
        self.assertIn("simulated", msgs[0])
        self.assertIn("[계산", msgs[0])

    def test_greybox_records_skip_simulated_sessions(self):
        self.assertNotIn("g_bot", datasets._greybox_log(self.entries))

    def test_played_stages_skip_simulated_sessions(self):
        self.assertNotIn("zone_9", datasets._played_stages(self.entries))


class Calibration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "game"
        shutil.copytree(SAMPLE, self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def sessions(self, *new):
        p = self.root / "data/playtests.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        d["playtests"] = [x for x in d["playtests"] if "stage_stats" not in x and "groups" not in x] + list(new)
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")

    def rec(self, sid, **over):
        s = {"id": sid, "date": "2026-11-12", "concept": "parry_tempo", "build": "abc", "players": ["p"], "runs": 10, "upgrades": [],
             "stage_stats": [{"stage": "zone_2", "entered": 10, "cleared": 10, "level": 4, "duration": 300}]}
        s.update(over)
        return s

    def test_simulated_sessions_are_left_out_unless_chosen(self):
        self.sessions(self.rec("human"), self.rec("bot", simulated=True, stage_stats=[{"stage": "zone_2", "entered": 10, "cleared": 10, "level": 9, "duration": 300}]))
        r = cal.calibrate(self.root)
        level = next(x for x in r["compare"] if x["kind"] == "level" and x["stage"] == "zone_2")
        self.assertEqual(level["measured"], 4)
        self.assertTrue(any("자동 플레이" in n and "bot" in n for n in r["notes"]), r["notes"])
        chosen = cal.calibrate(self.root, sessions=["bot"])
        self.assertEqual(next(x for x in chosen["compare"] if x["kind"] == "level" and x["stage"] == "zone_2")["measured"], 9)

    def test_only_simulated_sessions_is_refused(self):
        self.sessions(self.rec("bot", simulated=True))
        with self.assertRaisesRegex(cal.ConfigError, "사람"):
            cal.calibrate(self.root)


class Docs(unittest.TestCase):
    def test_the_record_format_names_the_key(self):
        text = (ROOT / "skills/playtest-verdict/references/playtest-record.md").read_text(encoding="utf-8")
        self.assertIn("`simulated`", text)
        self.assertIn("`verdict_simulated_session`", text)
        row = next(x for x in text.splitlines() if x.startswith("| `simulated` |"))
        for words in ("그레이박스", "측정"):
            self.assertIn(words, row)


if __name__ == "__main__":
    unittest.main()
