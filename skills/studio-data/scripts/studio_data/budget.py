"""스탯 예산(data/budget.json): 아이템·적 수치를 하나씩 감으로 정하지 않고 곡선과 원형에서 만들고, 곡선에서 벗어난 것을 찾는다.

항목의 예산 = Σ(스탯 × 스탯 원가). 기준(티어·구역 등)마다 곡선이 기대 예산을 정하고, 배수(등급·희귀도 등)를 곱한다.
허용 오차를 넘으면 넘침·모자람을 경고한다. 원형(archetype)은 예산을 스탯에 나누는 비율이며, 초안(draft)을 만든다.
전투 계산(combat)이 있으면 단계마다 스탯 1의 값어치를 재어 원가 제안으로 보여 준다(자동으로 바꾸지 않는다).
재미나 실제 난이도를 판정하지 않는다. 형식: stat-budget/references/budget-format.md
"""
from __future__ import annotations

from . import common as c
from .common import add_issue as _err, did_you_mean

SIDES = ("items", "enemies")
SIDE_LABEL = {"items": "아이템", "enemies": "적"}
GROWTHS = ("linear", "exponential", "table")
FLAG_LABEL = {"ok": "곡선 안", "over": "넘침", "under": "모자람", "excluded": "판정 제외", "unchecked": "미확인"}
DEFAULT_TOLERANCE = 0.2
SPLIT_EPSILON = 1e-6
INT_FIELDS = {"items": ("tier",), "enemies": ("zone",)}  # 초안이 들어갈 원본 파일이 1 이상의 정수로 요구하는 필드


# ---------- 곡선 ----------
def curve_value(curve: dict, at) -> float | None:
    """기준 값 at에서의 기대 예산. linear: base + rate × (at − 1), exponential: base × (1 + rate)^(at − 1), table: values[at]."""
    if curve["growth"] == "table":
        v = curve["values"].get(str(at if not isinstance(at, float) or not at.is_integer() else int(at)))
        return v if c.is_number(v) else None
    if curve["growth"] == "linear":
        return curve["base"] + curve["rate"] * (at - 1)
    return curve["base"] * (1 + curve["rate"]) ** (at - 1)


def read_curve(curve, where: str, errors: list, by: bool = True) -> dict | None:
    """곡선 형식을 검사하고 growth를 채워 돌려준다. 틀리면 오류를 남기고 None. by: 기준 필드(curve.by)가 필요한가."""
    if not (isinstance(curve, dict) and (isinstance(curve.get("by"), str) or not by) and curve.get("growth", "linear") in GROWTHS):
        _err(errors, "schema", where, f"curve에 {'by(기준 필드 이름)와 ' if by else ''}growth({', '.join(GROWTHS)})가 필요합니다.")
        return None
    curve = {"growth": "linear", **curve}
    if curve["growth"] == "table":
        vals = curve.get("values")
        if not (isinstance(vals, dict) and vals and all(c.is_number(v) and v > 0 for v in vals.values())):
            _err(errors, "schema", where, "table 곡선에는 {기준 값: 0보다 큰 예산} values가 필요합니다.")
            return None
    elif not (c.is_number(curve.get("base")) and curve["base"] > 0 and c.is_number(curve.get("rate"))
              and (curve["growth"] == "linear" or curve["rate"] > -1)):
        _err(errors, "schema", where, f"{curve['growth']} 곡선에는 수 base(> 0)와 rate가 필요합니다.")
        return None
    return curve


def _multiplier(spec: dict | None, entry: dict) -> tuple[float | None, object]:
    """(배수, 그 항목의 배수 필드 값). 배수 표에 그 값이 없으면 (None, 값)."""
    if not spec:
        return 1.0, None
    key = entry.get(spec["field"])
    v = spec["values"].get(str(key)) if key is not None else None
    return (v if c.is_number(v) else None), key


def entry_budget(spec: dict, entry: dict) -> float | None:
    """항목의 예산 Σ(스탯 × 원가). 원가 없는 스탯이 있거나 형식이 틀리면 None. 다른 검사기(강화·합성)도 쓴다."""
    stats = entry.get("stats") or {}
    if not isinstance(stats, dict) or not all(k in spec["costs"] and c.is_number(v) for k, v in stats.items()):
        return None
    return sum(v * spec["costs"][k] for k, v in stats.items())


