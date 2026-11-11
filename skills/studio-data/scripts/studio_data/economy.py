"""재화 흐름(data/economy.json): 단계마다 들어오는 재화와 구매 계획을 이어 "언제 살 수 있나", "얼마나 남나"를 계산한다.

수입: 단계(구역·레벨·시간 구간)마다 처치 수 × 적 보상, 드랍 횟수 × 드랍을 팔 때의 기대값, 그 밖의 수입.
지출: 구매 계획의 순서대로. 가격은 직접 적거나 아이템 가격, 강화 기대 비용(crafting), 합성 비용, 영구 강화 비용에서 가져온다.
판이 끝나면 사라지는 재화는 판 안의 시점으로, 판 사이에 남는 재화(carry)는 몇 번째 판에 사는지로 본다.
기대값 계산이며 실제 체감이나 재미를 판정하지 않는다. 형식: economy-flow/references/economy-format.md
"""
from __future__ import annotations

import math

from . import combat as cb
from . import common as c
from . import crafting as cr
from . import meta_sim
from .common import add_issue as _err, did_you_mean

PRICE_SOURCES = ("items", "enhance", "recipes", "upgrades")
PURCHASE_TIMINGS = ("any", "stage_end")  # 단계 안 어느 때나 산다 / 단계가 끝날 때만 산다(라운드 사이의 상점)
TOP_FIELDS = {"economy", "stages", "purchases", "note"}
SETTING_FIELDS = {"currencies", "kill_reward", "sell", "prices", "time_unit", "leftover_max", "purchase_timing", "provenance", "note"}
STAGE_FIELDS = {"id", "combat_stage", "duration", "kills", "drops", "income", "name", "intent", "status", "provenance", "acknowledged", "note"}
PURCHASE_FIELDS = {"id", "price", "target", "after", "name", "intent", "status", "provenance", "acknowledged", "note"}
PRICE_KEY = {"item": "items", "enhance": "enhance", "recipe": "recipes", "upgrade": "upgrades"}
INCOME_PARTS = ("kills", "drops", "other")
UNCHECKED_LABEL = {"enemies": "적", "items": "아이템", "upgrades": "영구 강화", "crafting": "강화·합성",
                   "combat": "전투 계산(combat_stage 연결)", "meta": "메타 성장 설정(meta_config)"}
EPS = 1e-9


def _time_hint(after) -> str:
    """after에 시각을 글로 적었을 때의 안내."""
    try:
        float(after if isinstance(after, str) else "글이 아님")
    except ValueError:
        return ""
    return " 시각이면 따옴표 없이 수로 적습니다."


def _known_keys(entry: dict, known: set, where: str, errors: list) -> None:
    """모르는 키는 오류다. 그대로 두면 값이 조용히 빠져 구매 시점이나 길이가 말없이 달라진다. 값 계산은 계속한다."""
    text = c.unknown_keys_text(entry, known)
    if text:
        _err(errors, "schema", where, text)


def _num(v, minimum: float = 0.0, strict: bool = False) -> bool:
    return c.is_number(v) and (v > minimum if strict else v >= minimum)


def _amounts(d, currencies: dict, where: str, label: str, errors: list) -> dict | None:
    """{재화: 0 이상의 양}. 형식이 틀리면 오류를 남기고 None."""
    if d is None:
        return {}
    if not (isinstance(d, dict) and all(isinstance(k, str) and _num(v) for k, v in d.items())):
        _err(errors, "schema", where, f"{c.josa(label, '은는')} {{재화: 0 이상의 수}}여야 합니다.")
        return None
    unknown = [k for k in d if k not in currencies]
    if unknown:
        _err(errors, "schema", where, f"{label}에 없는 재화: {', '.join(unknown)}.{''.join(did_you_mean(k, currencies) for k in unknown)} "
             "economy.currencies에 먼저 적습니다.")
        return None
    return d


def read_settings(data: dict, errors: list) -> dict | None:
    cfg = data.get("economy")
    if not isinstance(cfg, dict):
        _err(errors, "schema", "economy", "economy 객체(currencies, kill_reward, sell, prices)가 필요합니다.")
        return None
    cur = cfg.get("currencies")
    if not (isinstance(cur, dict) and cur and all(isinstance(k, str) and isinstance(v, dict) for k, v in cur.items())):
        _err(errors, "schema", "economy.currencies", "currencies는 {재화 id: {name, carry}}여야 합니다.")
        return None
    ok = True
    kill = cfg.get("kill_reward")
    if kill is not None and kill not in cur:
        _err(errors, "schema", "economy.kill_reward", f"kill_reward는 currencies의 재화여야 합니다: {kill!r}.{did_you_mean(str(kill), cur)}")
        ok = False
    sell = cfg.get("sell")
    if sell is not None and not (isinstance(sell, dict) and sell.get("currency") in cur and _num(sell.get("ratio")) and sell["ratio"] <= 1):
        hint = did_you_mean(str(sell.get("currency")), cur) if isinstance(sell, dict) else ""
        _err(errors, "schema", "economy.sell", f"sell은 {{currency: 재화, ratio: 0~1(가격 중 받는 비율)}}이어야 합니다.{hint}")
        ok = False
    for k, v in cur.items():
        link = v.get("meta_config")
        if link is not None and not (isinstance(link, str) and link.strip() and v.get("carry")):
            _err(errors, "schema", f"economy.currencies.{k}",
                 "meta_config는 판 사이 재화(carry)에만 적는 메타 성장 설정 파일 경로입니다(economy.json이 있는 폴더 기준).")
            ok = False
    # 가격 출처의 재화가 틀리면 그 출처를 쓰는 구매만 빠진다. 나머지 수입·구매는 계산한다
    prices, good, bad = cfg.get("prices", {}), {}, {}
    if not isinstance(prices, dict):
        _err(errors, "schema", "economy.prices", f"prices는 {{{'/'.join(PRICE_SOURCES)}: 재화}}여야 합니다.")
        prices = {}
    for k, v in prices.items():
        if k not in PRICE_SOURCES:
            _err(errors, "schema", "economy.prices", f"알 수 없는 가격 출처 '{k}'.{did_you_mean(k, PRICE_SOURCES)} 출처: {', '.join(PRICE_SOURCES)}")
        elif v not in cur:
            _err(errors, "schema", f"economy.prices.{k}",
                 f"prices.{k}의 재화 {c.josa(repr(v), '이가')} currencies에 없습니다.{did_you_mean(str(v), cur)} 이 출처의 가격을 쓰는 구매는 계산에서 뺍니다.")
            bad[k] = v
        else:
            good[k] = v
    left = cfg.get("leftover_max")
    if left is not None and not (_num(left) and left <= 1):
        _err(errors, "schema", "economy.leftover_max", "leftover_max는 0~1 비율입니다(판 끝에 남아도 되는 수입의 비율).")
        ok = False
    _known_keys(cfg, SETTING_FIELDS, "economy", errors)
    timing = cfg.get("purchase_timing", "any")
    if timing not in PURCHASE_TIMINGS:
        _err(errors, "schema", "economy.purchase_timing", f"purchase_timing은 {', '.join(PURCHASE_TIMINGS)} 중 하나입니다: {timing!r}")
        ok = False
    if not ok:
        return None
    return {"currencies": cur, "kill_reward": kill, "sell": sell, "prices": good, "bad_prices": bad, "leftover_max": left,
            "time_unit": c.time_unit(cfg), "purchase_timing": timing}


