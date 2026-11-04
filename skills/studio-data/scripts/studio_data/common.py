"""게임 설계 데이터(컨셉·아이템·영구 강화·적·전투 계산·판 안 성장·스탯 예산·강화·합성·재화 흐름·레벨 구성·플레이 기록)의 읽기, 종류 판별, 공통 필드 검사. 표준 라이브러리만 사용한다."""
from __future__ import annotations

import csv
import difflib
import json
import math
import re
from pathlib import Path

ID_PATTERN = re.compile(r"^[a-z0-9_]+$")
STATUSES = ("proposed", "approved", "cut")
PROVENANCE_KINDS = {"assumed": "assumed", "computed": "computed", "measured": "measured",
                    "가정": "assumed", "계산": "computed", "측정": "measured"}
TEXT_FIELDS = ("name", "effect", "intent")
DATASET_KINDS = ("concepts", "items", "upgrades", "enemies", "combat", "growth", "budget", "crafting", "economy", "levels", "playtests")
KIND_LABELS = {"concepts": "컨셉", "items": "아이템", "upgrades": "영구 강화", "enemies": "적", "combat": "전투 계산",
               "growth": "판 안 성장", "budget": "스탯 예산", "crafting": "강화·합성", "economy": "재화 흐름", "levels": "레벨 구성", "playtests": "플레이 기록"}
LIST_KEYS = {"combat": ("stages",), "budget": ("archetypes",), "crafting": ("enhance", "recipes"), "economy": ("stages", "purchases"),
             "growth": ("choices", "builds")}  # 항목 배열의 키가 종류 이름과 다른 경우
FOREIGN_NAMES = ("levels",)  # 게임이 자기 형식으로도 흔히 쓰는 파일 이름. 종류 키가 없으면 이 도구의 파일로 보지 않는다
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


def closest(name: str, known) -> str | None:
    """가장 비슷한 이름(오타 추정). 없으면 None."""
    close = difflib.get_close_matches(str(name), [str(k) for k in known], n=1, cutoff=0.6)
    return close[0] if close else None


def did_you_mean(name: str, known) -> str:
    """오타 안내 문장. 비슷한 이름이 없으면 빈 문자열."""
    close = closest(name, known)
    return f" '{close}'의 오타인가요?" if close else ""


def unknown_keys_text(entry: dict, known) -> str | None:
    """모르는 키 안내 문장. 없으면 None. 모르는 키는 오타일 수 있고, 그대로 두면 값이 조용히 기본값이 된다. _로 시작하는 키는 메모로 둔다."""
    unknown = sorted(k for k in entry if k not in known and not str(k).startswith("_"))
    if not unknown:
        return None
    return f"알 수 없는 키 {', '.join(map(str, unknown))}.{''.join(did_you_mean(k, known) for k in unknown)}"


_DIGIT_FINAL = "0136780"  # 영·일·삼·육·칠·팔·십(0)은 받침이 있다


def josa(word: str, pair: str) -> str:
    """word에 받침에 맞는 조사를 붙인다. pair: "을를", "이가", "은는", "과와". 닫는 따옴표는 건너뛰고 본다.
    영문은 끝소리를 글자로 알 수 없어(queen, elite) 두 조사를 함께 적는다."""
    last = str(word).rstrip("'\"")[-1:] if word else ""
    if last.isascii() and last.isalpha():
        return f"{word}{pair[0]}({pair[1]})"
    if "가" <= last <= "힣":
        final = (ord(last) - 0xAC00) % 28 != 0
    else:
        final = last.isdigit() and last in _DIGIT_FINAL
    return f"{word}{pair[0] if final else pair[1]}"


def num_text(v) -> str:
    """수를 사람이 읽는 형태로(부동소수 오차를 지운다). 1.2000000000000002 → 1.2"""
    return f"{round(v, 6):g}" if isinstance(v, float) else str(v)


def match_text(filt) -> str:
    """조건 {필드: 값}을 [필드=값, … 아무거나]로 쓴다. 파이썬 dict 표기를 그대로 보이지 않는다."""
    if not isinstance(filt, dict):
        return str(filt)
    return "[" + ", ".join(f"{k}={v}" for k, v in filt.items()) + " 아무거나]"


def valid_range(rng) -> bool:
    """목표 범위 [최소, 최대]. 한쪽은 None(열림)일 수 있고, 둘 다 있으면 최소 ≤ 최대."""
    return (isinstance(rng, list) and len(rng) == 2 and all(v is None or is_number(v) for v in rng)
            and rng != [None, None] and (None in rng or rng[0] <= rng[1]))


def out_of_range(v, rng) -> bool:
    lo, hi = rng
    return (lo is not None and v < lo) or (hi is not None and v > hi)


def range_text(rng) -> str:
    lo, hi = rng
    return f"{'' if lo is None else f'{lo:g}'}~{'' if hi is None else f'{hi:g}'}"


def is_int(v, minimum: int | None = None) -> bool:
    """정수(bool 제외)이고 minimum 이상인가."""
    return isinstance(v, int) and not isinstance(v, bool) and (minimum is None or v >= minimum)


def is_number(v) -> bool:
    """유한한 수. JSON의 Infinity·NaN은 파이썬이 읽어 주지만 수치로 쓸 수 없다."""
    return isinstance(v, int) and not isinstance(v, bool) or isinstance(v, float) and math.isfinite(v)


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
    if ("rooms" in data and "difficulty" in data) or data.get("model") == "combat":
        return "meta"  # 메타 성장 시뮬레이터 설정(추상 모델 또는 전투 계산 모델)
    for kind in DATASET_KINDS:
        if kind in data:
            return kind  # 형식이 틀려도 종류로 인정해야 검사기가 형식 오류를 보고한다
    return "levels" if "threat_budget" in data else None


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
    with path.open(encoding="utf-8-sig") as fh:  # Windows 메모장은 BOM을 붙여 저장한다
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
            errors.append({"code": "schema", "where": where, "message": f"{josa(f, '은는')} 문자열이어야 합니다."})
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
        kind = PROVENANCE_KINDS.get(prov.get("kind")) if isinstance(prov.get("kind"), str) else None
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


