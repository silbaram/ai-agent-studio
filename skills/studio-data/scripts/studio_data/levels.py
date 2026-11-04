"""레벨 구성(data/levels.json): 레벨마다 조우를 순서대로 적고, 조우의 위협도를 곡선 예산과 비교한다.

조우의 위협도 = Σ(적 수 × 적의 위협도). 위협도는 적 검사와 같은 값이다(스탯 예산의 원가, 없으면 threat_weights).
예산 = 곡선(전투 단계의 순서) × 역할 배수. 허용 오차를 넘으면 넘침·모자람을 경고한다.
조우의 처치 수(적 수 × 판당 횟수)를 재화 흐름의 처치 가정과, 나오는 적을 전투 단계의 적과 맞춰 본다.
곡선은 조우 초안에서 뽑으면 근거가 되지 못하므로 바깥 기준을 함께 낸다. 단일 대상 처치 시간과 단계 길이, 스탯 예산의 적 곡선이다.
설계 가정의 계산이며 실제 난이도나 재미를 판정하지 않는다. 형식: level-design/references/levels-format.md
"""
from __future__ import annotations

import json

from . import budget as bg
from . import combat as cb
from . import common as c
from .common import add_issue as _err, did_you_mean

DEFAULT_TOLERANCE = bg.DEFAULT_TOLERANCE
ENCOUNTER_FIELDS = {"id", "name", "role", "enemies", "repeat", "enemy_repeat", "intent", "provenance", "note"}
LEVEL_FIELDS = {"id", "name", "combat_stage", "encounters", "intent", "status", "provenance", "acknowledged", "note"}
BUDGET_FIELDS = {"curve", "roles", "tolerance", "kills_tolerance", "provenance", "note"}
CURVE_FIELDS = {"growth", "base", "rate", "values", "note"}  # 곡선의 기준은 전투 단계의 순서로 정해져 있어 by를 쓰지 않는다
FLAG_LABEL = {"ok": "예산 안", "over": "넘침", "under": "모자람"}
UNCHECKED_LABEL = {"enemies": "적", "combat": "전투 계산"}
SOURCE_LABEL = {"assumed": "가정", "computed": "계산", "measured": "측정", "unspecified": "미지정"}
SECOND_UNITS = ("초", "s", "sec", "secs", "second", "seconds")  # 전투 계산의 처치 시간(초)과 나눌 수 있는 재화 흐름 time_unit


def _positive(v) -> bool:
    return c.is_number(v) and v > 0


def _known_keys(entry: dict, known: set, at: str, errors: list) -> bool:
    text = c.unknown_keys_text(entry, known)
    if text:
        _err(errors, "schema", at, text)
    return text is None


def _read_ratio(cfg: dict, key: str, where: str, errors: list) -> float | None:
    v = cfg.get(key, DEFAULT_TOLERANCE)
    if c.is_number(v) and 0 <= v < 1:
        return v
    _err(errors, "schema", where, f"{key}는 0 이상 1 미만의 비율입니다: {v!r}")
    return None


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
    tol = _read_ratio(cfg, "tolerance", where, errors)
    kills_tol = _read_ratio(cfg, "kills_tolerance", where, errors)
    ok = ok and tol is not None and kills_tol is not None
    return {"curve": curve, "roles": roles, "tolerance": tol, "kills_tolerance": kills_tol} if ok else None


def _check_own_counts(x: dict, at: str, errors: list) -> bool:
    """enemy_repeat: {이 조우의 적 id: 한 판에서 나오는 횟수}. 보스는 한 번인데 곁의 무리는 다시 차는 조우처럼 적마다 횟수가 다를 때 쓴다."""
    own, foes = x.get("enemy_repeat", {}), x.get("enemies")
    if not (isinstance(own, dict) and all(_positive(v) for v in own.values())):
        _err(errors, "schema", at, "enemy_repeat는 {적 id: 0보다 큰 횟수}입니다(조우의 repeat와 다르게 나오는 적만 적습니다).")
        return False
    stray = [k for k in own if isinstance(foes, dict) and k not in foes]
    for k in stray:
        _err(errors, "schema", at, f"enemy_repeat의 적이 이 조우의 enemies에 없습니다: {k}.{did_you_mean(k, foes)}")
    return not stray


