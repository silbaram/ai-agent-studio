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
PAIR = re.compile(r"^([a-z0-9_]+): ([0-9a-f]{8})$")
SKIP_SPECS = re.compile(r"^skip_specs:\s*true\s*$", re.MULTILINE)
SYSTEMS_FILE = Path("design/systems.json")
CHANGES = Path("openspec/changes")
RELINK = "명세를 지금 규칙에 맞춘 뒤 studio.py scope --link로 다시 잇습니다."


def missing(root: Path) -> str | None:
    """검사할 수 없는 프로젝트면 그 이유. 둘 다 있어야 범위를 잴 수 있다."""
    if not (root / "openspec").is_dir():
        return "openspec 폴더가 없습니다. 게임 프로젝트에서 openspec init을 먼저 실행합니다."
    if not (root / SYSTEMS_FILE).is_file():
        return f"{SYSTEMS_FILE.as_posix()}이 없습니다. system-design으로 시스템을 먼저 적습니다."
    return None


def _norm(text: str) -> str:
    return unicodedata.normalize("NFC", text).casefold()


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
    report = found["report"]
    if report["errors"]:
        first = report["errors"][0]
        _err(design["errors"], "design_invalid", found["name"], f"시스템 설계에 오류 {len(report['errors'])}개가 있어 범위를 믿을 수 없습니다. 첫 오류: [{first['code']}] {first['message']} studio.py check로 고칩니다.")
        return design
    if report["brief_out_of_scope"] is None:
        _err(design["errors"], "design_unreadable", found["name"], "브리프를 읽지 못해 범위를 잴 수 없습니다. concept-exploration으로 브리프를 씁니다.")
        return design
    design["systems"] = {s["id"]: s for s in found["data"]["systems"]}
    design["out_of_scope"] = report["brief_out_of_scope"]
    return design


def _declared(text: str) -> dict | None:
    """적힌 {시스템: 지문}. 줄이 없거나 비면 빈 값이고, 이 도구가 쓰는 형식이 아니면 None이다."""
    line = LINE.search(text)
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


def _phrase(item: str) -> re.Pattern:
    """범위 밖 문구를 찾는 식. 다른 낱말의 일부면 안 된다. 뒤에는 조사가 붙으므로 영문·숫자로 끝날 때만 뒤를 본다."""
    key = _norm(item.strip())
    return re.compile(r"(?<!\w)" + re.escape(key) + (r"(?![a-z0-9])" if key[-1].isascii() and key[-1].isalnum() else ""))


def _check_specs(change: Path, specs: list[Path], items: list, errors: list) -> None:
    wanted = [(x, _phrase(x)) for x in items if x.strip()]
    for path in specs:
        for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            text = _norm(line)
            for item, phrase in wanted:
                if phrase.search(text):
                    where = f"{change.name}/{path.relative_to(change).as_posix()}:{number}"
                    _err(errors, "out_of_scope_in_spec", where, f"브리프가 범위 밖이라고 한 항목이 명세에 있습니다: {item}. 명세에서 빼거나, 브리프를 바꿀지 사용자에게 묻습니다.")


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
            _err(errors, "design_changed", change.name, f"명세를 쓴 뒤 규칙이 바뀌었습니다: {sid}. {RELINK}")
    _check_specs(change, specs, design["out_of_scope"], errors)


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
    print(f"전체: 변경 {len(report['changes'])}개 · 오류 {len(report['errors'])} → {'FAIL' if report['errors'] else 'PASS'}")


def link(root: Path, change: str, ids: list[str]) -> tuple[int, list[str]]:
    """(종료 코드, 출력 줄). 변경이 다루는 시스템과 지금 규칙의 지문을 적는다. 뒤에 막힐 값은 적지 않는다."""
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
    pairs = ", ".join(f"{x}: {stamp(systems[x])}" for x in sorted(set(ids)))
    line = f"{KEY}: {{{pairs}}}"
    try:
        text = meta.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return 2, [f"변경의 메타데이터가 UTF-8이 아닙니다: {change}. 파일을 고친 뒤 다시 잇습니다."]
    if LINE.search(text):
        text = LINE.sub(lambda _: line, text, count=1)
    else:
        text += ("" if not text or text.endswith("\n") else "\n") + line + "\n"
    meta.write_text(text, encoding="utf-8")
    return 0, [f"{change}: {pairs}"]


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


def widened(name: str, before: dict, after: dict, in_use=None) -> list[str]:
    """before에서 after로 가며 범위가 넓어진 것. name은 systems 또는 concepts다. 줄어든 것은 묻지 않는다."""
    if name == "systems":
        found = [f"MVP 시스템 추가 {x}" for x in sorted(_mvp_systems(after) - _mvp_systems(before))]
        if "concept" in after and after["concept"] != before.get("concept"):
            found.append(f"이을 컨셉을 {after['concept']}(으)로 바꿈")
        return found
    old = _standing_briefs(before, in_use)
    found = []
    for cid, brief in sorted(_standing_briefs(after, in_use).items()):
        if cid not in old:
            found.append(f"승인된 컨셉 추가 {cid}")
            continue
        found += [f"{cid}의 MVP 추가 {x}" for x in sorted(_texts(brief, "mvp") - _texts(old[cid], "mvp"))]
        found += [f"{cid}의 범위 밖에서 뺌 {x}" for x in sorted(_texts(old[cid], "out_of_scope") - _texts(brief, "out_of_scope"))]
    return found
