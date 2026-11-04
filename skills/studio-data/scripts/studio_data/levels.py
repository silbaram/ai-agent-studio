"""레벨 구성(data/levels.json): 레벨마다 조우를 순서대로 적고, 조우의 위협도를 곡선 예산과 비교한다.

조우의 위협도 = Σ(적 수 × 적의 위협도). 위협도는 적 검사와 같은 값이다(스탯 예산의 원가, 없으면 threat_weights).
예산 = 곡선(전투 단계의 순서) × 역할 배수. 허용 오차를 넘으면 넘침·모자람을 경고한다.
조우의 처치 수(적 수 × 판당 횟수)를 재화 흐름의 처치 가정과, 나오는 적을 전투 단계의 적과 맞춰 본다.
설계 가정의 계산이며 실제 난이도나 재미를 판정하지 않는다. 형식: level-design/references/levels-format.md
"""
from __future__ import annotations

from . import budget as bg
from . import combat as cb
from . import common as c
from .common import add_issue as _err, did_you_mean

DEFAULT_TOLERANCE = bg.DEFAULT_TOLERANCE
ENCOUNTER_FIELDS = {"id", "name", "role", "enemies", "repeat", "intent", "note"}
LEVEL_FIELDS = {"id", "name", "combat_stage", "encounters", "intent", "status", "provenance", "acknowledged", "note"}
BUDGET_FIELDS = {"curve", "roles", "tolerance", "provenance", "note"}
CURVE_FIELDS = {"growth", "base", "rate", "values", "note"}  # 곡선의 기준은 전투 단계의 순서로 정해져 있어 by를 쓰지 않는다
FLAG_LABEL = {"ok": "예산 안", "over": "넘침", "under": "모자람"}
UNCHECKED_LABEL = {"enemies": "적", "combat": "전투 계산"}


def _positive(v) -> bool:
    return c.is_number(v) and v > 0


def _known_keys(entry: dict, known: set, at: str, errors: list) -> bool:
    text = c.unknown_keys_text(entry, known)
    if text:
        _err(errors, "schema", at, text)
    return text is None


# ---------- 형식 검사 ----------
def read_settings(data: dict, errors: list) -> dict | None:
    """위협도 예산. 없으면 None(미확인). 틀리면 오류를 남기고 None."""
    cfg = data.get("threat_budget")
    if cfg is None:
        return None
    where = "threat_budget"
    if not isinstance(cfg, dict):
        _err(errors, "schema", where, "threat_budget은 {curve, roles, tolerance} 객체입니다.")
        return None
    raw_curve = cfg.get("curve")
    curve = bg.read_curve(raw_curve, where, errors, by=False)
    roles = cfg.get("roles")
    ok = c.check_common(cfg, where, errors) and curve is not None
    ok = _known_keys(cfg, BUDGET_FIELDS, where, errors) and ok
    if isinstance(raw_curve, dict):
        ok = _known_keys(raw_curve, CURVE_FIELDS, f"{where}.curve", errors) and ok
    if not (isinstance(roles, dict) and roles and all(isinstance(k, str) and _positive(v) for k, v in roles.items())):
        _err(errors, "schema", where, "roles는 {역할 이름: 0보다 큰 배수}입니다.")
        ok = False
    tol = cfg.get("tolerance", DEFAULT_TOLERANCE)
    if not (c.is_number(tol) and 0 <= tol < 1):
        _err(errors, "schema", where, f"tolerance는 0 이상 1 미만의 비율입니다: {tol!r}")
        ok = False
    return {"curve": curve, "roles": roles, "tolerance": tol} if ok else None


