"""시스템 설계(design/systems.json): 게임을 이루는 시스템의 규칙과 의존 관계를 브리프의 필러·범위에 잇는다.

브리프가 말한 필러와 MVP를 시스템이 빠짐없이 맡는지, 범위 밖 항목이 구현 쪽으로 새지 않는지, 어느 순서로 만들 수 있는지를 본다.
규칙은 사람이 쓰는 글이다. 규칙이 좋은지, 시스템이 재미있는지는 판정하지 않는다. 형식: system-design/references/systems-format.md
"""
from __future__ import annotations

from . import common as c
from .common import add_issue as _err, did_you_mean

SCOPES = {"mvp": "MVP", "later": "나중", "out": "범위 밖"}
TOP_FIELDS = {"concept", "systems", "note"}
SYSTEM_FIELDS = {"id", "name", "intent", "scope", "foundation", "pillars", "mvp", "out_of_scope", "rules", "depends_on", "status", "provenance", "acknowledged", "note"}
RULE_FIELDS = {"id", "text", "note"}
LINKS = (("pillars", "unknown_pillar", "필러"), ("mvp", "unknown_mvp", "MVP 항목"), ("out_of_scope", "unknown_out_of_scope", "범위 밖 항목"))  # 키, 오류 코드, 이름


def _pick_concept(data: dict, concepts: list, errors: list, warnings: list) -> dict | None:
    """연결할 컨셉. 적혀 있으면 그 컨셉이고, 없으면 승인된 컨셉 하나다."""
    wanted = data.get("concept")
    if wanted is not None:
        found = next((x for x in concepts if x.get("id") == wanted), None)
        if found is None:
            _err(errors, "unknown_concept", "concept", f"컨셉 데이터에 없는 컨셉입니다: {wanted}.{did_you_mean(str(wanted), [x.get('id') for x in concepts])}")
        elif not c.is_active(found):
            _err(warnings, "cut_referenced", "concept", f"삭제(cut)된 컨셉에 이었습니다: {wanted}. 선택했던 컨셉을 되돌렸으면 다음 컨셉을 고를 때까지 그대로 두고, "
                 "고른 뒤 그 컨셉에 다시 잇습니다. 다른 컨셉으로 옮겼으면 지금 컨셉의 브리프로 옮겨 적습니다.")
        elif found.get("status") != "approved":
            _err(warnings, "concept_not_approved", "concept", f"승인(approved)되지 않은 컨셉에 이었습니다: {wanted}. 브리프가 확정되지 않아 이 연결도 확정이 아닙니다. "
                 "선택했던 컨셉을 되돌렸으면 다음 컨셉을 고를 때까지 그대로 두고, 고른 뒤 그 컨셉에 다시 잇습니다.")
        return found
    approved = [x for x in concepts if x.get("status") == "approved"]
    if len(approved) != 1:
        _err(errors, "schema", "concept", f"승인된 컨셉이 {len(approved)}개라 고를 수 없습니다. 최상위에 concept(컨셉 id)을 적습니다.")
        return None
    return approved[0]


def _brief_items(concept: dict | None, errors: list) -> dict | None:
    """브리프의 {pillars, mvp, out_of_scope} 목록. 브리프가 없으면 오류를 남기고 None."""
    if concept is None:
        return None
    brief = concept.get("brief")
    if not isinstance(brief, dict):
        _err(errors, "brief_missing", "concept", f"컨셉 {concept.get('id')}에 brief가 없습니다. concept-exploration으로 브리프를 먼저 씁니다.")
        return None
    pillars = brief.get("pillars")
    texts = {k: [x for x in brief.get(k) or [] if isinstance(x, str)] if isinstance(brief.get(k) or [], list) else [] for k in ("mvp", "out_of_scope")}
    return {"pillars": [p["name"] for p in pillars if isinstance(p, dict) and isinstance(p.get("name"), str)] if isinstance(pillars, list) else [], **texts}


def _text_list(s: dict, key: str, errors: list) -> bool:
    v = s.get(key, [])
    if isinstance(v, list) and all(isinstance(x, str) and x.strip() for x in v):
        return True
    _err(errors, "schema", s["id"], f"{c.josa(key, '은는')} 글의 배열입니다: {c.json_text(v)}")
    return False