# ---------- 수입 ----------
def rarity_pools(items: dict) -> dict:
    """{희귀도: [(아이템 id, 가격)]}. 활성 아이템만. 드랍 판매 기대값을 낼 때 한 번만 만든다."""
    pools: dict = {}
    for i, x in items.items():
        if c.is_active(x) and x.get("rarity") is not None:
            pools.setdefault(x["rarity"], []).append((i, x.get("price")))
    return pools


def sell_value(table: dict, items: dict, pools: dict | None = None) -> tuple[float | None, tuple | None]:
    """드랍 한 번에서 나오는 아이템 가격의 기대값과, 계산하지 못한 이유 (코드, 대상).
    아이템 칸은 그 아이템 가격, 희귀도 칸은 그 희귀도 활성 아이템 가격의 평균. 삭제된 아이템 칸은 나오지 않으므로 빼고 나머지로 나눈다."""
    pools = rarity_pools(items) if pools is None else pools
    entries = table.get("entries") if isinstance(table, dict) else None
    if not isinstance(entries, list) or not entries:
        return None, ("price_missing", "entries")
    priced = []
    for e in entries:
        if not (isinstance(e, dict) and c.is_number(e.get("weight"))):
            return None, ("price_missing", "entries")
        if isinstance(e.get("item"), str):
            it = items.get(e["item"])
            if it is not None and not c.is_active(it):
                continue  # 삭제 아이템(드랍 테이블 쪽 경고는 아이템 검사가 낸다)
            if it is None or not c.is_number(it.get("price")):
                return None, ("price_missing", e["item"])
            priced.append((e["weight"], it["price"]))
        else:
            pool = pools.get(e.get("rarity"), [])
            if not pool:
                return None, ("rarity_empty", e.get("rarity"))
            bad = [i for i, price in pool if not c.is_number(price)]
            if bad:
                return None, ("price_missing", ", ".join(bad[:5]))
            priced.append((e["weight"], sum(price for _, price in pool) / len(pool)))
    total_w = sum(w for w, _ in priced)
    if total_w <= 0:
        return None, ("price_missing", "entries")
    return sum(w / total_w * price for w, price in priced), None


def _stage_income(s: dict, settings: dict, refs: dict, errors: list, warnings: list, missing: set) -> dict | None:
    where, cur = s["id"], settings["currencies"]
    other = _amounts(s.get("income"), cur, where, "income", errors)
    kills, drops = s.get("kills", {}), s.get("drops", {})
    ok = other is not None
    for key, val in (("kills", kills), ("drops", drops)):
        if not (isinstance(val, dict) and all(isinstance(k, str) and _num(v) for k, v in val.items())):
            _err(errors, "schema", where, f"{c.josa(key, '은는')} {{id: 0 이상의 횟수}}여야 합니다.")
            ok = False
    if not ok:
        return None
    sources = {k: {p: 0.0 for p in INCOME_PARTS} for k in cur}
    for k, v in other.items():
        sources[k]["other"] += v
    if kills:
        if refs["enemies"] is None:
            missing.add("enemies")
        elif settings["kill_reward"] is None:
            _err(errors, "schema", where, "kills를 쓰려면 economy.kill_reward(처치 보상 재화)가 필요합니다.")
            return None
        else:
            for eid, n in kills.items():
                e = refs["enemies"].get(eid)
                if e is None:
                    _err(errors, "unknown_enemy", where, f"적 데이터에 없는 id입니다: {eid}")
                    ok = False
                elif not c.is_active(e):
                    _err(warnings, "cut_referenced", where, f"삭제(cut)된 적 {eid}의 처치를 셉니다. 수입에서 뺍니다.", owner=where)
                elif not c.is_number(e.get("reward")):
                    _err(warnings, "reward_missing", where, f"적 {eid}에 reward(처치 보상)가 없어 0으로 셉니다.", owner=where)
                else:
                    sources[settings["kill_reward"]]["kills"] += n * e["reward"]
    if drops:
        if refs["items"] is None or refs["drop_tables"] is None:
            missing.add("items")
        elif settings["sell"] is None:
            _err(errors, "schema", where, "drops를 쓰려면 economy.sell(판매 재화와 비율)이 필요합니다.")
            return None
        else:
            for tid, n in drops.items():
                table = refs["drop_tables"].get(tid)
                if table is None:
                    _err(errors, "unknown_drop_table", where, f"아이템 데이터에 없는 드랍 테이블입니다: {tid}")
                    ok = False
                    continue
                if tid not in refs["sell_cache"]:  # 같은 테이블은 단계마다 다시 계산하지 않는다
                    refs["sell_cache"][tid] = sell_value(table, refs["items"], refs["pools"])
                v, problem = refs["sell_cache"][tid]
                if v is None:
                    code, what = problem
                    msg = (f"드랍 테이블 {tid}의 희귀도 {what}에 해당하는 활성 아이템이 없어 판매 기대값을 계산하지 못했습니다." if code == "rarity_empty"
                           else f"드랍 테이블 {tid}에서 가격(price)이 없는 아이템이 있어 판매 기대값을 계산하지 못했습니다: {what}")
                    _err(errors, code, where, msg)
                    ok = False
                    continue
                sources[settings["sell"]["currency"]]["drops"] += n * v * settings["sell"]["ratio"]
    if not ok:
        return None
    return {k: {p: round(x, 4) for p, x in parts.items()} for k, parts in sources.items()}


