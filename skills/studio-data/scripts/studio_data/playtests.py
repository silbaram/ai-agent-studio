"""플레이 기록과 가설 판정(data/playtests.json)을 결정적으로 검사한다.

재미나 가설의 참거짓을 판정하지 않는다. 판정 기록이 증거를 가리키는지, 가리킨 세션이 실제로 있고
그 가설을 관찰했는지, 선택한 컨셉의 가설 중 판정이 확정되지 않은 것이 무엇인지만 본다.
형식: playtest-verdict/references/playtest-record.md
"""
from __future__ import annotations

import re

from .common import STATUSES, check_identity, did_you_mean, is_int, is_number, unknown_keys_text, josa
from .common import add_issue as _err

RESULTS = ("holds", "refuted", "unknown")
RESULT_LABEL = {"holds": "버팀", "refuted": "틀림", "unknown": "모름"}
DECIDED = ("holds", "refuted")
NOTE_KINDS = ("observation", "preference")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
STAGE_FIELDS = {"stage", "entered", "cleared", "level", "duration", "kills", "income", "source", "note"}
GROUP_FIELDS = {"upgrades", "growth_build", "stage_stats"}
GREYBOX_FIELDS = {"check", "value", "passed", "n", "source", "note"}
REF_LABEL = {"stages": "전투 단계", "upgrades": "영구 강화", "enemies": "적", "builds": "판 안 성장 빌드", "currencies": "재화", "greybox": "그레이박스 확인"}
UNCHECKED_REASON = {
    "no_concepts": "컨셉 데이터를 함께 검사하지 않음 — 프로젝트 폴더나 design/concepts.json을 같이 넘기세요",
    "concepts_unreadable": "컨셉 파일을 읽지 못함 — 컨셉 파일의 오류를 먼저 고치세요",
}


def _text(v) -> bool:
    return isinstance(v, str) and v.strip() != ""


def _amounts(v) -> bool:
    return isinstance(v, dict) and all(isinstance(k, str) and is_number(x) and x >= 0 for k, x in v.items())


def _check_records(holder: dict, label: str, runs, where: str, errors: list, warnings: list) -> bool:
    """단계 기록 배열 하나(세션 또는 묶음). 판 수는 정수, 나머지는 판 평균이다."""
    ok = True
    stats = holder.get("stage_stats", [])
    if not isinstance(stats, list):
        _err(errors, "schema", where, f"{label}stage_stats는 단계 기록 배열입니다(판에서 지나는 순서대로).")
        return False
    seen: set = set()
    for n, x in enumerate(stats):
        at = f"{label}stage_stats[{n}]"
        if not (isinstance(x, dict) and _text(x.get("stage")) and is_int(x.get("entered"), 0) and is_int(x.get("cleared"), 0)):
            _err(errors, "schema", where, f"{at}에 stage(전투 단계 id)와 정수 entered(들어간 판), cleared(넘긴 판)가 필요합니다.")
            ok = False
            continue
        unknown = unknown_keys_text(x, STAGE_FIELDS)
        if unknown:
            _err(errors, "schema", where, f"{at}: {unknown}")
            ok = False
        if x["stage"] in seen:
            _err(errors, "schema", where, f"{at}: 단계 {x['stage']}의 기록이 둘입니다. 묶음마다 단계 하나에 기록 하나입니다.")
            ok = False
        seen.add(x["stage"])
        if x["cleared"] > x["entered"]:
            _err(errors, "schema", where, f"{at}: cleared {josa(x['cleared'], '이가')} entered {x['entered']}보다 큽니다.")
            ok = False
        if is_int(runs) and x["entered"] > runs:
            _err(errors, "schema", where, f"{at}: entered {josa(x['entered'], '이가')} 세션의 판 수 {runs}보다 큽니다.")
            ok = False
        if "level" in x and not (is_number(x["level"]) and x["level"] >= 1):
            _err(errors, "schema", where, f"{at}: level은 1 이상의 수입니다(그 단계에 들어설 때의 평균 레벨): {x['level']!r}")
            ok = False
        if "duration" in x and not (is_number(x["duration"]) and x["duration"] > 0):
            _err(errors, "schema", where, f"{at}: duration은 0보다 큰 수입니다: {x['duration']!r}")
            ok = False
        for key in ("kills", "income"):
            if key in x and not _amounts(x[key]):
                _err(errors, "schema", where, f"{at}: {josa(key, '은는')} {{id: 0 이상의 판 평균}}입니다.")
                ok = False
    if ok:
        for a, b in zip(stats, stats[1:]):
            if b["entered"] > a["cleared"]:
                _err(warnings, "stage_counts_mismatch", where,
                     f"단계 {b['stage']}에 {b['entered']}판이 들어갔는데 앞 단계 {josa(a['stage'], '을를')} 넘긴 판은 {a['cleared']}판입니다. 기록을 확인합니다.")
    return ok


