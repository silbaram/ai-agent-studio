"""적 데이터를 결정적으로 검사한다.

위협도 = Σ(스탯 × threat_weights). 구역이 오를수록, 등급(일반 → 정예 → 보스)이 오를수록
위협도 평균이 줄지 않는지 본다. 가중치는 설계 가정이며 실제 난이도 판정이 아니다.
형식: progression-economy/references/data-format.md
"""
from __future__ import annotations

from pathlib import Path

from . import common as c

RANKS = ("normal", "elite", "boss")
RANK_LABEL = {"normal": "일반", "elite": "정예", "boss": "보스"}
UNCHECKED_REASON = {
    "no_items": "아이템 데이터를 함께 검사하지 않음 — data/ 폴더나 items.json을 같이 넘기세요",
    "items_unreadable": "아이템 파일을 읽지 못함 — 아이템 파일의 오류를 먼저 고치세요",
}


def load(path: Path) -> dict:
    kind, data = c.load_dataset(Path(path), expected="enemies")
    if kind != "enemies":
        raise ValueError("적 데이터가 아닙니다 (최상위에 enemies 배열이 필요합니다).")
    return data


def zone_key(zone: int) -> str:
    return f"zone_{zone}"


def check_schema(enemies: list, errors: list) -> list[dict]:
    valid = []
    for _, e in c.check_identity(enemies, "enemies", errors):
        where, ok = e["id"], True
        if e.get("rank") not in RANKS:
            errors.append({"code": "schema", "where": where, "message": f"rank는 {', '.join(RANKS)} 중 하나입니다: {e.get('rank')!r}"})
            ok = False
        zone = e.get("zone")
        if not (isinstance(zone, int) and not isinstance(zone, bool) and zone >= 1):
            errors.append({"code": "schema", "where": where, "message": f"zone은 1 이상의 정수여야 합니다: {zone!r}"})
            ok = False
        reward = e.get("reward")
        if reward is not None and not (c.is_number(reward) and reward >= 0):
            errors.append({"code": "schema", "where": where, "message": f"reward는 0 이상의 수여야 합니다: {reward!r}"})
            ok = False
        if "drop_table" in e and e["drop_table"] is not None and not isinstance(e["drop_table"], str):
            errors.append({"code": "schema", "where": where, "message": "drop_table은 문자열이어야 합니다."})
            ok = False
        ok = c.check_stats(e, where, errors) and ok
        ok = c.check_common(e, where, errors) and ok
        if ok:
            valid.append(e)
    return valid


def check_progression(active: list[dict], threat: dict, warnings: list) -> dict:
    """구역별·등급별 평균 위협도를 계산하고 역전을 경고한다."""
    table: dict = {}
    for e in active:
        table.setdefault(e["zone"], {}).setdefault(e["rank"], []).append(threat[e["id"]])
    means = {z: {r: sum(v) / len(v) for r, v in ranks.items()} for z, ranks in table.items()}
    zones = sorted(means)
    for rank in RANKS:
        seq = [z for z in zones if rank in means[z]]
        for lo, hi in zip(seq, seq[1:]):
            if means[hi][rank] < means[lo][rank]:
                warnings.append({"code": "zone_inversion", "where": zone_key(hi),
                                 "message": f"{RANK_LABEL[rank]} 평균 위협도가 구역 {lo}({means[lo][rank]:.4g})보다 구역 {hi}({means[hi][rank]:.4g})에서 낮습니다."})
    for z in zones:
        present = [r for r in RANKS if r in means[z]]
        for lo, hi in zip(present, present[1:]):
            if means[z][hi] <= means[z][lo]:
                warnings.append({"code": "rank_inversion", "where": zone_key(z),
                                 "message": f"구역 {z}에서 {RANK_LABEL[hi]} 평균 위협도({means[z][hi]:.4g})가 {RANK_LABEL[lo]}({means[z][lo]:.4g})보다 높지 않습니다."})
    return {str(z): {r: round(m, 4) for r, m in means[z].items()} for z in zones}


def validate(data: dict, drop_tables: dict | None = None, items_unreadable: bool = False) -> dict:
    """drop_tables를 주면(아이템 데이터의 drop_tables) 적의 drop_table 참조를 확인한다.
    items_unreadable이면 읽지 못한 아이템 파일에 있을 수 있으므로, 찾지 못한 참조를 오류 대신 미확인으로 둔다."""
    errors: list = []
    warnings: list = []
    raw = data.get("enemies")
    if not isinstance(raw, list):
        errors.append({"code": "schema", "where": "enemies", "message": "enemies 배열이 필요합니다."})
        raw = []
    weights = data.get("threat_weights", {}) or {}
    enemies = check_schema(raw, errors)
    threat = {e["id"]: round(c.weighted(e, weights), 4) for e in enemies}
    active = [e for e in enemies if c.is_active(e)]
    zone_means = check_progression(active, threat, warnings)
    unchecked = []
    for e in active:
        ref = e.get("drop_table")
        if not ref:
            continue
        if drop_tables is None or (items_unreadable and ref not in drop_tables):
            unchecked.append(e["id"])
        elif ref not in drop_tables:
            errors.append({"code": "unknown_drop_table", "where": e["id"], "message": f"아이템 데이터에 없는 드랍 테이블입니다: {ref}"})
    reason = None
    if unchecked:
        reason = "items_unreadable" if items_unreadable else "no_items"
    return {
        "kind": "enemies",
        "count": len(enemies),
        **c.summary_counts(enemies),
        "scores": threat,
        "zone_rank_mean_threat": zone_means,
        "drop_table_not_checked": sorted(unchecked),
        "drop_table_unchecked_reason": reason,
        "unchecked": len(unchecked),
        "errors": errors,
        "warnings": warnings,
    }


def print_extra(result: dict) -> None:
    for z, ranks in result["zone_rank_mean_threat"].items():
        print(f"구역 {z}: " + " · ".join(f"{RANK_LABEL[r]} {m:g}" for r, m in ranks.items()))
    if result["drop_table_not_checked"]:
        reason = UNCHECKED_REASON.get(result.get("drop_table_unchecked_reason"), "")
        print(f"드랍 테이블 참조 미확인({reason}): " + ", ".join(result["drop_table_not_checked"]))