def _check_encounter(x: dict, at: str, cfg, errors: list) -> bool:
    ok = _known_keys(x, ENCOUNTER_FIELDS, at, errors)
    foes = x.get("enemies")
    if not (isinstance(foes, dict) and foes and all(_positive(v) for v in foes.values())):
        _err(errors, "schema", at, "enemies는 {적 id: 0보다 큰 수}입니다(한 번 만날 때 나오는 수, 평균이면 소수).")
        ok = False
    if "repeat" in x and not _positive(x["repeat"]):
        _err(errors, "schema", at, f"repeat(한 판에서 만나는 횟수)는 0보다 큰 수입니다: {x['repeat']!r}")
        ok = False
    role = x.get("role")
    if "role" in x and not isinstance(role, str):
        _err(errors, "schema", at, f"role은 threat_budget.roles의 역할 이름입니다: {role!r}")
        ok = False
    elif cfg is not None and "role" not in x:
        _err(errors, "schema", at, f"role이 필요합니다. 역할: {', '.join(cfg['roles'])}")
        ok = False
    elif cfg is not None and role not in cfg["roles"]:
        _err(errors, "unknown_role", at, f"threat_budget.roles에 없는 역할입니다: {role}.{did_you_mean(role, cfg['roles'])}")
        ok = False
    return ok


def _encounters(lv: dict, cfg, seen: set, errors: list) -> tuple[list, bool]:
    """(형식이 맞는 조우, 하나도 빠지지 않았는가). 조우 id는 파일 전체에서 하나다."""
    raw = lv.get("encounters")
    if not isinstance(raw, list):
        _err(errors, "schema", lv["id"], "encounters(조우 배열, 판에서 지나는 순서대로)가 필요합니다.")
        return [], False
    found = c.check_identity(raw, f"{lv['id']}.encounters", errors)
    out = []
    for _, x in found:
        at = f"{lv['id']}.{x['id']}"
        if x["id"] in seen:
            _err(errors, "duplicate_id", at, f"조우 id가 겹칩니다: {x['id']}")
        elif _check_encounter(x, at, cfg, errors):
            out.append(x)
        seen.add(x["id"])
    return out, len(out) == len(raw)


# ---------- 계산 ----------
def _stage_budget(cfg, stage: str, order: list | None, lid: str, errors: list) -> float | None:
    """그 단계의 곡선 값. 표 곡선은 단계 id로, 나머지는 전투 단계의 순서(1부터)로 읽는다. 순서를 모르면 None."""
    if cfg is None:
        return None
    if cfg["curve"]["growth"] == "table":
        at = stage
    elif order is not None and stage in order:
        at = order.index(stage) + 1
    else:
        return None
    value = bg.curve_value(cfg["curve"], at)
    if value is None:
        _err(errors, "curve_missing_point", lid, f"table 곡선의 values에 단계 {stage}가 없습니다.")
    elif value <= 0:
        _err(errors, "curve_not_positive", lid, f"단계 {stage}의 곡선 값이 {value:g}입니다. 곡선은 모든 단계에서 0보다 커야 합니다.")
    return value if value and value > 0 else None


def _score(x: dict, lid: str, enemies: dict | None, threat: dict | None, errors: list, warnings: list) -> tuple[float | None, dict, bool]:
    """(조우의 위협도, 나오는 적 {id: 수}, 적을 모두 알아봤는가). 삭제된 적은 뺀다. 위협도를 모르는 적이 있으면 위협도는 None."""
    total: float | None = 0.0 if threat is not None else None
    placed, known = {}, True
    for eid, n in x["enemies"].items():
        if enemies is not None and eid not in enemies:
            _err(errors, "unknown_enemy", f"{lid}.{x['id']}", f"적 데이터에 없는 id입니다: {eid}.{did_you_mean(eid, enemies)}")
            total, known = None, False
            continue
        if enemies is not None and not c.is_active(enemies[eid]):
            _err(warnings, "cut_referenced", f"{lid}.{x['id']}", f"삭제(cut)된 적 {eid}를 넣었습니다. 계산에서 뺍니다.", owner=lid, part=x["id"])
            continue
        placed[eid] = n
        if total is not None:
            total = total + n * threat[eid] if eid in threat else None
    return total, placed, known


def _row(x: dict, lid: str, base, threat, cfg, warnings: list) -> dict:
    row = {"id": x["id"], "name": x.get("name"), "role": x.get("role"), "repeat": x.get("repeat", 1), "enemies": x["enemies"],
           "threat": None if threat is None else round(threat, 4), "expected": None, "low": None, "high": None, "flag": None}
    if base is None:
        return row
    expected, tol = base * cfg["roles"][x["role"]], cfg["tolerance"]
    row.update({"expected": round(expected, 4), "low": round(expected * (1 - tol), 4), "high": round(expected * (1 + tol), 4)})
    if threat is None:
        return row
    ratio = threat / expected
    row["flag"] = "over" if ratio > 1 + tol + 1e-9 else ("under" if ratio < 1 - tol - 1e-9 else "ok")
    if row["flag"] != "ok":
        _err(warnings, f"{row['flag']}_budget", f"{lid}.{x['id']}",
             f"조우 {x['id']}의 위협도 {threat:g}가 예산 {expected:g}의 {ratio:.0%}입니다(허용 ±{tol:.0%}).", owner=lid, part=x["id"])
    return row


