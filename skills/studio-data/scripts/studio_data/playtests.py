"""플레이 기록과 가설 판정(data/playtests.json)을 결정적으로 검사한다.

재미나 가설의 참거짓을 판정하지 않는다. 판정 기록이 증거를 가리키는지, 가리킨 세션이 실제로 있고
그 가설을 관찰했는지, 선택한 컨셉의 가설 중 판정이 확정되지 않은 것이 무엇인지만 본다.
형식: playtest-verdict/references/playtest-record.md
"""
from __future__ import annotations

import datetime
import posixpath
import re
from pathlib import Path

from .common import ID_PATTERN, STATUSES, YARDSTICK_TAG, ack_reason, check_identity, did_you_mean, is_int, is_number, unknown_keys_text, josa
from .common import add_issue as _err

RESULTS = ("holds", "refuted", "unknown")
RESULT_LABEL = {"holds": "버팀", "refuted": "틀림", "unknown": "모름"}
DECIDED = ("holds", "refuted")
CRITERIA_GATE_REASON = {"missing": "지문 없음", "changed": "기준 바뀜"}
NOT_CHOSEN_GATE = "이 컨셉은 지금 선택(approved)한 컨셉이 아니라 게이트에 들지 않습니다. 다시 고르면 확정해도 게이트를 넘지 못합니다. "
NOTE_KINDS = ("observation", "preference", "deviation")  # deviation: 가설 test의 시험 절차를 어긴 일(순서, 중간 결과를 본 뒤 플레이 등)
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PATH_LIKE = re.compile(r"^(?!.*://).*\.[A-Za-z][A-Za-z0-9]{0,4}$")  # 확장자로 끝나는 source만 파일로 본다. URL, 말, 앵커(#), 판 번호(v1.2)는 보지 않는다
COMPUTED = "[계산"
CRITERIA = re.compile(r"^[0-9a-f]{8}$")
NUMBER = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")  # 낱말에 붙은 수(pt_2, v1.2)는 보지 않는다. 0-60은 0과 60이다. 1e-05는 수 하나다
DATE_TIME = re.compile(r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?")  # 관찰값의 날짜·시각은 수로 보지 않는다
SOURCE_READ_LIMIT = 5_000_000
STAGE_FIELDS = {"stage", "entered", "cleared", "level", "level_end", "duration", "timed", "kills", "kill_rate", "played_length", "income", "source", "note"}
GROUP_FIELDS = {"upgrades", "growth_build", "variant", "runs", "players", "stage_stats"}
GREYBOX_FIELDS = {"check", "value", "passed", "n", "source", "note"}
SESSION_FIELDS = {"id", "date", "concept", "build", "game_build", "players", "runs", "events", "observations", "notes", "logs", "stage_stats", "upgrades", "growth_build", "groups", "greybox", "acknowledged", "note"}
TOP_FIELDS = {"playtests", "verdicts", "note"}
REF_LABEL = {"stages": "전투 단계", "upgrades": "영구 강화", "enemies": "적", "builds": "판 안 성장 빌드", "currencies": "재화", "greybox": "그레이박스 확인"}
UNCHECKED_REASON = {
    "no_concepts": "컨셉 데이터를 함께 검사하지 않음 — 프로젝트 폴더나 design/concepts.json을 같이 넘기세요",
    "concepts_unreadable": "컨셉 파일을 읽지 못함 — 컨셉 파일의 오류를 먼저 고치세요",
}


def valid_date(v) -> bool:
    """YYYY-MM-DD이고 달력에 있는 날짜인가. 기록의 순서가 날짜로 정해지므로 틀린 날짜는 판정을 바꾼다."""
    if not (isinstance(v, str) and DATE.match(v)):
        return False
    try:
        datetime.date.fromisoformat(v)
    except ValueError:
        return False
    return True


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
        if "level_end" in x and not (is_number(x["level_end"]) and x["level_end"] >= 1):
            _err(errors, "schema", where, f"{at}: level_end는 1 이상의 수입니다(그 단계를 넘긴 판이 단계를 끝낼 때의 평균 레벨): {x['level_end']!r}")
            ok = False
        if "duration" in x and not (is_number(x["duration"]) and x["duration"] > 0):
            _err(errors, "schema", where, f"{at}: duration은 0보다 큰 수입니다: {x['duration']!r}")
            ok = False
        if "timed" in x and not isinstance(x["timed"], bool):
            _err(errors, "schema", where, f"{at}: timed는 true/false입니다(시간이 다 되면 끝나는 단계): {x['timed']!r}")
            ok = False
        for key in ("kills", "income"):
            if key in x and not _amounts(x[key]):
                _err(errors, "schema", where, f"{at}: {josa(key, '은는')} {{id: 0 이상의 판 평균}}입니다.")
                ok = False
        if "played_length" in x and not (is_number(x["played_length"]) and x["played_length"] > 0):
            _err(errors, "schema", where, f"{at}: played_length는 0보다 큰 수입니다(kill_rate를 낸 판들의 길이 합): {x['played_length']!r}")
            ok = False
        if "kill_rate" in x and not _amounts(x["kill_rate"]):
            _err(errors, "schema", where, f"{at}: kill_rate는 {{적 id: 들어간 판 전체의 길이 1당 처치 수}}입니다.")
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
        _err(errors, "schema", where, "groups는 강화 상태별 묶음 {upgrades, growth_build, variant, stage_stats} 배열입니다.")
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
        if "runs" in g and not is_int(g["runs"], 1):
            _err(errors, "schema", where, f"{label}runs는 그 묶음의 판 수(1 이상의 정수)입니다(runlog가 씁니다): {g['runs']!r}")
            ok = False
        if "players" in g and not (isinstance(g["players"], list) and g["players"] and all(_text(p) for p in g["players"])):
            _err(errors, "schema", where, f"{label}players는 그 묶음의 판을 한 사람 이름 배열입니다(runlog가 씁니다): {g['players']!r}")
            ok = False
        variant = g.get("variant")
        if "variant" in g and not (isinstance(variant, dict) and variant
                                   and all(_text(k) and (_text(x) or (is_number(x) and not isinstance(x, bool))) for k, x in variant.items())):
            _err(errors, "schema", where, f"{label}variant는 강화 밖의 시험 조건 {{로그 열: 값}}입니다(runlog --group-by가 씁니다): {variant!r}")
            ok = False
        if not (isinstance(g.get("stage_stats"), list) and g["stage_stats"]):
            _err(errors, "schema", where, f"{label}stage_stats(단계 기록 배열)가 필요합니다.")
            ok = False
            continue
        ok = _check_records(g, label, g["runs"] if is_int(g.get("runs"), 1) else s.get("runs"), where, errors, warnings) and ok
        for x in g["stage_stats"]:
            if isinstance(x, dict) and _text(x.get("stage")) and is_int(x.get("entered"), 0):
                totals[x["stage"]] = totals.get(x["stage"], 0) + x["entered"]
    counted = [g["runs"] for g in groups if is_int(g.get("runs"), 1)]
    if counted and is_int(s.get("runs")) and sum(counted) > s["runs"]:
        _err(errors, "schema", where, f"묶음의 runs를 합친 {sum(counted)}판이 세션의 판 수 {s['runs']}보다 큽니다.")
        ok = False
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
        out["enemies"] += [k for x in stats for key in ("kills", "kill_rate") for k in x.get(key, {})]
        out["builds"] += [build] if build else []
        out["currencies"] += [k for x in stats for k in x.get("income", {})]
    return out


def check_refs(s: dict, refs: dict | None, errors: list, warnings: list, missing: set) -> None:
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
                hint = did_you_mean(x, known)
                # 그레이박스 기록의 오타는 그 기록을 버려서 앞 판정이 그대로 남으므로 경고로 두지 않는다
                _err(errors if kind == "greybox" and hint else warnings, "unknown_reference", s["id"], f"{REF_LABEL[kind]} 데이터에 없는 id입니다: {x}.{hint}{advice}")


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
    if not valid_date(s.get("date")):
        _err(errors, "schema", where, f"date는 달력에 있는 YYYY-MM-DD 날짜여야 합니다: {s.get('date')!r}")
        ok = False
    unknown = unknown_keys_text(s, SESSION_FIELDS)
    if unknown:
        _err(errors, "schema", where, f"{unknown} 빠진 값은 판정에 들어가지 않습니다.")
    for f in ("concept", "build"):
        if not _text(s.get(f)):
            _err(errors, "schema", where, f"{josa(f, '이가')} 비어 있습니다." + (" 빌드는 커밋 해시나 빌드 이름입니다." if f == "build" else ""))
            ok = False
    if "game_build" in s and not _text(s["game_build"]):
        _err(errors, "schema", where, f"game_build는 프로토타입이 판 로그에 남긴 빌드 지문입니다(예: cfg721feeb5): {s['game_build']!r}")
        ok = False
    players = s.get("players")
    if not (isinstance(players, list) and players and all(_text(p) for p in players)):
        _err(errors, "schema", where, "players는 플레이한 사람 이름(문자열)이 1개 이상인 배열이어야 합니다.")
        ok = False
    runs = s.get("runs")
    if not is_int(runs, 1):
        _err(errors, "schema", where, f"runs(판 수)는 1 이상의 정수여야 합니다: {runs!r}")
        ok = False
    ev = s.get("events")
    if "events" in s and not (isinstance(ev, dict) and all(isinstance(k, str) and ID_PATTERN.match(k) and is_int(x, 0) for k, x in ev.items())):
        _err(errors, "schema", where, "events는 {사건 이름(소문자·숫자·밑줄): 이 세션에서 센 건수(0 이상의 정수)} 객체입니다. 이름은 가설 sample.events와 같게 씁니다.")
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
        elif COMPUTED in str(o.get("note") or "") and (not _text(o.get("source")) or _same_path(o["source"], s.get("logs"))):
            warnings.append({"code": "computed_without_output", "where": where,
                             "message": f"observations[{n}]는 계산한 값인데 source가 결과 파일이 아닙니다({o.get('source') or '없음'}). "
                                        "판정 에이전트는 스크립트를 돌리지 못하므로, 계산 출력을 세션 폴더에 결과 파일로 남기고 source로 둡니다."})
    notes = s.get("notes", [])
    if not (isinstance(notes, list) and all(isinstance(x, dict) and x.get("kind") in NOTE_KINDS and _text(x.get("text")) for x in notes)):
        _err(errors, "schema", where, "notes는 {kind: observation(관찰) / preference(선호) / deviation(절차 이탈), text} 배열이어야 합니다.")
        ok = False
    elif any("hypotheses" in x and not (isinstance(x["hypotheses"], list) and x["hypotheses"] and all(_text(h) for h in x["hypotheses"])) for x in notes):
        _err(errors, "schema", where, "notes의 hypotheses는 그 메모가 가리키는 가설 id 배열입니다(절차 이탈을 그 가설의 판정에만 셉니다).")
        ok = False
    logs = s.get("logs", [])
    if not (isinstance(logs, list) and all(_text(x) for x in logs)):
        _err(errors, "schema", where, "logs는 기록 파일 경로(문자열) 배열이어야 합니다.")
        ok = False
    ok = check_stage_stats(s, errors, warnings) and ok
    ok = _check_greybox(s, where, errors) and ok
    if ok:
        _check_beyond_records(s, warnings)
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
    if "criteria" in v and not (isinstance(v["criteria"], str) and CRITERIA.match(v["criteria"])):
        _err(errors, "schema", where, f"criteria(판정 기준 지문)는 소문자 16진수 8자입니다. 지금 지문은 check가 알려 줍니다: {v['criteria']!r}")
        ok = False
    if "cut_reason" in v and not (_text(v["cut_reason"]) and v.get("status") == "cut"):
        _err(errors, "schema", where, "cut_reason은 지난 판정(status cut)에 지운 날짜와 까닭을 적는 글입니다. 기준을 고쳐 지웠으면 바뀐 기준 문장도 적습니다.")
        ok = False
    if "next_needs" in v and not _text(v["next_needs"]):
        _err(errors, "schema", where, "next_needs는 다음 시험 전에 풀 것을 적는 글입니다(비우지 않습니다).")
        ok = False
    if "proposed_result" in v and v["proposed_result"] not in RESULTS:
        _err(errors, "schema", where, f"proposed_result(판정 에이전트가 낸 결과)는 {', '.join(RESULTS)} 중 하나입니다: {v['proposed_result']!r}")
        ok = False
    return where if ok else None


def _check_override(v: dict, where: str, errors: list) -> None:
    """사용자는 제안을 모름으로 낮춰 확정할 수 있다. 버팀·틀림으로 올리거나 둘을 바꾸려면 다시 판정한다."""
    proposed = v.get("proposed_result")
    if proposed is None or proposed == v["result"] or v["result"] == "unknown":
        return
    _err(errors, "verdict_overrides_proposal", where,
         f"판정 에이전트의 제안은 {RESULT_LABEL[proposed]}, 적힌 결과는 {RESULT_LABEL[v['result']]}입니다. "
         "제안을 모름으로 낮추는 것만 사용자가 바꿔 확정할 수 있습니다. 버팀·틀림으로 바꾸려면 바꾸려는 까닭을 판정 에이전트에게 주고 다시 판정합니다.")


def _check_criteria(v: dict, where: str, concepts: dict | None, warnings: list, restamp: dict | None = None) -> str:
    """판정의 기준 지문(criteria)을 지금 가설 기준과 견준다. ok / missing(지문 없음) / changed(판정 뒤에 기준이 바뀜).
    예전 꼴로 계산한 지문이 맞으면 ok이고, restamp에 {판정: {from, to}}를 남긴다(지금 꼴로 바꿔 두면 태그를 더해도 지문이 그대로다)."""
    info = concepts[v["concept"]] if concepts is not None else {}
    current = info.get("criteria", {}).get(v["hypothesis"])
    chosen = info.get("approved", True)   # 되돌린 컨셉의 판정은 게이트에 들지 않는다
    if not current:
        return "ok"
    if "criteria" not in v:
        warnings.append({"code": "verdict_criteria_missing", "where": where,
                         "message": "판정에 기준 지문이 없어 판정 뒤에 기준(claim, failure_signal, test, sample)이 바뀌어도 알 수 없습니다. "
                                    + ("확정해도 게이트(--fail-on-assumed)를 넘지 못합니다. " if chosen else NOT_CHOSEN_GATE)
                                    + f"판정 에이전트가 돌려준 지문을 적습니다. 판정한 뒤 가설을 고치지 않았으면 지금 지문을 적어도 됩니다: \"criteria\": \"{current}\"."})
        return "missing"
    if v["criteria"] == current:
        return "ok"
    if v["criteria"] in info.get("legacy_criteria", {}).get(v["hypothesis"], ()):   # 예전 꼴의 지문도 같은 기준이다(태그만 다르게 계산함)
        if restamp is not None:
            restamp[where] = {"from": v["criteria"], "to": current}
        return "ok"
    warnings.append({"code": "verdict_criteria_changed", "where": where,
                     "message": "판정 뒤에 가설 기준(claim, failure_signal, test, sample)이 바뀌었습니다. "
                                + ("확정 판정이어도 게이트를 넘지 못합니다. " if chosen else NOT_CHOSEN_GATE)
                                + "뜻이 같은 고침(맞춤법, 옮겨 적은 빌드의 게임 수치를 지우고 빌드를 이름으로 가리킴)인지 사용자와 가립니다. 이미 확인했으면 다시 묻지 않습니다. "
                                f"같은 뜻이면 criteria를 고칩니다(지금 지문: {current}). 뜻이 바뀌었으면 지금 기준으로 다시 판정하고 이 판정은 cut으로 둡니다. "
                                "다시 시험하려고 기준을 바꿨으면 묻지 않고, 새 기록을 기다리지 말고 지금 cut으로 둡니다(지우지 않습니다)."})
    return "changed"


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


def _norm_path(raw: str) -> str:
    return posixpath.normpath(raw.strip().replace("\\", "/"))


def _same_path(raw: str, paths) -> bool:
    """raw가 paths 중 하나와 같은 파일을 가리키는가. ./, 역슬래시, 앞뒤 공백은 같은 경로로 본다."""
    return isinstance(paths, list) and _norm_path(raw) in {_norm_path(x) for x in paths if _text(x)}


def _recorded(s: dict) -> tuple:
    """판별 로그가 말하는 (판 수, 사람들): runlog가 묶음마다 쓴 runs와 players의 합. 모든 묶음에 있어야 센다. 없으면 None.
    손으로 쓴 단계 기록(세션의 stage_stats)은 로그가 아니라서 세지 않는다."""
    groups = s.get("groups") or []
    runs = sum(g["runs"] for g in groups) if groups and all("runs" in g for g in groups) else None
    players = {p.strip() for g in groups for p in g["players"]} if groups and all("players" in g for g in groups) else None
    return runs, players


def _check_beyond_records(s: dict, warnings: list) -> None:
    """손으로 쓴 판 수·사람이 판별 로그 묶음보다 많으면 표본이 부풀 수 있다. 판정 표본은 로그를 센다(확인하면 세션 값을 믿는다)."""
    runs, players = _recorded(s)
    parts = []
    if runs is not None and runs < s["runs"]:
        parts.append(f"판 수 {josa(s['runs'], '이가')} 판별 로그 묶음의 {runs}판보다 많습니다")
    extra = sorted({p.strip() for p in s["players"]} - players) if players is not None else []
    if extra:
        parts.append(f"판별 로그 묶음에 없는 사람이 있습니다: {', '.join(extra)}")
    if parts:
        warnings.append({"code": "session_beyond_records", "where": s["id"],
                         "message": "; ".join(parts) + ". 판정 표본은 로그에 남은 판과 사람만 셉니다. 로그에 남기지 못한 판이나 사람이 맞으면 이 세션의 acknowledged에 이유를 적습니다."})


def _counted(s: dict) -> tuple[int, set]:
    """표본에 넣는 (판 수, 사람들). 판별 로그 묶음이 있으면 로그를 넘지 않는다. session_beyond_records를 확인한 세션은 세션 값을 쓴다."""
    names = {p.strip() for p in s["players"]}
    if ack_reason(s, "session_beyond_records"):
        return s["runs"], names
    runs, players = _recorded(s)
    return (s["runs"] if runs is None else min(s["runs"], runs)), (names if players is None else players)


def _check_files(s: dict, root: Path, warnings: list) -> None:
    """세션이 가리키는 기록 파일(logs, source)이 프로젝트에 있는가. 경로처럼 보이는 것만 본다."""
    cited = [(f"logs[{n}]", x) for n, x in enumerate(s.get("logs") or [])]
    cited += [(f"observations[{n}].source", o.get("source")) for n, o in enumerate(s.get("observations") or [])]
    cited += [(f"greybox[{n}].source", g.get("source")) for n, g in enumerate(s.get("greybox") or [])]
    cited += [("stage_stats.source", x.get("source")) for h in _holders(s) for x in h.get("stage_stats") or []]
    seen: set = set()
    for label, raw in cited:
        if not (_text(raw) and PATH_LIKE.search(raw.strip())) or _norm_path(raw) in seen:
            continue
        seen.add(_norm_path(raw))
        path = Path(_norm_path(raw))
        if not (path if path.is_absolute() else root / path).exists():
            warnings.append({"code": "source_missing", "where": s["id"],
                             "message": f"{label}의 기록 파일이 없습니다: {raw}. 경로는 프로젝트 폴더 기준입니다. 옮겼으면 경로를 고칩니다."})


def _check_name_variants(sessions: dict, warnings: list) -> None:
    """대소문자·공백만 다른 이름(self와 Self )은 사람 수를 따로 센다. 날짜순으로 처음 쓴 이름과 다르게 쓴 세션을 알린다."""
    first: dict = {}
    for s in sorted(sessions.values(), key=lambda x: (x["date"], x["id"])):
        for name in s["players"]:
            key = " ".join(name.split()).casefold()
            seen = first.setdefault(key, (name, s["id"]))
            if seen[0] != name:
                other = "같은 세션의" if seen[1] == s["id"] else f"앞 세션 {seen[1]}의"
                warnings.append({"code": "player_name_variants", "where": s["id"],
                                 "message": f"players의 이름이 {other} 이름과 대소문자·공백만 다릅니다: {name!r}, {seen[0]!r}. 표본은 두 사람으로 셉니다. "
                                            "같은 사람이면 같은 이름으로 씁니다. 다른 사람이 맞으면 이 세션의 acknowledged에 이유를 적습니다."})


def _check_event_names(s: dict, info: dict, warnings: list) -> None:
    """세션 events의 사건 이름이 그 컨셉의 어느 가설 sample.events에도 없으면 그 건수는 어떤 판정에도 세지 않는다(오타)."""
    known = {name for smp in info.get("samples", {}).values() for name in smp.get("events") or {}}
    for name in s.get("events") or {}:
        if name not in known:
            hint = did_you_mean(name, known) if known else f" {s['concept']}의 가설에 sample.events가 없습니다."
            warnings.append({"code": "unknown_event", "where": s["id"],
                             "message": f"events의 사건 {josa(name, '이가')} 가설 sample.events에 없습니다.{hint} 이 건수는 어느 판정에도 세지 않습니다. 이름을 sample.events와 맞춥니다."})


def _result_numbers(path: Path, cache: dict):
    """결과 파일의 수(값) 집합. 파일마다 한 번만 읽는다. 읽지 못하거나 너무 크면 None."""
    if path not in cache:
        try:
            ok = path.is_file() and path.stat().st_size <= SOURCE_READ_LIMIT
            cache[path] = {float(x) for x in NUMBER.findall(path.read_text(encoding="utf-8", errors="replace"))} if ok else None
        except OSError:
            cache[path] = None
    return cache[path]


def _check_values(s: dict, root: Path, warnings: list, cache: dict) -> None:
    """계산한 관찰값의 수가 결과 파일(source)에 글자 그대로 있는가. 결과 파일을 열지 않고 옮겨 적으면 틀린 수가 들어간다.
    수는 값으로 맞춘다(1과 1.0은 같다). 원본 기록을 가리키면 computed_without_output이, 없는 파일이면 source_missing이 말한다."""
    for n, o in enumerate(s.get("observations") or []):
        src = o.get("source")
        if COMPUTED not in str(o.get("note") or "") or not (_text(src) and PATH_LIKE.search(src.strip())) or _same_path(src, s.get("logs")):
            continue
        path = Path(_norm_path(src))
        have = _result_numbers(path if path.is_absolute() else root / path, cache)
        if have is None:
            continue
        missing = [x for x in dict.fromkeys(NUMBER.findall(DATE_TIME.sub(" ", str(o.get("value"))))) if float(x) not in have]
        if missing:
            warnings.append({"code": "value_not_in_source", "where": s["id"],
                             "message": f"observations[{n}]의 값에 결과 파일 {src}에 없는 수가 있습니다: {', '.join(missing)}. "
                                        "결과 파일의 수를 반올림하거나 고치지 않고 그대로 옮깁니다. 문턱값은 value가 아니라 판정 reason에 씁니다."})


def _events(sessions: list, names) -> dict:
    """사건별 {count: 근거 세션이 센 건수 합, missing: 그 사건을 세지 않은 세션 수}."""
    out = {}
    for name in names:
        counted = [s["events"][name] for s in sessions if name in (s.get("events") or {})]
        out[name] = {"count": sum(counted), "missing": len(sessions) - len(counted), "counted": len(counted)}
    return out


def _events_text(have: dict, need: dict) -> str:
    """세지 않은 세션은 0건으로 센다. 근거 세션이 하나도 세지 않았으면 0건이 아니라 미집계로 쓴다(나중에 sample.events를 더한 경우)."""
    return ", ".join(f"{name} {'미집계' if e['missing'] and not e['counted'] else e['count']}/{need[name]}"
                     + (f"(세지 않은 세션 {e['missing']}개)" if e["missing"] else "") for name, e in have.items())


def _against(have: dict, need: dict | None, key: str, unit: str) -> str:
    return f"{have[key]}/{need[key]}{unit}" if need and key in need else f"{have[key]}{unit}"


def _sample_line(have: dict, need: dict | None, deviations: int, builds: list) -> str:
    """판정의 표본 글: 근거 세션 수, 판·사람(최소 표본과 나란히), 사건 수, 절차 이탈, 섞인 빌드. check 출력과 뷰어가 같은 글을 쓴다."""
    parts = [f"세션 {have['sessions']}", _against(have, need, "runs", "판"), _against(have, need, "players", "명")]
    reduced = (need or {}).get("reduced_from")
    if reduced:   # 줄인 표본이면 줄이기 전 값과 때를 함께 보인다
        before = ", ".join(f"{reduced[k]}{u}" for k, u in (("runs", "판"), ("players", "명")) if k in reduced)
        parts[1] += f" ({before}에서 줄임, {reduced['after_run']}판째 뒤" + ("" if reduced["before_results"] else ", 결과를 본 뒤") + ")"
    if len(builds) > 1:
        parts.append(f"빌드 {len(builds)}개({', '.join(builds)})")
    if have.get("events"):
        parts.append("사건 " + _events_text(have["events"], need["events"]))
    if deviations:
        parts.append(f"절차 이탈 {deviations}건")
    return " · ".join(parts)


def _sample(sessions: list) -> dict:
    """세션들을 합친 표본: 세션 수, 판 수, 사람 수(같은 이름은 한 사람). 판별 로그 묶음이 있으면 로그를 넘지 않는다."""
    counted = [_counted(s) for s in sessions]
    return {"sessions": len(sessions), "runs": sum(r for r, _ in counted), "players": len(set().union(*(p for _, p in counted)))}


def _sample_text(sample: dict) -> str:
    return " · ".join(f"{sample[k]}{unit}" for k, unit in (("players", "명"), ("runs", "판")) if k in sample)


def validate(data: dict, concepts: dict | None = None, concepts_unreadable: bool = False, refs: dict | None = None, root: Path | None = None) -> dict:
    """concepts: concepts.hypothesis_index()의 결과. None이면 컨셉·가설 참조를 확인하지 못한 것으로 센다.
    refs: 단계 기록이 가리키는 id {stages, upgrades, enemies, builds, currencies}. 값이 None인 종류는 쓰면 미확인이다."""
    errors: list = []
    warnings: list = []
    top = unknown_keys_text(data, TOP_FIELDS)
    if top:
        _err(errors, "schema", "playtests", top)
    raw = data.get("playtests")
    if not isinstance(raw, list):
        _err(errors, "schema", "playtests", "playtests 배열이 필요합니다.")
        raw = []
    raw_verdicts = data.get("verdicts", [])
    if not isinstance(raw_verdicts, list):
        _err(errors, "schema", "verdicts", "verdicts는 배열이어야 합니다.")
        raw_verdicts = []
    sessions = {s["id"]: s for _, s in check_identity(raw, "playtests", errors) if check_session(s, errors, warnings)}
    numbers: dict = {}   # 결과 파일마다 한 번 읽은 수
    _check_name_variants(sessions, warnings)
    unchecked = 0
    missing_refs: set = set()
    for s in sessions.values():
        check_refs(s, refs, errors, warnings, missing_refs)
        if root is not None:
            _check_files(s, root, warnings)
            _check_values(s, root, warnings, numbers)
        observed = [o["hypothesis"] for o in s.get("observations", [])] + [h for x in s.get("notes") or [] for h in x.get("hypotheses") or []]
        if concepts is None:
            unchecked += 1
        elif s["concept"] not in concepts:
            _err(errors, "unknown_concept", s["id"], f"컨셉 데이터에 없는 컨셉입니다: {s['concept']}")
        else:
            for h in dict.fromkeys(observed):
                _hypothesis_ref(s["concept"], h, s["id"], concepts, errors)
            _check_event_names(s, concepts[s["concept"]], warnings)

    verdicts: dict = {}
    left: dict = {}   # 지난 판정이 남긴 '다음 시험 전에 풀 것' {가설: 글}. 새 판정이 나오기 전까지 보인다
    restamp: dict = {}   # 예전 꼴 지문으로 기록한 판정 {판정: {from, to}}
    status_counts = {st: 0 for st in STATUSES + ("unspecified",)}
    for n, v in enumerate(raw_verdicts):
        where = check_verdict(v, n, errors)
        if where is None:
            continue
        status = v.get("status") or "unspecified"
        status_counts[status] += 1
        if status == "cut":
            if _text(v.get("next_needs")):
                left[where] = v["next_needs"]
            continue  # 지난 판정은 기록으로만 남긴다
        if where in verdicts:
            _err(errors, "duplicate_verdict", where, "삭제(cut)되지 않은 판정이 둘 이상입니다. 지난 판정은 status를 cut으로 두고 남깁니다.")
            continue
        if concepts is None:
            unchecked += 1
        elif not _hypothesis_ref(v["concept"], v["hypothesis"], where, concepts, errors):
            continue
        criteria = _check_criteria(v, where, concepts, warnings, restamp)
        _check_override(v, where, errors)
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
        seen = [s for s in found if any(o["hypothesis"] == v["hypothesis"] for o in s.get("observations", []))]
        have = _sample(seen)   # 그 가설을 관찰한 근거 세션만 센다. 출력과 게이트가 같은 값을 쓴다
        need = concepts[v["concept"]].get("samples", {}).get(v["hypothesis"]) if concepts is not None else None
        if need and "events" in need:
            have["events"] = _events(seen, need["events"])
        if v["result"] in DECIDED and seen and need and any(have[k] < need[k] for k in ("players", "runs") if k in need):   # 관찰값이 없으면 observation_missing이 말한다
            _err(errors, "verdict_sample_short", where,
                 f"{RESULT_LABEL[v['result']]} 판정의 근거 표본({_sample_text(have)})이 가설의 최소 표본({_sample_text(need)})보다 적습니다. "
                 "세션을 더 하거나 unknown(모름)으로 둡니다. 표본을 바꾸려면 브리프의 sample을 사용자와 고칩니다.")
        short = {k: e for k, e in have.get("events", {}).items() if e["count"] < need["events"][k]}
        if v["result"] == "holds" and seen and short:   # 틀림은 사건에 기대지 않는 다른 쪽 신호로 낼 수 있어 막지 않는다
            _err(errors, "verdict_events_short", where,
                 f"버팀 판정의 근거 사건 수({_events_text(short, need['events'])})가 가설의 최소 사건 수보다 적습니다. "
                 "사건에 기대는 쪽 신호를 가리지 못했으면 버팀이 아니라 unknown(모름)입니다. 세션마다 그 세션에서 센 건수를 events에 적습니다(세지 않은 세션은 0으로 셉니다).")
        allowed = concepts[v["concept"]].get("builds", {}).get(v["hypothesis"]) if concepts is not None else None
        wrong = [s["id"] for s in seen if allowed and s["build"] not in allowed and s.get("game_build") not in allowed]
        if v["result"] in DECIDED and wrong:
            _err(errors, "verdict_session_wrong_build", where,
                 f"{RESULT_LABEL[v['result']]} 판정의 근거 세션 {', '.join(wrong)}의 빌드가 가설이 세는 빌드({', '.join(allowed)})가 아닙니다. "
                 "세션의 build(커밋)나 game_build(판 로그의 빌드 지문)를 확인합니다. 다른 빌드의 기록이면 근거에서 뺍니다.")
        reduced = (need or {}).get("reduced_from")
        if v["result"] in DECIDED and reduced and not reduced["before_results"]:
            _err(errors, "verdict_sample_reduced_after_results", where,
                 f"{RESULT_LABEL[v['result']]} 판정의 가설은 결과 파일을 연 뒤에 표본을 줄였습니다(sample.reduced_from). "
                 "결과를 보고 기준을 바꾼 것과 구별되지 않으므로 버팀·틀림이 아니라 unknown(모름)으로 둡니다. 원래 표본을 채우면 다시 판정할 수 있습니다.")
        deviations = sum(1 for s in found for x in s.get("notes") or []   # 가설을 적은 절차 이탈은 그 가설에만 센다
                         if x.get("kind") == "deviation" and v["hypothesis"] in (x.get("hypotheses") or [v["hypothesis"]]))
        verdicts[where] = {"result": v["result"], "status": status, "reason": v["reason"], "sample": have, "need": need,
                           "deviations": deviations, "criteria": criteria, "proposed_result": v.get("proposed_result"), "next_needs": v.get("next_needs"),
                           "sample_text": _sample_line(have, need, deviations, list(dict.fromkeys(s.get("game_build") or s["build"] for s in seen)))}

    unverified: list = []
    unverified_reasons: dict = {}   # 확정 판정인데 게이트에 걸린 까닭. 데이터는 키 그대로 두고 화면(check 게이트 줄, 뷰어)이 붙인다
    refuted: list = []
    if concepts is not None:
        for cid, info in sorted(concepts.items()):
            if not info["approved"]:
                continue
            for i, h in enumerate(info["hypotheses"]):
                key = f"{cid}.{h}" if h else f"{cid}.brief.hypotheses[{i}]"
                got = verdicts.get(key)
                decided = bool(got) and got["result"] in DECIDED and got["status"] == "approved"
                if not decided or got["criteria"] != "ok":   # 지문이 없거나 기준이 바뀐 확정 판정은 지금 기준의 판정인지 모른다
                    unverified.append(key)
                    if decided and got["criteria"] in CRITERIA_GATE_REASON:   # 판정 줄은 '확정'인데 게이트에 걸린 까닭
                        unverified_reasons[key] = CRITERIA_GATE_REASON[got["criteria"]]
                if decided and got["result"] == "refuted" and got["criteria"] != "changed":   # 기준을 고쳤으면 다시 시험하는 중이다
                    refuted.append(key)
                    warnings.append({"code": "approved_concept_refuted", "where": key,
                                     "message": "선택(approved)한 컨셉의 가설이 틀림으로 확정됐습니다. 이 가설에 기대는 다음 단계로 가지 않습니다. "
                                                "규칙 하나를 바꿔 다시 시험할지 컨셉을 되돌릴지 사용자와 정합니다(playtest-verdict 6단계의 '다시 시험할 때', "
                                                "'컨셉을 되돌릴 때'. 승인을 내리는 편집은 범위 훅이 사용자에게 묻습니다)."})
    # 선택한 컨셉이 없고 판정까지 한 컨셉이 있으면 되돌린 것이다. 판정이 없는 컨셉(승인 전에 설계하는 중)은 되돌린 것이 아니다
    reverted = sorted({w.split(".")[0] for w in verdicts if w.split(".")[0] in concepts}) \
        if concepts and not any(info["approved"] for info in concepts.values()) else []
    next_needs = {w: {"text": x["next_needs"], "cut": False} for w, x in verdicts.items() if x["next_needs"] and x["result"] == "unknown"}
    next_needs.update({w: {"text": text, "cut": True} for w, text in left.items()
                       if w not in next_needs and not (w in verdicts and verdicts[w]["result"] in DECIDED)})
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
        "unverified_reasons": unverified_reasons,
        "refuted": refuted,
        "reverted": reverted,
        "next_needs": next_needs,
        "restamp": restamp,
        "unchecked": unchecked + len(missing_refs),
        "unchecked_reason": reason,
        "unchecked_refs": sorted(missing_refs),
        "errors": errors,
        "warnings": warnings,
    }