# ---------- 가격 ----------
def _cut(entry: dict, label: str, ref: str, where: str, warnings: list) -> bool:
    if c.is_active(entry):
        return False
    _err(warnings, "cut_referenced", where, f"삭제(cut)된 {label} {c.josa(ref, '을를')} 삽니다. 구매 계획에서 뺍니다.", owner=where)
    return True


def _invalid(kind: str, ref: str, where: str, errors: list) -> None:
    _err(errors, "price_source_invalid", where,
         f"{kind} {ref}의 형식 오류 때문에 가격을 계산하지 못했습니다. 강화·합성 검사 결과를 먼저 고치세요.")


def _price(p: dict, settings: dict, refs: dict, errors: list, warnings: list, missing: set) -> tuple[float, str] | str:
    """구매 하나의 (가격, 재화), 또는 가격을 내지 못한 이유: "cut"(삭제된 출처, 경고), "error"(오류), "missing"(함께 읽지 않은 데이터).
    미확인이면 missing에 종류를 넣는다."""
    where, spec = p["id"], p.get("price")
    if not isinstance(spec, dict):
        _err(errors, "schema", where, "price 객체가 필요합니다: {amount, currency} 또는 {item | enhance+level | recipe | upgrade}.")
        return "error"
    if "amount" in spec:
        if not (_num(spec["amount"]) and spec.get("currency") in settings["currencies"]):
            _err(errors, "schema", where, "직접 적은 가격은 {amount: 0 이상의 수, currency: currencies의 재화}입니다."
                 + did_you_mean(str(spec.get("currency")), settings["currencies"]))
            return "error"
        return spec["amount"], spec["currency"]
    kinds = [k for k in PRICE_KEY if k in spec]
    if len(kinds) != 1:
        _err(errors, "schema", where, "price에는 amount, item, enhance, recipe, upgrade 중 하나만 적습니다.")
        return "error"
    kind = kinds[0]
    source = PRICE_KEY[kind]
    currency = settings["prices"].get(source)
    if currency is None:
        if source not in settings["bad_prices"]:  # 틀린 재화는 economy.prices에서 이미 보고했다
            _err(errors, "schema", where, f"{source} 가격의 재화가 정해지지 않았습니다. economy.prices.{c.josa(source, '을를')} 적습니다.")
        return "error"
    ref = spec[kind]
    if source in ("items", "upgrades"):
        label = "아이템" if source == "items" else "영구 강화"
        if refs[source] is None:
            missing.add(source)
            return "missing"
        e = refs[source].get(ref)
        if e is None:
            _err(errors, "unknown_item" if source == "items" else "unknown_upgrade", where,
                 f"{label} 데이터에 없는 id입니다: {ref}{did_you_mean(str(ref), refs[source])}")
            return "error"
        if _cut(e, label, ref, where, warnings):
            return "cut"
        field = "price" if source == "items" else "cost"
        if not c.is_number(e.get(field)):
            _err(errors, "price_missing", where, f"{label} {ref}에 {c.josa(field, '이가')} 없습니다.")
            return "error"
        return e[field], currency
    if refs["crafting"] is None:
        missing.add("crafting")
        return "missing"
    entries = refs["crafting"].get("enhance" if source == "enhance" else "recipes") or []
    found = next((x for x in entries if isinstance(x, dict) and x.get("id") == ref), None) if isinstance(entries, list) else None
    if source == "enhance":
        if found is None:
            _err(errors, "unknown_enhance", where, f"강화·합성 데이터에 없는 강화입니다: {ref}")
            return "error"
        if not cr.check_track(found, []):  # 강화·합성 검사와 같은 규칙. 틀린 데이터로 가격을 내지 않는다
            _invalid("강화", ref, where, errors)
            return "error"
        if _cut(found, "강화", ref, where, warnings):
            return "cut"
        level, start = spec.get("level"), spec.get("from", 0)
        levels = found.get("levels")
        top = len(levels) if isinstance(levels, list) else 0
        if not (c.is_int(level) and c.is_int(start) and 0 <= start < level <= top):
            _err(errors, "schema", where, f"강화 {ref}의 가격은 from(시작 단계, 기본 0) < level ≤ {top}인 정수로 적습니다: from {start!r}, level {level!r}")
            return "error"
        costs = cr.level_costs(levels, found.get("replace_cost", 0.0))
        before = costs[start - 1]["expected_cost"] if start else 0.0  # 이미 산 단계까지의 비용은 빼고 그다음 단계부터
        return round(costs[level - 1]["expected_cost"] - before, 4), currency
    if found is None:
        _err(errors, "unknown_recipe", where, f"강화·합성 데이터에 없는 합성입니다: {ref}")
        return "error"
    if cr.check_recipe(found, []) is None:
        _invalid("합성", ref, where, errors)
        return "error"
    if _cut(found, "합성", ref, where, warnings):
        return "cut"
    return round(found.get("cost", 0) / found.get("success", 1.0), 4), currency