def _check_encounter(x: dict, at: str, cfg, errors: list) -> bool:
    ok = _known_keys(x, ENCOUNTER_FIELDS, at, errors)
    ok = c.check_common(x, at, errors) and ok
    ok = _check_own_counts(x, at, errors) and ok
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
        _err(errors, "curve_missing_point", lid, f"table 곡선의 values에 없는 단계입니다: {stage}.")
    elif value <= 0:
        _err(errors, "curve_not_positive", lid, f"단계 {stage}의 곡선 값이 {value:g}입니다. 곡선은 모든 단계에서 0보다 커야 합니다.")
    return value if value and value > 0 else None


def _stage_hint(sid: str, free: list, order: list) -> str:
    """없는 단계의 안내. 레벨이 없는 단계를 먼저 오타로 본다. 레벨이 있는 단계는 이름만 비슷한 새 단계일 수 있어 오타로 단정하지 않는다."""
    text = did_you_mean(sid, free)
    near = None if text else c.closest(sid, [k for k in order if k not in free])
    if free:
        text += f" 레벨이 없는 전투 단계: {', '.join(free)}."
    if near:
        text += f" 이름이 비슷한 단계: {near}(이미 레벨이 있습니다. 그 단계에 더 두는 레벨이면 combat_stage를 그 id로 적습니다)."
    return text


def _order_note(cfg, stage: str, stages: dict | None, order: list | None) -> str:
    """삭제된 단계 때문에 곡선의 순서가 당겨졌으면 알리는 문장. 적은 그대로인데 예산만 바뀐 것을 적의 문제로 읽지 않게 한다."""
    if cfg is None or cfg["curve"]["growth"] == "table" or stages is None or stage not in (order or []):
        return ""
    ids = list(stages)
    cut = [k for k in ids[:ids.index(stage)] if k not in order]
    if not cut:
        return ""
    now = order.index(stage) + 1
    return f" 삭제된 단계 {', '.join(cut)} 때문에 단계 {stage}의 순서가 당겨져({now + len(cut)} → {now}) 예산이 달라졌습니다."


def _times(x: dict, eid: str):
    """그 적이 한 판에서 나오는 횟수. enemy_repeat에 없으면 조우의 repeat를 따른다."""
    return x.get("enemy_repeat", {}).get(eid, x.get("repeat", 1))


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
            _err(warnings, "cut_referenced", f"{lid}.{x['id']}", f"삭제(cut)된 적을 넣었습니다: {eid}. 계산에서 뺍니다.", owner=lid, part=x["id"])
            continue
        placed[eid] = n
        if total is not None:
            total = total + n * threat[eid] if eid in threat else None
    return total, placed, known


def _row(x: dict, lid: str, base, threat, cfg, order_note: str, warnings: list) -> dict:
    row = {"id": x["id"], "name": x.get("name"), "role": x.get("role"), "repeat": x.get("repeat", 1), "enemies": x["enemies"],
           "enemy_repeat": x.get("enemy_repeat"), "threat": None if threat is None else round(threat, 4),
           "expected": None, "low": None, "high": None, "flag": None}
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
             f"조우 {x['id']}의 위협도 {c.josa(f'{threat:g}', '이가')} 예산 {expected:g}의 {ratio:.0%}입니다(허용 ±{tol:.0%}).{order_note}", owner=lid, part=x["id"])
    return row


def _encounter_time(placed: dict, times: dict | None) -> float | None:
    """조우를 한 번 치우는 단일 대상 처치 시간. 처치 시간을 모르는 적이 있으면 None."""
    if not times or not placed or any(times.get(k) is None for k in placed):
        return None
    return round(sum(n * times[k] for k, n in placed.items()), 1)


def _economy_stages(economy: dict | None) -> dict:
    """재화 흐름을 전투 단계별로 모은다 {전투 단계: {"kills": {적: 수}, "sources": 처치를 적은 단계의 출처, "length": 길이 합}}.
    combat_stage로 이은 단계, 없으면 같은 id. 처치를 적지 않았거나 비워 둔 단계는 kills가 비어 있다."""
    out: dict = {}
    stages = (economy or {}).get("stages")
    for s in stages if isinstance(stages, list) else []:
        if not (isinstance(s, dict) and c.is_active(s)):
            continue
        link = out.setdefault(c.combat_link(s), {"kills": {}, "sources": set(), "length": 0})
        if c.is_number(s.get("duration")) and s["duration"] > 0:
            link["length"] += s["duration"]
        kills = s.get("kills")
        if isinstance(kills, dict) and kills:
            link["sources"].add(c.provenance_kind(s))
            for k, v in kills.items():
                if c.is_number(v):
                    link["kills"][k] = link["kills"].get(k, 0) + v
    return out


