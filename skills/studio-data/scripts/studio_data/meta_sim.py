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

from . import combat as cb
from . import common as c
from . import growth as gr
from . import upgrades as vu

EVIDENCE_NOTE = (
    "computed: abstract model. Not a difficulty or fun verdict. "
    "Calibrate survival/skill against playtest telemetry before treating outcomes as measured."
)
COMBAT_EVIDENCE_NOTE = (
    "computed: combat model (expected hits and times from the combat data, logistic survival on the time margin). "
    "Not a difficulty or fun verdict. Calibrate survival slope/skill against playtest telemetry before treating outcomes as measured."
)


POLICIES = ("listed_order", "cheapest_first")  # 어떤 설정에서나 쓰는 구매 정책(--compare-policies의 기본)
ECONOMY_POLICY = "economy"                      # 재화 흐름(economy.json)의 구매 계획 순서. economy 연결이 있을 때만
ALL_POLICIES = POLICIES + (ECONOMY_POLICY,)
MODELS = ("abstract", "combat")


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


def _opt_num(d: dict, key: str, default: float, where: str = "") -> float:
    """선택 수치. 없으면 기본값, 있으면 수여야 한다(불리언·문자열·객체는 형식 오류)."""
    v = d.get(key, default)
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        raise ConfigError(f"{where}{key}는 수여야 합니다: {v!r}")
    return float(v)


def _numbers(v, where: str) -> dict:
    if v is None:
        return {}
    if not (isinstance(v, dict) and all(isinstance(k, str) and isinstance(x, (int, float)) and not isinstance(x, bool) for k, x in v.items())):
        raise ConfigError(f"{where}는 {{이름: 수}}여야 합니다.")
    return {k: float(x) for k, x in v.items()}


def _path(cfg: dict, key: str, base_dir: Path | None, where: str = "") -> Path:
    name = cfg.get(key)
    if not isinstance(name, str) or not name.strip():
        raise ConfigError(f"{where}{key}는 파일 경로 문자열이어야 합니다.")
    path = Path(name)
    return path if path.is_absolute() else (base_dir or Path.cwd()) / path


