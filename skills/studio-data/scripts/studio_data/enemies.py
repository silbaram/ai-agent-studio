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


INHERITED = ("name", "rank", "zone", "reward", "drop_table", "status", "provenance")   # level_of 행이 적지 않으면 기본 적에서 받는 칸


def _growth_problem(base: dict) -> str | None:
    """기본 적의 growth가 쓸 수 있는가. 레벨당 상승치는 기본 적의 stats에 있는 스탯에만 붙는다(오타가 새 스탯이 되지 않게)."""
    growth, stats = base.get("growth"), base.get("stats")
    if not (isinstance(growth, dict) and all(isinstance(k, str) and c.is_number(v) for k, v in growth.items())):
        return "growth는 레벨당 상승치 {스탯: 수}입니다."
    extra = [k for k in growth if not (isinstance(stats, dict) and k in stats)]
    if extra:
        known = list(stats) if isinstance(stats, dict) else []
        return f"growth의 {', '.join(extra)} 스탯이 stats에 없습니다.{''.join(c.did_you_mean(k, known) for k in extra)}"
    return None


class Index(dict):
    """다른 데이터가 가리키는 적 {id: 항목}. templates: 틀 id → 그 틀을 쓰는 level_of 행 id. 틀을 직접 가리킬 때 안내에 쓴다."""
    templates: dict = {}


def missing_text(eid: str, index) -> str | None:
    """적 참조가 틀(template)을 가리키면 그 안내. 아니면 None(호출하는 쪽이 '없는 id'로 알린다)."""
    rows = getattr(index, "templates", {}).get(eid)
    if rows is None:
        return None
    return (f"{c.josa(eid, '은는')} 틀(template)이라 적으로 세지 않습니다. 그 레벨로 나오는 행"
            + (f"({', '.join(rows)})" if rows else "(level_of 행)") + "을 가리킵니다.")


def _base_problem(e: dict) -> str | None:
    """level_of의 기본이 되는 적의 칸 중 적혀 있는데 틀린 값. 레벨 행이 그 값을 물려받아 행마다 같은 오류가 나지 않게 기본 적에서 한 번 막는다."""
    if "rank" in e and e["rank"] not in RANKS:
        return f"rank는 {', '.join(RANKS)} 중 하나입니다: {e['rank']!r}"
    if e.get("zone") is not None and not c.is_int(e["zone"], 1):
        return f"zone은 1 이상의 정수여야 합니다: {e['zone']!r}"
    if e.get("reward") is not None and not (c.is_number(e["reward"]) and e["reward"] >= 0):
        return f"reward는 0 이상의 수여야 합니다: {e['reward']!r}"
    if e.get("drop_table") is not None and not isinstance(e["drop_table"], str):
        return "drop_table은 문자열이어야 합니다."
    if e.get("level") is not None and not c.is_int(e["level"], 1):
        return f"level은 1 이상의 정수입니다: {e['level']!r}"
    if not isinstance(e.get("stats"), dict) or not all(isinstance(k, str) and c.is_number(v) for k, v in e["stats"].items()):
        return "stats는 {이름: 수} 형태여야 합니다."
    return _growth_problem(e) if e.get("growth") is not None else None


def is_template(e) -> bool:
    """틀로만 쓰는 기본 적. 게임에 그 레벨로 나오지 않고 level_of 행의 기본으로만 쓴다. 적 목록·위협도·다른 데이터의 참조에 들지 않는다."""
    return isinstance(e, dict) and e.get("template") is True and "level_of" not in e


def check_templates(raw: list, errors: list) -> list[str]:
    """틀 행의 형식. 틀은 적 검사(check_schema)를 거치지 않으므로 여기서 id·스탯·상승치를 본다. 쓸 수 있는 틀의 id를 돌려준다."""
    others = {e.get("id") for e in raw if isinstance(e, dict) and not is_template(e)}
    good = []
    for _, e in c.check_identity([e for e in raw if is_template(e)], "enemies", errors):
        where = e["id"]
        if where in others:
            errors.append({"code": "duplicate_id", "where": where, "message": "id가 중복됩니다(틀과 적이 같은 id)."})
            continue
        problem = (_base_problem(e) if e.get("growth") is not None
                   else "틀(template)에는 growth(레벨당 상승치 {스탯: 수})가 필요합니다. level_of 행의 기본으로만 쓰입니다.")
        if problem:
            errors.append({"code": "schema", "where": where, "message": problem})
        elif c.check_common(e, where, errors):
            good.append(where)
    return good


