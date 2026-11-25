"""content-ideas: 직업·스킬·카드 같은 게임 내용을 조사해 법칙부터 제안하고, 법칙을 따르는 안을 사용자와 다듬는다.
hordeweave에서 사용자가 던진 '전사는 돌진, 마법사는 이탈'이 내용 설계 없이 바로 브리프와 무거운 가설로 간 일에서 나왔다.
문서만 있는 스킬이라 문서의 규칙과 연결을 본다. 표준 라이브러리 unittest만 사용한다."""
import re
import unittest

from _studio import ROOT

SKILL_DIR = ROOT / "skills/content-ideas"
SKILL = SKILL_DIR / "SKILL.md"
RESEARCH = SKILL_DIR / "references/research.md"
RECORD = SKILL_DIR / "references/record.md"
CALLED = SKILL_DIR / "references/when-called.md"
LINK = "../content-ideas/SKILL.md"


def read(path):
    return path.read_text(encoding="utf-8")


def step(text, n):
    start = text.index(f"### {n}.")
    nxt = text.find(f"### {n + 1}.", start)
    end = nxt if nxt != -1 else text.index("\n## ", start)
    return text[start:end]


def section(text, title):
    start = text.index(title)
    rest = text[start + len(title):]
    nxt = re.search(r"^## ", rest, re.M)
    return rest[:nxt.start()] if nxt else rest


class Shape(unittest.TestCase):
    def test_folder_has_the_install_files(self):
        for rel in ("SKILL.md", "LICENSE", "agents/openai.yaml", "references/research.md", "references/record.md",
                    "references/when-called.md"):
            self.assertTrue((SKILL_DIR / rel).is_file(), rel)
        yaml = read(SKILL_DIR / "agents/openai.yaml")
        for key in ("display_name", "short_description", "default_prompt", "$content-ideas"):
            self.assertIn(key, yaml)

    def test_frontmatter_says_what_and_when_in_english(self):
        head = read(SKILL).split("---")[1]
        self.assertIn("\nname: content-ideas\n", head)
        desc = re.search(r'description: "([^"]+)"', head).group(1)
        self.assertIsNone(re.search(r"[가-힣]", desc.replace("[가정]", "")), "description is English")
        self.assertIn("Use when", desc)
        self.assertIn("laws", desc)
        self.assertIn("seed", desc)                  # 사용자가 던진 아이디어로도 불린다
        self.assertIn("before", desc)                # 브리프나 가설을 고치기 전에

    def test_skill_page_stays_short(self):
        self.assertLess(len(read(SKILL).encode("utf-8")), 8192)


