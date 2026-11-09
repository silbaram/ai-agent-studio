"""전투 계산(data/combat.json): 플레이어·아이템·강화·적을 하나의 스탯 모델과 방어 공식으로 잇는다.

단계(구역·레벨·웨이브)마다 기준 장비를 갖춘 플레이어가 각 적을 몇 번·몇 초에 잡는지(처치),
적에게 몇 번·몇 초 맞으면 쓰러지는지(버팀)를 계산하고, 등급별 목표 범위를 벗어나면 경고한다.
기대값 계산이며 회피·이동·광역 공격·상태 이상은 넣지 않는다. 재미나 실제 난이도를 판정하지 않는다.
형식: combat-balance/references/combat-format.md
"""
from __future__ import annotations

import math

from . import common as c
from . import crafting as cr
from .common import add_issue as _err, did_you_mean

FORMS = {
    "flat": {"factor": 1.0, "min_damage": 1.0},  # 공격 − 방어 × factor, 최소 min_damage
    "ratio": {"k": None},                          # 공격 × k / (k + 방어)
    "level_ratio": {"a": None, "b": None},         # k = a × 단계 level + b
    "percent": {"cap": None},                      # 공격 × (1 − min(방어, cap) / 100)
}
FORM_LABEL = {"flat": "고정값 감산", "ratio": "비율", "level_ratio": "레벨 비율", "percent": "직접 퍼센트"}
REQUIRED_ROLES = ("hp", "attack")
OPTIONAL_ROLES = ("defense", "attack_rate", "crit_chance", "crit_multiplier")
ROLES = REQUIRED_ROLES + OPTIONAL_ROLES
SIDES = ("player", "enemy")
RANKS = ("normal", "elite", "boss")
RANK_LABEL = {"normal": "일반", "elite": "정예", "boss": "보스"}
ZONE_RULES = ("first_seen", "up_to")  # 단계의 zone: 그 구역에서 처음 나오는 적 / 그 구역까지 나온 적(앞 구역의 적이 계속 나오는 게임)
METRICS = ("hits_to_kill", "time_to_kill", "hits_to_die", "time_to_die")
METRIC_LABEL = {"hits_to_kill": "처치 타수", "time_to_kill": "처치 시간(초)", "hits_to_die": "버티는 타수", "time_to_die": "버티는 시간(초)"}
UNCHECKED_REASON = {
    "items": "아이템 데이터를 함께 검사하지 않았거나 읽지 못함",
    "upgrades": "영구 강화 데이터를 함께 검사하지 않았거나 읽지 못함",
    "enemies": "적 데이터를 함께 검사하지 않았거나 읽지 못함",
    "crafting": "강화·합성 데이터를 함께 검사하지 않았거나 읽지 못함(강화한 기준 장비)",
    "nothing": "계산한 단계·적이 없음(빈 stages, 모두 삭제, 적 없는 단계)",
}


# ---------- 공식 ----------
def hit_damage(attack: float, defense: float, formula: dict, level: float | None = None) -> float:
    """방어를 적용한 한 번의 피해."""
    form = formula["form"]
    if form == "flat":
        return max(formula.get("min_damage", 1.0), attack - defense * formula.get("factor", 1.0))
    if form == "ratio":
        k = formula["k"]
    elif form == "level_ratio":
        k = formula["a"] * level + formula["b"]
    else:  # percent
        return attack * (1 - min(defense, formula["cap"]) / 100)
    return attack * k / (k + defense)


def expected_hit(attack: float, defense: float, formula: dict, level: float | None = None,
                 crit_chance: float = 0.0, crit_multiplier: float = 1.0) -> float:
    """치명을 포함한 한 번의 기대 피해. 치명은 방어 전에 곱한다(고정값 공식에서 순서가 결과를 바꾼다)."""
    p = min(max(crit_chance, 0.0), 1.0)
    normal = hit_damage(attack, defense, formula, level)
    if p == 0:
        return normal
    return (1 - p) * normal + p * hit_damage(attack * crit_multiplier, defense, formula, level)