def _currency_of(p: dict, settings: dict) -> str:
    """가격을 내지 못한 구매가 쓰려던 재화. 이름이 틀렸으면 오타 추정으로 가장 비슷한 재화, 그래도 모르면 "*"(모든 재화)."""
    spec = p.get("price") if isinstance(p.get("price"), dict) else {}
    cur = settings["currencies"]
    guess = lambda name: name if name in cur else (c.closest(str(name), cur) or "*")  # noqa: E731
    if "amount" in spec:
        return guess(spec.get("currency"))
    kinds = [k for k in PRICE_KEY if k in spec]
    if len(kinds) != 1:
        return "*"
    source = PRICE_KEY[kinds[0]]
    if source in settings["prices"]:
        return settings["prices"][source]
    return guess(settings["bad_prices"][source]) if source in settings["bad_prices"] else "*"


# ---------- 시점 ----------
def _stage_at(stages: list[dict], t: float) -> str:
    """판 안 시점 t가 속한 단계(경계는 다음 단계)."""
    acc = 0.0
    for s in stages:
        if t < acc + s["duration"] - EPS:
            return s["id"]
        acc += s["duration"]
    return stages[-1]["id"] if stages else ""

def _stage_end(stages: list[dict], t: float) -> tuple[float, str]:
    """시점 t 뒤로 처음 끝나는 단계의 끝과 그 단계. 단계 사이에만 사는 게임의 구매 시점이다. 판을 시작할 때 살 수 있으면 그대로 둔다."""
    if not stages:
        return 0.0, ""
    if t <= EPS:
        return 0.0, stages[0]["id"]
    end = 0.0
    for s in stages:
        end += s["duration"]
        if t <= end + EPS:
            return end, s["id"]
    return end, stages[-1]["id"]


def _kit_buys(x, item_buys: dict, enhance_buys: dict) -> list:
    """기준 장비 한 칸을 사는 구매 [(이름, 구매 행)]. 아이템을 사는 구매와, 강화했으면 그 단계에 처음 닿는 구매다. 합성으로 얻는 장비는 보지 않는다."""
    rid = x.get("item") if isinstance(x, dict) else x
    out = [(rid, item_buys[rid])] if isinstance(rid, str) and rid in item_buys else []
    if isinstance(x, dict) and isinstance(x.get("enhance"), str) and c.is_int(x.get("level")):
        reach = next((row for level, row in enhance_buys.get(x["enhance"], []) if level >= x["level"]), None)
        if reach:
            out.append((f"{rid} +{x['level']}", reach))
    return out


def _check_gear(item_buys: dict, enhance_buys: dict, stages: list[dict], combat_stages: dict, stage_end: bool, warnings: list) -> None:
    """전투 단계의 기준 장비가 구매 계획보다 앞서면 알린다. 처치 시간의 입력이 아직 살 수 없는 장비가 된다.
    단계 끝에 사면 다음 단계부터, 단계 안에서 사면 그 단계부터 쓴다고 본다."""
    place = {s["id"]: n for n, s in enumerate(stages)}
    linked: dict = {}
    for n, s in enumerate(stages):
        linked.setdefault(c.combat_link(s), n)
    for sid, cs in combat_stages.items():
        kit = (cs.get("player") or {}).get("items") if isinstance(cs.get("player"), dict) else None
        if sid not in linked or not c.is_active(cs) or not isinstance(kit, list):
            continue
        for name, row in (pair for x in kit for pair in _kit_buys(x, item_buys, enhance_buys)):
            if row["stage"] not in place or row["at"] <= EPS:  # 시점이 없는 구매는 stage도 없다. 판을 시작할 때 산 것은 어느 단계에나 있다
                continue
            bought = place[row["stage"]]
            if bought > linked[sid] or (stage_end and bought == linked[sid]):
                _err(warnings, "gear_before_purchase", row["id"],
                     f"전투 단계 {sid}의 기준 장비에 {c.josa(name, '이가')} 있는데 구매 계획은 {row['stage']}{' 끝' if stage_end else ''}에 삽니다. "
                     "기준 장비를 맞추거나, 드랍처럼 다른 길로 먼저 얻으면 acknowledged에 이유를 적습니다.", owner=row["id"], part=sid)


def _time_reaching(stages: list[dict], currency: str, amount: float, settings: dict) -> tuple[float, str] | None:
    """누적 수입이 amount에 처음 닿는 판 안의 시점과 그 단계. 닿지 못하면 None. 단계 안에서는 고르게 들어온다고 본다."""
    if amount <= EPS:
        return 0.0, stages[0]["id"] if stages else ""
    t = acc = 0.0
    for s in stages:
        got = sum(s["sources"][currency].values())
        if acc + got >= amount - EPS and got > 0:
            return round(t + (amount - acc) / got * s["duration"], 4), s["id"]
        acc += got
        t += s["duration"]
    return None


