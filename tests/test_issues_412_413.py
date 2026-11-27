"""412: Windows에서 studio.py 출력이 cp949로 나가 Bash 도구와 훅에서 한글이 깨졌다.
413: 콘텐츠 늘리기의 이어 감 판정 예시가 `<가설 id>_main`이라 `_main`이 꼭 붙는 것처럼 읽혔다.
표준 라이브러리 unittest만 사용한다."""
import json
import os
import subprocess
import sys
import unittest

from _studio import ROOT

STUDIO = ROOT / "skills/studio-data/scripts/studio.py"
GROWTH = ROOT / "skills/production-milestones/references/content-growth.md"
SAMPLE = ROOT / "skills/studio-data/assets/sample-project"


def run_with(encoding, *args):
    """표준 출력의 기본 인코딩이 encoding인 환경(Windows 파이프는 cp949)에서 studio.py를 돌린다."""
    env = dict(os.environ, PYTHONIOENCODING=encoding, PYTHONUTF8="0")
    return subprocess.run([sys.executable, str(STUDIO), *args], capture_output=True, env=env, timeout=120)


class OutputIsUtf8(unittest.TestCase):
    """412: 코드 페이지와 상관없이 UTF-8로 쓴다."""

    def test_stdout_is_utf8_under_cp949(self):
        r = run_with("cp949", "check", str(SAMPLE))
        text = r.stdout.decode("utf-8")   # cp949 바이트면 여기서 깨진다
        self.assertIn("전체:", text)

    def test_stdout_keeps_korean_under_ascii(self):
        r = run_with("ascii", "check", str(SAMPLE))
        self.assertIn("전체:", r.stdout.decode("utf-8"))
        self.assertNotIn("??", r.stdout.decode("utf-8").split("전체:", 1)[1])

    def test_stderr_is_utf8_too(self):
        r = run_with("cp949", "hypothesis", "없는컨셉.없는가설", str(SAMPLE))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("없는 가설입니다", r.stderr.decode("utf-8"))

    def test_judge_guard_block_message_is_utf8(self):
        payload = json.dumps({"agent_type": "studio-judge", "tool_name": "Bash",
                              "tool_input": {"command": "PYTHONIOENCODING=utf-8 py studio.py check ."}})
        env = dict(os.environ, PYTHONIOENCODING="cp949", PYTHONUTF8="0")
        r = subprocess.run([sys.executable, str(STUDIO), "hook", "judge-guard"], input=payload.encode("utf-8"),
                           capture_output=True, env=env, timeout=60)
        self.assertEqual(r.returncode, 2)
        self.assertIn("판정 에이전트는", r.stderr.decode("utf-8"))


class CarriedExample(unittest.TestCase):
    """413: 이어 간 판정의 가설 id는 사람이 플레이한 판정 그대로다."""

    def test_example_does_not_force_main_suffix(self):
        text = GROWTH.read_text(encoding="utf-8")
        self.assertNotIn('"<가설 id>_main"', text)
        self.assertIn('"hypothesis": "<가설 id>"', text)

    def test_step_says_hypothesis_stays_the_same(self):
        step = GROWTH.read_text(encoding="utf-8").split("3. **사용자가 정한다.**", 1)[1].split("\n", 1)[0]
        self.assertIn("가설(`hypothesis`", step)
        self.assertIn("_main", step)


if __name__ == "__main__":
    unittest.main()