def expected_budget(spec: dict, entry: dict, at=None) -> float | None:
    """항목의 기대 예산(곡선 × 배수). at을 주면 그 기준 값에서. 계산할 수 없거나 0 이하면 None."""
    at = entry.get(spec["curve"]["by"]) if at is None else at
    if not c.is_number(at):
        return None
    base = curve_value(spec["curve"], at)
    mult, _ = _multiplier(spec["multiplier"], entry)
    if base is None or mult is None or base * mult <= 0:
        return None
    return base * mult


def _round(v: float) -> float:
    if abs(v) >= 10:
        return round(v)
    if abs(v) >= 1:
        return round(v, 1)
    return round(v, 3)


# ---------- 형식 검사 ----------
def read_settings(data: dict, errors: list) -> dict | None:
    cfg = data.get("budget")
    if not isinstance(cfg, dict):
        _err(errors, "schema", "budget", "budget 객체(items / enemies의 costs·curve, tolerance)가 필요합니다.")
        return None
    sides, broken = {}, set()
    for side in SIDES:
        spec = cfg.get(side)
        if spec is None:
            continue
        where, ok = f"budget.{side}", True
        if not isinstance(spec, dict):
            _err(errors, "schema", where, "costs와 curve가 있는 객체여야 합니다.")
            broken.add(side)
            continue
        costs = spec.get("costs")
        if not (isinstance(costs, dict) and costs and all(isinstance(k, str) and c.is_number(v) and v > 0 for k, v in costs.items())):
            _err(errors, "schema", where, "costs는 {스탯 이름: 0보다 큰 원가}여야 합니다.")
            ok = False
        curve = read_curve(spec.get("curve"), where, errors)
        ok = ok and curve is not None
        mult = spec.get("multiplier")
        if mult is not None and not (isinstance(mult, dict) and isinstance(mult.get("field"), str) and isinstance(mult.get("values"), dict)
                                     and all(c.is_number(v) and v > 0 for v in mult["values"].values())):
            _err(errors, "schema", where, "multiplier는 {field: 필드 이름, values: {값: 0보다 큰 배수}}여야 합니다.")
            ok = False
        if ok:
            sides[side] = {"costs": costs, "curve": curve, "multiplier": mult}
        else:
            broken.add(side)  # 이 쪽만 비교하지 않는다. 다른 쪽은 계속한다
    if not sides and not broken:
        _err(errors, "schema", "budget", "budget에 items나 enemies 중 하나 이상이 필요합니다.")
    tol = cfg.get("tolerance", DEFAULT_TOLERANCE)
    if not (c.is_number(tol) and 0 <= tol < 1):
        _err(errors, "schema", "budget.tolerance", f"tolerance는 0 이상 1 미만의 비율입니다: {tol!r}")
        return None
    return {"sides": sides, "broken": sorted(broken), "tolerance": tol} if sides else None


def check_archetypes(raw, settings: dict | None, errors: list) -> list[dict]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        _err(errors, "schema", "archetypes", "archetypes는 배열이어야 합니다.")
        return []
    out = []
    for _, a in c.check_identity(raw, "archetypes", errors):
        where, ok = a["id"], c.check_common(a, a["id"], errors)
        side = a.get("for")
        if side not in SIDES:
            _err(errors, "schema", where, f"for는 {', '.join(SIDES)} 중 하나입니다: {side!r}{did_you_mean(str(side), SIDES)}")
            continue
        split = a.get("split")
        if not (isinstance(split, dict) and split and all(isinstance(k, str) and c.is_number(v) and v > 0 for k, v in split.items())):
            _err(errors, "schema", where, "split은 {스탯 이름: 0보다 큰 비율}이어야 합니다.")
            continue
        if abs(sum(split.values()) - 1) > SPLIT_EPSILON:
            _err(errors, "schema", where, f"split 비율의 합은 1이어야 합니다: {sum(split.values()):g}")
            ok = False
        spec = settings["sides"].get(side) if settings is not None else None
        if settings is not None and spec is None:
            if side not in settings["broken"]:  # 깨진 쪽이면 그 오류를 이미 보고했다
                _err(errors, "schema", where, f"budget.{side}가 없어 이 원형의 예산을 정할 수 없습니다.")
            ok = False
        if spec is not None:
            missing = [k for k in split if k not in spec["costs"]]
            if missing:
                _err(errors, "schema", where, f"split의 스탯 {', '.join(missing)}에 원가(costs)가 없습니다.")
                ok = False
        fields = a.get("fields", {})
        if not isinstance(fields, dict):
            _err(errors, "schema", where, "fields는 초안에 그대로 넣을 {필드: 값} 객체여야 합니다.")
            ok = False
        elif spec is not None and spec["curve"]["by"] in fields:
            _err(errors, "schema", where, f"fields에 곡선 기준 필드 {spec['curve']['by']}를 넣지 않습니다. 초안의 기준 값은 --at으로 정합니다.")
            ok = False
        if ok:
            out.append(a)
    return out


