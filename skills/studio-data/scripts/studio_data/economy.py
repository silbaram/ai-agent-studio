"""재화 흐름(data/economy.json): 단계마다 들어오는 재화와 구매 계획을 이어 "언제 살 수 있나", "얼마나 남나"를 계산한다.

수입: 단계(구역·레벨·시간 구간)마다 처치 수 × 적 보상, 드랍 횟수 × 드랍을 팔 때의 기대값, 그 밖의 수입.
지출: 구매 계획의 순서대로. 가격은 직접 적거나 아이템 가격, 강화 기대 비용(crafting), 합성 비용, 영구 강화 비용에서 가져온다.
판이 끝나면 사라지는 재화는 판 안의 시점으로, 판 사이에 남는 재화(carry)는 몇 번째 판에 사는지로 본다.
기대값 계산이며 실제 체감이나 재미를 판정하지 않는다. 형식: economy-flow/references/economy-format.md
"""
from __future__ import annotations

import math

from . import common as c
from . import crafting as cr
from .common import add_issue as _err

PRICE_SOURCES = ("items", "enhance", "recipes", "upgrades")
PRICE_KEY = {"item": "items", "enhance": "enhance", "recipe": "recipes", "upgrade": "upgrades"}
INCOME_PARTS = ("kills", "drops", "other")
UNCHECKED_LABEL = {"enemies": "적", "items": "아이템", "upgrades": "영구 강화", "crafting": "강화·합성"}
EPS = 1e-9


def _num(v, minimum: float = 0.0, strict: bool = False) -> bool:
    return c.is_number(v) and (v > minimum if strict else v >= minimum)


def _amounts(d, currencies: dict, where: str, label: str, errors: list) -> dict | None:
    """{재화: 0 이상의 양}. 형식이 틀리면 오류를 남기고 None."""
    if d is None:
        return {}
    if not (isinstance(d, dict) and all(isinstance(k, str) and _num(v) for k, v in d.items())):
        _err(errors, "schema", where, f"{label}은 {{재화: 0 이상의 수}}여야 합니다.")
        return None
    unknown = [k for k in d if k not in currencies]
    if unknown:
        _err(errors, "schema", where, f"{label}에 없는 재화: {', '.join(unknown)}. economy.currencies에 먼저 적습니다.")
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
        _err(errors, "schema", "economy.kill_reward", f"kill_reward는 currencies의 재화여야 합니다: {kill!r}")
        ok = False
    sell = cfg.get("sell")
    if sell is not None and not (isinstance(sell, dict) and sell.get("currency") in cur and _num(sell.get("ratio")) and sell["ratio"] <= 1):
        _err(errors, "schema", "economy.sell", "sell은 {currency: 재화, ratio: 0~1(가격 중 받는 비율)}이어야 합니다.")
        ok = False
    prices = cfg.get("prices", {})
    if not (isinstance(prices, dict) and all(k in PRICE_SOURCES and v in cur for k, v in prices.items())):
        _err(errors, "schema", "economy.prices", f"prices는 {{{'/'.join(PRICE_SOURCES)}: 재화}}여야 합니다.")
        ok = False
    left = cfg.get("leftover_max")
    if left is not None and not (_num(left) and left <= 1):
        _err(errors, "schema", "economy.leftover_max", "leftover_max는 0~1 비율입니다(판 끝에 남아도 되는 수입의 비율).")
        ok = False
    if not ok:
        return None
    return {"currencies": cur, "kill_reward": kill, "sell": sell, "prices": prices, "leftover_max": left,
            "time_unit": cfg.get("time_unit") if isinstance(cfg.get("time_unit"), str) else "초"}


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
            _err(errors, "schema", where, f"{key}는 {{id: 0 이상의 횟수}}여야 합니다.")
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
    _err(warnings, "cut_referenced", where, f"삭제(cut)된 {label} {ref}를 삽니다. 구매 계획에서 뺍니다.", owner=where)
    return True


def _invalid(kind: str, ref: str, where: str, errors: list) -> None:
    _err(errors, "price_source_invalid", where,
         f"{kind} {ref}의 형식 오류 때문에 가격을 계산하지 못했습니다. 강화·합성 검사 결과를 먼저 고치세요.")