def _economy_kills(economy: dict | None) -> dict:
    """재화 흐름의 처치 가정 {전투 단계: {적: 수}}. combat_stage로 이은 단계, 없으면 같은 id. 처치를 적지 않은 단계는 없다."""
    out: dict = {}
    stages = (economy or {}).get("stages")
    for s in stages if isinstance(stages, list) else []:
        if isinstance(s, dict) and c.is_active(s) and isinstance(s.get("kills"), dict):
            mine = out.setdefault(c.combat_link(s), {})
            for k, v in s["kills"].items():
                if c.is_number(v):
                    mine[k] = mine.get(k, 0) + v
    return out


def _stage_owner(levels: list, code: str, part: str) -> str:
    """단계 전체의 경고가 걸리는 레벨. 어느 레벨에서든 확인할 수 있게, 확인한 레벨이 있으면 그 레벨이고 없으면 첫 레벨이다."""
    return next((lv["id"] for lv in levels if c.ack_reason(lv, code, part)), levels[0]["id"])


def _compare_kills(stage: str, levels: list, mine: dict, assumed: dict, tol: float, warnings: list) -> None:
    for eid in dict.fromkeys([*assumed, *mine]):
        got, want = mine.get(eid, 0), assumed.get(eid, 0)
        if abs(got - want) > tol * want + 1e-9:
            owner = _stage_owner(levels, "kills_differ", eid)
            _err(warnings, "kills_differ", owner, f"단계 {stage}의 적 {eid} 처치 수가 조우로는 {got:g}, 재화 흐름은 {want:g}입니다(허용 ±{tol:.0%}).", owner=owner, part=eid)


def _check_unlinked_kills(assumed: dict, active: list, by_stage: dict, stages: dict | None, dropped: set, warnings: list) -> None:
    """처치 수가 있는 재화 흐름 단계가 어떤 레벨과도 이어지지 않으면 비교하지 못한 것을 알린다.
    전투 단계인데 레벨이 없는 경우는 조우 없는 단계(stages)로 이미 미확인이다. 어느 단계인지 모르는 레벨이 있으면 판단하지 않는다."""
    if not active or None in dropped:
        return
    for link, kills in assumed.items():
        if link and kills and link not in by_stage and link not in (stages or {}) and link not in dropped:
            owner = _stage_owner(active, "kills_not_linked", link)
            _err(warnings, "kills_not_linked", owner, f"재화 흐름 단계 {link}의 처치 수가 어떤 레벨과도 이어지지 않아 맞춰 보지 못했습니다. "
                                                     "그 단계에 combat_stage를 적거나 전투 단계와 같은 id로 둡니다.", owner=owner, part=link)


def _check_stage_foes(stage: dict, levels: list, group: list, enemies: dict, warnings: list) -> None:
    """전투 단계의 적과 조우의 적을 맞춘다. levels: 그 단계의 레벨, group: 그 단계의 조우 [(레벨 id, 조우, 놓은 적)]."""
    foes = cb.stage_foes(stage, enemies)
    if foes is None:
        return
    for lid, x, placed in group:
        outside = sorted(k for k in placed if k not in foes)
        for eid in outside:
            _err(warnings, "enemy_not_in_stage", f"{lid}.{x['id']}",
                 f"전투 단계 {stage['id']}에 나오지 않는 적입니다: {eid}. 전투 계산과 레벨이 다른 적을 보고 있습니다.{cb.earlier_zone_hint([eid], stage, enemies)}",
                 owner=lid, part=eid)
    for eid in sorted(foes - {k for _, _, placed in group for k in placed}):
        owner = _stage_owner(levels, "enemy_unplaced", eid)
        _err(warnings, "enemy_unplaced", owner, f"전투 단계 {stage['id']}의 적 {eid}가 어떤 조우에도 없습니다. 전투 계산만 그 적을 셉니다.", owner=owner, part=eid)


