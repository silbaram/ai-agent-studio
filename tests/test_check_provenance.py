"""수치 출처 태그 검사기 테스트. 표준 라이브러리 unittest만 사용한다."""
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from _studio import ROOT, concepts as cc, provenance as cp, run_cli as studio_cli


def errors(report):
    return [f.message for f in report.findings if f.level == "error"]


class TagParsing(unittest.TestCase):
    def test_counts_each_kind_including_english_aliases(self):
        r = cp.check_text(
            "포션 가격 50 [가정]\n"
            "드랍률 5% [계산: sim/drop.json]\n"
            "클리어 시간 12분 [측정: playtest-003]\n"
            "price 40 [assumed: genre norm]\n"
        )
        self.assertEqual(r.counts, {"assumed": 2, "computed": 1, "measured": 1, "decided": 0})
        self.assertEqual(errors(r), [])

    def test_computed_and_measured_require_source(self):
        r = cp.check_text("공격력 10 [계산]\n체력 100 [측정:  ]\n")
        self.assertEqual(len(errors(r)), 2)
        self.assertEqual(r.counts["computed"], 0)

    def test_assumed_source_is_optional(self):
        r = cp.check_text("값 3 [가정]\n값 4 [가정: 장르 평균 추정]\n")
        self.assertEqual(r.counts["assumed"], 2)
        self.assertEqual(errors(r), [])

    def test_malformed_tag_without_colon_is_error(self):
        r = cp.check_text("값 3 [가정 장르 평균]\n")
        self.assertEqual(len(errors(r)), 1)
        self.assertIn("형식", errors(r)[0])

    def test_fullwidth_colon_is_accepted(self):
        r = cp.check_text("값 3 [계산：sim/a.json]\n")
        self.assertEqual(r.counts["computed"], 1)
        self.assertEqual(errors(r), [])

    def test_code_blocks_and_inline_code_are_ignored(self):
        r = cp.check_text("```\n[계산]\n```\n설명: `[측정]` 처럼 씁니다.\n")
        self.assertEqual(errors(r), [])
        self.assertEqual(sum(r.counts.values()), 0)

    def test_unrelated_brackets_are_ignored(self):
        r = cp.check_text("[링크](https://example.com) [가정적인 문장](x) [TODO]\n")
        self.assertEqual(errors(r), [])


class ProvenanceTables(unittest.TestCase):
    TABLE = (
        "| 항목 | 값 | 출처 |\n"
        "| --- | ---: | --- |\n"
        "| 포션 가격 | 50 | [가정] |\n"
        "| 드랍률 | 5% | [계산: sim/drop.json] |\n"
        "{extra}"
    )

    def test_every_row_needs_a_tag_in_provenance_column(self):
        r = cp.check_text(self.TABLE.format(extra="| 보스 체력 | 900 | 감으로 |\n"))
        msgs = errors(r)
        self.assertEqual(len(msgs), 1)
        self.assertIn("보스 체력", msgs[0])

    def test_complete_table_passes(self):
        r = cp.check_text(self.TABLE.format(extra=""))
        self.assertEqual(errors(r), [])
        self.assertEqual(r.counts, {"assumed": 1, "computed": 1, "measured": 0, "decided": 0})

    def test_english_source_header_and_missing_cell(self):
        text = "| item | value | Source |\n|---|---|---|\n| sword | 10 |\n"
        r = cp.check_text(text)
        self.assertEqual(len(errors(r)), 1)

    def test_table_without_provenance_column_is_not_enforced(self):
        text = "| 항목 | 값 |\n|---|---|\n| 포션 | 50 |\n"
        self.assertEqual(errors(cp.check_text(text)), [])

    def test_escaped_pipe_inside_cell(self):
        text = "| 항목 | 출처 |\n|---|---|\n| a \\| b | [가정] |\n"
        self.assertEqual(errors(cp.check_text(text)), [])

    def test_table_ends_at_non_table_line(self):
        text = "| 항목 | 출처 |\n|---|---|\n| a | [가정] |\n\n| 다른 | 표 |\n|---|---|\n| x | y |\n"
        self.assertEqual(errors(cp.check_text(text)), [])


