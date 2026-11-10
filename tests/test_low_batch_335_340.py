"""낮음 등급 이슈 335~340을 묶어 고친 것의 테스트(2026-11-11). 표준 라이브러리 unittest만 사용한다.

335~336: 표본 줄이기 재시험에서 나온 것(after_run의 뜻, 줄인 세션 안의 앞 판).
337~340: 레벨 구성 덜어내기 현장 시험에서 나온 것(다시 차는 주기를 둘 곳과 다시 쓰는 법, 거꾸로 낸 repeat,
구간 일부 바꾸기, 역할 바꾸기의 경계)."""
import unittest

from _studio import LEVEL, changes_section, concepts as cc, level_format, section

SECTION = "표본을 줄이자는 말이 나올 때"


def step(n: int) -> str:
    text = (LEVEL / "SKILL.md").read_text(encoding="utf-8")
    start = text.index(f"### {n}.")
    return text[start:text.index("\n#", start + 4)]


def shapes(title: str) -> str:
    return section(LEVEL / "references/game-shapes.md", title)


class SampleReduction(unittest.TestCase):
    def test_after_run_counts_the_session_in_progress_335(self):
        self.assertIn("`after_run`은 줄일 때 진행 중이던 세션에서 마친 판 수", changes_section(SECTION))
        self.assertIn("세션 사이에 줄였으면 0", changes_section(SECTION))   # 진행 중인 세션이 없을 때
        bad = {"players": 1, "runs": 6, "reduced_from": {"runs": 9}}
        self.assertIn("진행 중이던 세션", cc.sample_problem(bad))

    def test_runs_before_the_cut_in_the_same_session_count_336(self):
        self.assertIn("줄인 세션 안에서 줄이기 전에 한 판은 센다", changes_section(SECTION))


class RefillPeriod(unittest.TestCase):
    def test_reuse_a_period_already_set_and_say_whose_it_is_337(self):
        part = step(3)
        self.assertIn("사용자가 정한 주기가 조우의 `note`에 있으면 그 값을 쓴다", part)
        for words in ("거꾸로 낸 주기", "계산으로만 나오는 주기", "어디서 온 값인지 보고한다"):   # 가정·역산 값은 다시 쓰지 않고 묻는다
            with self.subTest(words=words):
                self.assertIn(words, part)

    def test_split_encounters_share_one_period_337(self):
        self.assertIn("같은 주기를 나눠 가진다", shapes("적이 끊임없이 나오는 게임"))

    def test_back_derived_repeats_are_reported_338(self):
        self.assertIn("이미 거꾸로 나눠 정한 `repeat`가 있으면", step(3))


class ReplacingPartOfASpan(unittest.TestCase):
    def test_the_time_span_section_says_how_339(self):
        part = shapes("적이 끊임없이 나오는 게임")
        self.assertIn("구간 일부를 다른 조우로 바꿀 때", part)
        self.assertIn("조건부 조우의 몫을 뺀다", part)   # 정예가 끼는 무리를 두 번 세지 않는다
        self.assertIn("합이 원래 구간 길이 ÷ 주기와 같은지", part)
        self.assertIn("겹치는 조건부 조우", part)


class RoleChange(unittest.TestCase):
    def test_role_follows_the_use_not_the_warning_340(self):
        row = next(line for line in level_format().splitlines() if line.startswith("| `over_budget`, `under_budget` |"))
        self.assertIn("역할은 그 조우의 쓰임에 맞춘다", row)
        self.assertIn("경고를 없애려고 역할을 바꾸지 않는다", row)


if __name__ == "__main__":
    unittest.main()