def _upgrade_list(v) -> bool:
    return isinstance(v, list) and all(_text(x) for x in v)


def check_stage_stats(s: dict, errors: list, warnings: list) -> bool:
    """세션의 단계 기록과 그때의 상태. 강화가 한 가지면 세션에 stage_stats·upgrades를, 판 사이에 바뀌면 groups에 상태별로 적는다."""
    where, ok = s["id"], True
    if "growth_build" in s and not _text(s["growth_build"]):
        _err(errors, "schema", where, f"growth_build는 판 안 성장의 빌드 id입니다: {s['growth_build']!r}")
        ok = False
    groups = s.get("groups")
    if groups is None:
        if not _upgrade_list(s.get("upgrades", [])):
            _err(errors, "schema", where, "upgrades는 이 세션의 플레이어가 가진 영구 강화 id 배열입니다(없으면 []).")
            ok = False
        return _check_records(s, "", s.get("runs"), where, errors, warnings) and ok
    if not (isinstance(groups, list) and groups and all(isinstance(g, dict) for g in groups)):
        _err(errors, "schema", where, "groups는 강화 상태별 묶음 {upgrades, growth_build, stage_stats} 배열입니다.")
        return False
    for key in ("stage_stats", "upgrades"):
        if key in s:
            _err(errors, "schema", where, f"groups를 쓰면 세션의 {josa(key, '을를')} 함께 쓰지 않습니다. 묶음마다 적습니다.")
            ok = False
    totals: dict = {}
    for n, g in enumerate(groups):
        label = f"groups[{n}]."
        unknown = unknown_keys_text(g, GROUP_FIELDS)
        if unknown:
            _err(errors, "schema", where, f"{label[:-1]}: {unknown}")
            ok = False
        if not _upgrade_list(g.get("upgrades")):
            _err(errors, "schema", where, f"{label}upgrades가 필요합니다(그 묶음의 판을 시작할 때 가진 영구 강화 id, 없으면 []).")
            ok = False
        if "growth_build" in g and not _text(g["growth_build"]):
            _err(errors, "schema", where, f"{label}growth_build는 판 안 성장의 빌드 id입니다: {g['growth_build']!r}")
            ok = False
        if not (isinstance(g.get("stage_stats"), list) and g["stage_stats"]):
            _err(errors, "schema", where, f"{label}stage_stats(단계 기록 배열)가 필요합니다.")
            ok = False
            continue
        ok = _check_records(g, label, s.get("runs"), where, errors, warnings) and ok
        for x in g["stage_stats"]:
            if isinstance(x, dict) and _text(x.get("stage")) and is_int(x.get("entered"), 0):
                totals[x["stage"]] = totals.get(x["stage"], 0) + x["entered"]
    over = [k for k, v in totals.items() if is_int(s.get("runs")) and v > s["runs"]]
    if over:
        _err(errors, "schema", where, f"묶음을 합친 entered가 세션의 판 수 {s.get('runs')}보다 큰 단계: {', '.join(over)}")
        ok = False
    return ok


def _holders(s: dict) -> list:
    """세션의 단계 기록을 담은 곳: groups가 있으면 묶음들, 없으면 세션 자신."""
    return s["groups"] if s.get("groups") else [s]


def _used_refs(s: dict) -> dict:
    out: dict = {"stages": [], "upgrades": [], "enemies": [], "builds": [], "currencies": [], "greybox": [x["check"] for x in s.get("greybox", [])]}
    for h in _holders(s):
        stats = h.get("stage_stats", [])
        if not stats:
            continue
        build = h.get("growth_build", s.get("growth_build"))
        out["stages"] += [x["stage"] for x in stats]
        out["upgrades"] += h.get("upgrades", [])
        out["enemies"] += [k for x in stats for k in x.get("kills", {})]
        out["builds"] += [build] if build else []
        out["currencies"] += [k for x in stats for k in x.get("income", {})]
    return out


