"""레벨 구성(data/levels.json): 레벨마다 조우를 순서대로 적고, 조우의 위협도를 곡선 예산과 비교한다.

조우의 위협도 = Σ(적 수 × 적의 위협도) + 적 없이 드는 소모. 위협도는 적 검사와 같은 값이다(스탯 예산의 원가, 없으면 threat_weights).
예산 = 곡선(전투 단계의 순서) × 역할 배수. 허용 오차를 넘으면 넘침·모자람을 경고한다.
조우의 처치 수(적 수 × 판당 횟수)를 재화 흐름의 처치 가정과, 나오는 적을 전투 단계의 적과 맞춰 본다.
곡선은 조우 초안에서 뽑으면 근거가 되지 못하므로 바깥 기준을 함께 낸다. 단일 대상 처치 시간과 단계 길이, 스탯 예산의 적 곡선이다.
페이싱: 적이 없는 구간도 조우로 적고, 조우를 판의 시계에 놓아 재화 흐름의 단계 길이·구매 시점과 맞춘다.
쉬는 곳·보상 사이의 부담은 조우의 위협도 × 횟수 ÷ 곡선, 곧 평범한 조우 몇 개 분량이다.
설계 가정의 계산이며 실제 난이도나 재미를 판정하지 않는다. 형식: level-design/references/levels-format.md
"""
from __future__ import annotations

import json
from operator import add

from . import budget as bg
from . import combat as cb
from . import common as c
from .common import add_issue as _err, did_you_mean

DEFAULT_TOLERANCE = bg.DEFAULT_TOLERANCE
ENCOUNTER_FIELDS = {"id", "name", "role", "enemies", "repeat", "enemy_repeat", "intent", "provenance", "note", "at", "duration", "rest", "reward", "hazard", "purchases", "open_for"}
LEVEL_FIELDS = {"id", "name", "combat_stage", "encounters", "intent", "status", "provenance", "acknowledged", "note", "greybox"}
GREYBOX_FIELDS = {"id", "check", "encounter", "expect", "note"}
GREYBOX_LABEL = {"passed": "통과", "failed": "실패", "open": "판정 없음", "none": "기록 없음"}
BUDGET_FIELDS = {"curve", "roles", "tolerance", "kills_tolerance", "provenance", "note"}
CURVE_FIELDS = {"growth", "base", "rate", "values", "note"}  # 곡선의 기준은 전투 단계의 순서로 정해져 있어 by를 쓰지 않는다
TOP_FIELDS = {"threat_budget", "pacing", "levels", "note"}
PACING_LIMITS = ("strong_at", "max_strong_run", "max_rest_load", "max_reward_load")
PACING_FIELDS = {*PACING_LIMITS, "carry_levels", "provenance", "note"}
SPAN_KINDS = {"rest": ("쉬는 곳 사이", "max_rest_load", "long_stretch", "쉬는 곳을 넣거나 조우를 줄입니다.", "쉬는 곳이"),
              "reward": ("보상 사이", "max_reward_load", "reward_drought", "보상을 넣거나 조우를 줄입니다.", "보상이")}  # 구간의 이름, 상한, 경고, 처방, 표시가 없을 때의 주어
FLAG_LABEL = {"ok": "예산 안", "over": "넘침", "under": "모자람", "quiet": "–"}
UNCHECKED_LABEL = {"enemies": "적", "combat": "전투 계산", "economy": "재화 흐름"}
SOURCE_LABEL = {"assumed": "가정", "computed": "계산", "measured": "측정", "unspecified": "미지정"}
SECOND_UNITS = ("초", "s", "sec", "secs", "second", "seconds")  # 전투 계산의 처치 시간(초)과 나눌 수 있는 재화 흐름 time_unit
KILL_HEADS = {"time": ("처치 시간(초)", "단일 대상 처치 시간(초)", "처치 시간 ÷ 길이"), "hits": ("처치 타수", "단일 대상 처치 타수", "타수 ÷ 길이")}  # 조우 표, 단계 표, 비율
LATE_ADVICE = {"money": "돈이 늦습니다. 가격이나 수입을 보고, 그때도 열려 있으면 조우에 open_for를 적습니다.",
               "after": "재화 흐름의 after 때문에 늦습니다. after를 고치거나, 그때도 열려 있으면 조우에 open_for를 적습니다.",
               "order": "구매 계획의 앞 구매를 기다리느라 늦습니다. 구매 순서를 보거나, 그때도 열려 있으면 조우에 open_for를 적습니다.",
               "stage_end": "단계 끝에 사는 게임입니다. 조우를 단계 끝으로 옮깁니다."}  # 재화 흐름이 구매 시점을 정한 까닭별 처방
EPS = 1e-9


_shown = c.json_text


def _positive(v) -> bool:
    return c.is_number(v) and v > 0


def _in_seconds(unit: str) -> bool:
    return unit.strip().lower() in SECOND_UNITS


def _known_keys(entry: dict, known: set, at: str, errors: list) -> bool:
    text = c.unknown_keys_text(entry, known)
    if text:
        _err(errors, "schema", at, text)
    return text is None


def _read_ratio(cfg: dict, key: str, where: str, errors: list) -> float | None:
    v = cfg.get(key, DEFAULT_TOLERANCE)
    if c.is_number(v) and 0 <= v < 1:
        return v
    _err(errors, "schema", where, f"{c.josa(key, '은는')} 0 이상 1 미만의 비율입니다: {v!r}")
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


def read_pacing(data: dict, tolerance: float, errors: list) -> dict:
    """페이싱 기준. 없어도 된다. 상한이 없으면 표만 내고 경고하지 않는다. 틀린 값은 오류를 남기고 없는 것으로 본다.
    strong_at의 기본은 평범한 조우의 범위 위(1 + 허용 오차)다."""
    out = {"strong_at": 1 + tolerance, "max_strong_run": None, "max_rest_load": None, "max_reward_load": None, "carry_levels": False}
    raw = data.get("pacing")
    if raw is None:
        return out
    if not isinstance(raw, dict):
        _err(errors, "schema", "pacing", f"pacing은 {{{', '.join(PACING_LIMITS)}, carry_levels}} 객체입니다.")
        return out
    _known_keys(raw, PACING_FIELDS, "pacing", errors)
    c.check_common(raw, "pacing", errors)
    for key in PACING_LIMITS:
        if key in raw and _positive(raw[key]):
            out[key] = raw[key]
        elif key in raw:
            _err(errors, "schema", "pacing", f"{c.josa(key, '은는')} 0보다 큰 수입니다: {_shown(raw[key])}")
    if isinstance(raw.get("carry_levels", False), bool):
        out["carry_levels"] = raw.get("carry_levels", False)
    else:
        _err(errors, "schema", "pacing", f"carry_levels는 true나 false입니다: {_shown(raw['carry_levels'])}")
    return out


def _at_or_after_zero(v) -> bool:
    return c.is_number(v) and v >= 0


PACE_KEYS = (("at", _at_or_after_zero, "at(판 시작부터의 시각)은 0 이상의 수입니다"),
             ("duration", _at_or_after_zero, "duration(이 조우가 차지하는 전체 시간)은 0 이상의 수입니다"),
             ("rest", lambda v: isinstance(v, bool), "rest(쉬는 곳인가)는 true나 false입니다"),
             ("reward", lambda v: isinstance(v, str) and bool(v.strip()), "reward(주는 보상)는 비어 있지 않은 글입니다"),
             ("hazard", _positive, "hazard(적 없이 드는 소모를 위협도로 적은 값)는 0보다 큰 수입니다"),
             ("open_for", _positive, "open_for(구매가 열려 있는 시간)는 0보다 큰 수입니다"),
             ("purchases", lambda v: isinstance(v, list) and bool(v) and all(isinstance(k, str) for k in v) and len(set(v)) == len(v),
              "purchases(재화 흐름의 구매 id 목록)는 겹치지 않는 id의 비어 있지 않은 배열입니다"))


def _check_pace_keys(x: dict, at: str, errors: list) -> bool:
    bad = [(key, text) for key, valid, text in PACE_KEYS if key in x and not valid(x[key])]
    for key, text in bad:
        _err(errors, "schema", at, f"{text}: {_shown(x[key])}")
    if "open_for" in x and not {"at", "purchases"} <= set(x):
        _err(errors, "schema", at, "open_for는 구매가 열려 있는 시간이라 at, purchases와 함께 씁니다.")
        return False
    return not bad


def _judged(x: dict) -> bool:
    """예산과 견주는 조우인가. 적이 있으면 그렇고, 적이 없으면 소모(hazard)에 역할까지 적은 경우만 그렇다."""
    return bool(x.get("enemies")) or ("hazard" in x and "role" in x)


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
    ok = _known_keys(x, ENCOUNTER_FIELDS | {"acknowledged"}, at, errors)
    if "acknowledged" in x:
        _err(errors, "schema", at, "acknowledged는 조우가 아니라 레벨에 적습니다. {경고 코드: {대상: 이유}} 형식이고 대상은 경고가 말하는 조우나 구간입니다.")
        ok = False
    ok = c.check_common(x, at, errors) and ok
    ok = _check_own_counts(x, at, errors) and ok
    ok = _check_pace_keys(x, at, errors) and ok
    foes = x.get("enemies")
    if not (isinstance(foes, dict) and all(_positive(v) for v in foes.values())):
        _err(errors, "schema", at, "enemies는 {적 id: 0보다 큰 수}입니다(한 번 만날 때 나오는 수, 평균이면 소수). 적이 없는 구간은 {}로 적습니다.")
        ok = False
    if "repeat" in x and not _positive(x["repeat"]):
        _err(errors, "schema", at, f"repeat(한 판에서 만나는 횟수)는 0보다 큰 수입니다: {x['repeat']!r}")
        ok = False
    role = x.get("role")
    if "role" in x and not isinstance(role, str):
        _err(errors, "schema", at, f"role은 threat_budget.roles의 역할 이름입니다: {role!r}")
        ok = False
    elif cfg is None or not _judged(x):
        pass   # 적이 없는 구간의 역할은 이름표다
    elif "role" not in x:
        _err(errors, "schema", at, f"role이 필요합니다. 역할: {', '.join(cfg['roles'])}")
        ok = False
    elif role not in cfg["roles"]:
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
    return (None if total is None else total + x.get("hazard", 0)), placed, known


