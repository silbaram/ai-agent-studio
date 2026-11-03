"""플레이 기록(data/playtests.json의 stage_stats)으로 가정값을 보정한다.

기획에서 가정한 값(단계별 레벨, 길이, 처치 수, 수입)을 실측과 나란히 놓고, 시뮬레이터 설정(전투 계산 모델)을 주면
단계 통과율의 예측과 실측을 비교해 생존 곡선(slope, even_margin) 값을 제안한다. 파일을 고치지 않는다.
제안은 표본에 맞춘 계산값이며, 재미나 실제 난이도를 판정하지 않는다. 형식: playtest-verdict/references/calibration.md
"""
from __future__ import annotations

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
KIND_LABEL = {"level": "레벨", "duration": "길이", "kills": "처치", "income": "수입"}
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
    for rank in ranks:
        finite = [m for m in (mm.row_margin(r) for p in points for r in p["rows"] if r.get("rank") == rank) if 0 < m < math.inf]
        ranges[rank] = (math.log(min(finite) / 16), math.log(max(finite) * 16))
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
        return {"slope": chosen["slope"], "even": chosen["even_margin"]}, edges

    free, free_slope = list(ranks), fit_slope
    state, edges = descend(free, free_slope)
    rejected: set = set()
    while edges:  # 끝에 닿은 값은 제안하지 않으므로, 그 값을 지금 값으로 돌리고 나머지를 다시 맞춘다
        rejected |= edges
        free, free_slope = [r for r in free if r not in edges], free_slope and "slope" not in edges
        state, edges = descend(free, free_slope)
    for name in sorted(rejected, key=str):
        notes.append(f"{name}의 값이 찾는 범위의 끝에 닿았습니다. 기록으로 정해지지 않은 값이라 제안하지 않고 지금 값을 둡니다.")
    fitted = {r: r in free for r in decided}
    suggested_even: object = even0
    if any(fitted.values()):
        suggested_even = {r: round(v, 4) if fitted.get(r) else v for r, v in state["even"].items() if r is not None}
    suggested = {**survival, "slope": round(state["slope"], 3) if free_slope else survival["slope"], "even_margin": suggested_even}
    return {"slope": {"current": survival["slope"], "suggested": suggested["slope"], "fitted": free_slope},
            "even_margin": {"current": even0, "suggested": suggested_even, "fitted": fitted},
            "log_likelihood": {"current": round(log_likelihood(points, survival, skill, spread), 3),
                               "suggested": round(log_likelihood(points, suggested, skill, spread), 3)},
            "points": len(points), "runs": entered, "notes": notes}


# ---------- 가정값과 실측 ----------
def _mean(pairs: list):
    total = sum(w for _, w in pairs)
    return round(sum(v * w for v, w in pairs) / total, 4) if total else None


def _row(kind: str, stage: str, item, assumed, measured, n: int, where: str, tolerance: float) -> dict:
    off = measured != assumed if not assumed else abs(measured - assumed) > tolerance * abs(assumed) + 1e-9
    return {"kind": kind, "stage": stage, "item": item, "assumed": assumed, "measured": measured, "n": n, "off": off, "where": where}


def _economy_by_stage(entries: list) -> dict:
    """{전투 단계: [재화 흐름 단계(원본, 계산 결과)]}. combat_stage로 이은 단계, 없으면 같은 id. 계산하지 못한 단계는 뺀다."""
    out: dict = {}
    for d in entries:
        if d["ok"] and d["kind"] == "economy":
            timeline = {st["id"]: st for st in d["report"]["stages"]}
            for s in d["data"].get("stages") or []:
                if isinstance(s, dict) and s.get("id") in timeline:
                    out.setdefault(s.get("combat_stage") or s["id"], []).append((s, timeline[s["id"]]))
    return out