class Flow(unittest.TestCase):
    def setUp(self):
        self.text = read(SKILL)

    def test_laws_come_before_sets(self):
        self.assertIn("법칙", step(self.text, 2).split("\n", 1)[0])
        self.assertIn("벌", step(self.text, 3).split("\n", 1)[0])

    def test_seed_idea_is_kept_at_the_center(self):
        s1 = step(self.text, 1)
        self.assertIn("씨앗", s1)
        self.assertIn("사용자의 말 그대로", s1)
        s3 = step(self.text, 3)
        self.assertIn("씨앗", s3)
        self.assertIn("갈아 치우지 않는다", self.text)

    def test_called_mid_edit_is_offered_not_forced(self):
        table = section(self.text, "## 이럴 때 읽을 곳")
        self.assertIn("references/when-called.md#다른-스킬의-편집-중에-불려-왔을-때", table)
        self.assertNotIn("멈추고 여기부터 한다", self.text)

    def test_scope_conflict_is_said_and_left_to_the_user(self):
        s1 = step(self.text, 1)
        self.assertIn("범위 밖", s1)
        self.assertIn("MVP", s1)
        self.assertIn("사용자가 정한다", s1)

    def test_each_law_has_source_pillar_and_weight(self):
        s2 = step(self.text, 2)
        self.assertIn("안티필러", s2)
        self.assertIn("](references/research.md#법칙이란)", s2)
        shape = read(RESEARCH).split("## 어디서 찾나")[0]
        for word in ("출처", "필러", "필수", "선택", "걸러지는 예"):
            self.assertIn(word, shape, word)

    def test_sets_differ_by_structure_and_map_to_laws(self):
        s3 = step(self.text, 3)
        self.assertIn("구조", s3)
        self.assertIn("법칙", s3)
        self.assertIn("일부러 어긴", s3)
        self.assertIn("](references/record.md#벌의-모양)", s3)

    def test_refining_checks_changes_against_the_laws(self):
        s4 = step(self.text, 4)
        self.assertIn("법칙", s4)
        self.assertRegex(s4, r"법칙.{0,30}고칠")    # 법칙 쪽을 고칠 수도 있다

    def test_handoff_splits_heavy_from_light(self):
        s5 = step(self.text, 5)
        self.assertIn("../concept-exploration/SKILL.md", s5)   # 필러를 건드리는 주장만 가설로
        self.assertIn("../system-design/SKILL.md", s5)         # 새 규칙
        self.assertIn("[가정]", s5)                             # 수치는 데이터로
        self.assertIn("../stat-budget/SKILL.md", s5)
        self.assertIn("가설로 만들지 않는다", s5)               # 체력·속도 같은 나머지
        self.assertIn("../scope-guard/SKILL.md", s5)
        self.assertIn("1단계에서 정한", s5)

    def test_no_verdict_or_gate_here(self):
        self.assertIn("판정하지 않는다", section(self.text, "## 원칙"))
        self.assertNotIn("studio.py check", self.text)


class ReviewFixes(unittest.TestCase):
    """검토에서 찾은 열 건."""

    def setUp(self):
        self.text = read(SKILL)

    def test_seed_set_is_shown_even_when_it_breaks_a_required_law_1(self):
        s3 = step(self.text, 3)
        self.assertIn("씨앗 벌", s3)
        self.assertIn("충돌", s3)
        self.assertNotIn("씨앗을 넓히거나", s3)       # 넓힌 것은 구조가 같아 다른 벌이 아니다
        self.assertIn("변형", s3)
        self.assertNotIn("필수 법칙을 어긴 벌은 내지 않는다", read(RECORD))
        self.assertIn("씨앗 벌", read(RESEARCH))

    def test_existing_hypotheses_are_looked_at_first_2(self):
        s5 = step(self.text, 5)
        self.assertIn("이미 있는 가설", s5)
        self.assertIn("새 가설을 만들지 않", s5)
        self.assertIn("../concept-exploration/references/brief.md#가설-hypotheses-1개-이상", s5)

    def test_after_a_verdict_the_change_follows_the_retest_or_revert_path_3(self):
        called = read(CALLED)
        self.assertIn("## 가설에 판정이 있을 때", called)
        self.assertIn("../../playtest-verdict/references/changes.md#다시-시험할-때", called)
        self.assertIn("../../playtest-verdict/references/changes.md#컨셉을-되돌릴-때", called)
        self.assertIn("규칙 하나", called)
        self.assertIn("](references/when-called.md#가설에-판정이-있을-때)", self.text)

    def test_counts_in_the_record_are_decided_values_4(self):
        self.assertRegex(read(RECORD), r"개수.{0,60}\[결정: 사용자")

    def test_skill_points_at_the_shapes_instead_of_listing_them_5(self):
        s2, s3 = step(self.text, 2), step(self.text, 3)
        self.assertNotIn("네 가지", s2)
        self.assertIn("걸러지는 예", s2)               # 댈 수 없는 법칙은 내지 않는다
        self.assertNotIn("역할, 플레이어가 하는 일", s3)
        self.assertNotIn("따름, 어김, 해당 없음", s3)
        self.assertNotIn("네 줄", section(self.text, "## 보고"))

    def test_no_law_reason_uses_the_shared_hold_back_line_6(self):
        self.assertIn("../studio-data/references/telling-the-user.md#정할-것", section(self.text, "## 원칙"))

    def test_production_entry_covers_freeze_and_build_7(self):
        row = next(l for l in read(ROOT / "skills/production-milestones/SKILL.md").splitlines() if LINK in l)
        self.assertIn("동결", row)
        self.assertIn("#3-베타-콘텐츠-동결과-다듬기", row)
        called = read(CALLED)
        self.assertIn("## 본 게임에서 불려 왔을 때", called)
        self.assertIn("../../production-handoff/SKILL.md#7-본-게임-빌드에서-가설을-다시-확인한다", called)

    def test_user_can_skip_the_skill_8(self):
        called = read(CALLED)
        self.assertIn("## 다른 스킬의 편집 중에 불려 왔을 때", called)
        self.assertIn("씨앗", called)
        self.assertRegex(called, r"바로 고치자고 하면.{0,20}따른다")
        concept = next(l for l in read(ROOT / "skills/concept-exploration/SKILL.md").splitlines() if LINK in l)
        self.assertIn("권한다", concept)
        verdict = next(l for l in read(ROOT / "skills/playtest-verdict/SKILL.md").splitlines() if LINK in l)
        self.assertIn("권한다", verdict)

    def test_duplicates_are_gone_9(self):
        page = read(ROOT / "skills/studio-data/references/telling-the-user.md")
        row = next(l for l in page.splitlines() if "`content-ideas`" in l)
        self.assertNotIn("불려 와도", row)               # 표 아래 공통 규칙이 맡는다
        self.assertEqual(read(RESEARCH).count("벌을 내지 않는"), 1)

    def test_brief_is_settled_before_rules_move_10(self):
        s5 = step(self.text, 5)
        self.assertLess(s5.index("브리프를 먼저 맞춘다"), s5.index("../system-design/SKILL.md"))
        self.assertIn("systems.json", s5)               # 필러 이름을 바꾸면 연결도 고친다


