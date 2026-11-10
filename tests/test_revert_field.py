"""컨셉 되돌리기 현장 시험(2026-11-09)의 이슈 321~323 테스트. 표준 라이브러리 unittest만 사용한다."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from _studio import ROOT, changes_section, run_cli, systems as sy
from test_verdict_field import CONCEPTS, judge, stamp, three, verdict, hyp

VERDICT = ROOT / "skills/playtest-verdict/SKILL.md"
SECTION = "컨셉을 되돌릴 때"
BRIEF = {"pillars": [{"name": "p", "test": "t"}], "mvp": ["m"], "out_of_scope": ["o"]}


def read(path) -> str:
    return path.read_text(encoding="utf-8")


def section() -> str:
    return changes_section(SECTION)


def refuted_warning() -> str:
    r = judge(three(), [verdict(result="refuted", status="approved", criteria=stamp())])
    return next(w["message"] for w in r["warnings"] if w["code"] == "approved_concept_refuted")


class HookAsks321(unittest.TestCase):
    """321번: 컨셉 승인을 내리면 범위 훅이 사용자에게 묻는다. 확인 창이 없는 실행에서는 거부된다."""

    def test_the_refuted_warning_says_the_hook_asks_321(self):
        msg = refuted_warning()
        self.assertIn("범위 훅", msg)
        self.assertIn("컨셉을 되돌릴 때", msg)
        self.assertLessEqual(msg.count("니다."), 3)   # 자세한 순서는 절에 두고 경고는 짧게

    def test_the_revert_section_says_so_too_321(self):
        part = section()
        self.assertIn("범위 훅", part)
        self.assertIn("claude -p", part)
        self.assertIn("scope-guard/SKILL.md#한계", part)   # 확인한 범위는 scope-guard의 한계 한 곳에 둔다

    def test_the_scope_limit_names_the_checked_mode_321(self):
        text = read(ROOT / "skills/scope-guard/SKILL.md")
        line = next(x for x in text.splitlines() if "claude -p" in x and "거부" in x)
        self.assertIn("acceptEdits", line)
        self.assertIn("bypassPermissions", line)


class GateReason322(unittest.TestCase):
    """322번: 확정 판정인데 게이트에 걸린 가설은 까닭(지문 없음, 기준 바뀜)을 함께 보인다."""

    def test_a_confirmed_verdict_without_a_stamp_says_why_322(self):
        r = judge(three(), [verdict(result="refuted", status="approved")])
        self.assertIn("parry_tempo.learn_timing", r["unverified"])   # 데이터는 가설 키 그대로다
        self.assertEqual(r["unverified_reasons"], {"parry_tempo.learn_timing": "지문 없음"})
        self.assertIn("parry_tempo.learn_timing", r["refuted"])

    def test_a_changed_criteria_says_why_322(self):
        data = copy.deepcopy(CONCEPTS)
        old = stamp(data)
        hyp(data)["failure_signal"] = "3판 [가정] 동안 피격률이 줄지 않는다"
        r = judge(three(), [verdict(status="approved", criteria=old)], concepts=data)
        self.assertEqual(r["unverified_reasons"].get("parry_tempo.learn_timing"), "기준 바뀜")

    def test_an_unconfirmed_verdict_stays_plain_322(self):
        r = judge(three(), [verdict(status="proposed", criteria=stamp())])
        self.assertIn("parry_tempo.learn_timing", r["unverified"])
        self.assertEqual(r["unverified_reasons"], {})

    def test_the_cli_gate_line_shows_the_reason_322(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "concepts.json").write_text(json.dumps(CONCEPTS, ensure_ascii=False), encoding="utf-8")
        sessions = three()
        (root / "playtests.json").write_text(json.dumps({"playtests": sessions, "verdicts": [verdict(result="refuted", status="approved")]},
                                                        ensure_ascii=False), encoding="utf-8")
        _, out = run_cli("check", root, "--fail-on-assumed")
        line = next(x for x in out.splitlines() if x.startswith("gate: 판정이 확정되지 않았거나 지금 기준의 판정인지 모르는 가설"))
        self.assertIn("learn_timing(지문 없음)", line)
        _, js = run_cli("check", root, "--json")
        report = next(d["report"] for d in json.loads(js)["datasets"] if d["kind"] == "playtests")
        self.assertIn("parry_tempo.learn_timing", report["unverified"])

    def test_the_viewer_adds_the_reason_on_screen_322(self):
        html = read(ROOT / "skills/studio-data/assets/viewer.html")
        self.assertIn("unverified_reasons", html)


class RevertOrder323(unittest.TestCase):
    """323번: 컨셉을 되돌릴 때의 순서와 뒷정리. 묻고 → 상태를 바꾸고 → 시험판 변경을 합치지 않고 닫고 → 설계와 데이터는 다음 컨셉까지 둔다."""

    def test_the_revert_section_orders_the_steps_323(self):
        part = section()
        order = ["hard_reject", "상태를 바꾼다", "--skip-specs", "systems.json", "선택 단계"]
        found = [part.index(x) for x in order]
        self.assertEqual(found, sorted(found))
        self.assertIn("지우지 않는다", part)

    def test_step_6_points_to_the_section_323(self):
        text = read(VERDICT)
        step6 = text[text.index("### 6. 틀렸으면 되돌아간다"):text.index("## 보고")]
        self.assertIn("changes.md#컨셉을-되돌릴-때", step6)

    def test_a_cut_concept_warning_covers_a_revert_too_323(self):
        r = sy.validate({"systems": [{"id": "s", "scope": "mvp", "pillars": ["p"], "mvp": ["m"], "rules": [{"id": "r", "text": "t"}]}], "concept": "gems"},
                        concepts=[{"id": "gems", "status": "cut", "brief": BRIEF}])
        msg = next(w["message"] for w in r["warnings"] if w["code"] == "cut_referenced")
        self.assertIn("되돌렸으면", msg)
        self.assertLess(msg.index("되돌렸으면"), msg.index("옮겨 적습니다"))
        self.assertIn("cut_referenced", section())

    def test_the_systems_warning_covers_a_reverted_concept_323(self):
        r = sy.validate({"systems": [{"id": "s", "scope": "mvp", "pillars": ["p"], "mvp": ["m"], "rules": [{"id": "r", "text": "t"}]}], "concept": "gems"},
                        concepts=[{"id": "gems", "status": "proposed", "brief": BRIEF}])
        msg = next(w["message"] for w in r["warnings"] if w["code"] == "concept_not_approved")
        self.assertIn("되돌렸으면", msg)


if __name__ == "__main__":
    unittest.main()
