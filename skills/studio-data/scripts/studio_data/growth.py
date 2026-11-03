"""판 안 성장(data/growth.json): 레벨업 선택지와 빌드 정책으로 단계마다 얻는 스탯을 내고, 전투 계산(combat)에 더해 빌드를 비교한다.

단계마다 기대 레벨(level_at)까지 레벨업할 때, 매번 선택지 중 offers개가 무작위로 제시되고 빌드 정책대로 하나를 고른다.
priority: 목록 앞쪽부터(최대 횟수에 닿은 것은 건너뜀), spread: 목록 중 가장 적게 고른 것. 목록에 없는 것만 제시되면 그중 첫째.
시드를 고정한 반복 시뮬레이션의 평균이며 같은 설정이면 결과가 같다. 재미나 실제 난이도를 판정하지 않는다.
형식: run-growth/references/growth-format.md
"""
from __future__ import annotations

import random

from . import combat as cb
from . import common as c
from .common import add_issue as _err, did_you_mean

PICKS = ("priority", "spread")
DEFAULT_TRIALS = 1000
MAX_TRIALS = 20000  # 검사·뷰어 갱신마다 다시 돌므로 상한을 둔다
DEFAULT_SEED = 7
METRICS = ("hits_to_kill", "time_to_kill", "hits_to_die", "time_to_die")
LOWER_IS_BETTER = {"hits_to_kill": True, "time_to_kill": True, "hits_to_die": False, "time_to_die": False}


def read_settings(data: dict, errors: list) -> dict | None:
    cfg = data.get("growth")
    if not isinstance(cfg, dict):
        _err(errors, "schema", "growth", "growth 객체(level_at, offers)가 필요합니다.")
        return None
    ok = True
    level_at = cfg.get("level_at")
    if not (isinstance(level_at, dict) and level_at and all(isinstance(k, str) and c.is_int(v, 1) for k, v in level_at.items())):
        _err(errors, "schema", "growth.level_at", "level_at은 {전투 단계 id: 1 이상의 정수 레벨}이어야 합니다(레벨 1에서 시작).")
        ok = False
    for key, default, top in (("offers", None, None), ("trials", DEFAULT_TRIALS, MAX_TRIALS)):
        v = cfg.get(key, default)
        if not c.is_int(v, 1) or (top is not None and v > top):
            _err(errors, "schema", f"growth.{key}", f"{key}는 1 이상" + (f" {top} 이하" if top else "") + f"의 정수입니다: {v!r}")
            ok = False
    seed = cfg.get("seed", DEFAULT_SEED)
    if not c.is_int(seed):
        _err(errors, "schema", "growth.seed", f"seed는 정수입니다: {seed!r}")
        ok = False
    if not ok:
        return None
    return {"level_at": level_at, "offers": cfg["offers"], "trials": cfg.get("trials", DEFAULT_TRIALS), "seed": seed}


def check_choices(raw, errors: list) -> list[dict]:
    if not isinstance(raw, list) or not raw:
        _err(errors, "schema", "choices", "choices(레벨업 선택지 배열)가 1개 이상 필요합니다.")
        return []
    out = []
    for _, ch in c.check_identity(raw, "choices", errors):
        ok = c.check_common(ch, ch["id"], errors)
        stats = ch.get("stats")
        if not (isinstance(stats, dict) and stats and all(isinstance(k, str) and c.is_number(v) for k, v in stats.items())):
            _err(errors, "schema", ch["id"], "stats는 {스탯 이름: 수}이고 하나 이상이어야 합니다.")
            ok = False
        if "max_picks" in ch and not c.is_int(ch["max_picks"], 1):
            _err(errors, "schema", ch["id"], f"max_picks는 1 이상의 정수입니다: {ch['max_picks']!r}")
            ok = False
        if ok:
            out.append(ch)
    return out


def check_builds(raw, choice_ids: set, errors: list) -> list[dict]:
    if not isinstance(raw, list) or not raw:
        _err(errors, "schema", "builds", "builds(빌드 정책 배열)가 1개 이상 필요합니다.")
        return []
    out = []
    for _, b in c.check_identity(raw, "builds", errors):
        ok = c.check_common(b, b["id"], errors)
        pri = b.get("priority")
        if not (isinstance(pri, list) and pri and all(isinstance(x, str) for x in pri)):
            _err(errors, "schema", b["id"], "priority는 선택지 id 배열(고르는 순서)이어야 합니다.")
            continue
        for x in pri:
            if x not in choice_ids:
                _err(errors, "unknown_choice", b["id"], f"없는 선택지 '{x}'.{did_you_mean(x, choice_ids)}")
                ok = False
        if b.get("pick", "priority") not in PICKS:
            _err(errors, "schema", b["id"], f"pick은 {', '.join(PICKS)} 중 하나입니다: {b.get('pick')!r}")
            ok = False
        if ok:
            out.append(b)
    return out


