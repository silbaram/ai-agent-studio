#!/usr/bin/env python3
"""영구 강화(메타 성장) 데이터를 결정적으로 검사한다.

입력: JSON({"upgrades": [...]}) 또는 upgrades CSV(requires는 ;로 구분).
형식은 skills/progression-economy/references/data-format.md를 따른다. 표준 라이브러리만 사용한다.
simulate_meta.py는 설정의 upgrades_file로 이 파일을 그대로 읽는다.

종료 코드: 0 통과, 1 오류(또는 --strict 경고, --fail-on-assumed 가정), 2 사용법 오류
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as c  # noqa: E402


def load(path: Path) -> dict:
    kind, data = c.load_dataset(Path(path), expected="upgrades")
    if kind != "upgrades":
        raise ValueError("영구 강화 데이터가 아닙니다 (최상위에 upgrades 배열이 필요합니다).")
    return data


def requires(u: dict) -> list:
    return u.get("requires") or []


def check_schema(upgrades: list, errors: list) -> list[dict]:
    valid = []
    for _, u in c.check_identity(upgrades, "upgrades", errors):
        where, ok = u["id"], True
        cost = u.get("cost")
        if not (c.is_number(cost) and cost >= 0):
            errors.append({"code": "schema", "where": where, "message": f"cost는 0 이상의 수여야 합니다: {cost!r}"})
            ok = False
        if "power" in u and u["power"] is not None and not c.is_number(u["power"]):
            errors.append({"code": "schema", "where": where, "message": f"power는 수여야 합니다: {u['power']!r}"})
            ok = False
        req = requires(u)
        if not (isinstance(req, list) and all(isinstance(r, str) for r in req)):
            errors.append({"code": "schema", "where": where, "message": "requires는 id 문자열 배열이어야 합니다."})
            ok = False
        for f in ("track",):
            if f in u and not isinstance(u[f], str):
                errors.append({"code": "schema", "where": where, "message": f"{f}는 문자열이어야 합니다."})
                ok = False
        if "level" in u and u["level"] is not None and not (isinstance(u["level"], int) and not isinstance(u["level"], bool)):
            errors.append({"code": "schema", "where": where, "message": "level은 정수여야 합니다."})
            ok = False
        if "stats" in u:
            ok = c.check_stats(u, where, errors) and ok
        ok = c.check_common(u, where, errors) and ok
        if ok:
            valid.append(u)
    return valid


def depth_of(uid: str, by_id: dict, memo: dict) -> int:
    """선행 조건 사슬의 길이. 선행이 없으면 0. 순환이 없다는 전제에서 호출한다."""
    if uid in memo:
        return memo[uid]
    reqs = [r for r in requires(by_id[uid]) if r in by_id]
    memo[uid] = 0 if not reqs else 1 + max(depth_of(r, by_id, memo) for r in reqs)
    return memo[uid]


def validate(data: dict) -> dict:
    errors: list = []
    warnings: list = []
    raw = data.get("upgrades")
    if not isinstance(raw, list):
        errors.append({"code": "schema", "where": "upgrades", "message": "upgrades 배열이 필요합니다."})
        raw = []
    ups = check_schema(raw, errors)
    by_id = {u["id"]: u for u in ups}
    for u in ups:
        for r in requires(u):
            if r not in by_id:
                errors.append({"code": "unknown_requirement", "where": u["id"], "message": f"선행 조건 '{r}'가 없습니다."})
    cycle = c.find_cycle({u["id"]: list(requires(u)) for u in ups})
    if cycle:
        errors.append({"code": "requirement_cycle", "where": cycle[0], "message": "선행 조건에 순환이 있습니다: " + " → ".join(cycle)})
    active = [u for u in ups if c.is_active(u)]
    for u in active:
        for r in requires(u):
            if r in by_id and not c.is_active(by_id[r]):
                errors.append({"code": "requires_cut", "where": u["id"], "message": f"삭제(cut)된 '{r}'가 선행 조건이라 살 수 없습니다."})
            elif r in by_id and by_id[r]["cost"] > u["cost"]:
                warnings.append({"code": "cost_inversion", "where": u["id"],
                                 "message": f"선행 조건 '{r}'({by_id[r]['cost']:g})보다 싸게({u['cost']:g}) 책정되어 있습니다."})
        if u.get("power") is None:
            warnings.append({"code": "power_missing", "where": u["id"], "message": "power가 없어 메타 성장 시뮬레이터에서 쓸 수 없습니다."})
    depth: dict = {}
    if not cycle:
        memo: dict = {}
        depth = {u["id"]: depth_of(u["id"], by_id, memo) for u in ups}
    tracks: dict = {}
    for u in active:
        t = tracks.setdefault(u.get("track") or "(트랙 없음)", {"count": 0, "total_cost": 0.0, "total_power": 0.0})
        t["count"] += 1
        t["total_cost"] += u["cost"]
        t["total_power"] += u.get("power") or 0.0
    return {
        "kind": "upgrades",
        "count": len(ups),
        **c.summary_counts(ups),
        "depth": depth,
        "efficiency": {u["id"]: round(u["power"] / u["cost"], 4) for u in ups if u.get("power") is not None and u["cost"] > 0},
        "tracks": {k: {kk: round(vv, 4) if isinstance(vv, float) else vv for kk, vv in v.items()} for k, v in sorted(tracks.items())},
        "totals": {"active": len(active), "cost": round(sum(u["cost"] for u in active), 4),
                   "power": round(sum(u.get("power") or 0.0 for u in active), 4)},
        "errors": errors,
        "warnings": warnings,
    }


def _print_extra(result: dict) -> None:
    t = result["totals"]
    print(f"활성 강화 {t['active']}개 · 총비용 {t['cost']:g} · 총 power {t['power']:g}")
    for name, tr in result["tracks"].items():
        print(f"  트랙 {name}: {tr['count']}개 · 비용 {tr['total_cost']:g} · power {tr['total_power']:g}")


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="영구 강화 데이터를 검사합니다.")
    ap.add_argument("path", help="upgrades JSON 또는 CSV")
    c.add_common_args(ap)
    args = ap.parse_args(argv)
    try:
        data = load(Path(args.path))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"입력을 읽을 수 없습니다: {exc}", file=sys.stderr)
        return 2
    result = validate(data)
    result["source"] = args.path
    return c.finish_cli(result, args, "강화", _print_extra)


if __name__ == "__main__":
    sys.exit(main())
