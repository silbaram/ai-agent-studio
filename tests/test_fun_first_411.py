"""411: 검증이 게임의 재미 요소 대신 플레이하며 바꿀 요소(이동기 종류와 쓰임새, 그림 스타일)에 몰렸다.
- 무엇을 가설로 삼을지(틀리면 재미가 무너지나, 조정 하나로 끝나나) 가르는 규칙이 없었다.
- 조정할 요소가 틀려도 '재시험 / 컨셉 되돌리기' 둘만 있어 길을 막았다.
- 취향 질문('2D-HD에서 좋을지')을 읽힘 시험으로 바꿨다.
- 직업·고유 스킬·스테이지·아이템을 짜는 일이 주 흐름에 없었다.
표준 라이브러리 unittest만 사용한다."""
import copy
import unittest

from _studio import ROOT, changes_section, common, run_cli, systems as sy
from test_untested_systems import HYPS, run as run_systems, system
from test_verdict_field import CONCEPTS, cc, codes, hyp, judge, printed, stamp, three, verdict
from test_verdict_issues_357 import Project

SKILLS = ROOT / "skills"
BRIEF = SKILLS / "concept-exploration/references/brief.md"
VERDICT = SKILLS / "playtest-verdict/SKILL.md"
TUNING = {"date": "2026-11-27", "why": "사용자: 해 보며 바꾼다"}


def read(path):
    return path.read_text(encoding="utf-8")


def bullet(text, head):
    return next(l for l in text.splitlines() if l.startswith(f"- **{head}"))


def tuned(hid="learn_timing", value=TUNING):
    data = copy.deepcopy(CONCEPTS)
    h = hyp(data, hid)
    h["tuning"] = value
    return data


class WhatToTest(unittest.TestCase):
    """1·3: 재미가 무너지는 주장만 가설로, 조정과 취향은 가설이 아니다."""

    def test_brief_rule_comes_first_in_the_checklist(self):
        text = read(BRIEF)
        rule = bullet(text, "재미가 무너지는 주장만 가설로 삼는다.")
        self.assertLess(text.index(rule), text.index("- **사람이 해야 아는 것을 잰다.**"))
        self.assertIn("틀리면 무엇을 다시 짜나", rule)
        self.assertIn("조정", rule)
        self.assertIn("잴 수 있다는 것은 가설로 삼을 까닭이 아니다", rule)

    def test_taste_is_the_users_call_not_a_hypothesis(self):
        rule = bullet(read(BRIEF), "재미가 무너지는 주장만 가설로 삼는다.")
        self.assertIn("취향", rule)
        self.assertIn("가설로 바꾸지 않는다", rule)
        self.assertIn("../../art-handoff/SKILL.md", rule)

    def test_tuning_field_is_in_the_brief_table(self):
        row = next(l for l in read(BRIEF).splitlines() if l.startswith("| `tuning` |"))
        self.assertIn("조정으로 돌릴 때", row)