def _check_rules(s: dict, errors: list) -> bool:
    raw = s.get("rules", [])
    if not isinstance(raw, list):
        _err(errors, "schema", s["id"], f"rules는 규칙 {{id, text}} 배열입니다: {c.json_text(raw)}")
        return False
    found = c.check_identity(raw, f"{s['id']}.rules", errors)
    ok = len(found) == len(raw)
    for _, r in found:
        text = c.unknown_keys_text(r, RULE_FIELDS)
        if text:
            _err(errors, "schema", f"{s['id']}.{r['id']}", text)
            ok = False
        if not (isinstance(r.get("text"), str) and r["text"].strip()):
            _err(errors, "schema", f"{s['id']}.{r['id']}", "text(규칙 문장)가 필요합니다.")
            ok = False
    return ok


def _check_system(s: dict, errors: list) -> bool:
    ok = True
    text = c.unknown_keys_text(s, SYSTEM_FIELDS)
    if text:
        _err(errors, "schema", s["id"], text)
        ok = False
    if not isinstance(s.get("foundation", False), bool):
        _err(errors, "schema", s["id"], f"foundation(기반 시스템인가)은 true나 false입니다: {c.json_text(s['foundation'])}")
        ok = False
    if s.get("scope") not in SCOPES:
        _err(errors, "schema", s["id"], f"scope는 {', '.join(SCOPES)} 중 하나입니다: {c.json_text(s.get('scope'))}")
        ok = False
    for key in ("pillars", "mvp", "out_of_scope", "depends_on"):
        ok = _text_list(s, key, errors) and ok
    return _check_rules(s, errors) and ok


def _check_links(s: dict, items: dict, errors: list) -> None:
    for key, code, label in LINKS:
        for x in s.get(key, []):
            if x not in items[key]:
                _err(errors, code, s["id"], f"브리프에 없는 {label}입니다: {x}.{did_you_mean(x, items[key])} 브리프의 문구 그대로 적습니다.")
            elif key == "out_of_scope" and s["scope"] != "out":
                _err(errors, "out_of_scope_claimed", s["id"], f"브리프가 범위 밖이라고 한 항목을 맡습니다: {x}. 브리프를 바꾸거나 범위를 out으로 둡니다.")


def _check_text(s: dict, items: dict, errors: list) -> None:
    """브리프가 뺀 것을 시스템의 글로 옮겨 넣지 않았는가. 범위 밖 시스템은 그 항목을 이름으로 쓴다."""
    if s["scope"] == "out":
        return
    texts = [c.fold_text(x) for x in (s.get("name"), s.get("intent"), *(r["text"] for r in s.get("rules", []))) if isinstance(x, str)]
    for item in items["out_of_scope"]:
        if item.strip() and any(c.phrase_pattern(item).search(x) for x in texts):
            _err(errors, "out_of_scope_claimed", s["id"], f"브리프가 범위 밖이라고 한 항목이 시스템의 글에 있습니다: {item}. 글에서 빼거나, 브리프를 바꿀지 사용자에게 묻습니다.")


def _check_scope(s: dict, warnings: list) -> None:
    """시스템의 범위가 브리프와 맞는가."""
    scope, sid, base = s["scope"], s["id"], s.get("foundation", False)
    problems = []
    if scope == "mvp" and not s.get("mvp") and not base:
        problems.append("범위가 MVP인데 브리프의 어떤 MVP 항목도 맡지 않습니다. 브리프의 MVP에 넣거나, 범위를 later로 두거나, 다른 시스템이 기대는 기반이면 foundation을 true로 둡니다.")
    if scope != "mvp" and s.get("mvp"):
        problems.append(f"범위가 {SCOPES[scope]}인데 브리프의 MVP 항목을 맡습니다: {', '.join(s['mvp'])}.")
    if scope == "out" and not s.get("out_of_scope"):
        problems.append("범위가 out인데 브리프의 범위 밖 항목을 가리키지 않습니다.")
    for text in problems:
        _err(warnings, "scope_mismatch", sid, text, owner=sid)
    if scope != "out" and not s.get("pillars") and not base:
        _err(warnings, "system_without_pillar", sid, "어떤 필러도 맡지 않습니다. 필러를 돕지 않는 시스템은 만들 이유를 다시 봅니다. 다른 시스템이 기대는 기반이면 foundation을 true로 둡니다.", owner=sid)
    if scope != "out" and not s.get("rules"):
        _err(warnings, "system_without_rules", sid, "규칙이 없습니다. 구현할 수 있게 규칙을 문장으로 적습니다.", owner=sid)