def compare(entries: list, sessions: list, tolerance: float, notes: list) -> list:
    """가정값(판 안 성장의 단계별 레벨, 재화 흐름의 길이·처치 수·수입)을 기록의 판 평균과 나란히 놓는다.
    레벨은 그 단계에 들어간 판 기준, 나머지는 그 단계를 넘긴 판 기준이다(재화 흐름은 평범하게 끝까지 깬 판을 가정한다).
    기록은 있는데 가정을 읽지 못해 비교하지 못한 값은 notes에 남긴다."""
    growth = next((d["data"] for d in entries if d["ok"] and d["kind"] == "growth"), None)
    settings = gr.read_settings(growth, []) if growth else None
    level_at = (settings or {}).get("level_at", {})
    econ = _economy_by_stage(entries)
    stages = list(dict.fromkeys(x["stage"] for s in sessions for x in s["stage_stats"]))
    rows = []
    no_level, no_econ = [], []
    for stage in stages:
        recs = [x for s in sessions for x in s["stage_stats"] if x["stage"] == stage]
        levels = [(x["level"], x["entered"]) for x in recs if "level" in x and x["entered"]]
        if levels and level_at.get(stage) is not None:
            rows.append(_row("level", stage, None, level_at[stage], _mean(levels), sum(w for _, w in levels), f"growth.json growth.level_at.{stage}", tolerance))
        elif levels:
            no_level.append(stage)
        parts = econ.get(stage)
        full = [x for x in recs if x["cleared"]]
        if not parts and any(k in x for x in full for k in ("duration", "kills", "income")):
            no_econ.append(stage)
        if not parts or not full:
            continue
        first = parts[0][0]["id"]
        durations = [(x["duration"], x["cleared"]) for x in full if "duration" in x]
        if durations:
            rows.append(_row("duration", stage, None, sum(st["duration"] for _, st in parts), _mean(durations), sum(w for _, w in durations),
                             f"economy.json stages.{first}.duration", tolerance))
        kills = [x for x in full if "kills" in x]
        if kills:
            assumed: dict = {}
            for raw, _ in parts:
                for k, v in (raw.get("kills") or {}).items():
                    assumed[k] = assumed.get(k, 0) + v
            for enemy in dict.fromkeys(list(assumed) + [k for x in kills for k in x["kills"]]):
                pairs = [(x["kills"].get(enemy, 0), x["cleared"]) for x in kills]
                rows.append(_row("kills", stage, enemy, assumed.get(enemy, 0), _mean(pairs), sum(w for _, w in pairs),
                                 f"economy.json stages.{first}.kills.{enemy}", tolerance))
        incomes = [x for x in full if "income" in x]
        for cur in dict.fromkeys(k for x in incomes for k in x["income"]):
            pairs = [(x["income"].get(cur, 0), x["cleared"]) for x in incomes]
            rows.append(_row("income", stage, cur, sum(st["income"].get(cur, 0) for _, st in parts), _mean(pairs), sum(w for _, w in pairs),
                             f"economy.json stages.{first} 수입({cur})", tolerance))
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
    out = []
    for s in sessions:
        if "upgrades" not in s:
            notes.append(f"세션 {s['id']}: upgrades(그때 가진 영구 강화)가 없어 통과율 비교에서 뺐습니다. 없었으면 []로 적습니다.")
            continue
        old = [u for u in s["upgrades"] if u not in known]
        build = s.get("growth_build")
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


def survival_report(cfg: dict, sessions: list, notes: list) -> dict | None:
    points = _points(cfg, sessions, notes)
    if not points:
        notes.append("통과율을 비교할 기록이 없습니다.")
        return None
    skill, spread, survival = cfg["player"]["skill"], cfg["player"]["skill_spread"], cfg["survival"]
    result = fit(points, survival, skill, spread)
    notes += result.pop("notes")
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


def _inputs(entries: list, used: list) -> list:
    kinds = ("playtests", "growth", "economy", "combat", "items", "upgrades", "enemies", "crafting")
    return [{"path": d["path"], "sha256": hashlib.sha256(Path(d["path"]).read_bytes()).hexdigest()}
            for d in entries if d["ok"] and d["kind"] in kinds] + used


