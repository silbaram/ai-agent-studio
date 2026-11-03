"""게임 설계 데이터(컨셉·아이템·영구 강화·적·플레이 기록)의 읽기, 종류 판별, 공통 필드 검사. 표준 라이브러리만 사용한다."""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

ID_PATTERN = re.compile(r"^[a-z0-9_]+$")
STATUSES = ("proposed", "approved", "cut")
PROVENANCE_KINDS = {"assumed": "assumed", "computed": "computed", "measured": "measured",
                    "가정": "assumed", "계산": "computed", "측정": "measured"}
TEXT_FIELDS = ("name", "effect", "intent")
DATASET_KINDS = ("concepts", "items", "upgrades", "enemies", "playtests")
KIND_LABELS = {"concepts": "컨셉", "items": "아이템", "upgrades": "영구 강화", "enemies": "적", "playtests": "플레이 기록"}
SUBFOLDERS = ("design", "data")
STAT_PREFIX = "stat."

# CSV 열 중 수로 읽을 것과 목록(;로 구분)으로 읽을 것. 컨셉과 플레이 기록은 CSV를 지원하지 않는다.
CSV_KINDS = ("items", "upgrades", "enemies")
CSV_NUMERIC = {
    "items": ("tier", "price"),
    "upgrades": ("cost", "power", "level"),
    "enemies": ("zone", "reward"),
}
CSV_LISTS = {"upgrades": ("requires",)}


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


def apply_acknowledged(kind: str, data: dict, report: dict) -> None:
    """항목의 acknowledged({경고 코드: 확인한 이유})에 적힌 경고를 report["acknowledged"]로 옮긴다.
    확인한 경고는 경고 수와 --strict에서 빠지지만 지워지지 않고 이유와 함께 남는다. 오류는 옮기지 않는다."""
    report.setdefault("acknowledged", [])
    entries = data.get(kind)
    if not isinstance(entries, list):
        return
    acks: dict = {}
    for e in entries:
        if not isinstance(e, dict) or not isinstance(e.get("id"), str) or "acknowledged" not in e:
            continue
        ack = e["acknowledged"]
        if not isinstance(ack, dict) or not all(isinstance(k, str) and isinstance(v, str) and v.strip() for k, v in ack.items()):
            report["errors"].append({"code": "schema", "where": e["id"],
                                     "message": "acknowledged는 {경고 코드: 확인한 이유} 객체여야 합니다. 이유를 비워 두지 않습니다."})
            continue
        acks.setdefault(e["id"], ack)  # 검사기와 같이 첫 항목을 쓴다
    kept = []
    for w in report["warnings"]:
        reason = acks.get(w["where"], {}).get(w["code"])
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
