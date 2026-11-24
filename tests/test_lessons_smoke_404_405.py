"""404: 구현에서 같은 실수를 세션마다 되풀이한다. 게임 프로젝트에 배운 것을 남길 곳이 없다.
405: 사용자에게 플레이를 넘기기 전에 에이전트가 그 빌드로 한 판을 끝까지 돌려 보지 않는다.
문서만 바꾼 이슈라 문서의 규칙과 연결을 본다. 표준 라이브러리 unittest만 사용한다."""
import re
import unittest

from _studio import ROOT

SKILLS = ROOT / "skills"
PAGE = SKILLS / "studio-data/references/telling-the-user.md"
LESSONS = SKILLS / "studio-data/references/lessons.md"
VERDICT = SKILLS / "playtest-verdict/SKILL.md"


def read(path):
    return path.read_text(encoding="utf-8")


def between(text, start, end):
    i = text.index(start)
    return text[i:text.index(end, i + len(start))]


class Lessons(unittest.TestCase):
    def test_shared_page_is_linked_from_the_report_page_intro(self):
        # 모든 스킬의 '보고' 절이 telling-the-user.md를 가리키므로 그 첫 문단에서 가리킨다
        intro = read(PAGE).split("\n## ", 1)[0]
        self.assertIn("(lessons.md)", intro)
        self.assertIn("두 번", intro)

    def test_page_says_when_where_shape_and_how_to_shrink(self):
        text = read(LESSONS)
        self.assertIn("두 번", text)              # 한 번 난 일은 남기지 않는다
        self.assertIn("## 배운 것", text)          # 규칙 파일 안의 자리
        self.assertIn("CLAUDE.md", text)
        self.assertIn("AGENTS.md", text)
        self.assertRegex(text, r"사용자.{0,20}묻")  # 사용자의 파일이라 처음엔 묻는다
        self.assertIn("합친다", text)              # 쌓이면 줄인다
        self.assertIn("지운다", text)
        self.assertIn("design/", text)            # 설계 결정은 여기 쓰지 않는다
        self.assertIn("continue.md", text)        # 이어 갈 일과 나눈다

    def test_shape_line_is_one_line_without_history(self):
        text = read(LESSONS)
        self.assertIn("→", text)
        self.assertRegex(text, r"날짜.{0,30}적지 않는다")


class SmokeRun(unittest.TestCase):
    def step1(self):
        return between(read(VERDICT), "### 1.", "### 2.")

    def test_step1_runs_one_full_run_before_handing_over(self):
        step = self.step1()
        self.assertIn("한 판을 끝까지", step)
        self.assertIn("판 끝 질문", step)
        self.assertIn("판 로그", step)
        self.assertIn("대신하지 못한다", step)   # 테스트·봇 기준선은 화면을 돌리지 않는다

    def test_agent_run_is_not_a_playtest(self):
        step = self.step1()
        self.assertRegex(step, r"`logs`에.{0,10}넣지 않는다")
        self.assertIn("섞이지 않게", step)        # 사용자가 받을 로그에 에이전트 판이 섞이지 않게

    def test_cannot_launch_is_reported(self):
        step = self.step1()
        self.assertIn("돌려 보지 못했다고", step)

    def test_report_lists_the_run_result(self):
        report = read(VERDICT).split("## 보고", 1)[1].split("\n## ", 1)[0]
        self.assertIn("돌려 본 결과", report)


class ReviewFixes(unittest.TestCase):
    """검토에서 찾은 다섯 건."""

    def test_cross_session_repeats_are_caught_1(self):
        text = read(LESSONS)
        self.assertIn("전에도", text)        # 사용자가 전에도 그랬다고 하면 두 번째다
        self.assertIn("첫 번째", text)       # 다음 세션도 반드시 부딪힐 환경 사실은 처음에 남긴다
        intro = read(PAGE).split("\n## ", 1)[0]
        self.assertNotIn("이번 일에서", intro)   # 한 세션 안으로 좁히지 않는다

    def test_fix_after_smoke_run_follows_the_rebuild_bullet_2(self):
        step = between(read(VERDICT), "**넘기기 전에", "- **질문 문장")
        self.assertIn("'어긋나면 플레이 전에 고친다'", step)

    def test_declined_rule_file_3(self):
        text = read(LESSONS)
        self.assertIn("거절", text)
        self.assertIn("다시 묻지 않는다", text)

    def test_screen_is_the_build_being_handed_over_4(self):
        self.assertNotIn("그 판의 시험판 화면", read(VERDICT))

    def test_rare_rejudge_moved_to_changes_5(self):
        from _studio import changes_section
        moved = changes_section("사용자가 제안과 다르게 정할 때")
        for word in ("proposed_result", "모름으로 낮춰", "받아들이지 않으면", "cut_reason"):
            self.assertIn(word, moved, word)
        step3 = between(read(VERDICT), "### 3.", "### 4.")
        self.assertIn("](references/changes.md#사용자가-제안과-다르게-정할-때)", step3)
        self.assertNotIn("같은 편집에서 새 판정을 넣는다", step3)   # 원본은 옮긴 절과 기록 형식


if __name__ == "__main__":
    unittest.main()