def _price(p: dict, settings: dict, refs: dict, errors: list, warnings: list, missing: set) -> tuple[float, str] | None:
    """구매 하나의 (가격, 재화). 출처를 확인하지 못하면 None(미확인이면 missing에 종류를 넣는다). 삭제된 출처는 경고하고 None."""
    where, spec = p["id"], p.get("price")
    if not isinstance(spec, dict):
        _err(errors, "schema", where, "price 객체가 필요합니다: {amount, currency} 또는 {item | enhance+level | recipe | upgrade}.")
        return None
    if "amount" in spec:
        if not (_num(spec["amount"]) and spec.get("currency") in settings["currencies"]):
            _err(errors, "schema", where, "직접 적은 가격은 {amount: 0 이상의 수, currency: currencies의 재화}입니다.")
            return None
        return spec["amount"], spec["currency"]
    kinds = [k for k in PRICE_KEY if k in spec]
    if len(kinds) != 1:
        _err(errors, "schema", where, "price에는 amount, item, enhance, recipe, upgrade 중 하나만 적습니다.")
        return None
    kind = kinds[0]
    source = PRICE_KEY[kind]
    currency = settings["prices"].get(source)
    if currency is None:
        _err(errors, "schema", where, f"{source} 가격의 재화가 정해지지 않았습니다. economy.prices.{source}를 적습니다.")
        return None
    ref = spec[kind]
    if source == "items":
        if refs["items"] is None:
            missing.add("items")
            return None
        it = refs["items"].get(ref)
        if it is None:
            _err(errors, "unknown_item", where, f"아이템 데이터에 없는 id입니다: {ref}")
            return None
        if _cut(it, "아이템", ref, where, warnings):
            return None
        if not c.is_number(it.get("price")):
            _err(errors, "price_missing", where, f"아이템 {ref}에 price(가격)가 없습니다.")
            return None
        return it["price"], currency
    if source == "upgrades":
        if refs["upgrades"] is None:
            missing.add("upgrades")
            return None
        u = refs["upgrades"].get(ref)
        if u is None:
            _err(errors, "unknown_upgrade", where, f"영구 강화 데이터에 없는 id입니다: {ref}")
            return None
        if _cut(u, "영구 강화", ref, where, warnings):
            return None
        if not c.is_number(u.get("cost")):
            _err(errors, "price_missing", where, f"영구 강화 {ref}에 cost가 없습니다.")
            return None
        return u["cost"], currency
    if refs["crafting"] is None:
        missing.add("crafting")
        return None
    entries = refs["crafting"].get("enhance" if source == "enhance" else "recipes") or []
    found = next((x for x in entries if isinstance(x, dict) and x.get("id") == ref), None) if isinstance(entries, list) else None
    if source == "enhance":
        if found is None:
            _err(errors, "unknown_enhance", where, f"강화·합성 데이터에 없는 강화입니다: {ref}")
            return None
        if not cr.check_track(found, []):  # 강화·합성 검사와 같은 규칙. 틀린 데이터로 가격을 내지 않는다
            _invalid("강화", ref, where, errors)
            return None
        if _cut(found, "강화", ref, where, warnings):
            return None
        level, start = spec.get("level"), spec.get("from", 0)
        levels = found.get("levels")
        top = len(levels) if isinstance(levels, list) else 0
        is_int = lambda v: isinstance(v, int) and not isinstance(v, bool)  # noqa: E731
        if not (is_int(level) and is_int(start) and 0 <= start < level <= top):
            _err(errors, "schema", where, f"강화 {ref}의 가격은 from(시작 단계, 기본 0) < level ≤ {top}인 정수로 적습니다: from {start!r}, level {level!r}")
            return None
        costs = cr.level_costs(levels, found.get("replace_cost", 0.0))
        before = costs[start - 1]["expected_cost"] if start else 0.0  # 이미 산 단계까지의 비용은 빼고 그다음 단계부터
        return round(costs[level - 1]["expected_cost"] - before, 4), currency
    if found is None:
        _err(errors, "unknown_recipe", where, f"강화·합성 데이터에 없는 합성입니다: {ref}")
        return None
    if cr.check_recipe(found, []) is None:
        _invalid("합성", ref, where, errors)
        return None
    if _cut(found, "합성", ref, where, warnings):
        return None
    return round(found.get("cost", 0) / found.get("success", 1.0), 4), currency