def _row(x: dict, lid: str, base, threat, cfg, order_note: str, warnings: list) -> dict:
    row = {"id": x["id"], "name": x.get("name"), "role": x.get("role"), "repeat": x.get("repeat", 1), "enemies": x["enemies"],
           "enemy_repeat": x.get("enemy_repeat"), "threat": None if threat is None else round(threat, 4),
           "expected": None, "low": None, "high": None, "flag": None, "at": x.get("at"), "duration": x.get("duration"), "rest": x.get("rest", False),
           "reward": x.get("reward"), "hazard": x.get("hazard"), "purchases": x.get("purchases", []), "open_for": x.get("open_for"), "bought": {}}
    if not _judged(x):
        row["flag"] = "quiet"
        return row
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


def _encounter_cost(placed: dict, each: dict | None) -> float | None:
    """조우를 한 번 치우는 단일 대상 처치 시간이나 타수. 값을 모르는 적이 있으면 None."""
    if not each or not placed or any(each.get(k) is None for k in placed):
        return None
    return round(sum(n * each[k] for k, n in placed.items()), 1)


def _economy_stages(economy: dict | None) -> dict:
    """재화 흐름을 전투 단계별로 모은다 {전투 단계: {"kills": {적: 수}, "sources": 처치를 적은 단계의 출처, "ids": 처치를 적은 단계의 id, "length": 길이 합,
    "all": 이어진 단계의 id, "start"·"end": 판의 시계로 그 단계들의 처음과 끝}}.
    combat_stage로 이은 단계, 없으면 같은 id. 처치를 적지 않았거나 비워 둔 단계는 kills가 비어 있다. 단계에 출처가 없으면 economy의 출처를 쓴다.
    길이가 없는 단계를 지나면 그 뒤의 시각은 모른다."""
    out: dict = {}
    clock: float | None = 0.0
    stages = (economy or {}).get("stages")
    settings = (economy or {}).get("economy")
    for s in stages if isinstance(stages, list) else []:
        if not (isinstance(s, dict) and c.is_active(s)):
            continue
        link = out.setdefault(c.combat_link(s), {"kills": {}, "sources": set(), "ids": [], "length": 0, "all": [], "start": clock, "end": None})
        link["all"].append(s.get("id"))
        if c.is_number(s.get("duration")) and s["duration"] > 0:
            link["length"] += s["duration"]
            clock = None if clock is None else clock + s["duration"]
        else:
            clock = None
        link["end"] = clock
        kills = s.get("kills")
        if isinstance(kills, dict) and kills:
            link["sources"].add(c.provenance_kind(s if s.get("provenance") or not isinstance(settings, dict) else settings))
            link["ids"].append(s.get("id"))
            for k, v in kills.items():
                if c.is_number(v):
                    link["kills"][k] = link["kills"].get(k, 0) + v
    return out


def _stage_owner(levels: list, code: str, part: str) -> str:
    """단계 전체의 경고가 걸리는 레벨. 어느 레벨에서든 확인할 수 있게, 확인한 레벨이 있으면 그 레벨이고 없으면 첫 레벨이다."""
    return next((lv["id"] for lv in levels if c.ack_reason(lv, code, part)), levels[0]["id"])


def _source_text(kinds: set) -> str:
    return SOURCE_LABEL.get(next(iter(kinds)), "미지정") if len(kinds) == 1 else "섞임"


def _kill_sources(group: list, eid: str) -> dict:
    """그 적의 처치 수를 정한 조우와 출처 {조우 id: 출처}. 조우에 출처가 없으면 레벨의 출처다. 어떤 조우에도 없는 적이면 단계의 조우 전부를 본다."""
    placing = [(lv, x) for lv, x, placed in group if eid in placed] or [(lv, x) for lv, x, _ in group]
    return {x["id"]: c.provenance_kind(x if x.get("provenance") else lv) for lv, x in placing}


def _kills_advice(mine: dict, theirs: set) -> str:
    """고칠 쪽. 측정값이 앞서고, 측정값이 없으면 조우가 처치 수의 원본이다. mine: {조우 id: 출처}, theirs: 재화 흐름의 출처."""
    kinds = set(mine.values())
    if theirs == {"measured"}:
        if kinds == {"measured"}:
            return " 둘 다 측정값입니다. 측정한 판과 범위가 같은지 봅니다."
        others = [k for k, v in mine.items() if v != "measured"]
        return " 재화 흐름이 측정값이므로 " + (f"측정값이 아닌 조우({', '.join(others)})의" if "measured" in kinds else "조우의") + " 횟수를 고칩니다."
    if kinds == {"measured"}:
        return " 조우가 측정값이므로 재화 흐름의 kills를 고칩니다."
    if "measured" in kinds | theirs:
        return " 측정값이 일부만 있습니다. 측정한 값을 앞세워 나머지를 맞춥니다."
    return " 조우가 처치 수의 원본이므로 재화 흐름의 kills에 옮깁니다(--table levels 끝의 값)."


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
                 f"출처: 조우 {_source_text(set(sources.values()))}, 재화 흐름 {_source_text(link['sources'])}.{_kills_advice(sources, link['sources'])}",
                 owner=owner, part=eid)


def _check_unlinked_kills(links: dict, active: list, by_stage: dict, stages: dict | None, dropped: set, warnings: list) -> None:
    """처치 수가 있는 재화 흐름 단계가 어떤 레벨과도 이어지지 않으면 비교하지 못한 것을 알린다.
    전투 단계인데 레벨이 없는 경우는 조우 없는 단계(stages)로 이미 미확인이다. 어느 단계인지 모르는 레벨이 있으면 판단하지 않는다."""
    if not active or None in dropped:
        return
    for link, info in links.items():
        if link and info["kills"] and link not in by_stage and link not in (stages or {}) and link not in dropped:
            for eid in info["ids"]:
                owner = _stage_owner(active, "kills_not_linked", eid)
                advice = "그 단계에 combat_stage를 적거나 전투 단계와 같은 id로 둡니다." if eid == link else f"combat_stage {c.josa(link, '이가')} 전투 단계 id인지 봅니다."
                _err(warnings, "kills_not_linked", eid, f"재화 흐름 단계 {eid}의 처치 수가 어떤 레벨과도 이어지지 않아 맞춰 보지 못했습니다. {advice}", owner=owner, part=eid)


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
             f"전투 단계 {stage['id']}에 나오지 않는 적입니다: {eid}(조우 {', '.join(spots[eid])}). 전투 계산과 레벨이 다른 적을 보고 있습니다.{cb.outside_hint([eid], stage, enemies)}",
             owner=owner, part=eid)
    for eid in sorted(foes - {k for _, _, placed in group for k in placed}):
        owner = _stage_owner(levels, "enemy_unplaced", eid)
        _err(warnings, "enemy_unplaced", owner, f"전투 단계 {stage['id']}의 적이 어떤 조우에도 없습니다: {eid}. 전투 계산만 그 적을 셉니다. "
                                                "앞 구역에서 끝난 적이면 전투 단계의 enemies 목록으로 빼고, 조우 밖에서만 나오면 레벨의 acknowledged에 이유를 적습니다.",
             owner=owner, part=eid)


def _check_curve_points(cfg, stages: dict | None, order: list | None, active: list, warnings: list) -> None:
    """표 곡선에서 어느 단계도 읽지 않는 값. 단계 이름을 바꾸면 옛 값이 남는다. 삭제된 단계의 값은 그대로 둔다.
    값이 이미 있는 단계는 오타일 수 없어 값이 없는 단계만 추정한다. 다음 단계를 미리 적어 둔 값이면 아무 레벨에서 확인할 수 있다."""
    if cfg is None or stages is None or cfg["curve"]["growth"] != "table":
        return
    values = cfg["curve"]["values"]
    open_stages = [k for k in order or [] if k not in values]
    for k in values:
        if k not in stages:
            who = {"owner": _stage_owner(active, "curve_unused_point", k), "part": k} if active else {}
            _err(warnings, "curve_unused_point", "threat_budget", f"table 곡선의 값이 가리키는 전투 단계가 없습니다: {k}.{did_you_mean(k, open_stages)}", **who)


def _group_size(base, stage: dict | None, enemy_curve: dict | None) -> float | None:
    """곡선 ÷ 스탯 예산의 적 곡선: 평범한 조우에 평범한 적이 몇이나 드는가. 적 곡선이 구역 기준일 때만 잰다."""
    zone = (stage or {}).get("zone")
    if base is None or not enemy_curve or enemy_curve.get("by") != "zone" or not c.is_number(zone):
        return None
    unit = bg.curve_value(enemy_curve, zone)
    return round(base / unit, 4) if unit and unit > 0 else None


def _stage_cost(kills: dict | None, each: dict | None) -> tuple:
    """(처치 수 × 적마다의 값의 합, 값을 모르는 적). 아는 적이 없으면 합은 None."""
    known = {k: n for k, n in (kills or {}).items() if each and each.get(k) is not None}
    return (sum(n * each[k] for k, n in known.items()) if known else None), (sorted(k for k in kills or {} if k not in known) if each else [])