# ---------- 시뮬레이션 ----------
def _choose(offered: list[str], build: dict, counts: dict) -> str:
    listed = [x for x in build["priority"] if x in offered]
    if not listed:
        return offered[0]  # 원하는 것이 제시되지 않으면 제시된 것 중 첫째를 고른다
    if build.get("pick") == "spread":
        return min(listed, key=lambda x: (counts.get(x, 0), build["priority"].index(x)))
    return listed[0]


def simulate_trials(choices: list[dict], build: dict, levels: list[int], offers: int, trials: int, seed: int) -> list[list[tuple]]:
    """levels: 단계 순서대로 그 단계까지의 레벨. 시행마다, 단계마다 그때까지의 선택 횟수 ((선택지, 횟수), ...)."""
    rng = random.Random(seed)
    order = [ch["id"] for ch in choices]
    cap = {ch["id"]: ch.get("max_picks") for ch in choices}
    out = []
    for _ in range(trials):
        counts: dict = {}
        done, per_stage = 1, []
        for level in levels:
            for _ in range(max(0, level - done)):
                open_ = [x for x in order if cap[x] is None or counts.get(x, 0) < cap[x]]
                if not open_:
                    break
                offered = sorted(rng.sample(open_, min(offers, len(open_))), key=order.index)
                pick = _choose(offered, build, counts)
                counts[pick] = counts.get(pick, 0) + 1
            done = max(done, level)
            per_stage.append(tuple(sorted(counts.items(), key=lambda kv: order.index(kv[0]))))
        out.append(per_stage)
    return out


def _build_rows(choices: list[dict], build: dict, order: list[str], levels: list[int], settings: dict, prep: dict) -> tuple[dict, list, tuple | None]:
    """빌드 하나의 (단계별 평균 선택·스탯, 시행마다 전투 결과를 평균한 행, 계산할 수 없었던 (시행 수, 이유)).
    전투는 평균 스탯이 아니라 시행마다 계산해 평균한다(올림이 있는 타수는 평균 스탯으로 구하면 기대값과 다르다)."""
    stats_of = {ch["id"]: ch["stats"] for ch in choices}
    trials = simulate_trials(choices, build, levels, settings["offers"], settings["trials"], settings["seed"])
    n = len(trials)
    cache: dict = {}
    stages, rows, bad = {}, [], None
    for i, (sid, level) in enumerate(zip(order, levels)):
        pick_sum: dict = {}
        sums: dict = {}
        for per_stage in trials:
            counts = per_stage[i]
            for k, v in counts:
                pick_sum[k] = pick_sum.get(k, 0) + v
            key = (sid, counts)
            if key not in cache:  # 같은 선택 결과는 다시 계산하지 않는다
                bonus: dict = {}
                for ch, times in counts:
                    for k, v in stats_of[ch].items():
                        bonus[k] = bonus.get(k, 0) + v * times
                cache[key] = cb.evaluate(prep, sid, bonus)
            got, problem = cache[key]
            if got is None:
                bad = (bad[0] + 1 if bad else 1, problem)
                continue
            for r in got:
                acc = sums.setdefault(r["enemy"], {"rank": r["rank"], **{m: 0.0 for m in METRICS}})
                for m in METRICS:
                    acc[m] = None if acc[m] is None or r[m] is None else acc[m] + r[m]
        picks = {k: round(v / n, 4) for k, v in pick_sum.items()}
        bonus = {}
        for ch, times in picks.items():
            for k, v in stats_of[ch].items():
                bonus[k] = round(bonus.get(k, 0) + v * times, 4)
        stages[sid] = {"level": level, "picks": picks, "bonus": bonus}
        for eid, acc in sums.items():
            rows.append({"stage": sid, "enemy": eid, "rank": acc["rank"],
                         **{m: (None if acc[m] is None else round(acc[m] / n, 4)) for m in METRICS}})
    return stages, rows, bad


def _better_or_equal(a: dict, b: dict) -> tuple[bool, bool]:
    """(a가 모든 지표에서 b 이상인가, 하나라도 더 나은가). 값이 없는 지표는 비교하지 않는다."""
    ge, gt = True, False
    for m in METRICS:
        x, y = a.get(m), b.get(m)
        if x is None or y is None:
            continue
        if LOWER_IS_BETTER[m]:
            x, y = -x, -y
        if x < y:
            ge = False
        elif x > y:
            gt = True
    return ge, gt


