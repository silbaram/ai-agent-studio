"""production-handoff: 가설이 버틴 뒤 엔진을 정하고 본 게임으로 넘어가는 절차 문서. 검사기는 없다(사용자 결정 2026-11-16).
표준 라이브러리 unittest만 사용한다."""
import re
import unittest

from _studio import ROOT, cli, provenance as cp, section

SKILL = ROOT / "skills/production-handoff"
DOC = SKILL / "SKILL.md"
RECORD = SKILL / "references/production-record.md"
GROW = SKILL / "references/grow-prototype.md"
TRIAL = SKILL / "references/engine-trial.md"


def read(path):
    return path.read_text(encoding="utf-8")


def frontmatter(text):
    return text.split("---")[1]


class SkillShape(unittest.TestCase):
    def test_entry_and_codex_card_exist(self):
        self.assertTrue(DOC.is_file())
        self.assertTrue(RECORD.is_file())
        self.assertTrue((SKILL / "agents/openai.yaml").is_file())

    def test_description_is_english_and_says_when(self):
        head = frontmatter(read(DOC))
        self.assertIn("name: production-handoff", head)
        self.assertRegex(head, r'description: "[A-Z]')
        self.assertIn("Use when", head)

    def test_no_scripts_and_under_the_size_cap(self):
        self.assertFalse((SKILL / "scripts").exists())   # 파이썬 코드는 studio-data에만 둔다
        self.assertLess(len(read(DOC).encode("utf-8")), 20000)


class Flow(unittest.TestCase):
    def test_gate_reuses_the_existing_check(self):
        text = read(DOC)
        self.assertIn("check . --fail-on-assumed", text)
        self.assertIn("하지 않은 확인은 통과가 아니다", text)

    def test_engine_is_the_users_decision_with_an_exact_version(self):
        text = read(DOC)
        for word in ("필수 조건", "엔진 시험", "[결정: 사용자", "버전"):
            self.assertIn(word, text, word)

    def test_two_paths_for_the_prototype(self):
        text = read(DOC)
        for word in ("버리고 새로", "키워 가기", "원본", "같은 시드"):
            self.assertIn(word, text, word)

    def test_hypotheses_are_rechecked_on_the_real_build(self):
        text = read(DOC)
        for word in ("`builds`", "`sample`", "작은 표본"):
            self.assertIn(word, text, word)

    def test_outcomes_include_going_back(self):
        text = read(DOC)
        for word in ("진행", "되돌아가기", "그만두기"):
            self.assertIn(word, text, word)


class Record(unittest.TestCase):
    def test_record_lives_in_design_and_names_its_sections(self):
        text = read(RECORD)
        self.assertIn("design/production.md", text)
        for head in ("## 엔진", "## 넘어가기 판정", "## 시험판", "## 가져갈 것과 버릴 것", "## 본 게임 빌드에서 다시 확인"):
            self.assertIn(head, text, head)

    def test_record_template_has_no_provenance_errors(self):
        report = cp.check_paths_cli([str(RECORD), str(DOC)])
        errors = [f"{r.path}:{f.line}: {f.message}" for r in report for f in r.findings if f.level == "error"]
        self.assertEqual(errors, [])


class Links(unittest.TestCase):
    def test_readme_and_guide_list_the_skill(self):
        for rel in ("README.md", "docs/guide.md"):
            self.assertIn("production-handoff", read(ROOT / rel), rel)
        self.assertIn("(skills/production-handoff/SKILL.md)", read(ROOT / "README.md"))

    def test_counts_say_fourteen(self):
        for rel in ("README.md", "docs/guide.md", "docs/walkthrough.html"):
            text = read(ROOT / rel)
            self.assertNotRegex(text, r"스킬 13개|열세 (개|폴더)", rel)

    def test_neighbouring_skills_point_to_it(self):
        for rel in ("skills/concept-exploration/SKILL.md", "skills/scope-guard/SKILL.md"):
            self.assertIn("../production-handoff/SKILL.md", read(ROOT / rel), rel)

    def test_architecture_roadmap_has_the_stage(self):
        self.assertTrue(re.search(r"\|[^|\n]*\|[^|\n]*`production-handoff`", read(ROOT / "docs/architecture.md")))


