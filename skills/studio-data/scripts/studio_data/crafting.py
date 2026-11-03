"""강화·합성(data/crafting.json)을 결정적으로 검사하고 계산한다.

강화(enhance): 단계마다 비용·성공률·실패 시 처리(그대로 / 한 단계 하락 / 파괴)를 두고, 0단계에서 각 단계까지의
기대 비용과 기대 시도 수를 계산한다. 스탯 예산(budget)이 있으면 최고 단계까지 강화한 아이템이 다음 티어를 넘는지 본다.
합성(recipes): 특정 아이템 레시피와, 조건에 맞는 아이템을 합쳐 조건에 맞는 아이템 중 하나를 얻는 무작위 합성을 함께 다룬다.
재료와 결과의 가치(예산) 비율, 같은 아이템이 늘어나는 고리, 어떤 경로로도 얻을 수 없는 아이템을 찾는다.
기대값 계산이며 재미나 실제 경제 체감을 판정하지 않는다. 형식: crafting-balance/references/crafting-format.md
"""
from __future__ import annotations

import math

from . import budget as bg
from . import common as c
from .common import add_issue as _err

ON_FAIL = ("keep", "down", "destroy")
ON_FAIL_LABEL = {"keep": "그대로", "down": "한 단계 하락", "destroy": "파괴"}
LOOP_EPSILON = 1e-9
VALUE_SKIPPED = {
    "no_items": "아이템 데이터를 함께 검사하지 않았거나 읽지 못함",
    "no_budget": "스탯 예산(budget.json)이 없거나 형식이 틀림",
    "no_items_side": "스탯 예산에 아이템 쪽(budget.items)이 없거나 그 설정이 틀림",
}


def _text(v) -> bool:
    return isinstance(v, str) and v.strip() != ""


def match_items(items: dict, filt: dict) -> list[str]:
    """조건 {필드: 값}에 모두 맞는 활성 아이템 id."""
    return sorted(i for i, e in items.items() if c.is_active(e) and all(e.get(k) == v for k, v in filt.items()))


# ---------- 강화 ----------
def level_costs(levels: list[dict], replace_cost: float = 0.0) -> list[dict]:
    """0단계에서 각 단계까지의 기대 비용·기대 시도 수.
    한 단계 오르는 데 드는 기대값 x_k: 그대로면 c/p, 하락이면 (c + (1−p)·x_{k−1})/p,
    파괴면 (c + (1−p)·(대체 비용 + 0→k 누적))/p. 시도 수는 비용 1, 대체 비용 0으로 같은 식."""
    out, steps, tries, cum_bonus = [], [], [], 0.0
    for k, lv in enumerate(levels):
        p, cost, fail = lv.get("success", 1.0), lv["cost"], lv.get("on_fail", "keep")
        if fail == "down" and k > 0:
            x = (cost + (1 - p) * steps[k - 1]) / p
            a = (1 + (1 - p) * tries[k - 1]) / p
        elif fail == "destroy":
            x = (cost + (1 - p) * (replace_cost + sum(steps))) / p
            a = (1 + (1 - p) * sum(tries)) / p
        else:
            x, a = cost / p, 1 / p
        steps.append(x)
        tries.append(a)
        cum_bonus += lv.get("bonus_pct", 0.0)
        out.append({"level": k + 1, "cost": cost, "success": p, "on_fail": fail, "bonus_pct": round(cum_bonus, 4),
                    "expected_cost": round(sum(steps), 4), "expected_attempts": round(sum(tries), 4)})
    return out