def _stage_rows(listed: list, by_stage: dict, order: list | None, stages: dict | None, whole, kill_times: dict | None, kill_hits: dict | None,
                links: dict, unit: str, enemy_curve: dict | None) -> list:
    """단계별 요약. listed: 전투 단계 순서대로, 순서를 모르면 나온 순서대로. 레벨이 없는 단계도 빈 행으로 낸다.
    처치 시간을 낼 수 없는 게임(공격 속도가 없는 턴제)은 타수를 낸다.
    비율은 여기서 한 번만 소수 둘째 자리로 줄인다. check와 뷰어가 따로 줄이면 0.625가 0.62와 0.63으로 갈린다."""
    rows = []
    for sid in listed:
        info = by_stage.get(sid)
        counted = info is not None and whole(sid)
        kills = info["kills"] if counted else None
        spent, left_out = _stage_cost(kills, (kill_times or {}).get(sid))
        hits, left_hits = (None, []) if spent is not None else _stage_cost(kills, (kill_hits or {}).get(sid))
        length = links.get(sid, {}).get("length") or None
        rows.append({"id": sid, "position": order.index(sid) + 1 if sid in (order or []) else None,
                     "curve": info["base"] if info else None, "threat": info["threat"] if counted else None,
                     "kills": None if kills is None else {k: round(v, 4) for k, v in kills.items()},
                     "kill_time": None if spent is None else round(spent, 1), "kill_hits": None if hits is None else round(hits, 1),
                     "kill_time_unknown": left_hits if hits is not None else left_out,
                     "duration": length, "time_unit": unit,
                     "kill_ratio": round(spent / length, 2) if spent is not None and length and _in_seconds(unit) else None,
                     "hits_per_unit": round(hits / length, 2) if hits is not None and length else None,
                     "group_size": _group_size(info["base"] if info else None, (stages or {}).get(sid), enemy_curve)})
    previous = None
    for row in rows:   # 값이 없는 단계를 건너뛰고 앞뒤를 잇는다
        row["vs_previous"] = round(row["threat"] / previous, 4) if row["threat"] is not None and previous else None
        previous = row["threat"] if row["threat"] is not None else previous
    return rows


def _check_kill_ratio(rows: list, by_stage: dict, warnings: list) -> None:
    """단일 대상 처치 시간이 단계 길이를 넘으면, 한 마리씩 잡아서는 그 단계의 적을 다 잡지 못한다. 무엇이 메우는지 사람이 확인한다."""
    for row in rows:
        if row["kill_ratio"] is None or row["kill_ratio"] <= 1:
            continue
        owner = _stage_owner(by_stage[row["id"]]["levels"], "kill_time_over_length", row["id"])
        bound = " 이상" if row["kill_time_unknown"] else ""
        _err(warnings, "kill_time_over_length", owner,
             f"단계 {row['id']}: 단일 대상 처치 시간 {_fmt(row['kill_time'])}초{bound} / 길이 {_fmt(row['duration'])}초 = {row['kill_ratio']:g}배{bound}입니다. "
             "그 단계의 기준 장비로 한 마리씩 잡으면 단계 안에 다 잡지 못합니다. 범위 공격·관통·판 안 성장이 메우면 그 이유를 이 단계 레벨의 "
             "acknowledged에 적고, 아니면 조우 수나 기준 장비를 고칩니다.", owner=owner, part=row["id"])


def _kill_check_note(listed: list, by_stage: dict, links: dict, economy, whole, dropped: set, astray: set) -> str | None:
    """처치 수를 어디까지 맞춰 봤는가. 재화 흐름은 없어도 미확인이 아니라서, 대조가 끝난 것처럼 읽히지 않게 따로 알린다.
    분모는 전투 단계다. astray: combat_stage가 틀려 어떤 단계에도 잇지 못한 재화 흐름 단계의 id."""
    if not by_stage:
        return None
    if economy is None:
        return "처치 수 대조: 재화 흐름을 함께 읽지 않아 하지 못했습니다."
    stated = [k for k in listed if links.get(k, {}).get("kills")]
    done = [k for k in stated if k in by_stage and whole(k)]
    text = f"처치 수 대조: {len(done)}/{len(listed)} 단계"
    silent = [k for k in listed if k not in stated and k not in astray]
    if silent:
        text += f" · 재화 흐름에 처치 수가 없는 단계: {', '.join(silent)}"
    missed = [k for k in listed if k not in done and k not in silent]
    bare = [k for k in missed if k not in astray and not dropped & {k, None} and (k not in by_stage or (by_stage[k]["whole"] and not by_stage[k]["group"]))]
    if bare:
        text += f" · 조우가 없는 단계: {', '.join(bare)}"
    if len(bare) < len(missed):
        text += f" · 오류로 못 본 단계: {', '.join(k for k in missed if k not in bare)}"
    strays = sorted(k for k in astray if k and k not in listed)
    if strays:
        text += f" · 이어지지 않은 재화 흐름 단계: {', '.join(strays)}"
    return text


def _gap_notes(rows: list, economy, unit: str, enemy_curve: dict | None) -> list:
    """표의 칸이 모두 빈 이유. 값이 말없이 사라지면 표를 읽는 사람이 다음 할 일을 찾지 못한다."""
    out = []
    shown = [s for s in rows if s["kills"] is not None]
    timed = [s for s in shown if s["kill_time"] is not None]
    hit = [s for s in shown if s["kill_hits"] is not None]
    if hit and not timed:
        out.append("처치 시간: 전투 계산에 공격 속도가 없어 타수로 냅니다.")
    elif hit:
        out.append(f"처치 시간: 공격 속도가 없는 단계: {', '.join(s['id'] for s in hit)}. 그 단계는 타수라 다른 단계와 견주지 못합니다.")
    counted = [s for s in shown if s["kill_time"] is not None or s["kill_hits"] is not None]
    lacking = [s["id"] for s in counted if s["duration"] is None]
    if counted and economy is None:
        out.append("처치 시간 ÷ 길이: 재화 흐름을 함께 읽지 않아 내지 않습니다.")
    elif counted and len(lacking) == len(counted):
        out.append("처치 시간 ÷ 길이: 재화 흐름에 단계 길이(duration)가 없어 내지 않습니다.")
    elif lacking:
        out.append(f"처치 시간 ÷ 길이: 길이를 모르는 단계: {', '.join(lacking)}.")
    sized = [s for s in timed if s["duration"] is not None]
    if sized and all(s["kill_ratio"] is None for s in sized):
        out.append("처치 시간 ÷ 길이: 재화 흐름의 time_unit이 초가 아니라 내지 않습니다.")
    based = [s for s in shown if s["curve"] is not None]
    if based and all(s["group_size"] is None for s in based):
        out.append("평범한 조우의 적 수: " + ("스탯 예산의 적 곡선이 없어 내지 않습니다." if not enemy_curve
                                          else "스탯 예산의 적 곡선이 구역(zone) 기준이 아니라 내지 않습니다." if enemy_curve.get("by") != "zone"
                                          else "전투 단계에 zone이 없어 내지 않습니다."))
    return out


def _time_text(a, b, unit: str) -> str:
    """구간의 시각. 순간이면 하나만 적는다."""
    return f"{_fmt(a)}{unit}" if a == b else f"{_fmt(a)}~{_fmt(b)}{unit}"


def _has_time(x: dict) -> bool:
    return x["at"] is not None or x["duration"] is not None


def _walk(ordered: list):
    """판에서 지나는 순서대로 (레벨, 조우)."""
    return ((lv, x) for lv in ordered for x in lv["encounters"])


def _known(fn, a, b):
    """둘 다 알 때만 합친다. 일부만 더한 값을 내지 않기 위해서다."""
    return None if a is None or b is None else fn(a, b)


def _place_in_time(ordered: list, links: dict, shaky: set) -> None:
    """조우를 판의 시계에 놓는다. at이 없으면 앞 조우가 끝날 때 시작한다. 단계의 첫 레벨은 재화 흐름이 말하는 단계 시작에서 출발한다.
    at만 있으면 순간이다. 시계는 뒤로 가지 않으므로 겹치는 구간이나 앞선 순간은 시계를 옮기지 않는다. 시각이 없는 조우를 지나면 at을 다시 만날 때까지 시각을 모른다.
    open_for로 열려 있는 시설은 판의 시간을 차지하지 않아서 시계를 옮기지 않는다.
    shaky: 조우나 레벨이 형식 오류로 빠진 단계. 빠진 시간이 어디에 있었는지 몰라서 적어 둔 at만 믿는다."""
    clock: float | None = 0.0
    begun: set = set()
    for lv in ordered:
        if lv["stage"] not in begun:
            begun.add(lv["stage"])
            start = links.get(lv["stage"], {}).get("start")
            unlinked = links and lv["stage"] not in links   # 재화 흐름에 없는 단계(대표가 아닌 등급)는 판의 어디인지 모른다
            clock = None if lv["stage"] in shaky or unlinked else clock if start is None else start
        for x in lv["encounters"]:
            timed = _has_time(x)
            x["start"] = x["at"] if x["at"] is not None else clock if timed else None
            x["end"] = x["start"] if x["start"] is None or not x["duration"] else round(x["start"] + x["duration"], 4)
            if not timed or lv["stage"] in shaky:
                clock = None
            elif x["end"] is not None and (x["open_for"] is None or x["duration"]):
                clock = x["end"] if clock is None else max(clock, x["end"])


