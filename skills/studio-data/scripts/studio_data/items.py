"""아이템 데이터와 드랍 테이블을 결정적으로 검사한다. 형식: progression-economy/references/data-format.md"""
from __future__ import annotations

from pathlib import Path

from . import common as c


def load(path: Path) -> dict:
    kind, data = c.load_dataset(Path(path), expected="items")
    if kind not in (None, "items") or "items" not in data:
        raise ValueError("아이템 데이터가 아닙니다 (최상위에 items 배열이 필요합니다).")
    return data


def budget(item: dict, weights: dict) -> float:
    return c.weighted(item, weights)


def check_schema(items: list, errors: list) -> list[dict]:
    valid = []
    for _, item in c.check_identity(items, "items", errors):
        where, ok = item["id"], True
        if not isinstance(item.get("slot"), str) or not item["slot"]:
            errors.append({"code": "schema", "where": where, "message": "slot이 필요합니다."})
            ok = False
        tier = item.get("tier")
        if not (isinstance(tier, int) and not isinstance(tier, bool) and tier >= 1):
            errors.append({"code": "schema", "where": where, "message": f"tier는 1 이상의 정수여야 합니다: {tier!r}"})
            ok = False
        price = item.get("price")
        if price is not None and not (c.is_number(price) and price >= 0):
            errors.append({"code": "schema", "where": where, "message": f"price는 0 이상의 수여야 합니다: {price!r}"})
            ok = False
        ok = c.check_stats(item, where, errors) and ok
        ok = c.check_common(item, where, errors) and ok
        if ok:
            valid.append(item)
    return valid


def check_tiers(items: list[dict], weights: dict, warnings: list) -> dict:
    """slot별로 티어 평균 스탯 예산이 줄어들지 않는지, 하위 티어 전부보다 약한 아이템이 없는지 본다."""
    summary: dict = {}
    by_slot: dict = {}
    for it in items:
        by_slot.setdefault(it["slot"], {}).setdefault(it["tier"], []).append(it)
    for slot, tiers in sorted(by_slot.items()):
        means = {t: sum(budget(i, weights) for i in its) / len(its) for t, its in sorted(tiers.items())}
        summary[slot] = {str(t): round(m, 4) for t, m in means.items()}
        ordered = sorted(means)
        for lo, hi in zip(ordered, ordered[1:]):
            if means[hi] < means[lo]:
                warnings.append({"code": "tier_inversion", "where": slot,
                                 "message": f"티어 {hi} 평균 예산 {means[hi]:.4g} < 티어 {lo} 평균 {means[lo]:.4g}"})
        for t in ordered:
            lower = [budget(i, weights) for lt in ordered if lt < t for i in tiers[lt]]
            if not lower:
                continue
            for it in tiers[t]:
                if budget(it, weights) < min(lower):
                    warnings.append({"code": "tier_inversion", "where": it["id"],
                                     "message": f"티어 {t}인데 하위 티어 어떤 아이템보다도 예산이 낮습니다 ({budget(it, weights):.4g} < {min(lower):.4g}, 하위 최고 {max(lower):.4g})."})
    return summary


def dominates(b: dict, a: dict) -> bool:
    keys = set(a.get("stats", {})) | set(b.get("stats", {}))
    sa, sb = a.get("stats", {}), b.get("stats", {})
    if any(sb.get(k, 0) < sa.get(k, 0) for k in keys):
        return False
    pa, pb = a.get("price"), b.get("price")
    if pa is not None and pb is not None and pb > pa:
        return False
    if b["tier"] > a["tier"]:
        return False
    strictly = any(sb.get(k, 0) > sa.get(k, 0) for k in keys)
    cheaper = pa is not None and pb is not None and pb < pa
    lower_tier = b["tier"] < a["tier"]
    return strictly or cheaper or lower_tier


def check_dominance(items: list[dict], warnings: list) -> list[str]:
    """완전 열위: 같은 slot에서 다른 아이템이 모든 스탯 이상, 가격 이하, 티어 이하이고 하나라도 더 나은 경우."""
    not_assessed = sorted(i["id"] for i in items if i.get("unique_effect"))
    comparable = [i for i in items if not i.get("unique_effect")]
    for a in comparable:
        for b in comparable:
            if a is b or a["slot"] != b["slot"]:
                continue
            if dominates(b, a):
                warnings.append({"code": "dominated", "where": a["id"],
                                 "message": f"같은 slot의 '{b['id']}'가 모든 면에서 같거나 낫습니다. 의도한 시작 아이템이 아니라면 고를 이유가 없습니다."})
                break
    return not_assessed


def capped_expected_draws(p: float, guarantee_after: int | None) -> float | None:
    """확률 p 성공을 처음 얻을 때까지의 기대 시도 수. guarantee_after번째에 확정되면 상한을 둔다."""
    if p <= 0:
        return float(guarantee_after) if guarantee_after else None
    if not guarantee_after:
        return 1.0 / p
    return (1.0 - (1.0 - p) ** guarantee_after) / p