class DryRunFixes(unittest.TestCase):
    """my-cards 복사본에서 손으로 돌려 보고 찾은 곳(2026-11-16)."""

    def test_step1_quotes_the_real_gate_lines(self):
        # 가설 쪽 gate 줄은 data/playtests.json 아래에 나온다. 전체 FAIL은 데이터 gate 때문일 수 있다.
        step1 = read(DOC).split("### 1.")[1].split("### 2.")[0]
        self.assertNotIn("컨셉 gate 줄", read(DOC))
        self.assertIn("data/playtests.json", step1)
        self.assertIn(cli.GATE_LABELS["playtests"].rstrip(": "), step1)
        self.assertIn(cli.REFUTED_GATE.rstrip(": "), step1)
        self.assertIn("FAIL", step1)

    def test_openspec_condition_only_when_used(self):
        step1 = read(DOC).split("### 1.")[1].split("### 2.")[0]
        self.assertIn("OpenSpec을 쓰는", step1)

    def test_engine_in_brief_assumed_is_not_decided(self):
        step2 = read(DOC).split("### 2.")[1].split("### 3.")[0]
        self.assertIn("`constraints.assumed`", step2)

    def test_headless_rules_are_a_condition_from_the_tests(self):
        step2 = read(DOC).split("### 2.")[1].split("### 3.")[0]
        self.assertIn("화면 없이", step2)
        self.assertIn("화면 없이", read(RECORD))

    def test_logs_and_bots_stay_until_main_verdicts(self):
        text = read(DOC)
        self.assertIn("개발용 빌드", text)
        self.assertNotIn("기록 내려받기", text)   # 판 로그는 버리는 시험용 기능이 아니다

    def test_real_build_name_differs_from_prototype(self):
        step7 = read(DOC).split("### 7.")[1].split("### 8.")[0]
        self.assertIn("`game_build`", step7)
        self.assertIn("시험판 세션에 없는", step7)


class Strengths(unittest.TestCase):
    """조사한 저장소의 장점을 우리 도구로 옮긴 것."""

    def test_flow_table_names_user_decisions_and_stops(self):
        flow = section(DOC, "흐름")
        self.assertIn("| 단계 | 사용자가 정하는 것 | 멈추는 조건 |", flow)

    def test_rare_paths_live_in_references(self):
        text = read(DOC)
        self.assertIn("| 이럴 때 | 읽을 곳 |", text)
        for ref in ("references/grow-prototype.md", "references/engine-trial.md"):
            self.assertIn(f"({ref}", text, ref)
        self.assertTrue(GROW.is_file())
        self.assertTrue(TRIAL.is_file())

    def test_parity_compares_two_output_files(self):
        grow = read(GROW)
        for word in ("같은 시드", "원본", "두 결과 파일"):
            self.assertIn(word, grow, word)
        self.assertIn("동일성 확인", read(RECORD))

    def test_knowledge_risk_is_a_candidate_column(self):
        self.assertIn("| 지식 위험 |", read(RECORD))
        trial = read(TRIAL)
        for level in ("높음", "중간", "낮음"):
            self.assertIn(level, trial, level)

    def test_prototype_isolation_is_checked(self):
        step5 = read(DOC).split("### 5.")[1].split("### 6.")[0]
        self.assertIn("grep", step5)
        self.assertIn("격리 확인", read(RECORD))

    def test_new_references_have_no_provenance_errors(self):
        paths = [str(x) for x in (GROW, TRIAL) if x.is_file()]
        self.assertEqual(len(paths), 2)
        report = cp.check_paths_cli(paths)
        errors = [f"{r.path}:{f.line}: {f.message}" for r in report for f in r.findings if f.level == "error"]
        self.assertEqual(errors, [])


class ReviewFixes(unittest.TestCase):
    """먼저 검토에서 찾은 곳(2026-11-16)."""

    def step(self, n):
        return read(DOC).split(f"### {n}.")[1].split(f"### {n + 1}.")[0]

    def test_old_gate_wording_is_gone_everywhere(self):
        self.assertNotIn("컨셉 gate 줄", read(RECORD))
        line = [x for x in read(ROOT / "docs/architecture.md").splitlines() if "`production-handoff`)" in x and x.startswith("- ")]
        self.assertEqual(len(line), 1)
        self.assertNotIn("컨셉 gate", line[0])

    def test_record_gate_rows_follow_step1(self):
        gate = read(RECORD).split("## 넘어가기 판정")[1]
        self.assertIn("data/playtests.json", gate)
        self.assertIn("모름으로 둠", gate)
        self.assertIn("design/concepts.json", gate)

    def test_step1_has_no_contradicting_two_lines_rule(self):
        self.assertNotIn("위 두 줄이 없으면", self.step(1))

    def test_step1_says_main_hypotheses_left_are_fine(self):
        self.assertIn("`_main`", self.step(1))

    def test_step1_handles_the_brief_gate_line(self):
        step1 = self.step(1)
        self.assertIn("`== design/concepts.json`", step1)
        self.assertIn("success_criteria", step1)

    def test_isolation_uses_git_grep_and_the_archive_in_grow(self):
        step5 = self.step(5)
        self.assertIn("git grep -n", step5)
        self.assertNotIn("grep -rn", step5)
        self.assertIn("원본으로 남긴 폴더", step5)

    def test_dev_build_tools_follow_the_step2_condition(self):
        self.assertIn("가설의 `test`가", self.step(5))

    def test_scope_guard_points_to_dev_build_rule(self):
        self.assertIn("../production-handoff/SKILL.md#5-시험판을-어떻게-할지-정한다", read(ROOT / "skills/scope-guard/SKILL.md"))

    def test_architecture_records_the_dry_run(self):
        line = [x for x in read(ROOT / "docs/architecture.md").splitlines() if "`production-handoff`)" in x and x.startswith("- ")][0]
        for word in ("손 시험", "`game_build`", "지식 위험", "격리 확인"):
            self.assertIn(word, line, word)