def validate(data: dict, enemies: dict | None = None, items: dict | None = None, drop_tables: dict | None = None,
             upgrades: dict | None = None, crafting: dict | None = None, combat: dict | None = None, meta: dict | None = None) -> dict:
    """enemies·items·upgrades: 함께 읽은 데이터의 {id: 항목}, drop_tables: 아이템 데이터의 드랍 테이블, crafting: 강화·합성 파일 내용.
    combat: 전투 계산 파일 내용(단계의 combat_stage 연결을 확인), meta: {재화: 메타 성장 설정(meta_sim.normalize 결과) 또는 {"error": 이유}}.
    쓰는 데이터가 None이면 그 부분은 미확인으로 센다."""
    errors: list = []
    warnings: list = []
    settings = read_settings(data, errors)
    _known_keys(data, TOP_FIELDS, "economy", errors)
    raw_stages, raw_buys = data.get("stages"), data.get("purchases", [])
    if not isinstance(raw_stages, list):
        _err(errors, "schema", "stages", "stages(단계 배열)가 필요합니다.")
        raw_stages = []
    if not isinstance(raw_buys, list):
        _err(errors, "schema", "purchases", "purchases(구매 계획 배열)는 배열이어야 합니다.")
        raw_buys = []
    stages = [s for _, s in c.check_identity(raw_stages, "stages", errors) if c.check_common(s, s["id"], errors)]
    buys = [p for _, p in c.check_identity(raw_buys, "purchases", errors) if c.check_common(p, p["id"], errors)]
    for entry, known in [*((s, STAGE_FIELDS) for s in stages), *((p, PURCHASE_FIELDS) for p in buys)]:
        _known_keys(entry, known, entry["id"], errors)
    refs = {"enemies": enemies, "items": items, "drop_tables": drop_tables, "upgrades": upgrades, "crafting": crafting,
            "pools": rarity_pools(items) if items is not None else {}, "sell_cache": {}}
    missing: set = set()
    timeline: list = []
    rows: list = []
    leftover: dict = {}
    affected: set = set()  # 미확인 때문에 시점·판 수·남는 양을 다 내지 못한 재화
    combat_stages = {x["id"]: x for x in (combat or {}).get("stages") or [] if isinstance(x, dict) and isinstance(x.get("id"), str)} \
        if isinstance((combat or {}).get("stages"), list) else {}
    linked = {c.combat_link(s) for s in stages if c.is_active(s)}
    free = [k for k in cb.main_stage_ids(combat) if k not in linked]  # 재화 흐름과 이어지지 않은 전투 단계. 변형 단계(variant_of)는 잇지 않는다
    if settings is not None:
        cur = settings["currencies"]
        complete, gap = True, False
        for s in (x for x in stages if c.is_active(x)):
            _check_link(s, combat, combat_stages, free, enemies, errors, warnings, missing)
            if not _num(s.get("duration"), strict=True):
                _err(errors, "schema", s["id"], f"duration(단계 길이, {settings['time_unit']})은 0보다 큰 수여야 합니다: {s.get('duration')!r}")
                complete, gap = False, True
                continue
            before = len(missing)
            src = _stage_income(s, settings, refs, errors, warnings, missing)
            if src is None or len(missing) > before:
                complete, gap = False, True
                continue
            timeline.append({"id": s["id"], "name": s.get("name"), "duration": s["duration"], "sources": src, "after_gap": gap})
        acc = {k: 0.0 for k in cur}
        for st in timeline:
            st["income"] = {k: round(sum(v.values()), 4) for k, v in st["sources"].items() if sum(v.values()) > 0}
            st["rate"] = {k: round(v / st["duration"], 4) for k, v in st["income"].items()}
            for k, v in st["income"].items():
                acc[k] += v
            # 앞 단계를 계산하지 못했으면 누적은 처음부터 다시 센 값이 되어 틀린다. 내지 않는다
            st["cumulative"] = None if st.pop("after_gap") else {k: round(v, 4) for k, v in acc.items() if v > 0}
        per_run = acc
        spent = {k: 0.0 for k in cur}
        starts, t0 = {}, 0.0
        for st in timeline:
            starts[st["id"]] = t0
            t0 += st["duration"]
        run_end = t0
        stage_ids = {s["id"] for s in stages}
        last_time = 0.0
        planned_ups: set = set()   # 계획에서 앞서 사는 영구 강화. 가격을 구하지 못한 구매도 계획에는 있다
        first_buy: dict = {}       # 영구 강화 → 처음 사는 구매
        reached: dict = {}         # 강화 → 앞 구매까지 오른 단계
        blocked: dict = {}         # 재화 → 시점을 계산하지 못한 앞 구매("*"는 재화를 알 수 없음 = 모든 재화)
        upgrade_order: dict = {}   # 재화 → 계획 순서대로 사는 영구 강화
        item_buys: dict = {}       # 아이템 → 처음 사는 구매 행
        enhance_buys: dict = {}    # 강화 → [(닿는 단계, 구매 행)] 계획 순서대로
        for p in (x for x in buys if c.is_active(x)):
            spec = p.get("price") if isinstance(p.get("price"), dict) else {}
            ref_up, prior = spec.get("upgrade"), set(planned_ups)
            if isinstance(ref_up, str):
                planned_ups.add(ref_up)
                if ref_up in first_buy:
                    _err(warnings, "duplicate_purchase", p["id"],
                         f"영구 강화 {c.josa(ref_up, '을를')} {first_buy[ref_up]}에서 이미 삽니다. 같은 영구 강화를 두 번 사는 계획입니다.", owner=p["id"])
                else:
                    first_buy[ref_up] = p["id"]
            ref_enh = spec.get("enhance")
            if isinstance(ref_enh, str) and c.is_int(spec.get("level")) and c.is_int(spec.get("from", 0)):
                start, now = spec.get("from", 0), reached.get(ref_enh, 0)
                if start != now:
                    _err(warnings, "enhance_gap", p["id"],
                         f"강화 {c.josa(ref_enh, '을를')} +{start}부터 사는데 계획의 앞 구매까지는 +{now}입니다. "
                         + ("단계를 건너뜁니다." if start > now else "이미 산 단계를 다시 삽니다.") + " from을 앞 구매의 level과 맞춥니다.", owner=p["id"])
                reached[ref_enh] = spec["level"]
            target = p.get("target")
            if target is not None and not c.valid_range(target):
                _err(errors, "schema", p["id"], "target은 [최소, 최대]이고 한쪽은 null로 비울 수 있습니다(최소 ≤ 최대).")
                target = None
            after = p.get("after")
            if c.is_number(after) and (after < 0 or (complete and timeline and after > run_end + EPS)):
                _err(errors, "schema", p["id"], f"after(팔기 시작하는 단계나 시각)의 시각은 0부터 판 끝 {run_end:g}까지입니다: {after:g}")
                blocked.setdefault(_currency_of(p, settings), p["id"])
                continue
            if after is not None and not c.is_number(after) and not (isinstance(after, str) and after in stage_ids):
                _err(errors, "unknown_stage", p["id"], f"after에 적은 단계가 stages에 없습니다: {c.json_text(after)}{did_you_mean(str(after), stage_ids)}{_time_hint(after)}")
                blocked.setdefault(_currency_of(p, settings), p["id"])
                continue
            got = _price(p, settings, refs, errors, warnings, missing)
            if isinstance(got, str):
                if got == "cut" and isinstance(ref_up, str) and ref_up not in prior:
                    planned_ups.discard(ref_up)  # 삭제된 영구 강화는 계획에서 빠졌다. 뒤 강화의 선행 조건을 채우지 않는다
                elif got != "cut":  # 계획에서 뺀 삭제 출처와 달리, 오류·미확인 구매는 그 재화의 뒤 시점을 틀리게 만든다
                    blocked.setdefault(_currency_of(p, settings), p["id"])
                continue
            price, currency = got
            if after is not None and cur[currency].get("carry"):
                _err(errors, "schema", p["id"], "after(팔기 시작하는 단계나 시각)는 판 안 재화의 구매에만 씁니다. 판 사이 재화는 판 단위로 셉니다.")
                blocked.setdefault(currency, p["id"])
                continue
            if ref_up and refs["upgrades"] is not None:
                upgrade_order.setdefault(currency, []).append(ref_up)
                reqs = refs["upgrades"][ref_up].get("requires") or []
                lacking = [x for x in reqs if isinstance(x, str) and x not in prior] if isinstance(reqs, list) else []
                if lacking:
                    _err(warnings, "requirement_missing", p["id"],
                         f"{p['id']}의 영구 강화 {c.josa(ref_up, '은는')} {c.josa(', '.join(lacking), '이가')} 먼저 필요한데 계획에서 그보다 앞에 있습니다.", owner=p["id"])
            row = {"id": p["id"], "name": p.get("name"), "currency": currency, "price": round(price, 4),
                   "at": None, "stage": None, "held_by": None, "runs": None, "affordable": True, "out_of_range": False, "blocked": None}
            rows.append(row)
            if isinstance(spec.get("item"), str):
                item_buys.setdefault(spec["item"], row)
            if isinstance(ref_enh, str) and c.is_int(spec.get("level")):
                enhance_buys.setdefault(ref_enh, []).append((spec["level"], row))
            stop = blocked.get(currency) or blocked.get("*")
            if stop:
                row["blocked"] = stop  # 앞 구매를 계산하지 못해 이 구매의 시점도 알 수 없다(목표도 검사하지 않는다)
                continue
            spent[currency] += price
            if cur[currency].get("carry"):
                if complete:  # 한 판 수입을 다 셀 수 있을 때만 판 수를 낸다(일부 단계만으로 세면 판 수가 부풀려진다)
                    row["runs"] = math.ceil(round(spent[currency] / per_run[currency], 9)) if per_run[currency] > 0 else None
                row["affordable"] = row["runs"] is not None or not complete
                measure, unit = row["runs"], "판"
            else:
                hit = _time_reaching(timeline, currency, spent[currency], settings) if complete else None
                if hit:
                    # 돈이 모이는 시점, 파는 단계가 시작하는 시점, 앞선 구매 시점 중 가장 늦은 때(계획 순서대로 산다)
                    ready = max(hit[0], after if c.is_number(after) else starts.get(after, 0.0))   # 앞 구매가 없어도 살 수 있는 때
                    at = max(ready, last_time)
                    row["held_by"] = "order" if at > ready + EPS else "money" if ready <= hit[0] + EPS else "after"   # 시점을 정한 까닭. 레벨 구성의 안내가 읽는다
                    if settings["purchase_timing"] == "stage_end":
                        end, row["stage"] = _stage_end(timeline, at)
                        if end > ready + EPS and _stage_end(timeline, ready)[0] >= end - EPS:
                            row["held_by"] = "stage_end"   # 앞 구매가 없어도 같은 단계 끝이다
                        at = end
                    else:
                        row["stage"] = _stage_at(timeline, at)
                    last_time = at
                    row["at"] = round(at, 4)
                row["affordable"] = hit is not None or not complete
                measure, unit = row["at"], settings["time_unit"]
            if not row["affordable"]:
                spent[currency] -= price  # 사지 못한 것은 남는 재화 계산에서 뺀다
                _err(warnings, "unaffordable", p["id"],
                     f"{p['id']}({price:g} {currency})는 " + ("판 사이 수입이 없어 살 수 없습니다." if cur[currency].get("carry")
                                                               else "한 판의 수입으로 살 수 없습니다. 구매 순서나 가격, 수입을 확인하세요."), owner=p["id"])
                continue
            if target is not None and measure is not None and c.out_of_range(measure, target):
                row["out_of_range"] = True
                _err(warnings, "target_out_of_range", p["id"],
                     f"{c.josa(p['id'], '을를')} {c.num_text(measure)}{unit}에 삽니다. 목표 {c.josa(c.range_text(target) + unit, '을를')} 벗어납니다.", owner=p["id"])
        _check_gear(item_buys, enhance_buys, [x for x in stages if c.is_active(x)], combat_stages, settings["purchase_timing"] == "stage_end", warnings)
        if complete:
            for k in cur:
                if cur[k].get("carry") or per_run[k] <= 0 or k in blocked or "*" in blocked:
                    continue  # 계산하지 못한 구매가 있는 재화는 남는 양을 내지 않는다(빼고 세면 남는 재화가 부풀려진다)
                left = per_run[k] - spent[k]
                share = left / per_run[k]
                leftover[k] = {"amount": round(left, 4), "share": round(share, 4)}
                if settings["leftover_max"] is not None and share > settings["leftover_max"] + EPS:
                    _err(warnings, "currency_piles_up", f"economy.currencies.{k}",
                         f"한 판 수입 {per_run[k]:g} {k} 중 {share:.0%}({left:g})가 구매 계획 뒤에도 남습니다(허용 {settings['leftover_max']:.0%}). "
                         "쓸 곳을 늘리거나 수입을 줄입니다.")
        _check_meta(settings, meta, complete, blocked, per_run, upgrade_order, errors, warnings, missing)
        if missing:
            affected = set(cur) if not complete or "*" in blocked else set(blocked) & set(cur)
        if not timeline and not errors and not missing:
            missing.add("nothing")  # 계산한 단계가 없으면 통과가 아니다(빈 stages, 모두 삭제)
    summary = c.summary_counts(stages + buys)
    prov = (data.get("economy") or {}).get("provenance") if isinstance(data.get("economy"), dict) else None
    if prov is not None:
        c.check_common({"provenance": prov}, "economy", errors)
    if settings is not None and c.provenance_kind({"provenance": prov}) in ("assumed", "unspecified"):
        summary["unverified"] = ["economy(수입·구매 계획)"] + summary["unverified"]
    return {
        "kind": "economy",
        "count": len(stages) + len(buys),
        **summary,
        "time_unit": c.time_unit(settings),
        "purchase_timing": settings["purchase_timing"] if settings else "any",
        "currencies": {k: {"name": v.get("name"), "carry": bool(v.get("carry"))} for k, v in (settings or {}).get("currencies", {}).items()},
        "stages": timeline,
        "purchases": rows,
        "leftover": leftover,
        "unchecked": len(missing),
        "unchecked_kinds": sorted(missing),
        "unchecked_currencies": sorted(affected),
        "errors": errors,
        "warnings": warnings,
    }