def check_track(t: dict, errors: list) -> bool:
    where, ok = t["id"], c.check_common(t, t["id"], errors)
    filt = t.get("applies_to")
    ids = t.get("items")
    if filt is not None and ids is not None:
        _err(errors, "schema", where, "강화 대상은 applies_to와 items 중 하나만 씁니다. 둘을 함께 쓰면 어느 쪽인지 모호합니다.")
        ok = False
    elif not ((isinstance(filt, dict) and filt) or (isinstance(ids, list) and ids and all(_text(x) for x in ids))):
        _err(errors, "schema", where, "강화 대상이 필요합니다: applies_to {필드: 값} 또는 items [id, ...].")
        ok = False
    levels = t.get("levels")
    if not (isinstance(levels, list) and levels):
        _err(errors, "schema", where, "levels(단계 배열)가 1개 이상 필요합니다.")
        return False
    destroy = False
    for n, lv in enumerate(levels, start=1):
        if not (isinstance(lv, dict) and c.is_number(lv.get("cost")) and lv["cost"] >= 0):
            _err(errors, "schema", where, f"{n}단계: cost(0 이상의 수)가 필요합니다.")
            ok = False
            continue
        p = lv.get("success", 1.0)
        if not (c.is_number(p) and 0 < p <= 1):
            _err(errors, "schema", where, f"{n}단계: success는 0 초과 1 이하의 확률입니다: {p!r}")
            ok = False
        if lv.get("on_fail", "keep") not in ON_FAIL:
            _err(errors, "schema", where, f"{n}단계: on_fail은 {', '.join(ON_FAIL)} 중 하나입니다: {lv.get('on_fail')!r}")
            ok = False
        destroy = destroy or lv.get("on_fail") == "destroy"
        if "bonus_pct" in lv and not (c.is_number(lv["bonus_pct"]) and lv["bonus_pct"] >= 0):
            _err(errors, "schema", where, f"{n}단계: bonus_pct는 0 이상의 비율입니다(0.1 = 기본 스탯의 10%).")
            ok = False
    if destroy and not (c.is_number(t.get("replace_cost")) and t["replace_cost"] >= 0):
        _err(errors, "schema", where, "파괴(destroy) 단계가 있으면 replace_cost(파괴된 아이템을 다시 구하는 비용)가 필요합니다.")
        ok = False
    return ok


# ---------- 합성 ----------
def _side_of(spec, where: str, label: str, errors: list) -> dict | None:
    if not (isinstance(spec, dict) and (_text(spec.get("item")) or (isinstance(spec.get("match"), dict) and spec["match"]))):
        _err(errors, "schema", where, f"{label}에는 item(아이템 id)이나 match({{필드: 값}})가 필요합니다.")
        return None
    count = spec.get("count", 1)
    if not (isinstance(count, int) and not isinstance(count, bool) and count >= 1):
        _err(errors, "schema", where, f"{label}의 count는 1 이상의 정수입니다: {count!r}")
        return None
    return {"item": spec.get("item"), "match": spec.get("match"), "count": count}


def check_recipe(r: dict, errors: list) -> dict | None:
    where, ok = r["id"], c.check_common(r, r["id"], errors)
    raw = r.get("inputs")
    if not (isinstance(raw, list) and raw):
        _err(errors, "schema", where, "inputs(재료 배열)가 1개 이상 필요합니다.")
        return None
    inputs = [_side_of(x, where, f"재료 {n}", errors) for n, x in enumerate(raw, start=1)]
    output = _side_of(r.get("output"), where, "결과(output)", errors)
    cost, p = r.get("cost", 0), r.get("success", 1.0)
    if not (c.is_number(cost) and cost >= 0):
        _err(errors, "schema", where, f"cost는 0 이상의 수입니다: {cost!r}")
        ok = False
    if not (c.is_number(p) and 0 < p <= 1):
        _err(errors, "schema", where, f"success는 0 초과 1 이하의 확률입니다: {p!r}")
        ok = False
    if None in inputs or output is None or not ok:
        return None
    return {"id": r["id"], "inputs": inputs, "output": output, "cost": cost, "success": p}


def _candidates(side: dict, items: dict, where: str, errors: list, warnings: list) -> list[str] | None:
    """재료·결과 한 칸이 가리키는 활성 아이템. 없는 id·빈 조건은 오류, 삭제 아이템은 경고하고 None."""
    if side["item"]:
        e = items.get(side["item"])
        if e is None:
            _err(errors, "unknown_item", where, f"아이템 데이터에 없는 id입니다: {side['item']}")
            return None
        if not c.is_active(e):
            _err(warnings, "cut_referenced", where, f"삭제(cut)된 아이템 {side['item']}를 씁니다. 이 레시피는 계산에서 뺍니다.", owner=where)
            return None
        return [side["item"]]
    found = match_items(items, side["match"])
    if not found:
        _err(errors, "match_empty", where, f"조건 {side['match']}에 맞는 아이템이 없습니다.")
        return None
    return found


def _slot_value(ids: list[str], value, cheapest: bool) -> float | None:
    """한 칸의 가치. 재료 칸은 맞는 것 중 가장 싼 것(플레이어는 싼 것을 넣는다), 결과 칸은 평균(무작위로 하나가 나온다).
    하나라도 잴 수 없으면(고유 효과, 원가 없는 스탯) None."""
    vals = [value(i) for i in ids]
    if None in vals:
        return None
    return min(vals) if cheapest else sum(vals) / len(vals)


