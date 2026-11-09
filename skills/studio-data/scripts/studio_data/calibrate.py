"""플레이 기록(data/playtests.json의 stage_stats)으로 가정값을 보정한다.

기획에서 가정한 값(단계별 레벨, 길이, 처치 수, 수입)을 실측과 나란히 놓고, 시뮬레이터 설정(전투 계산 모델)을 주면
단계 통과율의 예측과 실측을 비교해 생존 곡선(slope, even_margin) 값을 제안한다. 파일을 고치지 않는다.
제안은 표본에 맞춘 계산값이며, 재미나 실제 난이도를 판정하지 않는다. 형식: playtest-verdict/references/calibration.md
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from statistics import NormalDist

from . import combat as cb
from . import common as c
from . import datasets
from . import growth as gr
from . import meta_sim as mm
from .meta_sim import ConfigError

EVIDENCE = ("computed: assumed values compared with recorded stage statistics; survival suggestions are a maximum-likelihood fit "
            "to those records. Valid for the recorded builds and players only. Not a difficulty or fun verdict.")
DEFAULT_TOLERANCE = 0.2
Z95 = 1.96
SKILL_POINTS = [NormalDist().inv_cdf((i + 0.5) / 9) for i in range(9)]  # 실력 분포를 같은 확률의 9칸으로 나눈 값
CHI2_95 = {1: 3.84, 2: 5.99, 3: 7.81, 4: 9.49}  # 맞춘 값 수별 95% 기준. 가능도 비 검정으로 기록이 지금 값과 구분되는지 본다
KIND_LABEL = {"level": "레벨", "level_end": "끝 레벨", "duration": "길이", "kills": "처치", "kill_rate": "길이 1당 처치", "income": "수입"}
FEW_CLEARED = 3   # 넘긴 판이 이보다 적거나 들어간 판의 절반보다 적으면 넘긴 판의 평균은 살아남은 판으로 치우친 참고 값이다
VERDICT_LABEL = {"inside": "구간 안", "model_easier": "모델이 쉬움", "model_harder": "모델이 어려움"}


def wilson(cleared: int, entered: int) -> tuple[float, float]:
    """통과율의 95% 윌슨 구간. 표본이 적을수록 넓다."""
    if entered <= 0:
        return 0.0, 1.0
    p, z2 = cleared / entered, Z95 * Z95
    mid = (p + z2 / (2 * entered)) / (1 + z2 / entered)
    half = Z95 * math.sqrt(p * (1 - p) / entered + z2 / (4 * entered * entered)) / (1 + z2 / entered)
    return (0.0 if cleared == 0 else mid - half), (1.0 if cleared == entered else mid + half)


def predicted(rows: list, survival: dict, skill: float, spread: float) -> float:
    """단계를 넘길 확률. 실력 차이(spread)가 있으면 실력 분포에 대해 평균한다."""
    rel, cfg = mm.stage_margin(rows, survival["even_margin"]), {"survival": survival}
    if spread <= 0:
        return mm.combat_survival(cfg, rel, skill)
    return sum(mm.combat_survival(cfg, rel, skill + spread * z) for z in SKILL_POINTS) / len(SKILL_POINTS)


def log_likelihood(points: list, survival: dict, skill: float, spread: float) -> float:
    total = 0.0
    for pt in points:
        p = min(1 - 1e-9, max(1e-9, predicted(pt["rows"], survival, skill, spread)))
        total += pt["cleared"] * math.log(p) + (pt["entered"] - pt["cleared"]) * math.log(1 - p)
    return total


def _maximize(score, start: list, low: list, high: list) -> tuple[list, float]:
    """score를 가장 크게 하는 점을 넬더-미드 단체법으로 찾는다. 서로 얽힌 값(slope와 even_margin)을 함께 움직인다.
    범위 밖의 점은 버린다. 작은 보폭으로 다시 시작해 멈춘 자리에서 더 찾는다. (점, 값)."""
    n = len(start)

    def value(x: list) -> float:
        return score(x) if all(a <= v <= b for v, a, b in zip(x, low, high)) else -math.inf

    best, best_score = list(start), value(start)
    for step in (1.0, 0.3, 0.1):
        points = [list(best)]
        for i in range(n):
            x = list(best)
            x[i] += step if x[i] + step <= high[i] else -step
            points.append(x)
        scored = sorted(((value(x), x) for x in points), key=lambda t: t[0], reverse=True)
        for _ in range(200):
            if max(max(x[i] for _, x in scored) - min(x[i] for _, x in scored) for i in range(n)) < 1e-4:
                break
            worst_score, worst = scored[-1]
            center = [sum(x[i] for _, x in scored[:-1]) / n for i in range(n)]
            flip = [c2 + (c2 - w) for c2, w in zip(center, worst)]
            flip_score = value(flip)
            if flip_score > scored[0][0]:
                far = [c2 + 2 * (c2 - w) for c2, w in zip(center, worst)]
                far_score = value(far)
                scored[-1] = (far_score, far) if far_score > flip_score else (flip_score, flip)
            elif flip_score > scored[-2][0]:
                scored[-1] = (flip_score, flip)
            else:
                near = [(c2 + w) / 2 for c2, w in zip(center, worst)]
                near_score = value(near)
                if near_score > worst_score:
                    scored[-1] = (near_score, near)
                else:
                    top = scored[0][1]
                    moved = [[(a + b) / 2 for a, b in zip(top, x)] for _, x in scored[1:]]
                    scored = [scored[0]] + [(value(x), x) for x in moved]
            scored.sort(key=lambda t: t[0], reverse=True)
        if scored[0][0] > best_score:
            best_score, best = scored[0]
    return best, best_score


def fit(points: list, survival: dict, skill: float, spread: float) -> dict:
    """기록에 가장 잘 맞는 slope와 등급별 even_margin(최대 가능도). skill은 even_margin과 같은 자리에 들어가 기록만으로 나눌 수 없어 고정한다.
    판단할 근거가 없는 값(모두 넘김·모두 실패, 여유가 다른 기록이 모자람, 찾는 범위의 끝)은 지금 값을 두고 notes에 이유를 남긴다."""
    notes: list = []
    even0 = survival["even_margin"]
    decided: dict = {}
    for pt in points:
        _, who = mm.stage_limit(pt["rows"], even0)
        decided.setdefault(who.get("rank"), []).append(pt)
    ranks = []
    for rank, pts in decided.items():
        cleared, entered = sum(p["cleared"] for p in pts), sum(p["entered"] for p in pts)
        if 0 < cleared < entered:
            ranks.append(rank)
        else:
            notes.append(f"{rank} 등급이 정한 단계는 {'모두 넘겼' if cleared else '모두 실패했'}습니다. 그 등급의 even_margin을 정할 수 없어 지금 값을 둡니다.")
    rel = {round(math.log(r), 6) for r in (mm.stage_margin(p["rows"], even0) for p in points) if 0 < r < math.inf}
    cleared, entered = sum(p["cleared"] for p in points), sum(p["entered"] for p in points)
    fit_slope = len(rel) >= 3 and 0 < cleared < entered
    if not fit_slope:
        notes.append("여유가 서로 다른 기록이 셋 미만이라(또는 모두 넘겼거나 모두 실패해) slope를 정할 수 없어 지금 값을 둡니다.")
    # 등급별 표로 풀어 둔다. 수 하나였으면 맞추지 않는 등급도 그 값을 지킨다(표에 없는 등급은 1이 된다)
    start = {r: mm.margin_reference(even0, r) for r in (*cb.RANKS, *decided)}
    if isinstance(even0, dict):
        start = {**start, **even0}
    ranges = {}
    for rank in list(ranks):
        finite = [m for m in (mm.row_margin(r) for p in points for r in p["rows"] if r.get("rank") == rank) if 0 < m < math.inf]
        if finite:
            ranges[rank] = (math.log(min(finite) / 16), math.log(max(finite) * 16))
        else:
            ranks.remove(rank)
            notes.append(f"{rank} 등급은 여유가 모두 0이거나 끝이 없습니다(서로 피해를 주지 못함). 그 등급의 even_margin을 정할 수 없어 지금 값을 둡니다.")
    ranges["slope"] = (math.log(0.1), math.log(20.0))

    def descend(free: list, free_slope: bool) -> tuple[dict, set]:
        """free(등급)와 slope를 로그 공간에서 함께 맞춘다. (결과, 찾는 범위 끝에 닿은 값들). 맞추지 않는 값은 지금 값이다."""
        names = free + (["slope"] if free_slope else [])
        result = {"slope": survival["slope"], "even": dict(start)}
        if not names:
            return result, set()
        low, high = [ranges[k][0] for k in names], [ranges[k][1] for k in names]

        def apply(x: list) -> dict:
            got = dict(zip(names, (math.exp(v) for v in x)))
            return {**survival, "slope": got.get("slope", survival["slope"]), "even_margin": {**start, **{r: got[r] for r in free}}}

        def score(x: list) -> float:
            return log_likelihood(points, apply(x), skill, spread)

        clip = lambda v, a, b: min(b, max(a, v))  # noqa: E731
        now = [clip(math.log(survival["slope"] if k == "slope" else start[k]), a, b) for k, a, b in zip(names, low, high)]
        best, best_score = _maximize(score, now, low, high)
        current = log_likelihood(points, {**survival, "even_margin": start}, skill, spread)
        if best_score <= current + 1e-9:
            return result, set()
        chosen = apply(best)
        edges = {k for k, v, a, b in zip(names, best, low, high) if v - a < 0.02 or b - v < 0.02}

        def span(i: int) -> list:
            """다른 값을 고정하고 이 값만 움직여 95% 안에 드는 범위(로그 공간에서 이분 탐색). 대략의 범위다."""
            out = []
            for bound in (low[i], high[i]):
                inside, outside, x = best[i], bound, list(best)
                x[i] = bound
                if score(x) >= best_score - 1.92:
                    out.append(math.exp(bound))
                    continue
                for _ in range(30):
                    x[i] = (inside + outside) / 2
                    if score(x) >= best_score - 1.92:
                        inside = x[i]
                    else:
                        outside = x[i]
                out.append(math.exp(inside))
            return out

        return {"slope": chosen["slope"], "even": chosen["even_margin"], "spans": {k: span(i) for i, k in enumerate(names)},
                "gain": 2 * (best_score - current), "count": len(names)}, edges

    free, free_slope = list(ranks), fit_slope
    state, edges = descend(free, free_slope)
    rejected: set = set()
    while edges:  # 끝에 닿은 값은 제안하지 않으므로, 그 값을 지금 값으로 돌리고 나머지를 다시 맞춘다
        rejected |= edges
        free, free_slope = [r for r in free if r not in edges], free_slope and "slope" not in edges
        state, edges = descend(free, free_slope)
    for name in sorted(rejected, key=str):
        notes.append(f"{name}의 값이 찾는 범위의 끝에 닿았습니다. 기록으로 정해지지 않은 값이라 제안하지 않고 지금 값을 둡니다.")
    # 값을 맞추면 가능도는 늘 조금 오른다. 기록의 잡음을 값으로 옮기지 않게, 지금 값과 구분될 때만 제안한다
    gain, count = state.get("gain", 0.0), state.get("count", 0)
    limit = CHI2_95.get(count, 9.49 + 2 * (count - 4))
    significant = count > 0 and gain >= limit
    if count and not significant:
        notes.append(f"기록이 지금 값과 구분되지 않습니다(가능도 차이 {gain:.1f} < 기준 {limit:g}). 바꿀 근거가 없어 제안하지 않습니다.")
    fitted = {r: significant and r in free for r in decided}
    fit_slope_now = significant and free_slope
    suggested_even: object = even0
    if any(fitted.values()):
        suggested_even = {r: round(v, 4) if fitted.get(r) else v for r, v in state["even"].items() if r is not None}
    spans = state.get("spans", {})
    width = lambda name: [round(v, 4) for v in spans[name]]  # noqa: E731
    suggested = {**survival, "slope": round(state["slope"], 3) if fit_slope_now else survival["slope"], "even_margin": suggested_even}
    return {"slope": {"current": survival["slope"], "suggested": suggested["slope"], "fitted": fit_slope_now,
                      "range": width("slope") if fit_slope_now else None},
            "even_margin": {"current": even0, "suggested": suggested_even, "fitted": fitted,
                            "range": {r: width(r) for r, ok in fitted.items() if ok}},
            "significant": significant,
            "log_likelihood": {"current": round(log_likelihood(points, survival, skill, spread), 3),
                               "suggested": round(log_likelihood(points, suggested, skill, spread), 3)},
            "points": len(points), "runs": entered, "notes": notes}


# ---------- 가정값과 실측 ----------
def _mean(pairs: list):
    total = sum(w for _, w in pairs)
    return round(sum(v * w for v, w in pairs) / total, 4) if total else None


def _row(kind: str, stage: str, item, assumed, measured, n: int, where: str, tolerance: float, entered: int | None = None,
         survivors: bool = False) -> dict:
    """entered: 넘긴 판으로 잰 값이면 그 단계에 들어간 판 수. 넘긴 판이 적으면 few(참고)로 둔다.
    survivors: 가정 자체가 넘긴 판의 값(다음 단계에 들어설 때의 레벨)이면 비율로는 치우치지 않으므로 판 수만 본다."""
    off = measured != assumed if not assumed else abs(measured - assumed) > tolerance * abs(assumed) + 1e-9
    few = entered is not None and (n < FEW_CLEARED or (not survivors and 2 * n < entered))
    return {"kind": kind, "stage": stage, "item": item, "assumed": assumed, "measured": measured, "n": n, "off": off, "where": where,
            "entered": entered, "few": few, "mixed": False}   # mixed: 조건을 섞은 평균이고 조건마다 같은 쪽으로 다르지 않음(calibrate가 단다)


def _entered(records: list, key: str) -> int:
    """그 값을 잴 수 있었던 기록들이 들어간 판 수. 넘긴 판이 없는 기록은 값을 적을 수 없어도 센다(모두 실패한 묶음).
    넘긴 판이 있는데 값을 적지 않은 기록(그 값을 남기지 않는 세션)은 세지 않는다."""
    return sum(x["entered"] for x in records if key in x or not x["cleared"])


def _economy_by_stage(entries: list) -> dict:
    """{전투 단계: [재화 흐름 단계(원본, 계산 결과)]}. combat_stage로 이은 단계, 없으면 같은 id. 계산하지 못한 단계는 뺀다."""
    out: dict = {}
    for d in entries:
        if d["ok"] and d["kind"] == "economy":
            timeline = {st["id"]: st for st in d["report"]["stages"]}
            for s in d["data"].get("stages") or []:
                if isinstance(s, dict) and isinstance(s.get("id"), str) and s["id"] in timeline and c.combat_link(s):
                    out.setdefault(c.combat_link(s), []).append((s, timeline[s["id"]]))
    return out


def compare(entries: list, sessions: list, tolerance: float, notes: list) -> list:
    """가정값(판 안 성장의 단계별 레벨, 재화 흐름의 길이·처치 수·수입)을 기록의 판 평균과 나란히 놓는다.
    레벨은 그 단계에 들어간 판 기준, 나머지는 그 단계를 넘긴 판 기준이다(재화 흐름은 평범하게 끝까지 깬 판을 가정한다).
    기록은 있는데 가정을 읽지 못해 비교하지 못한 값은 notes에 남긴다."""
    growth = next((d["data"] for d in entries if d["ok"] and d["kind"] == "growth"), None)
    settings = gr.read_settings(growth, []) if growth else None
    level_at = (settings or {}).get("level_at", {})
    order = list(level_at)
    econ = _economy_by_stage(entries)
    stages = list(dict.fromkeys(x["stage"] for s in sessions for x in s["stage_stats"]))
    rows = []
    no_level, no_econ, no_next, timed, same = [], [], [], [], []
    for stage in stages:
        recs = [x for s in sessions for x in s["stage_stats"] if x["stage"] == stage]
        levels = [(x["level"], x["entered"]) for x in recs if "level" in x and x["entered"]]
        if levels and level_at.get(stage) is not None:
            rows.append(_row("level", stage, None, level_at[stage], _mean(levels), sum(w for _, w in levels), f"growth.json growth.level_at.{stage}", tolerance))
        elif levels:
            no_level.append(stage)
        full = [x for x in recs if x["cleared"]]
        ends = [(x["level_end"], x["cleared"]) for x in full if "level_end" in x]
        if ends:   # 넘긴 판이 단계를 끝낼 때의 레벨은 다음 단계에 들어설 때의 레벨이다(다음 단계의 기록이 없는 시험판도 잰다)
            nxt = order[order.index(stage) + 1] if stage in order and order.index(stage) + 1 < len(order) else None
            if nxt is None:
                no_next.append(stage)
            else:
                rows.append(_row("level_end", stage, None, level_at[nxt], _mean(ends), sum(w for _, w in ends), f"growth.json growth.level_at.{nxt}", tolerance,
                                 _entered(recs, "level_end"), survivors=True))
        parts = econ.get(stage)
        if not parts and (any(k in x for x in full for k in ("duration", "kills", "income")) or any("kill_rate" in x for x in recs)):
            no_econ.append(stage)
        if not parts:
            continue
        first = parts[0][0]["id"]
        length = sum(st["duration"] for _, st in parts)
        assumed: dict = {}
        for raw, _ in parts:
            for k, v in (raw.get("kills") or {}).items():
                assumed[k] = assumed.get(k, 0) + v
        paced = [x for x in recs if "kill_rate" in x and x["entered"]]
        if paced and length:   # 들어간 판 전체의 처치 속도. 넘긴 판이 적어도 잴 수 있다
            for enemy in dict.fromkeys(list(assumed) + [k for x in paced for k in x["kill_rate"]]):
                pairs = [(x["kill_rate"].get(enemy, 0), x.get("played_length", x["entered"])) for x in paced]   # 길이로 가중하면 처치 합 ÷ 길이 합이다
                rows.append(_row("kill_rate", stage, enemy, round(assumed.get(enemy, 0) / length, 4), _mean(pairs), sum(x["entered"] for x in paced),
                                 f"economy.json stages.{first}.kills.{enemy}", tolerance))
        if not full:
            continue
        durations = [(x["duration"], x["cleared"]) for x in full if "duration" in x]
        if durations and any(x.get("timed") for x in recs):
            timed.append(stage)
        elif durations:
            rows.append(_row("duration", stage, None, length, _mean(durations), sum(w for _, w in durations),
                             f"economy.json stages.{first}.duration", tolerance, _entered(recs, "duration")))
            if all(d == length for d, _ in durations):
                same.append(stage)
        kills = [x for x in full if "kills" in x]
        if kills:
            for enemy in dict.fromkeys(list(assumed) + [k for x in kills for k in x["kills"]]):
                pairs = [(x["kills"].get(enemy, 0), x["cleared"]) for x in kills]
                rows.append(_row("kills", stage, enemy, assumed.get(enemy, 0), _mean(pairs), sum(w for _, w in pairs),
                                 f"economy.json stages.{first}.kills.{enemy}", tolerance, _entered(recs, "kills")))
        incomes = [x for x in full if "income" in x]
        for cur in dict.fromkeys(k for x in incomes for k in x["income"]):
            pairs = [(x["income"].get(cur, 0), x["cleared"]) for x in incomes]
            rows.append(_row("income", stage, cur, sum(st["income"].get(cur, 0) for _, st in parts), _mean(pairs), sum(w for _, w in pairs),
                             f"economy.json stages.{first} 수입({cur})", tolerance, _entered(recs, "income")))
    if timed:
        notes.append(f"단계 {', '.join(timed)}: 시간이 다 되면 끝나는 단계(timed)라 길이는 늘 같아 비교하지 않았습니다. 처치는 처치 속도(kill_rate)로 봅니다.")
    if same:   # 시간 제한 단계인지는 기록만으로 알 수 없다(합성 기록이나 정수로 찍은 길이도 같아진다). 적게 한다
        notes.append(f"단계 {', '.join(same)}: 넘긴 판의 길이가 모두 가정과 같습니다. 시간이 다 되면 끝나는 단계면 그 단계 기록에 \"timed\": true를 적습니다. 그러면 길이를 비교하지 않습니다.")
    if no_next:
        notes.append(f"단계 {', '.join(no_next)}의 끝 레벨을 비교하지 못했습니다(판 안 성장의 level_at에 다음 단계가 없음).")
    if no_level:
        why = "판 안 성장 데이터가 없거나 그 설정에 오류가 있어" if settings is None else "판 안 성장의 level_at에 없어"
        notes.append(f"단계 {', '.join(no_level)}의 레벨을 비교하지 못했습니다({why}).")
    if no_econ:
        notes.append(f"단계 {', '.join(no_econ)}의 길이·처치·수입을 비교하지 못했습니다(이어진 재화 흐름 단계가 없거나 그 단계를 계산하지 못함).")
    return rows


# ---------- 통과율 ----------
def _points(cfg: dict, sessions: list, notes: list) -> list:
    ctx = cfg["_combat"]
    known = {u["id"] for u in cfg["upgrades"]}
    builds = (ctx["growth"] or {}).get("builds", {})
    if not ctx["growth"] and any(s.get("growth_build") or any("level" in x for x in s["stage_stats"]) for s in sessions):
        notes.append("설정이 판 안 성장을 쓰지 않아 기록의 growth_build와 level을 예측에 반영하지 못했습니다.")
    out = []
    for s in sessions:
        if "upgrades" not in s:
            notes.append(f"세션 {s['id']}: upgrades(그때 가진 영구 강화)가 없어 통과율 비교에서 뺐습니다. 없었으면 []로 적습니다.")
            continue
        old = [u for u in s["upgrades"] if u not in known]
        build = s.get("growth_build") if ctx["growth"] else None
        if old or (build and build not in builds):
            notes.append(f"세션 {s['id']}: 지금 데이터에 없는 {', '.join(old + ([build] if build and build not in builds else []))} 때문에 통과율 비교에서 뺐습니다.")
            continue
        recs = [x for x in s["stage_stats"] if x["entered"]]
        outside = [x["stage"] for x in recs if x["stage"] not in ctx["stages"]]
        if outside:
            notes.append(f"세션 {s['id']}: 판의 단계에 없는 {', '.join(outside)}의 기록은 통과율 비교에서 뺐습니다.")
        levels = {x["stage"]: max(1, round(x["level"])) for x in recs if "level" in x}
        rows = mm.stage_rows(cfg, s["upgrades"], levels, build)
        out += [{"session": s["id"], "stage": x["stage"], "rows": rows[x["stage"]], "entered": x["entered"], "cleared": x["cleared"]}
                for x in recs if x["stage"] in rows]
    return out


LARGE_CHANGE = 4   # 제안이 지금 값의 이 배수를 넘거나(또는 1/배수 밑) 바뀌면 모델이 담지 못하는 것을 값이 메우는지 의심한다


def _fit_warnings(cfg: dict, points: list, result: dict) -> list:
    """맞춘 등급의 even_margin은 그 등급의 적이 있는 모든 단계에 쓰인다. 기록이 없는 단계와, 지금 값과 크게 다른 제안을 알린다."""
    e = result["even_margin"]
    fitted = [r for r, ok in e["fitted"].items() if ok]
    if not fitted:
        return []
    try:
        rows = mm.stage_rows(cfg, [])
    except ConfigError:
        rows = {}
    recorded = {p["stage"] for p in points}
    out = []
    for rank in fitted:
        others = [sid for sid, got in rows.items() if sid not in recorded and any(x.get("rank") == rank for x in got)]
        if others:
            out.append(f"맞춘 등급 {rank}의 even_margin은 기록이 없는 단계({', '.join(others)})의 예측도 바꿉니다. "
                       "그 단계를 플레이한 기록이 생기기 전에는 옮기지 않거나, 옮긴 뒤 그 단계의 목표를 다시 봅니다.")
        now, new = mm.margin_reference(e["current"], rank), e["suggested"][rank]
        ratio = new / now if now else math.inf
        if ratio >= LARGE_CHANGE or ratio <= 1 / LARGE_CHANGE:
            out.append(f"등급 {rank}의 even_margin 제안이 지금 값의 {ratio:.2g}배입니다(지금 {now:g} → 제안 {new:g}). "
                       "모델이 담지 못하는 것(적이 쌓임, 이동, 앞 단계에서 잃은 체력)을 이 값이 대신 메우는 것일 수 있습니다. "
                       "옮기기 전에 처치 시간이 단계 길이를 넘는지(kill_time_over_length)와 처치 속도(kill_rate)를 먼저 봅니다.")
    return out


def survival_report(cfg: dict, sessions: list, notes: list) -> dict | None:
    points = _points(cfg, sessions, notes)
    if not points:
        return None
    skill, spread, survival = cfg["player"]["skill"], cfg["player"]["skill_spread"], cfg["survival"]
    result = fit(points, survival, skill, spread)
    notes += result.pop("notes")
    notes += _fit_warnings(cfg, points, result)
    better = {**survival, "slope": result["slope"]["suggested"], "even_margin": result["even_margin"]["suggested"]}
    stages = []
    for stage in cfg["_combat"]["stages"]:
        mine = [p for p in points if p["stage"] == stage]
        if not mine:
            continue
        entered, cleared = sum(p["entered"] for p in mine), sum(p["cleared"] for p in mine)
        low, high = wilson(cleared, entered)
        guess = sum(predicted(p["rows"], survival, skill, spread) * p["entered"] for p in mine) / entered
        guess2 = sum(predicted(p["rows"], better, skill, spread) * p["entered"] for p in mine) / entered
        stages.append({"stage": stage, "entered": entered, "cleared": cleared, "rate": round(cleared / entered, 4),
                       "low": round(low, 4), "high": round(high, 4), "predicted": round(guess, 4), "predicted_suggested": round(guess2, 4),
                       "verdict": "inside" if low <= guess <= high else ("model_easier" if guess > high else "model_harder")})
    return {"stages": stages, "fit": result}


def _expanded(s: dict) -> list:
    """세션을 강화 상태별 기록으로 편다. groups가 있으면 묶음마다 하나(세션의 growth_build가 기본값), 없으면 세션 그대로."""
    if not s.get("groups"):
        return [s]
    base = {k: v for k, v in s.items() if k != "groups"}
    return [{**base, **g, "id": f"{s['id']}#{n}"} for n, g in enumerate(s["groups"], start=1)]


def _inputs(entries: list, used: list) -> list:
    kinds = ("playtests", "growth", "economy", "combat", "items", "upgrades", "enemies", "crafting")
    return [{"path": d["path"], "sha256": hashlib.sha256(Path(d["path"]).read_bytes()).hexdigest()}
            for d in entries if d["ok"] and d["kind"] in kinds] + used


def _same_value(have, want) -> bool:
    """시험 조건 값이 같은가. 둘 다 수로 읽히면 수로(1, 1.0, "1"은 같다), 아니면 글자 그대로 맞춘다. 참·거짓 값은 기록 검사가 막는다."""
    if have is None:
        return False
    try:
        return math.isclose(float(have), float(want))
    except (TypeError, ValueError):
        return str(have) == str(want)


def _supply_capped(rows: list, entries: list) -> list:
    """넘긴 판의 처치가 레벨 구성에 놓인 적 수와 같은 단계. 나온 적을 다 잡았다는 뜻이라, 처치 수는 처치 능력이 아니라 공급을 잰 값이다."""
    placed: dict = {}
    for d in entries:   # 레벨 구성 검사의 단계 합계. 모르는 적이 있어 다 세지 못한 단계는 kills가 None이다
        if d["ok"] and d["kind"] == "levels":
            for st in d["report"].get("stages") or []:
                for enemy, n in (st.get("kills") or {}).items():
                    key = (st.get("id"), enemy)
                    placed[key] = placed.get(key, 0) + n
    capped: dict = {}
    for x in rows:
        n = placed.get((x["stage"], x["item"]))
        if x["kind"] == "kills" and n and x["measured"] is not None and abs(x["measured"] - n) < 1e-6:
            capped.setdefault(x["stage"], []).append(f"{x['item']} {_num(n)}")
    return [f"단계 {stage}: 넘긴 판의 처치({', '.join(items)})가 레벨 구성에 놓인 적 수와 같습니다. 나온 적을 다 잡았다는 뜻이라 처치 수로는 더 잡을 수 있었는지 알 수 없습니다"
            "(적이 나오는 수가 처치를 묶음). 처치 속도나 남은 적 수로 봅니다. 그 레벨에 처치 시간 경고(kill_time_over_length)가 나면, 기록상 다 잡았다는 것을 근거로 "
            "그 레벨의 acknowledged에 적을 수 있습니다." for stage, items in capped.items()]


def _mark_mixed(rows: list, entries: list, records: list, cols: list, tolerance: float) -> None:
    """조건을 섞어 계산한 비교 줄마다, 조건별로 다시 비교해 모든 조건이 같은 쪽으로 다르고(참고가 아님) 둘 이상일 때만 고칠 곳으로 둔다.
    그렇지 않은 다른 줄은 mixed(참고)로 둔다. 섞인 평균은 한 조건이 만든 차이일 수 있다."""
    key = lambda r: tuple(str((r.get("variant") or {}).get(col)) for col in cols)  # noqa: E731
    parts: dict = {}
    for r in records:
        parts.setdefault(key(r), []).append(r)
    per = [compare(entries, recs, tolerance, []) for recs in parts.values()]
    for x in rows:
        x["mixed"] = False
        same = [y for got in per for y in got if (y["kind"], y["stage"], y["item"]) == (x["kind"], x["stage"], x["item"])]
        if not x["off"]:   # 평균이 가정과 맞아도 조건마다 가정의 양쪽으로 크게 갈리면 맞는 것이 아니다
            vals = [y["measured"] for y in same if y["measured"] is not None and not y["few"]]   # 넘긴 판이 적은 조건은 살아남은 판의 값(참고)이다
            x["mixed"] = bool(x["assumed"]) and len(vals) > 1 and min(vals) < x["assumed"] < max(vals) \
                and max(vals) - min(vals) > tolerance * abs(x["assumed"]) + 1e-9
            continue
        side = 1 if (x["measured"] or 0) > (x["assumed"] or 0) else -1
        agree = len(same) > 1 and all(y["off"] and not y["few"] and (1 if (y["measured"] or 0) > (y["assumed"] or 0) else -1) == side for y in same)
        x["mixed"] = not agree


def calibrate(path, sessions: list | None = None, tolerance: float = DEFAULT_TOLERANCE, variant: dict | None = None) -> dict:
    """path: 프로젝트·데이터 폴더(가정값 비교만) 또는 시뮬레이터 설정 파일(전투 계산 모델, 통과율 비교와 제안까지). 파일을 고치지 않는다.
    variant: {열: 값}. 주면 그 시험 조건의 묶음(runlog --group-by가 단 variant)만 쓴다. 값은 글자로 맞춘다(1과 "1"은 같다)."""
    path = Path(path)
    if tolerance < 0:
        raise ConfigError(f"--tolerance는 0 이상의 비율입니다: {tolerance:g}")
    cfg = None
    if path.is_file():
        read = datasets.read(path)
        if read["ok"] and "trials" not in read["data"]:  # 데이터 파일(playtests.json 등). 설정의 모르는 키로 보고하면 엉뚱한 오타 안내가 된다
            raise ConfigError(f"{c.josa(path.name, '은는')} 시뮬레이터 설정이 아닙니다. 시뮬레이터 설정(전투 계산 모델)이나 프로젝트·데이터 폴더를 넘기세요.")
        cfg = mm.load_config(path)
        if cfg["model"] != "combat":
            raise ConfigError("통과율 비교는 전투 계산 모델(model: combat) 설정만 씁니다. 가정값 비교만 하려면 프로젝트 폴더를 넘기세요.")
        cfg = mm.attach(cfg, path.resolve().parent)
    entries = cfg["_entries"] if cfg else datasets.collect([path])
    logs = [d for d in entries if d["ok"] and d["kind"] == "playtests"]
    if not logs:
        raise ConfigError("플레이 기록(playtests.json)을 찾지 못했습니다.")
    broken = [e for d in logs for e in d["report"]["errors"]]
    if broken:
        raise ConfigError(f"플레이 기록에 오류 {len(broken)}건이 있습니다({broken[0]['where']}: {broken[0]['message']}). `studio.py check`로 먼저 고치세요.")
    raw = [s for d in logs for s in d["data"].get("playtests") or [] if isinstance(s, dict)]
    chosen = [s for s in raw if s.get("stage_stats") or s.get("groups")]
    if sessions:
        missing = [x for x in sessions if x not in {s.get("id") for s in chosen}]
        if missing:
            raise ConfigError(f"단계 기록이 있는 세션이 아닙니다: {', '.join(missing)}.{c.did_you_mean(missing[0], [s['id'] for s in chosen])}")
        chosen = [s for s in chosen if s["id"] in sessions]
    if not chosen:
        raise ConfigError("단계 기록(stage_stats)이 있는 세션이 없습니다. 아무것도 비교하지 않았으므로 통과가 아닙니다.")
    notes: list = []
    for key, label in (("build", "빌드"), ("concept", "컨셉")):
        values = list(dict.fromkeys(s.get(key) for s in chosen))
        if len(values) > 1:
            notes.append(f"{c.josa(label, '이가')} 다른 세션을 합쳐 계산했습니다({', '.join(map(str, values))}). 한쪽만 보려면 --sessions로 고릅니다.")
    ids = {s["id"] for s in chosen}
    broken_counts = dict.fromkeys(w["where"] for d in logs for w in d["report"]["warnings"] if w["code"] == "stage_counts_mismatch" and w["where"] in ids)
    notes += [f"세션 {sid}: 판 수가 단계 사이에 이어지지 않습니다. 기록을 확인하세요(그대로 계산했습니다)." for sid in broken_counts]
    records = [r for s in chosen for r in _expanded(s)]
    variants: dict = {}
    for r in records:
        for col, value in (r.get("variant") or {}).items():
            variants.setdefault(col, {})[str(value)] = None
    if variant:
        wanted = " · ".join(f"{k}={v}" for k, v in variant.items())
        kept = [r for r in records if all(_same_value((r.get("variant") or {}).get(k), v) for k, v in variant.items())]
        if not kept:
            have = "; ".join(f"{col}: {', '.join(values)}" for col, values in variants.items()) or "묶음에 variant가 없음(runlog --group-by로 나눕니다)"
            raise ConfigError(f"시험 조건 {wanted}인 묶음이 없습니다. 기록의 시험 조건: {have}.")
        notes.append(f"시험 조건 {wanted}인 묶음만 썼습니다({len(kept)}/{len(records)}묶음).")
        records = kept
        variants = {col: {str(v): None for v in dict.fromkeys((r.get("variant") or {}).get(col) for r in records) if v is not None} for col in variants}
    mixed = [col for col, values in variants.items() if len(values) > 1]
    for col in mixed:
        notes.append(f"시험 조건이 다른 묶음을 합쳐 계산했습니다({col}: {', '.join(variants[col])}). 조건마다 같은 쪽으로 다를 때만 고칠 곳(⚠)을 가리킵니다. "
                     f"조건별로 보려면 --variant {col}=값으로 고릅니다.")
    survival = survival_report(cfg, records, notes) if cfg else None
    if cfg is not None and survival is None:
        raise ConfigError("통과율을 비교할 기록이 없습니다(" + " ".join(notes) + "). 가정값 비교만 하려면 프로젝트 폴더를 넘기세요.")
    if cfg is None:
        notes.append("통과율 비교와 생존 곡선 제안은 시뮬레이터 설정(전투 계산 모델)을 넘기면 합니다.")
    rows = compare(entries, records, tolerance, notes)
    notes += _supply_capped(rows, entries)
    if mixed:
        _mark_mixed(rows, entries, records, mixed, tolerance)
        if survival and survival["fit"]["significant"]:
            survival["fit"]["mixed"] = True
            notes.append("생존 곡선 제안은 시험 조건을 섞어 맞춘 값입니다. --variant로 조건마다 보고, 같은 쪽으로 바뀔 때만 옮깁니다.")
    if not rows and survival is None:
        raise ConfigError("단계 기록과 가정값을 맞춰 볼 값이 없습니다. 같은 단계에 가정값(판 안 성장의 level_at, 재화 흐름의 duration·kills·income)이 있고, "
                          "기록에도 그 값(level, duration, kills, income)과 통과한 판이 있어야 비교합니다(" + " ".join(notes) + "). 아무것도 비교하지 않았으므로 통과가 아닙니다.")
    return {"evidence": EVIDENCE, "config": str(path) if cfg else None, "tolerance": tolerance,
            "sessions": [{"id": s["id"], "date": s.get("date"), "build": s.get("build"), "runs": s.get("runs")} for s in chosen],
            "compare": rows, "survival": survival, "notes": notes,
            "inputs": _inputs(entries, [{"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}] if cfg else [])}


# ---------- 판별 로그 ----------
RUN_REQUIRED = ("run", "stage", "cleared")
RUN_COLUMNS = (*RUN_REQUIRED, "upgrades", "growth_build", "player", "level", "level_end", "duration")
RUN_PREFIXES = ("kills.", "income.")
RUN_HELP = "열: run, stage, cleared(1/0), upgrades, growth_build, player, level, level_end, duration, kills.<적>, income.<재화>. 쓰지 않는 열은 이름 앞에 _를 붙입니다."
CLEARED = {"1": True, "true": True, "yes": True, "0": False, "false": False, "no": False}


def _log_number(raw: str, column: str, n: int) -> float | None:
    raw = (raw or "").strip()
    if raw == "":
        return None
    try:
        value = float(raw)
    except ValueError:
        value = math.nan
    if not math.isfinite(value):
        raise ConfigError(f"{n}번째 줄 {column}: 수가 아닙니다: {raw!r}")
    return value


def _whole(v: float):
    return int(v) if float(v).is_integer() else round(v, 4)


def _check_run_columns(columns: list) -> None:
    """모르는 열을 그대로 두면 오타 난 열의 값이 조용히 사라진다. _로 시작하는 열은 쓰지 않는다고 표시한 열이다."""
    lacking = [k for k in RUN_REQUIRED if k not in columns]
    if lacking:
        raise ConfigError(f"판 로그에 {', '.join(lacking)} 열이 필요합니다. {RUN_HELP}")
    unknown = [k for k in columns if not (k in RUN_COLUMNS or k.startswith("_") or (k.startswith(RUN_PREFIXES) and k.split(".", 1)[1]))]
    if unknown:
        names = ", ".join(k or "(이름 없는 열)" for k in unknown)
        raise ConfigError(f"판 로그에 모르는 열이 있습니다: {names}.{c.did_you_mean(unknown[0].split('.')[0], [*RUN_COLUMNS, 'kills', 'income'])} {RUN_HELP}")
    repeated = [k for k in dict.fromkeys(columns) if columns.count(k) > 1]
    if repeated:
        raise ConfigError(f"판 로그의 열 이름이 겹칩니다: {', '.join(repeated)}")


def summarize_runs(path, group_by: str | None = None, timed: list | None = None) -> dict:
    """판별 로그(CSV, 들어간 단계마다 한 줄)를 세션의 단계 기록으로 모은다. 강화 상태(와 빌드)별 묶음을 돌려주고 파일을 고치지 않는다.
    group_by: 강화가 아닌 시험 조건(예: _setting)의 열. 주면 그 값으로도 나누고 묶음에 variant {열: 값}을 단다.
    열: run, stage, cleared(1/0) 필수. upgrades(;로 구분), growth_build, player, level, duration, kills.<적 id>, income.<재화> 선택.
    레벨은 들어간 판의 평균, 길이·처치·수입은 넘긴 판의 평균이다. 형식: playtest-verdict/references/calibration.md"""
    path = Path(path)
    try:
        with path.open(encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            columns = [x.strip() for x in reader.fieldnames or []]
            rows = [(reader.line_num, row) for row in reader]
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise ConfigError(f"판 로그를 읽지 못했습니다({path}): {exc}")
    _check_run_columns(columns)
    if group_by is not None and group_by not in columns:
        raise ConfigError(f"판 로그에 나눌 열 {c.josa(group_by, '이가')} 없습니다. 열: {', '.join(columns)}")
    runs: dict = {}
    for n, row in rows:
        if None in row:  # DictReader는 열보다 많은 칸을 키 None에 모은다
            raise ConfigError(f"{n}번째 줄: 칸이 열({len(columns)}개)보다 많습니다: {', '.join(row[None])}")
        row = {k.strip(): (v or "").strip() for k, v in row.items()}
        rid, stage, flag = row["run"], row["stage"], CLEARED.get(row["cleared"].lower())
        if not rid or not stage or flag is None:
            raise ConfigError(f"{n}번째 줄: run, stage와 cleared(1/0)가 필요합니다: cleared {row['cleared']!r}")
        if group_by is not None and not row[group_by]:
            raise ConfigError(f"{n}번째 줄: 나눌 열 {group_by}의 값이 비어 있습니다. 판마다 시험 조건을 적습니다.")
        state = (tuple(sorted(x.strip() for x in row.get("upgrades", "").split(";") if x.strip())), row.get("growth_build") or None,
                 row[group_by] if group_by is not None else None)
        run = runs.setdefault(rid, {"state": state, "stages": [], "failed": False, "player": row.get("player")})
        if run["state"] != state:
            kept = "upgrades나 growth_build" + (f"나 {group_by}" if group_by is not None else "")
            raise ConfigError(f"{n}번째 줄: 판 {rid}의 줄마다 {c.josa(kept, '이가')} 다릅니다. 판 안에서는 같아야 합니다.")
        if stage in [x["stage"] for x in run["stages"]]:
            raise ConfigError(f"{n}번째 줄: 판 {rid}에 단계 {c.josa(stage, '이가')} 두 번 있습니다.")
        if run["failed"]:
            raise ConfigError(f"{n}번째 줄: 판 {c.josa(rid, '은는')} 앞 단계에서 실패했는데 단계 {c.josa(stage, '이가')} 이어집니다.")
        rec = {"stage": stage, "cleared": flag, "level": _log_number(row.get("level"), "level", n),
               "level_end": _log_number(row.get("level_end"), "level_end", n),
               "duration": _log_number(row.get("duration"), "duration", n), "kills": {}, "income": {}}
        for k, v in row.items():
            if k.startswith(RUN_PREFIXES):
                got = _log_number(v, k, n)
                if got is not None:
                    key, name = k.split(".", 1)
                    rec[key][name] = got
        run["stages"].append(rec)
        run["failed"] = not flag
    if not runs:
        raise ConfigError(f"판 로그에 판이 없습니다: {path}")
    logged = {x["stage"] for r in runs.values() for x in r["stages"]}
    stray = [s for s in timed or [] if s not in logged]
    if stray:
        raise ConfigError(f"--timed의 단계가 판 로그에 없습니다: {', '.join(stray)}. 로그의 단계: {', '.join(sorted(logged))}")
    groups: dict = {}
    for run in runs.values():
        groups.setdefault(run["state"], []).append(run)
    out = []
    for (upgrades, build, variant), mine in groups.items():
        order = list(dict.fromkeys(x["stage"] for r in mine for x in r["stages"]))
        stats = []
        for stage in order:
            recs = [x for r in mine for x in r["stages"] if x["stage"] == stage]
            full = [x for x in recs if x["cleared"]]
            item: dict = {"stage": stage, "entered": len(recs), "cleared": len(full)}
            levels = [x["level"] for x in recs if x["level"] is not None]
            ends = [x["level_end"] for x in full if x["level_end"] is not None]
            durations = [x["duration"] for x in full if x["duration"] is not None]
            if levels:
                item["level"] = _whole(sum(levels) / len(levels))
            if ends:
                item["level_end"] = _whole(sum(ends) / len(ends))   # 넘긴 판이 다음 단계에 들어설 때의 레벨
            if durations:
                item["duration"] = _whole(sum(durations) / len(durations))
            if stage in (timed or []):
                item["timed"] = True   # 시간이 다 되면 끝나는 단계(사용자가 --timed로 알려 준 것. 짐작하지 않는다)
            paced = [x for x in recs if x["kills"] and x["duration"]]   # 실패한 판도 센다. 넘긴 판만 세면 살아남은 판으로 치우친다
            if paced:
                length = sum(x["duration"] for x in paced)
                item["kill_rate"] = {k: round(sum(x["kills"].get(k, 0) for x in paced) / length, 4)
                                     for k in dict.fromkeys(k for x in paced for k in x["kills"])}
                item["played_length"] = _whole(length)   # 묶음을 합칠 때 처치 속도를 길이로 가중한다
            for key in ("kills", "income"):
                names = list(dict.fromkeys(k for x in full for k in x[key]))
                with_data = [x for x in full if x[key]]
                if names:
                    item[key] = {k: _whole(sum(x[key].get(k, 0) for x in with_data) / len(with_data)) for k in names}
            item["source"] = str(path)
            stats.append(item)
        group: dict = {"upgrades": list(upgrades), "runs": len(mine), "stage_stats": stats}   # runs: 이 묶음의 판 수. 단계를 골라 시작해도 맞다
        if build:
            group["growth_build"] = build
        if group_by is not None:
            group["variant"] = {group_by: variant}
        named = list(dict.fromkeys(r["player"] for r in mine if r["player"]))
        if named:
            group["players"] = named   # 판정 표본이 손으로 쓴 사람 수 대신 센다
        out.append(group)
    result: dict = {"runs": len(runs), "logs": [str(path)], "groups": out}
    players = list(dict.fromkeys(r["player"] for r in runs.values() if r["player"]))
    if players:
        result["players"] = players
    return result


# ---------- 출력 ----------
def _num(v) -> str:
    return c.num_text(float(v)) if v is not None else "–"


def _print_fit(f: dict) -> None:
    if not f["significant"]:
        print(f"생존 곡선 제안 없음 (기록 {f['points']}건 · {f['runs']}판): 지금 값을 그대로 둡니다. 이유는 아래 참고에 있습니다.")
        return
    print(f"생존 곡선 제안{' (조건 섞임, 참고)' if f.get('mixed') else ''} (기록 {f['points']}건 · {f['runs']}판, 가능도 {f['log_likelihood']['current']:g} → {f['log_likelihood']['suggested']:g}):")
    span = lambda r: f" (대략 {_num(r[0])}~{_num(r[1])})" if r else ""  # noqa: E731
    print(f"  slope {f['slope']['current']:g} → {f['slope']['suggested']:g}" + (span(f["slope"]["range"]) if f["slope"]["fitted"] else " (그대로)"))
    e = f["even_margin"]
    print(f"  even_margin {json.dumps(e['current'])} → {json.dumps(e['suggested'])}")
    done = [k for k, ok in e["fitted"].items() if ok]
    print("  맞춘 등급: " + (", ".join(f"{k}{span(e['range'].get(k))}" for k in done) or "없음"))
    others = [k for k in e["suggested"] if k not in done] if isinstance(e["suggested"], dict) else []
    if others:
        print("  기록으로 확인되지 않은 등급(지금 값 그대로): " + ", ".join(others))


def print_report(r: dict, off_only: bool = False) -> None:
    print("세션: " + " · ".join(f"{s['id']}({s['build']}, {s['runs']}판)" for s in r["sessions"]))
    s = r["survival"]
    if s:
        suggested = s["fit"]["significant"]
        for x in s["stages"]:
            print(f"단계 {x['stage']}: 실측 통과 {x['cleared']}/{x['entered']}판 {x['rate']:.0%} (구간 {x['low']:.0%}~{x['high']:.0%}) · "
                  f"예측 {x['predicted']:.0%} → {VERDICT_LABEL[x['verdict']]}" + (f" · 제안 값으로 {x['predicted_suggested']:.0%}" + (" (참고)" if s["fit"].get("mixed") else "") if suggested else ""))
        _print_fit(s["fit"])
    hint = lambda x: x.get("few") or x.get("mixed")  # noqa: E731
    off = sum(1 for x in r["compare"] if x["off"] and not hint(x))
    hints = sum(1 for x in r["compare"] if x["off"] and hint(x))
    print(f"가정값 비교: {len(r['compare'])}건 중 {off}건이 {r['tolerance']:.0%} 넘게 다름"
          + (f"(넘긴 판이 적거나 조건마다 달라 참고로 둔 {hints}건 제외)" if hints else ""))
    for x in r["compare"]:
        if off_only and not (x["off"] and not hint(x)):   # 머리줄의 "다름"과 같은 줄만 보인다
            continue
        item = f"({x['item']})" if x["item"] else ""
        if x.get("few"):   # 넘긴 판이 적으면 살아남은 판의 평균이라 고칠 곳을 가리키지 않는다
            tail = f" · 넘긴 판 {x['n']}/{x['entered']}판, 참고"
        elif x.get("mixed"):   # 조건을 섞은 평균이 한 조건의 차이이거나, 양쪽으로 갈린 값의 평균일 수 있다
            tail = " · 조건마다 다름, 참고"
        else:
            tail = f" ⚠ {x['where']}" if x["off"] else ""
        print(f"단계 {x['stage']} {KIND_LABEL[x['kind']]}{item}: 가정 {_num(x['assumed'])} · 측정 {_num(x['measured'])} (판 {x['n']})" + tail)
    for n in r["notes"]:
        print("참고: " + n)
    print("주의: 기록한 빌드와 플레이어에서 나온 값입니다. 제안은 자동으로 적용하지 않습니다. 실제 난이도·재미 판정이 아닙니다.")
