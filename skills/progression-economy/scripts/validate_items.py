#!/usr/bin/env python3
"""아이템 데이터와 드랍 테이블을 결정적으로 검사한다.

입력: JSON({"items": [...], "stat_weights": {...}, "drop_tables": {...}}) 또는 아이템 CSV.
형식은 skills/progression-economy/references/data-format.md를 따른다. 표준 라이브러리만 사용한다.

종료 코드
  0  오류 없음 (--strict이면 경고도 없음)
  1  오류 있음, 또는 --strict에서 경고 있음
  2  사용법 오류(파일 없음, 파싱 실패)
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

ID_PATTERN = re.compile(r"^[a-z0-9_]+$")
STAT_PREFIX = "stat."


def load(path: Path) -> dict:
    if path.suffix.lower() == ".csv":
        return {"items": _load_csv(path)}
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, list):
        data = {"items": data}
    if not isinstance(data, dict):
        raise ValueError("최상위는 객체 또는 아이템 배열이어야 합니다.")
    return data


def _num(value: str):
    value = value.strip()
    if value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return float(value)


def _load_csv(path: Path) -> list[dict]:
    items = []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            item: dict = {"stats": {}}
            for key, raw in row.items():
                if key is None:
                    continue
                key = key.strip()
                raw = (raw or "").strip()
                if key.startswith(STAT_PREFIX):
                    if raw != "":
                        item["stats"][key[len(STAT_PREFIX):]] = _num(raw)
                elif key in ("tier", "price"):
                    item[key] = _num(raw) if raw else None
                elif key == "unique_effect":
                    item[key] = raw.lower() in ("1", "true", "yes", "y")
                elif raw != "":
                    item[key] = raw
            items.append(item)
    return items


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def check_schema(items: list, errors: list) -> list[dict]:
    valid, seen = [], set()
    for idx, item in enumerate(items):
        where = f"items[{idx}]"
        if not isinstance(item, dict):
            errors.append({"code": "schema", "where": where, "message": "아이템은 객체여야 합니다."})
            continue
        iid = item.get("id")
        if not isinstance(iid, str) or not ID_PATTERN.match(iid):
            errors.append({"code": "schema", "where": where, "message": f"id는 소문자·숫자·밑줄만 씁니다: {iid!r}"})
            continue
        where = iid
        if iid in seen:
            errors.append({"code": "duplicate_id", "where": where, "message": "id가 중복됩니다."})
            continue
        seen.add(iid)
        ok = True
        if not isinstance(item.get("slot"), str) or not item["slot"]:
            errors.append({"code": "schema", "where": where, "message": "slot이 필요합니다."})
            ok = False
        tier = item.get("tier")
        if not (isinstance(tier, int) and not isinstance(tier, bool) and tier >= 1):
            errors.append({"code": "schema", "where": where, "message": f"tier는 1 이상의 정수여야 합니다: {tier!r}"})
            ok = False
        price = item.get("price")
        if price is not None and not (_is_number(price) and price >= 0):
            errors.append({"code": "schema", "where": where, "message": f"price는 0 이상의 수여야 합니다: {price!r}"})
            ok = False
        stats = item.get("stats", {})
        if not isinstance(stats, dict) or not all(isinstance(k, str) and _is_number(v) for k, v in stats.items()):
            errors.append({"code": "schema", "where": where, "message": "stats는 {이름: 수} 형태여야 합니다."})
            ok = False
        if ok:
            valid.append(item)
    return valid


def budget(item: dict, weights: dict) -> float:
    return sum(v * weights.get(k, 1.0) for k, v in item.get("stats", {}).items())


def check_tiers(items: list[dict], weights: dict, warnings: list) -> dict:
    """slot별로 티어 평균 스탯 예산이 줄어들지 않는지 본다."""
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
            floor = max(lower)
            for it in tiers[t]:
                if budget(it, weights) < min(lower):
                    warnings.append({"code": "tier_inversion", "where": it["id"],
                                     "message": f"티어 {t}인데 하위 티어 어떤 아이템보다도 예산이 낮습니다 ({budget(it, weights):.4g} < {min(lower):.4g}, 하위 최고 {floor:.4g})."})
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


def check_drop_tables(tables: dict, items_by_id: dict, errors: list, warnings: list) -> dict:
    report: dict = {}
    if not isinstance(tables, dict):
        errors.append({"code": "schema", "where": "drop_tables", "message": "drop_tables는 객체여야 합니다."})
        return report
    for tid, table in sorted(tables.items()):
        entries = table.get("entries") if isinstance(table, dict) else None
        if not isinstance(entries, list) or not entries:
            errors.append({"code": "schema", "where": tid, "message": "entries 배열이 필요합니다."})
            continue
        weights, bad = [], False
        for n, e in enumerate(entries):
            w = e.get("weight") if isinstance(e, dict) else None
            if not (_is_number(w) and w > 0):
                errors.append({"code": "schema", "where": f"{tid}.entries[{n}]", "message": f"weight는 0보다 커야 합니다: {w!r}"})
                bad = True
                continue
            ref = e.get("item")
            if ref is not None and ref not in items_by_id:
                errors.append({"code": "unknown_item", "where": f"{tid}.entries[{n}]", "message": f"없는 아이템입니다: {ref}"})
                bad = True
            if ref is None and "rarity" not in e:
                errors.append({"code": "schema", "where": f"{tid}.entries[{n}]", "message": "item 또는 rarity가 필요합니다."})
                bad = True
            weights.append((e, w))
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
    tier_summary = check_tiers(items, weights, warnings)
    not_assessed = check_dominance(items, warnings)
    drops = check_drop_tables(data.get("drop_tables", {}) or {}, by_id, errors, warnings)
    return {
        "items": len(items),
        "tier_mean_budget": tier_summary,
        "dominance_not_assessed": not_assessed,
        "drop_tables": drops,
        "errors": errors,
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="아이템 데이터와 드랍 테이블을 검사합니다.")
    ap.add_argument("path", help="items JSON 또는 CSV")
    ap.add_argument("--strict", action="store_true", help="경고도 실패로 처리합니다.")
    ap.add_argument("--json", action="store_true", help="결과를 JSON으로 출력합니다.")
    ap.add_argument("--out", help="JSON 보고서를 이 경로에 저장합니다. 문서에서 [계산: 이 경로]로 인용합니다.")
    args = ap.parse_args(argv)
    try:
        data = load(Path(args.path))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"입력을 읽을 수 없습니다: {exc}", file=sys.stderr)
        return 2
    result = validate(data)
    failed = bool(result["errors"]) or (args.strict and bool(result["warnings"]))
    result["status"] = "fail" if failed else "pass"
    result["source"] = args.path
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for e in result["errors"]:
            print(f"error [{e['code']}] {e['where']}: {e['message']}")
        for w in result["warnings"]:
            print(f"warning [{w['code']}] {w['where']}: {w['message']}")
        for tid, t in result["drop_tables"].items():
            pity = t.get("pity")
            line = f"drop {tid}: " + ", ".join(f"{k} {v:.2%}" for k, v in t["rarity_probability"].items())
            if pity:
                line += f" | {pity['target_rarity']} 기대 시도 {pity['expected_draws_with_pity']} (천장 {pity['guarantee_after']})"
            print(line)
        if result["dominance_not_assessed"]:
            print("열위 판정 제외(고유 효과): " + ", ".join(result["dominance_not_assessed"]))
        print(f"아이템 {result['items']}개 · 오류 {len(result['errors'])} · 경고 {len(result['warnings'])} → {result['status'].upper()}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