def pick_weights(own, costs: dict | None, entries: list[dict], own_key: str, costs_key: str, warnings: list) -> tuple[dict, str]:
    """아이템·적 검사의 예산 가중치. 스탯 예산(budget.json)의 원가가 있으면 그것을 쓴다(같은 '예산'을 두 곳에서 따로 정하지 않는다).
    파일 안의 가중치(own)가 원가와 비율이 다르면 무시한다고 경고한다(전체 배율만 다른 것은 판정에 영향이 없어 괜찮다).
    (쓸 가중치, 출처 "budget" | own_key)."""
    own = own if isinstance(own, dict) else {}
    if costs is None:
        return own, own_key
    stats = {k for e in entries for k in e.get("stats", {})}
    used = sorted(k for k in stats if k in costs)
    ratios = {k: own.get(k, 1.0) / costs[k] for k in used}
    if own and ratios and max(ratios.values()) > min(ratios.values()) * (1 + 1e-6):
        diff = ", ".join(f"{k} {num_text(own.get(k, 1.0))}/{num_text(costs[k])}" for k in used[:4])
        add_issue(warnings, "weights_ignored", own_key,
                  f"{josa(own_key, '이가')} 스탯 예산({costs_key})과 비율이 달라 무시하고 budget.json의 원가를 씁니다({own_key}/원가: {diff}). "
                  f"{josa(own_key, '을를')} 지우거나 같은 비율로 맞춥니다.")
    # 원가가 없는 스탯(예산 비교에서는 stat_without_cost로 빠진다)은 옛 가중치를 원가 단위로 바꿔 쓴다. 1로 두면 판정이 조용히 바뀐다
    ordered = sorted(ratios.values())
    scale = 1 / ordered[len(ordered) // 2] if ordered else 1.0
    extra = {k: own.get(k, 1.0) * scale for k in stats if k not in costs}
    return {**costs, **extra}, "budget"


def provenance_kind(entry: dict) -> str:
    prov = entry.get("provenance")
    return prov["kind"] if isinstance(prov, dict) and "kind" in prov else "unspecified"


def combat_link(stage: dict) -> str | None:
    """재화 흐름 단계나 레벨이 이어지는 전투 단계 id: combat_stage, 없으면 자기 id. 문자열이 아니면 None(형식 오류는 그 파일의 검사가 보고한다)."""
    link = stage.get("combat_stage") or stage.get("id")
    return link if isinstance(link, str) else None


def time_unit(cfg) -> str:
    """재화 흐름 설정의 시간 단위. 적지 않았거나 문자열이 아니면 초다."""
    unit = cfg.get("time_unit") if isinstance(cfg, dict) else None
    return unit if isinstance(unit, str) else "초"


def is_active(entry: dict) -> bool:
    return entry.get("status") != "cut"


def _reason(v) -> bool:
    return isinstance(v, str) and bool(v.strip())


def valid_acknowledged(ack) -> bool:
    """acknowledged 형식: {경고 코드: 비어 있지 않은 이유} 또는 {경고 코드: {대상: 이유}}(예: 전투 단계의 적 하나만).
    한 칸이라도 틀리면 전체를 쓰지 않는다."""
    return isinstance(ack, dict) and all(
        isinstance(k, str) and (_reason(v) or (isinstance(v, dict) and v and all(isinstance(t, str) and _reason(r) for t, r in v.items())))
        for k, v in ack.items())


def ack_reason(entry: dict, code: str, part: str | None = None) -> str | None:
    """항목이 그 경고 코드를 확인한 이유. 다른 파일의 검사기(예: 스탯 예산)가 항목의 확인을 읽을 때 같은 규칙을 쓴다.
    이유가 {대상: 이유}이면 경고의 대상(part)이 맞을 때만 확인으로 본다. 문자열 이유는 그 항목의 그 코드 경고 전부를 덮는다.
    형식이 틀린 확인은 무시한다. 그 오류는 항목이 있는 파일의 검사(apply_acknowledged)가 보고한다."""
    ack = entry.get("acknowledged") if isinstance(entry, dict) else None
    if not (valid_acknowledged(ack) and code in ack):
        return None
    reason = ack[code]
    if isinstance(reason, dict):
        reason = reason.get(part) if part is not None else None
    return reason.strip() if reason else None


def apply_acknowledged(kind: str, data: dict, report: dict) -> None:
    """항목의 acknowledged({경고 코드: 확인한 이유})에 적힌 경고를 report["acknowledged"]로 옮긴다.
    확인한 경고는 경고 수와 --strict에서 빠지지만 지워지지 않고 이유와 함께 남는다. 오류는 옮기지 않는다.
    경고에 owner가 있으면 그 항목의 확인으로 본다(예: 전투 계산의 '단계.적' 경고는 단계가 주인).
    경고에 part(대상)가 있으면 {코드: {대상: 이유}} 확인은 그 대상의 경고만 덮는다."""
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
        acks.setdefault(e["id"], e)  # 검사기와 같이 첫 항목을 쓴다
    kept = []
    for w in report["warnings"]:
        owner = acks.get(w.get("owner", w["where"]))
        reason = ack_reason(owner, w["code"], w.get("part")) if owner else None
        if reason:
            report["acknowledged"].append({**w, "reason": reason})
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