def check_refs(s: dict, refs: dict | None, warnings: list, missing: set) -> None:
    """단계 기록이 가리키는 id. 기록은 지난 빌드의 사실이라 데이터가 바뀌어도 고치지 않으므로, 없는 id는 오류가 아니라 경고다
    (calibrate의 통과율 비교는 지금 데이터로 계산할 수 없는 기록을 뺀다). 함께 읽지 않은 데이터는 미확인으로 센다."""
    for kind, ids in _used_refs(s).items():
        if not ids:
            continue
        known = (refs or {}).get(kind)
        if known is None:
            missing.add(kind)
            continue
        for x in dict.fromkeys(ids):
            if x not in known:
                advice = (" levels.json의 greybox에 있는 항목 id를 적습니다. 그 뒤에 항목을 지웠으면 기록은 그대로 둡니다." if kind == "greybox" else
                          " 그 뒤에 바뀐 것이면 기록은 그대로 둡니다(calibrate의 통과율 비교는 지금 데이터로 계산할 수 없는 기록을 뺍니다).")
                _err(warnings, "unknown_reference", s["id"], f"{REF_LABEL[kind]} 데이터에 없는 id입니다: {x}.{did_you_mean(x, known)}{advice}")


def _check_greybox(s: dict, where: str, errors: list) -> bool:
    """세션의 그레이박스 확인 기록. 수(value)나 판정(passed) 중 하나는 있어야 기록이다."""
    rows = s.get("greybox", [])
    if not isinstance(rows, list):
        _err(errors, "schema", where, "greybox는 확인 기록 {check, value, passed, n} 배열입니다.")
        return False
    ok = True
    for n, x in enumerate(rows):
        at = f"greybox[{n}]"
        if not (isinstance(x, dict) and _text(x.get("check")) and ("value" in x or "passed" in x)):
            _err(errors, "schema", where, f"{at}에 check(확인 항목 id)와 value(값)나 passed(판정)가 필요합니다.")
            ok = False
            continue
        unknown = unknown_keys_text(x, GREYBOX_FIELDS)
        if unknown:
            _err(errors, "schema", where, f"{at}: {unknown}")
            ok = False
        if "value" in x and not is_number(x["value"]):
            _err(errors, "schema", where, f"{at}.value는 수입니다. 수로 잴 수 없으면 passed(true나 false)를 적습니다.")
            ok = False
        if "passed" in x and not isinstance(x["passed"], bool):
            _err(errors, "schema", where, f"{at}.passed는 true나 false입니다.")
            ok = False
        if "n" in x and not is_int(x["n"], 1):
            _err(errors, "schema", where, f"{at}.n(해 본 판 수)은 1 이상의 정수여야 합니다. 해 보지 않았으면 기록을 적지 않습니다.")
            ok = False
    return ok


def check_session(s: dict, errors: list, warnings: list) -> bool:
    where, ok = s["id"], True
    if not (isinstance(s.get("date"), str) and DATE.match(s["date"])):
        _err(errors, "schema", where, f"date는 YYYY-MM-DD 형식이어야 합니다: {s.get('date')!r}")
        ok = False
    for f in ("concept", "build"):
        if not _text(s.get(f)):
            _err(errors, "schema", where, f"{josa(f, '이가')} 비어 있습니다." + (" 빌드는 커밋 해시나 빌드 이름입니다." if f == "build" else ""))
            ok = False
    players = s.get("players")
    if not (isinstance(players, list) and players and all(_text(p) for p in players)):
        _err(errors, "schema", where, "players는 플레이한 사람 이름(문자열)이 1개 이상인 배열이어야 합니다.")
        ok = False
    runs = s.get("runs")
    if not is_int(runs, 1):
        _err(errors, "schema", where, f"runs(판 수)는 1 이상의 정수여야 합니다: {runs!r}")
        ok = False
    obs = s.get("observations", [])
    if not isinstance(obs, list):
        _err(errors, "schema", where, "observations는 배열이어야 합니다.")
        return False
    for n, o in enumerate(obs):
        if not (isinstance(o, dict) and _text(o.get("hypothesis")) and (_text(o.get("value")) or is_number(o.get("value")))):
            _err(errors, "schema", where, f"observations[{n}]에 hypothesis(가설 id)와 value(관찰값)가 필요합니다.")
            ok = False
        elif "n" in o and not is_int(o["n"], 0):
            _err(errors, "schema", where, f"observations[{n}].n(표본 수)은 0 이상의 정수여야 합니다.")
            ok = False
    notes = s.get("notes", [])
    if not (isinstance(notes, list) and all(isinstance(x, dict) and x.get("kind") in NOTE_KINDS and _text(x.get("text")) for x in notes)):
        _err(errors, "schema", where, "notes는 {kind: observation(관찰) / preference(선호), text} 배열이어야 합니다.")
        ok = False
    logs = s.get("logs", [])
    if not (isinstance(logs, list) and all(_text(x) for x in logs)):
        _err(errors, "schema", where, "logs는 기록 파일 경로(문자열) 배열이어야 합니다.")
        ok = False
    ok = check_stage_stats(s, errors, warnings) and ok
    ok = _check_greybox(s, where, errors) and ok
    if ok and not obs and not s.get("stage_stats") and not s.get("groups") and not s.get("greybox"):
        warnings.append({"code": "session_without_observations", "where": where,
                         "message": "가설에 대한 관찰값이 없습니다. 이 세션은 어떤 가설의 증거도 되지 못합니다."})
    return ok