def _holes(stretches: list, first, last) -> list:
    """단계의 시간 중 어떤 조우도 차지하지 않는 때. stretches: 길이가 있는 구간 [(시작, 끝)]. first·last: 단계의 처음과 끝(모르면 None).
    순간만 적은 단계(웨이브 시각표)는 길이를 적지 않은 것이므로 보지 않는다."""
    if not stretches:
        return []
    out = []
    reach = first if first is not None else min(a for a, _ in stretches)
    for a, b in sorted(stretches):
        if a > reach + EPS:
            out.append((reach, a))
        reach = max(reach, b)
    if last is not None and reach < last - EPS:
        out.append((reach, last))
    return out


def _long(x: dict) -> bool:
    return x["end"] > x["start"] + EPS


def _meet(a: dict, b: dict) -> bool:
    """두 구간이 시간을 나누는가. 맞닿은 구간은 나누지 않는다."""
    return a["start"] < b["end"] - EPS and b["start"] < a["end"] - EPS


def _overlaps(timed: list) -> list:
    """시간이 겹치는 조우의 쌍. 길이가 없는 순간은 겹치지 않는다. 둘 다 횟수가 1보다 작으면 택일이라 함께 나오지 않는다."""
    long = [x for x in timed if _long(x)]
    return [f"{a['id']}·{b['id']}" for i, a in enumerate(long) for b in long[i + 1:] if _meet(a, b) and (a["repeat"] >= 1 or b["repeat"] >= 1)]


def _fills(x: dict, timed: list) -> bool:
    """단계의 시간을 메우는 구간인가. 싸움과 겹치는 적 없는 조우는 그동안 열려 있는 시설이라 메우지 않는다."""
    return _long(x) and (x["weight"] != 0 or not any(y["weight"] != 0 and y["start"] is not None and _meet(x, y) for y in timed))


def _window_text(first, last, unit: str) -> str:
    """재화 흐름의 단계 시각. 길이가 없는 단계는 끝을 모른다."""
    return f"{_fmt(first)}{unit}부터" if last is None else _time_text(first, last, unit)


def _check_times(listed: list, ordered: list, by_stage: dict, shaky: set, links: dict, economy, unit: str, warnings: list) -> list:
    """단계마다 조우의 시각을 재화 흐름의 단계 길이와 맞춘다. 조우의 시각을 모두 알 때만 본다. 읽을 때 알아야 할 문장을 돌려준다.
    시각을 하나도 적지 않은 게임에는 문장을 내지 않는다."""
    if not any(_has_time(x) for _, x in _walk(ordered)):
        return []
    done, blind, plain, late, broken, pairs = [], [], [], [], [], []
    for sid in listed:
        info = by_stage.get(sid)
        xs = [x for lv in ordered if lv["stage"] == sid for x in lv["encounters"]]
        if sid in shaky:
            broken.append(sid)
            continue
        if info is None or not any(_has_time(x) for x in xs):
            plain.append(sid)
            continue
        unknown = [x["id"] for x in xs if x["start"] is None]
        if unknown:
            blind += unknown
            continue
        link = links.get(sid, {})
        first, last = link.get("start"), link.get("end")
        low, high = min(x["start"] for x in xs), max(x["end"] for x in xs)
        pairs += _overlaps(xs)
        outside = [x["id"] for x in xs if (first is not None and x["start"] < first - EPS) or (last is not None and x["end"] > last + EPS)]
        if outside:
            owner = _stage_owner(info["levels"], "time_outside_stage", sid)
            _err(warnings, "time_outside_stage", owner, f"단계 {sid}의 조우가 {_time_text(low, high, unit)}에 걸치는데 재화 흐름의 단계는 "
                 f"{_window_text(first, last, unit)}입니다(벗어난 조우: {', '.join(outside)}). 조우의 시각이나 재화 흐름의 duration을 맞춥니다."
                 + (" 싸움 동안 열려 있는 시설이면 duration 대신 open_for를 적습니다." if any(x["id"] in outside and x["weight"] == 0 for x in xs) else ""), owner=owner, part=sid)
        holes = _holes([(x["start"], x["end"]) for x in xs if _fills(x, xs)], first, last)
        if holes:
            owner = _stage_owner(info["levels"], "time_gap", sid)
            _err(warnings, "time_gap", owner, f"단계 {sid}에 어떤 조우도 차지하지 않는 시간이 있습니다: {', '.join(_time_text(a, b, unit) for a, b in holes)}. "
                 "적이 없는 구간이면 enemies를 {}로 적어 메우고, 앞 조우가 이어지는 시간이면 그 조우에 duration을 적습니다.", owner=owner, part=sid)
        (done if last is not None else late).append(sid)
    text = f"시각 대조: {len(done)}/{len(listed)} 단계" if economy is not None else "시각 대조: 재화 흐름을 함께 읽지 않아 단계 길이와 맞춰 보지 못했습니다"
    for label, ids in (("시각을 모르는 조우", blind), ("재화 흐름에 길이가 없는 단계", late if economy is not None else []), ("시각을 적지 않은 단계", plain), ("오류로 못 본 단계", broken)):
        if ids:
            text += f" · {label}: {', '.join(ids)}"
    out = [text]
    if pairs:
        out.append(f"시간이 겹치는 조우: {', '.join(pairs)}. 같은 시간에 둘 다 나오는 것으로 읽습니다.")
    return out


def _next_stages(economy) -> dict:
    """단계 끝에 사는 게임의 {재화 흐름 단계: 다음 단계}. 단계가 끝나는 때는 다음 단계가 시작하는 때라서 상점을 어느 쪽에 적어도 같은 시점이다. 다른 게임은 비어 있다."""
    settings = (economy or {}).get("economy")
    if not (isinstance(settings, dict) and settings.get("purchase_timing") == "stage_end"):
        return {}
    stages = (economy or {}).get("stages")
    ids = [s.get("id") for s in stages if isinstance(s, dict) and c.is_active(s)] if isinstance(stages, list) else []
    return dict(zip(ids, ids[1:]))


def _open_until(x: dict) -> float:
    """구매가 열려 있는 끝 시각. 조우가 끝나도 open_for만큼 더 열릴 수 있다."""
    return max(x["end"], round(x["start"] + (x["open_for"] or 0), 4))


def _off_span(row: dict, lv: dict, x: dict, links: dict, following: dict, unit: str) -> str | None:
    """구매가 조우의 시각이나 단계를 벗어나면 그 문장. 시각을 모르는 조우는 단계로 본다. 어느 단계인지 모르는 구매는 넘긴다.
    following: 단계 끝에 사는 게임의 다음 단계."""
    pid = c.josa(row["id"], "은는")
    if x["start"] is not None:
        closing = _open_until(x)
        if x["start"] - EPS <= row["at"] <= closing + EPS:
            return None
        advice = f"돈이 먼저 모입니다. 재화 흐름의 구매 after에 시각 {c.josa(_fmt(x['start']), '을를')} 적습니다." if row["at"] < x["start"] else LATE_ADVICE[row.get("held_by") or "money"]
        return f"구매 {pid} 재화 흐름에서 {_fmt(row['at'])}{unit}에 일어나는데 조우 {x['id']}의 시각은 {_time_text(x['start'], closing, unit)}입니다. {advice}"
    here = links.get(lv["stage"], {}).get("all", [lv["stage"]])
    if row.get("stage") is None or row["stage"] in here or following.get(row["stage"]) in here:
        return None
    return f"구매 {pid} 재화 흐름에서 단계 {row['stage']}에 일어나는데 조우 {x['id']}의 단계는 {lv['stage']}입니다. 재화 흐름의 구매 계획이나 조우의 자리를 맞춥니다."


def _check_purchases(ordered: list, links: dict, plan: dict | None, economy, unit: str, errors: list, warnings: list) -> list:
    """조우에 이은 구매가 그 조우의 시각에 일어나는가. plan: 재화 흐름이 계산한 구매 {id: 행}. 읽을 때 알아야 할 문장을 돌려준다."""
    raw = (economy or {}).get("purchases")
    written = [p for p in raw if isinstance(p, dict)] if isinstance(raw, list) else []
    cut = {p.get("id") for p in written if not c.is_active(p)}
    known = {*plan, *(p.get("id") for p in written if isinstance(p.get("id"), str))} if plan is not None else set()   # 적혀 있어도 재화 흐름의 오류로 계산하지 못한 구매가 있다
    tied = [(lv, x, pid) for lv, x in _walk(ordered) for pid in x["purchases"]]
    if not tied or plan is None:
        return []
    compared, off, blind, between, following = 0, 0, [], [], _next_stages(economy)
    for lv, x, pid in tied:
        where = f"{lv['id']}.{x['id']}"
        if pid in cut:
            _err(warnings, "cut_referenced", where, f"삭제(cut)된 구매에 이었습니다: {pid}.", owner=lv["id"], part=x["id"])
        elif pid not in known:
            _err(errors, "unknown_purchase", where, f"재화 흐름에 없는 구매입니다: {pid}.{did_you_mean(pid, known)}")
        elif plan.get(pid, {}).get("at") is None:
            (between if plan.get(pid, {}).get("runs") is not None else blind).append(pid)
        else:
            compared += 1
            x["bought"][pid] = plan[pid]["at"]
            text = _off_span(plan[pid], lv, x, links, following, unit)
            if text:
                off += 1
                _err(warnings, "purchase_off_span", where, text, owner=lv["id"], part=pid)
    text = f"구매 대조: {compared}/{len(tied)}" + (f" · 어긋남 {off}" if off else "")
    for label, ids in (("시점을 모르는 구매", blind), ("판 사이 구매", between)):
        if ids:
            text += f" · {label}: {', '.join(ids)}"
    ends = [k["end"] for k in links.values()]
    run_end = max(ends) if ends and None not in ends else None   # 길이가 없는 단계가 있으면 판 끝을 모른다
    past = [x["id"] for _, x in _walk(ordered) if x["open_for"] and run_end is not None and x["start"] is not None and _open_until(x) > run_end + EPS]
    return [text] + ([f"판 끝({_fmt(run_end)}{unit})을 넘어 열려 있는 시설: {', '.join(past)}. 판 끝까지 열려 있으면 그 시각까지만 적습니다."] if past else [])


