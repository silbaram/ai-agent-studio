"""게임 설계 데이터(컨셉·아이템·영구 강화·적·전투 계산·스탯 예산·강화·합성·플레이 기록)의 읽기, 종류 판별, 공통 필드 검사. 표준 라이브러리만 사용한다."""
from __future__ import annotations

import csv
import difflib
import json
import re
from pathlib import Path

ID_PATTERN = re.compile(r"^[a-z0-9_]+$")
STATUSES = ("proposed", "approved", "cut")
PROVENANCE_KINDS = {"assumed": "assumed", "computed": "computed", "measured": "measured",
                    "가정": "assumed", "계산": "computed", "측정": "measured"}
TEXT_FIELDS = ("name", "effect", "intent")
DATASET_KINDS = ("concepts", "items", "upgrades", "enemies", "combat", "budget", "crafting", "playtests")
KIND_LABELS = {"concepts": "컨셉", "items": "아이템", "upgrades": "영구 강화", "enemies": "적", "combat": "전투 계산",
               "budget": "스탯 예산", "crafting": "강화·합성", "playtests": "플레이 기록"}
LIST_KEYS = {"combat": ("stages",), "budget": ("archetypes",), "crafting": ("enhance", "recipes")}  # 항목 배열의 키가 종류 이름과 다른 경우
SUBFOLDERS = ("design", "data")
STAT_PREFIX = "stat."

# CSV 열 중 수로 읽을 것과 목록(;로 구분)으로 읽을 것. 아이템·영구 강화·적만 CSV를 지원한다.
CSV_KINDS = ("items", "upgrades", "enemies")
CSV_NUMERIC = {
    "items": ("tier", "price"),
    "upgrades": ("cost", "power", "level"),
    "enemies": ("zone", "reward"),
}
CSV_LISTS = {"upgrades": ("requires",)}


def add_issue(target: list, code: str, where: str, message: str, **extra) -> None:
    """오류·경고 목록에 한 건을 넣는다. extra(예: owner)는 그대로 붙는다."""
    target.append({"code": code, "where": where, "message": message, **extra})


def did_you_mean(name: str, known) -> str:
    """오타 안내 문장. 비슷한 이름이 없으면 빈 문자열."""
    close = difflib.get_close_matches(name, list(known), n=1, cutoff=0.6)
    return f" '{close[0]}'의 오타인가요?" if close else ""


def is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _num(value: str):
    value = value.strip()
    if value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return float(value)


def detect_kind(data, path: Path | None = None) -> str | None:
    """JSON 최상위 키로 종류를 판단한다. 시뮬레이터 설정은 'meta'로 구분한다."""
    if not isinstance(data, dict):
        return None
    if "rooms" in data and "difficulty" in data:
        return "meta"
    for kind in DATASET_KINDS:
        if kind in data:
            return kind  # 형식이 틀려도 종류로 인정해야 검사기가 형식 오류를 보고한다
    return None


def kind_from_filename(path: Path) -> str | None:
    stem = Path(path).stem.lower()
    for key, kind in (("concept", "concepts"), ("upgrade", "upgrades"), ("enem", "enemies"), ("item", "items")):
        if key in stem:
            return kind
    return None


def read_csv(path: Path, kind: str) -> list[dict]:
    numeric = CSV_NUMERIC.get(kind, ())
    lists = CSV_LISTS.get(kind, ())
    rows = []
    with Path(path).open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            entry: dict = {"stats": {}}
            for key, raw in row.items():
                if key is None:
                    continue
                key = key.strip()
                raw = (raw or "").strip()
                if key.startswith(STAT_PREFIX):
                    if raw != "":
                        entry["stats"][key[len(STAT_PREFIX):]] = _num(raw)
                elif key in numeric:
                    entry[key] = _num(raw) if raw else None
                elif key in lists:
                    entry[key] = [p.strip() for p in raw.split(";") if p.strip()]
                elif key == "unique_effect":
                    entry[key] = raw.lower() in ("1", "true", "yes", "y")
                elif key.startswith("provenance_"):
                    if raw != "":
                        entry.setdefault("provenance", {})[key[len("provenance_"):]] = raw
                elif raw != "":
                    entry[key] = raw
            rows.append(entry)
    return rows


