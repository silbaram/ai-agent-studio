"""기준 이력 남기기 현장 시험(2026-11-10)의 이슈 328~329 테스트. 표준 라이브러리 unittest만 사용한다.

328: 고칠 때 남기지 못한 이력을 나중에 남기는 법(날짜, 고치기 전 값과 지문을 가져올 곳, cut 판정)을 문서가 정한다.
329: 판정 기준 문장이 게임 데이터 파일을 가리키면(\"값은 data/growth.json의 …\") 검사기가 경고한다."""
import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from _studio import ROOT, SAMPLE, STUDIO, common, concepts as cc, run_cli
from test_criteria_history_297 import entry
from test_verdict_field import CONCEPTS, approved, hyp

CODE = "criteria_points_to_data"
REAL = ("보석 깨짐 규칙과 tune-levelup-power 수치(값은 data/growth.json의 sharp_bolt, quick_draw)에 체감 기록을 넣은 "
        "회색 상자 빌드의 판만 센다")


def changed(field: str, text: str, where=None) -> dict:
    data = copy.deepcopy(CONCEPTS)
    (where or hyp)(data)[field] = text
    return data


def pointers(data: dict, root=SAMPLE) -> list:
    return [w for w in cc.validate(data, root=root)["warnings"] if w["code"] == CODE]


def proto(data):
    return approved(data)["brief"]["prototype"]


class PointsToData(unittest.TestCase):
    """329. 데이터 파일은 다음 조정에서 바뀌어, 그 파일을 가리키는 판정 기준 문장은 다른 빌드를 가리키게 된다."""

    def test_the_real_record_sentence_warns(self):
        found = pointers(changed("test", REAL))
        self.assertEqual([w["part"] for w in found], ["data/growth.json"])
        msg = found[0]["message"]
        self.assertIn("learn_timing", msg)
        self.assertIn("builds", msg)
        self.assertIn("판정한 가설의 문장을 고칠 때", msg)
        self.assertIn(CODE, msg)   # 그대로 둘 때 적을 확인

    def test_each_criteria_field_is_checked(self):
        for field in ("claim", "failure_signal", "test"):
            with self.subTest(field=field):
                self.assertEqual(len(pointers(changed(field, hyp(CONCEPTS)[field] + " 값은 data/enemies.json을 따른다"))), 1)
        self.assertEqual(len(pointers(changed("success_criteria", "data/items.json의 값으로 본다", proto))), 1)

    def test_a_data_file_is_known_by_its_content(self):   # 이름이 종류가 아니어도 데이터 파일이면 경고한다
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(SAMPLE / "data", root / "data")
            shutil.copy(root / "data/growth.json", root / "data/tuning.json")
            self.assertEqual(len(pointers(changed("test", "강화 값은 data/tuning.json이다"), root)), 1)

    def test_without_the_file_the_name_decides(self):
        self.assertEqual(len(pointers(changed("test", "값은 data/upgrades.json을 따른다"), None)), 1)
        self.assertEqual(len(pointers(changed("test", "값은 data\\growth.json을 따른다"), None)), 1)   # Windows 경로
        self.assertEqual(pointers(changed("test", "결과는 reports/levelup_out.json에 남는다"), None), [])

    def test_records_and_design_files_do_not_warn(self):   # 판정 기록·컨셉·시스템 설계는 빌드가 아니다
        for path in ("data/playtests.json", "design/concepts.json", "design/systems.json", "data/meta.json"):
            with self.subTest(path=path):
                self.assertEqual(pointers(changed("test", f"기록은 {path}에서 읽는다")), [])

    def test_a_source_tag_is_not_a_pointer(self):   # 태그 안의 경로는 출처다. 출처 검사가 따로 본다
        found = pointers(changed("test", hyp(CONCEPTS)["test"] + " 기준선 12% [계산: data/growth.json]"))
        self.assertEqual(found, [])

    def test_scope_and_history_do_not_warn(self):
        data = changed("scope", "data/growth.json의 강화 셋만 넣는다", proto)
        self.assertEqual(pointers(data), [])
        data = copy.deepcopy(CONCEPTS)
        hyp(data)["criteria_history"] = [entry({"test": REAL})]
        self.assertEqual(pointers(data), [])

    def test_the_same_file_twice_in_a_sentence_warns_once(self):
        self.assertEqual(len(pointers(changed("test", "data/growth.json의 sharp_bolt와 data/growth.json의 quick_draw"))), 1)

    def test_it_can_be_acknowledged_per_file(self):
        data = changed("test", REAL)
        approved(data)["acknowledged"] = {CODE: {"data/growth.json": "판정한 문장이라 사용자와 정해 둔다"}}
        report = cc.validate(data, root=SAMPLE)
        common.apply_acknowledged("concepts", data, report)
        self.assertNotIn(CODE, [w["code"] for w in report["warnings"]])
        self.assertIn(CODE, [w["code"] for w in report["acknowledged"]])

    def test_it_does_not_hold_the_gate(self):   # 가정값이 아니다. 게이트는 그대로다
        base = cc.validate(copy.deepcopy(CONCEPTS), root=SAMPLE)["unverified"]
        self.assertEqual(cc.validate(changed("test", hyp(CONCEPTS)["test"] + " 값은 data/growth.json"), root=SAMPLE)["unverified"], base)

    def test_the_sample_project_has_none(self):
        self.assertEqual(pointers(copy.deepcopy(CONCEPTS)), [])