# ---------- 형식 검사 ----------
def read_settings(data: dict, errors: list) -> dict | None:
    cfg = data.get("combat")
    if not isinstance(cfg, dict):
        _err(errors, "schema", "combat", "combat 객체(stats, defense, targets)가 필요합니다.")
        return None
    ok = True
    roles = cfg.get("stats")
    if not (isinstance(roles, dict) and all(isinstance(roles.get(s), dict) for s in SIDES)):
        _err(errors, "schema", "combat.stats", "stats에 player와 enemy의 {역할: 스탯 이름} 객체가 필요합니다.")
        ok = False
    else:
        for side in SIDES:
            for role, name in roles[side].items():
                if role not in ROLES:
                    _err(errors, "schema", f"combat.stats.{side}", f"알 수 없는 역할 '{role}'.{did_you_mean(role, ROLES)} 역할: {', '.join(ROLES)}")
                    ok = False
                elif not (isinstance(name, str) and name.strip()):
                    _err(errors, "schema", f"combat.stats.{side}", f"역할 '{role}'의 스탯 이름이 비어 있습니다.")
                    ok = False
            missing = [r for r in REQUIRED_ROLES if r not in roles[side]]
            if missing:
                _err(errors, "schema", f"combat.stats.{side}", f"필수 역할 {', '.join(missing)}의 스탯 이름이 없습니다.")
                ok = False
    formula = cfg.get("defense")
    if not (isinstance(formula, dict) and formula.get("form") in FORMS):
        _err(errors, "schema", "combat.defense", f"defense.form은 {', '.join(FORMS)} 중 하나입니다: {formula.get('form') if isinstance(formula, dict) else formula!r}")
        ok = False
    else:
        formula = {**{k: v for k, v in FORMS[formula["form"]].items() if v is not None}, **formula}
        params = [k for k in FORMS[formula["form"]]]
        bad = [k for k in params if not c.is_number(formula.get(k))]
        if bad:
            _err(errors, "schema", "combat.defense", f"{formula['form']} 공식에는 수 {c.josa(', '.join(bad), '이가')} 필요합니다.")
            ok = False
        elif ((formula["form"] == "ratio" and formula["k"] <= 0)
              or (formula["form"] == "percent" and not 0 < formula["cap"] <= 100)
              or (formula["form"] == "flat" and (formula["factor"] < 0 or formula["min_damage"] < 0))):
            _err(errors, "schema", "combat.defense", "공식 값의 범위: ratio k > 0, percent 0 < cap ≤ 100, flat factor ≥ 0·min_damage ≥ 0.")
            ok = False
    targets = cfg.get("targets", {})
    if not isinstance(targets, dict):
        _err(errors, "schema", "combat.targets", "targets는 {등급: {지표: [최소, 최대]}} 객체여야 합니다.")
        ok = False
        targets = {}
    for rank, metrics in targets.items():
        if rank not in RANKS or not isinstance(metrics, dict):
            _err(errors, "schema", "combat.targets", f"targets의 등급은 {', '.join(RANKS)} 중 하나입니다: {rank!r}")
            ok = False
            continue
        for m, rng in metrics.items():
            if m not in METRICS:
                _err(errors, "schema", f"combat.targets.{rank}", f"알 수 없는 지표 '{m}'.{did_you_mean(m, METRICS)}")
                ok = False
            elif not c.valid_range(rng):
                _err(errors, "schema", f"combat.targets.{rank}.{m}", "목표 범위는 [최소, 최대]이고 한쪽은 null로 비울 수 있습니다(최소 ≤ 최대).")
                ok = False
    if not ok:
        return None
    return {"roles": roles, "formula": formula, "targets": targets}


def _stats_of(entry) -> dict | None:
    stats = entry.get("stats", {}) if isinstance(entry, dict) else None
    if stats is None:
        return {}
    if isinstance(stats, dict) and all(isinstance(k, str) and c.is_number(v) for k, v in stats.items()):
        return stats
    return None


# ---------- 계산 ----------
def _item_ref(x) -> bool:
    """기준 장비의 아이템 칸: id, 또는 강화한 아이템 {item, enhance, level}."""
    return isinstance(x, str) or (isinstance(x, dict) and isinstance(x.get("item"), str) and isinstance(x.get("enhance"), str)
                                  and c.is_int(x.get("level"), 0) and set(x) <= {"item", "enhance", "level"})


def _enhance_bonus(x: dict, item: dict, refs: dict, where: str, errors: list, warnings: list) -> tuple[float | None, int]:
    """강화한 아이템의 누적 보너스 비율(bonus_pct 합). (보너스 또는 None, 미확인 수). 강화·합성 데이터에서 그 강화를 찾는다."""
    if refs.get("crafting") is None:
        return None, 1
    tracks = refs["crafting"].get("enhance")
    track = next((t for t in tracks if isinstance(t, dict) and t.get("id") == x["enhance"]), None) if isinstance(tracks, list) else None
    if track is None:
        _err(errors, "unknown_enhance", where, f"강화·합성 데이터에 없는 강화입니다: {x['enhance']}{did_you_mean(x['enhance'], [t.get('id') for t in tracks or [] if isinstance(t, dict)])}")
        return None, 0
    if not cr.check_track(track, []):
        return None, 1  # 강화의 형식 오류는 강화·합성 검사가 보고한다
    if not c.is_active(track):
        _err(warnings, "cut_referenced", where, f"삭제(cut)된 강화 {c.josa(x['enhance'], '을를')} 기준 장비에 썼습니다. 강화 없이 계산합니다.", owner=where)
        return 0.0, 0
    targets = track.get("items")
    fits = x["item"] in targets if targets is not None else all(item.get(k) == v for k, v in track["applies_to"].items())
    if not fits:
        _err(errors, "schema", where, f"아이템 {c.josa(x['item'], '은는')} 강화 {x['enhance']}의 대상이 아닙니다.")
        return None, 0
    if x["level"] > len(track["levels"]):
        _err(errors, "schema", where, f"강화 {c.josa(x['enhance'], '은는')} +{len(track['levels'])}까지입니다: level {x['level']}")
        return None, 0
    return sum(lv.get("bonus_pct", 0.0) for lv in track["levels"][:x["level"]]), 0