def _beats(lv: dict) -> list:
    """레벨의 조우를 판에서 만나는 차례로 묶는다 [[같은 때의 조우]]. 목록 순서에 결과가 달리지 않게 시각을 모두 알면 시각으로 줄 세우고, 시간을 나누는 싸움을 한 묶음으로 둔다.
    적 없는 조우는 싸움 사이의 표시라 따로 두고, 같은 시각이면 싸움 앞에 놓는다. 시각을 모르는 조우가 있으면 목록 순서다."""
    xs = lv["encounters"]
    if any(x["start"] is None for x in xs):
        return [[x] for x in xs]
    calm, fights, reach = [], [], 0.0
    for x in sorted(xs, key=lambda k: k["start"]):
        if x["weight"] == 0:
            calm.append([x])
        elif fights and x["start"] < reach - EPS:
            fights[-1].append(x)
            reach = max(reach, x["end"])
        else:
            fights.append([x])
            reach = x["end"]
    return sorted(calm + fights, key=lambda beat: beat[0]["start"])


def _standing(x: dict, timed: list) -> bool:
    """시간을 차지하지 않고 서 있는 적 없는 조우인가. 시설이나 순간이라 구간을 시작하지 않는다."""
    return x["weight"] == 0 and x["start"] is not None and not _fills(x, timed)


def _reach(x: dict, shut, timed: list):
    """구간의 끝이 되는 시각. 적 없는 조우로 끊으면 그 시작까지이고, 싸움과 겹치는 적 없는 조우는 열려 있는 시설이라 끝을 늘리지 않는다."""
    if x["weight"] != 0 or x["start"] is None:
        return x["end"]
    return x["end"] if x is not shut and _fills(x, timed) else x["start"]


def _span_walk(ordered: list, kind: str, carry: bool, lost: bool) -> tuple[list, list]:
    """(표시로 끊은 구간, 끊지 못한 표시). kind: rest나 reward. 표시가 있는 조우는 자기 부담까지 넣고 끊는다. 적 없는 조우로 끊으면 길이는 그 시작까지다.
    횟수가 1보다 작은 표시는 없는 판이 있어 끊지 않는다. 위협이 없는 구간은 내지 않는다. 일부만 더한 값을 내지 않는다.
    lost: 형식 오류로 빠진 레벨이 있는가. 레벨을 넘어 이으면 어느 구간에 들었는지 몰라 부담을 내지 않는다."""
    out, maybe = [], []
    now: dict | None = None

    def close(by) -> None:
        nonlocal now
        if now is not None and now["threat"] != 0:
            load, threat = now["load"], now["threat"]
            length = None if now["start"] is None or now["end"] is None else round(now["end"] - now["start"], 4)
            out.append({**now, "closed_by": by, "load": None if load is None else round(load, 2), "threat": None if threat is None else round(threat, 4), "length": length,
                        "rate": round(load / length, 3) if load is not None and length else None})
        now = None

    for lv in ordered:
        if not carry:
            close(None)
        whole = not lv["kills_partial"] and not (carry and lost)
        for beat in _beats(lv):
            marked = [x for x in beat if x[kind]]
            shut = next((x for x in reversed(marked) if x["repeat"] >= 1), None)
            maybe += [x["id"] for x in marked if x["repeat"] < 1]
            for x in beat:
                if now is None and _standing(x, lv["encounters"]):
                    continue
                if now is None:
                    now = {"kind": kind, "level": lv["id"], "from": x["id"], "load": 0.0, "threat": 0.0, "start": x["start"], "end": x["start"]}
                now.update(to_level=lv["id"], to=x["id"],
                           load=_known(add, now["load"], x["load"] if whole else None), threat=_known(add, now["threat"], x["weight"] if whole else None),
                           end=_known(max, now["end"], _reach(x, shut, lv["encounters"])))
            if shut is not None:
                close(shut["id"])
    close(None)
    return out, maybe


def _passing(beat: list) -> bool:
    """쉬는 곳이 아니고 시간을 차지하지 않는 적 없는 순간인가. 숨 돌릴 틈이 없으므로 강한 조우 연속을 끊지 않는다."""
    x = beat[0]
    return len(beat) == 1 and x["weight"] == 0 and x["start"] is not None and not _long(x) and not x["rest"]


def _strong_walk(ordered: list, carry: bool) -> list:
    """강한 조우가 이어지는 곳. 길이는 횟수까지 센다. 강하지 않은 조우와 쉬는 곳에서 끊는다. 같은 때의 조우는 모두 강해야 강하다.
    구간과 같이, 횟수가 1보다 작은 조우는 없는 판이 있어 끊지 않는다."""
    out = []
    now: dict | None = None

    def close() -> None:
        nonlocal now
        if now is not None and now["length"] > 1 + EPS:
            out.append({**now, "length": round(now["length"], 4)})
        now = None

    for lv in ordered:
        if not carry:
            close()
        for beat in _beats(lv):
            if not all(x["strong"] for x in beat):
                if any(x["repeat"] >= 1 for x in beat) and not _passing(beat):
                    close()
                continue
            now = now or {"level": lv["id"], "from": beat[0]["id"], "length": 0.0}
            now.update(to_level=lv["id"], to=beat[-1]["id"], length=now["length"] + sum(x["repeat"] for x in beat))
            if any(x["rest"] and x["repeat"] >= 1 for x in beat):
                close()
    close()
    return out


def _span_key(s: dict) -> str:
    """구간의 id. 경고의 대상이라서 구간의 끝이 바뀌면 확인이 풀리고 경고가 돌아온다."""
    return s["from"] if s["from"] == s["to"] else f"{s['from']}~{s['to']}"


def _span_name(s: dict) -> str:
    """구간의 이름. 레벨을 넘으면 어느 레벨까지인지 적는다."""
    return _span_key(s) + (f" ({s['level']}~{s['to_level']})" if s["to_level"] != s["level"] else "")


def _ack_way(code: str, s: dict) -> str:
    """구간 경고를 확인하는 길. 대상은 괄호의 레벨 범위를 뺀 구간 이름이다."""
    return f"의도한 구간이면 레벨 {s['level']}의 acknowledged에 {{{_shown(code)}: {{{_shown(_span_key(s))}: 이유}}}}로 적습니다."


def _pace(ordered: list, settings: dict, lost: bool, warnings: list) -> tuple[dict, list]:
    """(구간과 연속, 읽을 때 알아야 할 문장). 상한을 넘으면 첫 조우에 경고를 건다. lost: 형식 오류로 빠진 레벨이 있는가."""
    spans, unsure, notes, kinds = [], [], [], []
    carry = settings["carry_levels"]
    for kind, (label, key, code, advice, subject) in SPAN_KINDS.items():
        across = carry or kind == "reward"   # 레벨이 끝나도 보상이 들어오지는 않는다. carry_levels는 체력의 일이다
        found, maybe = _span_walk(ordered, kind, across, lost)
        unsure += maybe
        limit = settings[key]
        marked = any(x[kind] for _, x in _walk(ordered))
        if limit is not None or marked:
            kinds.append(kind)
        for s in found:
            s.update(limit=limit, over=limit is not None and s["load"] is not None and s["load"] > limit + EPS)
            if s["over"]:
                _err(warnings, code, f"{s['level']}.{s['from']}", f"{label} 구간 {_span_name(s)}의 부담이 평범한 조우 {_fmt(s['load'])}개 분량입니다(상한 {_fmt(limit)}). {advice} {_ack_way(code, s)}",
                     owner=s["level"], part=_span_key(s), value=f"부담 {_fmt(s['load'])}")
        spans += found
        if limit is not None and not marked:
            notes.append(f"{subject} 없습니다. {kind} 표시가 있는 조우가 없어 {'판 전체' if across else '레벨 전체'}를 한 구간으로 봅니다.")
    runs = _strong_walk(ordered, carry and not lost)
    limit = settings["max_strong_run"]
    for s in runs:
        s.update(limit=limit, over=limit is not None and s["length"] > limit + EPS)
        if s["over"]:
            advice = "한 조우의 횟수입니다. 횟수를 줄이거나 조우를 나눠 사이에 약한 조우를 넣습니다." if s["from"] == s["to"] else "사이에 약한 조우나 쉬는 곳을 넣습니다."
            _err(warnings, "strong_run", f"{s['level']}.{s['from']}", f"강한 조우가 {_span_key(s)}에서 {_fmt(s['length'])}번 이어집니다(상한 {_fmt(limit)}). {advice} {_ack_way('strong_run', s)}",
                 owner=s["level"], part=_span_key(s), value=f"{_fmt(s['length'])}번")
    if limit is not None and not carry and not lost:
        crossing = [s for s in _strong_walk(ordered, True) if s["to_level"] != s["level"] and s["length"] > limit + EPS]
        notes += [f"레벨을 넘으면 강한 조우가 {_span_name(s)}에서 {_fmt(s['length'])}번 이어집니다(상한 {_fmt(limit)}). 레벨 사이에 체력이 이어지는 게임이면 carry_levels를 적습니다." for s in crossing]
    if unsure:
        notes.append(f"횟수가 1보다 작아 구간을 끊지 않은 조우: {', '.join(dict.fromkeys(unsure))}. 없는 판이 있어서입니다. 구간의 값은 평균이고 어느 한 경로의 값이 아닙니다.")
    if lost and (carry or "reward" in kinds):
        notes.append("형식 오류로 빠진 레벨이 있어 레벨을 넘는 구간의 부담을 내지 않고, 강한 조우 연속은 레벨 안에서만 봅니다.")
    return {"spans": spans, "strong_runs": runs, "kinds": kinds}, notes