class BodyNumbers(unittest.TestCase):
    """본문 수치는 줄이 아니라 수치마다 태그를 본다. 한 줄의 태그 하나가 다른 수치를 통과시키지 않는다."""

    def warned(self, text):
        return [f.message for f in cp.check_text(text).findings if f.level == "warning"]

    def test_one_tag_does_not_pass_other_numbers_on_the_line(self):
        w = self.warned("체력 100hp [가정], 공격 쿨타임 3초, 속도 5배.\n")
        self.assertEqual(len(w), 1)
        self.assertIn("3초", w[0])
        self.assertIn("5배", w[0])
        self.assertNotIn("100hp", w[0])

    def test_tag_must_follow_the_number_before_the_next_number(self):
        self.assertEqual(len(self.warned("[가정] 부화는 6초, 숙성은 8초다.\n")), 1)
        w = self.warned("설정마다 5분 [가정] 플레이, 본인 3판 + 지인 2명 [가정: 1인 개발].\n")
        self.assertEqual(len(w), 1)
        self.assertIn("3판", w[0])
        self.assertNotIn("2명", w[0])

    def test_every_number_tagged_passes(self):
        self.assertEqual(self.warned("부화는 6초 [가정], 숙성은 8초 [가정: 웨이브 간격]이다.\n"), [])

    def test_numbers_inside_a_tag_are_part_of_the_source(self):
        self.assertEqual(self.warned("클리어 7분 [측정: playtest-2026-11-03 3명 평균]\n"), [])

    def test_brief_criterion_with_one_untagged_threshold_is_warned(self):
        sample = json.loads((ROOT / "skills/studio-data/assets/sample-project/design/concepts.json").read_text(encoding="utf-8"))
        c = next(x for x in sample["concepts"] if x["status"] == "approved")
        c["brief"]["hypotheses"] = [{"id": "h1", "claim": "c", "failure_signal": "80% [가정] 이상이거나 사망의 50% 이상", "test": "t", "sample": {"runs": 5}}]
        r = cc.validate({"concepts": [c]})
        self.assertEqual([w["code"] for w in r["warnings"]], ["untagged_number"])
        self.assertIn("50%", r["warnings"][0]["message"])


class CommandLine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        (self.dir / "sim").mkdir()
        (self.dir / "sim" / "drop.json").write_text("{}", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        return studio_cli("provenance", *args)

    def write(self, name, text):
        path = self.dir / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_assumed_passes_by_default_but_fails_gate(self):
        doc = self.write("a.md", "값 3 [가정]\n")
        self.assertEqual(self.run_cli(str(doc))[0], 0)
        code, out = self.run_cli(str(doc), "--fail-on-assumed")
        self.assertEqual(code, 1)
        self.assertIn("gate", out)

    def test_errors_fail_without_gate(self):
        doc = self.write("a.md", "값 3 [계산]\n")
        self.assertEqual(self.run_cli(str(doc))[0], 1)

    def test_directory_is_scanned_recursively(self):
        (self.dir / "sub").mkdir()
        self.write("sub/b.md", "값 [측정: playtest-1]\n")
        self.write("c.md", "값 [가정]\n")
        code, out = self.run_cli(str(self.dir), "--json")
        data = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(data["summary"]["files"], 2)
        self.assertEqual(data["summary"]["counts"], {"assumed": 1, "computed": 0, "measured": 1, "decided": 0})

    def test_check_paths_resolves_relative_to_document(self):
        ok = self.write("ok.md", "값 [계산: sim/drop.json]\n")
        bad = self.write("bad.md", "값 [계산: sim/missing.json]\n")
        self.assertEqual(self.run_cli(str(ok), "--check-paths")[0], 0)
        code, out = self.run_cli(str(bad), "--check-paths")
        self.assertEqual(code, 1)
        self.assertIn("missing.json", out)

    def test_non_path_source_is_not_checked(self):
        doc = self.write("a.md", "값 [측정: 2026-11 플레이테스트 3회차]\n")
        self.assertEqual(self.run_cli(str(doc), "--check-paths")[0], 0)

    def test_missing_path_is_usage_error(self):
        self.assertEqual(self.run_cli(str(self.dir / "nope.md"))[0], 2)


class RepositoryDocs(unittest.TestCase):
    def test_repository_markdown_has_no_provenance_errors(self):
        reports = cp.check_paths_cli([str(ROOT / "skills"), str(ROOT / "docs"), str(ROOT / "README.md")])
        problems = [f"{r.path}:{f.line}: {f.message}" for r in reports for f in r.findings if f.level == "error"]
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
