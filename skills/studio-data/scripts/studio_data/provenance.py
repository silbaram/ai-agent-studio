"""설계 문서(md)의 수치 출처 태그를 검사한다. 규약: numeric-provenance/SKILL.md"""
from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .common import DECIDED_SOURCE, PATH_KINDS, SOURCED_KINDS
from .common import PROVENANCE_KINDS as KINDS   # 데이터 필드와 같은 종류·별칭

SOURCE_REQUIRED = set(SOURCED_KINDS)
SOURCE_KINDS = ("assumed", "computed", "measured", "decided")   # 개수를 세는 순서
PROVENANCE_HEADERS = {"출처", "source", "provenance"}
NEAR_HEADER = re.compile(r"출처|\bsource\b|\bprovenance\b", re.IGNORECASE)
SOURCE_EXAMPLE = {"computed": "reports/meta.json", "measured": "playtest-2026-11-02", "decided": "사용자 2026-11-09"}
# 본문에서 조정 가능한 값으로 보이는 '숫자 + 단위'. 경고만 낸다(추정이므로 오류로 막지 않는다). 순서(5판째, 3번째)는 값이 아니라 뺀다
NUMBER_UNIT = re.compile(
    r"(?<![\w.])\d+(?:\.\d+)?\s?(?:%|％|퍼센트|초|분|시간|일|주|배|칸|타일|프레임|회|번|개|종|명|골드|코인|레벨|층|방|웨이브|판|런|스택|건"
    r"|(?:px|ms|hp|HP|fps)(?![A-Za-z]))(?!째)")
BARE_NUMBER = re.compile(r"(?<![\w.])-?\d+\.\d+(?![0-9A-Za-z_.%％])|(?<![\w.])-\d+(?![0-9A-Za-z_.%％])")  # 단위 없는 소수와 음수(상관 0.2, -0.2보다). 판정 기준 문장에서만 본다
RANGE_GAP = re.compile(r"\s*[~～–—-]\s*")   # 범위의 두 수 사이
RANGE_HEAD = re.compile(r"-?\d+(?:\.\d+)?\s*[~～–—-]\s*$")   # 범위의 앞 수(4~9%의 4~)
NAMED_BRACKET = re.compile(r"\[([^\[\]:：\s]{1,12})\s*[:：]")
LINK_TARGET = re.compile(r"\]\([^)]*\)")

_KIND_ALT = "|".join(sorted(KINDS, key=len, reverse=True))
STRICT_TAG = re.compile(rf"\[({_KIND_ALT})(?:\s*[:：]\s*([^\]]*))?\]")
LOOSE_TAG = re.compile(rf"\[({_KIND_ALT})(?![\w])[^\]]*\]")
FENCE = re.compile(r"^\s*(```|~~~)")
INLINE_CODE = re.compile(r"`[^`]*`")
TABLE_SEP_CELL = re.compile(r"^:?-{3,}:?$")
TAG_CHOICES = "[가정] / [계산: 출처] / [측정: 출처] / [결정: 누가 날짜](사용자가 정한 잣대)"
PATHLIKE = re.compile(r"^[\w./\\-]+\.(py|json|csv|tsv|yaml|yml|md|txt|log)(#\S*)?$|[/\\]")


@dataclass
class Tag:
    kind: str
    source: str
    line: int
    value: str = ""   # 태그 바로 앞의 수치(60초, -0.2, 4~9%). 수치 뒤가 아니면 빈칸
    near: str = ""    # 보일 말: 수치, 아니면 태그 앞의 두 낱말(…강화만 센다)


@dataclass
class Finding:
    level: str  # "error" | "warning"
    line: int
    message: str


@dataclass
class FileReport:
    path: str
    counts: dict = field(default_factory=lambda: dict.fromkeys(SOURCE_KINDS, 0))
    tags: list = field(default_factory=list)
    findings: list = field(default_factory=list)
    untagged: list = field(default_factory=list)   # 태그 없는 수치(경고에 보인 것 전부)

    @property
    def errors(self) -> int:
        return sum(1 for f in self.findings if f.level == "error")

    @property
    def warnings(self) -> int:
        return sum(1 for f in self.findings if f.level == "warning")


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