def _beat_rate(beat: list):
    """길이당 부담. 시간을 나누는 묶음은 합을 묶음의 시간으로 나눈 값이라 행끼리 견줄 수 있다."""
    if any(x["load"] is None for x in beat):
        return None
    length = beat[0]["duration"] if len(beat) == 1 else max(x["end"] for x in beat) - min(x["start"] for x in beat)
    return round(sum(x["load"] for x in beat) / length, 3) if length else None


def _judge(item: dict, record: dict | None) -> str:
    """기록 하나의 판정. 수와 기대 범위가 있으면 수로 정하고, 없으면 기록에 적은 판정을 따른다."""
    if record is None:
        return "none"
    if item.get("expect") is not None and "value" in record:
        return "failed" if c.out_of_range(record["value"], item["expect"]) else "passed"
    if "passed" in record:
        return "passed" if record["passed"] else "failed"
    return "open"


def _greybox_rows(lv: dict, log: dict | None, seen: set, errors: list, warnings: list) -> list:
    """레벨의 그레이박스 확인 항목과 판정. log: 플레이 기록 {항목 id: 날짜순 기록}. 마지막 기록이 지금의 판정이다."""
    raw = lv.get("greybox", [])
    if not isinstance(raw, list):
        _err(errors, "schema", f"{lv['id']}.greybox", f"greybox는 확인 항목 {{id, check, encounter, expect}} 배열입니다: {_shown(raw)}")
        return []
    written = lv.get("encounters")
    spots = [x["id"] for x in written if isinstance(x, dict) and isinstance(x.get("id"), str)] if isinstance(written, list) else []
    rows = []
    for _, item in c.check_identity(raw, f"{lv['id']}.greybox", errors):
        at = f"{lv['id']}.{item['id']}"
        ok = _known_keys(item, GREYBOX_FIELDS, at, errors)
        if item["id"] in seen:
            _err(errors, "duplicate_id", at, f"그레이박스 확인 id가 겹칩니다: {item['id']}. 플레이 기록이 이 id로 가리키므로 파일 전체에서 하나입니다.")
            ok = False
        seen.add(item["id"])
        if not (isinstance(item.get("check"), str) and item["check"].strip()):
            _err(errors, "schema", at, "check(그래픽 없이 확인할 것)는 비어 있지 않은 글입니다.")
            ok = False
        if "expect" in item and not c.valid_range(item["expect"]):
            _err(errors, "schema", at, f"expect는 기대 범위 [최소, 최대]이고 한쪽은 null로 비울 수 있습니다: {_shown(item['expect'])}")
            ok = False
        if "encounter" in item and item["encounter"] not in spots:
            _err(errors, "unknown_encounter", at, f"이 레벨에 없는 조우입니다: {item['encounter']}.{did_you_mean(str(item['encounter']), spots)}")
            ok = False
        if not ok:
            continue
        record = ((log or {}).get(item["id"]) or [None])[-1]
        status = _judge(item, record)
        got = record or {}
        rows.append({"id": item["id"], "check": item["check"], "encounter": item.get("encounter"), "expect": item.get("expect"), "status": status,
                     "value": got.get("value"), "session": got.get("session"), "date": got.get("date"), "n": got.get("n")})
        if status == "failed":
            told = f"값 {_fmt(got['value'])}" if "value" in got else "실패로 기록"
            aim = f", 기대 {c.range_text(item['expect'])}" if item.get("expect") is not None else ""
            _err(warnings, "greybox_failed", at, f"그레이박스 확인 {item['id']}: {item['check']} → {told}{aim} (세션 {got['session']}). 레벨이나 기대 범위를 고칩니다.",
                 owner=lv["id"], part=item["id"], value=told)
    return rows


def _greybox_note(rows: list, log: dict | None, played: dict | None = None) -> list:
    """확인 목록을 어디까지 해 봤는가. 목록을 쓰지 않는 게임에는 말하지 않는다. 다만 목록 없이 그 단계를 플레이한 기록이 있으면 알린다."""
    items = [x for lv in rows for x in lv["greybox"]]
    if not items:
        hit = [f"{lv['id']}({lv['stage']}, 세션 {played[lv['stage']]}개)" for lv in rows if lv["stage"] in (played or {})]
        if not hit:
            return []
        return [f"그레이박스 확인 항목이 없습니다: 플레이 기록이 있는 레벨 {', '.join(hit)}. 확인할 값(분당 처치, 처음 죽은 시각 등)을 "
                "levels.json의 greybox에 적으면 플레이 기록의 greybox와 이어져 판정됩니다. 처치 시간이 단계 길이를 넘는다는 경고"
                "(kill_time_over_length)가 난 단계면 분당 처치를 항목으로 둡니다."]
    counts = {k: sum(x["status"] == k for x in items) for k in GREYBOX_LABEL}
    text = f"그레이박스 확인: {len(items)}개 · " + " · ".join(f"{GREYBOX_LABEL[k]} {n}" for k, n in counts.items() if n)
    bare = [lv["id"] for lv in rows if not lv["greybox"]]
    if bare:
        text += f" · 항목이 없는 레벨: {', '.join(bare)}"
    return [text + (" · 플레이 기록을 함께 읽지 않았습니다" if log is None else "")]


def _pace_used(data: dict, ordered: list) -> bool:
    """페이싱 표를 낼 게임인가. 페이싱 기준이나 표시를 하나도 적지 않은 게임의 표는 그대로 둔다."""
    return "pacing" in data or any(_has_time(x) or x["rest"] or x["reward"] or x["hazard"] or x["purchases"] or not x["enemies"] for _, x in _walk(ordered))


def _limits_assumed(data: dict) -> bool:
    raw = data.get("pacing")
    return isinstance(raw, dict) and any(k in raw for k in PACING_LIMITS) and c.provenance_kind(raw) in ("assumed", "unspecified")


def _notes(budget, cfg, rows: list, kill_check: str | None, gaps: list) -> list:
    """결과를 읽을 때 알아야 할 문장. 경고가 아니다. check와 뷰어가 같은 문장을 쓴다. 곡선도 함께 내려간 단계는 의도를 이미 적은 것이라 말하지 않는다."""
    out = []
    if cfg is not None and c.provenance_kind(budget) in ("assumed", "unspecified"):
        out.append("곡선의 출처가 가정입니다. \"예산 안\"은 곡선과 맞는다는 뜻이고 난이도의 근거가 아닙니다.")
    measured = [s for s in rows if s["threat"] is not None]   # 값이 없는 단계를 건너뛰고 앞뒤를 잇는다
    for before, after in zip(measured, measured[1:]):
        falling = before["curve"] is not None and after["curve"] is not None and after["curve"] < before["curve"]
        if after["threat"] < before["threat"] and not falling:
            out.append(f"단계 {after['id']}의 위협도 합이 앞 단계 {before['id']}보다 줄었습니다: {_fmt(before['threat'])} → {_fmt(after['threat'])}. 의도가 아니면 조우와 횟수를 봅니다.")
    for s in rows:   # 하한만 아는 비율이 1배 아래면 경고가 나지 않는다. 모르는 적이 그 차이를 메울 수 있다
        if s["kill_ratio"] is not None and s["kill_ratio"] <= 1 and s["kill_time_unknown"]:
            out.append(f"단계 {s['id']}: 처치 시간 / 길이가 {s['kill_ratio']:g}배 이상입니다. 처치 시간을 모르는 적({', '.join(s['kill_time_unknown'])})을 빼고 낸 하한이라 "
                       "1배를 넘는지 모릅니다. 그 적을 전투 계산의 그 단계에 넣으면 잽니다.")
    if kill_check:
        out.append(kill_check)
    return out + gaps


