#!/usr/bin/env python3
"""컨셉 기록(design/concepts.json)을 결정적으로 검사한다.

재미를 점수로 매기지 않는다. 기록이 빠짐없는지, 구조가 사실상 같은 컨셉이 있는지,
후보들이 한 구조에 몰려 있지 않은지, 선택한 컨셉의 브리프가 반증 가능한 형태인지 본다.
형식은 skills/concept-exploration/references/concept-record.md를 따른다. 표준 라이브러리만 사용한다.

종료 코드: 0 통과, 1 오류(또는 --strict 경고), 2 사용법 오류
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ID_PATTERN = re.compile(r"^[a-z0-9_]+$")
STATUSES = ("proposed", "approved", "cut")
STATUS_LABEL = {"proposed": "후보", "approved": "선택", "cut": "제외", "unspecified": "미지정"}
REQUIRED_TEXT = ("name", "pitch", "core_verb", "decision", "state_read", "skill_expression", "risk")
POLICY_RESULTS = ("dominates", "competitive", "loses", "unknown")
RESULT_LABEL = {"dominates": "지배", "competitive": "대등", "loses": "짐", "unknown": "미확인"}
REJECT_TYPES = ("unreachable_goal", "forced_failure", "dominant_simple_policy",
                "no_recurring_decision", "contradiction", "constraint_violation")
COST_LEVELS = ("small", "medium", "large")
COST_LABEL = {"small": "작음", "medium": "중간", "large": "큼"}
MIN_SIGNATURE_AXES = 4
DUPLICATE_THRESHOLD = 0.8
MVP_LIMIT = 7


def _text(v) -> bool:
    return isinstance(v, str) and v.strip() != ""


def _status(c: dict) -> str:
    return c.get("status") or "unspecified"


def _active(c: dict) -> bool:
    return c.get("status") != "cut"


def load(path: Path) -> dict:
    with Path(path).open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict) or not isinstance(data.get("concepts"), list):
        raise ValueError("컨셉 기록이 아닙니다 (최상위에 concepts 배열이 필요합니다).")
    return data


def check_concept(c: dict, where: str, errors: list, warnings: list) -> bool:
    ok = True
    for f in REQUIRED_TEXT:
        if not _text(c.get(f)):
            errors.append({"code": "missing_field", "where": where, "message": f"{f}가 비어 있습니다."})
            ok = False
    status = c.get("status")
    if status is not None and status not in STATUSES:
        errors.append({"code": "schema", "where": where, "message": f"status는 {', '.join(STATUSES)} 중 하나입니다: {status!r}"})
        ok = False
    sig = c.get("signature")
    if not isinstance(sig, dict) or not all(isinstance(k, str) and _text(v) for k, v in sig.items()):
        errors.append({"code": "schema", "where": where, "message": "signature는 {축: 값(문자열)} 객체여야 합니다."})
        ok = False
    elif len(sig) < MIN_SIGNATURE_AXES:
        errors.append({"code": "signature_too_small", "where": where,
                       "message": f"signature 축이 {len(sig)}개입니다. 구조 비교를 위해 {MIN_SIGNATURE_AXES}개 이상 적으세요."})
        ok = False
    stress = c.get("stress", [])
    if not isinstance(stress, list):
        errors.append({"code": "schema", "where": where, "message": "stress는 배열이어야 합니다."})
        ok = False
        stress = []
    for n, s in enumerate(stress):
        if not isinstance(s, dict) or not _text(s.get("policy")) or s.get("result") not in POLICY_RESULTS:
            errors.append({"code": "schema", "where": f"{where}.stress[{n}]",
                           "message": f"policy(문자열)와 result({', '.join(POLICY_RESULTS)})가 필요합니다."})
            ok = False
            continue
        if s["result"] != "unknown" and not _text(s.get("evidence")):
            errors.append({"code": "evidence_missing", "where": where,
                           "message": f"'{s['policy']}' 결과가 {s['result']}인데 근거(evidence)가 없습니다. 근거가 없으면 unknown으로 둡니다."})
            ok = False
    rej = c.get("hard_reject")
    if rej is not None:
        if not isinstance(rej, dict) or rej.get("type") not in REJECT_TYPES or not _text(rej.get("reason")) or not _text(rej.get("evidence")):
            errors.append({"code": "reject_unsupported", "where": where,
                           "message": f"hard_reject에는 type({', '.join(REJECT_TYPES)}), reason, evidence가 모두 필요합니다. 낯설다·위험하다는 탈락 사유가 아닙니다."})
            ok = False
        elif status != "cut":
            warnings.append({"code": "rejected_but_active", "where": where, "message": "hard_reject가 있는데 status가 cut이 아닙니다."})
    cost = c.get("cost")
    if cost is not None and (not isinstance(cost, dict) or cost.get("level") not in COST_LEVELS or not _text(cost.get("reason"))):
        errors.append({"code": "schema", "where": where, "message": f"cost는 {{level: {'/'.join(COST_LEVELS)}, reason}} 형태여야 합니다."})
        ok = False
    return ok


def check_brief(c: dict, where: str, errors: list) -> None:
    """선택(approved)한 컨셉은 반증 가능한 브리프를 갖춰야 한다."""
    b = c.get("brief")
    if not isinstance(b, dict):
        errors.append({"code": "brief_missing", "where": where, "message": "선택한 컨셉에는 brief가 필요합니다."})
        return

    def need(cond: bool, message: str) -> None:
        if not cond:
            errors.append({"code": "brief_incomplete", "where": where, "message": message})

    need(_text(b.get("experience")), "brief.experience(한 문장 경험 목표)가 비어 있습니다.")
    pillars = b.get("pillars")
    need(isinstance(pillars, list) and 2 <= len(pillars) <= 5, "brief.pillars는 2~5개여야 합니다.")
    for n, p in enumerate(pillars if isinstance(pillars, list) else []):
        need(isinstance(p, dict) and _text(p.get("name")) and _text(p.get("test")),
             f"brief.pillars[{n}]에 name과 test(\"A와 B 중 이 게임은 __를 고른다\")가 필요합니다.")
    anti = b.get("anti_pillars")
    need(isinstance(anti, list) and len(anti) >= 1 and all(_text(a) for a in anti), "brief.anti_pillars가 1개 이상 필요합니다.")
    loop = b.get("loop")
    need(isinstance(loop, dict) and all(_text(loop.get(k)) for k in ("moment", "run", "meta")),
         "brief.loop에 moment(30초), run(한 판), meta(판 사이 성장)가 필요합니다.")
    hyps = b.get("hypotheses")
    need(isinstance(hyps, list) and len(hyps) >= 1, "brief.hypotheses가 1개 이상 필요합니다.")
    for n, h in enumerate(hyps if isinstance(hyps, list) else []):
        need(isinstance(h, dict) and all(_text(h.get(k)) for k in ("claim", "failure_signal", "test")),
             f"brief.hypotheses[{n}]에 claim, failure_signal(틀렸다는 신호), test가 필요합니다.")
    proto = b.get("prototype")
    need(isinstance(proto, dict) and _text(proto.get("scope")) and _text(proto.get("success_criteria"))
         and isinstance(proto.get("duration_days"), (int, float)) and not isinstance(proto.get("duration_days"), bool)
         and proto.get("duration_days") > 0,
         "brief.prototype에 scope, success_criteria, duration_days(양수)가 필요합니다.")
    mvp = b.get("mvp")
    need(isinstance(mvp, list) and 1 <= len(mvp) <= MVP_LIMIT and all(_text(m) for m in mvp),
         f"brief.mvp는 1~{MVP_LIMIT}개여야 합니다. 넘으면 줄이세요.")
    oos = b.get("out_of_scope")
    need(isinstance(oos, list) and len(oos) >= 1 and all(_text(o) for o in oos), "brief.out_of_scope가 1개 이상 필요합니다.")


def similarity(a: dict, b: dict) -> tuple[float, int]:
    shared = set(a) & set(b)
    if not shared:
        return 0.0, 0
    same = sum(1 for k in shared if a[k].strip().lower() == b[k].strip().lower())
    return same / len(shared), len(shared)


def check_structure(active: list[dict], warnings: list) -> dict:
    """구조 중복과 축 쏠림을 본다. 테마·이름은 보지 않는다."""
    pairs = []
    for i, a in enumerate(active):
        for b in active[i + 1:]:
            ratio, shared = similarity(a["signature"], b["signature"])
            if shared >= MIN_SIGNATURE_AXES and ratio >= DUPLICATE_THRESHOLD:
                pairs.append((a["id"], b["id"], round(ratio, 3)))
                warnings.append({"code": "near_duplicate", "where": b["id"],
                                 "message": f"'{a['id']}'와 구조 축 {shared}개 중 {round(ratio * shared)}개가 같습니다. 테마만 다른 변형일 수 있습니다. 대표 하나만 남기거나 인과 관계를 바꾸세요."})
    coverage: dict = {}
    for c in active:
        for k, v in c["signature"].items():
            coverage.setdefault(k, set()).add(v.strip().lower())
    if len(active) >= 3:
        for k, vals in sorted(coverage.items()):
            holders = [c for c in active if k in c["signature"]]
            if len(holders) >= 3 and len(vals) == 1:
                warnings.append({"code": "axis_collapse", "where": k,
                                 "message": f"후보 {len(holders)}개가 '{k}' 축에서 모두 '{next(iter(vals))}'입니다. 이 축은 탐색되지 않았습니다."})
    return {"duplicates": pairs, "axis_coverage": {k: sorted(v) for k, v in sorted(coverage.items())}}


def validate(data: dict) -> dict:
    errors: list = []
    warnings: list = []
    raw = data.get("concepts")
    if not isinstance(raw, list):
        errors.append({"code": "schema", "where": "concepts", "message": "concepts 배열이 필요합니다."})
        raw = []
    valid, seen = [], set()
    for idx, c in enumerate(raw):
        where = f"concepts[{idx}]"
        if not isinstance(c, dict):
            errors.append({"code": "schema", "where": where, "message": "컨셉은 객체여야 합니다."})
            continue
        cid = c.get("id")
        if not isinstance(cid, str) or not ID_PATTERN.match(cid):
            errors.append({"code": "schema", "where": where, "message": f"id는 소문자·숫자·밑줄만 씁니다: {cid!r}"})
            continue
        if cid in seen:
            errors.append({"code": "duplicate_id", "where": cid, "message": "id가 중복됩니다."})
            continue
        seen.add(cid)
        if check_concept(c, cid, errors, warnings):
            valid.append(c)
    ids = {c["id"] for c in raw if isinstance(c, dict) and isinstance(c.get("id"), str)}
    for c in valid:
        origin = c.get("origin")
        if origin is not None and origin != "root" and origin not in ids:
            errors.append({"code": "unknown_origin", "where": c["id"], "message": f"origin '{origin}'가 없습니다. 처음 만든 컨셉은 'root'로 둡니다."})
    active = [c for c in valid if _active(c)]
    for c in active:
        if not _text(c.get("next_test")):
            warnings.append({"code": "next_test_missing", "where": c["id"], "message": "이 가설을 가장 싸게 확인할 다음 시험(next_test)이 없습니다."})
        if any(s.get("result") == "dominates" for s in c.get("stress", [])):
            warnings.append({"code": "dominant_policy", "where": c["id"],
                             "message": "단순 전략이 지배하는 결과가 있습니다. 규칙을 바꾸거나, 증거가 충분하면 hard_reject로 제외하세요."})
    for c in valid:
        if c.get("status") == "approved":
            check_brief(c, c["id"], errors)
    structure = check_structure(active, warnings)
    status_counts = {s: 0 for s in STATUSES + ("unspecified",)}
    for c in valid:
        status_counts[_status(c)] += 1
    return {
        "kind": "concepts",
        "count": len(valid),
        "status_counts": status_counts,
        "approved": sorted(c["id"] for c in valid if c.get("status") == "approved"),
        "stress_summary": {c["id"]: {r: sum(1 for s in c.get("stress", []) if s.get("result") == r) for r in POLICY_RESULTS} for c in valid},
        **structure,
        "errors": errors,
        "warnings": warnings,
    }


def _cell(v) -> str:
    return str(v).replace("|", "\\|").replace("\n", " ") if v else "–"


def table(data: dict, result: dict) -> str:
    """대화에 붙일 비교표(마크다운). 점수 합계 열은 일부러 두지 않는다."""
    rows = ["| id | 이름 | 상태 | 반복 결정 | 숙련 표현 | 단순 전략 결과 | 최대 위험 | 제작 부담(가정) | 다음 시험 |",
            "|---|---|---|---|---|---|---|---|---|"]
    by_id = {c["id"]: c for c in data.get("concepts", []) if isinstance(c, dict) and isinstance(c.get("id"), str)}
    order = {"approved": 0, "proposed": 1, "unspecified": 2, "cut": 3}
    for cid in sorted(result["stress_summary"], key=lambda i: (order[_status(by_id[i])], i)):
        c = by_id[cid]
        st = result["stress_summary"][cid]
        stress = " · ".join(f"{RESULT_LABEL[r]} {n}" for r, n in st.items() if n) or "–"
        cost = c.get("cost")
        cost_txt = f"{COST_LABEL[cost['level']]}: {cost['reason']}" if isinstance(cost, dict) and cost.get("level") in COST_LABEL else "–"
        rows.append("| " + " | ".join(_cell(x) for x in (
            cid, c.get("name"), STATUS_LABEL[_status(c)], c.get("decision"), c.get("skill_expression"),
            stress, c.get("risk"), cost_txt, c.get("next_test"))) + " |")
    return "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="컨셉 기록을 검사합니다 (재미 점수는 매기지 않습니다).")
    ap.add_argument("path", help="concepts.json")
    ap.add_argument("--strict", action="store_true", help="경고도 실패로 처리합니다.")
    ap.add_argument("--table", action="store_true", help="비교표(마크다운)를 출력합니다. 파일로 저장하지 않습니다.")
    ap.add_argument("--json", action="store_true", help="결과를 JSON으로 출력합니다.")
    args = ap.parse_args(argv)
    try:
        data = load(Path(args.path))
    except (OSError, ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        print(f"입력을 읽을 수 없습니다: {exc}", file=sys.stderr)
        return 2
    result = validate(data)
    failed = bool(result["errors"]) or (args.strict and bool(result["warnings"]))
    result["status"] = "fail" if failed else "pass"
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if failed else 0
    for e in result["errors"]:
        print(f"error [{e['code']}] {e['where']}: {e['message']}")
    for w in result["warnings"]:
        print(f"warning [{w['code']}] {w['where']}: {w['message']}")
    if args.table:
        print(table(data, result))
    sc = result["status_counts"]
    print(f"컨셉 {result['count']}개 · 후보 {sc['proposed']} · 선택 {sc['approved']} · 제외 {sc['cut']}"
          + (f" · 미지정 {sc['unspecified']}" if sc["unspecified"] else "")
          + f" · 오류 {len(result['errors'])} · 경고 {len(result['warnings'])} → {result['status'].upper()}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