def _class_node(filt: dict) -> str:
    return "[" + ", ".join(f"{k}={v}" for k, v in filt.items()) + " 아무거나]"


def _best_gains(edges: dict) -> dict:
    """노드 쌍마다 가장 좋은 수율(곱). 늘어나는 고리가 없을 때만 부른다(그래야 값이 유한하다)."""
    nodes = sorted({u for u, _ in edges} | {v for _, v in edges})
    best = {(u, v): w for (u, v), w in edges.items()}
    for k in nodes:
        for i in nodes:
            ik = best.get((i, k))
            if not ik:
                continue
            for j in nodes:
                kj = best.get((k, j))
                if kj and ik * kj > best.get((i, j), 0.0):
                    best[(i, j)] = ik * kj
    return best


def _random_loops(groups: list, edges: dict, members: dict) -> tuple[str, str, float] | None:
    """무작위 결과를 거치는 고리. 결과마다 처음(재료) 노드로 돌아오는 최선 수율을 구해 평균하고, 합성 수율을 곱한다.
    groups: [(합성 id, 재료 노드, 결과 아이템들, 수율)]. 결과가 재료 칸의 조건에 맞으면 바로 돌아온 것(수율 1)으로 본다."""
    best = _best_gains(edges)
    for rid, src, outs, w in groups:
        back = [1.0 if v == src or v in members.get(src, ()) else best.get((v, src), 0.0) for v in outs]
        gain = w * sum(back) / len(back)
        if gain > 1 + LOOP_EPSILON:
            return rid, src, gain
    return None


def _find_loop(edges: dict) -> tuple[list[str], float] | None:
    """같은 아이템이 늘어나는 고리(곱한 수율 > 1)를 하나 찾는다. 벨만-포드로 −ln(수율)의 음수 고리를 찾는다."""
    nodes = sorted({u for u, _ in edges} | {v for _, v in edges})
    dist = {n: 0.0 for n in nodes}
    pred: dict = {}
    last = None
    for _ in range(len(nodes)):
        last = None
        for (u, v), w in edges.items():
            if dist[u] - math.log(w) < dist[v] - LOOP_EPSILON:
                dist[v] = dist[u] - math.log(w)
                pred[v] = u
                last = v
        if last is None:
            return None
    for _ in range(len(nodes)):  # 고리 안으로 들어간다
        last = pred[last]
    cycle, node = [last], pred[last]
    while node != last:
        cycle.append(node)
        node = pred[node]
    cycle.reverse()
    gain = 1.0
    for a, b in zip(cycle, cycle[1:] + cycle[:1]):
        gain *= edges[(a, b)]
    return cycle, gain