def calibrate(path, sessions: list | None = None, tolerance: float = DEFAULT_TOLERANCE) -> dict:
    """path: 프로젝트·데이터 폴더(가정값 비교만) 또는 시뮬레이터 설정 파일(전투 계산 모델, 통과율 비교와 제안까지). 파일을 고치지 않는다."""
    path = Path(path)
    cfg = None
    if path.is_file():
        read = datasets.read(path)
        if read["ok"] and "trials" not in read["data"]:  # 데이터 파일(playtests.json 등). 설정의 모르는 키로 보고하면 엉뚱한 오타 안내가 된다
            raise ConfigError(f"{path.name}은 시뮬레이터 설정이 아닙니다. 시뮬레이터 설정(전투 계산 모델)이나 프로젝트·데이터 폴더를 넘기세요.")
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
    chosen = [s for s in raw if s.get("stage_stats")]
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
            notes.append(f"{label}가 다른 세션을 합쳐 계산했습니다({', '.join(map(str, values))}). 한쪽만 보려면 --sessions로 고릅니다.")
    survival = survival_report(cfg, chosen, notes) if cfg else None
    if cfg is None:
        notes.append("통과율 비교와 생존 곡선 제안은 시뮬레이터 설정(전투 계산 모델)을 넘기면 합니다.")
    rows = compare(entries, chosen, tolerance, notes)
    if not rows and survival is None:
        raise ConfigError("단계 기록은 있지만 비교할 가정값이 없습니다(" + " ".join(notes) + "). 아무것도 비교하지 않았으므로 통과가 아닙니다.")
    return {"evidence": EVIDENCE, "config": str(path) if cfg else None, "tolerance": tolerance,
            "sessions": [{"id": s["id"], "date": s.get("date"), "build": s.get("build"), "runs": s.get("runs")} for s in chosen],
            "compare": rows, "survival": survival, "notes": notes,
            "inputs": _inputs(entries, [{"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}] if cfg else [])}


# ---------- 출력 ----------
def _num(v) -> str:
    return c.num_text(float(v)) if v is not None else "–"


def print_report(r: dict) -> None:
    print("세션: " + " · ".join(f"{s['id']}({s['build']}, {s['runs']}판)" for s in r["sessions"]))
    s = r["survival"]
    if s:
        for x in s["stages"]:
            print(f"단계 {x['stage']}: 실측 통과 {x['cleared']}/{x['entered']}판 {x['rate']:.0%} (구간 {x['low']:.0%}~{x['high']:.0%}) · "
                  f"예측 {x['predicted']:.0%} → {VERDICT_LABEL[x['verdict']]} · 제안 값으로 {x['predicted_suggested']:.0%}")
        f = s["fit"]
        print(f"생존 곡선 제안 (기록 {f['points']}건 · {f['runs']}판, 가능도 {f['log_likelihood']['current']:g} → {f['log_likelihood']['suggested']:g}):")
        print(f"  slope {f['slope']['current']:g} → {f['slope']['suggested']:g}" + ("" if f["slope"]["fitted"] else " (그대로)"))
        print(f"  even_margin {json.dumps(f['even_margin']['current'])} → {json.dumps(f['even_margin']['suggested'])}")
    for x in r["compare"]:
        item = f"({x['item']})" if x["item"] else ""
        print(f"단계 {x['stage']} {KIND_LABEL[x['kind']]}{item}: 가정 {_num(x['assumed'])} · 측정 {_num(x['measured'])} (판 {x['n']})"
              + (f" ⚠ {r['tolerance']:.0%} 넘게 다름: {x['where']}" if x["off"] else ""))
    for n in r["notes"]:
        print("참고: " + n)
    print("주의: 기록한 빌드와 플레이어에서 나온 값입니다. 제안은 자동으로 적용하지 않습니다. 실제 난이도·재미 판정이 아닙니다.")