def _stage_owner(levels: list, code: str, part: str) -> str:
    """단계 전체의 경고가 걸리는 레벨. 어느 레벨에서든 확인할 수 있게, 확인한 레벨이 있으면 그 레벨이고 없으면 첫 레벨이다."""
    return next((lv["id"] for lv in levels if c.ack_reason(lv, code, part)), levels[0]["id"])


def _source_text(kinds: set) -> str:
    return SOURCE_LABEL.get(next(iter(kinds)), "미지정") if len(kinds) == 1 else "섞임"


def _kill_sources(group: list, eid: str) -> set:
    """그 적의 처치 수를 정한 조우의 출처. 조우에 출처가 없으면 레벨의 출처다. 어떤 조우에도 없는 적이면 단계의 조우 전부를 본다."""
    placing = [(lv, x) for lv, x, placed in group if eid in placed] or [(lv, x) for lv, x, _ in group]
    return {c.provenance_kind(x if x.get("provenance") else lv) for lv, x in placing}


def _kills_advice(mine: set, theirs: set) -> str:
    """한쪽만 측정값이면 고칠 쪽을 말한다. 측정값이 가정을 앞선다."""
    if theirs == {"measured"} and mine != {"measured"}:
        return " 재화 흐름이 측정값이므로 조우의 횟수를 고칩니다."
    if mine == {"measured"} and theirs != {"measured"}:
        return " 조우가 측정값이므로 재화 흐름의 kills를 고칩니다."
    return ""


def _compare_kills(stage: str, info: dict, link: dict, tol: float, enemies: dict | None, warnings: list) -> None:
    assumed, mine = link["kills"], info["kills"]
    for eid in dict.fromkeys([*assumed, *mine]):
        if enemies is not None and eid in enemies and not c.is_active(enemies[eid]):
            continue  # 삭제된 적은 cut_referenced로 알렸고, 재화 흐름도 수입에서 뺀다
        got, want = mine.get(eid, 0), assumed.get(eid, 0)
        if abs(got - want) > tol * want + 1e-9:
            owner = _stage_owner(info["levels"], "kills_differ", eid)
            sources = _kill_sources(info["group"], eid)
            _err(warnings, "kills_differ", owner,
                 f"단계 {stage}의 적 {eid} 처치 수가 조우로는 {got:g}, 재화 흐름은 {want:g}입니다(허용 ±{tol:.0%}). "
                 f"출처: 조우 {_source_text(sources)}, 재화 흐름 {_source_text(link['sources'])}.{_kills_advice(sources, link['sources'])}",
                 owner=owner, part=eid)


def _check_unlinked_kills(links: dict, active: list, by_stage: dict, stages: dict | None, dropped: set, warnings: list) -> None:
    """처치 수가 있는 재화 흐름 단계가 어떤 레벨과도 이어지지 않으면 비교하지 못한 것을 알린다.
    전투 단계인데 레벨이 없는 경우는 조우 없는 단계(stages)로 이미 미확인이다. 어느 단계인지 모르는 레벨이 있으면 판단하지 않는다."""
    if not active or None in dropped:
        return
    for link, info in links.items():
        if link and info["kills"] and link not in by_stage and link not in (stages or {}) and link not in dropped:
            owner = _stage_owner(active, "kills_not_linked", link)
            _err(warnings, "kills_not_linked", link, f"재화 흐름 단계 {link}의 처치 수가 어떤 레벨과도 이어지지 않아 맞춰 보지 못했습니다. "
                                                    "그 단계에 combat_stage를 적거나 전투 단계와 같은 id로 둡니다.", owner=owner, part=link)