def _load_upgrades_file(name, base_dir: Path | None, need_power: bool = True) -> tuple[list, dict]:
    """영구 강화 데이터 파일(단일 원본)을 읽어 시뮬레이터용 목록으로 바꾼다. 삭제(cut) 항목은 뺀다.
    need_power: 추상 모델은 power가 있어야 한다. 전투 계산 모델은 power 대신 stats를 쓴다."""
    path = _path({"upgrades_file": name}, "upgrades_file", base_dir)
    try:
        data = vu.load(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ConfigError(f"upgrades_file을 읽을 수 없습니다 ({path}): {exc}")
    report = vu.validate(data)
    if report["errors"]:
        first = "; ".join(f"{e['where']}: {e['message']}" for e in report["errors"][:3])
        raise ConfigError(f"강화 데이터에 오류가 있습니다 ({path}). `studio.py check`로 확인하세요. {first}")
    active = [u for u in data["upgrades"] if u.get("status") != "cut"]
    missing = [u["id"] for u in active if u.get("power") is None]
    if need_power and missing:
        raise ConfigError("power가 없는 강화는 시뮬레이션할 수 없습니다: " + ", ".join(missing))
    ups = [{"id": u["id"], "cost": u["cost"], "power": u.get("power") or 0.0, "requires": list(u.get("requires") or []),
            "stats": dict(u.get("stats") or {})} for u in active]
    info = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return ups, info


def normalize(cfg: dict, base_dir: Path | None = None) -> dict:
    """설정을 검사하고 기본값을 채운다. 상대 경로는 base_dir(설정 파일 폴더) 기준이다.
    전투 계산 모델(model: combat)은 여기서 파일 경로만 확인한다. 그 데이터를 읽고 계산을 준비하는 것은 attach다."""
    if not isinstance(cfg, dict):
        raise ConfigError("설정 최상위는 객체여야 합니다.")
    model = cfg.get("model", "abstract")
    if model not in MODELS:
        raise ConfigError(f"model은 {' 또는 '.join(MODELS)}입니다: {model!r}{c.did_you_mean(str(model), MODELS)}")
    _check_keys(cfg, model)
    out = {"model": model, "seed": _req(cfg, "seed", int), "trials": _req(cfg, "trials", int), "max_runs": _req(cfg, "max_runs", int)}
    for k in ("trials", "max_runs"):
        if out[k] < 1:
            raise ConfigError(f"{k}는 1 이상이어야 합니다.")
    if model == "abstract":
        _abstract_part(cfg, out)
    else:
        _combat_part(cfg, out, base_dir)

    p = cfg.get("player", {}) if model == "combat" else _req(cfg, "player", dict)
    if not isinstance(p, dict):
        raise ConfigError("player는 객체여야 합니다.")
    out["player"] = {**out.get("player", {}), "skill": _opt_num(p, "skill", 0.0, "player."),
                     "skill_spread": _opt_num(p, "skill_spread", 0.0, "player.")}
    if out["player"]["skill_spread"] < 0:
        raise ConfigError("player.skill_spread는 0 이상이어야 합니다.")

    s = _req(cfg, "survival", dict)
    floor_, ceil_ = _opt_num(s, "floor", 0.0, "survival."), _opt_num(s, "ceiling", 1.0, "survival.")
    if not (0.0 <= floor_ <= ceil_ <= 1.0):
        raise ConfigError("survival은 0 <= floor <= ceiling <= 1 이어야 합니다.")
    out["survival"] = {"slope": _req(s, "slope", float, "survival."), "floor": floor_, "ceiling": ceil_}
    if model == "combat":
        out["survival"]["even_margin"] = _even_margin(s.get("even_margin", 1.0))
    elif "even_margin" in s:
        raise ConfigError("survival.even_margin은 전투 계산 모델(model: combat)에서만 씁니다.")

    econ = cfg.get("economy")
    if econ is not None:
        if not (isinstance(econ, dict) and isinstance(econ.get("currency"), str)):
            raise ConfigError("economy는 {file: 재화 흐름 파일 경로, currency: 판 사이 재화 id}입니다.")
        out["economy"] = {"file": _path(econ, "file", base_dir, "economy."), "currency": econ["currency"]}

    if "upgrades_file" in cfg:
        if "upgrades" in cfg:
            raise ConfigError("upgrades와 upgrades_file 중 하나만 쓰세요. 단일 원본은 upgrades_file입니다.")
        ups, out["upgrades_file"] = _load_upgrades_file(cfg["upgrades_file"], base_dir, need_power=model == "abstract")
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
        reqs = u.get("requires", []) or []
        if not (isinstance(reqs, list) and all(isinstance(r, str) for r in reqs)):
            raise ConfigError(f"{where}requires는 강화 id 배열입니다.")
        seen[uid] = {"id": uid, "cost": cost, "power": _opt_num(u, "power", 0.0, where), "requires": list(reqs),
                     "stats": _numbers(u.get("stats"), where + "stats")}
    for uid, u in seen.items():
        for r in u["requires"]:
            if r not in seen:
                raise ConfigError(f"강화 '{uid}'의 선행 조건 '{r}'가 없습니다.")
    _check_cycles(seen)
    out["upgrades"] = list(seen.values())
    if out.get("stat_effects"):
        stats = {k for u in seen.values() for k in u["stats"]}
        for name in out["stat_effects"]:
            if name not in stats:  # 오타면 가정한 효과가 조용히 사라진다
                raise ConfigError(f"stat_effects의 스탯 {name}을 가진 영구 강화가 없습니다.{c.did_you_mean(name, stats)} "
                                  f"강화 스탯: {', '.join(sorted(stats)) or '없음'}")

    policy = cfg.get("purchase_policy", "listed_order")
    if policy not in ALL_POLICIES:
        raise ConfigError(f"purchase_policy는 {', '.join(ALL_POLICIES)} 중 하나입니다: {policy!r}")
    if policy == ECONOMY_POLICY and "economy" not in out:
        raise ConfigError("purchase_policy economy(재화 흐름의 구매 계획 순서)는 economy {file, currency} 연결이 필요합니다.")
    out["purchase_policy"] = policy

    ms = cfg.get("milestones", []) or []
    if not isinstance(ms, list):
        raise ConfigError("milestones는 배열이어야 합니다.")
    out["milestones"] = []
    for n, m in enumerate(ms):
        if not isinstance(m, dict):
            raise ConfigError(f"milestones[{n}]는 객체여야 합니다.")
        mid = _req(m, "id", str, f"milestones[{n}].")
        if model == "abstract":
            room = _req(m, "clear_room", int, f"milestones[{n}].")
            if not 1 <= room <= out["rooms"]:
                raise ConfigError(f"마일스톤 '{mid}'의 clear_room은 1~{out['rooms']} 사이여야 합니다.")
            out["milestones"].append({"id": mid, "clear_room": room})
        else:
            out["milestones"].append({"id": mid, "clear_stage": _req(m, "clear_stage", str, f"milestones[{n}].")})
    return out


_KEYS = {
    "abstract": {"model", "seed", "trials", "max_runs", "rooms", "difficulty", "player", "survival", "currency", "economy",
                 "upgrades_file", "upgrades", "purchase_policy", "milestones"},
    "combat": {"model", "seed", "trials", "max_runs", "combat_file", "stages", "growth_file", "build", "survival", "player", "currency",
               "economy", "stat_effects", "upgrades_file", "upgrades", "purchase_policy", "milestones"},
}
_SUB_KEYS = {
    ("abstract", "player"): {"base_power", "power_per_room", "skill", "skill_spread"}, ("combat", "player"): {"skill", "skill_spread"},
    ("abstract", "survival"): {"slope", "floor", "ceiling"}, ("combat", "survival"): {"slope", "even_margin", "floor", "ceiling"},
    ("abstract", "currency"): {"per_room", "bonus_rooms", "keep_on_death"}, ("combat", "currency"): {"per_stage", "keep_on_death"},
    ("abstract", "difficulty"): {"growth", "base", "rate"}, ("abstract", "economy"): {"file", "currency"}, ("combat", "economy"): {"file", "currency"},
    ("abstract", "milestones"): {"id", "clear_room"}, ("combat", "milestones"): {"id", "clear_stage"},
}
EFFECTS = ("income_pct", "levels")  # 전투 밖 스탯의 효과: 판 사이 재화 수입 +비율, 판 안 레벨업 +횟수(스탯 1당)


def _known_keys(d: dict, allowed: set, where: str) -> None:
    """모르는 키는 오타일 가능성이 크다(조용히 기본값으로 돌면 결과가 통째로 달라진다). _로 시작하는 키(_note 등)는 메모로 둔다."""
    for k in d:
        if isinstance(k, str) and k.startswith("_"):
            continue
        if k not in allowed:
            raise ConfigError(f"{where}알 수 없는 키 '{k}'.{c.did_you_mean(str(k), allowed)} 쓸 수 있는 키: {', '.join(sorted(allowed))}")


def _check_keys(cfg: dict, model: str) -> None:
    _known_keys(cfg, _KEYS[model], "")
    for (m, key), allowed in _SUB_KEYS.items():
        if m != model or key not in cfg:
            continue
        items = cfg[key] if key == "milestones" and isinstance(cfg[key], list) else [cfg[key]]
        for n, d in enumerate(items):
            if isinstance(d, dict):
                _known_keys(d, allowed, f"{key}[{n}]." if key == "milestones" else f"{key}.")


def _stat_effects(v, has_growth: bool) -> dict:
    """{스탯 이름: {income_pct: 수, levels: 수}}. 전투 역할에 연결되지 않은 강화 스탯(수집·숙성 등)을 시뮬레이터에 잇는 가정."""
    if v is None:
        return {}
    if not isinstance(v, dict):
        raise ConfigError("stat_effects는 {스탯 이름: {income_pct, levels}}입니다.")
    out = {}
    for stat, eff in v.items():
        where = f"stat_effects.{stat}."
        if not (isinstance(eff, dict) and eff):
            raise ConfigError(f"{where[:-1]}는 {{{', '.join(EFFECTS)}: 스탯 1당 값}}입니다.")
        _known_keys(eff, set(EFFECTS), where)
        out[stat] = {k: _opt_num(eff, k, 0.0, where) for k in eff}
        if "levels" in out[stat] and not has_growth:
            raise ConfigError(f"{where}levels(판 안 레벨업)는 growth_file과 build가 있어야 씁니다.")
    return out


def _even_margin(v):
    """수 하나(모든 등급) 또는 {등급: 수}(없는 등급은 1). 모두 0보다 커야 한다."""
    where = "survival.even_margin"
    if isinstance(v, dict):
        out = {}
        for rank, x in v.items():
            if rank not in cb.RANKS:
                raise ConfigError(f"{where}의 등급은 {', '.join(cb.RANKS)} 중 하나입니다: {rank!r}{c.did_you_mean(str(rank), cb.RANKS)}")
            out[rank] = _opt_num(v, rank, 1.0, where + ".")
        values = list(out.values())
    else:
        out = _opt_num({"even_margin": v}, "even_margin", 1.0, "survival.")
        values = [out]
    if any(x <= 0 for x in values):
        raise ConfigError(f"{where}은 0보다 커야 합니다(평균 실력이 절반의 확률로 넘기는 여유).")
    return out


def _abstract_part(cfg: dict, out: dict) -> None:
    out["rooms"] = _req(cfg, "rooms", int)
    if out["rooms"] < 1:
        raise ConfigError("rooms는 1 이상이어야 합니다.")
    d = _req(cfg, "difficulty", dict)
    growth = d.get("growth", "linear")
    if growth not in ("linear", "exponential"):
        raise ConfigError("difficulty.growth는 linear 또는 exponential입니다.")
    out["difficulty"] = {"base": _req(d, "base", float, "difficulty."), "rate": _req(d, "rate", float, "difficulty."), "growth": growth}
    p = _req(cfg, "player", dict)
    out["player"] = {"base_power": _req(p, "base_power", float, "player."), "power_per_room": _opt_num(p, "power_per_room", 0.0, "player.")}
    c = _req(cfg, "currency", dict)
    bonus = c.get("bonus_rooms", {}) or {}
    try:
        bonus = {int(k): float(v) for k, v in bonus.items()}
    except (TypeError, ValueError, AttributeError):
        raise ConfigError("currency.bonus_rooms는 {방 번호: 재화} 형태여야 합니다.")
    keep = _opt_num(c, "keep_on_death", 1.0, "currency.")
    if not 0.0 <= keep <= 1.0:
        raise ConfigError("currency.keep_on_death는 0~1 사이여야 합니다.")
    out["currency"] = {"per_room": _req(c, "per_room", float, "currency."), "bonus_rooms": bonus, "keep_on_death": keep}


def _combat_part(cfg: dict, out: dict, base_dir: Path | None) -> None:
    """전투 계산 모델: 방·난이도 대신 전투 계산의 단계를 순서대로 지난다."""
    for key in ("rooms", "difficulty"):
        if key in cfg:
            raise ConfigError(f"전투 계산 모델(model: combat)에는 {key}를 쓰지 않습니다. 판은 combat_file의 단계를 순서대로 지납니다.")
    out["combat_file"] = _path(cfg, "combat_file", base_dir)
    stages = cfg.get("stages")
    if stages is not None and not (isinstance(stages, list) and stages and all(isinstance(x, str) for x in stages)):
        raise ConfigError("stages는 판에서 지나는 전투 단계 id 배열입니다(없으면 전투 계산의 활성 단계 전부).")
    out["stages"] = stages
    if "growth_file" in cfg or "build" in cfg:
        if "growth_file" not in cfg:
            raise ConfigError("build(판 안 성장의 빌드 id)를 쓰면 growth_file이 필요합니다(판 안 성장 파일 경로).")
        out["growth_file"] = _path(cfg, "growth_file", base_dir)
        if not isinstance(cfg.get("build"), str):
            raise ConfigError("growth_file을 쓰면 build(판 안 성장의 빌드 id)가 필요합니다.")
        out["build"] = cfg["build"]
    out["stat_effects"] = _stat_effects(cfg.get("stat_effects"), "growth_file" in out)
    c = cfg.get("currency", {})
    if not isinstance(c, dict):
        raise ConfigError("currency는 객체여야 합니다.")
    keep = _opt_num(c, "keep_on_death", 1.0, "currency.")
    if not 0.0 <= keep <= 1.0:
        raise ConfigError("currency.keep_on_death는 0~1 사이여야 합니다.")
    out["currency"] = {"keep_on_death": keep}
    if "per_stage" in c:
        out["currency"]["per_stage"] = _numbers(c["per_stage"], "currency.per_stage")
    elif not isinstance(cfg.get("economy"), dict):
        raise ConfigError("전투 계산 모델은 단계별 재화가 필요합니다: currency.per_stage {단계 id: 재화}, 또는 economy {file, currency} 연결.")


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
        if cfg["purchase_policy"] == ECONOMY_POLICY:
            # 재화 흐름의 구매 계획 순서대로. 다음 것을 살 수 없으면(재화·선행 조건) 그 뒤도 사지 않고 저축한다
            nxt = next((uid for uid in cfg["economy_order"] if uid not in owned), None)
            pick = next((u for u in available if u["id"] == nxt), None)
            if pick is None or pick["cost"] > bank:
                break
        elif cfg["purchase_policy"] == "listed_order":
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


def targets(cfg: dict) -> list[str]:
    """다 사면 '모두 샀다'로 보는 강화. 재화 흐름 정책이면 그 계획에 있는 강화만(계획에 없는 강화는 사지 않는다)."""
    if cfg["purchase_policy"] == ECONOMY_POLICY:
        return list(cfg["economy_order"])
    return [u["id"] for u in cfg["upgrades"]]


def simulate_trial(cfg: dict, trial: int, cache: dict | None = None) -> dict:
    rng = random.Random(cfg["seed"] * 1_000_003 + trial)
    skill = cfg["player"]["skill"]
    if cfg["player"]["skill_spread"] > 0:
        skill = rng.gauss(skill, cfg["player"]["skill_spread"])
    power_of = {u["id"]: u["power"] for u in cfg["upgrades"]}
    combat = cfg["model"] == "combat"
    goal = set(targets(cfg))
    cache = {} if cache is None else cache
    owned: set = set()
    bank, best = 0.0, 0
    first_run_for_milestone: dict = {}
    purchase_run: dict = {}
    depths, banks, meta_powers = [], [], []
    stall, longest_stall = 0, 0
    for run in range(1, cfg["max_runs"] + 1):
        if combat:
            depth, earned = play_combat_run(cfg, rng, owned, skill, cache)
        else:
            depth, earned = play_run(cfg, rng, sum(power_of[u] for u in owned), skill)
        bank += earned
        bank, bought = buy(cfg, bank, owned)
        for uid in bought:
            purchase_run[uid] = run
        for m in cfg["milestones"]:
            if m["id"] not in first_run_for_milestone and depth >= m["clear_room"]:
                first_run_for_milestone[m["id"]] = run
        progressed = bool(bought) or depth > best
        best = max(best, depth)
        complete = best >= cfg["rooms"] and goal <= owned
        # 더 얻을 것이 남아 있을 때만 정체로 센다. 모두 끝낸 뒤의 런은 정체가 아니다.
        stall = 0 if (progressed or complete) else stall + 1
        longest_stall = max(longest_stall, stall)
        depths.append(depth)
        banks.append(bank)
        meta_powers.append(len(owned) if combat else sum(power_of[u] for u in owned))
    return {
        "skill": skill,
        "milestones": first_run_for_milestone,
        "purchases": purchase_run,
        "depths": depths,
        "banks": banks,
        "meta_powers": meta_powers,
        "longest_stall": longest_stall,
    }


# ---------- 전투 계산 모델 ----------
def row_margin(r: dict) -> float:
    """적 하나와의 여유 = 버티는 시간 ÷ 처치 시간. 어느 쪽이든 공격 속도가 없으면 버티는 타수 ÷ 처치 타수(양쪽 공격 빈도가 같다고 보는 셈).
    피해를 줄 수 없으면 0, 피해를 받지 않으면 무한대."""
    if r["hits_to_kill"] is None:
        return 0.0
    if r["hits_to_die"] is None:
        return math.inf
    if r["time_to_kill"] is not None and r["time_to_die"] is not None:
        return r["time_to_die"] / r["time_to_kill"]
    return r["hits_to_die"] / r["hits_to_kill"]


def _reference(even, rank) -> float:
    return even.get(rank, 1.0) if isinstance(even, dict) else even


def stage_limit(rows: list[dict], even=1.0) -> tuple[float, dict | None]:
    """(기준 대비 여유, 그 단계를 정한 적의 행). 적마다 여유 ÷ 그 등급의 기준(even_margin)을 내고 가장 작은 적이 단계를 정한다."""
    worst, who = math.inf, None
    for r in rows:
        m = row_margin(r) / _reference(even, r.get("rank"))
        if who is None or m < worst:
            worst, who = m, r
    return worst, who


def stage_margin(rows: list[dict], even=1.0) -> float:
    """단계의 기준 대비 여유(stage_limit의 값). even이 1이면 가장 어려운 적의 여유 그대로."""
    return stage_limit(rows, even)[0]


def combat_survival(cfg: dict, relative: float, skill: float) -> float:
    """단계를 넘길 확률 = clamp(sigmoid(slope × ln(기준 대비 여유) + skill), floor, ceiling). 기준 대비 여유 = 여유 ÷ even_margin(stage_limit).
    even_margin(기본 1, 등급별로 줄 수 있음)은 평균 실력(skill 0)의 플레이어가 절반의 확률로 넘기는 여유다. 피하며 싸우는 액션 게임은
    기대값 여유가 1보다 훨씬 작아도 넘기므로(보스는 특히) 1보다 작게 둔다. slope·skill과 함께 가정이며 플레이 기록으로 보정한다."""
    s = cfg["survival"]
    if relative <= 0:
        p = 0.0
    elif relative == math.inf:
        p = 1.0
    else:
        x = max(-60.0, min(60.0, s["slope"] * math.log(relative) + skill))
        p = 1.0 / (1.0 + math.exp(-x))
    return min(s["ceiling"], max(s["floor"], p))


def _entry(entries: list, path: Path, kind: str, label: str, currency: str | None = None) -> dict:
    """함께 읽은 데이터 중 설정이 가리키는 파일. 없거나, 읽지 못했거나, 오류·미확인이 있으면 ConfigError.
    currency를 주면(재화 흐름) 그 재화에 닿지 않는 미확인은 허용한다(예: 골드로 사는 합성의 데이터가 없음)."""
    found = next((d for d in entries if Path(d["path"]).resolve() == path.resolve()), None)
    if found is None:
        raise ConfigError(f"{label} 파일을 찾지 못했습니다: {path}")
    if not found["ok"]:
        raise ConfigError(f"{label} 파일을 읽지 못했습니다({path}): {found.get('error')}")
    if found["kind"] != kind:
        raise ConfigError(f"{label} 파일이 아닙니다({path}): 최상위 {kind}가 필요합니다.")
    r = found["report"]
    if currency is not None and not r["errors"] and r.get("unchecked"):
        if currency in r.get("unchecked_currencies", []):
            raise ConfigError(f"{label}({path})의 {currency}에 함께 읽지 못한 데이터 때문에 계산하지 못한 수입·구매가 있습니다"
                              f"({', '.join(r.get('unchecked_kinds', []))}). `studio.py check`로 먼저 고치세요.")
        return found
    if r["errors"] or r.get("unchecked"):
        first = "; ".join(f"{e['where']}: {e['message']}" for e in r["errors"][:2])
        raise ConfigError(f"{label}({path})에 오류 {len(r['errors'])}건·미확인 {r.get('unchecked', 0)}건이 있습니다"
                          + (f"({first})" if first else "") + ". `studio.py check`로 먼저 고치세요(틀린 데이터로 시뮬레이션하지 않습니다).")
    return found


def attach(cfg: dict, base_dir: Path | None = None) -> dict:
    """전투 계산 모델과 재화 흐름 연결(economy)이 쓰는 데이터를 함께 읽어 계산을 준비한다. 추상 모델이고 연결이 없으면 그대로.
    데이터는 설정 파일 폴더와 설정이 가리키는 파일의 폴더에서 check와 같은 규칙으로 읽고 검사한다."""
    if cfg["model"] != "combat" and "economy" not in cfg:
        return cfg
    from . import datasets  # datasets → economy → meta_sim 순으로 불러오므로 여기서 읽는다
    files = [cfg.get("combat_file"), cfg.get("growth_file"), (cfg.get("economy") or {}).get("file")]
    folders = sorted({str(base_dir or Path.cwd())} | {str(f.parent) for f in files if f})
    entries = datasets.collect([Path(x) for x in folders])
    ups = {u["id"]: u for u in cfg["upgrades"]}
    out = dict(cfg)
    used = ("combat", "growth", "economy", "items", "upgrades", "enemies", "crafting") if cfg["model"] == "combat" else ("economy",)
    # 결과를 인용할 때 어느 데이터에서 나왔는지 확인할 수 있게, 함께 읽어 계산에 쓴 파일의 경로와 해시를 남긴다
    out["inputs"] = [{"path": d["path"], "sha256": hashlib.sha256(Path(d["path"]).read_bytes()).hexdigest()}
                     for d in entries if d["ok"] and d["kind"] in used]
    out["milestones"] = [dict(m) for m in cfg["milestones"]]  # 단계 위치를 적어 넣으므로 넘겨받은 설정을 바꾸지 않게 복사한다
    if "economy" in cfg:
        need_income = cfg["model"] == "combat" and "per_stage" not in cfg["currency"]  # 추상 모델은 구매 순서만 쓴다
        _attach_economy(out, _entry(entries, cfg["economy"]["file"], "economy", "재화 흐름", cfg["economy"]["currency"]), ups, need_income)
    if cfg["model"] == "combat":
        _attach_combat(out, entries, ups)
    return out


def _attach_economy(cfg: dict, entry: dict, ups: dict, need_income: bool) -> None:
    econ, r = cfg["economy"], entry["report"]
    cur = econ["currency"]
    if cur not in r["currencies"]:
        raise ConfigError(f"재화 흐름에 없는 재화입니다: {cur}.{c.did_you_mean(cur, r['currencies'])}")
    if not r["currencies"][cur]["carry"]:
        raise ConfigError(f"economy.currency {cur}는 판 사이 재화(carry: true)여야 합니다. 메타 성장은 판 사이에 남는 재화로 산다.")
    raw = {p.get("id"): p for p in entry["data"].get("purchases") or [] if isinstance(p, dict)}
    order: list = []
    for row in r["purchases"]:
        uid = ((raw.get(row["id"]) or {}).get("price") or {}).get("upgrade")
        if row["currency"] == cur and isinstance(uid, str) and uid not in order:
            order.append(uid)
    unknown = [u for u in order if u not in ups]
    if unknown:
        raise ConfigError(f"재화 흐름의 구매 계획에 시뮬레이터의 강화 목록에 없는 강화가 있습니다: {', '.join(unknown)}. 같은 upgrades 파일을 쓰는지 확인하세요.")
    cfg["economy_order"] = order
    if not need_income:
        return
    stages = {s.get("id"): s for s in entry["data"].get("stages") or [] if isinstance(s, dict)}
    income: dict = {}
    for st in r["stages"]:
        amount = st["income"].get(cur, 0)
        if not amount:
            continue
        link = stages.get(st["id"], {}).get("combat_stage")
        if not isinstance(link, str):
            raise ConfigError(f"재화 흐름 단계 {st['id']}에 {cur} 수입이 있는데 combat_stage(같은 구간의 전투 단계)가 없습니다. "
                              "전투 계산 모델은 전투 단계마다 수입을 받습니다.")
        income[link] = income.get(link, 0.0) + amount
    cfg["economy_income"] = income


def _attach_combat(cfg: dict, entries: list, ups: dict) -> None:
    from . import datasets
    combat_entry = _entry(entries, cfg["combat_file"], "combat", "전투 계산")
    refs = datasets.indexes(entries)
    crafting = next((d["data"] for d in entries if d["ok"] and d["kind"] == "crafting"), None)
    data = json.loads(json.dumps(combat_entry["data"]))
    for s in data["stages"]:
        if isinstance(s, dict) and isinstance(s.get("player"), dict):
            s["player"]["upgrades"] = []  # 단계에 적은 강화 대신 그 판까지 산 영구 강화를 더한다
    prep = cb.prepare(data, crafting=crafting, **refs)
    active = [s["id"] for s in data["stages"] if isinstance(s, dict) and c.is_active(s)]
    stages = cfg["stages"] or active
    for sid in stages:
        if sid not in active:
            raise ConfigError(f"전투 계산에 없거나 삭제된 단계입니다: {sid}{c.did_you_mean(sid, active)}")
        if prep is None or sid not in prep["stages"]:
            raise ConfigError(f"전투 단계 {sid}를 계산할 수 없습니다(계산할 적이 없음 등). 전투 계산 결과를 확인하세요.")
    index = {sid: n for n, sid in enumerate(stages, start=1)}
    for m in cfg["milestones"]:
        if m["clear_stage"] in active and m["clear_stage"] not in index:
            raise ConfigError(f"마일스톤 {m['id']}의 clear_stage {m['clear_stage']}는 전투 계산에 있지만 이 설정의 stages에서 뺀 단계입니다. "
                              f"stages에 넣거나 마일스톤을 판의 단계({', '.join(stages)})로 바꿉니다.")
        if m["clear_stage"] not in index:
            raise ConfigError(f"마일스톤 {m['id']}의 clear_stage가 판의 단계에 없습니다: {m['clear_stage']}{c.did_you_mean(m['clear_stage'], stages)}")
        m["clear_room"] = index[m["clear_stage"]]
    per_stage = cfg["currency"].get("per_stage")
    income = per_stage if per_stage is not None else cfg.get("economy_income", {})
    extra = [k for k in income if k not in index]
    if extra:
        raise ConfigError(f"판의 단계에 없는 전투 단계에 수입이 있습니다: {', '.join(extra)}. stages나 수입 연결을 확인하세요.")
    growth = None
    if "growth_file" in cfg:
        g = _entry(entries, cfg["growth_file"], "growth", "판 안 성장")["data"]
        settings = gr.read_settings(g, [])
        choices = [ch for ch in gr.check_choices(g.get("choices"), []) if c.is_active(ch)]
        builds = {b["id"]: b for b in gr.check_builds(g.get("builds"), {ch["id"] for ch in choices}, []) if c.is_active(b)}
        build = builds.get(cfg["build"])
        if build is None:
            raise ConfigError(f"판 안 성장에 없거나 삭제된 빌드입니다: {cfg['build']}{c.did_you_mean(cfg['build'], builds)}")
        gains, _ = gr.choice_stats(choices, refs["items"], [], [])
        usable = [dict(ch, stats=gains[ch["id"]]) for ch in choices if ch["id"] in gains]
        own, levels, last = build.get("level_at") or {}, [], 1
        for sid in stages:  # 레벨이 없는 단계는 앞 단계의 레벨을 이어 쓴다
            v = own.get(sid, settings["level_at"].get(sid))
            last = v if v is not None else last
            levels.append(last)
        growth = {"choices": usable, "build": build, "levels": levels, "offers": settings["offers"],
                  "stats": {ch["id"]: ch["stats"] for ch in usable}}
    roles = set(prep["settings"]["roles"]["player"].values())
    doubled = sorted(set(cfg["stat_effects"]) & roles)
    if doubled:
        raise ConfigError(f"stat_effects의 {', '.join(doubled)}는 전투 계산의 역할에 연결된 스탯이라 이미 생존에 들어갑니다. "
                          "전투 밖 효과를 더하면 두 번 계산됩니다. 전투 역할에 연결되지 않은 스탯만 적습니다.")
    known = roles | set(cfg["stat_effects"])
    cfg["rooms"] = len(stages)
    cfg["_combat"] = {"prep": prep, "stages": stages, "income": {sid: float(income.get(sid, 0.0)) for sid in stages},
                      "upgrade_stats": {uid: u["stats"] for uid, u in ups.items()},
                      "growth": growth, "no_effect": [u for u, x in ups.items() if not set(x["stats"]) & known]}
    _check_reachable_stats(cfg)


def _effects(cfg: dict, owned) -> tuple[float, int]:
    """산 강화의 전투 밖 효과: (판 사이 재화 수입 배율, 판 안 레벨업 추가 횟수). stat_effects가 없으면 (1, 0)."""
    eff = cfg.get("stat_effects") or {}
    if not eff:
        return 1.0, 0
    total = gr.stat_bonus(cfg["_combat"]["upgrade_stats"], ((u, 1) for u in owned))
    income = 1.0 + sum(total.get(k, 0) * e.get("income_pct", 0.0) for k, e in eff.items())
    levels = int(math.floor(sum(total.get(k, 0) * e.get("levels", 0.0) for k, e in eff.items()) + 1e-9))
    return max(0.0, income), max(0, levels)


def _stage_margin_for(cfg: dict, sid: str, owned, growth_counts, cache: dict) -> float:
    ctx = cfg["_combat"]
    key = (sid, frozenset(owned), growth_counts)
    if key not in cache:
        bonus = gr.stat_bonus(ctx["upgrade_stats"], ((u, 1) for u in owned))
        if ctx["growth"]:
            bonus = gr.stat_bonus(ctx["growth"]["stats"], growth_counts, bonus)
        rows, problem = cb.evaluate(ctx["prep"], sid, bonus)
        if rows is None:
            picks = ", ".join(f"{ch} {n}회" for ch, n in growth_counts) or "없음"
            raise ConfigError(f"단계 {sid}에서 스탯을 전투 계산에 쓸 수 없는 판이 나왔습니다: {problem}. "
                              f"영구 강화: {', '.join(sorted(owned)) or '없음'} · 판 안 성장 선택: {picks}. "
                              "강화·선택지 수치나 max_picks를 고치세요(판 안 성장 검사는 영구 강화 없이 본다).")
        cache[key] = stage_limit(rows, cfg["survival"]["even_margin"])
    return cache[key][0]


def _growth_counts(cfg: dict, seed: int, trials: int = 1, extra_levels: int = 0) -> list:
    """판 안 성장의 단계별 선택 횟수(시행마다). extra_levels: 전투 밖 강화(stat_effects levels)로 더해지는 레벨업 횟수."""
    g = cfg["_combat"]["growth"]
    if not g:
        return [[()] * len(cfg["_combat"]["stages"])] * trials
    return gr.simulate_trials(g["choices"], g["build"], [lv + extra_levels for lv in g["levels"]], g["offers"], trials, seed)


def _check_reachable_stats(cfg: dict) -> None:
    """살 수 있는 강화(구매 정책의 목표)를 모두 산 상태의 스탯이 계산에 쓸 수 있는 값인지 미리 본다. 판 안 성장 없이 보므로
    결정적이다(비싸서 시뮬레이션에서 닿지 않는 강화도 잡는다). 판 안 성장까지 더한 조합은 판마다 뽑으므로, 쓸 수 없는 판이 나오면
    시뮬레이션이 그 단계·강화·선택을 적어 멈춘다. 일부를 뽑아 미리 보는 검사는 드문 조합을 놓쳐 거짓 안심을 주므로 하지 않는다."""
    owned = targets(cfg)
    for sid in cfg["_combat"]["stages"]:
        _stage_margin_for(cfg, sid, owned, (), {})


def play_combat_run(cfg: dict, rng: random.Random, owned: set, skill: float, cache: dict) -> tuple[int, float]:
    """한 판: 단계를 순서대로 지나며 단계마다 전투 계산의 여유로 넘길지 정한다. (넘긴 단계 수, 얻은 재화)."""
    ctx = cfg["_combat"]
    income, extra = _effects(cfg, owned)
    counts = _growth_counts(cfg, rng.randrange(2 ** 31), 1, extra)[0]  # 판마다 레벨업 선택이 다르다
    earned, cleared = 0.0, 0
    for n, sid in enumerate(ctx["stages"]):
        margin = _stage_margin_for(cfg, sid, owned, counts[n], cache)
        if rng.random() >= combat_survival(cfg, margin, skill):
            return cleared, earned * cfg["currency"]["keep_on_death"]
        cleared = n + 1
        earned += ctx["income"][sid] * income
    return cleared, earned


def combat_overview(cfg: dict) -> dict:
    """단계마다 영구 강화·판 안 성장 없이와 계획한 강화를 모두 사고 판 안 성장(평균)을 더했을 때의 여유와 넘길 확률(평균 실력).
    여유는 그 단계를 정한 적(기준 대비 여유가 가장 작은 적)의 값이고, 그 적과 등급을 함께 낸다."""
    ctx, skill = cfg["_combat"], cfg["player"]["skill"]
    g = ctx["growth"]
    goal = targets(cfg)

    def average(extra_levels: int) -> list:
        out: list = [{} for _ in ctx["stages"]]
        if g:
            runs = _growth_counts(cfg, cfg["seed"], 200, extra_levels)
            for per_stage in runs:
                for n, counts in enumerate(per_stage):
                    for ch, times in counts:
                        out[n][ch] = out[n].get(ch, 0) + times / len(runs)
        return out

    avg, avg_new = average(_effects(cfg, goal)[1]), average(0)
    even = cfg["survival"]["even_margin"]

    def limit(bonus: dict) -> tuple:
        got, _ = cb.evaluate(ctx["prep"], sid, bonus)
        return stage_limit(got, even) if got else (0.0, None)

    rows = []
    for n, sid in enumerate(ctx["stages"]):
        rel_none, who_none = limit({})
        # 첫 판의 새 플레이어: 영구 강화는 없지만 판 안 성장은 있다(성장 설정이 없으면 위와 같다)
        rel_new, who_new = limit(gr.stat_bonus(g["stats"], avg_new[n].items()) if g else {})
        bonus = gr.stat_bonus(ctx["upgrade_stats"], ((u, 1) for u in goal))
        if g:
            bonus = gr.stat_bonus(g["stats"], avg[n].items(), bonus)
        rel_all, who_all = limit(bonus)
        margin = lambda who: _round(row_margin(who)) if who else 0  # noqa: E731
        rows.append({"stage": sid, "decided_by": who_none["enemy"], "rank": who_none.get("rank"),
                     "margin_none": margin(who_none), "p_none": round(combat_survival(cfg, rel_none, skill), 4),
                     "decided_by_growth": who_new["enemy"] if who_new else None,
                     "margin_growth": margin(who_new), "p_growth": round(combat_survival(cfg, rel_new, skill), 4),
                     "decided_by_all": who_all["enemy"] if who_all else None,
                     "margin_all": margin(who_all), "p_all": round(combat_survival(cfg, rel_all, skill), 4)})
    return {"survival_by_stage": rows, "stage_income": {k: _round(v) for k, v in ctx["income"].items()},
            "upgrades_without_combat_effect": ctx["no_effect"],
            "growth_build": cfg.get("build")}


def _round(v: float):
    if v == math.inf:
        return None  # JSON에 무한대를 쓰지 않는다. 피해를 받지 않는 단계
    return int(v) if float(v).is_integer() else round(v, 4)


def full_run_income(cfg: dict) -> float | None:
    """한 판을 끝까지 깼을 때 얻는 메타 재화. 재화 흐름 파일에서 수입을 읽는 설정이면 None(같은 원본이라 비교할 것이 없다)."""
    if cfg["model"] == "abstract":
        cur = cfg["currency"]
        return cur["per_room"] * cfg["rooms"] + sum(v for r, v in cur["bonus_rooms"].items() if 1 <= r <= cfg["rooms"])
    per_stage = cfg["currency"].get("per_stage")
    return None if per_stage is None else sum(per_stage.values())


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
    """전투 계산 모델은 attach를 거친 설정이어야 한다(run_config가 한다)."""
    combat = cfg["model"] == "combat"
    if combat and "_combat" not in cfg:
        raise ConfigError("전투 계산 모델은 attach(설정, 폴더)로 데이터를 읽은 뒤 시뮬레이션합니다.")
    cache: dict = {}
    trials = [simulate_trial(cfg, t, cache) for t in range(cfg["trials"])]
    milestones = {m["id"]: _dist([t["milestones"].get(m["id"], math.inf) for t in trials]) for m in cfg["milestones"]}
    upgrades = {u["id"]: _dist([t["purchases"].get(u["id"], math.inf) for t in trials]) for u in cfg["upgrades"]}
    goal = targets(cfg)
    all_bought = [max(t["purchases"][u] for u in goal) if goal and all(u in t["purchases"] for u in goal) else math.inf for t in trials]
    curve = []
    power_key = "median_upgrades_owned" if combat else "median_meta_power"
    for i in range(cfg["max_runs"]):
        curve.append({
            "run": i + 1,
            "median_depth": percentile([t["depths"][i] for t in trials], 50),
            "median_bank": percentile([t["banks"][i] for t in trials], 50),
            power_key: percentile([t["meta_powers"][i] for t in trials], 50),
        })
    stalls = [t["longest_stall"] for t in trials]
    out = {
        "evidence": COMBAT_EVIDENCE_NOTE if combat else EVIDENCE_NOTE,
        "model": cfg["model"],
        "seed": cfg["seed"],
        "trials": cfg["trials"],
        "max_runs": cfg["max_runs"],
        "purchase_policy": cfg["purchase_policy"],
        "milestones": milestones,
        "upgrades": upgrades,
        "all_upgrades_bought": _dist(all_bought) if goal else None,
        "longest_stall_runs": {"median": percentile(stalls, 50), "p90": percentile(stalls, 90), "max": max(stalls)},
        "curve": curve,
    }
    if combat:
        out.update(combat_overview(cfg))
    else:
        out["survival_at_base_power"] = [
            {"room": r, "difficulty": round(difficulty(cfg, r), 4),
             "p_clear": round(survival_probability(cfg, cfg["player"]["base_power"] + cfg["player"]["power_per_room"] * (r - 1), r, cfg["player"]["skill"]), 4)}
            for r in range(1, cfg["rooms"] + 1)]
    return out


def fmt_dist(d: dict | None) -> str:
    if d is None:
        return "-"
    def f(v):
        return "미도달" if v is None else str(v)
    return f"도달 {d['reached_fraction']:.0%} · 런 p10 {f(d['p10'])} / 중앙 {f(d['median'])} / p90 {f(d['p90'])}"


def _read(config_path, policy: str | None) -> tuple[bytes, dict]:
    path = Path(config_path)
    try:
        raw = path.read_bytes()
        data = json.loads(raw.decode("utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ConfigError(str(exc))
    if policy is not None and isinstance(data, dict):
        data["purchase_policy"] = policy
    return raw, data


def load_config(config_path, policy: str | None = None) -> dict:
    """설정 파일을 읽어 검사만 한다(함께 쓰는 데이터는 읽지 않고 시뮬레이션하지 않는다)."""
    _, data = _read(config_path, policy)
    return normalize(data, Path(config_path).resolve().parent)


def run_config(config_path, policy: str | None = None) -> tuple[dict, dict]:
    """설정 파일을 읽어 검사·시뮬레이션하고 (정규화된 설정, 결과)를 돌려준다. 잘못되면 ConfigError.
    policy를 주면 파일을 고치지 않고 구매 정책만 바꿔 실행한다(결과에 policy_override로 남는다)."""
    path = Path(config_path)
    raw, data = _read(config_path, policy)
    cfg = attach(normalize(data, path.resolve().parent), path.resolve().parent)
    result = simulate(cfg)
    if policy is not None:
        result["policy_override"] = policy
    result["config"] = str(config_path)
    result["config_sha256"] = hashlib.sha256(raw).hexdigest()
    if "upgrades_file" in cfg:
        result["upgrades_file"] = cfg["upgrades_file"]
    if "inputs" in cfg:
        result["inputs"] = cfg["inputs"]
    return cfg, result