def _player(stage: dict, settings: dict, refs: dict, errors: list, warnings: list) -> tuple[dict | None, int]:
    """(합친 플레이어 스탯 또는 None, 미확인 수). 없는 참조나 형식 오류가 있으면 계산하지 않는다.
    아이템 칸이 {item, enhance, level}이면 그 아이템 스탯에 강화 보너스(1 + 누적 bonus_pct)를 곱한다."""
    where = stage["id"]
    player = stage.get("player")
    if not isinstance(player, dict):
        _err(errors, "schema", where, "player 객체(base, items, upgrades)가 필요합니다.")
        return None, 0
    base = _stats_of({"stats": player.get("base", {})})
    if base is None:
        _err(errors, "schema", where, "player.base는 {스탯 이름: 수}여야 합니다.")
        return None, 0
    total = dict(base)
    ok, unchecked = True, 0
    for kind, label in (("items", "아이템"), ("upgrades", "영구 강화")):
        ids = player.get(kind, [])
        if not (isinstance(ids, list) and all((_item_ref if kind == "items" else lambda x: isinstance(x, str))(x) for x in ids)):
            _err(errors, "schema", where, f"player.{c.josa(kind, '은는')} {label} id 배열이어야 합니다"
                 + (". 강화한 아이템은 {\"item\": id, \"enhance\": 강화 id, \"level\": 단계}로 적습니다." if kind == "items" else "."))
            ok = False
            continue
        if ids and refs[kind] is None:
            unchecked += 1
            ok = False
            continue
        for x in ids:
            rid = x if isinstance(x, str) else x["item"]
            e = refs[kind].get(rid)
            if e is None:
                _err(errors, "unknown_item" if kind == "items" else "unknown_upgrade", where, f"{label} 데이터에 없는 id입니다: {rid}")
                ok = False
            elif not c.is_active(e):
                _err(warnings, "cut_referenced", where, f"삭제(cut)된 {label} {c.josa(rid, '을를')} 기준 장비에 넣었습니다. 계산에서 뺍니다.", owner=where)
            else:
                stats = _stats_of(e)
                if stats is None:
                    unchecked += 1  # 그 항목의 형식 오류는 그 파일에서 보고한다
                    ok = False
                    continue
                scale = 1.0
                if isinstance(x, dict):
                    bonus, n = _enhance_bonus(x, e, refs, where, errors, warnings)
                    unchecked += n
                    if bonus is None:
                        ok = False
                        continue
                    scale += bonus
                for k, v in stats.items():
                    total[k] = total.get(k, 0) + v * scale
    if ok and refs["upgrades"] is not None:
        owned = set(player.get("upgrades", []))
        for uid in player.get("upgrades", []):
            reqs = refs["upgrades"][uid].get("requires") or []
            missing = [r for r in reqs if isinstance(r, str) and r not in owned] if isinstance(reqs, list) else []
            if missing:
                _err(warnings, "requirement_missing", where,
                     f"기준 장비의 강화 {c.josa(uid, '은는')} {c.josa(', '.join(missing), '이가')} 먼저 필요합니다. 살 수 없는 조합으로 계산됩니다.", owner=where)
    return (total if ok else None), unchecked


def _side(stats: dict, roles: dict) -> dict:
    get = lambda role, default=None: stats.get(roles[role], default) if role in roles else default  # noqa: E731
    return {"hp": get("hp"), "attack": get("attack"), "defense": get("defense", 0) or 0,
            "attack_rate": get("attack_rate"), "crit_chance": get("crit_chance", 0) or 0,
            "crit_multiplier": get("crit_multiplier", 2.0) if "crit_chance" in roles else 1.0}


def _bad_stats(side: dict, roles: dict) -> list[str]:
    """계산에 쓸 수 없는 값: 체력 0 이하, 공격 속도 0 이하, 치명 확률 0~1 밖, 치명 배율 1 미만."""
    bad = []
    n = c.num_text
    if c.is_number(side["hp"]) and side["hp"] <= 0:
        bad.append(f"{roles['hp']} {n(side['hp'])}(0보다 커야 함)")
    if c.is_number(side["attack_rate"]) and side["attack_rate"] <= 0:
        bad.append(f"{roles['attack_rate']} {n(side['attack_rate'])}(초당 공격 횟수, 0보다 커야 함)")
    if not 0 <= side["crit_chance"] <= 1:
        # 2 이상이면 퍼센트로 적었을 가능성이 크다. 1을 조금 넘는 값은 누적(성장·강화)으로 넘친 것이다
        hint = "0~1 비율. 퍼센트로 적었다면 100으로 나눔" if side["crit_chance"] >= 2 else "0~1 비율. 1을 넘음"
        bad.append(f"{roles['crit_chance']} {n(side['crit_chance'])}({hint})")
    if side["crit_multiplier"] < 1:
        bad.append(f"{roles['crit_multiplier']} {n(side['crit_multiplier'])}(1 이상)")
    return bad


def _metric(hp: float, hit: float, rate) -> tuple:
    if hit <= 0:
        return None, None
    hits = math.ceil(round(hp / hit, 9))
    return hits, (round(hits / rate, 3) if c.is_number(rate) and rate > 0 else None)


def _row_metrics(me: dict, foe: dict, formula: dict, level) -> dict:
    """한 단계·한 적의 처치·버팀. 검사(validate)와 반복 계산(evaluate)이 같은 식을 쓴다."""
    my_hit = expected_hit(me["attack"], foe["defense"], formula, level, me["crit_chance"], me["crit_multiplier"])
    their_hit = expected_hit(foe["attack"], me["defense"], formula, level, foe["crit_chance"], foe["crit_multiplier"])
    htk, ttk = _metric(foe["hp"], my_hit, me["attack_rate"])
    htd, ttd = _metric(me["hp"], their_hit, foe["attack_rate"])
    return {"player_hit": round(my_hit, 4), "enemy_hit": round(their_hit, 4),
            "hits_to_kill": htk, "time_to_kill": ttk, "hits_to_die": htd, "time_to_die": ttd}


def _side_problem(side: dict, roles: dict, formula: dict) -> str | None:
    """계산에 쓸 수 없는 스탯이면 그 이유."""
    lacking = [roles[r] for r in REQUIRED_ROLES if not c.is_number(side[r])]
    if lacking:
        return f"{', '.join(lacking)} 없음"
    bad = _bad_stats(side, roles)
    if bad:
        return ", ".join(bad)
    if formula["form"] in ("ratio", "level_ratio") and side["defense"] < 0:
        return "비율 공식에서 음수 방어"
    return None


