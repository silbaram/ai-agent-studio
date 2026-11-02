#!/usr/bin/env python3
"""설계 문서의 수치 출처 태그를 검사한다.

규약은 skills/numeric-provenance/SKILL.md를 따른다. 표준 라이브러리만 사용한다.

종료 코드
  0  문제 없음
  1  오류(형식 오류, 출처 열의 태그 누락, 경로 없음) 또는 --fail-on-assumed 조건 위반
  2  사용법 오류(경로 없음 등)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

KINDS = {
    "가정": "assumed",
    "assumed": "assumed",
    "계산": "computed",
    "computed": "computed",
    "측정": "measured",
    "measured": "measured",
}
SOURCE_REQUIRED = {"computed", "measured"}
PROVENANCE_HEADERS = {"출처", "source", "provenance"}

_KIND_ALT = "|".join(sorted(KINDS, key=len, reverse=True))
STRICT_TAG = re.compile(rf"\[({_KIND_ALT})(?:\s*[:：]\s*([^\]]*))?\]")
LOOSE_TAG = re.compile(rf"\[({_KIND_ALT})(?![\w])[^\]]*\]")
FENCE = re.compile(r"^\s*(```|~~~)")
INLINE_CODE = re.compile(r"`[^`]*`")
TABLE_SEP_CELL = re.compile(r"^:?-{3,}:?$")
PATHLIKE = re.compile(r"^[\w./\\-]+\.(py|json|csv|tsv|yaml|yml|md|txt|log)(#\S*)?$|[/\\]")


@dataclass
class Tag:
    kind: str
    source: str
    line: int


@dataclass
class Finding:
    level: str  # "error" | "warning"
    line: int
    message: str


@dataclass
class FileReport:
    path: str
    counts: dict = field(default_factory=lambda: {"assumed": 0, "computed": 0, "measured": 0})
    tags: list = field(default_factory=list)
    findings: list = field(default_factory=list)

    @property
    def errors(self) -> int:
        return sum(1 for f in self.findings if f.level == "error")


def _split_row(line: str) -> list[str]:
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    cells, cur, i = [], [], 0
    while i < len(body):
        ch = body[i]
        if ch == "\\" and i + 1 < len(body) and body[i + 1] == "|":
            cur.append("|")
            i += 2
            continue
        if ch == "|":
            cells.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
        i += 1
    cells.append("".join(cur).strip())
    return cells


def _is_separator(line: str) -> bool:
    if "|" not in line:
        return False
    cells = [c.replace(" ", "") for c in _split_row(line)]
    nonempty = [c for c in cells if c]
    return bool(nonempty) and all(TABLE_SEP_CELL.match(c) for c in nonempty)


def _visible_lines(text: str):
    """코드 블록과 인라인 코드를 뺀 (줄 번호, 원문, 검사용 텍스트)를 돌려준다."""
    in_fence = False
    for no, raw in enumerate(text.splitlines(), start=1):
        if FENCE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        yield no, raw, INLINE_CODE.sub("", raw)


def _parse_tags(text: str, line: int, report: FileReport, base_dirs: list[Path], check_paths: bool) -> None:
    strict_spans = []
    for m in STRICT_TAG.finditer(text):
        kind = KINDS[m.group(1)]
        source = (m.group(2) or "").strip()
        strict_spans.append(m.span())
        if kind in SOURCE_REQUIRED and not source:
            report.findings.append(Finding("error", line, f"'{m.group(0)}' 태그에 출처가 없습니다. 예: [{m.group(1)}: sim/run-001.json]"))
            continue
        if check_paths and kind in SOURCE_REQUIRED and PATHLIKE.search(source):
            target = source.split("#", 1)[0].strip()
            if not any((b / target).exists() for b in base_dirs):
                report.findings.append(Finding("error", line, f"출처 경로를 찾을 수 없습니다: {target}"))
        report.counts[kind] += 1
        report.tags.append(Tag(kind, source, line))
    for m in LOOSE_TAG.finditer(text):
        if not any(s <= m.start() < e for s, e in strict_spans):
            report.findings.append(Finding("error", line, f"태그 형식이 잘못되었습니다: '{m.group(0)}'. 콜론으로 출처를 구분하세요. 예: [가정: 메모]"))


def check_text(text: str, path: str = "<text>", base_dirs: list[Path] | None = None, check_paths: bool = False) -> FileReport:
    report = FileReport(path=path)
    base_dirs = base_dirs or [Path.cwd()]
    lines = list(_visible_lines(text))
    prov_col: int | None = None
    in_table = False
    for idx, (no, raw, visible) in enumerate(lines):
        _parse_tags(visible, no, report, base_dirs, check_paths)
        stripped = visible.strip()
        if not stripped.startswith("|"):
            in_table, prov_col = False, None
            continue
        nxt = lines[idx + 1] if idx + 1 < len(lines) else None
        if not in_table and nxt and nxt[0] == no + 1 and _is_separator(nxt[2]):
            in_table = True
            headers = [c.strip().lower() for c in _split_row(stripped)]
            prov_col = next((i for i, h in enumerate(headers) if h in PROVENANCE_HEADERS), None)
            continue
        if _is_separator(stripped):
            continue
        if in_table and prov_col is not None:
            cells = _split_row(stripped)
            cell = cells[prov_col] if prov_col < len(cells) else ""
            if not STRICT_TAG.search(cell):
                label = cells[0] if cells and cells[0] else f"{no}행"
                report.findings.append(Finding("error", no, f"출처 열에 태그가 없습니다: '{label}'. [가정] / [계산: 출처] / [측정: 출처] 중 하나를 쓰세요."))
    return report


def iter_markdown(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            files.extend(sorted(q for q in path.rglob("*.md") if q.is_file()))
        elif path.is_file():
            files.append(path)
        else:
            raise FileNotFoundError(p)
    return files


def check_paths_cli(paths: list[str], check_paths: bool = False) -> list[FileReport]:
    reports = []
    root = Path.cwd()
    for f in iter_markdown(paths):
        text = f.read_text(encoding="utf-8")
        reports.append(check_text(text, str(f), [f.parent, root], check_paths))
    return reports


def summarize(reports: list[FileReport]) -> dict:
    total = {"assumed": 0, "computed": 0, "measured": 0}
    for r in reports:
        for k, v in r.counts.items():
            total[k] += v
    errors = sum(r.errors for r in reports)
    return {"files": len(reports), "counts": total, "errors": errors}


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    parser = argparse.ArgumentParser(description="설계 문서의 수치 출처 태그를 검사합니다.")
    parser.add_argument("paths", nargs="+", help="검사할 .md 파일 또는 폴더")
    parser.add_argument("--fail-on-assumed", action="store_true", help="[가정] 태그가 하나라도 남아 있으면 실패합니다 (확정 판정 전 게이트).")
    parser.add_argument("--check-paths", action="store_true", help="[계산]/[측정] 출처가 경로처럼 보이면 실제 파일 존재를 확인합니다.")
    parser.add_argument("--json", action="store_true", help="결과를 JSON으로 출력합니다.")
    args = parser.parse_args(argv)

    try:
        reports = check_paths_cli(args.paths, args.check_paths)
    except FileNotFoundError as exc:
        print(f"경로를 찾을 수 없습니다: {exc}", file=sys.stderr)
        return 2

    summary = summarize(reports)
    gate_failed = args.fail_on_assumed and summary["counts"]["assumed"] > 0
    status = "fail" if summary["errors"] or gate_failed else "pass"

    if args.json:
        out = {
            "status": status,
            "summary": summary,
            "fail_on_assumed": args.fail_on_assumed,
            "files": [
                {
                    "path": r.path,
                    "counts": r.counts,
                    "assumed_lines": [t.line for t in r.tags if t.kind == "assumed"],
                    "findings": [asdict(f) for f in r.findings],
                }
                for r in reports
            ],
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        for r in reports:
            for f in r.findings:
                print(f"{r.path}:{f.line}: {f.level}: {f.message}")
            if args.fail_on_assumed:
                for t in r.tags:
                    if t.kind == "assumed":
                        print(f"{r.path}:{t.line}: gate: [가정]이 남아 있습니다.")
        c = summary["counts"]
        print(f"파일 {summary['files']}개 · 가정 {c['assumed']} · 계산 {c['computed']} · 측정 {c['measured']} · 오류 {summary['errors']} → {status.upper()}")
    return 0 if status == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