def load_dataset(path: Path, expected: str | None = None) -> tuple[str | None, dict]:
    """파일을 읽어 (종류, 데이터)를 돌려준다. CSV는 파일 이름이나 expected로 종류를 정한다."""
    path = Path(path)
    if path.suffix.lower() == ".csv":
        kind = expected or kind_from_filename(path)
        if kind not in CSV_KINDS:
            raise ValueError("CSV 종류를 알 수 없습니다. 파일 이름에 items / upgrades / enemies를 넣으세요. 컨셉은 JSON만 지원합니다.")
        return kind, {kind: read_csv(path, kind)}
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, list) and expected:
        data = {expected: data}
    if not isinstance(data, dict):
        raise ValueError("최상위는 객체여야 합니다.")
    return detect_kind(data, path), data


def check_common(entry: dict, where: str, errors: list) -> bool:
    """name/effect/intent, status, provenance를 검사한다. provenance.kind는 영문으로 정규화한다."""
    ok = True
    for f in TEXT_FIELDS:
        if f in entry and not isinstance(entry[f], str):
            errors.append({"code": "schema", "where": where, "message": f"{f}는 문자열이어야 합니다."})
            ok = False
    status = entry.get("status")
    if status is not None and status not in STATUSES:
        errors.append({"code": "schema", "where": where, "message": f"status는 {', '.join(STATUSES)} 중 하나입니다: {status!r}"})
        ok = False
    prov = entry.get("provenance")
    if prov is not None:
        if not isinstance(prov, dict):
            errors.append({"code": "provenance", "where": where, "message": "provenance는 {kind, source, note} 객체여야 합니다."})
            return False
        kind = PROVENANCE_KINDS.get(prov.get("kind"))
        if kind is None:
            errors.append({"code": "provenance", "where": where, "message": f"provenance.kind는 assumed/computed/measured(가정/계산/측정) 중 하나입니다: {prov.get('kind')!r}"})
            return False
        source = prov.get("source")
        if kind in ("computed", "measured") and not (isinstance(source, str) and source.strip()):
            errors.append({"code": "provenance", "where": where, "message": f"provenance.kind가 {kind}이면 source가 필요합니다."})
            return False
        prov["kind"] = kind
    return ok


def check_identity(entries: list, label: str, errors: list) -> list[tuple[int, dict]]:
    """객체이고 id 규칙을 지키며 중복되지 않은 항목만 (원래 위치, 항목)으로 돌려준다."""
    out, seen = [], set()
    for idx, entry in enumerate(entries):
        where = f"{label}[{idx}]"
        if not isinstance(entry, dict):
            errors.append({"code": "schema", "where": where, "message": "항목은 객체여야 합니다."})
            continue
        eid = entry.get("id")
        if not isinstance(eid, str) or not ID_PATTERN.match(eid):
            errors.append({"code": "schema", "where": where, "message": f"id는 소문자·숫자·밑줄만 씁니다: {eid!r}"})
            continue
        if eid in seen:
            errors.append({"code": "duplicate_id", "where": eid, "message": "id가 중복됩니다."})
            continue
        seen.add(eid)
        out.append((idx, entry))
    return out


def check_stats(entry: dict, where: str, errors: list) -> bool:
    stats = entry.get("stats", {})
    if not isinstance(stats, dict) or not all(isinstance(k, str) and is_number(v) for k, v in stats.items()):
        errors.append({"code": "schema", "where": where, "message": "stats는 {이름: 수} 형태여야 합니다."})
        return False
    return True


def weighted(entry: dict, weights: dict) -> float:
    return sum(v * weights.get(k, 1.0) for k, v in entry.get("stats", {}).items())