def prepare(data: dict, items: dict | None = None, upgrades: dict | None = None, enemies: dict | None = None,
            crafting: dict | None = None) -> dict | None:
    """추가 스탯만 바꿔 같은 전투 계산을 여러 번(판 안 성장 시뮬레이션 등) 빠르게 하기 위한 준비. 설정이 틀렸거나 적이 없으면 None.
    단계마다 기준 장비 합계와 적 스탯을 한 번만 모은다. 참조가 틀려 계산할 수 없는 단계는 빠진다(그 오류는 validate가 보고한다)."""
    settings = read_settings(data, [])
    raw = data.get("stages")
    if settings is None or not isinstance(raw, list) or enemies is None:
        return None
    roles, formula = settings["roles"], settings["formula"]
    refs = {"items": items, "upgrades": upgrades, "enemies": enemies, "crafting": crafting}
    stages = {}
    for s in raw:
        if not (isinstance(s, dict) and isinstance(s.get("id"), str) and c.is_active(s)):
            continue
        if formula["form"] == "level_ratio" and not c.is_number(s.get("level")):
            continue
        stats, n = _player(s, settings, refs, [], [])
        foes = stage_enemies(s, enemies, [], []) if stats is not None and not n else None
        sides = []
        for e in foes or []:
            st = _stats_of(e)
            foe = _side(st, roles["enemy"]) if st is not None else None
            if foe is not None and _side_problem(foe, roles["enemy"], formula) is None:
                sides.append((e["id"], e.get("rank"), foe))
        if sides:
            stages[s["id"]] = {"player": stats, "foes": sides, "level": s.get("level")}
    return {"settings": settings, "stages": stages}


def evaluate(prep: dict, stage_id: str, bonus: dict) -> tuple[list[dict] | None, str | None]:
    """준비한 단계의 기준 장비에 bonus를 더해 적마다 처치·버팀을 낸다. 스탯이 계산에 쓸 수 없으면 (None, 이유)."""
    roles, formula = prep["settings"]["roles"], prep["settings"]["formula"]
    st = prep["stages"][stage_id]
    stats = dict(st["player"])
    for k, v in bonus.items():
        stats[k] = stats.get(k, 0) + v
    me = _side(stats, roles["player"])
    problem = _side_problem(me, roles["player"], formula)
    if problem:
        return None, problem
    return [{"enemy": eid, "rank": rank, **_row_metrics(me, foe, formula, st["level"])} for eid, rank, foe in st["foes"]], None


def stage_enemies(stage: dict, enemies: dict, errors: list, warnings: list) -> list[dict] | None:
    """단계에서 계산할 적 항목: enemies 목록(없는 id는 오류, 삭제된 적은 경고하고 뺌) 또는 zone의 활성 적. 목록 형식이 틀리면 None.
    적 데이터의 zone은 처음 나오는 구역이다. zone_rule이 up_to면 그 구역까지 나온 적(zone 이하)을 모두 쓴다.
    재화 흐름의 combat_stage 연결도 이 규칙을 쓴다."""
    where = stage["id"]
    if "enemies" in stage:
        ids = stage["enemies"]
        if not (isinstance(ids, list) and all(isinstance(x, str) for x in ids)):
            _err(errors, "schema", where, "enemies는 적 id 배열이어야 합니다.")
            return None
        out = []
        for eid in ids:
            if eid not in enemies:
                _err(errors, "unknown_enemy", where, f"적 데이터에 없는 id입니다: {eid}")
            elif not c.is_active(enemies[eid]):
                _err(warnings, "cut_referenced", where, f"삭제(cut)된 적 {c.josa(eid, '을를')} 이 단계에 넣었습니다. 계산에서 뺍니다.", owner=where)
            else:
                out.append(enemies[eid])
        return out
    zone = stage.get("zone")
    if zone is None:
        return []
    if stage.get("zone_rule") == "up_to":
        return [e for e in enemies.values() if c.is_number(e.get("zone")) and c.is_number(zone) and e["zone"] <= zone and c.is_active(e)]
    return [e for e in enemies.values() if e.get("zone") == zone and c.is_active(e)]


def stage_foes(stage: dict, enemies: dict | None) -> set | None:
    """전투 계산이 그 단계에서 계산하는 적 id(전투 계산과 같은 규칙: 목록 또는 구역, 삭제·없는 적 제외). 알 수 없으면 None.
    적 데이터가 없으면 목록에 적힌 id만 쓴다(구역은 알 수 없다)."""
    if enemies is None:
        ids = stage.get("enemies")
        return {x for x in ids if isinstance(x, str)} if isinstance(ids, list) else None
    found = stage_enemies(stage, enemies, [], [])  # 목록 형식 오류·없는 적은 전투 계산 검사가 보고한다
    return None if found is None else {e["id"] for e in found}


CONDITIONAL_HINT = " 플레이어 행동으로만 나오는 조건부 적이면 단계에 넣지 않고 acknowledged에 이유를 적습니다."


def stage_hint(sid: str, free: list, order: list, free_label: str, near_note: str) -> str:
    """없는 전투 단계의 안내. 아직 이어지지 않은 단계(free)를 먼저 오타로 본다. 이미 이어진 단계는 이름만 비슷한 새 단계일 수 있어 오타로 단정하지 않는다."""
    text = did_you_mean(sid, free)
    near = None if text else c.closest(sid, [k for k in order if k not in free])
    if free:
        text += f" {free_label}: {', '.join(free)}."
    if near:
        text += f" 이름이 비슷한 단계: {near}({near_note})."
    return text


def earlier_zone_hint(outside: list, stage: dict, enemies: dict | None) -> str:
    """단계 밖의 적 중 앞 구역에서 처음 나온 적이 있으면 안내. 없으면 빈 문자열.
    up_to는 앞 구역의 적을 모두 넣는다. 일부만 이어지는 게임이면 끝난 적까지 들어오므로 단계의 enemies 목록을 쓴다."""
    zone = stage.get("zone")
    earlier = [k for k in outside if c.is_number(zone) and c.is_number((enemies or {}).get(k, {}).get("zone")) and enemies[k]["zone"] < zone]
    if not earlier or stage.get("zone_rule") == "up_to":
        return ""
    names = ", ".join(earlier)
    if isinstance(stage.get("enemies"), list):
        return f" 앞 구역에서 처음 나온 적: {names}. 평소에도 이 단계에 나오면 전투 단계 {stage['id']}의 enemies 목록에 넣습니다."
    return (f" 앞 구역에서 처음 나온 적: {names}. 앞 구역의 적이 모두 계속 나오면 전투 단계 {stage['id']}에 zone_rule: \"up_to\"를, "
            "일부만 이어지면 enemies 목록을 적습니다.")