class DraftCompletion(unittest.TestCase):
    """초본을 마치려고 더한 것(2026-11-16): 이미 쓰는 엔진 알아보기, 엔진 시험 뒤 위험 목록."""

    def test_existing_engine_is_found_from_project_files(self):
        trial = read(TRIAL)
        self.assertIn("## 이미 쓰는 엔진 알아보기", trial)
        for marker in ("project.godot", "ProjectSettings/ProjectVersion.txt", ".uproject", "default.project.json", "package.json"):
            self.assertIn(marker, trial, marker)
        step2 = read(DOC).split("### 2.")[1].split("### 3.")[0]
        self.assertIn("references/engine-trial.md#이미-쓰는-엔진-알아보기", step2)

    def test_found_engine_still_needs_the_user(self):
        section = read(TRIAL).split("## 이미 쓰는 엔진 알아보기")[1].split("\n## ")[0]
        self.assertIn("사용자", section)

    def test_risk_list_after_the_trial(self):
        trial = read(TRIAL)
        self.assertIn("## 위험 목록", trial)
        self.assertIn("| 위험 | 미리 보이는 신호 | 할 일 |", read(RECORD))
        step3 = read(DOC).split("### 3.")[1].split("### 4.")[0]
        self.assertIn("references/engine-trial.md#위험-목록", step3)

    def test_risk_list_has_no_made_up_odds(self):
        section = read(TRIAL).split("## 위험 목록")[1].split("\n## ")[0]
        self.assertIn("가능성이나 영향을 숫자나 등급으로 매기지 않는다", section)
        self.assertIn("엔진 시험에서 막힌 곳", section)   # 위험의 출처


def detect_section():
    return read(TRIAL).split("## 이미 쓰는 엔진 알아보기")[1].split("\n## ")[0]


class DraftReviewFixes(unittest.TestCase):
    """초본 마무리분 먼저 검토(2026-11-17)에서 고친 것."""

    def test_partial_version_is_not_the_exact_version(self):
        section = detect_section()
        self.assertIn("버전 단서", section)
        self.assertIn("GUID", section)
        self.assertIn("정확한 버전은 사용자에게", section)

    def test_engine_without_version_pinning(self):
        step4 = read(DOC).split("### 4.")[1].split("### 5.")[0]
        self.assertIn("고정할 수 없음", step4)
        self.assertIn("고정할 수 없음", read(RECORD))

    def test_search_scope_skips_dependency_and_tool_folders(self):
        section = detect_section()
        for folder in ("node_modules", ".git", ".claude", "archive"):
            self.assertIn(folder, section, folder)
        self.assertIn("아래 폴더", section)   # 시험판이 하위 폴더에 있는 경우(my-cards prototype/)

    def test_report_shows_detection_and_risk_list(self):
        report = read(DOC).split("## 보고")[1].split("\n## ")[0]
        self.assertIn("이미 쓰는 엔진", report)
        self.assertIn("위험 목록", report)
        trial_risk = read(TRIAL).split("## 위험 목록")[1]
        self.assertNotIn("후보 표와 함께 보인다", trial_risk)   # 보이는 규칙은 보고 한 곳

    def test_fixed_engine_still_gets_trial_and_risk_list(self):
        step2 = read(DOC).split("### 2.")[1].split("### 3.")[0]
        self.assertIn("엔진 시험", step2)
        self.assertIn("위험 목록", step2)
        self.assertNotIn("3단계를 건너뛴다", step2)

    def test_doc_only_pass_is_marked(self):
        step3 = read(DOC).split("### 3.")[1].split("### 4.")[0]
        self.assertIn("통과(문서)", step3)
        self.assertIn("통과(문서)", read(RECORD))
        self.assertIn("통과(문서)", read(TRIAL).split("## 위험 목록")[1])

    def test_package_json_version_source(self):
        row = [l for l in detect_section().splitlines() if l.startswith("| `package.json`")][0]
        for lock in ("package-lock.json", "pnpm-lock.yaml", "yarn.lock"):
            self.assertIn(lock, row, lock)
        self.assertIn("엔진 없이", row)

    def test_rules_are_not_repeated(self):
        field = [l for l in read(RECORD).splitlines() if l.startswith("| 위험 목록 |")][0]
        self.assertNotIn("가능성", field)
        step2 = read(DOC).split("### 2.")[1].split("### 3.")[0]
        self.assertNotIn("확인하기 전에는 정해진 것이 아니다", step2)