def check_verdict(v, n: int, errors: list) -> str | None:
    """형식이 맞으면 판정 위치(컨셉.가설)를 돌려준다."""
    if not (isinstance(v, dict) and _text(v.get("concept")) and _text(v.get("hypothesis"))):
        _err(errors, "schema", f"verdicts[{n}]", "판정에는 concept와 hypothesis(가설 id)가 필요합니다.")
        return None
    where, ok = f"{v['concept']}.{v['hypothesis']}", True
    if v.get("result") not in RESULTS:
        _err(errors, "schema", where, f"result는 {', '.join(RESULTS)} 중 하나입니다: {v.get('result')!r}")
        ok = False
    if not _text(v.get("reason")):
        _err(errors, "schema", where, "reason(판정 이유)이 비어 있습니다. 모름이면 무엇이 부족한지 적습니다.")
        ok = False
    if v.get("status") is not None and v.get("status") not in STATUSES:
        _err(errors, "schema", where, f"status는 {', '.join(STATUSES)} 중 하나입니다: {v.get('status')!r}")
        ok = False
    sessions = v.get("sessions", [])
    if not (isinstance(sessions, list) and all(_text(x) for x in sessions)):
        _err(errors, "schema", where, "sessions는 세션 id(문자열) 배열이어야 합니다.")
        ok = False
    return where if ok else None


def _hypothesis_ref(concept: str, hyp: str, where: str, concepts: dict, errors: list) -> bool:
    info = concepts.get(concept)
    if info is None:
        _err(errors, "unknown_concept", where, f"컨셉 데이터에 없는 컨셉입니다: {concept}")
        return False
    ids = [h for h in info["hypotheses"] if h]
    if hyp in ids:
        return True
    if ids:
        hint = f"이 컨셉의 가설 id: {', '.join(ids)}"
    else:
        hint = f"{concept}의 brief.hypotheses에 id가 없습니다. 가설마다 id를 넣으세요"
    _err(errors, "unknown_hypothesis", where, f"없는 가설 '{hyp}'. {hint}.")
    return False