def outside_hint(outside: list, stage: dict, enemies: dict | None) -> str:
    """단계 밖의 적을 놓았을 때의 처방. 평소에도 나오는 적과 조건부로 나오는 적을 함께 말한다."""
    usual = earlier_zone_hint(outside, stage, enemies) or f" 평소에도 이 단계에 나오면 전투 단계 {stage['id']}의 enemies 목록에 넣습니다."
    return usual + CONDITIONAL_HINT


def _role_names(settings: dict, stages: list[dict], refs: dict, warnings: list) -> dict:
    """역할이 가리키는 스탯 이름이 그 쪽 데이터 어디에도 없는 역할. 어느 역할도 쓰지 않는 비슷한 이름이 있으면 오타로 보고 경고한다.
    비슷한 이름도 없으면 '값이 없는 역할'로만 돌려준다(아직 그 스탯을 주는 데이터가 없는 게임). 데이터를 함께 읽지 않은 쪽은 보지 않는다."""
    names: dict = {}
    if refs["items"] is not None and refs["upgrades"] is not None:
        found = set()
        for s in stages:
            base = (s.get("player") or {}).get("base") if isinstance(s.get("player"), dict) else None
            found |= set(base) if isinstance(base, dict) else set()
        for kind in ("items", "upgrades"):
            for e in refs[kind].values():
                if isinstance(e, dict) and c.is_active(e) and isinstance(e.get("stats"), dict):
                    found |= set(e["stats"])
        names["player"] = found
    if refs["enemies"] is not None:
        names["enemy"] = {k for e in refs["enemies"].values() if isinstance(e, dict) and c.is_active(e) and isinstance(e.get("stats"), dict)
                          for k in e["stats"]}
    empty = {}
    for side, found in names.items():
        mapped = set(settings["roles"][side].values())
        for role, name in settings["roles"][side].items():
            if name in found:
                continue
            hint = did_you_mean(name, found - mapped)  # 다른 역할이 이미 쓰는 이름은 오타 후보가 아니다(attack_speed ≠ attack)
            if hint:
                label = "플레이어(base·아이템·영구 강화)" if side == "player" else "적"
                _err(warnings, "stat_not_found", f"combat.stats.{side}.{role}",
                     f"역할 {role}의 스탯 이름 '{name}'이 {label} 데이터 어디에도 없습니다.{hint} 이대로면 이 역할은 값이 없는 것으로 계산됩니다.")
            else:
                empty.setdefault(side, []).append(role)
    return empty