def validate(data: dict, combat: dict | None = None, items: dict | None = None, upgrades: dict | None = None,
             enemies: dict | None = None) -> dict:
    """combat: 전투 계산 파일 내용, items·upgrades·enemies: 함께 읽은 데이터의 {id: 항목}. 전투 계산이 없으면 미확인."""
    errors: list = []
    warnings: list = []
    settings = read_settings(data, errors)
    choices = check_choices(data.get("choices"), errors)
    builds = check_builds(data.get("builds"), {ch["id"] for ch in choices}, errors)
    active_choices = [ch for ch in choices if c.is_active(ch)]
    active_builds = [b for b in builds if c.is_active(b)]
    report_builds: dict = {}
    base_rows: list = []
    unchecked = 0
    if settings is not None and combat is None:
        unchecked = 1
    elif settings is not None and not (active_choices and active_builds):
        _err(warnings, "nothing_to_compare", "growth",
             "삭제되지 않은 선택지나 빌드가 없어 아무것도 계산하지 않았습니다. 통과가 아닙니다.")
    elif settings is not None:
        raw_stages = [s for s in combat.get("stages", []) if isinstance(s, dict) and isinstance(s.get("id"), str)] \
            if isinstance(combat.get("stages"), list) else []
        stage_ids = [s["id"] for s in raw_stages if c.is_active(s)]
        cut_ids = {s["id"] for s in raw_stages if not c.is_active(s)}
        unknown = [k for k in settings["level_at"] if k not in stage_ids and k not in cut_ids]
        for k in unknown:
            _err(errors, "unknown_stage", "growth.level_at", f"전투 계산(combat.json)에 없는 단계입니다: {k}")
        for k in sorted(set(settings["level_at"]) & cut_ids):
            _err(warnings, "cut_referenced", "growth.level_at", f"삭제(cut)된 전투 단계 {k}의 레벨이 있습니다. 계산에서 뺍니다.")
        order = [sid for sid in stage_ids if sid in settings["level_at"]]
        levels = [settings["level_at"][sid] for sid in order]
        for a, b, la, lb in zip(order, order[1:], levels, levels[1:]):
            if lb < la:
                _err(warnings, "level_decreases", "growth.level_at", f"{b}의 레벨 {lb}가 앞 단계 {a}의 {la}보다 낮습니다. 레벨은 판 안에서 줄지 않습니다.")
        if not unknown:
            base = cb.validate(combat, items=items, upgrades=upgrades, enemies=enemies)
            if base["errors"] or base["unchecked"]:
                unchecked = 1  # 전투 계산 쪽 문제는 전투 계산 검사가 보고한다
            else:
                base_rows = base["rows"]
                known = set(base_settings_roles(combat).values())
                for ch in active_choices:
                    extra = [k for k in ch["stats"] if k not in known]
                    if extra:
                        hint = "".join(did_you_mean(k, known) for k in extra)
                        _err(warnings, "stat_not_in_combat", ch["id"],
                             f"선택지 {ch['id']}의 스탯 {', '.join(extra)}는 전투 계산이 쓰지 않아 효과가 0으로 계산됩니다.{hint} "
                             "전투 밖 효과(이동 속도 등)라면 acknowledged에 이유를 적습니다.", owner=ch["id"])
                prep = cb.prepare(combat, items=items, upgrades=upgrades, enemies=enemies)
                order = [sid for sid in order if sid in prep["stages"]]
                levels = [settings["level_at"][sid] for sid in order]
                for b in active_builds:
                    stages, rows, bad = _build_rows(active_choices, b, order, levels, settings, prep)
                    if bad:
                        _err(errors, "build_invalid", b["id"],
                             f"빌드 {b['id']}의 성장 스탯이 시행 {bad[0]}건에서 전투 계산에 쓸 수 없는 값이 됩니다({bad[1]}). "
                             "선택지 수치나 max_picks를 고치세요. 이 빌드는 비교에서 뺍니다.")
                        continue
                    report_builds[b["id"]] = {"stages": stages, "rows": rows}
                _dominance(report_builds, warnings)
    used = {ch for info in report_builds.values() for st in info["stages"].values() for ch in st["picks"]}
    summary = c.summary_counts(choices + builds)
    cfg = data.get("growth") if isinstance(data.get("growth"), dict) else {}
    prov = cfg.get("provenance")
    if prov is not None:
        c.check_common({"provenance": prov}, "growth", errors)
    if settings is not None and c.provenance_kind({"provenance": prov}) in ("assumed", "unspecified"):
        summary["unverified"] = ["growth(레벨·선택지)"] + summary["unverified"]
    return {
        "kind": "growth",
        "count": len(choices) + len(builds),
        **summary,
        "settings": settings,
        "builds": report_builds,
        "base_rows": [r for r in base_rows if settings and r["stage"] in settings["level_at"]],
        "unused_choices": [ch["id"] for ch in active_choices if report_builds and ch["id"] not in used],
        "unchecked": unchecked,
        "unchecked_kinds": ["combat"] if unchecked else [],
        "errors": errors,
        "warnings": warnings,
    }