# ---------- 비교 ----------
def validate(data: dict, items: dict | None = None, enemies: dict | None = None, suggestions: dict | None = None) -> dict:
    """items·enemies: 함께 읽은 데이터의 {id: 항목}. None이면 그 쪽은 미확인. suggestions: combat.marginal_costs() 결과."""
    errors: list = []
    warnings: list = []
    acknowledged: list = []
    settings = read_settings(data, errors)
    archetypes = check_archetypes(data.get("archetypes"), settings, errors)
    rows: list = []
    unchecked, missing_kinds = 0, []
    refs = {"items": items, "enemies": enemies}
    if settings is not None:
        for side, spec in settings["sides"].items():
            entries = refs[side]
            if entries is None:
                unchecked += 1
                missing_kinds.append(side)
                continue
            by, uncosted, missing_points, missing_mult, no_at, not_positive = spec["curve"]["by"], {}, set(), set(), [], set()
            no_field: list = []
            for e in entries.values():
                if not c.is_active(e):
                    continue
                at = e.get(by)
                stats = e.get("stats") or {}
                row = {"side": side, "id": e["id"], "at": at, "group": None, "actual": None, "expected": None, "ratio": None, "flag": "unchecked"}
                rows.append(row)
                if e.get("unique_effect"):
                    row["flag"] = "excluded"  # 수치로 비교할 수 없는 효과가 있다(아이템 검사와 같은 규칙)
                    continue
                if not c.is_number(at):
                    no_at.append(e["id"])
                    unchecked += 1
                    continue
                if not (isinstance(stats, dict) and all(c.is_number(v) for v in stats.values())):
                    unchecked += 1  # 형식 오류는 그 데이터 파일의 검사기가 보고한다
                    continue
                extra = [k for k in stats if k not in spec["costs"]]
                if extra:
                    for k in extra:
                        uncosted.setdefault(k, []).append(e["id"])
                    unchecked += 1
                    continue
                base = curve_value(spec["curve"], at)
                if base is None:
                    if at not in missing_points:
                        missing_points.add(at)
                        _err(errors, "curve_missing_point", f"budget.{side}.curve", f"table 곡선에 {by} {at:g}의 값이 없습니다.")
                    continue
                mult, key = _multiplier(spec["multiplier"], e)
                row["group"] = key
                if mult is None:
                    if key is None:
                        no_field.append(e["id"])
                    elif key not in missing_mult:
                        missing_mult.add(key)
                        _err(warnings, "multiplier_missing", f"budget.{side}.multiplier",
                             f"배수 표({spec['multiplier']['field']})에 값 {key!r}가 없어 그 {c.josa(SIDE_LABEL[side], '을를')} 비교하지 못했습니다.")
                    unchecked += 1
                    continue
                actual = entry_budget(spec, e)
                expected = base * mult
                if expected <= 0:
                    if at not in not_positive:
                        not_positive.add(at)
                        _err(errors, "curve_not_positive", f"budget.{side}.curve",
                             f"{by} {at:g}에서 기대 예산이 {expected:g}입니다. 곡선은 모든 기준 값에서 0보다 커야 합니다.")
                    continue
                ratio = actual / expected
                row.update({"actual": round(actual, 4), "expected": round(expected, 4), "ratio": round(ratio, 4), "flag": "ok"})
                tol = settings["tolerance"]
                if ratio > 1 + tol or ratio < 1 - tol:
                    code = "over_budget" if ratio > 1 else "under_budget"
                    row["flag"] = "over" if ratio > 1 else "under"
                    issue = {"code": code, "where": e["id"], "owner": f"{side}:{e['id']}",
                             "message": f"{SIDE_LABEL[side]} {e['id']}의 예산 {c.josa(f'{actual:g}', '이가')} {by} {at:g} 기대 예산 {expected:g}의 "
                                        f"{ratio:.0%}입니다(허용 ±{tol:.0%})."}
                    reason = c.ack_reason(e, code)  # 형식이 틀린 확인은 그 항목의 파일에서 오류로 보고된다
                    if reason:
                        acknowledged.append({**issue, "reason": reason})
                    else:
                        warnings.append(issue)
            if no_field:
                field = spec["multiplier"]["field"]
                fields = {k for e in entries.values() if isinstance(e, dict) for k in e}
                _err(warnings, "multiplier_missing", f"budget.{side}.multiplier",
                     f"{SIDE_LABEL[side]} {len(no_field)}개에 배수 필드 {field}가 없어 비교하지 못했습니다"
                     f"({', '.join(no_field[:5])}{' …' if len(no_field) > 5 else ''}).{did_you_mean(field, fields)}")
            if no_at:
                _err(warnings, "curve_field_missing", f"budget.{side}.curve",
                     f"곡선 기준 필드 {by}가 없거나 수가 아니라 {len(no_at)}개 항목을 비교하지 못했습니다({', '.join(no_at[:5])}{' …' if len(no_at) > 5 else ''}).")
            for stat, ids in sorted(uncosted.items()):
                _err(warnings, "stat_without_cost", f"budget.{side}.costs",
                     f"스탯 {stat}에 원가가 없어 {len(ids)}개 항목을 비교하지 못했습니다({', '.join(ids[:5])}{' …' if len(ids) > 5 else ''}). "
                     "원가를 정하거나, 예산 밖 효과라면 그 항목에 unique_effect를 붙입니다.")
    if suggestions and suggestions.get("failed"):
        _err(warnings, "suggestions_unavailable", "budget",
             f"전투 계산으로 원가 제안을 만들지 못했습니다({suggestions['failed']}). 전투 계산 검사 결과를 먼저 확인하세요.")
    used = {side: set(spec["costs"]) | {k for e in (refs[side] or {}).values() if isinstance(e.get("stats"), dict) for k in e["stats"]}
            for side, spec in settings["sides"].items()} if settings is not None else {}
    summary = c.summary_counts(archetypes)
    prov = data["budget"].get("provenance") if isinstance(data.get("budget"), dict) else None
    if prov is not None:
        c.check_common({"provenance": prov}, "budget", errors)
    if settings is not None and c.provenance_kind({"provenance": prov}) in ("assumed", "unspecified"):
        summary["unverified"] = ["budget(곡선·원가)"] + summary["unverified"]
    return {
        "kind": "budget",
        "count": len(archetypes),
        **summary,
        "settings": settings,
        "rows": rows,
        "curve_points": _curve_points(settings, rows),
        "suggested_costs": _scale_suggestions(settings, suggestions, used),
        "suggestions_skipped": (suggestions or {}).get("skipped", {}),
        "suggestions_missing": (suggestions or {}).get("unavailable", {}),
        "unchecked": unchecked,
        "unchecked_kinds": missing_kinds,
        "acknowledged": acknowledged,
        "errors": errors,
        "warnings": warnings,
    }