def _before_tag(head: str, tail: str = "") -> tuple[str, str]:
    """태그 앞 글(앞 태그 뒤부터)에서 (태그 바로 앞의 수치, 보일 말). 수치가 바로 앞에 없으면 앞의 두 낱말을,
    앞에 낱말이 없으면(문장 맨 앞의 태그) 뒤 글(tail)의 두 낱말을 보인다."""
    m = next((m for m in [*NUMBER_UNIT.finditer(head), *BARE_NUMBER.finditer(head)] if not head[m.end():].strip()), None)
    if m:   # 바로 앞에서 끝나는 수치는 하나뿐이다(단위 없는 소수는 단위 앞에서 끝나지 않는다)
        r = RANGE_HEAD.search(head[:m.start()])
        value = head[r.start() if r else m.start():m.end()].replace(" ", "")
        return value, value
    words = head.split()
    if words:
        return "", "…" + " ".join(words[-2:])[-12:]
    after = STRICT_TAG.sub(" ", tail).split()
    return "", (" ".join(after[:2])[:12] + "…") if after else "태그만 있음"


def _parse_tags(text: str, line: int, report: FileReport, base_dirs: list[Path], check_paths: bool) -> None:
    strict_spans = []
    for m in STRICT_TAG.finditer(text):
        kind = KINDS[m.group(1)]
        source = (m.group(2) or "").strip()
        value, near = _before_tag(text[strict_spans[-1][1] if strict_spans else 0:m.start()], text[m.end():])
        strict_spans.append(m.span())
        if kind in SOURCE_REQUIRED and not source:
            report.findings.append(Finding("error", line, f"'{m.group(0)}' 태그에 출처가 없습니다. 예: [{m.group(1)}: {SOURCE_EXAMPLE[kind]}]"))
            continue
        if kind == "decided" and not DECIDED_SOURCE.search(source):
            report.findings.append(Finding("error", line, f"'{m.group(0)}' 태그에 정한 날짜가 없습니다. 예: [{m.group(1)}: {SOURCE_EXAMPLE[kind]}]. 에이전트가 짐작한 값은 [가정]입니다."))
            continue
        if check_paths and kind in PATH_KINDS and PATHLIKE.search(source):
            target, _, anchor = (part.strip() for part in source.partition("#"))
            found = next((b / target for b in base_dirs if (b / target).exists()), None)
            if found is None:
                report.findings.append(Finding("error", line, f"출처 경로를 찾을 수 없습니다: {target}"))
            elif anchor:
                missing = _missing_session(found, anchor.split()[0])
                if missing:
                    report.findings.append(Finding("error", line, missing))
        report.counts[kind] += 1
        report.tags.append(Tag(kind, source, line, value, near))
    for m in LOOSE_TAG.finditer(text):
        if not any(s <= m.start() < e for s, e in strict_spans):
            report.findings.append(Finding("error", line, f"태그 형식이 잘못되었습니다: '{m.group(0)}'. 콜론으로 출처를 구분하세요. 예: [가정: 메모]"))
    for m in NAMED_BRACKET.finditer(text):
        guess = _tag_typo(m.group(1))
        if guess:
            report.findings.append(Finding("error", line, f"알 수 없는 태그 이름 '[{m.group(1)}:'. '{guess}'의 오타인가요?"))


def _missing_session(path: Path, sid: str) -> str | None:
    """출처가 플레이 기록 파일#세션 id이면 그 세션이 기록에 있는지 본다. 플레이 기록이 아닌 파일은 보지 않는다."""
    if path.suffix.lower() != ".json" or not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    if not (isinstance(data, dict) and isinstance(data.get("playtests"), list)):
        return None
    if any(isinstance(s, dict) and s.get("id") == sid for s in data["playtests"]):
        return None
    return f"플레이 기록 {path.name}에 없는 세션입니다: {sid}. 측정값은 기록된 세션만 출처로 씁니다."


def _tag_typo(name: str) -> str | None:
    """태그 이름이 아닌데 태그 이름과 비슷하면(예: 게산) 가장 비슷한 이름을 돌려준다."""
    if name in KINDS:
        return None
    close = difflib.get_close_matches(name, list(KINDS), n=1, cutoff=0.5)
    return close[0] if close else None