def validate(data: dict, enemies: dict | None = None, threat: dict | None = None, combat: dict | None = None, economy: dict | None = None,
             kill_times: dict | None = None, kill_hits: dict | None = None, enemy_curve: dict | None = None, purchases: dict | None = None,
             greybox_log: dict | None = None, played_stages: dict | None = None) -> dict:
    """enemies: 함께 읽은 적의 {id: 항목}, threat: 적의 위협도 {id: 값}(적 검사와 같은 값), combat·economy: 전투 계산·재화 흐름 파일 내용.
    kill_times·kill_hits: 전투 계산의 처치 시간과 타수 {단계: {적: 값}}, enemy_curve: 스탯 예산의 적 곡선. 참고 값이라 없어도 미확인이 아니다.
    purchases: 재화 흐름이 계산한 구매 {id: 행}, greybox_log: 플레이 기록의 그레이박스 확인 {항목 id: 날짜순 기록}.
    played_stages: 플레이 기록의 단계 기록 {단계 id: 세션 수}. 확인 항목이 없는 레벨의 단계를 플레이했으면 알린다.
    적이나 전투 계산이 없으면 미확인으로 센다. 재화 흐름은 조우가 구매를 가리킬 때만 미확인이고, 그 밖에는 있을 때만 맞춰 본다."""
    errors: list = []
    warnings: list = []
    _known_keys(data, TOP_FIELDS, "levels", errors)
    cfg = read_settings(data, errors)
    settings = read_pacing(data, cfg["tolerance"] if cfg else DEFAULT_TOLERANCE, errors)
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
    rows, seen, computed, unscored, sourced, checks = [], set(), 0, [], [], set()
    by_stage: dict = {}   # 전투 단계 → {"levels": [...], "group": [...], "kills": {...}, "whole": 조우를 모두 셌는가, "threat": 합, "base": 곡선 값}
    active = [e for e in entries if c.is_active(e)]
    linked = {c.combat_link(e) for e in active}
    free = [k for k in order or [] if k not in linked]
    for lv in active:
        _known_keys(lv, LEVEL_FIELDS, lv["id"], errors)
        link = lv.get("combat_stage")
        if link is not None and not isinstance(link, str):
            _err(errors, "schema", lv["id"], f"combat_stage는 전투 단계 id입니다: {link!r}")
            dropped.add(None)
            continue
        sid = c.combat_link(lv)
        if stages is not None and sid not in stages:
            _err(errors, "unknown_stage", lv["id"], f"전투 계산에 없는 단계입니다: {sid}."
                 + cb.stage_hint(sid, free, order, "레벨이 없는 전투 단계", "이미 레벨이 있습니다. 그 단계에 더 두는 레벨이면 combat_stage를 그 id로 적습니다"))
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
        mine, kills, total, previous, complete = [], {}, 0.0 if whole else None, None, whole
        for x in found:
            score, placed, known = _score(x, lv["id"], enemies, threat, errors, warnings)
            info["whole"] = info["whole"] and known
            complete = complete and known
            entry = _row(x, lv["id"], base, score, cfg, order_note, warnings)
            fight = bool(x["enemies"]) or "hazard" in x   # 적이 없는 구간을 건너뛰어 앞 싸움과 견준다
            entry["vs_previous"] = round(score / previous, 4) if fight and score is not None and previous else None
            weight = None if score is None else sum(n * threat[k] * _times(x, k) for k, n in placed.items()) + x.get("hazard", 0) * x.get("repeat", 1)
            entry["weight"] = None if weight is None else round(weight, 4)
            entry["intensity"] = round(score / base, 4) if score is not None and base else None
            entry["load"] = round(weight / base, 4) if weight is not None and base else None
            entry["strong"] = entry["intensity"] is not None and entry["intensity"] >= settings["strong_at"] - EPS
            entry["kill_time"] = _encounter_cost(placed, (kill_times or {}).get(sid)) if known else None
            entry["kill_hits"] = _encounter_cost(placed, (kill_hits or {}).get(sid)) if known and entry["kill_time"] is None else None
            mine.append(entry)
            if fight:
                previous = score
            if x["enemies"]:
                info["group"].append((lv, x, placed))
            for k, n in placed.items():
                kills[k] = kills.get(k, 0) + n * _times(x, k)
                info["kills"][k] = info["kills"].get(k, 0) + n * _times(x, k)
            total = None if total is None or score is None else total + weight
            if score is None and known and threat is not None:
                unscored.append(f"{lv['id']}.{x['id']}")
            if "provenance" in x:
                sourced.append((lv["id"], x))
            computed += 1
        info["threat"] = None if total is None or info["threat"] is None else round(info["threat"] + total, 4)
        rows.append({"id": lv["id"], "name": lv.get("name"), "stage": sid, "encounters": mine, "kills": {k: round(v, 4) for k, v in kills.items()},
                     "kills_partial": not complete, "threat": None if total is None else round(total, 4),
                     "greybox": _greybox_rows(lv, greybox_log, checks, errors, warnings)})
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
    _check_unlinked_kills(links, active, by_stage, stages, dropped, warnings)
    _check_curve_points(cfg, stages, order, active, warnings)
    unit = c.time_unit((economy or {}).get("economy"))
    listed = list(order or []) + [k for k in by_stage if k not in (order or [])]
    ordered = sorted(rows, key=lambda lv: listed.index(lv["stage"]))   # 파일 순서가 아니라 판에서 지나는 순서
    shaky = {k for k in listed if dropped & {k, None} or not by_stage.get(k, {"whole": True})["whole"]}
    _place_in_time(ordered, links, shaky)
    pace_notes = _check_times(listed, ordered, by_stage, shaky, links, economy, unit, warnings) + _check_purchases(ordered, links, purchases, economy, unit, errors, warnings)
    pacing, walk_notes = _pace(ordered, settings, bool(dropped), warnings)
    for beat in (beat for lv in ordered for beat in _beats(lv)):
        for x in beat:
            x["rate"] = _beat_rate(beat)
    for _, x in _walk(ordered):   # 구간은 줄이기 전의 값으로 더했다. check와 뷰어가 따로 줄이지 않게 여기서 한 번만 줄인다
        x["intensity"] = None if x["intensity"] is None else round(x["intensity"], 2)
        x["load"] = None if x["load"] is None else round(x["load"], 2)
    if purchases is None and any(x["purchases"] for _, x in _walk(ordered)):
        missing.add("economy")
    empty = [k for k in order or [] if not (k in by_stage and by_stage[k]["group"])]
    unread = [k for k in empty if dropped & {k, None} or (k in by_stage and not by_stage[k]["whole"])]   # 조우나 레벨이 형식 오류로 빠진 단계
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
    summary["unverified"] += [f"그레이박스 {lv['id']}.{x['id']}({GREYBOX_LABEL[x['status']]})" for lv in rows for x in lv["greybox"] if x["status"] != "passed"]
    if _limits_assumed(data):
        summary["unverified"] = ["pacing(페이싱 기준)"] + summary["unverified"]
        walk_notes = ["페이싱 기준의 출처가 가정입니다. 경고가 없어도 리듬이 좋다는 뜻이 아닙니다.", *walk_notes]
    stage_rows = _stage_rows(listed, by_stage, order, stages, counted, kill_times, kill_hits, links, unit, enemy_curve)
    _check_kill_ratio(stage_rows, by_stage, warnings)
    astray = {i for link, info in links.items() if link not in (stages or {}) for i in info["ids"]} if stages is not None else set()
    threats = [lv["threat"] for lv in rows]
    return {
        "kind": "levels",
        "count": len(entries),
        **summary,
        "levels": rows,
        "stages": stage_rows,
        "kill_measure": "hits" if any(s["kill_hits"] is not None for s in stage_rows) and all(s["kill_time"] is None for s in stage_rows) else "time",
        "run_threat": round(sum(threats), 4) if threats and None not in threats and not dropped and not empty else None,
        "notes": _notes(budget, cfg, stage_rows, _kill_check_note(listed, by_stage, links, economy, counted, dropped, astray),
                        _gap_notes(stage_rows, economy, unit, enemy_curve)) + pace_notes + walk_notes + _greybox_note(rows, greybox_log, played_stages),
        "pacing": {"used": _pace_used(data, ordered), "time_unit": unit, "carry_levels": settings["carry_levels"], "strong_at": round(settings["strong_at"], 4),
                   "order": [lv["id"] for lv in ordered], **pacing},
        "encounters": computed,
        "unscored": unscored,
        "tolerance": cfg["tolerance"] if cfg else DEFAULT_TOLERANCE,
        "kills_tolerance": kills_tol,
        "stages_without_levels": [k for k in empty if k not in unread],
        "stages_unread": unread,
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
    parts = [f"{k} {_fmt(v)}" + (f" (판에 {_fmt(own[k])}회)" if k in own else "") for k, v in x["enemies"].items()]
    if x.get("hazard"):
        parts.append(f"소모 {_fmt(x['hazard'])}")
    return " · ".join(parts) or "적 없음"


def _vs(x: dict) -> str:
    return "–" if x["vs_previous"] is None else f"×{_fmt(round(x['vs_previous'], 2))}"


def _at_least(s: dict, text: str) -> str:
    """처치 시간을 모르는 적을 뺀 값은 실제보다 작다. 하한이라고 밝힌다."""
    return f"{text} 이상" if s["kill_time_unknown"] else text


def _ratio(s: dict) -> str:
    if s["kill_ratio"] is not None:
        return _at_least(s, f"{s['kill_ratio']:.2f}배")
    return "–" if s["hits_per_unit"] is None else _at_least(s, f"{s['hits_per_unit']:.2f}타/{s['time_unit']}")


def _spent(s: dict) -> str:
    """단일 대상 처치 시간(없으면 타수)과 단계 길이. 둘 다 모르면 빈 문자열."""
    if s["kill_time"] is None and s["kill_hits"] is None:
        return ""
    noun, cost = ("시간", _fmt(s["kill_time"]) + "초") if s["kill_time"] is not None else ("타수", _fmt(s["kill_hits"]) + "타")
    text = f"단일 대상 처치 {noun} {_at_least(s, cost)}"
    if s["duration"] is not None:
        text += f" / 길이 {_fmt(s['duration'])}{s['time_unit']}"
    if _ratio(s) != "–":
        text += f" = {_ratio(s)}"
    return text + (f" (처치 {c.josa(noun, '을를')} 모르는 적 제외: {', '.join(s['kill_time_unknown'])})" if s["kill_time_unknown"] else "")


def _cost(x: dict) -> str:
    """조우의 처치 시간. 없으면 타수."""
    return _fmt(x["kill_time"]) if x["kill_time"] is not None or x["kill_hits"] is None else _fmt(x["kill_hits"]) + "타"


def _stage_time(s: dict) -> str:
    """표의 단일 대상 처치 시간(없으면 타수). 표는 따로 옮겨 붙이므로 뺀 적을 칸에 함께 적는다."""
    if s["kill_time"] is None and s["kill_hits"] is None:
        return "–"
    left_out = f" ({', '.join(s['kill_time_unknown'])} 제외)" if s["kill_time_unknown"] else ""
    return _at_least(s, _cost(s)) + left_out


def _verdict(x: dict) -> str:
    return FLAG_LABEL.get(x["flag"], "미확인")


def print_extra(result: dict) -> None:
    for lv in result["levels"]:
        print(f"레벨 {lv['id']} (단계 {lv['stage']}): 레벨 위협도 {_fmt(lv['threat'])} · 처치 {_parts(lv['kills']) or '없음'}" + (" (일부)" if lv["kills_partial"] else ""))
        for x in lv["encounters"]:
            print(f"  조우 {x['id']} ({x['role'] or '역할 없음'} × {_fmt(x['repeat'])}): 위협도 {_fmt(x['threat'])} · 예산 {_fmt(x['expected'])} → {_verdict(x)}"
                  + (" ⚠" if x["flag"] in ("over", "under") else ""))
    for s in result["stages"]:
        parts = [f"위협도 합 {_fmt(s['threat'])}", _spent(s), f"평범한 조우의 적 수 {_fmt(s['group_size'])}" if s["group_size"] is not None else ""]
        print(f"단계 {s['id']}" + (f" (순서 {s['position']})" if s["position"] else "") + ": " + " · ".join(p for p in parts if p))
    if result["run_threat"] is not None:
        print(f"판 전체 위협도 {_fmt(result['run_threat'])}")
    pacing = result["pacing"]
    for s in _shown_spans(pacing):
        length = "" if s["length"] is None else f" · 길이 {_fmt(s['length'])}{pacing['time_unit']}"
        print(f"구간 {SPAN_KINDS[s['kind']][0]} {_span_name(s)}: 부담 {_fmt(s['load'])}{length}" + _over_mark(s, SPAN_KINDS[s["kind"]][2], result))
    for s in pacing["strong_runs"]:
        print(f"강한 조우 연속 {_span_name(s)}: {_fmt(s['length'])}번 (세기 {_fmt(pacing['strong_at'])} 이상)" + _over_mark(s, "strong_run", result))
    for text in result["notes"]:
        print("참고: " + text)
    kinds = result["unchecked_kinds"]
    data_kinds = [UNCHECKED_LABEL[k] for k in kinds if k in UNCHECKED_LABEL]
    if data_kinds:
        print("레벨 구성 미확인: " + ", ".join(data_kinds) + " 데이터를 함께 검사하지 않았거나 읽지 못함")
    if "threat_budget" in kinds:
        print("레벨 구성 미확인: threat_budget이 없어 위협도를 예산과 비교하지 못함")
    if result["stages_without_levels"]:
        print("레벨 구성 미확인: 적이 있는 조우가 없는 전투 단계 " + ", ".join(result["stages_without_levels"]))
    if result["stages_unread"]:
        print("레벨 구성 미확인: 형식 오류로 조우를 세지 못한 전투 단계 " + ", ".join(result["stages_unread"]))
    if "nothing" in kinds:
        print("레벨 구성 미확인: 계산한 조우가 없음(빈 levels이거나 모두 삭제)")
    if "scores" in kinds:
        print("레벨 구성 미확인: 적의 위협도를 내지 못한 조우 " + ", ".join(result["unscored"]))


def _over_mark(s: dict, code: str, result: dict) -> str:
    """상한을 넘었다는 표시. 확인한 구간은 확인함이다."""
    if not s["over"]:
        return ""
    return " (확인함)" if any(a["code"] == code and a.get("part") == _span_key(s) for a in result.get("acknowledged", [])) else " ⚠"


def _shown_spans(pacing: dict) -> list:
    """표에 낼 구간. 표시도 상한도 없는 종류는 뺀다. 회복이 없는 게임의 쉬는 곳 구간은 판 전체 한 줄일 뿐이다."""
    return [s for s in pacing["spans"] if s["kind"] in pacing["kinds"]] if pacing["used"] else []


def _marks(x: dict, unit: str) -> str:
    """조우의 페이싱 표시. 구매는 재화 흐름의 시점을 함께 적는다."""
    parts = ["쉬는 곳"] if x["rest"] else []
    parts += [f"보상: {c.table_cell(x['reward'])}"] if x["reward"] else []
    if x["purchases"]:
        parts.append("구매 " + ", ".join(k + (f" {_fmt(x['bought'][k])}{unit}" if k in x["bought"] else "") for k in x["purchases"]))
    parts += [f"{_time_text(x['start'], _open_until(x), unit)} 열림"] if x["open_for"] and x["start"] is not None else []
    parts += ["강함"] if x["strong"] else []
    return " · ".join(parts) or "–"


def _greybox_table(result: dict) -> list:
    """레벨마다 그래픽 없이 확인할 항목과 기록. 플레이 기록에 옮길 때 보는 표다."""
    rows = []
    for lv in result["levels"]:
        for x in lv["greybox"]:
            aim = "–" if x["expect"] is None else c.range_text(x["expect"])
            got = "–" if x["session"] is None else (_fmt(x["value"]) + f" ({x['session']})" if x["value"] is not None else x["session"])
            rows.append("| " + " | ".join((lv["id"], f"{x['id']}: {c.table_cell(x['check'])}", x["encounter"] or "–", aim, got, GREYBOX_LABEL[x["status"]])) + " |")
    return ["", "| 레벨 | 확인 | 조우 | 기대 | 기록 | 판정 |", "|---|---|---|---|---|---|", *rows] if rows else []


def _pace_table(result: dict) -> list:
    """조우의 리듬과 구간. 페이싱을 쓰지 않는 게임은 강한 조우의 연속만 낸다."""
    pacing, unit, rows = result["pacing"], result["pacing"]["time_unit"], []
    if pacing["used"]:
        rows += ["", "| 레벨 | 조우 | 시각 | 세기 | 부담 | 길이당 부담 | 표시 |", "|---|---|---|---|---|---|---|"]
        for lv in sorted(result["levels"], key=lambda k: pacing["order"].index(k["id"])):   # 판에서 지나는 순서로 읽는 표다
            for x in (x for beat in _beats(lv) for x in beat):
                when = "–" if x["start"] is None else _time_text(x["start"], x["end"], unit)
                rows.append("| " + " | ".join((lv["id"], x["id"], when, _fmt(x["intensity"]), _fmt(x["load"]), _fmt(x["rate"]), _marks(x, unit))) + " |")
        rows += ["", f"세기는 평범한 조우가 1입니다. 강함은 세기 {_fmt(pacing['strong_at'])} 이상입니다."]
        shown = _shown_spans(pacing)
        rows += ["", "| 구간 | 조우 | 끝낸 곳 | 부담 | 길이 | 길이당 부담 | 상한 |", "|---|---|---|---|---|---|---|"] if shown else []
        for s in shown:
            length = "–" if s["length"] is None else f"{_fmt(s['length'])}{unit}"
            rows.append("| " + " | ".join((SPAN_KINDS[s["kind"]][0], _span_name(s), s["closed_by"] or "–", _fmt(s["load"]), length, _fmt(s["rate"]),
                                            _fmt(s["limit"]) + _over_mark(s, SPAN_KINDS[s["kind"]][2], result))) + " |")
    if pacing["strong_runs"]:
        rows += ["", f"| 강한 조우 연속(세기 {_fmt(pacing['strong_at'])} 이상) | 횟수 | 상한 |", "|---|---|---|"]
        rows += ["| " + " | ".join((_span_name(s), _fmt(s["length"]), _fmt(s["limit"]) + _over_mark(s, "strong_run", result))) + " |" for s in pacing["strong_runs"]]
    return rows


def table(data: dict, result: dict, ids: list[str] | None = None) -> str:
    """대화에 붙일 조우 표(마크다운). --ids는 컨셉 비교표용이라 여기서는 쓰지 않는다."""
    each, total, pace = KILL_HEADS[result["kill_measure"]]
    rows = [f"| 레벨 | 조우 | 역할 | 횟수 | 구성 | 위협도 | 앞 조우 대비 | {each} | 예산 | 판정 |", "|---|---|---|---|---|---|---|---|---|---|"]
    for lv in result["levels"]:
        for x in lv["encounters"]:
            rows.append("| " + " | ".join((lv["id"], x["id"], x["role"] or "–", _fmt(x["repeat"]), _mix(x), _fmt(x["threat"]), _vs(x), _cost(x),
                                            "–" if x["expected"] is None else f"{_fmt(x['expected'])} ({_fmt(x['low'])}~{_fmt(x['high'])})", _verdict(x))) + " |")
    rows += ["", f"| 단계 | 순서 | 위협도 합 | 앞 단계 대비 | {total} | 길이 | {pace} | 평범한 조우의 적 수 |", "|---|---|---|---|---|---|---|---|"]
    for s in result["stages"]:
        length = "–" if s["duration"] is None else f"{_fmt(s['duration'])}{s['time_unit']}"
        rows.append("| " + " | ".join((s["id"], _fmt(s["position"]), _fmt(s["threat"]), _vs(s), _stage_time(s), length, _ratio(s), _fmt(s["group_size"]))) + " |")
    rows += _pace_table(result) + _greybox_table(result)
    counted = [s for s in result["stages"] if s["kills"]]
    if counted:
        rows += ["", "재화 흐름 kills로 옮길 값(조우로 센 처치 수, 단계는 전투 단계 id, 파일에 쓰지 않음):"]
        rows += [f"- {s['id']}: {json.dumps({k: int(v) if float(v).is_integer() else v for k, v in s['kills'].items()}, ensure_ascii=False)}" for s in counted]
    rows += ["", "위협도는 스탯으로 낸 설계 가정입니다. 실제 난이도나 재미를 판정하지 않습니다."]
    return "\n".join(rows)


def print_counts(result: dict) -> None:
    tail = f"오류 {len(result['errors'])} · 경고 {len(result['warnings'])}"
    if result.get("acknowledged"):
        tail += f" · 확인한 경고 {len(result['acknowledged'])}"
    print(f"레벨 {result['count']}개 · 조우 {result['encounters']}개 · {tail}")