def _curve_points(settings: dict | None, rows: list) -> dict:
    """뷰어·표용: 쪽마다 데이터에 나온 기준 값에서의 기대 예산(배수 전)."""
    out: dict = {}
    if settings is None:
        return out
    for side, spec in settings["sides"].items():
        ats = sorted({r["at"] for r in rows if r["side"] == side and c.is_number(r["at"])})
        out[side] = {f"{a:g}": curve_value(spec["curve"], a) for a in ats}
    return out


def _scale_suggestions(settings: dict | None, suggestions: dict | None, used: dict) -> dict:
    """전투 계산의 값어치(공격 1 = 1)를 기획자가 정한 공격 스탯 원가에 맞춰 원가 단위로 바꾼다.
    그 쪽이 원가를 정했거나 데이터에서 쓰는 스탯만 보인다(예: 적에게 없는 방어는 빼고)."""
    out = {"items": {}, "enemies": {}}
    if settings is None or not suggestions or suggestions.get("failed"):
        return out
    for side, who in (("items", "player"), ("enemies", "enemy")):
        spec = settings["sides"].get(side)
        attack = (suggestions.get("attack_stat") or {}).get(who)
        if not spec or attack not in spec["costs"]:
            continue
        scale = spec["costs"][attack]
        for stage, values in (suggestions.get(who) or {}).items():
            out[side][stage] = {k: round(v * scale, 4) for k, v in values.items() if k in used.get(side, ())}
    return out


