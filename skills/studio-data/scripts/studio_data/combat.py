"""전투 계산(data/combat.json): 플레이어·아이템·강화·적을 하나의 스탯 모델과 방어 공식으로 잇는다.

단계(구역·레벨·웨이브)마다 기준 장비를 갖춘 플레이어가 각 적을 몇 번·몇 초에 잡는지(처치),
적에게 몇 번·몇 초 맞으면 쓰러지는지(버팀)를 계산하고, 등급별 목표 범위를 벗어나면 경고한다.
기대값 계산이며 회피·이동·광역 공격·상태 이상은 넣지 않는다. 재미나 실제 난이도를 판정하지 않는다.
형식: combat-balance/references/combat-format.md
"""
from __future__ import annotations

import math

from . import common as c
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
METRICS = ("hits_to_kill", "time_to_kill", "hits_to_die", "time_to_die")
METRIC_LABEL = {"hits_to_kill": "처치 타수", "time_to_kill": "처치 시간(초)", "hits_to_die": "버티는 타수", "time_to_die": "버티는 시간(초)"}
UNCHECKED_REASON = {
    "items": "아이템 데이터를 함께 검사하지 않았거나 읽지 못함",
    "upgrades": "영구 강화 데이터를 함께 검사하지 않았거나 읽지 못함",
    "enemies": "적 데이터를 함께 검사하지 않았거나 읽지 못함",
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
            _err(errors, "schema", "combat.defense", f"{formula['form']} 공식에는 수 {', '.join(bad)}가 필요합니다.")
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
def _player(stage: dict, settings: dict, refs: dict, errors: list, warnings: list) -> tuple[dict | None, int]:
    """(합친 플레이어 스탯 또는 None, 미확인 수). 없는 참조나 형식 오류가 있으면 계산하지 않는다."""
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
        if not (isinstance(ids, list) and all(isinstance(x, str) for x in ids)):
            _err(errors, "schema", where, f"player.{kind}는 {label} id 배열이어야 합니다.")
            ok = False
            continue
        if ids and refs[kind] is None:
            unchecked += 1
            ok = False
            continue
        for rid in ids:
            e = refs[kind].get(rid)
            if e is None:
                _err(errors, "unknown_item" if kind == "items" else "unknown_upgrade", where, f"{label} 데이터에 없는 id입니다: {rid}")
                ok = False
            elif not c.is_active(e):
                _err(warnings, "cut_referenced", where, f"삭제(cut)된 {label} {rid}를 기준 장비에 넣었습니다. 계산에서 뺍니다.", owner=where)
            else:
                stats = _stats_of(e)
                if stats is None:
                    unchecked += 1  # 그 항목의 형식 오류는 그 파일에서 보고한다
                    ok = False
                    continue
                for k, v in stats.items():
                    total[k] = total.get(k, 0) + v
    if ok and refs["upgrades"] is not None:
        owned = set(player.get("upgrades", []))
        for uid in player.get("upgrades", []):
            reqs = refs["upgrades"][uid].get("requires") or []
            missing = [r for r in reqs if isinstance(r, str) and r not in owned] if isinstance(reqs, list) else []
            if missing:
                _err(warnings, "requirement_missing", where,
                     f"기준 장비의 강화 {uid}는 {', '.join(missing)}가 먼저 필요합니다. 살 수 없는 조합으로 계산됩니다.", owner=where)
    return (total if ok else None), unchecked


def _side(stats: dict, roles: dict) -> dict:
    get = lambda role, default=None: stats.get(roles[role], default) if role in roles else default  # noqa: E731
    return {"hp": get("hp"), "attack": get("attack"), "defense": get("defense", 0) or 0,
            "attack_rate": get("attack_rate"), "crit_chance": get("crit_chance", 0) or 0,
            "crit_multiplier": get("crit_multiplier", 2.0) if "crit_chance" in roles else 1.0}


def _bad_stats(side: dict, roles: dict) -> list[str]:
    """계산에 쓸 수 없는 값: 체력 0 이하, 공격 속도 0 이하, 치명 확률 0~1 밖, 치명 배율 1 미만."""
    bad = []
    if c.is_number(side["hp"]) and side["hp"] <= 0:
        bad.append(f"{roles['hp']} {side['hp']}(0보다 커야 함)")
    if c.is_number(side["attack_rate"]) and side["attack_rate"] <= 0:
        bad.append(f"{roles['attack_rate']} {side['attack_rate']}(초당 공격 횟수, 0보다 커야 함)")
    if not 0 <= side["crit_chance"] <= 1:
        bad.append(f"{roles['crit_chance']} {side['crit_chance']}(0~1 비율. 퍼센트로 적었다면 100으로 나눔)")
    if side["crit_multiplier"] < 1:
        bad.append(f"{roles['crit_multiplier']} {side['crit_multiplier']}(1 이상)")
    return bad


def _metric(hp: float, hit: float, rate) -> tuple:
    if hit <= 0:
        return None, None
    hits = math.ceil(round(hp / hit, 9))
    return hits, (round(hits / rate, 3) if c.is_number(rate) and rate > 0 else None)


def _stage_enemies(stage: dict, enemies: dict, errors: list, warnings: list) -> list[dict] | None:
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
                _err(warnings, "cut_referenced", where, f"삭제(cut)된 적 {eid}를 이 단계에 넣었습니다. 계산에서 뺍니다.", owner=where)
            else:
                out.append(enemies[eid])
        return out
    zone = stage.get("zone")
    if zone is None:
        return []
    return [e for e in enemies.values() if e.get("zone") == zone and c.is_active(e)]


def validate(data: dict, items: dict | None = None, upgrades: dict | None = None, enemies: dict | None = None) -> dict:
    """items·upgrades·enemies: 함께 읽은 데이터의 {id: 항목}. None이면 그 참조는 미확인으로 센다."""
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
            stages.append(s)
    refs = {"items": items, "upgrades": upgrades, "enemies": enemies}
    rows: list = []
    stage_info: dict = {}
    unchecked = 0
    missing_kinds: set = set()
    skipped_targets: set = set()
    if settings is not None:
        roles, formula, targets = settings["roles"], settings["formula"], settings["targets"]
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
            unchecked += n
            if n:
                missing_kinds |= {k for k in ("items", "upgrades") if refs[k] is None and (s.get("player") or {}).get(k)}
            if enemies is None:
                unchecked += 1
                missing_kinds.add("enemies")
                foes = None
            else:
                foes = _stage_enemies(s, enemies, errors, warnings)
            if stats is None or foes is None or len(errors) > before:
                continue
            me = _side(stats, roles["player"])
            lacking = [roles["player"][r] for r in REQUIRED_ROLES if not c.is_number(me[r])]
            if lacking:
                _err(errors, "missing_stat", where, f"플레이어에 {', '.join(lacking)}가 없습니다(base·아이템·강화 합계 기준).")
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
            for e in foes:
                ewhere = f"{where}.{e['id']}"
                estats = _stats_of(e)
                if estats is None:
                    unchecked += 1
                    continue
                foe = _side(estats, roles["enemy"])
                lacking = [roles["enemy"][r] for r in REQUIRED_ROLES if not c.is_number(foe[r])]
                if lacking:
                    _err(errors, "missing_stat", ewhere, f"적 {e['id']}에 {', '.join(lacking)}가 없습니다.")
                    continue
                bad = _bad_stats(foe, roles["enemy"])
                if bad:
                    _err(errors, "bad_stat", ewhere, f"적 {e['id']}의 스탯을 계산에 쓸 수 없습니다: " + ", ".join(bad))
                    continue
                if formula["form"] in ("ratio", "level_ratio") and foe["defense"] < 0:
                    _err(errors, "negative_defense", ewhere, "비율 공식은 음수 방어를 지원하지 않습니다(v1).")
                    continue
                level = s.get("level")
                my_hit = expected_hit(me["attack"], foe["defense"], formula, level, me["crit_chance"], me["crit_multiplier"])
                their_hit = expected_hit(foe["attack"], me["defense"], formula, level, foe["crit_chance"], foe["crit_multiplier"])
                htk, ttk = _metric(foe["hp"], my_hit, me["attack_rate"])
                htd, ttd = _metric(me["hp"], their_hit, foe["attack_rate"])
                r = {"stage": where, "enemy": e["id"], "rank": e.get("rank"), "player_hit": round(my_hit, 4), "enemy_hit": round(their_hit, 4),
                     "hits_to_kill": htk, "time_to_kill": ttk, "hits_to_die": htd, "time_to_die": ttd, "out_of_range": []}
                if my_hit <= 0:
                    _err(warnings, "zero_damage", ewhere, f"이 단계 기준 장비로 {e['id']}에게 피해를 줄 수 없습니다.", owner=where)
                for m, rng in (targets.get(e.get("rank")) or {}).items():
                    v = r[m]
                    if v is None:
                        # 시간 지표는 공격 속도가 없으면 계산하지 못한다. 목표를 건너뛰었다고 알린다(조용히 통과시키지 않는다).
                        side = "플레이어" if m == "time_to_kill" else "적"
                        hits = r["hits_to_kill"] if m == "time_to_kill" else r["hits_to_die"]
                        key = (e.get("rank"), m)
                        if hits is not None and key not in skipped_targets:
                            skipped_targets.add(key)
                            _err(warnings, "target_unchecked", f"combat.targets.{e.get('rank')}.{m}",
                                 f"{METRIC_LABEL[m]} 목표를 검사하지 못했습니다: {side}에 공격 속도(attack_rate 역할) 값이 없습니다.")
                        continue
                    if c.out_of_range(v, rng):
                        r["out_of_range"].append(m)
                        _err(warnings, "target_out_of_range", ewhere,
                             f"{METRIC_LABEL[m]} {v}가 {RANK_LABEL.get(e.get('rank'), e.get('rank'))} 목표 {c.range_text(rng)}를 벗어납니다.", owner=where)
                rows.append(r)
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
        "errors": errors,
        "warnings": warnings,
    }


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