def _check_link(s: dict, combat: dict | None, combat_stages: dict, free: list, enemies: dict | None, errors: list, warnings: list, missing: set) -> None:
    """단계의 combat_stage(같은 구간의 전투 단계)를 확인하고, 그 전투 단계에 나오지 않는 적의 처치를 경고한다."""
    link = s.get("combat_stage")
    if link is None:
        return
    if not isinstance(link, str):
        _err(errors, "schema", s["id"], f"combat_stage는 전투 계산의 단계 id입니다: {link!r}")
        return
    if combat is None:
        missing.add("combat")
        return
    cs = combat_stages.get(link)
    if cs is None:
        _err(errors, "unknown_stage", s["id"], f"combat_stage가 전투 계산(combat.json)에 없는 단계입니다: {link}."
             + cb.stage_hint(link, free, [k for k, x in combat_stages.items() if c.is_active(x)], "재화 흐름과 이어지지 않은 전투 단계",
                             "이미 재화 흐름 단계가 이어져 있습니다. 같은 전투 단계를 나눠 적는 것이면 그 id로 적습니다"))
        return
    if not c.is_active(cs):
        _err(warnings, "cut_referenced", s["id"], f"삭제(cut)된 전투 단계 {link}에 이었습니다.", owner=s["id"])
        return
    if cb.is_variant(cs):
        _err(errors, "unknown_stage", s["id"], cb.variant_hint(cs))
        return
    foes = cb.stage_foes(cs, enemies)
    kills = s.get("kills") if isinstance(s.get("kills"), dict) else {}
    for k in sorted(k for k in kills if foes is not None and k not in foes):  # 적마다 확인할 수 있게 한 줄씩 낸다
        _err(warnings, "kill_not_in_stage", s["id"],
             f"전투 단계 {link}에 나오지 않는 적의 처치를 셉니다: {k}. 전투 계산과 재화 흐름이 다른 적을 보고 있습니다."
             f"{cb.outside_hint([k], cs, enemies)}", owner=s["id"], part=k)