# ---------- 시점 ----------
def _stage_at(stages: list[dict], t: float) -> str:
    """판 안 시점 t가 속한 단계(경계는 다음 단계)."""
    acc = 0.0
    for s in stages:
        if t < acc + s["duration"] - EPS:
            return s["id"]
        acc += s["duration"]
    return stages[-1]["id"] if stages else ""

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
             upgrades: dict | None = None, crafting: dict | None = None) -> dict:
    """enemies·items·upgrades: 함께 읽은 데이터의 {id: 항목}, drop_tables: 아이템 데이터의 드랍 테이블, crafting: 강화·합성 파일 내용.
    쓰는 데이터가 None이면 그 부분은 미확인으로 센다."""
    errors: list = []
    warnings: list = []
    settings = read_settings(data, errors)
    raw_stages, raw_buys = data.get("stages"), data.get("purchases", [])
    if not isinstance(raw_stages, list):
        _err(errors, "schema", "stages", "stages(단계 배열)가 필요합니다.")
        raw_stages = []
    if not isinstance(raw_buys, list):
        _err(errors, "schema", "purchases", "purchases(구매 계획 배열)는 배열이어야 합니다.")
        raw_buys = []
    stages = [s for _, s in c.check_identity(raw_stages, "stages", errors) if c.check_common(s, s["id"], errors)]
    buys = [p for _, p in c.check_identity(raw_buys, "purchases", errors) if c.check_common(p, p["id"], errors)]
    refs = {"enemies": enemies, "items": items, "drop_tables": drop_tables, "upgrades": upgrades, "crafting": crafting,
            "pools": rarity_pools(items) if items is not None else {}, "sell_cache": {}}
    missing: set = set()
    timeline: list = []
    rows: list = []
    leftover: dict = {}
    if settings is not None:
        cur = settings["currencies"]
        complete = True
        for s in (x for x in stages if c.is_active(x)):
            if not _num(s.get("duration"), strict=True):
                _err(errors, "schema", s["id"], f"duration(단계 길이, {settings['time_unit']})은 0보다 큰 수여야 합니다: {s.get('duration')!r}")
                complete = False
                continue
            before = len(missing)
            src = _stage_income(s, settings, refs, errors, warnings, missing)
            if src is None or len(missing) > before:
                complete = False
                continue
            timeline.append({"id": s["id"], "name": s.get("name"), "duration": s["duration"], "sources": src})
        acc = {k: 0.0 for k in cur}
        for st in timeline:
            st["income"] = {k: round(sum(v.values()), 4) for k, v in st["sources"].items() if sum(v.values()) > 0}
            st["rate"] = {k: round(v / st["duration"], 4) for k, v in st["income"].items()}
            for k, v in st["income"].items():
                acc[k] += v
            st["cumulative"] = {k: round(v, 4) for k, v in acc.items() if v > 0}
        per_run = acc
        spent = {k: 0.0 for k in cur}
        starts, t0 = {}, 0.0
        for st in timeline:
            starts[st["id"]] = t0
            t0 += st["duration"]
        stage_ids = {s["id"] for s in stages}
        last_time = 0.0
        owned: set = set()
        for p in (x for x in buys if c.is_active(x)):
            target = p.get("target")
            if target is not None and not c.valid_range(target):
                _err(errors, "schema", p["id"], "target은 [최소, 최대]이고 한쪽은 null로 비울 수 있습니다(최소 ≤ 최대).")
                target = None
            after = p.get("after")
            if after is not None and after not in stage_ids:
                _err(errors, "unknown_stage", p["id"], f"after에 적은 단계가 stages에 없습니다: {after!r}")
                continue
            got = _price(p, settings, refs, errors, warnings, missing)
            if got is None:
                continue
            price, currency = got
            if after is not None and cur[currency].get("carry"):
                _err(errors, "schema", p["id"], "after(파는 단계)는 판 안 재화의 구매에만 씁니다. 판 사이 재화는 판 단위로 셉니다.")
                continue
            ref_up = (p.get("price") or {}).get("upgrade")
            if ref_up and refs["upgrades"] is not None:
                reqs = refs["upgrades"][ref_up].get("requires") or []
                lacking = [x for x in reqs if isinstance(x, str) and x not in owned] if isinstance(reqs, list) else []
                if lacking:
                    _err(warnings, "requirement_missing", p["id"],
                         f"{p['id']}의 영구 강화 {ref_up}는 {', '.join(lacking)}가 먼저 필요한데 계획에서 그보다 앞에 있습니다.", owner=p["id"])
                owned.add(ref_up)
            row = {"id": p["id"], "name": p.get("name"), "currency": currency, "price": round(price, 4),
                   "at": None, "stage": None, "runs": None, "affordable": True, "out_of_range": False}
            rows.append(row)
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
                    at = max(hit[0], starts.get(after, 0.0), last_time)
                    last_time = at
                    row["at"] = round(at, 4)
                    row["stage"] = _stage_at(timeline, at)
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
                     f"{p['id']}를 {measure:g}{unit}에 삽니다. 목표 {c.range_text(target)}{unit}를 벗어납니다.", owner=p["id"])
        if complete:
            for k in cur:
                if cur[k].get("carry") or per_run[k] <= 0:
                    continue
                left = per_run[k] - spent[k]
                share = left / per_run[k]
                leftover[k] = {"amount": round(left, 4), "share": round(share, 4)}
                if settings["leftover_max"] is not None and share > settings["leftover_max"] + EPS:
                    _err(warnings, "currency_piles_up", f"economy.currencies.{k}",
                         f"한 판 수입 {per_run[k]:g} {k} 중 {share:.0%}({left:g})가 구매 계획 뒤에도 남습니다(허용 {settings['leftover_max']:.0%}). "
                         "쓸 곳을 늘리거나 수입을 줄입니다.")
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
        "time_unit": settings["time_unit"] if settings else "초",
        "currencies": {k: {"name": v.get("name"), "carry": bool(v.get("carry"))} for k, v in (settings or {}).get("currencies", {}).items()},
        "stages": timeline,
        "purchases": rows,
        "leftover": leftover,
        "unchecked": len(missing),
        "unchecked_kinds": sorted(missing),
        "errors": errors,
        "warnings": warnings,
    }