def validate(data: dict, enemies: dict | None = None, threat: dict | None = None, combat: dict | None = None, economy: dict | None = None) -> dict:
    """enemies: 함께 읽은 적의 {id: 항목}, threat: 적의 위협도 {id: 값}(적 검사와 같은 값), combat·economy: 전투 계산·재화 흐름 파일 내용.
    적이나 전투 계산이 없으면 미확인으로 센다. 재화 흐름은 레벨이 가리키지 않으므로 있을 때만 맞춰 본다."""
    errors: list = []
    warnings: list = []
    cfg = read_settings(data, errors)
    raw = data.get("levels")
    if not isinstance(raw, list):
        _err(errors, "schema", "levels", "levels(레벨 배열)가 필요합니다.")
        raw = []
    entries, dropped = [], set()   # dropped: 형식이 틀려 빠진 레벨의 단계. 어느 단계인지 모르면 None
    identified = c.check_identity(raw, "levels", errors)
    if len(identified) != len(raw):
        dropped.add(None)
    for _, e in identified:
        if c.check_common(e, e["id"], errors):
            entries.append(e)
        elif c.is_active(e):
            dropped.add(c.combat_link(e))
    stages = {x["id"]: x for x in (combat or {}).get("stages") or [] if isinstance(x, dict) and isinstance(x.get("id"), str)} \
        if isinstance((combat or {}).get("stages"), list) else None
    order = [k for k, x in stages.items() if c.is_active(x)] if stages is not None else None
    missing = {k for k, gap in (("enemies", enemies is None or threat is None), ("combat", stages is None),
                                ("threat_budget", data.get("threat_budget") is None)) if gap}
    rows, seen, computed = [], set(), 0
    by_stage: dict = {}   # 전투 단계 → {"levels": [...], "group": [...], "kills": {...}, "whole": 조우를 모두 셌는가}
    for lv in (e for e in entries if c.is_active(e)):
        _known_keys(lv, LEVEL_FIELDS, lv["id"], errors)
        link = lv.get("combat_stage")
        if link is not None and not isinstance(link, str):
            _err(errors, "schema", lv["id"], f"combat_stage는 전투 단계 id입니다: {link!r}")
            dropped.add(None)
            continue
        sid = c.combat_link(lv)
        if stages is not None and sid not in stages:
            _err(errors, "unknown_stage", lv["id"], f"전투 계산에 없는 단계입니다: {sid}.{did_you_mean(sid, stages)}")
            dropped.add(None)
            continue
        if stages is not None and not c.is_active(stages[sid]):
            _err(warnings, "cut_referenced", lv["id"], f"삭제(cut)된 전투 단계 {sid}에 이었습니다.", owner=lv["id"])
            continue
        found, whole = _encounters(lv, cfg, seen, errors)
        base = _stage_budget(cfg, sid, order, lv["id"], errors)
        info = by_stage.setdefault(sid, {"levels": [], "group": [], "kills": {}, "whole": True})
        info["levels"].append(lv)
        info["whole"] = info["whole"] and whole
        mine, kills, total = [], {}, 0.0 if whole else None
        for x in found:
            score, placed, known = _score(x, lv["id"], enemies, threat, errors, warnings)
            info["whole"] = info["whole"] and known
            mine.append(_row(x, lv["id"], base, score, cfg, warnings))
            info["group"].append((lv["id"], x, placed))
            times = x.get("repeat", 1)
            for k, n in placed.items():
                kills[k] = kills.get(k, 0) + n * times
                info["kills"][k] = info["kills"].get(k, 0) + n * times
            total = None if total is None or score is None else total + score * times
            computed += 1
        rows.append({"id": lv["id"], "name": lv.get("name"), "stage": sid, "encounters": mine, "kills": {k: round(v, 4) for k, v in kills.items()},
                     "threat": None if total is None else round(total, 4)})
    tol = cfg["tolerance"] if cfg else DEFAULT_TOLERANCE
    assumed = _economy_kills(economy)
    for sid, info in by_stage.items():
        if info["whole"] and info["group"] and not dropped & {sid, None}:
            if stages is not None and enemies is not None:
                _check_stage_foes(stages[sid], info["levels"], info["group"], enemies, warnings)
            if sid in assumed:
                _compare_kills(sid, info["levels"], info["kills"], assumed[sid], tol, warnings)
    _check_unlinked_kills(assumed, [e for e in entries if c.is_active(e)], by_stage, stages, dropped, warnings)
    empty = [k for k in order or [] if not (k in by_stage and by_stage[k]["group"])]
    if empty:
        missing.add("stages")
    if not computed:
        missing.add("nothing")
    summary = c.summary_counts(entries)
    if isinstance(data.get("threat_budget"), dict) and c.provenance_kind(data["threat_budget"]) in ("assumed", "unspecified"):
        summary["unverified"] = ["threat_budget(위협도 예산)"] + summary["unverified"]
    return {
        "kind": "levels",
        "count": len(entries),
        **summary,
        "levels": rows,
        "encounters": computed,
        "tolerance": tol,
        "stages_without_levels": empty,
        "unchecked": len(missing),
        "unchecked_kinds": sorted(missing),
        "errors": errors,
        "warnings": warnings,
    }