def check_drop_tables(tables: dict, items_by_id: dict, errors: list, warnings: list, invalid_ids: set | None = None) -> dict:
    """invalid_ids: 파일에는 있지만 형식 오류로 검사에서 빠진 아이템. '없는 아이템'으로 잘못 보고하지 않는다."""
    invalid_ids = invalid_ids or set()
    report: dict = {}
    if not isinstance(tables, dict):
        errors.append({"code": "schema", "where": "drop_tables", "message": "drop_tables는 객체여야 합니다."})
        return report
    for tid, table in sorted(tables.items()):
        entries = table.get("entries") if isinstance(table, dict) else None
        if not isinstance(entries, list) or not entries:
            errors.append({"code": "schema", "where": tid, "message": "entries 배열이 필요합니다."})
            continue
        weights, bad, cut_refs = [], False, set()
        for n, e in enumerate(entries):
            w = e.get("weight") if isinstance(e, dict) else None
            if not (c.is_number(w) and w > 0):
                errors.append({"code": "schema", "where": f"{tid}.entries[{n}]", "message": f"weight는 0보다 커야 합니다: {w!r}"})
                bad = True
                continue
            ref = e.get("item")
            if ref is not None and ref in invalid_ids:
                warnings.append({"code": "item_unchecked", "where": f"{tid}.entries[{n}]",
                                 "message": f"아이템 '{ref}'에 형식 오류가 있어 이 테이블의 확률을 계산하지 않았습니다. '{ref}'의 오류를 먼저 고치세요."})
                bad = True
            elif ref is not None and ref not in items_by_id:
                errors.append({"code": "unknown_item", "where": f"{tid}.entries[{n}]", "message": f"없는 아이템입니다: {ref}"})
                bad = True
            if ref is not None and items_by_id.get(ref, {}).get("status") == "cut":
                cut_refs.add(ref)
            if ref is None and "rarity" not in e:
                errors.append({"code": "schema", "where": f"{tid}.entries[{n}]", "message": "item 또는 rarity가 필요합니다."})
                bad = True
            weights.append((e, w))
        for ref in sorted(cut_refs):
            warnings.append({"code": "cut_item_referenced", "where": tid, "message": f"삭제(cut) 상태의 아이템을 드랍합니다: {ref}"})
        if bad:
            continue
        total = sum(w for _, w in weights)
        probs: dict = {}
        for e, w in weights:
            rarity = e.get("rarity") or items_by_id[e["item"]].get("rarity", "unspecified")
            probs[rarity] = probs.get(rarity, 0.0) + w / total
        entry: dict = {"rarity_probability": {k: round(v, 6) for k, v in sorted(probs.items())}}
        pity = table.get("pity")
        if pity:
            target = pity.get("target_rarity")
            n = pity.get("guarantee_after")
            if target not in probs:
                warnings.append({"code": "pity_target_missing", "where": tid, "message": f"천장 대상 희귀도 '{target}'가 테이블에 없습니다."})
            if not (isinstance(n, int) and n >= 1):
                errors.append({"code": "schema", "where": f"{tid}.pity", "message": "guarantee_after는 1 이상의 정수여야 합니다."})
            else:
                p = probs.get(target, 0.0)
                entry["pity"] = {
                    "target_rarity": target,
                    "guarantee_after": n,
                    "expected_draws_without_pity": None if p <= 0 else round(1.0 / p, 4),
                    "expected_draws_with_pity": round(capped_expected_draws(p, n), 4),
                    "probability_pity_triggers": round((1.0 - p) ** (n - 1), 6),
                }
        report[tid] = entry
    return report


def validate(data: dict) -> dict:
    errors: list = []
    warnings: list = []
    raw_items = data.get("items")
    if not isinstance(raw_items, list):
        errors.append({"code": "schema", "where": "items", "message": "items 배열이 필요합니다."})
        raw_items = []
    weights = data.get("stat_weights", {}) or {}
    items = check_schema(raw_items, errors)
    by_id = {i["id"]: i for i in items}
    active = [i for i in items if c.is_active(i)]
    # 고유 효과는 스탯 예산에 들어가지 않으므로 티어 비교와 열위 판정 모두에서 뺀다(판정 제외로 표시).
    tier_summary = check_tiers([i for i in active if not i.get("unique_effect")], weights, warnings)
    not_assessed = check_dominance(active, warnings)
    invalid = {i["id"] for i in raw_items if isinstance(i, dict) and isinstance(i.get("id"), str)} - set(by_id)
    drops = check_drop_tables(data.get("drop_tables", {}) or {}, by_id, errors, warnings, invalid)
    return {
        "kind": "items",
        "count": len(items),
        **c.summary_counts(items),
        "scores": {i["id"]: round(budget(i, weights), 4) for i in items},
        "tier_mean_budget": tier_summary,
        "dominance_not_assessed": not_assessed,
        "drop_tables": drops,
        "errors": errors,
        "warnings": warnings,
    }


def print_extra(result: dict) -> None:
    for tid, t in result["drop_tables"].items():
        pity = t.get("pity")
        line = f"drop {tid}: " + ", ".join(f"{k} {v:.2%}" for k, v in t["rarity_probability"].items())
        if pity:
            line += f" | {pity['target_rarity']} 기대 시도 {pity['expected_draws_with_pity']} (천장 {pity['guarantee_after']})"
        print(line)
    if result["dominance_not_assessed"]:
        print("티어·열위 판정 제외(고유 효과): " + ", ".join(result["dominance_not_assessed"]))
