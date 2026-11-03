"""플레이 기록과 가설 판정(data/playtests.json)을 결정적으로 검사한다.

재미나 가설의 참거짓을 판정하지 않는다. 판정 기록이 증거를 가리키는지, 가리킨 세션이 실제로 있고
그 가설을 관찰했는지, 선택한 컨셉의 가설 중 판정이 확정되지 않은 것이 무엇인지만 본다.
형식: playtest-verdict/references/playtest-record.md
"""
from __future__ import annotations

import re

from .common import STATUSES, check_identity, is_int, is_number
from .common import add_issue as _err

RESULTS = ("holds", "refuted", "unknown")
RESULT_LABEL = {"holds": "버팀", "refuted": "틀림", "unknown": "모름"}
DECIDED = ("holds", "refuted")
NOTE_KINDS = ("observation", "preference")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
UNCHECKED_REASON = {
    "no_concepts": "컨셉 데이터를 함께 검사하지 않음 — 프로젝트 폴더나 design/concepts.json을 같이 넘기세요",
    "concepts_unreadable": "컨셉 파일을 읽지 못함 — 컨셉 파일의 오류를 먼저 고치세요",
}


def _text(v) -> bool:
    return isinstance(v, str) and v.strip() != ""


def check_session(s: dict, errors: list, warnings: list) -> bool:
    where, ok = s["id"], True
    if not (isinstance(s.get("date"), str) and DATE.match(s["date"])):
        _err(errors, "schema", where, f"date는 YYYY-MM-DD 형식이어야 합니다: {s.get('date')!r}")
        ok = False
    for f in ("concept", "build"):
        if not _text(s.get(f)):
            _err(errors, "schema", where, f"{f}가 비어 있습니다." + (" 빌드는 커밋 해시나 빌드 이름입니다." if f == "build" else ""))
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
    if ok and not obs:
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


def validate(data: dict, concepts: dict | None = None, concepts_unreadable: bool = False) -> dict:
    """concepts: concepts.hypothesis_index()의 결과. None이면 컨셉·가설 참조를 확인하지 못한 것으로 센다."""
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
    for s in sessions.values():
        refs = [o["hypothesis"] for o in s.get("observations", [])]
        if concepts is None:
            unchecked += 1
        elif s["concept"] not in concepts:
            _err(errors, "unknown_concept", s["id"], f"컨셉 데이터에 없는 컨셉입니다: {s['concept']}")
        else:
            for h in dict.fromkeys(refs):
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
                _err(errors, "session_concept_mismatch", where, f"세션 {sid}는 {s['concept']}의 기록입니다.")
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
        "unchecked": unchecked,
        "unchecked_reason": reason,
        "errors": errors,
        "warnings": warnings,
    }


def print_extra(result: dict) -> None:
    for where, v in result["verdicts"].items():
        s = v["sample"]
        state = "확정" if v["status"] == "approved" else "제안"
        print(f"{where}: {RESULT_LABEL[v['result']]} ({state}) · 세션 {s['sessions']} · {s['runs']}판 · {s['players']}명")
    if result["unchecked"]:
        print(f"컨셉·가설 참조 미확인({UNCHECKED_REASON.get(result['unchecked_reason'], '')}): {result['unchecked']}건")


def print_counts(result: dict) -> None:
    rc = result["result_counts"]
    tail = f"오류 {len(result['errors'])} · 경고 {len(result['warnings'])}"
    if result.get("acknowledged"):
        tail += f" · 확인한 경고 {len(result['acknowledged'])}"
    print(f"플레이 기록 {result['count']}개 · 판정 버팀 {rc['holds']} · 틀림 {rc['refuted']} · 모름 {rc['unknown']} · {tail}")