def base_settings_roles(combat: dict) -> dict:
    """전투 계산의 플레이어 역할 → 스탯 이름. 형식이 틀렸으면 빈 dict(그 오류는 전투 계산 검사가 보고한다)."""
    roles = ((combat.get("combat") or {}).get("stats") or {}).get("player") if isinstance(combat.get("combat"), dict) else None
    return roles if isinstance(roles, dict) else {}


def _dominance(builds: dict, warnings: list) -> None:
    """한 빌드가 다른 빌드보다 모든 단계·적·지표에서 같거나 낫고 어딘가에서 나으면, 진 빌드에 경고한다.
    행은 (단계, 적)으로 맞춰 비교한다(순서로 짝짓지 않는다)."""
    ids = list(builds)
    keyed = {b: {(r["stage"], r["enemy"]): r for r in builds[b]["rows"]} for b in ids}
    for loser in ids:
        for winner in ids:
            if winner == loser:
                continue
            common_keys = sorted(set(keyed[winner]) & set(keyed[loser]))
            pairs = [(keyed[winner][k], keyed[loser][k]) for k in common_keys]
            results = [_better_or_equal(a, b) for a, b in pairs]
            if results and all(ge for ge, _ in results) and any(gt for _, gt in results):
                _err(warnings, "build_dominated", loser,
                     f"빌드 {winner}가 {loser}보다 모든 단계·적에서 같거나 낫습니다. {loser}를 고를 이유가 없습니다. "
                     "선택지 수치를 바꾸거나 빌드 정의를 확인하세요.", owner=loser)
                break


# ---------- 출력 ----------
def _fmt(v) -> str:
    if v is None:
        return "–"
    return f"{v:g}" if isinstance(v, float) else str(v)


def print_extra(result: dict) -> None:
    s = result.get("settings")
    if s:
        print(f"레벨업마다 선택지 {s['offers']}개 제시 · 시행 {s['trials']} · seed {s['seed']}")
    for bid, info in result["builds"].items():
        for sid, st in info["stages"].items():
            bonus = " · ".join(f"{k} +{_fmt(v)}" for k, v in st["bonus"].items()) or "없음"
            print(f"빌드 {bid} · {sid} (레벨 {st['level']}): {bonus}")
    if result["unused_choices"]:
        print("어느 빌드도 고르지 않은 선택지: " + ", ".join(result["unused_choices"]))
    if result["unchecked"]:
        print("판 안 성장 미확인: 전투 계산(combat.json)이 없거나 그 검사에 오류·미확인이 있음")


def table(data: dict, result: dict, ids: list[str] | None = None) -> str:
    """빌드 비교표(마크다운). --ids는 컨셉 비교표용이라 여기서는 쓰지 않는다."""
    rows = ["| 빌드 | 단계 | 레벨 | 얻은 스탯 | 적 | 처치 타수 | 처치 시간 | 버티는 타수 | 버티는 시간 |", "|---|---|---|---|---|---|---|---|---|"]
    base = {(r["stage"], r["enemy"]): r for r in result["base_rows"]}
    for (sid, eid), r in base.items():
        rows.append("| " + " | ".join(("(성장 없음: 기준 장비만)", sid, "–", "–", eid, _fmt(r["hits_to_kill"]), _fmt(r["time_to_kill"]),
                                        _fmt(r["hits_to_die"]), _fmt(r["time_to_die"]))) + " |")
    for bid, info in result["builds"].items():
        for r in info["rows"]:
            st = info["stages"][r["stage"]]
            bonus = " · ".join(f"{k} +{_fmt(v)}" for k, v in st["bonus"].items()) or "–"
            rows.append("| " + " | ".join((bid, r["stage"], str(st["level"]), bonus, r["enemy"], _fmt(r["hits_to_kill"]), _fmt(r["time_to_kill"]),
                                            _fmt(r["hits_to_die"]), _fmt(r["time_to_die"]))) + " |")
    rows += ["", "선택지 제시는 시드를 고정한 반복 시뮬레이션의 평균입니다. 기대값 계산이며 실제 난이도나 재미를 판정하지 않습니다."]
    return "\n".join(rows)


def print_counts(result: dict) -> None:
    tail = f"오류 {len(result['errors'])} · 경고 {len(result['warnings'])}"
    if result.get("acknowledged"):
        tail += f" · 확인한 경고 {len(result['acknowledged'])}"
    print(f"선택지·빌드 {result['count']}개 · 비교한 빌드 {len(result['builds'])}개 · {tail}")