def _check_dependencies(live: dict, cut: set, known: set, lost: set, errors: list, warnings: list) -> None:
    """lost: 형식 오류로 빠진 시스템. 그 오류를 이미 알렸으므로 없는 시스템으로 다시 말하지 않는다."""
    rank = list(SCOPES)
    for s in live.values():
        for d in s.get("depends_on", []):
            if d in cut:
                _err(warnings, "cut_referenced", s["id"], f"삭제(cut)된 시스템에 의존합니다: {d}.", owner=s["id"], part=d)
            elif d in lost:
                continue
            elif d not in live:
                _err(errors, "unknown_system", s["id"], f"없는 시스템입니다: {d}.{did_you_mean(d, known)}")
            elif rank.index(live[d]["scope"]) > rank.index(s["scope"]):
                _err(errors, "scope_dependency", s["id"], f"{SCOPES[s['scope']]} 시스템이 {SCOPES[live[d]['scope']]} 시스템 {d}에 의존해 만들 수 없습니다. 범위를 맞추거나 의존을 끊습니다.")
    leaned = {d for s in live.values() if s["scope"] != "out" for d in s.get("depends_on", [])}
    for s in live.values():
        if s.get("foundation") and s["id"] not in leaned and not lost:  # 빠진 시스템이 기대고 있을 수 있다
            _err(warnings, "foundation_unused", s["id"], "기반 시스템인데 어떤 시스템도 기대지 않습니다. 의존을 적거나 foundation을 뺍니다.", owner=s["id"])


def _steps(live: dict) -> dict:
    """만드는 순서 {시스템: 단계}. 의존하는 시스템보다 뒤다. 범위 밖과 순환에 걸린 시스템은 단계가 없다."""
    built = {k: s for k, s in live.items() if s["scope"] != "out"}
    steps: dict = {}
    while True:
        ready = [k for k, s in built.items() if k not in steps and all(d in steps or d not in built for d in s.get("depends_on", []))]
        if not ready:
            return steps
        for k in ready:
            steps[k] = 1 + max([steps[d] for d in built[k].get("depends_on", []) if d in steps], default=0)


def _cycle(live: dict, steps: dict) -> list:
    """순환을 이루는 시스템. 순환에 매달렸을 뿐인 시스템은 뺀다."""
    left = {k for k, s in live.items() if s["scope"] != "out" and k not in steps}
    while True:
        needed = {d for k in left for d in live[k].get("depends_on", []) if d in left}
        if needed >= left:
            return sorted(left)
        left &= needed


def _check_coverage(live: dict, items: dict, warnings: list) -> None:
    """브리프가 말한 것을 만들 시스템이 맡는가. 나중으로 미룬 시스템은 MVP의 필러를 맡지 못한다.
    일부러 미룬 것이면 어느 시스템의 acknowledged에든 대상으로 적어 확인한다."""
    now = [s for s in live.values() if s["scope"] == "mvp"]

    def issue(code: str, part: str, text: str) -> None:
        owner = next((k for k, s in live.items() if c.ack_reason(s, code, part)), next(iter(live), None))
        _err(warnings, code, "brief", text, part=part, **({"owner": owner} if owner else {}))

    served = {x for s in now for x in s.get("pillars", [])}
    for p in items["pillars"]:
        if p not in served:
            issue("pillar_unserved", p, f"범위가 MVP인 시스템이 맡지 않는 필러입니다: {p}. 이대로 만들면 이 필러를 시험할 수 없습니다.")
    claimed = {x for s in now for x in s.get("mvp", [])}
    for m in items["mvp"]:
        if m not in claimed:
            issue("mvp_unserved", m, f"어떤 시스템도 맡지 않는 MVP 항목입니다: {m}.")