def _check_meta(settings: dict, meta: dict | None, complete: bool, blocked: dict, per_run: dict, upgrade_order: dict,
                errors: list, warnings: list, missing: set) -> None:
    """판 사이 재화의 meta_config(메타 성장 설정)와 한 판 수입·영구 강화 구매 순서를 맞춰 본다.
    시뮬레이터(simulate)와 재화 흐름이 서로 다른 수입·순서로 계산하면 두 결과의 판 수 차이가 '지는 판' 때문인지 알 수 없다."""
    for k, v in settings["currencies"].items():
        if not v.get("meta_config"):
            continue
        where, cfg = f"economy.currencies.{k}", (meta or {}).get(k)
        if cfg is None:
            missing.add("meta")
            continue
        if "error" in cfg:
            _err(errors, "schema", where, f"meta_config {c.josa(v['meta_config'], '을를')} 읽지 못했습니다: {cfg['error']}")
            continue
        if not complete or k in blocked or "*" in blocked:
            continue
        sim = meta_sim.full_run_income(cfg)  # None: 설정이 재화 흐름에서 수입을 읽는다(같은 원본)
        if sim is not None and abs(sim - per_run[k]) > 1e-6 * max(1.0, abs(sim)):
            _err(warnings, "meta_income_differs", where,
                 f"한 판 수입이 다릅니다: 재화 흐름 {c.num_text(per_run[k])} {k}, 메타 성장 설정({v['meta_config']})의 끝까지 깬 판 {c.num_text(sim)}. "
                 "한쪽을 원본으로 정해 맞추거나, 설정이 재화 흐름에서 수입을 읽게(economy 연결) 합니다.")
        if cfg["purchase_policy"] == meta_sim.ECONOMY_POLICY:
            continue  # 시뮬레이터가 이 구매 계획 순서대로 산다
        _, order = meta_sim.buy(cfg, float("inf"), set())
        ours = [u for u in upgrade_order.get(k, []) if u in order]
        theirs = [u for u in order if u in ours]
        if ours != theirs:
            show = lambda xs: " → ".join(xs[:6]) + (" …" if len(xs) > 6 else "")  # noqa: E731
            _err(warnings, "meta_order_differs", where,
                 f"영구 강화 구매 순서가 다릅니다: 재화 흐름 {show(ours)}, 시뮬레이터({cfg['purchase_policy']}) {show(theirs)}. "
                 "두 결과의 판 수를 비교하려면 순서를 맞춥니다.")


