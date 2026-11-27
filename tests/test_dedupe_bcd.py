"""411 정리 B·C·D를 먼저 검토해 찾은 세 건. 표준 라이브러리 unittest만 사용한다."""
import unittest

from _studio import ROOT

SKILLS = ROOT / "skills"


def read(rel):
    return (SKILLS / rel).read_text(encoding="utf-8")


class Review(unittest.TestCase):
    def test_every_data_gate_suffix_has_a_route_1(self):
        from _studio import playtests as pt
        alpha = read("production-milestones/SKILL.md").split("### 1.", 1)[1].split("\n### ", 1)[0]
        for label in pt.DATA_GATE_REASON.values():
            self.assertIn(f"({label})", alpha, label)

    def test_delegated_ack_rule_lives_in_studio_data_2(self):
        ack = next(l for l in read("studio-data/SKILL.md").splitlines() if l.startswith("- **확인한 경고.**"))
        self.assertIn("맡겼으면 확인으로 본다", ack)
        self.assertNotIn("맡겼으면 확인으로 본다", read("stat-budget/SKILL.md"))

    def test_studio_data_stays_small_and_scope_env_lives_in_scope_guard_3(self):
        text = read("studio-data/SKILL.md")
        self.assertLess(len(text.encode("utf-8")), 20000)
        self.assertNotIn("범위 훅의 확인 범위: Claude Code", text)
        self.assertIn("../scope-guard/SKILL.md#한계", text)
        limits = read("scope-guard/SKILL.md").split("## 한계", 1)[1]
        self.assertIn("OpenSpec 1.16.0", limits)
        self.assertIn("가상 터미널", limits)


if __name__ == "__main__":
    unittest.main()