def _check_stage_foes(stage: dict, levels: list, group: list, enemies: dict, warnings: list) -> None:
    """전투 단계의 적과 조우의 적을 맞춘다. levels: 그 단계의 레벨, group: 그 단계의 조우 [(레벨, 조우, 놓은 적)]."""
    foes = cb.stage_foes(stage, enemies)
    if foes is None:
        return
    spots: dict = {}   # 단계 밖의 적 → 놓은 조우. 원인 하나가 조우마다 반복되지 않게 적별로 묶는다
    for _, x, placed in group:
        for eid in placed:
            if eid not in foes:
                spots.setdefault(eid, []).append(x["id"])
    for eid in sorted(spots):
        owner = _stage_owner(levels, "enemy_not_in_stage", eid)
        _err(warnings, "enemy_not_in_stage", owner,
             f"전투 단계 {stage['id']}에 나오지 않는 적입니다: {eid}(조우 {', '.join(spots[eid])}). 전투 계산과 레벨이 다른 적을 보고 있습니다.{cb.earlier_zone_hint([eid], stage, enemies)}",
             owner=owner, part=eid)
    for eid in sorted(foes - {k for _, _, placed in group for k in placed}):
        owner = _stage_owner(levels, "enemy_unplaced", eid)
        _err(warnings, "enemy_unplaced", owner, f"전투 단계 {stage['id']}의 적이 어떤 조우에도 없습니다: {eid}. 전투 계산만 그 적을 셉니다. "
                                                "앞 구역에서 끝난 적이면 전투 단계의 enemies 목록으로 빼고, 조우 밖에서만 나오면 레벨의 acknowledged에 이유를 적습니다.",
             owner=owner, part=eid)


def _check_curve_points(cfg, stages: dict | None, warnings: list) -> None:
    """표 곡선에서 어느 단계도 읽지 않는 값. 단계 이름을 바꾸면 옛 값이 남는다. 삭제된 단계의 값은 그대로 둔다."""
    if cfg is None or stages is None or cfg["curve"]["growth"] != "table":
        return
    for k in cfg["curve"]["values"]:
        if k not in stages:
            _err(warnings, "curve_unused_point", "threat_budget", f"table 곡선의 값이 가리키는 전투 단계가 없습니다: {k}.{did_you_mean(k, stages)}")


def _group_size(base, stage: dict | None, enemy_curve: dict | None) -> float | None:
    """곡선 ÷ 스탯 예산의 적 곡선: 평범한 조우에 평범한 적이 몇이나 드는가. 적 곡선이 구역 기준일 때만 잰다."""
    zone = (stage or {}).get("zone")
    if base is None or not enemy_curve or enemy_curve.get("by") != "zone" or not c.is_number(zone):
        return None
    unit = bg.curve_value(enemy_curve, zone)
    return round(base / unit, 4) if unit and unit > 0 else None


def _stage_rows(by_stage: dict, order: list | None, stages: dict | None, whole, kill_times: dict | None, links: dict, unit: str, enemy_curve: dict | None) -> list:
    """단계별 요약. 전투 단계 순서대로, 순서를 모르면 나온 순서대로.
    kill_ratio는 여기서 한 번만 소수 둘째 자리로 줄인다. check와 뷰어가 따로 줄이면 0.625가 0.62와 0.63으로 갈린다."""
    rows = []
    for sid in [k for k in order or [] if k in by_stage] + [k for k in by_stage if k not in (order or [])]:
        info, times = by_stage[sid], (kill_times or {}).get(sid)
        kills = info["kills"] if whole(sid) else None
        timed = {k: n for k, n in (kills or {}).items() if times and times.get(k) is not None}
        spent = sum(n * times[k] for k, n in timed.items()) if timed else None
        length = links.get(sid, {}).get("length") or None
        rows.append({"id": sid, "position": order.index(sid) + 1 if sid in (order or []) else None, "threat": info["threat"] if whole(sid) else None,
                     "kills": None if kills is None else {k: round(v, 4) for k, v in kills.items()},
                     "kill_time": None if spent is None else round(spent, 1), "kill_time_unknown": sorted(k for k in kills or {} if k not in timed) if times else [],
                     "duration": length, "time_unit": unit,
                     "kill_ratio": round(spent / length, 2) if spent is not None and length and unit in SECOND_UNITS else None,
                     "group_size": _group_size(info["base"], (stages or {}).get(sid), enemy_curve)})
    return rows


def _kill_check_note(by_stage: dict, links: dict, economy, whole) -> str | None:
    """처치 수를 어디까지 맞춰 봤는가. 재화 흐름은 없어도 미확인이 아니라서, 대조가 끝난 것처럼 읽히지 않게 따로 알린다."""
    if not by_stage:
        return None
    if economy is None:
        return "처치 수 대조: 재화 흐름을 함께 읽지 않아 하지 못했습니다."
    stated = [k for k in by_stage if links.get(k, {}).get("kills")]
    done = [k for k in stated if whole(k)]
    text = f"처치 수 대조: {len(done)}/{len(by_stage)} 단계"
    silent = [k for k in by_stage if k not in stated]
    if silent:
        text += f" · 재화 흐름에 처치 수가 없는 단계: {', '.join(silent)}"
    missed = [k for k in stated if k not in done]
    bare = [k for k in missed if by_stage[k]["whole"] and not by_stage[k]["group"]]
    if bare:
        text += f" · 조우가 없는 단계: {', '.join(bare)}"
    if len(bare) < len(missed):
        text += f" · 오류로 못 본 단계: {', '.join(k for k in missed if k not in bare)}"
    return text