def _has_tag(text: str) -> bool:
    return bool(STRICT_TAG.search(text) or LOOSE_TAG.search(text))


def _check_body_numbers(text: str, line: int, report: FileReport, bare: bool = False) -> None:
    """표 밖 문장에서 태그 없는 '숫자 + 단위'를 경고한다. 수치마다 다음 수치 전까지 뒤따르는 태그가 있어야 한다.
    한 줄의 태그 하나가 같은 줄의 다른 수치를 통과시키지 않는다. 제목 줄과 태그 안의 숫자(출처 설명)는 보지 않는다.
    bare: 판정 기준 문장처럼 단위 없는 문턱값(상관 0.2, -0.2)도 수치로 볼 때."""
    if text.lstrip().startswith("#"):
        return
    text = LINK_TARGET.sub("]", text)
    tag_spans = [m.span() for m in LOOSE_TAG.finditer(text)] + [m.span() for m in STRICT_TAG.finditer(text)]
    found_nums = list(NUMBER_UNIT.finditer(text)) + (list(BARE_NUMBER.finditer(text)) if bare else [])
    nums = sorted((m for m in found_nums if not any(s <= m.start() < e for s, e in tag_spans)), key=lambda m: m.start())
    nums = [m for i, m in enumerate(nums) if not any(o.start() <= m.start() < o.end() for o in nums[:i])]   # 겹친 것(0.5배와 0.5)은 앞의 것 하나
    nums = [m for i, m in enumerate(nums) if not (i + 1 < len(nums) and RANGE_GAP.fullmatch(text[m.end():nums[i + 1].start()]))]   # 0.2~0.3은 수 하나다(뒤의 태그를 함께 쓴다)
    found = []
    for i, m in enumerate(nums):
        until = nums[i + 1].start() if i + 1 < len(nums) else len(text)
        if not _has_tag(text[m.end():until]):
            found.append(m.group(0).replace(" ", ""))
    if found:
        report.untagged.extend(found)
        shown = ", ".join(list(dict.fromkeys(found))[:5])   # 겹친 것을 먼저 빼야 뒤의 다른 수치가 가려지지 않는다
        report.findings.append(Finding("warning", line, f"태그 없는 수치: {shown}. 조정할 수 있는 값이면 {TAG_CHOICES}를 붙이세요."))


def check_text(text: str, path: str = "<text>", base_dirs: list[Path] | None = None, check_paths: bool = False, bare_numbers: bool = False) -> FileReport:
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
            _check_body_numbers(stripped, no, report, bare_numbers)
            continue
        nxt = lines[idx + 1] if idx + 1 < len(lines) else None
        if not in_table and nxt and nxt[0] == no + 1 and _is_separator(nxt[2]):
            in_table = True
            headers = [c.strip().lower() for c in _split_row(stripped)]
            prov_col = next((i for i, h in enumerate(headers) if h in PROVENANCE_HEADERS), None)
            if prov_col is None:
                for h in headers:
                    if NEAR_HEADER.search(h):
                        report.findings.append(Finding("warning", no, f"헤더 '{h}'는 출처 열로 인식되지 않아 이 표는 검사하지 않습니다. "
                                                                      "수치 표면 헤더를 정확히 '출처'(또는 source, provenance)로 쓰세요."))
                        break
            continue
        if _is_separator(stripped):
            continue
        if in_table and prov_col is not None:
            cells = _split_row(stripped)
            cell = cells[prov_col] if prov_col < len(cells) else ""
            if not STRICT_TAG.search(cell):
                label = cells[0] if cells and cells[0] else f"{no}행"
                if not any(_tag_typo(m.group(1)) for m in NAMED_BRACKET.finditer(cell)):  # 오타는 위에서 이미 보고했다
                    report.findings.append(Finding("error", no, f"출처 열에 태그가 없습니다: '{label}'. {TAG_CHOICES} 중 하나를 쓰세요."))
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
    total = dict.fromkeys(SOURCE_KINDS, 0)
    for r in reports:
        for k, v in r.counts.items():
            total[k] += v
    errors = sum(r.errors for r in reports)
    warnings = sum(r.warnings for r in reports)
    return {"files": len(reports), "counts": total, "errors": errors, "warnings": warnings}