def expand(raw, errors: list | None = None, blocked: list | None = None):
    """level_of 행(같은 적의 다른 레벨)을 기본 적의 stats와 growth(레벨당 상승치)로 채운 목록. 다른 행은 그대로 둔다.
    적지 않은 칸 중 INHERITED는 기본 적에서 받는다. 계산할 수 없는 행은 빼고 errors에 남긴다.
    기본 적의 형식 오류 때문에 계산하지 못한 행은 그 행에서 이미 알리므로 errors 대신 blocked에 id만 남긴다.
    검사기와 다른 데이터의 적 참조(datasets.indexes)가 같은 결과를 쓴다."""
    if not isinstance(raw, list):
        return raw
    errors = [] if errors is None else errors
    bases = {e["id"]: e for e in raw if isinstance(e, dict) and isinstance(e.get("id"), str) and "level_of" not in e}
    out = []
    for e in raw:
        if is_template(e):
            continue   # 틀은 적이 아니다
        if not (isinstance(e, dict) and "level_of" in e):
            out.append(e)
            continue
        where = e["id"] if isinstance(e.get("id"), str) else "enemies"
        ref = e["level_of"]
        base = bases.get(ref) if isinstance(ref, str) else None
        if base is None:
            others = [k for k in bases if k != where]
            errors.append({"code": "unknown_enemy", "where": where,
                           "message": f"level_of가 가리키는 기본 적이 없습니다: {ref!r}. 기본 적은 level_of가 없는 행입니다."
                                      + (c.did_you_mean(ref, others) if isinstance(ref, str) else "")})
            continue
        growth = base.get("growth")
        start = 1 if base.get("level") is None else base.get("level")   # CSV의 빈 칸은 None이다
        problem = None
        if e.get("stats"):
            problem = "level_of로 계산하는 행에는 stats를 적지 않습니다. 기본 적의 stats와 growth에서 계산합니다."
        elif not c.is_int(e.get("level"), 1):
            problem = f"level은 1 이상의 정수입니다: {e.get('level')!r}"
        elif growth is None:
            problem = f"기본 적 {base['id']}에 growth(레벨당 상승치 {{스탯: 수}})가 필요합니다."
        elif _base_problem(base):
            if blocked is not None:
                blocked.append(where)
            continue
        if problem:
            errors.append({"code": "schema", "where": where, "message": problem})
            continue
        steps = e["level"] - start
        stats = {k: v + growth.get(k, 0) * steps if c.is_number(v) else v for k, v in base["stats"].items()}
        row = {k: base[k] for k in INHERITED if base.get(k) is not None}
        row.update({k: v for k, v in e.items() if k != "stats" and v is not None})
        row["stats"] = {k: round(v, 4) if isinstance(v, float) else v for k, v in stats.items()}
        out.append(row)
    return out


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
        if not c.is_int(zone, 1):
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
        problem = _growth_problem(e) if e.get("growth") is not None and "level_of" not in e else None
        if problem:
            errors.append({"code": "schema", "where": where, "message": problem})
            ok = False
        if "template" in e and e["template"] is not False:   # template: true인 기본 적은 expand에서 빠져 여기 오지 않는다
            message = ("level_of 행은 틀(template)이 될 수 없습니다. 틀은 level_of가 없는 기본 적입니다." if "level_of" in e
                       else f"template은 true(틀로만 쓰는 기본 적)나 false입니다: {e['template']!r}")
            errors.append({"code": "schema", "where": where, "message": message})
            ok = False
        if e.get("level") is not None and "level_of" not in e and not c.is_int(e["level"], 1):
            errors.append({"code": "schema", "where": where, "message": f"level은 1 이상의 정수입니다: {e['level']!r}"})
            ok = False
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


def validate(data: dict, drop_tables: dict | None = None, items_unreadable: bool = False, weights: dict | None = None) -> dict:
    """drop_tables를 주면(아이템 데이터의 drop_tables) 적의 drop_table 참조를 확인한다.
    items_unreadable이면 읽지 못한 아이템 파일에 있을 수 있으므로, 찾지 못한 참조를 오류 대신 미확인으로 둔다.
    weights: 함께 읽은 스탯 예산의 적 원가(budget.enemies.costs). 있으면 threat_weights 대신 쓴다."""
    errors: list = []
    warnings: list = []
    raw = data.get("enemies")
    if not isinstance(raw, list):
        errors.append({"code": "schema", "where": "enemies", "message": "enemies 배열이 필요합니다."})
        raw = []
    templates = check_templates(raw, errors)
    enemies = check_schema(expand(raw, errors), errors)
    bases = {e["id"]: e for e in raw if isinstance(e, dict) and isinstance(e.get("id"), str) and "level_of" not in e}
    for e in enemies:   # 틀이 아닌 기본 적과 같은 레벨의 행은 같은 적을 두 번 센다
        base = bases.get(e.get("level_of"))
        if base and c.is_active(e) and not is_template(base) and e["level"] == (1 if base.get("level") is None else base.get("level")):
            warnings.append({"code": "level_duplicate", "where": e["id"],
                             "message": f"{c.josa(e['id'], '은는')} 기본 적 {c.josa(base['id'], '과와')} 같은 레벨 {e['level']}입니다. 같은 적을 두 번 셉니다. "
                                        "다른 데이터가 기본 적을 가리키게 하고 이 행을 지우거나, 기본 적을 틀(template: true)로 둡니다."})
    weights, source = c.pick_weights(data.get("threat_weights"), weights, [e for e in enemies if c.is_active(e)],
                                     "threat_weights", "budget.enemies.costs", warnings)
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
        "leveled": {e["id"]: {"of": e["level_of"], "level": e["level"], "stats": e["stats"]} for e in enemies if "level_of" in e},
        "templates": templates,
        "weights_source": source,
        "zone_rank_mean_threat": zone_means,
        "drop_table_not_checked": sorted(unchecked),
        "drop_table_unchecked_reason": reason,
        "unchecked": len(unchecked),
        "errors": errors,
        "warnings": warnings,
    }


def print_extra(result: dict) -> None:
    if result.get("weights_source") == "budget":
        print("위협도: 스탯 예산의 원가(budget.enemies.costs)")
    for z, ranks in result["zone_rank_mean_threat"].items():
        print(f"구역 {z}: " + " · ".join(f"{RANK_LABEL[r]} {m:g}" for r, m in ranks.items()))
    if result["drop_table_not_checked"]:
        reason = UNCHECKED_REASON.get(result.get("drop_table_unchecked_reason"), "")
        print(f"드랍 테이블 참조 미확인({reason}): " + ", ".join(result["drop_table_not_checked"]))