class SecondReview(unittest.TestCase):
    """두 번째 검토에서 찾은 여덟 건."""

    def setUp(self):
        self.text = read(SKILL)
        self.called = read(CALLED)

    def test_held_or_unknown_change_keeps_old_runs_apart_1(self):
        part = self.called.split("## 가설에 판정이 있을 때", 1)[1].split("\n## ", 1)[0]
        self.assertIn("../../playtest-verdict/references/changes.md#다른-시스템이-바뀌어-지난-기록과-합치지-않을-때", part)

    def test_set_counts_are_assumed_until_chosen_2(self):
        text = read(RECORD)
        self.assertRegex(text, r"벌.{0,40}개수.{0,60}\[가정\]")
        self.assertEqual(text.count("[결정: 사용자 YYYY-MM-DD]"), 1)   # 개수 태그는 한 곳에

    def test_count_axis_only_when_left_open_3(self):
        self.assertIn("열어 두면", step(self.text, 1))
        self.assertIn("열어 둔", step(self.text, 3))

    def test_multi_rule_retest_offers_choices_4(self):
        part = self.called.split("## 가설에 판정이 있을 때", 1)[1].split("\n## ", 1)[0]
        self.assertIn("하나만 먼저", part)
        self.assertIn("가를 수 없다고", part)
        self.assertIn("notes", part)

    def test_reason_to_offer_is_true_5(self):
        part = self.called.split("## 다른 스킬의 편집 중에 불려 왔을 때", 1)[1].split("\n## ", 1)[0]
        self.assertNotIn("판정 기준이 바뀌", part)
        self.assertIn("두 번", part)

    def test_reopening_reads_the_handed_on_hypotheses_6(self):
        reopen = read(RECORD).split("## 다시 열 때", 1)[1].split("\n## ", 1)[0]
        self.assertNotIn("법칙이 기대던 가설", reopen)
        self.assertIn("넘긴 곳", reopen)
        self.assertIn("hypothesis", reopen)

    def test_later_scope_is_carried_to_handoff_7(self):
        self.assertIn("scope: later", self.text)

    def test_new_system_in_production_goes_back_to_alpha_8(self):
        part = self.called.split("## 본 게임에서 불려 왔을 때", 1)[1]
        self.assertIn("../../production-milestones/SKILL.md#1-알파-기능-완료", part)
        self.assertIn("새 시스템", part)


