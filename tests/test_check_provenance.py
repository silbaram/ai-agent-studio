"""수치 출처 태그 검사기 테스트. 표준 라이브러리 unittest만 사용한다."""
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from _studio import ROOT, provenance as cp, run_cli as studio_cli


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
        self.assertEqual(r.counts, {"assumed": 2, "computed": 1, "measured": 1})
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
        self.assertEqual(r.counts, {"assumed": 1, "computed": 1, "measured": 0})

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
        self.assertEqual(data["summary"]["counts"], {"assumed": 1, "computed": 0, "measured": 1})

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