# ---------- 출력 ----------
def _fmt(v) -> str:
    if v is None:
        return "–"
    return f"{v:g}" if isinstance(v, float) else str(v)


def _amounts_text(d) -> str:
    return " · ".join(f"{k} {_fmt(v)}" for k, v in d.items()) if d else "–"


def _when(p: dict, result: dict) -> str:
    if p.get("blocked"):
        return f"– (앞 구매 {c.josa(p['blocked'], '을를')} 계산하지 못해 미확인)"
    if not p["affordable"]:
        return "살 수 없음"
    if result["currencies"].get(p["currency"], {}).get("carry"):
        return f"{p['runs']}번째 판" if p["runs"] is not None else "–"
    end = " 끝" if result["purchase_timing"] == "stage_end" else ""
    return f"{_fmt(p['at'])}{result['time_unit']} ({p['stage']}{end})" if p["at"] is not None else "–"


def print_extra(result: dict) -> None:
    unit = result["time_unit"]
    for st in result["stages"]:
        cumulative = _amounts_text(st["cumulative"]) if st["cumulative"] is not None else "–(앞 단계를 계산하지 못함)"
        print(f"단계 {st['id']} ({_fmt(st['duration'])}{unit}): {_amounts_text(st['income']) if st['income'] else '수입 없음'} · 누적 {cumulative}")
    for p in result["purchases"]:
        print(f"구매 {p['id']}: {_fmt(p['price'])} {p['currency']} → {_when(p, result)}" + (" ⚠" if p["out_of_range"] or not p["affordable"] else ""))
    for k, left in result["leftover"].items():
        print(f"판 끝에 남는 {k}: {_fmt(left['amount'])} (한 판 수입의 {left['share']:.0%})")
    data_kinds = [UNCHECKED_LABEL[k] for k in result["unchecked_kinds"] if k in UNCHECKED_LABEL]
    if data_kinds:
        print("재화 흐름 미확인: " + ", ".join(data_kinds) + " 데이터를 함께 검사하지 않았거나 읽지 못함")
    if "nothing" in result["unchecked_kinds"]:
        print("재화 흐름 미확인: 계산한 단계가 없음(빈 stages이거나 모두 삭제)")


def table(data: dict, result: dict, ids: list[str] | None = None) -> str:
    """대화에 붙일 재화 흐름 표(마크다운). --ids는 컨셉 비교표용이라 여기서는 쓰지 않는다."""
    unit = result["time_unit"]
    rows = [f"| 단계 | 길이 | 수입 | {unit}당 | 누적 |", "|---|---|---|---|---|"]
    for st in result["stages"]:
        rows.append("| " + " | ".join((st["id"], _fmt(st["duration"]) + unit, _amounts_text(st["income"]), _amounts_text(st["rate"]),
                                        _amounts_text(st["cumulative"]) if st["cumulative"] is not None else "– (앞 단계 미확인)")) + " |")
    rows += ["", f"| 구매 | 재화 | 가격 | 시점({unit}) | 단계 | 판 | 판정 |", "|---|---|---|---|---|---|---|"]
    end = " 끝" if result["purchase_timing"] == "stage_end" else ""
    for p in result["purchases"]:
        verdict = ("미확인" if p.get("blocked") else "살 수 없음" if not p["affordable"] else "목표 이탈" if p["out_of_range"] else "–")
        rows.append("| " + " | ".join((p["id"], p["currency"], _fmt(p["price"]), _fmt(p["at"]), (p["stage"] + end) if p["stage"] else "–", _fmt(p["runs"]), verdict)) + " |")
    rows += ["", "기대값 계산입니다. 처치 수·드랍 횟수는 기획 가정이며, 실제 체감이나 재미를 판정하지 않습니다."]
    return "\n".join(rows)


def print_counts(result: dict) -> None:
    tail = f"오류 {len(result['errors'])} · 경고 {len(result['warnings'])}"
    if result.get("acknowledged"):
        tail += f" · 확인한 경고 {len(result['acknowledged'])}"
    print(f"단계 {len(result['stages'])}개 · 구매 {len(result['purchases'])}개 · {tail}")