class ThirdReview(unittest.TestCase):
    """세 번째 검토에서 찾은 일곱 건."""

    def setUp(self):
        self.text = read(SKILL)
        self.called = read(CALLED)
        self.judged = self.called.split("## 가설에 판정이 있을 때", 1)[1].split("\n## ", 1)[0]
        self.main = self.called.split("## 본 게임에서 불려 왔을 때", 1)[1]

    def test_verdicts_are_checked_by_state_not_by_timing_1(self):
        self.assertIn("](references/when-called.md#가설에-판정이-있을-때)", step(self.text, 1))
        self.assertNotIn("판정 뒤에 불려 왔", self.text)
        self.assertNotIn("## 판정 뒤에 불려 왔을 때", self.called)

    def test_new_data_after_holds_points_to_stale_verdicts_2(self):
        self.assertIn("../../production-milestones/references/content-growth.md#낡은-판정-풀기", self.judged)
        self.assertIn("데이터 바뀜", self.judged)

    def test_counts_of_other_games_are_written_in_words_3(self):
        record = read(RECORD).split("## 기록 파일", 1)[1].split("\n## ", 1)[0]
        self.assertRegex(record, r"다른 게임의 개수.{0,80}말로")
        self.assertIn("record.md#기록-파일", read(RESEARCH))

    def test_data_only_change_after_refuted_keeps_the_criteria_4(self):
        self.assertRegex(self.judged, r"`data/`만 바꾸면.{0,80}기준은 고치지 않는다")

    def test_production_count_lives_in_one_place_5(self):
        self.assertIn("../../production-milestones/SKILL.md#2-콘텐츠를-늘린다", self.main)
        self.assertIn("옮겨 적지 않", self.main)

    def test_back_to_step_two_names_the_skill_6(self):
        self.assertNotIn("넣기 전에 2단계로", self.main)

    def test_handed_on_hypotheses_carry_the_concept_7(self):
        handed = read(RECORD).split("## 넘긴 곳", 1)[1].split("```", 1)[0]
        self.assertIn("<컨셉>.<가설>", handed)


class FieldTest408(unittest.TestCase):
    """408: 현장 시험 세션이 진행 표의 '아직'을 믿고 틀림 확정 판정을 보지 않았다."""

    def test_step_one_runs_check_first_and_trusts_the_verdict_record(self):
        s1 = step(read(SKILL), 1)
        line = next(l for l in s1.splitlines() if "`check .`" in l)
        self.assertTrue(line.startswith("- [`check .`]"), line)   # 묻히지 않게 따로 한 줄, 맨 앞
        self.assertIn("production.md", line)
        self.assertIn("원본", line)
        self.assertLess(s1.index("`check .`"), s1.index("씨앗"))

    def test_verdict_pointer_lives_in_step_one_only(self):
        table = section(read(SKILL), "## 이럴 때 읽을 곳")
        self.assertNotIn("가설에-판정이-있을-때", table)


