"""399: 사용자 답을 기다리며 멈출 때 이어 갈 일을 continue.md에 적어 새 대화로 싸게 이어 간다.
문서만 바꾼 이슈라 문서의 틀과 연결을 본다. 표준 라이브러리 unittest만 사용한다."""
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from _studio import ROOT

SKILLS = ROOT / "skills"
PAGE = SKILLS / "studio-data/references/telling-the-user.md"
LINK = "studio-data/references/telling-the-user.md#새-대화로-이어-가기"


def read(path):
    return path.read_text(encoding="utf-8")


def section(text, title):
    start = text.index(title)
    rest = text[start + len(title):]
    nxt = re.search(r"^## ", rest, re.M)
    return rest[:nxt.start()] if nxt else rest


def template(part):
    """노트 틀의 줄들. 첫 줄이 제목이다."""
    body = part[part.index("```text") + len("```text"):]
    return [line for line in body[:body.index("```")].splitlines() if line.strip()]


class ContinueNote(unittest.TestCase):
    def test_page_has_the_note_and_its_lines(self):
        part = section(read(PAGE), "## 새 대화로 이어 가기")
        self.assertIn("`continue.md`", part)
        for line in ("하던 일", "정할 것", "정한 뒤 할 일", "이미 한 것", "먼저 읽을 것", "일하던 파일"):
            self.assertIn(line, part, line)

    def test_note_says_when_where_and_when_to_remove(self):
        part = section(read(PAGE), "## 새 대화로 이어 가기")
        self.assertIn("프로젝트 맨 위", part)        # design/ 아래면 숫자 출처 검사가 경고한다
        self.assertIn("임시 폴더", part)             # 대화의 임시 폴더는 다음 대화가 못 찾거나 지워진다
        self.assertIn("지운다", part)                # 다 하면 지워 낡은 노트가 남지 않는다
        self.assertIn("새 대화", part)
        self.assertIn("같은 대화", part)            # 같은 대화에서 답해도 노트를 정리한다

    def test_note_carries_its_own_pickup_steps(self):
        # 사용자는 'continue.md 이어서'만 보낸다. 새 대화가 스킬 문서를 못 읽어도 노트만으로 이어 받는다
        block = template(section(read(PAGE), "## 새 대화로 이어 가기"))
        pickup = block[1]
        for word in ("이어 받는 법", "<스킬>", "먼저 읽을 것", "바뀌었으면", "지운다", "고쳐 쓴다"):
            self.assertIn(word, pickup, word)

    def test_note_header_has_time_and_zone(self):
        # 같은 날 사이에 바뀐 파일을 가리려면 날짜만으로는 모자란다
        header = template(section(read(PAGE), "## 새 대화로 이어 가기"))[0]
        self.assertIn("시각", header)
        self.assertIn("시간대", header)

    def test_work_files_have_a_fixed_folder_and_fate(self):
        part = section(read(PAGE), "## 새 대화로 이어 가기")
        self.assertIn("`reports/work/`", part)      # 계획 폴더라 범위 훅이 막지 않고 게임 코드와 섞이지 않는다
        work = next(line for line in template(part) if line.startswith("- 일하던 파일"))
        self.assertIn("지울지", work)

    def test_report_tells_the_user_what_to_send(self):
        part = section(read(PAGE), "## 새 대화로 이어 가기")
        self.assertIn("continue.md 이어서", part)

    def test_decision_section_points_at_the_note(self):
        decisions = section(read(PAGE), "## 정할 것")
        self.assertIn("새 대화로 이어 가기", decisions)

    def test_user_guide_mentions_the_cheaper_way(self):
        guide = read(ROOT / "docs/guide.md")
        self.assertIn(LINK, guide)
        self.assertIn("continue.md", guide)

    def test_root_note_does_not_trigger_the_edit_hook(self):
        # 노트에 숫자가 있어도 데이터 검사나 숫자 출처 검사가 돌지 않는다
        from studio_data import claude
        temp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, temp)
        (temp / "design").mkdir()
        note = temp / "continue.md"
        note.write_text("# 이어 갈 일\n- 정할 것: 판 시간 하한 3분, 퍼즐 9개\n", encoding="utf-8")
        payload = {"session_id": "s", "cwd": str(temp), "tool_name": "Write",
                   "tool_input": {"file_path": str(note), "content": read(note)}}
        self.assertEqual(claude.post_edit(json.dumps(payload), temp), (0, "", ""))


if __name__ == "__main__":
    unittest.main()