def validate(data: dict, items: dict | None = None, upgrades: dict | None = None, enemies: dict | None = None,
             bonus: dict | None = None, crafting: dict | None = None) -> dict:
    """items·upgrades·enemies: 함께 읽은 데이터의 {id: 항목}. None이면 그 참조는 미확인으로 센다.
    bonus: {단계 id: {스탯: 값}}. 판 안 성장(run-growth)처럼 기준 장비 위에 더할 스탯.
    crafting: 강화·합성 파일 내용. 기준 장비에 강화한 아이템이 있을 때 쓴다."""
    errors: list = []
    warnings: list = []
    settings = read_settings(data, errors)
    raw = data.get("stages")
    if not isinstance(raw, list):
        _err(errors, "schema", "stages", "stages 배열이 필요합니다.")
        raw = []
    stages = []
    for _, s in c.check_identity(raw, "stages", errors):
        if c.check_common(s, s["id"], errors):
            if "level" in s and not c.is_number(s["level"]):
                _err(errors, "schema", s["id"], f"level은 수여야 합니다: {s['level']!r}")
                continue
            if s.get("zone_rule", "first_seen") not in ZONE_RULES:
                _err(errors, "schema", s["id"], f"zone_rule은 {', '.join(ZONE_RULES)} 중 하나입니다: {s.get('zone_rule')!r}"
                     f"{did_you_mean(str(s.get('zone_rule')), ZONE_RULES)}")
                continue
            if s.get("zone_rule") == "up_to" and not c.is_number(s.get("zone")):
                _err(errors, "schema", s["id"], f"zone_rule up_to는 zone이 수여야 합니다(그 구역 이하의 적을 고른다): {s.get('zone')!r}")
                continue
            stages.append(s)
    refs = {"items": items, "upgrades": upgrades, "enemies": enemies, "crafting": crafting}
    rows: list = []
    stage_info: dict = {}
    unchecked = 0
    missing_kinds: set = set()
    skipped_targets: set = set()
    empty_roles: dict = {}
    unmapped = {"player": set(), "enemy": set()}
    if settings is not None:
        roles, formula, targets = settings["roles"], settings["formula"], settings["targets"]
        empty_roles = _role_names(settings, [x for x in stages if c.is_active(x)], refs, warnings)
        for s in (x for x in stages if c.is_active(x)):
            where = s["id"]
            if formula["form"] == "level_ratio":
                if not c.is_number(s.get("level")):
                    _err(errors, "schema", where, "level_ratio 공식은 단계마다 level(수)이 필요합니다.")
                    continue
                if formula["a"] * s["level"] + formula["b"] <= 0:
                    _err(errors, "schema", where, f"level {s['level']}에서 k = a × level + b가 0 이하입니다.")
                    continue
            before = len(errors)
            stats, n = _player(s, settings, refs, errors, warnings)
            if stats is not None and bonus and bonus.get(where):
                stats = dict(stats)
                for k, v in bonus[where].items():
                    stats[k] = stats.get(k, 0) + v
            unchecked += n
            if n:
                loadout = s.get("player") or {}
                missing_kinds |= {k for k in ("items", "upgrades") if refs[k] is None and loadout.get(k)}
                if crafting is None and any(isinstance(x, dict) for x in loadout.get("items") or []):
                    missing_kinds.add("crafting")
            if enemies is None:
                unchecked += 1
                missing_kinds.add("enemies")
                foes = None
            else:
                foes = stage_enemies(s, enemies, errors, warnings)
            if stats is None or foes is None or len(errors) > before:
                continue
            me = _side(stats, roles["player"])
            lacking = [roles["player"][r] for r in REQUIRED_ROLES if not c.is_number(me[r])]
            if lacking:
                _err(errors, "missing_stat", where, f"플레이어에 {c.josa(', '.join(lacking), '이가')} 없습니다(base·아이템·강화 합계 기준).")
                continue
            bad = _bad_stats(me, roles["player"])
            if bad:
                _err(errors, "bad_stat", where, "플레이어 스탯을 계산에 쓸 수 없습니다: " + ", ".join(bad))
                continue
            if formula["form"] in ("ratio", "level_ratio") and me["defense"] < 0:
                _err(errors, "negative_defense", where, "비율 공식은 음수 방어를 지원하지 않습니다(v1).")
                continue
            if not foes:
                _err(warnings, "stage_without_enemies", where, "이 단계에 계산할 적이 없습니다. enemies 목록이나 zone을 적으세요.", owner=where)
            stage_info[where] = {"player": {k: v for k, v in stats.items()}, "level": s.get("level")}
            unmapped["player"] |= set(stats) - set(roles["player"].values())
            for e in foes:
                ewhere = f"{where}.{e['id']}"
                estats = _stats_of(e)
                if estats is None:
                    unchecked += 1
                    continue
                foe = _side(estats, roles["enemy"])
                unmapped["enemy"] |= set(estats) - set(roles["enemy"].values())
                lacking = [roles["enemy"][r] for r in REQUIRED_ROLES if not c.is_number(foe[r])]
                if lacking:
                    _err(errors, "missing_stat", ewhere, f"적 {e['id']}에 {c.josa(', '.join(lacking), '이가')} 없습니다.")
                    continue
                bad = _bad_stats(foe, roles["enemy"])
                if bad:
                    _err(errors, "bad_stat", ewhere, f"적 {e['id']}의 스탯을 계산에 쓸 수 없습니다: " + ", ".join(bad))
                    continue
                if formula["form"] in ("ratio", "level_ratio") and foe["defense"] < 0:
                    _err(errors, "negative_defense", ewhere, "비율 공식은 음수 방어를 지원하지 않습니다(v1).")
                    continue
                r = {"stage": where, "enemy": e["id"], "rank": e.get("rank"), **_row_metrics(me, foe, formula, s.get("level")), "out_of_range": []}
                row_issue = {"owner": where, "part": e["id"]}  # 단계의 확인이 적 하나만 덮을 수 있게 대상을 남긴다
                if r["player_hit"] <= 0:
                    _err(warnings, "zero_damage", ewhere, f"이 단계 기준 장비로 {e['id']}에게 피해를 줄 수 없습니다(처치 타수·시간 없음).", **row_issue)
                if r["enemy_hit"] <= 0:
                    _err(warnings, "zero_damage", ewhere,
                         f"{c.josa(e['id'], '이가')} 이 단계 기준 장비에 피해를 줄 수 없습니다(버티는 타수·시간 없음).", **row_issue)
                for m, rng in (targets.get(e.get("rank")) or {}).items():
                    v = r[m]
                    if v is None:
                        hits = r["hits_to_kill"] if m in ("hits_to_kill", "time_to_kill") else r["hits_to_die"]
                        if hits is None:
                            continue  # 피해 0이라 타수가 없다. zero_damage로 알렸다
                        # 여기는 시간 지표이고 공격 속도가 없다. 목표를 건너뛰었다고 알린다(조용히 통과시키지 않는다).
                        side = "플레이어" if m == "time_to_kill" else "적"
                        key = (e.get("rank"), m)
                        if key not in skipped_targets:
                            skipped_targets.add(key)
                            _err(warnings, "target_unchecked", f"combat.targets.{e.get('rank')}.{m}",
                                 f"{METRIC_LABEL[m]} 목표를 검사하지 못했습니다: {side}에 공격 속도(attack_rate 역할) 값이 없습니다.")
                        continue
                    if c.out_of_range(v, rng):
                        r["out_of_range"].append(m)
                        _err(warnings, "target_out_of_range", ewhere,
                             f"{METRIC_LABEL[m]} {c.josa(c.num_text(v), '이가')} {RANK_LABEL.get(e.get('rank'), e.get('rank'))} 목표 {c.josa(c.range_text(rng), '을를')} 벗어납니다.",
                             **row_issue)
                rows.append(r)
    if settings is not None and upgrades is not None:
        _check_upgrade_stats(settings, stages, stage_info, upgrades, errors)
    if settings is not None and not rows and not errors and not unchecked:
        unchecked, missing_kinds = 1, {"nothing"}  # 계산한 것이 없으면 통과가 아니다
    summary = c.summary_counts(stages)
    prov = (data.get("combat") or {}).get("provenance") if isinstance(data.get("combat"), dict) else None
    if prov is not None:
        c.check_common({"provenance": prov}, "combat", errors)
    if settings is not None and c.provenance_kind({"provenance": prov}) in ("assumed", "unspecified"):
        summary["unverified"] = ["combat(공식·목표)"] + summary["unverified"]
    return {
        "kind": "combat",
        "count": len(stages),
        **summary,
        "formula": settings["formula"] if settings else None,
        "stages": stage_info,
        "rows": rows,
        "unchecked": unchecked,
        "unchecked_kinds": sorted(missing_kinds),
        "empty_roles": empty_roles,
        "unmapped_stats": {k: sorted(v) for k, v in unmapped.items() if v},
        "errors": errors,
        "warnings": warnings,
    }