def validate(data: dict, concepts: list | None = None, concepts_unreadable: bool = False) -> dict:
    """concepts: 함께 읽은 컨셉 배열. None이면 브리프와의 연결을 확인하지 못한 것으로 센다."""
    errors: list = []
    warnings: list = []
    top = c.unknown_keys_text(data, TOP_FIELDS)
    if top:
        _err(errors, "schema", "systems", top)
    raw = data.get("systems")
    if not isinstance(raw, list):
        _err(errors, "schema", "systems", "systems(시스템 배열)가 필요합니다.")
        raw = []
    entries = [s for _, s in c.check_identity(raw, "systems", errors) if c.check_common(s, s["id"], errors)]
    known = {s["id"] for s in entries}
    good = [s for s in entries if _check_system(s, errors)]
    live = {s["id"]: s for s in good if c.is_active(s)}
    cut = {s["id"] for s in entries if not c.is_active(s)}
    missing: set = set()
    concept = None
    items = None
    if concepts is None:
        missing.add("concepts_unreadable" if concepts_unreadable else "concepts")
    else:
        concept = _pick_concept(data, concepts, errors, warnings)
        items = _brief_items(concept, errors)
    if not live and not errors:
        missing.add("nothing")
    for s in live.values():
        if items is not None:
            _check_links(s, items, errors)
            _check_text(s, items, errors)
        _check_scope(s, warnings)
    lost = {s.get("id") for s in raw if isinstance(s, dict)} - set(live) - cut
    _check_dependencies(live, cut, known, lost, errors, warnings)
    steps = _steps(live)
    loop = _cycle(live, steps)
    if loop:
        _err(errors, "dependency_cycle", loop[0], f"시스템이 서로 의존합니다: {', '.join(loop)}. 먼저 만들 수 있는 쪽이 없습니다. 의존을 끊거나 한 시스템으로 합칩니다.")
    if items is not None and not lost:   # 빠진 시스템이 맡던 것을 빠졌다고 말하지 않는다
        _check_coverage(live, items, warnings)
    order = list(SCOPES)
    rows = [{"id": s["id"], "name": s.get("name"), "scope": s["scope"], "foundation": s.get("foundation", False), "order": steps.get(s["id"]), "pillars": s.get("pillars", []), "mvp": s.get("mvp", []),
             "out_of_scope": s.get("out_of_scope", []), "depends_on": s.get("depends_on", []), "rules": len(s.get("rules", []))}
            for s in sorted(live.values(), key=lambda x: (steps.get(x["id"], 10 ** 6), order.index(x["scope"]), x["id"]))]
    return {
        "kind": "systems",
        "count": len(entries),
        **c.summary_counts(entries),
        "unverified": [],   # 시스템과 규칙은 설계 결정이다. 측정으로 올릴 수치가 아니라 출처 게이트에 걸지 않는다
        "concept": concept.get("id") if concept else None,
        "brief_out_of_scope": items["out_of_scope"] if items else None,
        "rows": rows,
        "unchecked": len(missing),
        "unchecked_kinds": sorted(missing),
        "errors": errors,
        "warnings": warnings,
    }


# ---------- 출력 ----------
def _title(x: dict) -> str:
    return f"{x['name']} ({x['id']})" if x["name"] else x["id"]


def print_extra(result: dict) -> None:
    if result["concept"]:
        print(f"연결한 컨셉: {result['concept']}")
    for x in result["rows"]:
        step = f"{x['order']}단계" if x["order"] else "단계 없음"
        print(f"시스템 {_title(x)}: {SCOPES[x['scope']]} · {step} · 규칙 {x['rules']}개")
    if {"concepts", "concepts_unreadable"} & set(result["unchecked_kinds"]):
        print("시스템 설계 미확인: 컨셉을 함께 검사하지 않았거나 읽지 못해 브리프와의 연결을 보지 못함")
    if "nothing" in result["unchecked_kinds"]:
        print("시스템 설계 미확인: 계산한 시스템이 없음(빈 systems이거나 모두 삭제)")


def table(data: dict, result: dict, ids: list[str] | None = None) -> str:
    """만드는 순서로 본 시스템 표(마크다운)."""
    rows = ["| 순서 | 시스템 | 범위 | 필러 | MVP | 의존 | 규칙 |", "|---|---|---|---|---|---|---|"]
    for x in result["rows"]:
        cells = ("–" if x["order"] is None else str(x["order"]), c.table_cell(_title(x)), SCOPES[x["scope"]] + ("(기반)" if x["foundation"] else ""), c.table_cell(", ".join(x["pillars"])), c.table_cell(", ".join(x["mvp"])),
                 c.table_cell(", ".join(x["depends_on"])), str(x["rules"]))
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join(rows)


def print_counts(result: dict) -> None:
    tail = f"오류 {len(result['errors'])} · 경고 {len(result['warnings'])}"
    if result.get("acknowledged"):
        tail += f" · 확인한 경고 {len(result['acknowledged'])}"
    print(f"시스템 {result['count']}개 · {tail}")