class ReviewFixes(unittest.TestCase):
    """검토에서 나온 것: 게임 고유 형식의 파일, 같은 파일의 다른 꼴, 깨진 파일, 바뀐 파일, 실제 명령의 출력."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "game"
        shutil.copytree(SAMPLE, self.root)

    def write(self, rel: str, text: str) -> None:
        (self.root / rel).write_text(text, encoding="utf-8")

    def parts(self, text: str) -> list:
        return [w["part"] for w in pointers(changed("test", text), self.root)]

    def test_a_game_own_format_file_is_known_by_its_name(self):   # 이 도구의 형식이 아니어도 이름이 데이터 종류면 게임 데이터다
        self.write("data/items.json", '{"weapons": [{"id": "bolt", "dmg": 10}]}')
        self.write("data/levels.json", '{"rooms": [{"id": "r1"}]}')
        self.write("data/notes.json", '{"weapons": []}')
        self.assertEqual(self.parts("값은 data/items.json의 bolt"), ["data/items.json"])
        self.assertEqual(self.parts("방은 data/levels.json을 따른다"), ["data/levels.json"])
        self.assertEqual(self.parts("메모는 data/notes.json에 있다"), [])

    def test_a_broken_file_is_known_by_its_name(self):
        self.write("data/growth.json", "{ 깨짐")
        self.write("data/notes.json", "{ 깨짐")
        self.assertEqual(self.parts("값은 data/growth.json의 값"), ["data/growth.json"])
        self.assertEqual(self.parts("메모는 data/notes.json에 있다"), [])

    def test_other_spellings_of_the_same_file_are_one_part(self):
        absolute = (self.root / "data/growth.json").as_posix()
        for text in ("값은 ./data/growth.json의 값", f"값은 {absolute}의 값", "값은 data/../data/growth.json의 값"):
            with self.subTest(text=text):
                self.assertEqual(self.parts(text), ["data/growth.json"])
        self.assertEqual(self.parts("data/growth.json과 ./data/growth.json"), ["data/growth.json"])

    def test_one_ack_covers_every_spelling(self):
        data = changed("test", "data/growth.json의 값")
        hyp(data)["failure_signal"] = hyp(CONCEPTS)["failure_signal"] + " ./data/growth.json의 값"
        approved(data)["acknowledged"] = {CODE: {"data/growth.json": "사용자와 정해 둔다"}}
        report = cc.validate(data, root=self.root)
        common.apply_acknowledged("concepts", data, report)
        self.assertNotIn(CODE, [w["code"] for w in report["warnings"]])
        self.assertEqual([w["code"] for w in report["acknowledged"]].count(CODE), 2)

    def test_a_changed_file_is_read_again(self):   # 같은 프로세스에서 검사를 거듭 돌려도(뷰어) 바뀐 파일의 종류를 다시 본다
        self.write("data/tuning.json", (self.root / "data/growth.json").read_text(encoding="utf-8"))
        self.assertEqual(self.parts("값은 data/tuning.json의 값"), ["data/tuning.json"])
        self.write("data/tuning.json", '{"notes": "다른 파일이 되었다, 길이도 다르다"}')
        self.assertEqual(self.parts("값은 data/tuning.json의 값"), [])

    def test_the_check_command_prints_it(self):
        data = changed("test", REAL)
        self.write("design/concepts.json", json.dumps(data, ensure_ascii=False))
        code, out = run_cli("check", self.root)
        self.assertIn(f"[{CODE}]", out)
        self.assertIn("data/growth.json", out)


class Docs(unittest.TestCase):
    def read(self, rel: str) -> str:
        return (ROOT / rel).read_text(encoding="utf-8")

    def section(self, text: str, head: str) -> str:
        part = text[text.index(head):]
        return part[:part.index("\n**", 5)]

    def test_the_verdict_skill_says_how_to_backfill_328(self):
        part = self.section(self.read("skills/playtest-verdict/SKILL.md"), "**이력을 나중에 남길 때.**")
        for words in ("고친 날", "^:design/concepts.json", "`cut`", "`why`", "오래된 것부터", "사용자에게 알린다", "`check`"):
            self.assertIn(words, part)

    def test_the_brief_points_to_the_backfill_328(self):
        brief = self.read("skills/concept-exploration/references/brief.md")
        row = next(line for line in brief.splitlines() if line.startswith("| `criteria_history`"))
        self.assertIn("이력을 나중에 남길 때", row)

    def test_the_new_warning_is_documented_329(self):
        brief = self.read("skills/concept-exploration/references/brief.md")
        rule = next(line for line in brief.splitlines() if line.startswith("- **세는 빌드는 이름으로 가리킨다.**"))
        self.assertIn(f"`{CODE}`", rule)
        self.assertIn(f"| `{CODE}` | 경고 |", self.read("skills/concept-exploration/references/concept-record.md"))
        self.assertIn(f"{CODE}:", (STUDIO / "assets/viewer.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