# ---------- 검사 ----------
def validate(data: dict, items: dict | None = None, drop_tables: dict | None = None, budget: dict | None = None) -> dict:
    """items: 함께 읽은 아이템 {id: 항목}, drop_tables: 아이템 데이터의 드랍 테이블, budget: budget.read_settings() 결과.
    items가 None이면 참조·가치·획득 경로를 확인하지 못한 것으로 센다. budget이 없으면 가치 비교만 하지 않는다."""
    errors: list = []
    warnings: list = []
    acknowledged: list = []
    cfg = data.get("crafting")
    if not isinstance(cfg, dict):
        _err(errors, "schema", "crafting", "crafting 객체가 필요합니다(provenance, other_sources).")
        cfg = {}
    raw_tracks, raw_recipes = data.get("enhance", []), data.get("recipes", [])
    for key, raw in (("enhance", raw_tracks), ("recipes", raw_recipes)):
        if not isinstance(raw, list):
            _err(errors, "schema", key, f"{key}는 배열이어야 합니다.")
    tracks = [t for _, t in c.check_identity(raw_tracks if isinstance(raw_tracks, list) else [], "enhance", errors) if check_track(t, errors)]
    recipe_entries = [r for _, r in c.check_identity(raw_recipes if isinstance(raw_recipes, list) else [], "recipes", errors)]
    recipes = [x for x in (check_recipe(r, errors) for r in recipe_entries) if x]
    item_spec = (budget or {}).get("sides", {}).get("items")
    tol = (budget or {}).get("tolerance", bg.DEFAULT_TOLERANCE)
    unchecked = 0 if items is not None else 1
    value_skipped = "no_items" if items is None else ("no_budget" if budget is None else (None if item_spec else "no_items_side"))
    if value_skipped is None:
        def value(i: str) -> float | None:
            # 고유 효과의 값어치는 스탯에 없다(스탯 예산도 비교에서 뺀다)
            return None if items[i].get("unique_effect") else bg.entry_budget(item_spec, items[i])
    else:
        value = None

    track_info: dict = {}
    for t in (x for x in tracks if c.is_active(x)):
        info = {"items": [], "levels": level_costs(t["levels"], t.get("replace_cost", 0.0)), "overtakes": []}
        track_info[t["id"]] = info
        if items is None:
            continue
        if "items" in t:
            info["items"] = [i for i in t["items"] if i in items and c.is_active(items[i])]
            for i in t["items"]:
                if i not in items:
                    _err(errors, "unknown_item", t["id"], f"아이템 데이터에 없는 id입니다: {i}")
        else:
            info["items"] = match_items(items, t["applies_to"])
            if not info["items"]:
                _err(errors, "match_empty", t["id"], f"조건 {t['applies_to']}에 맞는 아이템이 없습니다.")
        if value is None:
            continue
        top = info["levels"][-1]["bonus_pct"]
        by = item_spec["curve"]["by"]
        for i in info["items"]:
            e, b = items[i], value(i)
            at = e.get(by)
            if b is None or e.get("unique_effect") or not c.is_number(at):
                continue
            if not any(items[j].get(by) == at + 1 for j in info["items"]):
                continue  # 같은 강화 대상 안에 다음 단계가 없으면 넘을 대상이 없다
            nxt = bg.expected_budget(item_spec, e, at + 1)
            if nxt and b * (1 + top) > nxt * (1 + tol):
                info["overtakes"].append(i)
        if info["overtakes"]:
            _err(warnings, "enhance_overtakes_tier", t["id"],
                 f"최고 단계(+{len(t['levels'])}, 기본의 {1 + top:.0%})까지 강화하면 다음 {by}의 기대 예산을 넘는 아이템: "
                 + ", ".join(info["overtakes"][:6]) + (" …" if len(info["overtakes"]) > 6 else ""), owner=t["id"])

    recipe_info: dict = {}
    edges: dict = {}
    groups: list = []
    members: dict = {}
    usable: list = []
    by_id = {x["id"]: x for x in recipe_entries}
    for r in recipes:
        if not c.is_active(by_id[r["id"]]):
            continue
        info = {"value_in": None, "value_out": None, "value_ratio": None, "value_note": None, "cost": r["cost"], "success": r["success"],
                "outcomes": None, "crafts_for_specific": None, "inputs_for_specific": None}
        recipe_info[r["id"]] = info
        if items is None:
            continue
        ins = [_candidates(x, items, r["id"], errors, warnings) for x in r["inputs"]]
        outs = _candidates(r["output"], items, r["id"], errors, warnings)
        if None in ins or outs is None:
            continue
        usable.append((r, ins, outs))
        n_out = len(outs)
        info["outcomes"] = n_out
        crafts = n_out / (r["output"]["count"] * r["success"])
        info["crafts_for_specific"] = round(crafts, 4)
        info["inputs_for_specific"] = round(crafts * sum(x["count"] for x in r["inputs"]), 4)
        if len(r["inputs"]) == 1:  # 재료가 한 종류인 변환만 고리를 본다(여러 재료면 다른 재료가 함께 든다)
            spec = r["inputs"][0]
            src = spec["item"] or _class_node(spec["match"])
            if not spec["item"]:  # 조건 재료: 맞는 아이템이면 무엇이든 그 칸으로 쓸 수 있다
                members[src] = set(ins[0])
                for m in ins[0]:
                    edges[(m, src)] = 1.0
            w = r["output"]["count"] * r["success"] / spec["count"]
            if n_out == 1:
                edges[(src, outs[0])] = max(edges.get((src, outs[0]), 0.0), w)
            else:
                groups.append((r["id"], src, outs, w))
        if value is not None:
            parts = [_slot_value(cands, value, cheapest=True) for cands in ins]
            out_v = _slot_value(outs, value, cheapest=False)
            touched = [i for cands in ins + [outs] for i in cands]
            if any(items[i].get("unique_effect") for i in touched):
                info["value_note"] = "고유 효과 아이템이 있어 가치를 비교하지 않음"
            elif None in parts or out_v is None:
                info["value_note"] = "원가 없는 스탯이 있어 가치를 비교하지 않음"
            if None not in parts and out_v is not None and sum(x["count"] * v for x, v in zip(r["inputs"], parts)) > 0:
                info["value_in"] = round(sum(x["count"] * v for x, v in zip(r["inputs"], parts)), 4)
                info["value_out"] = round(r["output"]["count"] * out_v * r["success"], 4)
                info["value_ratio"] = round(info["value_out"] / info["value_in"], 4)
                if info["value_ratio"] < 1 - tol:
                    _err(warnings, "recipe_loses_value", r["id"],
                         f"재료 가치 {info['value_in']:g}로 결과 가치 {info['value_out']:g}(성공률 반영)를 얻습니다({info['value_ratio']:.0%}). "
                         "합성할 이유가 약합니다.", owner=r["id"])
    loop = _find_loop(edges) if edges else None
    if loop:
        cycle, gain = loop
        _err(errors, "value_loop", "recipes",
             f"합성을 돌면 아이템이 늘어납니다: {' → '.join(cycle + cycle[:1])} (한 바퀴에 {gain:.2f}배). 수량이나 성공률을 고치세요.")
    elif groups:
        found = _random_loops(groups, edges, members)
        if found:
            rid, src, gain = found
            _err(errors, "value_loop", "recipes",
                 f"합성을 돌면 아이템이 늘어납니다: {src} → {rid}(무작위 결과) → … → {src} (기대 {gain:.2f}배). 결과마다 되돌리는 합성의 수량이나 성공률을 고치세요.")

    obtainable: list = []
    unobtainable: list = []
    sources = cfg.get("other_sources", {})
    if not (isinstance(sources, dict) and all(_text(v) for v in sources.values())):
        _err(errors, "schema", "crafting.other_sources", "other_sources는 {아이템 id: 얻는 곳(상점, 시작 장비 등)}이어야 합니다.")
        sources = {}
    if items is not None and drop_tables is None:
        unchecked += 1
    elif items is not None:
        for i in sources:
            if i not in items:
                _err(errors, "unknown_item", "crafting.other_sources", f"아이템 데이터에 없는 id입니다: {i}")
        have = {i for i in sources if i in items}
        rarities = set()
        for table in drop_tables.values():
            for e in (table.get("entries") or []) if isinstance(table, dict) else []:
                if isinstance(e, dict) and isinstance(e.get("item"), str):
                    have.add(e["item"])
                elif isinstance(e, dict) and e.get("rarity") is not None:
                    rarities.add(e["rarity"])
        have |= {i for i, e in items.items() if e.get("rarity") in rarities}
        changed = True
        while changed:
            changed = False
            for r, ins, outs in usable:
                if all(any(x in have for x in cands) for cands in ins) and not set(outs) <= have:
                    have |= set(outs)
                    changed = True
        active = sorted(i for i, e in items.items() if c.is_active(e))
        obtainable = [i for i in active if i in have]
        unobtainable = [i for i in active if i not in have]
        open_ = []
        for i in unobtainable:
            reason = c.ack_reason(items[i], "unobtainable")  # 일부러 얻는 곳이 없는 아이템은 그 아이템에서 확인한다
            if reason:
                acknowledged.append({"code": "unobtainable", "where": i, "owner": f"items:{i}", "reason": reason,
                                     "message": f"{i}는 드랍·합성·other_sources 어디서도 얻을 수 없습니다."})
            else:
                open_.append(i)
        if open_:
            _err(warnings, "unobtainable", "crafting",
                 f"드랍·합성·other_sources 어디서도 얻을 수 없는 아이템 {len(open_)}개: " + ", ".join(open_[:8])
                 + (" …" if len(open_) > 8 else "") + ". 시작 장비·상점이면 crafting.other_sources에, 일부러 없으면 그 아이템의 acknowledged에 적습니다.")

    summary = c.summary_counts(tracks + recipe_entries)
    prov = cfg.get("provenance")
    if prov is not None:
        c.check_common({"provenance": prov}, "crafting", errors)
    if c.provenance_kind({"provenance": prov}) in ("assumed", "unspecified") and (tracks or recipes):
        summary["unverified"] = ["crafting(강화·합성 수치)"] + summary["unverified"]
    return {
        "kind": "crafting",
        "count": len(tracks) + len(recipe_entries),
        **summary,
        "tracks": track_info,
        "recipes": recipe_info,
        "obtainable": obtainable,
        "unobtainable": unobtainable,
        "value_skipped": value_skipped,
        "acknowledged": acknowledged,
        "unchecked": unchecked,
        "unchecked_kinds": ["items"] if items is None else ([] if drop_tables is not None else ["drop_tables"]),
        "errors": errors,
        "warnings": warnings,
    }