def _check_upgrade_stats(settings: dict, stages: list, stage_info: dict, upgrades: dict, errors: list) -> None:
    """기준 장비에 넣지 않은 영구 강화도 사면 더해진다(메타 성장 시뮬레이터). 활성 강화마다 계산한 단계의 기준 장비에 하나씩 더해
    스탯이 계산에 쓸 수 없는 값이 되면(치명 확률이 1을 넘는 등) 그 강화의 오류로 알린다. 강화 하나에 한 번만."""
    roles, formula = settings["roles"]["player"], settings["formula"]
    loadout = {s["id"]: set((s.get("player") or {}).get("upgrades") or []) for s in stages if isinstance(s.get("player"), dict)}
    for uid, u in upgrades.items():
        stats = _stats_of(u)
        if not (isinstance(u, dict) and c.is_active(u) and stats and set(stats) & set(roles.values())):
            continue
        for sid, info in stage_info.items():
            if uid in loadout.get(sid, ()):
                continue  # 그 단계의 기준 장비에 이미 있다
            total = dict(info["player"])
            for k, v in stats.items():
                total[k] = total.get(k, 0) + v
            problem = _side_problem(_side(total, roles), roles, formula)
            if problem:
                _err(errors, "bad_stat", f"upgrades:{uid}",
                     f"영구 강화 {c.josa(uid, '을를')} 단계 {sid}의 기준 장비에 더하면 플레이어 스탯을 계산에 쓸 수 없습니다: {problem}. 강화 수치를 고치세요.")
                break


# ---------- 스탯 원가 제안 (B2 예산에 쓴다) ----------
def _power(me_stats: dict, me_roles: dict, foes: list[dict], foe_roles: dict, formula: dict, level) -> float | None:
    """ln(초당 주는 피해) + ln(버티는 실질 체력)의 상대 평균. 주어진 적 중 계산할 수 없는 조합이 있으면 None."""
    total = 0.0
    me = _side(me_stats, me_roles)
    for foe_stats in foes:
        foe = _side(foe_stats, foe_roles)
        if not all(c.is_number(x) and x > 0 for x in (me["hp"], me["attack"], foe["attack"])):
            return None
        if formula["form"] in ("ratio", "level_ratio") and (me["defense"] < 0 or foe["defense"] < 0):
            return None
        rate = me["attack_rate"] if c.is_number(me["attack_rate"]) and me["attack_rate"] > 0 else 1.0
        dealt = expected_hit(me["attack"], foe["defense"], formula, level, me["crit_chance"], me["crit_multiplier"]) * rate
        taken = expected_hit(foe["attack"], me["defense"], formula, level, foe["crit_chance"], foe["crit_multiplier"])
        if dealt <= 0 or taken <= 0:
            return None
        total += math.log(dealt) + math.log(me["hp"] / taken)
    return total / len(foes) if foes else None


def _measurable(me_stats: dict, me_roles: dict, foes: list[dict], foe_roles: dict, formula: dict, level) -> list[dict]:
    """서로 피해를 주고받을 수 있는 적만. 피해 0인 적 하나 때문에 단계 전체를 버리지 않는다."""
    return [f for f in foes if _power(me_stats, me_roles, [f], foe_roles, formula, level) is not None]


def _gradient(me_stats: dict, me_roles: dict, foes: list[dict], foe_roles: dict, formula: dict, level) -> dict:
    """역할 스탯 1의 값어치를 공격 1 기준으로 환산한 {스탯 이름: 값}. 앞으로 차분(작은 증가)으로 잰다.
    잴 적은 호출하는 쪽이 _measurable로 고른다. 조금 올렸을 때 계산이 안 되는 역할은 빼고 잰다."""
    base = _power(me_stats, me_roles, foes, foe_roles, formula, level)
    if base is None:
        return {}
    current = _side(me_stats, me_roles)
    grads = {}
    for role, name in me_roles.items():
        if role == "attack_rate" and not c.is_number(current["attack_rate"]):
            continue  # 공격 속도를 모델에 넣지 않은 게임
        if role in ("crit_chance", "crit_multiplier") and "crit_chance" not in me_roles:
            continue
        step = 1e-4 * max(1.0, abs(current[role]))
        bumped = dict(me_stats, **{name: current[role] + step})
        after = _power(bumped, me_roles, foes, foe_roles, formula, level)
        if after is not None:
            grads[name] = (after - base) / step
    attack = grads.get(me_roles["attack"])
    if not attack or attack <= 0:
        return {}
    return {name: round(g / attack, 4) for name, g in grads.items()}