class TuningPath(unittest.TestCase):
    """2: 조정할 요소의 틀림은 조정으로 돌리고 길을 막지 않는다."""

    def test_step6_offers_the_tuning_path(self):
        step6 = read(VERDICT).split("### 6.", 1)[1].split("\n## ", 1)[0]
        self.assertIn("조정으로 돌린다", step6)
        self.assertIn("references/changes.md#조정으로-돌릴-때", step6)
        table = read(VERDICT).split("## 기준이나 컨셉을 바꿀 때", 1)[1]
        self.assertIn("(references/changes.md#조정으로-돌릴-때)", table)

    def test_changes_section_keeps_records_and_stops_retesting(self):
        s = changes_section("조정으로 돌릴 때")
        self.assertIn('"tuning"', s)
        self.assertIn("판정과 기준은 그대로", s)
        self.assertIn("다시 시험하지 않는다", s)
        self.assertIn("system_untested", s)

    def test_tuned_refuted_hypothesis_does_not_block(self):
        r = judge(three(), [verdict(result="refuted", status="approved", criteria=stamp())], concepts=tuned())
        self.assertNotIn("approved_concept_refuted", codes(r["warnings"]))
        self.assertNotIn("parry_tempo.learn_timing", r["unverified"])
        self.assertNotIn("parry_tempo.learn_timing", r["refuted"])

    def test_check_says_it_was_moved_to_tuning(self):
        r = judge(three(), [verdict(result="refuted", status="approved", criteria=stamp())], concepts=tuned())
        self.assertIn("조정으로 돌림(parry_tempo.learn_timing): 사용자: 해 보며 바꾼다", printed(r))

    def test_untuned_refuted_hypothesis_still_blocks(self):
        r = judge(three(), [verdict(result="refuted", status="approved", criteria=stamp())])
        self.assertIn("approved_concept_refuted", codes(r["warnings"]))

    def test_tuning_shape_is_checked(self):
        for bad in ("해 보며 바꾼다", {"date": "2026-11-27"}, {"why": "x"}, {"date": "11-27", "why": "x"}):
            r = cc.validate(tuned(value=bad))
            self.assertIn("schema", codes(r["errors"]), bad)
        self.assertNotIn("schema", codes(cc.validate(tuned())["errors"]))

    def test_assumed_values_of_a_tuned_hypothesis_do_not_gate(self):
        r = cc.validate(tuned())
        self.assertFalse([u for u in r["unverified"] if u.startswith("parry_tempo.brief.hypotheses[0]")], r["unverified"])
        self.assertTrue([u for u in cc.validate(CONCEPTS)["unverified"] if u.startswith("parry_tempo.brief.hypotheses[0]")])

    def test_all_hypotheses_tuned_warns(self):
        data = tuned()
        hyp(data, "tempo_choice")["tuning"] = TUNING
        self.assertIn("no_active_hypothesis", codes(cc.validate(data)["warnings"]))
        self.assertNotIn("no_active_hypothesis", codes(cc.validate(tuned())["warnings"]))

    def test_system_tested_only_by_a_tuned_hypothesis_is_untested(self):
        hyps = copy.deepcopy(HYPS)
        hyps[0]["tuning"] = TUNING
        brief = {"pillars": [{"name": "욕심이 곧 성장", "test": "t"}], "mvp": ["보석 숙성 3단계"], "out_of_scope": ["멀티플레이"], "hypotheses": hyps}
        concepts = [{"id": "gems", "status": "approved", "brief": brief}]
        r = run_systems(system(hypotheses=["greed_pays"]), concepts=concepts)
        self.assertEqual(r["errors"], [])   # 조정으로 돌린 가설도 있는 가설이다
        self.assertIn("system_untested", codes(r["warnings"]))
        self.assertNotIn("system_untested", codes(run_systems(system(hypotheses=["greed_pays", "ripening_read"]), concepts=concepts)["warnings"]))

    def test_hypothesis_command_shows_tuning(self):
        with Project(three(), [verdict(result="refuted", status="approved", criteria=stamp())], tuned()) as root:
            code, out = run_cli("hypothesis", "parry_tempo.learn_timing", root)
        self.assertEqual(code, 0)
        self.assertIn("조정으로 돌림(tuning): 2026-11-27 · 사용자: 해 보며 바꾼다", out)

    def test_handoff_does_not_recheck_tuned_hypotheses(self):
        step = read(SKILLS / "production-handoff/SKILL.md").split("### 7.", 1)[1].split("\n### ", 1)[0]
        self.assertIn("조정으로 돌린 가설", step)


class ContentInTheMainFlow(unittest.TestCase):
    """4: 직업·고유 스킬·스테이지·아이템을 짜는 일이 주 흐름에 있다."""

    def test_concept_next_step_designs_content_before_numbers(self):
        nxt = read(SKILLS / "concept-exploration/SKILL.md").split("## 다음 단계", 1)[1]
        self.assertIn("../content-ideas/SKILL.md", nxt)
        self.assertLess(nxt.index("content-ideas"), nxt.index("progression-economy"))

    def test_content_ideas_covers_stages_and_says_it_is_the_main_step(self):
        text = read(SKILLS / "content-ideas/SKILL.md")
        desc = text.split("description:", 1)[1].split("\n", 1)[0]
        self.assertIn("stages", desc)
        self.assertIn("main design step", desc)
        self.assertIn("스테이지", text.split("## 원칙", 1)[0])

    def test_content_ideas_step5_sends_tuning_away_from_hypotheses(self):
        step5 = read(SKILLS / "content-ideas/SKILL.md").split("### 5.", 1)[1].split("\n## ", 1)[0]
        self.assertIn("재미가 무너지는 주장만 가설로 삼는다", step5)

    def test_readme_row_and_history(self):
        row = next(l for l in read(ROOT / "README.md").splitlines() if "content-ideas" in l and l.startswith("|"))
        self.assertIn("스테이지", row)
        self.assertTrue(any("411번" in l for l in read(ROOT / "docs/architecture.md").splitlines()))


if __name__ == "__main__":
    unittest.main()