def provenance_kind(entry: dict) -> str:
    prov = entry.get("provenance")
    return prov["kind"] if isinstance(prov, dict) and "kind" in prov else "unspecified"


def is_active(entry: dict) -> bool:
    return entry.get("status") != "cut"


def valid_acknowledged(ack) -> bool:
    """acknowledged 형식: {경고 코드: 비어 있지 않은 이유}. 한 칸이라도 틀리면 전체를 쓰지 않는다."""
    return isinstance(ack, dict) and all(isinstance(k, str) and isinstance(v, str) and v.strip() for k, v in ack.items())


def ack_reason(entry: dict, code: str) -> str | None:
    """항목이 그 경고 코드를 확인한 이유. 다른 파일의 검사기(예: 스탯 예산)가 항목의 확인을 읽을 때 같은 규칙을 쓴다.
    형식이 틀린 확인은 무시한다. 그 오류는 항목이 있는 파일의 검사(apply_acknowledged)가 보고한다."""
    ack = entry.get("acknowledged") if isinstance(entry, dict) else None
    return ack[code].strip() if valid_acknowledged(ack) and code in ack else None


def apply_acknowledged(kind: str, data: dict, report: dict) -> None:
    """항목의 acknowledged({경고 코드: 확인한 이유})에 적힌 경고를 report["acknowledged"]로 옮긴다.
    확인한 경고는 경고 수와 --strict에서 빠지지만 지워지지 않고 이유와 함께 남는다. 오류는 옮기지 않는다.
    경고에 owner가 있으면 그 항목의 확인으로 본다(예: 전투 계산의 '단계.적' 경고는 단계가 주인)."""
    report.setdefault("acknowledged", [])
    lists = [data.get(k) for k in LIST_KEYS.get(kind, (kind,))]
    entries = [e for lst in lists if isinstance(lst, list) for e in lst]
    if not entries:
        return
    acks: dict = {}
    for e in entries:
        if not isinstance(e, dict) or not isinstance(e.get("id"), str) or "acknowledged" not in e:
            continue
        ack = e["acknowledged"]
        if not valid_acknowledged(ack):
            report["errors"].append({"code": "schema", "where": e["id"],
                                     "message": "acknowledged는 {경고 코드: 확인한 이유} 객체여야 합니다. 이유를 비워 두지 않습니다."})
            continue
        acks.setdefault(e["id"], ack)  # 검사기와 같이 첫 항목을 쓴다
    kept = []
    for w in report["warnings"]:
        reason = acks.get(w.get("owner", w["where"]), {}).get(w["code"])
        if reason:
            report["acknowledged"].append({**w, "reason": reason.strip()})
        else:
            kept.append(w)
    report["warnings"] = kept


def summary_counts(entries: list[dict]) -> dict:
    status = {s: 0 for s in STATUSES + ("unspecified",)}
    for e in entries:
        status[e.get("status") or "unspecified"] += 1
    prov = {k: 0 for k in ("assumed", "computed", "measured", "unspecified")}
    active = [e for e in entries if is_active(e)]
    for e in active:
        prov[provenance_kind(e)] += 1
    return {
        "status_counts": status,
        "provenance_counts": prov,
        "unverified": sorted(e["id"] for e in active if provenance_kind(e) in ("assumed", "unspecified")),
    }


def find_cycle(graph: dict) -> list[str] | None:
    """graph: {id: [선행 id, ...]}. 순환이 있으면 경로를 돌려준다."""
    state: dict = {}

    def visit(node: str, path: list):
        if state.get(node) == 1:
            return path[path.index(node):] + [node]
        if state.get(node) == 2:
            return None
        state[node] = 1
        for nxt in graph.get(node, []):
            if nxt in graph:
                found = visit(nxt, path + [node])
                if found:
                    return found
        state[node] = 2
        return None

    for node in graph:
        found = visit(node, [])
        if found:
            return found
    return None