class FieldTestFixes(unittest.TestCase):
    """현장 시험(2026-11-17)에서 찾은 377·378."""

    def test_prototype_evidence_has_its_own_marker(self):
        step3 = read(DOC).split("### 3.")[1].split("### 4.")[0]
        self.assertIn("통과(시험판)", step3)
        self.assertIn("통과(시험판)", read(RECORD))

    def test_step1_stop_writes_no_new_record(self):
        step1 = read(DOC).split("### 1.")[1].split("### 2.")[0]
        self.assertIn("기록을 새로 만들지 않고", step1)
        self.assertIn("이미 기록이 있으면", step1)

    def test_substituted_trial_marker(self):
        step2 = read(DOC).split("### 2.")[1].split("### 3.")[0]
        self.assertIn("대신한 확인은 `통과(시험판)`", step2)

    def test_substituted_trial_does_not_grade_knowledge(self):
        risk = read(TRIAL).split("## 지식 위험")[1].split("\n## ")[0]
        self.assertIn("시험판으로 대신했으면", risk)
        self.assertIn("확인하지 못함", risk)
        risks = read(TRIAL).split("## 위험 목록")[1]
        self.assertIn("확인하지 못함인 까닭", risks)

    def test_record_template_shows_prototype_evidence(self):
        record = read(RECORD)
        self.assertIn("통과(시험판): <", record)
        field = [l for l in record.splitlines() if l.startswith("| 후보의 통과·실패 |")][0]
        self.assertIn("세션 id", field)


class RealRunFixes(unittest.TestCase):
    """my-cards 실제 넘어가기(2026-11-17)에서 찾은 379~382."""

    @staticmethod
    def step(n):
        return read(DOC).split(f"### {n}.")[1].split(f"### {n + 1}.")[0]

    def test_no_engine_pins_build_tool_versions(self):
        step4 = self.step(4)
        self.assertIn("엔진 없이", step4)
        self.assertIn("빌드 도구", step4)
        self.assertIn("lock 파일", step4)
        chosen = read(RECORD).split("### 고른 엔진")[1].split("## 시험판")[0]
        self.assertIn("빌드 도구", chosen)

    def test_grow_keeps_the_original_where_records_point(self):
        first = read(GROW).split("## 순서")[1].split("\n2. ")[0]
        self.assertIn("경로를 가리키면", first)
        self.assertIn("새 폴더", first)
        self.assertIn("본 게임 코드 폴더: <", read(RECORD))
        self.assertNotIn("원본 복사 위치", read(RECORD))

    def test_isolation_searches_the_original_folder(self):
        step5 = self.step(5)
        self.assertIn("원본으로 남긴 폴더", step5)
        self.assertNotIn("본 게임 코드가 시험판 폴더에서 자라므로", step5)

    def test_detection_skips_the_kept_original(self):
        found = read(TRIAL).split("## 이미 쓰는 엔진 알아보기")[1].split("\n## ")[0]
        self.assertIn("시험판 보관 위치", found)

    def test_recheck_is_not_the_copy_right_after_growing(self):
        step7 = self.step(7)
        self.assertIn("키워 간 직후", step7)
        self.assertIn("화면과 조작", step7)

    def test_screen_only_build_is_told_apart(self):
        step7 = self.step(7)
        self.assertIn("화면만 바꾸", step7)
        self.assertIn("화면 판", step7)
        recheck = read(RECORD).split("## 본 게임 빌드에서 다시 확인")[1].split("## 넘어가기 판정")[0]
        self.assertIn("가르는 것", recheck)
        self.assertIn("화면과 조작", recheck)