class Review408(unittest.TestCase):
    """408 수정을 먼저 검토해 찾은 다섯 건."""

    def test_refuted_is_told_in_the_first_report_1(self):
        part = read(CALLED).split("## 가설에 판정이 있을 때", 1)[1].split("\n## ", 1)[0]
        self.assertRegex(part, r"틀림.{0,60}1단계.{0,40}(첫 보고|처음)")

    def test_recheck_table_has_no_verdict_cell_2(self):
        record = read(ROOT / "skills/production-handoff/references/production-record.md")
        table = record.split("## 본 게임 빌드에서 다시 확인", 1)[1].split("\n## ", 1)[0]
        header = next(l for l in table.splitlines() if l.startswith("| 원래 가설"))
        self.assertNotIn("판정", header)
        self.assertNotIn("| 아직 |", table)
        self.assertIn("data/playtests.json", table)
        self.assertIn("hypothesis", table)

    def test_source_of_verdicts_is_named_3(self):
        line = next(l for l in step(read(SKILL), 1).splitlines() if "`check .`" in l)
        self.assertIn("data/playtests.json", line)
        self.assertNotIn("이것이 원본", line)

    def test_check_points_at_the_tool_4(self):
        line = next(l for l in step(read(SKILL), 1).splitlines() if "`check .`" in l)
        self.assertIn("../studio-data/SKILL.md", line)

    def test_roadmap_does_not_claim_the_fix_is_verified_5(self):
        row = next(l for l in read(ROOT / "docs/architecture.md").splitlines() if l.startswith("| 8 |"))
        self.assertNotIn("1차 완료", row)
        self.assertIn("408", row)


class Research(unittest.TestCase):
    def test_sources_are_written_down_without_copying(self):
        text = read(RESEARCH)
        self.assertIn("URL", text)
        self.assertRegex(text, r"이름.{0,40}가져오지 않는다")   # 다른 게임의 직업 이름·설정을 옮기지 않는다
        self.assertIn("구조", text)

    def test_no_research_is_said_plainly(self):
        text = read(RESEARCH)
        self.assertIn("## 조사를 못 할 때", text)
        self.assertIn("조사 없음", text)

    def test_law_is_a_sentence_that_can_reject_an_item(self):
        text = read(RESEARCH)
        self.assertIn("걸러", text)


class Record(unittest.TestCase):
    def test_record_lives_in_design_content_without_numbers(self):
        text = read(RECORD)
        self.assertIn("design/content/", text)
        self.assertRegex(text, r"수치.{0,40}적지 않는다")
        self.assertIn("data/", text)

    def test_record_keeps_laws_sets_choices_and_reasons(self):
        text = read(RECORD)
        for word in ("법칙", "조사", "벌", "고른 것", "뺀 것", "까닭", "넘긴 곳", "씨앗"):
            self.assertIn(word, text, word)

    def test_reopening_reuses_the_laws(self):
        text = read(RECORD)
        self.assertIn("## 다시 열 때", text)
        self.assertIn("## 법칙을 바꿀 때", text)
        self.assertIn("](references/record.md#다시-열-때)", read(SKILL))


class Links(unittest.TestCase):
    def test_callers_point_here(self):
        for rel in ("concept-exploration/SKILL.md", "playtest-verdict/SKILL.md", "production-milestones/SKILL.md"):
            self.assertIn(f"]({LINK})", read(ROOT / "skills" / rel), rel)

    def test_stage_table_names_the_skill(self):
        page = read(ROOT / "skills/studio-data/references/telling-the-user.md")
        self.assertRegex(page, r"\| 설계 \| 내용 제안 \| `content-ideas`")

    def test_readme_guide_and_walkthrough_count_sixteen(self):
        self.assertIn("(skills/content-ideas/SKILL.md)", read(ROOT / "README.md"))
        self.assertIn("`content-ideas`", read(ROOT / "docs/guide.md"))
        for rel in ("README.md", "docs/guide.md", "docs/walkthrough.html"):
            text = read(ROOT / rel)
            self.assertNotRegex(text, r"스킬 15개|열다섯", rel)
            self.assertRegex(text, r"스킬 16개|열여섯", rel)

    def test_architecture_has_the_stage_and_why(self):
        text = read(ROOT / "docs/architecture.md")
        self.assertTrue(re.search(r"\| 8 \|[^\n]*`content-ideas`", text))
        self.assertIn("hordeweave", text)


if __name__ == "__main__":
    unittest.main()