# ---------- 초안 ----------
def draft(data: dict, archetype_id: str, at: float, entry_id: str | None = None, fields: dict | None = None,
          existing: set | None = None) -> tuple[dict, dict]:
    """원형과 곡선에서 항목 초안 하나를 만든다. (항목, 계산 정보). 형식이 틀리면 ValueError.
    existing: 초안이 들어갈 원본(아이템·적)에 이미 있는 id. 원본 검사에서 바로 실패할 초안(id 형식, 정수 필드, 중복 id)은 만들지 않는다."""
    errors: list = []
    settings = read_settings(data, errors)
    archetypes = {a["id"]: a for a in check_archetypes(data.get("archetypes"), settings, errors)}
    if settings is None:
        raise ValueError("budget.json 형식 오류: " + "; ".join(e["message"] for e in errors[:3]))
    a = archetypes.get(archetype_id)
    if a is None:
        own = [e["message"] for e in errors if e["where"] == archetype_id]
        raw_ids = [x.get("id") for x in data.get("archetypes") or [] if isinstance(x, dict)]
        if own or archetype_id in raw_ids:
            side = next((x.get("for") for x in data["archetypes"] if isinstance(x, dict) and x.get("id") == archetype_id), None)
            own += [e["message"] for e in errors if e["where"].startswith(f"budget.{side}")]
            raise ValueError(f"원형 {archetype_id}에 오류가 있어 초안을 만들 수 없습니다: " + "; ".join(own[:3] or ["형식을 확인하세요"]))
        raise ValueError(f"없는 원형입니다: {archetype_id}.{did_you_mean(archetype_id, archetypes)} 원형: {', '.join(archetypes) or '없음'}")
    side, spec = a["for"], settings["sides"][a["for"]]
    reserved = {"id", "stats", "status", "provenance", spec["curve"]["by"]} & set(fields or {})
    if reserved:
        raise ValueError(f"--set으로 {', '.join(sorted(reserved))}를 정하지 않습니다. 기준 값은 --at, id는 --id로 정합니다.")
    at = int(at) if isinstance(at, float) and at.is_integer() else at  # 티어·구역은 보통 정수 필드다
    by = spec["curve"]["by"]
    if by in INT_FIELDS[side] and not c.is_int(at, 1):
        raise ValueError(f"{SIDE_LABEL[side]}의 {by}는 1 이상의 정수입니다: --at {at:g}")
    eid = entry_id or f"{archetype_id}_{at:g}".replace(".", "_")
    if not c.ID_PATTERN.match(eid):
        raise ValueError(f"id는 소문자·숫자·밑줄만 씁니다: {eid!r}")
    if existing and eid in existing:
        raise ValueError(f"{SIDE_LABEL[side]} 데이터에 이미 있는 id입니다: {eid}. --id로 다른 id를 정하세요.")
    entry = {"id": eid, by: at, **a.get("fields", {}), **(fields or {})}
    base = curve_value(spec["curve"], at)
    if base is None:
        raise ValueError(f"table 곡선에 {spec['curve']['by']} {at:g}의 값이 없습니다.")
    mult, key = _multiplier(spec["multiplier"], entry)
    if mult is None:
        field = spec["multiplier"]["field"]
        what = f"초안에 배수 필드 {field}가 없습니다" if key is None else f"배수 표({field})에 값 {key!r}가 없습니다"
        raise ValueError(f"{what}. --set {field}=값으로 정하세요(배수 표의 값: {', '.join(spec['multiplier']['values'])}).")
    expected = base * mult
    if expected <= 0:
        raise ValueError(f"{spec['curve']['by']} {at:g}에서 기대 예산이 {expected:g}입니다. 곡선을 고치세요.")
    entry["stats"] = {k: _round(expected * share / spec["costs"][k]) for k, share in a["split"].items()}
    entry.update({"status": "proposed",
                  "provenance": {"kind": "computed", "source": f"data/budget.json#{archetype_id}",
                                 "note": "곡선·원형에서 계산한 초안. 곡선과 원가는 가정이다"},
                  "intent": f"{archetype_id} 원형 초안"})
    return entry, {"side": side, "expected": round(expected, 4), "curve": round(base, 4), "multiplier": mult}


