"""범위 이탈 검사(scope-guard): OpenSpec 변경을 브리프와 시스템 설계에 대어 본다.

변경이 다루는 시스템은 .openspec.yaml의 한 줄에 적는다: x-studio-systems: {gems: 3f2a1b9c}. 값은 그때 규칙의 지문이다.
OpenSpec은 x- 키를 검사에서 허용하고 보관할 때도 그대로 둔다. 줄은 --link가 쓰므로 형식이 하나뿐이고 YAML 파서가 필요 없다.
OpenSpec의 폴더 구조를 아는 곳은 이 파일뿐이다.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path

from . import common as c
from . import datasets
from .common import add_issue as _err, did_you_mean

META = ".openspec.yaml"
KEY = "x-studio-systems"
LINE = re.compile(rf"^{KEY}:(.*(?:\n[ \t]+.*)*)$", re.MULTILINE)
DROPPED_KEY = "x-studio-dropped"   # 뺀 시스템의 지문. 다시 이으면 이 지문을 되살려 그 사이 바뀐 규칙을 놓치지 않는다
DROPPED = re.compile(rf"^{DROPPED_KEY}:(.*(?:\n[ \t]+.*)*)$", re.MULTILINE)
DROPPED_WHOLE = re.compile(rf"^{DROPPED_KEY}:.*(?:\n[ \t]+.*)*(?:\n|\Z)", re.MULTILINE)
PAIR = re.compile(r"^([a-z0-9_]+): ([0-9a-f]{8})$")
SKIP_SPECS = re.compile(r"^skip_specs:\s*true\s*$", re.MULTILINE)
SYSTEMS_FILE = Path("design/systems.json")
CHANGES = Path("openspec/changes")
RULE_REF = re.compile(r"(?<![A-Za-z0-9_./\\-])([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)(?![A-Za-z0-9_/\\-]|\.[A-Za-z0-9])")  # gems.ripen. 대문자로 써도 같은 규칙이다. 경로는 뺀다
FILE_EXTENSIONS = {"json", "md", "csv", "tsv", "txt", "log", "yaml", "yml", "toml", "ini", "cfg", "py", "js", "mjs", "ts", "tsx", "jsx", "html", "htm", "css",
                   "gd", "tscn", "tres", "cs", "cpp", "h", "hpp", "lua", "rs", "go", "java", "png", "jpg", "jpeg", "gif", "svg", "webp", "wav", "ogg", "mp3", "zip"}  # gems.json은 규칙이 아니다
LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s")
NON_GOALS = re.compile(r"^\s*(?:#+\s*|\*\*)?\s*non[- ]?goals\b", re.IGNORECASE)   # design.md의 "## Non-Goals"나 "**Non-Goals:**"
MEASURED = ("proposal.md", "tasks.md")  # 무엇을 만들지 적는 문서. design.md는 Non-Goals에 범위 밖을 적는 자리라 재지 않는다


def missing(root: Path) -> str | None:
    """검사할 수 없는 프로젝트면 그 이유. 둘 다 있어야 범위를 잴 수 있다."""
    if not (root / "openspec").is_dir():
        return "openspec 폴더가 없습니다. 게임 프로젝트에서 openspec init을 먼저 실행합니다."
    if not (root / SYSTEMS_FILE).is_file():
        return f"{SYSTEMS_FILE.as_posix()}이 없습니다. system-design으로 시스템을 먼저 적습니다."
    return None


def stamp(system: dict) -> str:
    """규칙의 지문. 순서와 메모가 바뀐 것은 규칙이 바뀐 것이 아니다."""
    rules = sorted((r["id"], unicodedata.normalize("NFC", r["text"])) for r in system.get("rules", []))
    return hashlib.sha256(json.dumps(rules, ensure_ascii=False).encode("utf-8")).hexdigest()[:8]


def _buildable(system: dict) -> bool:
    return system["scope"] == "mvp" and c.is_active(system)


def _design(root: Path) -> dict:
    """{systems: {id: 항목}, out_of_scope: 브리프의 범위 밖, errors}. 오류가 있으면 범위를 믿을 수 없으므로 뒤를 보지 않는다.
    check와 같은 폴더에서 찾되 시스템 설계와 컨셉만 검사한다. 훅이 편집마다 부른다."""
    design: dict = {"systems": {}, "out_of_scope": [], "errors": []}
    entries = datasets.validate_all([d for d in datasets.scan([root]) if d.get("kind") in ("systems", "concepts")])
    for d in entries:
        if not d["ok"]:
            _err(design["errors"], "design_unreadable", d["name"], f"{d['error']} 설계를 읽지 못해 범위를 잴 수 없습니다.")
    found = next((d for d in entries if d["ok"] and d["kind"] == "systems"), None)
    if design["errors"]:
        return design
    if found is None:
        _err(design["errors"], "design_unreadable", SYSTEMS_FILE.name, "시스템 설계 파일을 읽지 못해 범위를 잴 수 없습니다.")
        return design
    problems = [(d["name"], e) for d in entries if d["ok"] for e in d["report"]["errors"]]
    if problems:
        name, first = problems[0]
        _err(design["errors"], "design_invalid", name, f"설계에 오류 {len(problems)}개가 있어 범위를 믿을 수 없습니다. 첫 오류: [{first['code']}] {first['message']} studio.py check로 고칩니다.")
        return design
    report = found["report"]
    if report["brief_out_of_scope"] is None:
        _err(design["errors"], "design_unreadable", found["name"], "브리프를 읽지 못해 범위를 잴 수 없습니다. concept-exploration으로 브리프를 씁니다.")
        return design
    design["systems"] = {s["id"]: s for s in found["data"]["systems"]}
    design["out_of_scope"] = report["brief_out_of_scope"]
    return design


def meta_lines(text: str) -> list[str]:
    """--link만 쓰는 줄들. 훅이 손편집을 가려낸다."""
    return [m.group(0) for pattern in (LINE, DROPPED) for m in pattern.finditer(text)]


def _declared(text: str, pattern: re.Pattern = LINE) -> dict | None:
    """적힌 {시스템: 지문}. 줄이 없거나 비면 빈 값이고, 이 도구가 쓰는 형식이 아니면 None이다."""
    line = pattern.search(text)
    if line is None:
        return {}
    value = line.group(1).strip()
    if not (value.startswith("{") and value.endswith("}")):
        return None
    pairs = [PAIR.match(p.strip()) for p in value[1:-1].split(",") if p.strip()]
    return {m.group(1): m.group(2) for m in pairs} if all(pairs) else None


def _changes(root: Path) -> list[Path]:
    folder = root / CHANGES
    return sorted(p for p in folder.iterdir() if p.is_dir() and p.name != "archive") if folder.is_dir() else []


def _measured_lines(text: str):
    """잴 줄 (번호, 글). REMOVED 절은 범위 밖 요구사항을 빼는 일이라 재지 않는다."""
    removed = False
    for number, line in enumerate(text.splitlines(), 1):
        if line.startswith("## "):
            removed = line[3:].strip().lower().startswith("removed")
        if not removed:
            yield number, line


def _found_items(text: str, items: list) -> list[tuple[int, str]]:
    wanted = [(x, c.phrase_pattern(x)) for x in items if x.strip()]
    return [(number, item) for number, line in _measured_lines(text) for item, phrase in wanted if phrase.search(c.fold_text(line))]


def _check_texts(change: Path, texts: list[tuple[Path, str]], items: list, errors: list) -> None:
    for path, text in texts:
        for number, item in _found_items(text, items):
            where = f"{change.name}/{path.relative_to(change).as_posix()}:{number}"
            _err(errors, "out_of_scope_in_spec", where, f"브리프가 범위 밖이라고 한 항목이 변경에 있습니다: {item}. 변경에서 빼거나, 브리프를 바꿀지 사용자에게 묻습니다.")


def _non_goal_rules(change: Path, systems: dict) -> set:
    """design.md의 Non-Goals에 적은 규칙(시스템, 규칙). "## Non-Goals" 제목이면 다음 제목 전까지,
    "**Non-Goals:**" 같은 이름표면 바로 뒤의 목록(항목과 들여 쓴 줄)까지만 읽는다. 목록 뒤 문단은 Non-Goals가 아니다."""
    path = change / "design.md"
    if not path.is_file():
        return set()
    found, mode = set(), None   # None(밖) / "heading" / "list"
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if NON_GOALS.match(line):
            mode = "heading" if line.lstrip().startswith("#") else "list"
            continue
        if mode and line.lstrip().startswith("#"):
            mode = None
        elif mode == "list" and line.strip() and not (LIST_ITEM.match(line) or line[:1] in (" ", "\t")):
            mode = None
        if mode:
            found |= {(sid, rid) for sid, rid in _rule_refs(line, systems) if rid in _rule_ids(systems[sid])}
    return found


def _rule_ids(system: dict) -> set:
    return {r.get("id") for r in system.get("rules", []) if isinstance(r, dict)}


def _rule_refs(line: str, systems: dict) -> list:
    """줄에서 설계에 있는 시스템의 시스템.규칙 표기. 대문자로 써도 같은 id다. 파일 이름(gems.json)은 뺀다."""
    out = []
    for sid, rid in RULE_REF.findall(line):
        sid, rid = sid.lower(), rid.lower()
        if sid in systems and rid not in FILE_EXTENSIONS:
            out.append((sid, rid))
    return out


def _check_rule_refs(change: Path, texts: list[tuple[Path, str]], systems: dict, declared: dict, errors: list) -> None:
    """명세가 가리키는 규칙(시스템.규칙)이 설계에 있는가, 그 시스템이 변경에 이어졌는가, design.md의 Non-Goals에 적은 규칙은 아닌가.
    잇지 않으면 그 규칙이 바뀌어도 design_changed가 나지 않는다. 설계에 있는 시스템 뒤의 표기만 본다."""
    excluded = _non_goal_rules(change, systems)
    for path, text in texts:
        for number, line in _measured_lines(text):
            for sid, rid in _rule_refs(line, systems):
                s = systems[sid]
                where = f"{change.name}/{path.relative_to(change).as_posix()}:{number}"
                if rid not in _rule_ids(s):
                    close = c.closest(rid, _rule_ids(s) - {None})
                    if close:   # 비슷한 규칙이 없으면 데이터 칸(weapons.fire_rate)일 수 있어 막지 않는다
                        _err(errors, "unknown_rule", where, f"시스템 설계에 없는 규칙입니다: {sid}.{rid}. '{close}'의 오타인가요? "
                                                            "규칙 id는 design/systems.json에 있는 것만 씁니다. 새 규칙이 필요하면 설계에 먼저 적습니다.")
                    continue
                if (sid, rid) in excluded:
                    _err(errors, "rule_in_non_goals", where, f"design.md의 Non-Goals에 적은 규칙을 가리킵니다: {sid}.{rid}. 이번에 하지 않을 일이면 그 줄을 뺍니다. "
                                                             "하기로 바뀌었으면 Non-Goals에서 빼고, 범위가 넓어지는지 사용자에게 묻습니다.")
                    continue
                if not declared or sid in declared:
                    continue
                if _buildable(s):
                    fix = (f"proposal에 그 시스템이 없거나 브리프의 prototype.scope 밖이면 그 줄을 뺍니다. 이 변경이 그 시스템도 다루기로 했으면 "
                           f"studio.py scope --link {change.name} {' '.join(sorted({*declared, sid}))}로 잇습니다.")
                else:   # 이을 수 없는 시스템이다. --link가 거부한다
                    fix = (f"그 시스템은 이번에 만들지 않습니다(범위 {s['scope']}, 상태 {s.get('status', '없음')}). 그 줄을 빼고, 하지 않을 일이면 design.md의 "
                           "Non-Goals에 적습니다. 만들어야 하면 범위를 바꿀지 사용자에게 묻습니다.")
                _err(errors, "rule_of_unlinked_system", where, f"변경이 잇지 않은 시스템의 규칙을 가리킵니다: {sid}.{rid}. {fix}")


def _check_change(change: Path, design: dict, errors: list) -> None:
    meta = change / META
    text = meta.read_text(encoding="utf-8", errors="replace") if meta.is_file() else ""
    declared = _declared(text)
    if declared is None:
        _err(errors, "change_unreadable", change.name, f"{KEY} 줄을 읽지 못했습니다. 손으로 적지 않고 studio.py scope --link로 다시 씁니다.")
        return
    specs = sorted((change / "specs").rglob("*.md"))
    if not declared and (specs or not SKIP_SPECS.search(text)):  # 명세가 있으면 동작을 바꾸는 변경이다
        _err(errors, "change_without_system", change.name, f"어떤 시스템을 다루는 변경인지 밝히지 않았습니다. studio.py scope --link {change.name} <시스템 id>로 잇습니다.")
    systems = design["systems"]
    for sid, mark in declared.items():
        s = systems.get(sid)
        if s is None:
            _err(errors, "unknown_system", change.name, f"시스템 설계에 없는 시스템입니다: {sid}.{did_you_mean(sid, systems)}")
        elif not _buildable(s):
            _err(errors, "system_not_in_mvp", change.name, f"이번에 만들 시스템이 아닙니다: {sid}(범위 {s['scope']}, 상태 {s.get('status', '없음')}). 범위를 바꿀지 사용자에게 묻습니다.")
        elif stamp(s) != mark:
            _err(errors, "design_changed", change.name, f"명세를 쓴 뒤 규칙이 바뀌었습니다: {sid}. 명세를 지금 규칙에 맞춘 뒤 studio.py scope --link {change.name} {' '.join(sorted(declared))} --refresh로 지문을 새로 찍습니다.")
    measured = [change / n for n in MEASURED if (change / n).is_file()] + specs
    texts = [(path, path.read_text(encoding="utf-8", errors="replace")) for path in measured]   # 훅이 편집마다 부르므로 한 번만 읽는다
    _check_texts(change, texts, design["out_of_scope"], errors)
    _check_rule_refs(change, texts, systems, declared, errors)   # 잇지 않은 변경은 change_without_system이 말하므로 이음은 보지 않는다


def check(root: Path) -> dict:
    """진행 중인 변경을 잰다. 보관한 변경은 이미 끝난 기록이라 보지 않는다."""
    design = _design(root)
    changes = _changes(root)
    errors = list(design["errors"])
    if not errors:
        for change in changes:
            _check_change(change, design, errors)
    return {"changes": [p.name for p in changes], "errors": errors}


def print_report(report: dict) -> None:
    for e in report["errors"]:
        print(f"error [{e['code']}] {e['where']}: {e['message']}")
    verdict = "FAIL" if report["errors"] else "PASS" if report["changes"] else "잴 변경 없음"
    print(f"전체: 변경 {len(report['changes'])}개 · 오류 {len(report['errors'])} → {verdict}")


def link(root: Path, change: str, ids: list[str], refresh: bool = False) -> tuple[int, list[str]]:
    """(종료 코드, 출력 줄). 변경이 다루는 시스템을 적는다. 뒤에 막힐 값은 적지 않는다.
    새 시스템은 지금 규칙의 지문을 찍고, 이미 이은 시스템은 지문을 그대로 둔다. 다시 이을 때 바뀐 규칙이 조용히 받아들여지지 않게 하려는 것이다.
    refresh: 적은 시스템의 지문을 모두 새로 찍는다. 명세를 바뀐 규칙에 맞춘 뒤 design_changed를 푸는 길이다."""
    names = [p.name for p in _changes(root)]
    meta = root / CHANGES / change / META
    if change not in names or not meta.is_file():
        return 2, [f"진행 중인 변경이 아닙니다: {change}.{did_you_mean(change, names)}"]
    if not ids:
        return 2, ["이을 시스템 id를 적습니다: studio.py scope --link <변경> <시스템 id> …"]
    design = _design(root)
    if design["errors"]:
        return 1, [f"[{e['code']}] {e['where']}: {e['message']}" for e in design["errors"]]
    systems = design["systems"]
    problems = [f"시스템 설계에 없는 시스템입니다: {x}.{did_you_mean(x, systems)}" for x in ids if x not in systems]
    problems += [f"이번에 만들 시스템이 아닙니다: {x}. 범위를 바꿀지 사용자에게 묻습니다." for x in ids if x in systems and not _buildable(systems[x])]
    if problems:
        return 1, problems
    try:
        text = meta.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return 2, [f"변경의 메타데이터가 UTF-8이 아닙니다: {change}. 파일을 고친 뒤 다시 잇습니다."]
    before = _declared(text)
    known = {**(_declared(text, DROPPED) or {}), **(before or {})}   # 읽지 못한 줄은 새로 쓴다
    marks = {x: (None if refresh else known.get(x)) or stamp(systems[x]) for x in sorted(set(ids))}
    pairs = ", ".join(f"{x}: {m}" for x, m in marks.items())
    text = _put_line(text, LINE, f"{KEY}: {{{pairs}}}")
    remembered = {k: v for k, v in sorted(known.items()) if k not in marks}
    gone = f"{DROPPED_KEY}: {{{', '.join(f'{k}: {v}' for k, v in remembered.items())}}}" if remembered else None
    text = _put_line(text, DROPPED, gone) if gone else DROPPED_WHOLE.sub("", text, count=1)
    meta.write_text(text, encoding="utf-8")
    dropped = sorted(set(before or {}) - set(ids))
    stale = [x for x, m in marks.items() if m != stamp(systems[x])]
    out = [f"{change}: {pairs}"] + ([f"뺀 시스템: {', '.join(dropped)}"] if dropped else [])
    if stale:
        out.append(f"규칙이 바뀐 시스템의 지문은 그대로 두었습니다: {', '.join(stale)}. 명세를 지금 규칙에 맞춘 뒤 --refresh로 새로 찍습니다.")
    return 0, out


def _put_line(text: str, pattern: re.Pattern, line: str) -> str:
    if pattern.search(text):
        return pattern.sub(lambda _: line, text, count=1)
    return text + ("" if not text or text.endswith("\n") else "\n") + line + "\n"


# ---------- 범위를 넓히는 편집 ----------
def _mvp_systems(data: dict) -> set:
    raw = data.get("systems")
    return {s["id"] for s in raw if isinstance(s, dict) and isinstance(s.get("id"), str) and s.get("scope") == "mvp" and c.is_active(s)} if isinstance(raw, list) else set()


def concept_in_use(root: Path):
    """시스템 설계가 잇는 컨셉. 승인 전이어도 지금 범위의 기준이다."""
    try:
        data = json.loads((root / SYSTEMS_FILE).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    return data.get("concept") if isinstance(data, dict) else None


def _standing_briefs(data: dict, in_use) -> dict:
    raw = data.get("concepts")
    return {x["id"]: x.get("brief") for x in raw if isinstance(x, dict) and isinstance(x.get("id"), str) and (x.get("status") == "approved" or x["id"] == in_use)} if isinstance(raw, list) else {}


def _texts(brief, key: str) -> set:
    value = brief.get(key) if isinstance(brief, dict) else None
    return {x for x in value if isinstance(x, str)} if isinstance(value, list) else set()


def _approved(data: dict) -> set:
    return set(_standing_briefs(data, None))


def added_out_of_scope(root: Path, before: str, after: str) -> list[str]:
    """글에 새로 들어온 범위 밖 항목. 이미 있던 줄은 그 뒤의 편집을 막지 않는다."""
    old, lines = set(before.splitlines()), after.splitlines()
    return sorted({item for number, item in _found_items(after, _design(root)["out_of_scope"]) if lines[number - 1] not in old})


def widened(name: str, before: dict, after: dict, in_use=None) -> list[str]:
    """before에서 after로 가며 범위가 넓어진 것. name은 systems 또는 concepts다. 줄어든 것은 묻지 않는다.
    승인을 내리는 것은 묻는다. 내린 동안의 편집은 묻지 않으므로 넓히는 길이 된다."""
    if name == "systems":
        found = [f"MVP 시스템 추가 {x}" for x in sorted(_mvp_systems(after) - _mvp_systems(before))]
        if "concept" in after and after["concept"] != before.get("concept"):
            found.append(f"이을 컨셉을 {after['concept']}(으)로 바꿈")
        return found
    old = _standing_briefs(before, in_use)
    found = [f"컨셉 승인을 내림 {x}" for x in sorted(_approved(before) - _approved(after))]
    for cid, brief in sorted(_standing_briefs(after, in_use).items()):
        if cid not in old:
            found.append(f"승인된 컨셉 추가 {cid}")
            continue
        found += [f"{cid}의 MVP 추가 {x}" for x in sorted(_texts(brief, "mvp") - _texts(old[cid], "mvp"))]
        found += [f"{cid}의 범위 밖에서 뺌 {x}" for x in sorted(_texts(old[cid], "out_of_scope") - _texts(brief, "out_of_scope"))]
    return found
