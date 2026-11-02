"""로그라이크 메타 성장을 추상 모델로 시뮬레이션한다.

런마다 방을 순서대로 지나며, 방 r의 생존 확률은
    p = clamp(sigmoid(slope * (power - difficulty(r)) + skill), floor, ceiling)
이다. 방을 통과하면 재화와 런 내 성장(power_per_room)을 얻고, 런이 끝나면 재화로 영구 강화를 산다.

이 모델은 경제·성장 곡선의 구조(몇 번째 런에 무엇을 사고 어디까지 가는지, 진척이 멈추는 구간)를
보기 위한 것이다. 실제 조작 난이도나 재미를 판정하지 않는다. 그 판단에는 플레이 기록이 필요하다.
형식: progression-economy/references/meta-model.md
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from pathlib import Path

from . import upgrades as vu

EVIDENCE_NOTE = (
    "computed: abstract model. Not a difficulty or fun verdict. "
    "Calibrate survival/skill against playtest telemetry before treating outcomes as measured."
)


class ConfigError(ValueError):
    pass


def _req(cfg: dict, key: str, kind, where: str = ""):
    if key not in cfg:
        raise ConfigError(f"{where}{key}가 필요합니다.")
    val = cfg[key]
    if kind is float:
        if not isinstance(val, (int, float)) or isinstance(val, bool):
            raise ConfigError(f"{where}{key}는 수여야 합니다: {val!r}")
    elif kind is int:
        if not isinstance(val, int) or isinstance(val, bool):
            raise ConfigError(f"{where}{key}는 정수여야 합니다: {val!r}")
    elif not isinstance(val, kind):
        raise ConfigError(f"{where}{key}의 형식이 잘못되었습니다: {val!r}")
    return val


def _load_upgrades_file(name, base_dir: Path | None) -> tuple[list, dict]:
    """영구 강화 데이터 파일(단일 원본)을 읽어 시뮬레이터용 목록으로 바꾼다. 삭제(cut) 항목은 뺀다."""
    if not isinstance(name, str) or not name:
        raise ConfigError("upgrades_file은 파일 경로 문자열이어야 합니다.")
    path = Path(name)
    if not path.is_absolute():
        path = (base_dir or Path.cwd()) / path
    try:
        data = vu.load(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ConfigError(f"upgrades_file을 읽을 수 없습니다 ({path}): {exc}")
    report = vu.validate(data)
    if report["errors"]:
        first = "; ".join(f"{e['where']}: {e['message']}" for e in report["errors"][:3])
        raise ConfigError(f"강화 데이터에 오류가 있습니다 ({path}). validate_upgrades.py로 확인하세요. {first}")
    active = [u for u in data["upgrades"] if u.get("status") != "cut"]
    missing = [u["id"] for u in active if u.get("power") is None]
    if missing:
        raise ConfigError("power가 없는 강화는 시뮬레이션할 수 없습니다: " + ", ".join(missing))
    ups = [{"id": u["id"], "cost": u["cost"], "power": u["power"], "requires": list(u.get("requires") or [])} for u in active]
    info = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return ups, info


def normalize(cfg: dict, base_dir: Path | None = None) -> dict:
    """설정을 검사하고 기본값을 채운다. upgrades_file의 상대 경로는 base_dir(설정 파일 폴더) 기준이다."""
    if not isinstance(cfg, dict):
        raise ConfigError("설정 최상위는 객체여야 합니다.")
    out = {
        "seed": _req(cfg, "seed", int),
        "trials": _req(cfg, "trials", int),
        "max_runs": _req(cfg, "max_runs", int),
        "rooms": _req(cfg, "rooms", int),
    }
    for k in ("trials", "max_runs", "rooms"):
        if out[k] < 1:
            raise ConfigError(f"{k}는 1 이상이어야 합니다.")

    d = _req(cfg, "difficulty", dict)
    growth = d.get("growth", "linear")
    if growth not in ("linear", "exponential"):
        raise ConfigError("difficulty.growth는 linear 또는 exponential입니다.")
    out["difficulty"] = {"base": _req(d, "base", float, "difficulty."), "rate": _req(d, "rate", float, "difficulty."), "growth": growth}

    p = _req(cfg, "player", dict)
    out["player"] = {
        "base_power": _req(p, "base_power", float, "player."),
        "power_per_room": float(p.get("power_per_room", 0.0)),
        "skill": float(p.get("skill", 0.0)),
        "skill_spread": float(p.get("skill_spread", 0.0)),
    }
    if out["player"]["skill_spread"] < 0:
        raise ConfigError("player.skill_spread는 0 이상이어야 합니다.")

    s = _req(cfg, "survival", dict)
    floor_, ceil_ = float(s.get("floor", 0.0)), float(s.get("ceiling", 1.0))
    if not (0.0 <= floor_ <= ceil_ <= 1.0):
        raise ConfigError("survival은 0 <= floor <= ceiling <= 1 이어야 합니다.")
    out["survival"] = {"slope": _req(s, "slope", float, "survival."), "floor": floor_, "ceiling": ceil_}

    c = _req(cfg, "currency", dict)
    bonus = c.get("bonus_rooms", {}) or {}
    try:
        bonus = {int(k): float(v) for k, v in bonus.items()}
    except (TypeError, ValueError, AttributeError):
        raise ConfigError("currency.bonus_rooms는 {방 번호: 재화} 형태여야 합니다.")
    keep = float(c.get("keep_on_death", 1.0))
    if not 0.0 <= keep <= 1.0:
        raise ConfigError("currency.keep_on_death는 0~1 사이여야 합니다.")
    out["currency"] = {"per_room": _req(c, "per_room", float, "currency."), "bonus_rooms": bonus, "keep_on_death": keep}

    if "upgrades_file" in cfg:
        if "upgrades" in cfg:
            raise ConfigError("upgrades와 upgrades_file 중 하나만 쓰세요. 단일 원본은 upgrades_file입니다.")
        ups, out["upgrades_file"] = _load_upgrades_file(cfg["upgrades_file"], base_dir)
    else:
        ups = cfg.get("upgrades", []) or []
    if not isinstance(ups, list):
        raise ConfigError("upgrades는 배열이어야 합니다.")
    seen: dict = {}
    for n, u in enumerate(ups):
        where = f"upgrades[{n}]."
        if not isinstance(u, dict):
            raise ConfigError(f"upgrades[{n}]는 객체여야 합니다.")
        uid = _req(u, "id", str, where)
        if uid in seen:
            raise ConfigError(f"강화 id가 중복됩니다: {uid}")
        cost = _req(u, "cost", float, where)
        if cost < 0:
            raise ConfigError(f"{where}cost는 0 이상이어야 합니다.")
        seen[uid] = {"id": uid, "cost": cost, "power": float(u.get("power", 0.0)), "requires": list(u.get("requires", []) or [])}
    for uid, u in seen.items():
        for r in u["requires"]:
            if r not in seen:
                raise ConfigError(f"강화 '{uid}'의 선행 조건 '{r}'가 없습니다.")
    _check_cycles(seen)
    out["upgrades"] = list(seen.values())

    policy = cfg.get("purchase_policy", "listed_order")
    if policy not in ("listed_order", "cheapest_first"):
        raise ConfigError("purchase_policy는 listed_order 또는 cheapest_first입니다.")
    out["purchase_policy"] = policy

    ms = cfg.get("milestones", []) or []
    out["milestones"] = []
    for n, m in enumerate(ms):
        mid = _req(m, "id", str, f"milestones[{n}].")
        room = _req(m, "clear_room", int, f"milestones[{n}].")
        if not 1 <= room <= out["rooms"]:
            raise ConfigError(f"마일스톤 '{mid}'의 clear_room은 1~{out['rooms']} 사이여야 합니다.")
        out["milestones"].append({"id": mid, "clear_room": room})
    return out


def _check_cycles(ups: dict) -> None:
    state: dict = {}

    def visit(uid: str, path: list) -> None:
        if state.get(uid) == 1:
            raise ConfigError("강화 선행 조건에 순환이 있습니다: " + " → ".join(path + [uid]))
        if state.get(uid) == 2:
            return
        state[uid] = 1
        for r in ups[uid]["requires"]:
            visit(r, path + [uid])
        state[uid] = 2

    for uid in ups:
        visit(uid, [])


def difficulty(cfg: dict, room: int) -> float:
    d = cfg["difficulty"]
    if d["growth"] == "linear":
        return d["base"] + d["rate"] * (room - 1)
    return d["base"] * (1.0 + d["rate"]) ** (room - 1)


def survival_probability(cfg: dict, power: float, room: int, skill: float) -> float:
    s = cfg["survival"]
    x = s["slope"] * (power - difficulty(cfg, room)) + skill
    x = max(-60.0, min(60.0, x))
    p = 1.0 / (1.0 + math.exp(-x))
    return min(s["ceiling"], max(s["floor"], p))


def play_run(cfg: dict, rng: random.Random, meta_power: float, skill: float) -> tuple[int, float]:
    """한 런을 진행해 (통과한 방 수, 얻은 재화)를 돌려준다."""
    power = cfg["player"]["base_power"] + meta_power
    cur = cfg["currency"]
    earned, cleared = 0.0, 0
    for room in range(1, cfg["rooms"] + 1):
        if rng.random() >= survival_probability(cfg, power, room, skill):
            return cleared, earned * cur["keep_on_death"]
        cleared = room
        earned += cur["per_room"] + cur["bonus_rooms"].get(room, 0.0)
        power += cfg["player"]["power_per_room"]
    return cleared, earned


def buy(cfg: dict, bank: float, owned: set) -> tuple[float, list]:
    bought = []
    ups = cfg["upgrades"]
    while True:
        available = [u for u in ups if u["id"] not in owned and all(r in owned for r in u["requires"])]
        if not available:
            break
        if cfg["purchase_policy"] == "listed_order":
            pick = available[0]
            if pick["cost"] > bank:
                break
        else:
            affordable = [u for u in available if u["cost"] <= bank]
            if not affordable:
                break
            pick = min(affordable, key=lambda u: (u["cost"], ups.index(u)))
        bank -= pick["cost"]
        owned.add(pick["id"])
        bought.append(pick["id"])
    return bank, bought


def simulate_trial(cfg: dict, trial: int) -> dict:
    rng = random.Random(cfg["seed"] * 1_000_003 + trial)
    skill = cfg["player"]["skill"]
    if cfg["player"]["skill_spread"] > 0:
        skill = rng.gauss(skill, cfg["player"]["skill_spread"])
    power_of = {u["id"]: u["power"] for u in cfg["upgrades"]}
    owned: set = set()
    bank, best = 0.0, 0
    first_run_for_milestone: dict = {}
    purchase_run: dict = {}
    depths, banks, meta_powers = [], [], []
    stall, longest_stall = 0, 0
    for run in range(1, cfg["max_runs"] + 1):
        meta = sum(power_of[u] for u in owned)
        depth, earned = play_run(cfg, rng, meta, skill)
        bank += earned
        bank, bought = buy(cfg, bank, owned)
        for uid in bought:
            purchase_run[uid] = run
        for m in cfg["milestones"]:
            if m["id"] not in first_run_for_milestone and depth >= m["clear_room"]:
                first_run_for_milestone[m["id"]] = run
        progressed = bool(bought) or depth > best
        best = max(best, depth)
        complete = best >= cfg["rooms"] and len(owned) == len(cfg["upgrades"])
        # 더 얻을 것이 남아 있을 때만 정체로 센다. 모두 끝낸 뒤의 런은 정체가 아니다.
        stall = 0 if (progressed or complete) else stall + 1
        longest_stall = max(longest_stall, stall)
        depths.append(depth)
        banks.append(bank)
        meta_powers.append(sum(power_of[u] for u in owned))
    return {
        "skill": skill,
        "milestones": first_run_for_milestone,
        "purchases": purchase_run,
        "depths": depths,
        "banks": banks,
        "meta_powers": meta_powers,
        "longest_stall": longest_stall,
    }


def percentile(values: list, q: float):
    """정렬된 값의 최근접 순위 백분위. 도달하지 못한 경우는 inf로 넣고, 결과가 inf이면 None."""
    if not values:
        return None
    vals = sorted(values)
    idx = min(len(vals) - 1, max(0, math.ceil(q / 100.0 * len(vals)) - 1))
    v = vals[idx]
    return None if v == math.inf else v


def _dist(values: list) -> dict:
    reached = [v for v in values if v != math.inf]
    return {
        "reached_fraction": round(len(reached) / len(values), 4) if values else 0.0,
        "p10": percentile(values, 10),
        "median": percentile(values, 50),
        "p90": percentile(values, 90),
    }


def simulate(cfg: dict) -> dict:
    trials = [simulate_trial(cfg, t) for t in range(cfg["trials"])]
    milestones = {m["id"]: _dist([t["milestones"].get(m["id"], math.inf) for t in trials]) for m in cfg["milestones"]}
    upgrades = {u["id"]: _dist([t["purchases"].get(u["id"], math.inf) for t in trials]) for u in cfg["upgrades"]}
    all_bought = [max(t["purchases"].values()) if len(t["purchases"]) == len(cfg["upgrades"]) and cfg["upgrades"] else math.inf for t in trials]
    curve = []
    for i in range(cfg["max_runs"]):
        curve.append({
            "run": i + 1,
            "median_depth": percentile([t["depths"][i] for t in trials], 50),
            "median_bank": percentile([t["banks"][i] for t in trials], 50),
            "median_meta_power": percentile([t["meta_powers"][i] for t in trials], 50),
        })
    stalls = [t["longest_stall"] for t in trials]
    return {
        "evidence": EVIDENCE_NOTE,
        "seed": cfg["seed"],
        "trials": cfg["trials"],
        "max_runs": cfg["max_runs"],
        "purchase_policy": cfg["purchase_policy"],
        "survival_at_base_power": [
            {"room": r, "difficulty": round(difficulty(cfg, r), 4),
             "p_clear": round(survival_probability(cfg, cfg["player"]["base_power"] + cfg["player"]["power_per_room"] * (r - 1), r, cfg["player"]["skill"]), 4)}
            for r in range(1, cfg["rooms"] + 1)
        ],
        "milestones": milestones,
        "upgrades": upgrades,
        "all_upgrades_bought": _dist(all_bought) if cfg["upgrades"] else None,
        "longest_stall_runs": {"median": percentile(stalls, 50), "p90": percentile(stalls, 90), "max": max(stalls)},
        "curve": curve,
    }


def fmt_dist(d: dict | None) -> str:
    if d is None:
        return "-"
    def f(v):
        return "미도달" if v is None else str(v)
    return f"도달 {d['reached_fraction']:.0%} · 런 p10 {f(d['p10'])} / 중앙 {f(d['median'])} / p90 {f(d['p90'])}"


def run_config(config_path) -> tuple[dict, dict]:
    """설정 파일을 읽어 검사·시뮬레이션하고 (정규화된 설정, 결과)를 돌려준다. 잘못되면 ConfigError."""
    path = Path(config_path)
    try:
        raw = path.read_bytes()
        cfg = normalize(json.loads(raw.decode("utf-8")), path.resolve().parent)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ConfigError(str(exc))
    result = simulate(cfg)
    result["config"] = str(config_path)
    result["config_sha256"] = hashlib.sha256(raw).hexdigest()
    if "upgrades_file" in cfg:
        result["upgrades_file"] = cfg["upgrades_file"]
    return cfg, result