# ---------- 출력 ----------
def print_extra(result: dict) -> None:
    s = result.get("settings")
    if not s:
        return
    for side, spec in s["sides"].items():
        cv = spec["curve"]
        shape = "표" if cv["growth"] == "table" else f"{cv['growth']} base {cv['base']:g} rate {cv['rate']:g}"
        points = " · ".join(f"{k}: {v:g}" for k, v in result["curve_points"].get(side, {}).items() if v is not None)
        print(f"{SIDE_LABEL[side]} 곡선 ({cv['by']}, {shape}): {points or '–'}")
        flags = [r for r in result["rows"] if r["side"] == side]
        counts = {f: sum(1 for r in flags if r["flag"] == f) for f in FLAG_LABEL}
        print("  " + " · ".join(f"{FLAG_LABEL[f]} {n}" for f, n in counts.items() if n))
    skipped = result.get("suggestions_skipped") or {}
    for side in SIDES:
        for stage, costs in result["suggested_costs"].get(side, {}).items():
            note = f" (피해를 주고받지 못하는 적 {skipped[stage]}개는 빼고 잼)" if side == "items" and skipped.get(stage) else ""
            print(f"원가 제안 ({SIDE_LABEL[side]}, 전투 단계 {stage}): " + " · ".join(f"{k} {v:g}" for k, v in costs.items()) + note)
    missing = result.get("suggestions_missing") or {}
    if missing:
        print("원가 제안 미확인: " + " · ".join(("전투 계산 전체" if k == "combat" else f"전투 단계 {k}") + f"({why})" for k, why in missing.items())
              + ". 전투 계산 검사 결과를 먼저 확인하세요.")
    if result["unchecked_kinds"]:
        print("예산 미확인: " + ", ".join(SIDE_LABEL[k] for k in result["unchecked_kinds"]) + " 데이터를 함께 검사하지 않았거나 읽지 못함")


def table(data: dict, result: dict, ids: list[str] | None = None) -> str:
    """대화에 붙일 예산 비교표(마크다운). --ids는 컨셉 비교표용이라 여기서는 쓰지 않는다."""
    rows = ["| 종류 | id | 기준 | 배수 기준 | 예산 | 기대 예산 | 비율 | 판정 |", "|---|---|---|---|---|---|---|---|"]
    for r in result["rows"]:
        cells = (SIDE_LABEL[r["side"]], r["id"], r["at"], r["group"], r["actual"], r["expected"],
                 f"{r['ratio']:.0%}" if r["ratio"] is not None else None, FLAG_LABEL[r["flag"]])
        rows.append("| " + " | ".join("–" if x is None else (f"{x:g}" if isinstance(x, float) else str(x)) for x in cells) + " |")
    rows += ["", "예산 = Σ(스탯 × 원가). 곡선과 원가는 기획 가정이며, 재미나 실제 난이도를 판정하지 않습니다."]
    return "\n".join(rows)


def print_counts(result: dict) -> None:
    tail = f"오류 {len(result['errors'])} · 경고 {len(result['warnings'])}"
    if result.get("acknowledged"):
        tail += f" · 확인한 경고 {len(result['acknowledged'])}"
    print(f"원형 {result['count']}개 · 비교 {sum(1 for r in result['rows'] if r['flag'] in ('ok', 'over', 'under'))}개 · {tail}")