def validate(data: dict, concepts: dict | None = None, concepts_unreadable: bool = False, refs: dict | None = None) -> dict:
    """concepts: concepts.hypothesis_index()의 결과. None이면 컨셉·가설 참조를 확인하지 못한 것으로 센다.
    refs: 단계 기록이 가리키는 id {stages, upgrades, enemies, builds, currencies}. 값이 None인 종류는 쓰면 미확인이다."""
    errors: list = []
    warnings: list = []
    raw = data.get("playtests")
    if not isinstance(raw, list):
        _err(errors, "schema", "playtests", "playtests 배열이 필요합니다.")
        raw = []
    raw_verdicts = data.get("verdicts", [])
    if not isinstance(raw_verdicts, list):
        _err(errors, "schema", "verdicts", "verdicts는 배열이어야 합니다.")
        raw_verdicts = []
    sessions = {s["id"]: s for _, s in check_identity(raw, "playtests", errors) if check_session(s, errors, warnings)}
    unchecked = 0
    missing_refs: set = set()
    for s in sessions.values():
        check_refs(s, refs, warnings, missing_refs)
        observed = [o["hypothesis"] for o in s.get("observations", [])]
        if concepts is None:
            unchecked += 1
        elif s["concept"] not in concepts:
            _err(errors, "unknown_concept", s["id"], f"컨셉 데이터에 없는 컨셉입니다: {s['concept']}")
        else:
            for h in dict.fromkeys(observed):
                _hypothesis_ref(s["concept"], h, s["id"], concepts, errors)

    verdicts: dict = {}
    status_counts = {st: 0 for st in STATUSES + ("unspecified",)}
    for n, v in enumerate(raw_verdicts):
        where = check_verdict(v, n, errors)
        if where is None:
            continue
        status = v.get("status") or "unspecified"
        status_counts[status] += 1
        if status == "cut":
            continue  # 지난 판정은 기록으로만 남긴다
        if where in verdicts:
            _err(errors, "duplicate_verdict", where, "삭제(cut)되지 않은 판정이 둘 이상입니다. 지난 판정은 status를 cut으로 두고 남깁니다.")
            continue
        if concepts is None:
            unchecked += 1
        elif not _hypothesis_ref(v["concept"], v["hypothesis"], where, concepts, errors):
            continue
        cited = v.get("sessions", [])
        if v["result"] in DECIDED and not cited:
            _err(errors, "verdict_without_evidence", where,
                 f"{RESULT_LABEL[v['result']]} 판정에 근거 세션(sessions)이 없습니다. 기록이 없으면 unknown(모름)으로 둡니다.")
        found = []
        for sid in cited:
            s = sessions.get(sid)
            if s is None:
                if not any(isinstance(x, dict) and x.get("id") == sid for x in raw):
                    _err(errors, "unknown_session", where, f"플레이 기록에 없는 세션입니다: {sid}")
                continue  # 형식 오류가 있는 세션은 그 세션 쪽에서 이미 보고했다
            if s["concept"] != v["concept"]:
                _err(errors, "session_concept_mismatch", where, f"세션 {josa(sid, '은는')} {s['concept']}의 기록입니다.")
                continue
            found.append(s)
        if v["result"] in DECIDED and found and not any(o["hypothesis"] == v["hypothesis"] for s in found for o in s.get("observations", [])):
            _err(errors, "observation_missing", where,
                 f"근거로 든 세션에 가설 '{v['hypothesis']}'의 관찰값이 없습니다. 관찰값을 세션에 적거나 unknown(모름)으로 둡니다.")
        verdicts[where] = {
            "result": v["result"], "status": status, "reason": v["reason"],
            "sample": {"sessions": len(found), "runs": sum(s["runs"] for s in found),
                       "players": len({p.strip() for s in found for p in s["players"]})},
        }

    unverified: list = []
    if concepts is not None:
        for cid, info in sorted(concepts.items()):
            if not info["approved"]:
                continue
            for i, h in enumerate(info["hypotheses"]):
                key = f"{cid}.{h}" if h else f"{cid}.brief.hypotheses[{i}]"
                got = verdicts.get(key)
                if not (got and got["result"] in DECIDED and got["status"] == "approved"):
                    unverified.append(key)
    counts = {r: sum(1 for x in verdicts.values() if x["result"] == r) for r in RESULTS}
    reason = None
    if unchecked:
        reason = "concepts_unreadable" if concepts_unreadable else "no_concepts"
    return {
        "kind": "playtests",
        "count": len(sessions),
        "status_counts": status_counts,
        "result_counts": counts,
        "verdicts": verdicts,
        "unverified": unverified,
        "unchecked": unchecked + len(missing_refs),
        "unchecked_reason": reason,
        "unchecked_refs": sorted(missing_refs),
        "errors": errors,
        "warnings": warnings,
    }


def print_extra(result: dict) -> None:
    for where, v in result["verdicts"].items():
        s = v["sample"]
        state = "확정" if v["status"] == "approved" else "제안"
        print(f"{where}: {RESULT_LABEL[v['result']]} ({state}) · 세션 {s['sessions']} · {s['runs']}판 · {s['players']}명")
    if result["unchecked_reason"]:
        print(f"컨셉·가설 참조 미확인({UNCHECKED_REASON.get(result['unchecked_reason'], '')}): {result['unchecked'] - len(result['unchecked_refs'])}건")
    if result["unchecked_refs"]:
        print("기록의 참조 미확인(그 데이터를 함께 검사하지 않음): " + ", ".join(REF_LABEL[k] for k in result["unchecked_refs"]))


def print_counts(result: dict) -> None:
    rc = result["result_counts"]
    tail = f"오류 {len(result['errors'])} · 경고 {len(result['warnings'])}"
    if result.get("acknowledged"):
        tail += f" · 확인한 경고 {len(result['acknowledged'])}"
    print(f"플레이 기록 {result['count']}개 · 판정 버팀 {rc['holds']} · 틀림 {rc['refuted']} · 모름 {rc['unknown']} · {tail}")