# ---------- 출력 ----------
def _fmt(v) -> str:
    if v is None:
        return "–"
    return f"{v:g}" if isinstance(v, float) else str(v)


def print_extra(result: dict) -> None:
    for tid, t in result["tracks"].items():
        last = t["levels"][-1]
        print(f"강화 {tid}: 대상 {len(t['items'])}개 · +{last['level']}까지 기대 비용 {_fmt(last['expected_cost'])} · 기대 시도 {_fmt(last['expected_attempts'])}"
              f" · 보너스 {last['bonus_pct']:.0%}")
    for rid, r in result["recipes"].items():
        ratio = f"가치 {r['value_ratio']:.0%}" if r["value_ratio"] is not None else "가치 –" + (f"({r['value_note']})" if r["value_note"] else "")
        extra = f" · 특정 결과까지 {_fmt(r['crafts_for_specific'])}회" if r["outcomes"] and r["outcomes"] > 1 else ""
        print(f"합성 {rid}: {ratio} · 비용 {_fmt(r['cost'])} · 성공률 {r['success']:.0%}{extra}")
    if result["value_skipped"]:
        print("강화·합성의 가치 비교는 하지 않았습니다: " + VALUE_SKIPPED[result["value_skipped"]])
    if result["unchecked"]:
        print("강화·합성 미확인: " + ", ".join({"items": "아이템 데이터", "drop_tables": "드랍 테이블"}[k] for k in result["unchecked_kinds"])
              + "를 함께 검사하지 않았거나 읽지 못함")