def _notes(budget, cfg, rows: list, kill_check: str | None) -> list:
    """결과를 읽을 때 알아야 할 문장. 경고가 아니다. check와 뷰어가 같은 문장을 쓴다."""
    out = []
    if cfg is not None and c.provenance_kind(budget) in ("assumed", "unspecified"):
        out.append("곡선의 출처가 가정입니다. \"예산 안\"은 곡선과 맞는다는 뜻이고 난이도의 근거가 아닙니다.")
    for before, after in zip(rows, rows[1:]):
        if before["threat"] is not None and after["threat"] is not None and after["threat"] < before["threat"]:
            out.append(f"단계 {after['id']}의 위협도 합이 앞 단계 {before['id']}보다 줄었습니다: {_fmt(before['threat'])} → {_fmt(after['threat'])}. 의도가 아니면 조우와 횟수를 봅니다.")
    if kill_check:
        out.append(kill_check)
    return out


def validate(data: dict, enemies: dict | None = None, threat: dict | None = None, combat: dict | None = None, economy: dict | None = None,
             kill_times: dict | None = None, enemy_curve: dict | None = None) -> dict:
    """enemies: 함께 읽은 적의 {id: 항목}, threat: 적의 위협도 {id: 값}(적 검사와 같은 값), combat·economy: 전투 계산·재화 흐름 파일 내용.
    kill_times: 전투 계산의 처치 시간 {단계: {적: 초}}, enemy_curve: 스탯 예산의 적 곡선. 둘은 참고 값이라 없어도 미확인이 아니다.
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
    rows, seen, computed, unscored, sourced = [], set(), 0, [], []
    by_stage: dict = {}   # 전투 단계 → {"levels": [...], "group": [...], "kills": {...}, "whole": 조우를 모두 셌는가, "threat": 합, "base": 곡선 값}
    linked = {c.combat_link(e) for e in entries if c.is_active(e)}
    free = [k for k in order or [] if k not in linked]
    for lv in (e for e in entries if c.is_active(e)):
        _known_keys(lv, LEVEL_FIELDS, lv["id"], errors)
        link = lv.get("combat_stage")
        if link is not None and not isinstance(link, str):
            _err(errors, "schema", lv["id"], f"combat_stage는 전투 단계 id입니다: {link!r}")
            dropped.add(None)
            continue
        sid = c.combat_link(lv)
        if stages is not None and sid not in stages:
            _err(errors, "unknown_stage", lv["id"], f"전투 계산에 없는 단계입니다: {sid}.{_stage_hint(sid, free, order)}")
            dropped.add(None)
            continue
        if stages is not None and not c.is_active(stages[sid]):
            _err(warnings, "cut_referenced", lv["id"], f"삭제(cut)된 전투 단계 {sid}에 이었습니다.", owner=lv["id"])
            continue
        found, whole = _encounters(lv, cfg, seen, errors)
        base = _stage_budget(cfg, sid, order, lv["id"], errors)
        order_note = _order_note(cfg, sid, stages, order)
        info = by_stage.setdefault(sid, {"levels": [], "group": [], "kills": {}, "whole": True, "threat": 0.0, "base": base})
        info["levels"].append(lv)
        info["whole"] = info["whole"] and whole
        mine, kills, total, previous = [], {}, 0.0 if whole else None, None
        for x in found:
            score, placed, known = _score(x, lv["id"], enemies, threat, errors, warnings)
            info["whole"] = info["whole"] and known
            entry = _row(x, lv["id"], base, score, cfg, order_note, warnings)
            entry["vs_previous"] = round(score / previous, 4) if score is not None and previous else None
            entry["kill_time"] = _encounter_time(placed, (kill_times or {}).get(sid))
            mine.append(entry)
            previous = score
            info["group"].append((lv, x, placed))
            for k, n in placed.items():
                kills[k] = kills.get(k, 0) + n * _times(x, k)
                info["kills"][k] = info["kills"].get(k, 0) + n * _times(x, k)
            total = None if total is None or score is None else total + sum(n * threat[k] * _times(x, k) for k, n in placed.items())
            if score is None and known and threat is not None:
                unscored.append(f"{lv['id']}.{x['id']}")
            if "provenance" in x:
                sourced.append((lv["id"], x))
            computed += 1
        info["threat"] = None if total is None or info["threat"] is None else round(info["threat"] + total, 4)
        rows.append({"id": lv["id"], "name": lv.get("name"), "stage": sid, "encounters": mine, "kills": {k: round(v, 4) for k, v in kills.items()},
                     "threat": None if total is None else round(total, 4)})
    kills_tol = cfg["kills_tolerance"] if cfg else DEFAULT_TOLERANCE

    def counted(sid: str) -> bool:
        """그 단계의 조우를 빠짐없이 셌는가. 일부만 세어 틀린 값을 내지 않는다."""
        return by_stage[sid]["whole"] and bool(by_stage[sid]["group"]) and not dropped & {sid, None}

    links = _economy_stages(economy)
    for sid, info in by_stage.items():
        if counted(sid):
            if stages is not None and enemies is not None:
                _check_stage_foes(stages[sid], info["levels"], info["group"], enemies, warnings)
            if links.get(sid, {}).get("kills"):
                _compare_kills(sid, info, links[sid], kills_tol, enemies, warnings)
    _check_unlinked_kills(links, [e for e in entries if c.is_active(e)], by_stage, stages, dropped, warnings)
    _check_curve_points(cfg, stages, warnings)
    empty = [k for k in order or [] if not (k in by_stage and by_stage[k]["group"])]
    if empty:
        missing.add("stages")
    if not computed:
        missing.add("nothing")
    if unscored:
        missing.add("scores")
    summary = c.summary_counts(entries)
    summary["unverified"] += [f"{lid}.{x['id']}" for lid, x in sourced if lid not in summary["unverified"] and c.provenance_kind(x) == "assumed"]
    budget = data.get("threat_budget")
    if isinstance(budget, dict) and c.provenance_kind(budget) in ("assumed", "unspecified"):
        summary["unverified"] = ["threat_budget(위협도 예산)"] + summary["unverified"]
    stage_rows = _stage_rows(by_stage, order, stages, counted, kill_times, links, c.time_unit((economy or {}).get("economy")), enemy_curve)
    threats = [lv["threat"] for lv in rows]
    return {
        "kind": "levels",
        "count": len(entries),
        **summary,
        "levels": rows,
        "stages": stage_rows,
        "run_threat": round(sum(threats), 4) if threats and None not in threats and not dropped and not empty else None,
        "notes": _notes(budget, cfg, stage_rows, _kill_check_note(by_stage, links, economy, counted)),
        "encounters": computed,
        "unscored": unscored,
        "tolerance": cfg["tolerance"] if cfg else DEFAULT_TOLERANCE,
        "kills_tolerance": kills_tol,
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


def _mix(x: dict) -> str:
    """조우의 구성. 횟수가 다른 적은 판에서 나오는 횟수를 붙인다."""
    own = x.get("enemy_repeat") or {}
    return " · ".join(f"{k} {_fmt(v)}" + (f" (판에 {_fmt(own[k])}회)" if k in own else "") for k, v in x["enemies"].items())


def _vs(x: dict) -> str:
    return "–" if x["vs_previous"] is None else f"×{_fmt(round(x['vs_previous'], 2))}"


def _at_least(s: dict, text: str) -> str:
    """처치 시간을 모르는 적을 뺀 값은 실제보다 작다. 하한이라고 밝힌다."""
    return f"{text} 이상" if s["kill_time_unknown"] else text


def _ratio(s: dict) -> str:
    return "–" if s["kill_ratio"] is None else _at_least(s, f"{s['kill_ratio']:.2f}배")


def _spent(s: dict) -> str:
    """단일 대상 처치 시간과 단계 길이. 처치 시간을 모르면 빈 문자열."""
    if s["kill_time"] is None:
        return ""
    text = f"단일 대상 처치 시간 {_at_least(s, _fmt(s['kill_time']) + '초')}"
    if s["duration"] is not None:
        text += f" / 길이 {_fmt(s['duration'])}{s['time_unit']}"
    if s["kill_ratio"] is not None:
        text += f" = {_ratio(s)}"
    return text + (f" (처치 시간을 모르는 적 제외: {', '.join(s['kill_time_unknown'])})" if s["kill_time_unknown"] else "")


def _stage_time(s: dict) -> str:
    """표의 단일 대상 처치 시간. 표는 따로 옮겨 붙이므로 뺀 적을 칸에 함께 적는다."""
    if s["kill_time"] is None:
        return "–"
    left_out = f" ({', '.join(s['kill_time_unknown'])} 제외)" if s["kill_time_unknown"] else ""
    return _at_least(s, _fmt(s["kill_time"])) + left_out


def _verdict(x: dict) -> str:
    return FLAG_LABEL.get(x["flag"], "미확인")


def print_extra(result: dict) -> None:
    for lv in result["levels"]:
        print(f"레벨 {lv['id']} (단계 {lv['stage']}): 레벨 위협도 {_fmt(lv['threat'])} · 처치 {_parts(lv['kills']) or '없음'}")
        for x in lv["encounters"]:
            print(f"  조우 {x['id']} ({x['role'] or '역할 없음'} × {_fmt(x['repeat'])}): 위협도 {_fmt(x['threat'])} · 예산 {_fmt(x['expected'])} → {_verdict(x)}"
                  + (" ⚠" if x["flag"] in ("over", "under") else ""))
    for s in result["stages"]:
        parts = [f"위협도 합 {_fmt(s['threat'])}", _spent(s), f"평범한 조우의 적 수 {_fmt(s['group_size'])}" if s["group_size"] is not None else ""]
        print(f"단계 {s['id']}" + (f" (순서 {s['position']})" if s["position"] else "") + ": " + " · ".join(p for p in parts if p))
    if result["run_threat"] is not None:
        print(f"판 전체 위협도 {_fmt(result['run_threat'])}")
    for text in result["notes"]:
        print("참고: " + text)
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
    if "scores" in kinds:
        print("레벨 구성 미확인: 적의 위협도를 내지 못한 조우 " + ", ".join(result["unscored"]))


def table(data: dict, result: dict, ids: list[str] | None = None) -> str:
    """대화에 붙일 조우 표(마크다운). --ids는 컨셉 비교표용이라 여기서는 쓰지 않는다."""
    rows = ["| 레벨 | 조우 | 역할 | 횟수 | 구성 | 위협도 | 앞 조우 대비 | 처치 시간(초) | 예산 | 판정 |", "|---|---|---|---|---|---|---|---|---|---|"]
    for lv in result["levels"]:
        for x in lv["encounters"]:
            rows.append("| " + " | ".join((lv["id"], x["id"], x["role"] or "–", _fmt(x["repeat"]), _mix(x), _fmt(x["threat"]), _vs(x), _fmt(x["kill_time"]),
                                            f"{_fmt(x['expected'])} ({_fmt(x['low'])}~{_fmt(x['high'])})", _verdict(x))) + " |")
    rows += ["", "| 단계 | 순서 | 위협도 합 | 단일 대상 처치 시간(초) | 길이 | 처치 시간 ÷ 길이 | 평범한 조우의 적 수 |", "|---|---|---|---|---|---|---|"]
    for s in result["stages"]:
        length = "–" if s["duration"] is None else f"{_fmt(s['duration'])}{s['time_unit']}"
        rows.append("| " + " | ".join((s["id"], _fmt(s["position"]), _fmt(s["threat"]), _stage_time(s), length, _ratio(s), _fmt(s["group_size"]))) + " |")
    counted = [s for s in result["stages"] if s["kills"]]
    if counted:
        rows += ["", "재화 흐름 kills로 옮길 값(조우로 센 처치 수, 단계는 전투 단계 id, 파일에 쓰지 않음):"]
        rows += [f"- {s['id']}: {json.dumps(s['kills'], ensure_ascii=False)}" for s in counted]
    rows += ["", "위협도는 스탯으로 낸 설계 가정입니다. 실제 난이도나 재미를 판정하지 않습니다."]
    return "\n".join(rows)


def print_counts(result: dict) -> None:
    tail = f"오류 {len(result['errors'])} · 경고 {len(result['warnings'])}"
    if result.get("acknowledged"):
        tail += f" · 확인한 경고 {len(result['acknowledged'])}"
    print(f"레벨 {result['count']}개 · 조우 {result['encounters']}개 · {tail}")