def marginal_costs(data: dict, items: dict | None = None, upgrades: dict | None = None, enemies: dict | None = None,
                   crafting: dict | None = None) -> dict:
    """단계마다 플레이어·적 스탯 1의 값어치(공격 1 = 1). 재지 못한 단계와 이유는 unavailable({단계 id 또는 combat: 이유})에 남긴다.
    값어치는 그 단계의 기준 장비와 적에서 잰 것이라 단계마다 다르다. 공식 바깥의 효과(이동 속도 등)는 잴 수 없다."""
    out: dict = {"player": {}, "enemy": {}, "skipped": {}, "unavailable": {}, "attack_stat": {}}
    settings = read_settings(data, [])
    stages = data.get("stages")
    if settings is None or not isinstance(stages, list) or enemies is None:
        out["unavailable"]["combat"] = ("전투 계산 설정(combat의 stats·defense·targets)에 오류가 있음" if settings is None
                                        else "stages 배열이 없음" if not isinstance(stages, list) else "적 데이터를 함께 읽지 못함")
        return out
    roles, formula = settings["roles"], settings["formula"]
    refs = {"items": items, "upgrades": upgrades, "enemies": enemies, "crafting": crafting}
    out["attack_stat"] = {"player": roles["player"]["attack"], "enemy": roles["enemy"]["attack"]}
    for st in stages:
        if not (isinstance(st, dict) and isinstance(st.get("id"), str) and c.is_active(st)):
            continue
        level = st.get("level")
        if formula["form"] == "level_ratio" and not c.is_number(level):
            out["unavailable"][st["id"]] = "level_ratio 공식인데 level이 없음"
            continue
        stats, _ = _player(st, settings, refs, [], [])
        if stats is None:
            out["unavailable"][st["id"]] = "기준 장비를 계산하지 못함(없는 id, 형식 오류, 함께 읽지 않은 데이터)"
            continue
        foes = stage_enemies(st, enemies, [], [])
        foe_stats = [x for x in (_stats_of(e) for e in foes or []) if x]
        usable = _measurable(stats, roles["player"], foe_stats, roles["enemy"], formula, level) if foe_stats else []
        if len(usable) < len(foe_stats):
            out["skipped"][st["id"]] = len(foe_stats) - len(usable)
        if not usable:
            out["unavailable"][st["id"]] = "적 목록 형식 오류" if foes is None else "서로 피해를 주고받을 수 있는 적이 없음"
            continue
        foe_stats = usable
        mine = _gradient(stats, roles["player"], foe_stats, roles["enemy"], formula, level)
        if mine:
            out["player"][st["id"]] = mine
        per_foe = [g for g in (_gradient(fs, roles["enemy"], [stats], roles["player"], formula, level) for fs in foe_stats) if g]
        if per_foe:
            names = set.intersection(*(set(g) for g in per_foe))
            out["enemy"][st["id"]] = {n: round(sum(g[n] for g in per_foe) / len(per_foe), 4) for n in sorted(names)}
    return out


# ---------- 출력 ----------
def _fmt(v) -> str:
    if v is None:
        return "–"
    return f"{v:g}" if isinstance(v, float) else str(v)


def print_extra(result: dict) -> None:
    f = result.get("formula")
    if f:
        params = ", ".join(f"{k} {f[k]:g}" for k in FORMS[f["form"]])
        print(f"방어 공식: {FORM_LABEL[f['form']]} ({params})")
    for sid, info in result["stages"].items():
        print(f"단계 {sid}: " + " · ".join(f"{k} {_fmt(v)}" for k, v in info["player"].items()))
        for r in (x for x in result["rows"] if x["stage"] == sid):
            mark = " ⚠" if r["out_of_range"] else ""
            print(f"  {r['enemy']} ({RANK_LABEL.get(r['rank'], r['rank'])}): 처치 {_fmt(r['hits_to_kill'])}타 {_fmt(r['time_to_kill'])}초"
                  f" · 버팀 {_fmt(r['hits_to_die'])}타 {_fmt(r['time_to_die'])}초{mark}")
    empty = result.get("empty_roles") or {}
    if empty:
        print("값이 있는 데이터가 없는 역할(없는 것으로 계산): "
              + " · ".join(f"{'플레이어' if side == 'player' else '적'} {', '.join(roles)}" for side, roles in empty.items()))
    unmapped = result.get("unmapped_stats") or {}
    if unmapped:
        print("역할에 연결하지 않아 전투 계산에 쓰지 않는 스탯: "
              + " · ".join(f"{'플레이어' if side == 'player' else '적'} {', '.join(names)}" for side, names in unmapped.items()))
    if result["unchecked"]:
        kinds = result.get("unchecked_kinds", [])
        text = ", ".join(UNCHECKED_REASON[k] for k in kinds if k in UNCHECKED_REASON)
        tail = "" if kinds == ["nothing"] else ": 프로젝트 폴더로 함께 검사하세요."
        print(f"전투 계산 미확인 {result['unchecked']}건" + (f" ({text})" if text else "") + tail)


def table(data: dict, result: dict, ids: list[str] | None = None) -> str:
    """대화에 붙일 계산표(마크다운). --ids는 컨셉 비교표용이라 여기서는 쓰지 않는다."""
    rows = ["| 단계 | 적 | 등급 | 주는 피해/타 | 처치 타수 | 처치 시간(초) | 받는 피해/타 | 버티는 타수 | 버티는 시간(초) | 목표 이탈 |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    for r in result["rows"]:
        rows.append("| " + " | ".join(_fmt(x) for x in (
            r["stage"], r["enemy"], RANK_LABEL.get(r["rank"], r["rank"]), r["player_hit"], r["hits_to_kill"], r["time_to_kill"],
            r["enemy_hit"], r["hits_to_die"], r["time_to_die"])) + " | " + (", ".join(METRIC_LABEL[m] for m in r["out_of_range"]) or "–") + " |")
    rows.append("")
    rows.append("기대값 계산입니다. 회피·이동·광역·상태 이상은 넣지 않았고, 실제 난이도나 재미를 판정하지 않습니다.")
    return "\n".join(rows)


def print_counts(result: dict) -> None:
    sc, pc = result["status_counts"], result["provenance_counts"]
    tail = f"오류 {len(result['errors'])} · 경고 {len(result['warnings'])}"
    if result.get("acknowledged"):
        tail += f" · 확인한 경고 {len(result['acknowledged'])}"
    print(f"상태: 제안 {sc['proposed']} · 승인 {sc['approved']} · 삭제 {sc['cut']} · 미지정 {sc['unspecified']}")
    print(f"출처(삭제 제외): {c.provenance_text(pc)}")
    print(f"전투 단계 {result['count']}개 · 계산 {len(result['rows'])}행 · {tail}")