def table(data: dict, result: dict, ids: list[str] | None = None) -> str:
    """대화에 붙일 강화·합성 표(마크다운). --ids는 컨셉 비교표용이라 여기서는 쓰지 않는다."""
    rows = ["| 강화 | 단계 | 성공률 | 실패 시 | 비용 | 누적 보너스 | 0에서 기대 비용 | 기대 시도 |", "|---|---|---|---|---|---|---|---|"]
    for tid, t in result["tracks"].items():
        for lv in t["levels"]:
            rows.append("| " + " | ".join((tid, f"+{lv['level']}", f"{lv['success']:.0%}", ON_FAIL_LABEL[lv["on_fail"]], _fmt(lv["cost"]),
                                            f"{lv['bonus_pct']:.0%}", _fmt(lv["expected_cost"]), _fmt(lv["expected_attempts"]))) + " |")
    rows += ["", "| 합성 | 재료 | 결과 | 가치 비율 | 비용 | 결과 가짓수 | 특정 결과까지 합성 | 특정 결과까지 재료 |", "|---|---|---|---|---|---|---|---|"]
    raw = {r.get("id"): r for r in data.get("recipes", []) if isinstance(r, dict)} if isinstance(data.get("recipes"), list) else {}
    side = lambda s: f"{s.get('count', 1)}× " + (s["item"] if s.get("item") else str(s.get("match")))  # noqa: E731
    for rid, r in result["recipes"].items():
        src = raw.get(rid, {})
        rows.append("| " + " | ".join((rid, ", ".join(side(x) for x in src.get("inputs", [])), side(src.get("output") or {}),
                                        f"{r['value_ratio']:.0%}" if r["value_ratio"] is not None else "–", _fmt(r["cost"]),
                                        _fmt(r["outcomes"]), _fmt(r["crafts_for_specific"]), _fmt(r["inputs_for_specific"]))) + " |")
    rows += ["", "기대값 계산입니다. 가치는 스탯 예산 기준이며, 실제 경제 체감이나 재미를 판정하지 않습니다."]
    return "\n".join(rows)


def print_counts(result: dict) -> None:
    tail = f"오류 {len(result['errors'])} · 경고 {len(result['warnings'])}"
    if result.get("acknowledged"):
        tail += f" · 확인한 경고 {len(result['acknowledged'])}"
    print(f"강화 {len(result['tracks'])}개 · 합성 {len(result['recipes'])}개 · 얻을 수 없는 아이템 {len(result['unobtainable'])}개 · {tail}")