def marginal_costs(data: dict, items: dict | None = None, upgrades: dict | None = None, enemies: dict | None = None) -> dict | None:
    """단계마다 플레이어·적 스탯 1의 값어치(공격 1 = 1). 전투 설정이 틀렸거나 적 데이터가 없으면 None.
    값어치는 그 단계의 기준 장비와 적에서 잰 것이라 단계마다 다르다. 공식 바깥의 효과(이동 속도 등)는 잴 수 없다."""
    settings = read_settings(data, [])
    stages = data.get("stages")
    if settings is None or not isinstance(stages, list) or enemies is None:
        return None
    roles, formula = settings["roles"], settings["formula"]
    refs = {"items": items, "upgrades": upgrades, "enemies": enemies}
    out = {"player": {}, "enemy": {}, "skipped": {}, "attack_stat": {"player": roles["player"]["attack"], "enemy": roles["enemy"]["attack"]}}
    for st in stages:
        if not (isinstance(st, dict) and isinstance(st.get("id"), str) and c.is_active(st)):
            continue
        level = st.get("level")
        if formula["form"] == "level_ratio" and not c.is_number(level):
            continue
        stats, _ = _player(st, settings, refs, [], [])
        foes = _stage_enemies(st, enemies, [], []) if stats is not None else None
        foe_stats = [x for x in (_stats_of(e) for e in foes or []) if x]
        usable = _measurable(stats, roles["player"], foe_stats, roles["enemy"], formula, level) if foe_stats else []
        if len(usable) < len(foe_stats):
            out["skipped"][st["id"]] = len(foe_stats) - len(usable)
        if not usable:
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
    if result["unchecked"]:
        kinds = ", ".join(UNCHECKED_REASON[k] for k in result.get("unchecked_kinds", []) if k in UNCHECKED_REASON)
        print(f"전투 계산 미확인 {result['unchecked']}건" + (f" ({kinds})" if kinds else "") + ": 프로젝트 폴더로 함께 검사하세요.")


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
    print(f"출처(삭제 제외): 가정 {pc['assumed']} · 계산 {pc['computed']} · 측정 {pc['measured']} · 미지정 {pc['unspecified']}")
    print(f"전투 단계 {result['count']}개 · 계산 {len(result['rows'])}행 · {tail}")