class RealRunReviewFixes(unittest.TestCase):
    """379~382 수정의 먼저 검토(2026-11-17)."""

    step = staticmethod(RealRunFixes.step)

    def test_no_screen_change_means_no_main_hypotheses(self):
        step7 = self.step(7)
        self.assertIn("다시 확인할 변화 없음", step7)
        self.assertIn("`_main` 가설을 더하지 않고", step7)

    def test_screen_version_lives_in_game_build(self):
        step7 = self.step(7)
        self.assertIn("화면 판", step7)
        self.assertNotIn("커밋만 적는다", step7)
        self.assertIn("플레이 중에 화면을 고쳐도", step7)

    def test_only_visible_information_goes_in_first(self):
        step7 = self.step(7)
        self.assertNotIn("본 게임에 넣을 것은", step7)
        self.assertIn("넣을 정보는 다시 확인 전에", step7)

    def test_no_engine_pin_waits_for_the_game_folder(self):
        step4 = self.step(4)
        self.assertIn("5단계에서", step4)
        self.assertIn("시험판의 프로젝트 파일은 고치지 않는다", step4)

    def test_one_field_for_the_original(self):
        record = read(RECORD)
        self.assertNotIn("원본 위치", record)
        self.assertNotIn("원본 위치", read(TRIAL))
        self.assertIn("'시험판 보관 위치'", self.step(5))

    def test_field_row_links_instead_of_restating(self):
        row = [l for l in read(RECORD).splitlines() if l.startswith("| 키워 간 직후 빌드와 가르는 것 |")][0]
        self.assertNotIn("화면만 바꾸면", row)
        self.assertIn("SKILL.md", row)


class RecheckSampleSize(unittest.TestCase):
    """385: 다시 확인 표본을 줄이면 시험판 판을 그 크기로 묶어 같은 판정을 내 본다. 순서는 references/recheck-sample.md 한 곳에."""
    REF = SKILL / "references/recheck-sample.md"

    @staticmethod
    def step7():
        return read(DOC).split("### 7.")[1].split("### 8.")[0]

    def part(self, title):
        return read(self.REF).split(f"## {title}", 1)[1].split("\n## ", 1)[0]

    def test_step4_points_to_the_bundle_check(self):
        item = self.step7().split("4. `sample`", 1)[1].split("\n5. ", 1)[0]
        self.assertIn("references/recheck-sample.md#시험판-판을-묶어-보기", item)
        self.assertIn("사용자에게 보인다", item)
        self.assertNotIn("판 순서대로", item)   # 묶는 법은 참고 문서에만
        self.assertIn("references/recheck-sample.md", read(DOC).split("## 흐름", 1)[0])   # 이럴 때 표

    def test_bundles_keep_excluded_runs_and_the_sample_shape(self):
        part = self.part("시험판 판을 묶어 보기")
        self.assertIn("판 순서대로", part)
        self.assertIn("빼는 판도", part)   # 센 판만 묶으면 빠지는 판 때문의 모름이 안 보인다
        self.assertNotIn("센 판만", part)
        self.assertIn("사람마다", part)   # 사람 수 x 판 수 표본
        self.assertIn("남은 판", part)

    def test_bundles_show_the_whole_verdict_with_the_prototype_tools(self):
        part = self.part("시험판 판을 묶어 보기")
        self.assertIn("버팀·틀림·모름", part)
        self.assertIn("시험판 보관 위치", part)
        self.assertIn("표본 칸", part)   # 보인 결과는 기록에 남긴다
        self.assertNotIn("버틴 가설인데도", part)

    def test_a_refuted_recheck_looks_at_the_same_comparison(self):
        para = [l for l in self.step7().splitlines() if "다시 확인에서 틀림이 나오면" in l][0]
        self.assertIn("4번", para)
        self.assertIn("references/recheck-sample.md#틀림이-표본-크기-탓일-수-있을-때", para)
        self.assertNotIn("after_results", para)   # 순서는 참고 문서에만

    def test_a_sample_size_refutation_has_a_way_forward(self):
        part = self.part("틀림이 표본 크기 탓일 수 있을 때")
        self.assertIn("references/changes.md#판정한-가설의-문장을-고칠-때", part)
        self.assertIn("after_results", part)
        self.assertIn("고친 뒤의 세션으로만", part)   # 지난 판과 합쳐 판을 더하지 않는다
        self.assertIn("사용자가 한다", part)

    def test_record_keeps_what_was_shown(self):
        row = [l for l in read(RECORD).splitlines() if l.startswith("| <가설 id> | <가설 id>_main |")][0]
        self.assertIn("묶음", row)


if __name__ == "__main__":
    unittest.main()
