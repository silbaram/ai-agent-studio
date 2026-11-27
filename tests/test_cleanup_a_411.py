"""411 정리 A: 스킬 문서를 세 갈래로 검토해 찾은, 틀렸거나 서로 어긋나는 곳.
문서와 검사 메시지의 연결을 본다. 표준 라이브러리 unittest만 사용한다."""
import re
import unittest

from _studio import ROOT, changes_section, concepts as cc

SKILLS = ROOT / "skills"


def read(rel):
    return (SKILLS / rel).read_text(encoding="utf-8") if not rel.startswith("/") else open(rel, encoding="utf-8").read()


def row(rel, code):
    return next(l for l in read(rel).splitlines() if l.startswith(f"| `{code}`"))


class Contradictions(unittest.TestCase):
    def test_no_verdict_cell_to_fill_a1(self):
        for path in SKILLS.rglob("*.md"):
            text = path.read_text(encoding="utf-8")
            self.assertNotRegex(text, r'판정 칸[^.\n]{0,20}"아직"', str(path))
        self.assertNotIn("여기에는 결과만 옮긴다", read("production-handoff/references/production-record.md"))

    def test_tuning_is_in_the_check_tables_a2(self):
        self.assertIn("tuning", row("playtest-verdict/references/playtest-record.md", "approved_concept_refuted"))
        gate = next(l for l in read("playtest-verdict/references/playtest-record.md").splitlines() if l.startswith("- `--fail-on-assumed`는"))
        self.assertIn("조정으로 돌린 가설", gate)
        tail = next(l for l in read("concept-exploration/references/concept-record.md").splitlines() if "`--fail-on-assumed`는 선택한 컨셉의 브리프에" in l)
        self.assertIn("조정으로 돌린 가설", tail)
        self.assertIn("tuning", row("system-design/references/systems-format.md", "system_untested"))

    def test_brief_and_changes_point_at_the_table_a2(self):
        brief_row = next(l for l in read("concept-exploration/references/brief.md").splitlines() if l.startswith("| `tuning` |"))
        self.assertNotIn("approved_concept_refuted", brief_row)
        self.assertIn("playtest-record.md#검사-내용", brief_row)
        self.assertNotIn("approved_concept_refuted`에서 뺀다", changes_section("조정으로 돌릴 때"))

    def test_if_wrong_has_a_home_a3(self):
        brief = read("concept-exploration/references/brief.md")
        r = next(l for l in brief.splitlines() if l.startswith("| `if_wrong` |"))
        self.assertIn("다시 짠다", r)                      # 예시가 필러 수준이다
        rule = next(l for l in brief.splitlines() if l.startswith("- **재미가 무너지는 주장만 가설로 삼는다.**"))
        self.assertIn("`if_wrong`", rule)
        card = read("studio-data/references/telling-the-user.md")
        self.assertIn("- 틀리면: <브리프의 `if_wrong`", card)
        h = {"id": "x", "claim": "c", "failure_signal": "f", "test": "t"}
        self.assertEqual(cc.criteria_stamp(h), cc.criteria_stamp({**h, "if_wrong": "다시 짠다"}))   # 지문에 들지 않는다

    def test_cut_timing_lives_in_changes_only_a4(self):
        r = row("playtest-verdict/references/playtest-record.md", "verdict_criteria_changed")
        self.assertNotIn("기준을 고친 편집에서 바로", r)
        self.assertIn("changes.md#다시-시험할-때", r)

    def test_builds_on_judged_hypothesis_lives_in_changes_only_a5(self):
        brief = read("concept-exploration/references/brief.md")
        rule = next(l for l in brief.splitlines() if l.startswith("- **세는 빌드는 이름으로 가리킨다.**"))
        self.assertNotIn("`builds`를 새로 더하지 않고", rule)
        self.assertNotIn("`builds`를 새로 더하지 않고", row("concept-exploration/references/concept-record.md", "criteria_points_to_data"))
        self.assertNotIn("builds를 새로 더하지 않고", cc.POINTS_TO_DATA_JUDGED)
        self.assertIn("판정한 가설의 문장을 고칠 때", cc.POINTS_TO_DATA_JUDGED)

    def test_stat_budget_ack_reason_follows_studio_data_a6(self):
        text = read("stat-budget/SKILL.md")
        self.assertNotIn("사용자 결정(2026-11-07)", text)
        self.assertIn("../studio-data/SKILL.md#실행", text.split("`over_budget` / `under_budget`", 1)[1].split("\n", 1)[0])

    def test_check_the_project_folder_a7(self):
        for rel in ("progression-economy/SKILL.md", "numeric-provenance/SKILL.md"):
            self.assertNotIn("check data/", read(rel), rel)

    def test_pick_no_effect_condition_in_the_table_a8(self):
        r = row("run-growth/references/growth-format.md", "pick_no_effect")
        self.assertIn("max_picks", r)
        self.assertIn("정수", r)
        line = next(l for l in read("run-growth/SKILL.md").splitlines() if l.startswith("- `pick_no_effect`"))
        self.assertLess(len(line.encode("utf-8")), 600)
        self.assertIn("references/growth-format.md#검사-내용", line)

    def test_budget_costs_replace_weights_a9(self):
        text = read("progression-economy/SKILL.md")
        self.assertNotIn("예산 원가는 그와 따로", text)
        self.assertIn("원가로", text)

    def test_one_way_to_add_an_item_a10(self):
        step1 = next(l for l in read("progression-economy/SKILL.md").splitlines() if l.startswith("1. 요청을 해당 원본 파일의 항목으로 바꾼다."))
        self.assertIn("../stat-budget/SKILL.md#4-새-항목은-초안에서-시작한다", step1)

    def test_one_way_to_close_without_a_prompt_a11(self):
        setup = read("scope-guard/references/openspec-setup.md")
        self.assertNotIn("CLI 대신 `/opsx:archive`로 닫는다", setup)
        self.assertIn("`--yes`를 붙인다", read("scope-guard/SKILL.md"))

    def test_art_handoff_copies_paths_not_ids_a12(self):
        text = read("art-handoff/SKILL.md")
        self.assertNotIn("`id` 목록으로 옮긴다", text)
        self.assertNotIn("id를 옮겨 적는다", text)

    def test_art_handoff_reads_the_content_record_a13(self):
        step1 = read("art-handoff/SKILL.md").split("### 1.", 1)[1].split("### 2.", 1)[0]
        self.assertIn("design/content/", step1)

    def test_readme_copy_count_includes_studio_data_a14(self):
        line = next(l for l in (ROOT / "README.md").read_text(encoding="utf-8").splitlines() if "Node.js 없이 설치하려면" in l)
        folders = sum(1 for p in SKILLS.iterdir() if (p / "SKILL.md").is_file())
        words = {16: "열여섯", 17: "열일곱", 18: "열여덟", 19: "열아홉", 20: "스무"}   # 검토 9: 폴더 수를 박아 두지 않는다
        self.assertIn(f"폴더 {words[folders]} 개", line)
        self.assertIn("`studio-data`", line)

    def test_readme_status_is_current_a15(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        status = readme.split("## 지금 상태", 1)[1].split("\n## ", 1)[0]
        self.assertNotIn("0~6단계", status)
        self.assertNotIn("아직 시험 게임으로 돌려 보지 않았다", status)
        r = next(l for l in readme.splitlines() if "[studio-data](skills/studio-data/SKILL.md)" in l and l.startswith("|"))
        for cmd in ("`hypothesis`", "`runlog`", "`draft`"):
            self.assertIn(cmd, r)

    def test_guide_flow_has_content_and_production_a16(self):
        flow = (ROOT / "docs/guide.md").read_text(encoding="utf-8").split("## 큰 흐름", 1)[1].split("```", 2)[1]
        self.assertIn("직업·스킬·스테이지·아이템", flow)
        self.assertIn("본 게임", flow)

    def test_measured_examples_use_session_ids_a17(self):
        self.assertNotIn("playtest-2026-11-03", read("numeric-provenance/references/example.md"))
        self.assertNotIn("playtest-2026-11-03", read("progression-economy/references/data-format.md"))

    def test_environment_notes_are_current_a18(self):
        text = read("studio-data/SKILL.md")
        self.assertNotIn("편집 훅의 경고 줄이기는 실제 세션에서 확인하지 않았다", text)
        self.assertNotIn("SessionStart의 배운 것 시작 알림은 실제 세션에서 확인하지 않았다", text)
        self.assertNotIn("Windows에서의 훅 명령 실행은 아직 확인하지 않았다", text)

    def test_step7_updates_the_art_record_a19(self):
        step = read("production-handoff/SKILL.md").split("### 7.", 1)[1].split("\n### ", 1)[0]
        item1 = next(l for l in step.splitlines() if l.startswith("1. "))
        self.assertIn("design/art-handoff.md", item1)
        self.assertLess(len(read("production-handoff/SKILL.md").encode("utf-8")), 20000)


import copy

from test_verdict_field import CONCEPTS, codes, hyp, judge, printed, stamp, three, verdict

TUNED = {"date": "2026-11-27", "why": "해 보며 바꾼다"}


def tuned_concepts(**over):
    d = copy.deepcopy(CONCEPTS)
    hyp(d).update({"tuning": TUNED, **over})
    return d


class Review(unittest.TestCase):
    """411+A를 먼저 검토해 찾은 아홉 건."""

    def test_tuned_hypothesis_has_no_open_needs_1(self):
        r = judge(three(), [verdict(result="unknown", status="approved", criteria=stamp(), next_needs="플레이 전에 문턱을 정한다")],
                  concepts=tuned_concepts())
        self.assertNotIn("parry_tempo.learn_timing", r["next_needs"])
        self.assertNotIn("다음 시험 전에 풀 것(parry_tempo.learn_timing)", printed(r))

    def test_tuned_hypothesis_gets_no_gate_warnings_2(self):
        r = cc.validate(tuned_concepts(test="3명에게 5판씩"))
        self.assertNotIn("untagged_number", codes(r["warnings"]))
        self.assertNotIn("parry_tempo.learn_timing", r["data_stamps"])
        info = cc.hypothesis_index(tuned_concepts())
        info["parry_tempo"]["data"] = {"learn_timing": "abcd1234"}
        from _studio import playtests as pt
        r2 = pt.validate({"playtests": three(), "verdicts": [verdict(result="holds", status="approved", criteria=stamp())]}, info)
        self.assertNotIn("verdict_data_missing", codes(r2["warnings"]))

    def test_content_ideas_keeps_its_rules_3(self):
        text = read("content-ideas/SKILL.md")
        self.assertIn("바꾸자는 제안은 다른 벌로 따로 내고, 까닭을 법칙으로 댄다", text)
        self.assertIn("이 게임에서 맞는지는 플레이가 가린다", text)
        self.assertIn("출처의 질은 에이전트가 고른다", text + read("content-ideas/references/research.md"))
        self.assertLess(len(read("content-ideas/SKILL.md").encode("utf-8")), 8192)

    def test_deleting_an_untested_hypothesis_cleans_links_4(self):
        step2 = next(l for l in changes_section("조정으로 돌릴 때").splitlines() if l.startswith("2. "))
        self.assertIn("systems.json", step2)
        self.assertIn("success_criteria", step2)

    def test_no_active_hypothesis_uses_valid_tuning_5(self):
        d = copy.deepcopy(CONCEPTS)
        hyp(d)["tuning"] = "bad"
        hyp(d, "tempo_choice")["tuning"] = TUNED
        self.assertNotIn("no_active_hypothesis", codes(cc.validate(d)["warnings"]))

    def test_rule_like_tuning_goes_to_system_rules_6(self):
        step5 = read("content-ideas/SKILL.md").split("### 5.", 1)[1].split("\n## ", 1)[0]
        item3 = next(l for l in step5.splitlines() if l.startswith("3. "))
        self.assertIn("2로", item3)
        step3 = next(l for l in changes_section("조정으로 돌릴 때").splitlines() if l.startswith("3. "))
        self.assertIn("system-design", step3)

    def test_handoff_routes_to_content_first_7(self):
        dont = read("production-handoff/SKILL.md").split("## 쓰지 않을 때", 1)[1].split("\n## ", 1)[0]
        self.assertIn("../content-ideas/SKILL.md", dont)
        self.assertLess(len(read("production-handoff/SKILL.md").encode("utf-8")), 20000)

    def test_verdict_description_keeps_survival_curve_8(self):
        head = read("playtest-verdict/SKILL.md").split("---", 2)[1]
        self.assertIn("survival-curve", head)
        self.assertLess(len(read("playtest-verdict/SKILL.md").encode("utf-8")), 20000)


if __name__ == "__main__":
    unittest.main()