# ---------- 출력 ----------
def _fmt(v) -> str:
    return "–" if v is None else c.num_text(float(v))


def _parts(enemies: dict) -> str:
    return " · ".join(f"{k} {_fmt(v)}" for k, v in enemies.items())


def _verdict(x: dict) -> str:
    return FLAG_LABEL.get(x["flag"], "미확인")


def print_extra(result: dict) -> None:
    for lv in result["levels"]:
        print(f"레벨 {lv['id']} (단계 {lv['stage']}): 한 판 위협도 {_fmt(lv['threat'])} · 처치 {_parts(lv['kills']) or '없음'}")
        for x in lv["encounters"]:
            print(f"  조우 {x['id']} ({x['role'] or '역할 없음'} × {_fmt(x['repeat'])}): 위협도 {_fmt(x['threat'])} · 예산 {_fmt(x['expected'])} → {_verdict(x)}"
                  + (" ⚠" if x["flag"] in ("over", "under") else ""))
    kinds = result["unchecked_kinds"]
    data_kinds = [UNCHECKED_LABEL[k] for k in kinds if k in UNCHECKED_LABEL]
    if data_kinds:
        print("레벨 구성 미확인: " + ", ".join(data_kinds) + " 데이터를 함께 검사하지 않았거나 읽지 못함")
    if "threat_budget" in kinds:
        print("레벨 구성 미확인: threat_budget이 없어 위협도를 예산과 비교하지 못함")
    if "stages" in kinds:
        print("레벨 구성 미확인: 조우가 없는 전투 단계 " + ", ".join(result["stages_without_levels"]))
    if "nothing" in kinds:
        print("레벨 구성 미확인: 계산한 조우가 없음(빈 levels이거나 모두 삭제)")


def table(data: dict, result: dict, ids: list[str] | None = None) -> str:
    """대화에 붙일 조우 표(마크다운). --ids는 컨셉 비교표용이라 여기서는 쓰지 않는다."""
    rows = ["| 레벨 | 조우 | 역할 | 횟수 | 구성 | 위협도 | 예산 | 판정 |", "|---|---|---|---|---|---|---|---|"]
    for lv in result["levels"]:
        for x in lv["encounters"]:
            rows.append("| " + " | ".join((lv["id"], x["id"], x["role"] or "–", _fmt(x["repeat"]), _parts(x["enemies"]), _fmt(x["threat"]),
                                            f"{_fmt(x['expected'])} ({_fmt(x['low'])}~{_fmt(x['high'])})", _verdict(x))) + " |")
    rows += ["", "위협도는 스탯으로 낸 설계 가정입니다. 실제 난이도나 재미를 판정하지 않습니다."]
    return "\n".join(rows)


def print_counts(result: dict) -> None:
    tail = f"오류 {len(result['errors'])} · 경고 {len(result['warnings'])}"
    if result.get("acknowledged"):
        tail += f" · 확인한 경고 {len(result['acknowledged'])}"
    print(f"레벨 {result['count']}개 · 조우 {result['encounters']}개 · {tail}")