# ---------- 출력 ----------
def _fmt(v) -> str:
    if v is None:
        return "–"
    return f"{v:g}" if isinstance(v, float) else str(v)


def print_extra(result: dict) -> None:
    unit = result["time_unit"]
    for st in result["stages"]:
        inc = " · ".join(f"{k} {_fmt(v)}" for k, v in st["income"].items()) or "수입 없음"
        print(f"단계 {st['id']} ({_fmt(st['duration'])}{unit}): {inc} · 누적 " + (" · ".join(f"{k} {_fmt(v)}" for k, v in st["cumulative"].items()) or "–"))
    for p in result["purchases"]:
        when = f"{_fmt(p['runs'])}번째 판" if result["currencies"].get(p["currency"], {}).get("carry") else (
            f"{_fmt(p['at'])}{unit} ({p['stage']})" if p["at"] is not None else ("살 수 없음" if not p["affordable"] else "–"))
        print(f"구매 {p['id']}: {_fmt(p['price'])} {p['currency']} → {when}" + (" ⚠" if p["out_of_range"] or not p["affordable"] else ""))
    for k, left in result["leftover"].items():
        print(f"판 끝에 남는 {k}: {_fmt(left['amount'])} (한 판 수입의 {left['share']:.0%})")
    if result["unchecked"]:
        print("재화 흐름 미확인: " + ", ".join(UNCHECKED_LABEL[k] for k in result["unchecked_kinds"]) + " 데이터를 함께 검사하지 않았거나 읽지 못함")


def table(data: dict, result: dict, ids: list[str] | None = None) -> str:
    """대화에 붙일 재화 흐름 표(마크다운). --ids는 컨셉 비교표용이라 여기서는 쓰지 않는다."""
    unit = result["time_unit"]
    rows = [f"| 단계 | 길이 | 수입 | {unit}당 | 누적 |", "|---|---|---|---|---|"]
    for st in result["stages"]:
        rows.append("| " + " | ".join((st["id"], _fmt(st["duration"]) + unit, " · ".join(f"{k} {_fmt(v)}" for k, v in st["income"].items()) or "–",
                                        " · ".join(f"{k} {_fmt(v)}" for k, v in st["rate"].items()) or "–",
                                        " · ".join(f"{k} {_fmt(v)}" for k, v in st["cumulative"].items()) or "–")) + " |")
    rows += ["", f"| 구매 | 재화 | 가격 | 시점({unit}) | 단계 | 판 | 판정 |", "|---|---|---|---|---|---|---|"]
    for p in result["purchases"]:
        verdict = "살 수 없음" if not p["affordable"] else ("목표 이탈" if p["out_of_range"] else "–")
        rows.append("| " + " | ".join((p["id"], p["currency"], _fmt(p["price"]), _fmt(p["at"]), p["stage"] or "–", _fmt(p["runs"]), verdict)) + " |")
    rows += ["", "기대값 계산입니다. 처치 수·드랍 횟수는 기획 가정이며, 실제 체감이나 재미를 판정하지 않습니다."]
    return "\n".join(rows)


def print_counts(result: dict) -> None:
    tail = f"오류 {len(result['errors'])} · 경고 {len(result['warnings'])}"
    if result.get("acknowledged"):
        tail += f" · 확인한 경고 {len(result['acknowledged'])}"
    print(f"단계 {len(result['stages'])}개 · 구매 {len(result['purchases'])}개 · {tail}")