def print_extra(result: dict) -> None:
    if result.get("reverted"):
        print(f"참고: 선택(approved)한 컨셉이 없습니다. 판정까지 한 컨셉(되돌린 컨셉): {', '.join(result['reverted'])}. "
              "다음 컨셉을 고르기 전까지 다른 데이터의 게이트 항목(가정 수치)은 지난 시험의 기록이고 할 일이 아닙니다. 다음 컨셉의 시스템 설계에서 다시 봅니다.")
    for where, v in result["verdicts"].items():
        state = "확정" if v["status"] == "approved" else "제안"
        if v.get("proposed_result") not in (None, v["result"]):
            state += f", 판정 에이전트는 {RESULT_LABEL[v['proposed_result']]}"   # 사용자가 제안을 모름으로 낮춰 확정했다
        print(f"{where}: {RESULT_LABEL[v['result']]} ({state}) · 관찰한 근거 {v['sample_text']}")
    for where, x in result.get("next_needs", {}).items():   # 옮겨 적은 잣대 태그는 브리프와 어긋날 수 있어 빼고 보인다
        print(f"다음 시험 전에 풀 것({where}): {YARDSTICK_TAG.sub('', x['text'])}" + (" (지난 판정)" if x["cut"] else ""))
    for where, x in result.get("restamp", {}).items():
        print(f"참고: 판정 {where}의 기준 지문이 예전 꼴입니다(criteria {x['from']}, 태그까지 넣어 계산함). 기준은 그대로이니 criteria를 바꿔 둡니다(새 지문: {x['to']}). "
              "그러면 태그 없던 수치에 태그를 달거나 태그를 바꿔도 지문이 그대로입니다.")
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
