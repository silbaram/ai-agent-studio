"""컨셉 기록(design/concepts.json)을 결정적으로 검사한다.

재미를 점수로 매기지 않는다. 기록이 빠짐없는지, 구조가 사실상 같은 컨셉이 있는지,
후보들이 한 구조에 몰려 있지 않은지, 선택한 컨셉의 브리프가 반증 가능한 형태인지 본다.
형식: concept-exploration/references/concept-record.md
"""
from __future__ import annotations

import hashlib
import json
import posixpath
import re
import unicodedata
from pathlib import Path

from . import provenance
from .common import DATASET_KINDS, ID_PATTERN, STATUSES, check_identity, is_active, is_int, josa, load_dataset, valid_date
from .common import did_you_mean as _did_you_mean
from .common import table_cell as _cell

STATUS_LABEL = {"proposed": "후보", "approved": "선택", "cut": "제외", "unspecified": "미지정"}
REQUIRED_TEXT = ("name", "pitch", "core_verb", "decision", "state_read", "skill_expression", "risk")
POLICY_RESULTS = ("dominates", "competitive", "loses", "unknown")
RESULT_LABEL = {"dominates": "지배", "competitive": "대등", "loses": "짐", "unknown": "미확인"}
REJECT_TYPES = ("unreachable_goal", "forced_failure", "dominant_simple_policy",
                "no_recurring_decision", "contradiction", "constraint_violation")
COST_LEVELS = ("small", "medium", "large")
COST_LABEL = {"small": "작음", "medium": "중간", "large": "큼"}
MIN_SIGNATURE_AXES = 4
# 구조 축과 단순 전략 이름. concept-exploration/references/search-axes.md, stress-policies.md와 맞춘다.
REQUIRED_AXES = ("decision", "information", "commitment", "risk_reward")
KNOWN_AXES = REQUIRED_AXES + ("space", "pressure", "progression")
KNOWN_POLICIES = ("idle", "spam", "kite", "rush", "corner", "safe_only", "greedy", "one_build", "random")
DUPLICATE_THRESHOLD = 0.8
MVP_LIMIT = 7
EXISTING_HINT = (" 이미 만들고 있는 게임의 컨셉이면 existing_game: true를 적고 브리프만 채웁니다"
                 "(concept-exploration references/existing-game.md의 '순서').")


def _text(v) -> bool:
    return isinstance(v, str) and v.strip() != ""


def _status(c: dict) -> str:
    return c.get("status") or "unspecified"


def read_constraints(data: dict, errors: list) -> dict:
    """constraints.fixed_axes({축: 값})와 constraints.extra_axes([축])를 읽는다. 나머지 제약은 자유 형식이다."""
    ctx = {"fixed": {}, "extra": set()}
    cons = data.get("constraints")
    if cons is None:
        return ctx
    if not isinstance(cons, dict):
        errors.append({"code": "schema", "where": "constraints", "message": "constraints는 객체여야 합니다."})
        return ctx
    fixed = cons.get("fixed_axes")
    if fixed is not None:
        if isinstance(fixed, dict) and all(isinstance(k, str) and _text(v) for k, v in fixed.items()):
            ctx["fixed"] = {k: v.strip().lower() for k, v in fixed.items()}
        else:
            errors.append({"code": "schema", "where": "constraints", "message": "fixed_axes는 {축: 값(문자열)} 객체여야 합니다."})
    extra = cons.get("extra_axes")
    if extra is not None:
        if isinstance(extra, list) and all(_text(x) for x in extra):
            ctx["extra"] = {x.strip() for x in extra}
        else:
            errors.append({"code": "schema", "where": "constraints", "message": "extra_axes는 축 이름(문자열) 배열이어야 합니다."})
    return ctx


def check_concept(c: dict, where: str, errors: list, warnings: list, ctx: dict | None = None) -> bool:
    ctx = ctx or {"fixed": {}, "extra": set()}
    fixed = ctx["fixed"]
    known = set(KNOWN_AXES) | ctx["extra"] | set(fixed)
    ok = True
    existing = c.get("existing_game", False)
    if not isinstance(existing, bool):   # 적으려던 것은 기존 게임이다. 후보 칸 오류를 줄줄이 내지 않는다
        errors.append({"code": "schema", "where": where, "message": f"existing_game은 true나 false입니다: {existing!r}"})
        existing, ok = True, False
    hint = "brief" in c   # 브리프만 적은 컨셉은 이미 만들고 있는 게임일 수 있다
    for f in ("name",) if existing else REQUIRED_TEXT:
        if not _text(c.get(f)):
            errors.append({"code": "missing_field", "where": where, "message": f"{josa(f, '이가')} 비어 있습니다."
                           + (EXISTING_HINT if hint and f != "name" else "")})
            hint = hint and f == "name"
            ok = False
    status = c.get("status")
    if status is not None and status not in STATUSES:
        errors.append({"code": "schema", "where": where, "message": f"status는 {', '.join(STATUSES)} 중 하나입니다: {status!r}"})
        ok = False
    sig = c.get("signature")
    if existing and sig is None:   # 견줄 후보가 없어 구조 축을 적지 않아도 된다
        pass
    elif not isinstance(sig, dict) or not all(isinstance(k, str) and _text(v) for k, v in sig.items()):
        errors.append({"code": "schema", "where": where, "message": "signature는 {축: 값(문자열)} 객체여야 합니다."})
        ok = False
    else:
        missing = [a for a in REQUIRED_AXES if a not in sig and a not in fixed]
        if missing:
            errors.append({"code": "signature_missing_axis", "where": where,
                           "message": f"signature에 필수 축 {josa(', '.join(missing), '이가')} 없습니다. 축 이름의 오타인지 확인하세요."})
            ok = False
        for k in sig:
            if k not in known:
                warnings.append({"code": "unknown_axis", "where": where,
                                 "message": f"알 수 없는 축 이름 '{k}'.{_did_you_mean(k, KNOWN_AXES)} "
                                            "이름이 다르면 다른 후보와 비교되지 않습니다. 새 축이면 constraints.extra_axes에 적으세요."})
            elif k in fixed and sig[k].strip().lower() != fixed[k]:
                warnings.append({"code": "fixed_axis_mismatch", "where": where,
                                 "message": f"'{k}' 축은 제약으로 '{fixed[k]}'에 고정되어 있는데 '{sig[k]}'입니다. 제약을 어기는지 확인하세요."})
        comparable = [k for k in sig if k not in fixed]
        if len(comparable) < MIN_SIGNATURE_AXES:
            errors.append({"code": "signature_too_small", "where": where,
                           "message": f"비교할 수 있는 signature 축이 {len(comparable)}개입니다(고정 축 제외). "
                                      f"구조 비교를 위해 {MIN_SIGNATURE_AXES}개 이상 적으세요."})
            ok = False
    stress = c.get("stress", [])
    if not isinstance(stress, list):
        errors.append({"code": "schema", "where": where, "message": "stress는 배열이어야 합니다."})
        ok = False
        stress = []
    for n, s in enumerate(stress):
        if not isinstance(s, dict) or not _text(s.get("policy")) or s.get("result") not in POLICY_RESULTS:
            errors.append({"code": "schema", "where": where,
                           "message": f"stress[{n}]: policy(문자열)와 result({', '.join(POLICY_RESULTS)})가 필요합니다."})
            ok = False
            continue
        if s["result"] != "unknown" and not _text(s.get("evidence")):
            errors.append({"code": "evidence_missing", "where": where,
                           "message": f"'{s['policy']}' 결과가 {s['result']}인데 근거(evidence)가 없습니다. 근거가 없으면 unknown으로 둡니다."})
            ok = False
        if s["policy"] not in KNOWN_POLICIES and not _text(s.get("definition")):
            warnings.append({"code": "unknown_policy", "where": where,
                             "message": f"목록에 없는 단순 전략 '{s['policy']}'.{_did_you_mean(s['policy'], KNOWN_POLICIES)} "
                                        "새 전략이면 그 stress 항목에 definition(어떻게 행동하는지)을 적으세요."})
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


SAMPLE_KEYS = ("players", "runs", "events", "reduced_from")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
REDUCED_KEYS = ("players", "runs", "after_run", "before_results", "date")
CRITERIA_KEYS = ("claim", "failure_signal", "test", "sample")  # 판정 기준. 이 칸이 바뀌면 지난 판정은 지금 기준의 판정이 아니다


def sample_problem(v) -> str | None:
    """가설 최소 표본의 형식 문제. 맞으면 None."""
    if not (isinstance(v, dict) and v):
        return "sample은 {players: 사람 수, runs: 판 수, events: {사건 이름: 건수}} 중 하나 이상을 적은 객체입니다"
    bad = sorted(str(k) for k in v if k not in SAMPLE_KEYS)
    if bad:
        return f"sample에 알 수 없는 키 {', '.join(bad)}.{''.join(_did_you_mean(k, SAMPLE_KEYS) for k in bad)} 쓸 수 있는 키는 {', '.join(SAMPLE_KEYS)}입니다"
    if any(not is_int(v[k], 1) for k in ("players", "runs") if k in v):
        return "sample의 players와 runs는 1 이상의 정수입니다"
    ev = v.get("events")
    if "events" in v and not (isinstance(ev, dict) and ev and all(isinstance(k, str) and ID_PATTERN.match(k) and is_int(x, 1) for k, x in ev.items())):
        return "sample.events는 {사건 이름(소문자·숫자·밑줄): 1 이상의 정수} 객체입니다"
    if "reduced_from" in v:
        return _reduced_problem(v)
    return None


def _reduced_problem(v: dict) -> str | None:
    """표본을 줄인 기록 {players·runs: 줄이기 전 값, after_run: 진행 중이던 세션에서 몇 판째 뒤에 줄였나, before_results: 결과 파일을 열기 전인가, date}."""
    r = v["reduced_from"]
    bad = sorted(str(k) for k in r if k not in REDUCED_KEYS) if isinstance(r, dict) else []
    if bad:
        return (f"sample.reduced_from에 알 수 없는 키 {', '.join(bad)}.{''.join(_did_you_mean(k, REDUCED_KEYS) for k in bad)} "
                f"쓸 수 있는 키는 {', '.join(REDUCED_KEYS)}입니다")
    if not (isinstance(r, dict) and isinstance(r.get("before_results"), bool)
            and is_int(r.get("after_run"), 0) and isinstance(r.get("date"), str) and DATE.match(r["date"])
            and any(k in r for k in ("players", "runs")) and all(is_int(r[k], 1) for k in ("players", "runs") if k in r)):
        return ("sample.reduced_from은 {runs 또는 players: 줄이기 전 값, after_run: 진행 중이던 세션에서 몇 판째 뒤에 줄였나(0 이상), "
                "before_results: 결과 파일을 열기 전에 줄였나(true/false), date: YYYY-MM-DD}입니다")
    if not any(k in v and r[k] > v[k] for k in ("players", "runs") if k in r):
        return "sample.reduced_from의 값이 지금 표본보다 커야 합니다(줄이기 전 값을 적습니다)"
    return None


def read_sample(v) -> dict | None:
    """가설의 최소 표본 {players, runs, events}: 확정 판정에 필요한 사람 수, 판 수, 사건 수(세션을 합친 값). 형식이 틀리면 None."""
    if sample_problem(v) is not None:
        return None
    return {k: (dict(v[k]) if k in ("events", "reduced_from") else v[k]) for k in SAMPLE_KEYS if k in v}


SPACES = re.compile(r"\s+")   # 지금 지문은 출처 태그와 띄어쓰기를 지운 문장으로 계산한다(태그를 달며 띄어 써도 기준은 그대로다)
KIND_TAG = re.compile(r"\[(?:가정|assumed|결정|decided)(?:\s*[:：][^\]]*)?\]")   # 2026-11-09(이슈 306)의 지문은 가정·결정 태그를 [가정]으로 맞췄다
STAMP_FORMS = ("tagless", "tag_kind", "nfc")   # 지금 꼴, 그리고 예전에 기록한 판정의 지문 꼴(새것부터)


def _norm(v, form: str = "tagless"):
    if isinstance(v, str):
        v = unicodedata.normalize("NFC", v)
        return SPACES.sub("", provenance.STRICT_TAG.sub("", v)) if form == "tagless" else KIND_TAG.sub("[가정]", v) if form == "tag_kind" else v
    if isinstance(v, dict):
        return {k: _norm(x, form) for k, x in v.items()}
    if isinstance(v, list):
        return [_norm(x, form) for x in v]
    return v


def criteria_stamp(h: dict, form: str = "tagless") -> str:
    """판정 기준의 지문(주장, 틀렸다는 신호, 확인 방법, 최소 표본, 적었으면 세는 빌드). 판정의 criteria에 남기면 판정 뒤에 기준이 바뀐 것을 안다.
    키 순서, 유니코드 정규화(NFC), 띄어쓰기, 출처 태그(있고 없음, 종류, 메모, 출처)가 다른 것은 바뀐 것으로 보지 않는다.
    태그를 지워도 지문은 그대로라서, 판정 기준 문장의 태그 없는 수치는 게이트가 막는다(check_brief_numbers).
    form: STAMP_FORMS의 예전 꼴은 그 전에 기록한 판정의 criteria와 견줄 때만 쓴다."""
    fields = {k: _norm(h.get(k), form) for k in CRITERIA_KEYS}
    if "builds" in h:   # 세는 빌드도 기준이다. 결과를 본 뒤 좁히면 지난 판정이 지금 기준의 판정이 아니다(없는 가설의 지문은 그대로 둔다)
        fields["builds"] = _norm(h["builds"], form)
    body = json.dumps(fields, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:8]


HISTORY_KEYS = CRITERIA_KEYS + ("builds",)   # 이력에 고치기 전 값을 남길 수 있는 칸(지문에 드는 칸)
HISTORY_STAMP = re.compile(r"^[0-9a-f]{8}$")
HISTORY_PATH = re.compile(r"\.criteria_history(?:\[|$)")   # 브리프 문장 중 이력의 예전 문장
HISTORY_SHAPE = '{"date": "2026-11-09", "stamp": "고치기 전 지문", "before": {"test": "고치기 전 문장"}, "why": "까닭과 확인한 사람"}'


def _history_problem(e) -> str | None:
    if not isinstance(e, dict):
        return f"항목은 {HISTORY_SHAPE} 꼴입니다"
    if not valid_date(e.get("date")):
        return "date는 고친 날짜(YYYY-MM-DD, 달력에 있는 날)입니다"
    if not (isinstance(e.get("stamp"), str) and HISTORY_STAMP.match(e["stamp"])):
        return "stamp는 고치기 전 기준의 지문(소문자 16진수 8자, 그때 판정의 criteria)입니다"
    before = e.get("before")
    if not (isinstance(before, dict) and before and set(before) <= set(HISTORY_KEYS)):
        return f"before는 고친 칸({', '.join(HISTORY_KEYS)})의 고치기 전 값입니다. 없던 칸은 null로 적습니다"
    if not _text(e.get("why")):
        return "why에 고친 까닭과 누가 확인했는지 적습니다"
    if "after_results" in e and not isinstance(e["after_results"], bool):
        return "after_results는 결과(요약 값, 판정 제안)를 본 뒤에 고쳤는지(true/false)입니다"
    return None


def check_criteria_history(h: dict, n: int, where: str, errors: list) -> None:
    """가설의 criteria_history(오래된 것부터): 기준을 고칠 때 고친 칸의 고치기 전 값과 그때 지문을 남긴다.
    판정 에이전트는 git을 볼 수 없어 '고치기 전이었다면'을 이 기록으로 읽는다(297번). 지문에는 들지 않는다.
    지금 가설에 뒤의 이력부터 고치기 전 값을 덮어 그때 기준을 만들고, 그 지문이 적힌 지문과 같은지 본다. 틀린 이력은 판정을 속이므로 오류다."""
    if "criteria_history" not in h:
        return
    hist, path = h["criteria_history"], f"brief.hypotheses[{n}].criteria_history"
    if not isinstance(hist, list):
        errors.append({"code": "criteria_history_invalid", "where": where, "message": f"{path}: 고친 순서(오래된 것부터)의 배열이어야 합니다. 항목: {HISTORY_SHAPE}"})
        return
    problems = [(i, _history_problem(e)) for i, e in enumerate(hist)]
    for i, problem in problems:
        if problem:
            errors.append({"code": "criteria_history_invalid", "where": where, "message": f"{path}[{i}]: {problem}."})
    if any(problem for _, problem in problems):
        return
    cur = dict(h)
    for i in range(len(hist) - 1, -1, -1):
        e, prev = hist[i], dict(cur)
        for k, v in e["before"].items():
            if v is None:
                prev.pop(k, None)
            else:
                prev[k] = v
        if criteria_stamp(prev) == criteria_stamp(cur):
            errors.append({"code": "criteria_history_mismatch", "where": where,
                           "message": f"{path}[{i}]({e['date']}): 고치기 전 값으로 계산한 기준이 그 뒤의 기준과 같습니다. "
                                      "출처 태그나 띄어쓰기만 바꾼 것은 기준이 바뀐 것이 아니라 이력에 적지 않습니다."})
        elif e["stamp"] not in {criteria_stamp(prev, f) for f in STAMP_FORMS}:
            errors.append({"code": "criteria_history_mismatch", "where": where,
                           "message": f"{path}[{i}]({e['date']}): 고치기 전 값으로 계산한 지문이 적힌 지문과 다릅니다(계산: {criteria_stamp(prev)}, 적힘: {e['stamp']}). "
                                      "고친 칸의 고치기 전 문장과 그때 판정의 criteria를 그대로 적습니다. 이력은 오래된 것이 앞입니다."
                                      + (" 이 항목 뒤에 기준을 또 고쳤으면 그 고침도 이력 끝에 더합니다." if i == len(hist) - 1 else "")})
        cur = prev


def _history_ok(h: dict) -> bool:
    """형식과 지문 사슬이 모두 맞는 이력이 있는가. 맞지 않는 이력은 판정 에이전트에게 그때 기준으로 알리지 않는다."""
    problems: list = []
    check_criteria_history(h, 0, "", problems)
    return bool(isinstance(h.get("criteria_history"), list) and h["criteria_history"]) and not problems


def _history_summary(h: dict) -> dict | None:
    if not _history_ok(h):
        return None
    hist = h["criteria_history"]
    return {"count": len(hist), "date": hist[-1]["date"], "fields": list(hist[-1]["before"])}


def check_brief(c: dict, where: str, errors: list, warnings: list | None = None) -> None:
    """선택(approved)한 컨셉은 반증 가능한 브리프를 갖춰야 한다."""
    warnings = [] if warnings is None else warnings
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
    seen_ids: set = set()
    for n, h in enumerate(hyps if isinstance(hyps, list) else []):
        need(isinstance(h, dict) and all(_text(h.get(k)) for k in ("claim", "failure_signal", "test")),
             f"brief.hypotheses[{n}]에 claim, failure_signal(틀렸다는 신호), test가 필요합니다.")
        if not isinstance(h, dict):
            continue
        problem = sample_problem(h["sample"]) if "sample" in h else None
        if problem:
            errors.append({"code": "schema", "where": where, "message": f"brief.hypotheses[{n}]: {problem}: {h['sample']!r}"})
        elif "sample" not in h:
            warnings.append({"code": "hypothesis_sample_missing", "where": where,
                             "message": f"brief.hypotheses[{n}]({h.get('id') or '이름 없음'})에 최소 표본(sample: {{players, runs}})이 없습니다. "
                                        "판정에 필요한 사람 수와 판 수를 플레이 전에 정해 둡니다."})
        if "builds" in h and not (isinstance(h["builds"], list) and h["builds"] and all(_text(x) for x in h["builds"])):
            errors.append({"code": "schema", "where": where,
                           "message": f"brief.hypotheses[{n}].builds는 이 가설이 세는 빌드(세션의 build나 game_build) 문자열 배열입니다: {h['builds']!r}"})
        hid = h.get("id")
        if hid is None:
            warnings.append({"code": "hypothesis_id_missing", "where": where,
                             "message": f"brief.hypotheses[{n}]에 id가 없습니다. 기록과 판정은 가설 id로 가리키므로 플레이 전에 답니다(소문자·숫자·밑줄)."})
            continue
        if not (isinstance(hid, str) and ID_PATTERN.match(hid)) or hid in seen_ids:
            errors.append({"code": "schema", "where": where,
                           "message": f"brief.hypotheses[{n}].id는 소문자·숫자·밑줄로 쓰고 컨셉 안에서 겹치지 않아야 합니다: {hid!r}"})
        seen_ids.add(hid)
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


# 성공 기준이 말하는 가설 수. '한 가설'(어느 한 가설이라도)과 '가설 2'(이름표)는 수로 보지 않는다
_COUNT_WORDS = {"두": 2, "둘": 2, "세": 3, "셋": 3, "네": 4, "넷": 4, "다섯": 5, "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9, "열": 10}
_COUNTER = r"\s*(?:개|가지)"
_BEFORE = "두|세|네|다섯|여섯|일곱|여덟|아홉|열"
_PARTICLE = "을|이|은|의|과|도|만|에|으로|로|이라도|이다|이고|이며|이면"   # '가설 둘' 뒤에 붙는 조사
HYPOTHESIS_COUNT = re.compile(
    rf"(?<![가-힣\w])(?:(?P<w1>{_BEFORE})(?:{_COUNTER})?|(?P<d1>\d+){_COUNTER})\s*(?:의\s*)?가설"     # 두 가설, 2개 가설, 두 개의 가설
    rf"|가설\s*(?:(?P<d2>\d+){_COUNTER}|(?P<w2>{_BEFORE}){_COUNTER}|(?P<w3>둘|셋|넷|다섯|여섯|일곱|여덟|아홉|열)(?=[^가-힣]|$|(?:{_PARTICLE})(?![가-힣])))")   # 가설 2개, 가설 두 개, 가설 둘(가설 열거·셋업·둘째는 수가 아니다)
THRESHOLD = re.compile(r"\s*(?:이상|이하|미만|초과|넘|이라도|라도|만)")   # 수 뒤에 오면 전체 수가 아니라 문턱이다(가설 1개 이상). '중' 앞은 전체 수다
SUCCESS_MISSES_HYPOTHESIS = ("브리프의 가설은 {n}개({ids})입니다. 가설을 더하거나 뺐으면 같은 편집에서 success_criteria와 prototype.scope를 맞춥니다"
                             "(concept-exploration references/brief.md의 '가설 (`hypotheses`, 1개 이상)' 절, '가설을 더하면 같은 편집에서 맞춘다'). 맞게 쓴 문장이면 컨셉의 acknowledged에 까닭을 적습니다.")


def _stated_counts(text: str) -> list[int]:
    out = []
    text = unicodedata.normalize("NFC", text)
    for m in HYPOTHESIS_COUNT.finditer(text):
        if THRESHOLD.match(text, m.end()):
            continue
        word = m.group("w1") or m.group("w2") or m.group("w3")
        out.append(_COUNT_WORDS[word] if word else int(m.group("d1") or m.group("d2")))
    return out


def check_success_covers(c: dict, warnings: list) -> None:
    """승인한 브리프의 성공 기준이 가설 수와 다른 수를 말하거나, 가설 id를 몇 개만 적고 나머지를 빼면 알린다(가설을 더할 때 맞추지 않은 문장)."""
    b = c["brief"]
    hyps = b.get("hypotheses") if isinstance(b.get("hypotheses"), list) else []
    text = (b.get("prototype") or {}).get("success_criteria") if isinstance(b.get("prototype"), dict) else None
    if not hyps or not isinstance(text, str):
        return
    ids = [h["id"] for h in hyps if isinstance(h, dict) and isinstance(h.get("id"), str) and h["id"]]
    problems = []
    counts = _stated_counts(text)
    if counts and max(counts) != len(hyps):
        problems.append(f"가설 {max(counts)}개를 말합니다")
    folded = unicodedata.normalize("NFC", text).casefold()
    named = [i for i in ids if re.search(rf"(?<![a-z0-9_]){re.escape(i.casefold())}(?![a-z0-9_])", folded)]
    left = [i for i in ids if i not in named]
    if len(ids) > 1 and named and left:
        problems.append(f"가설 {josa(', '.join(named), '을를')} 적었는데 {josa(', '.join(left), '이가')} 없습니다")
    if problems:
        warnings.append({"code": "success_criteria_misses_hypothesis", "where": c["id"],
                         "message": f"brief.prototype.success_criteria가 {', '.join(problems)}. "
                                    + SUCCESS_MISSES_HYPOTHESIS.format(n=len(hyps), ids=", ".join(ids) or "id 없음")})


def _strings(obj, path: str):
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _strings(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _strings(v, f"{path}[{i}]")


CRITERIA_TEXT = re.compile(r"^brief\.hypotheses\[(\d+)\]\.(claim|failure_signal|test)$")   # 지문에 드는 가설 문장


SUCCESS_PATH = "brief.prototype.success_criteria"


def _is_criteria_text(path: str) -> bool:
    """판정 기준 문장: 지문에 드는 가설 문장(claim, failure_signal, test)과 성공 기준. 태그 없는 수치를 경고하고 게이트에서 막는다.
    단위 없는 문턱값(상관 -0.2)도 수치로 본다."""
    return bool(CRITERIA_TEXT.match(path)) or path == SUCCESS_PATH


def _legacy_value(value: str) -> str:
    """PR #36까지 태그 값을 읽던 꼴. 가운뎃점 목록은 마지막 수만(0.5·1·2배 → 2배), 부호는 + 와 단위 수치의 - 를 뺐다(+0.3 → 0.3).
    그때 값으로 적은 criteria_tag_mismatch 확인을 이어 쓴다."""
    tail = re.split(r"[·・]", value)[-1]
    return tail[1:] if tail[:1] == "+" or (tail[:1] == "-" and not tail[-1:].isdigit()) else tail


def _mismatch_part(c: dict, value: str, notes: list | None) -> str:
    """확인의 대상 값. 지금 값으로 적은 확인이 없고 예전 꼴 값으로 적은 확인이 있으면 그것을 쓰고 이름을 바꾸라고 알린다."""
    acks = c.get("acknowledged")
    acks = acks.get("criteria_tag_mismatch") if isinstance(acks, dict) else None
    old = _legacy_value(value)
    if not isinstance(acks, dict) or value in acks or old == value or old not in acks:
        return value
    if notes is not None:
        notes.append(f"{c['id']}의 criteria_tag_mismatch 확인 '{old}'는 예전 값 꼴입니다. 지금 경고의 값은 '{value}'라 그 확인을 이어 씁니다. "
                     f"acknowledged의 대상을 '{value}'로 바꿔 둡니다.")
    return old


ASSUMED_CRITERIA_NOTE = ("판정 기준 문장에 [가정] 값이 남아 게이트를 막습니다({where}). 사용자가 정할 잣대(문턱, 표본, 창 길이)면 사용자에게 묻고, "
                         "정했다고 하면 [결정: 사용자 날짜]로 바꿉니다. 빌드의 게임 수치(피해, 발사 속도)를 옮겨 적은 것이면 지우고 빌드 id(builds, game_build)나 "
                         "변경 이름으로 가리킵니다. 판정한 가설이면 고치기 전에 사용자와 확인하고 문장과 판정의 criteria를 한 번에 바꿉니다"
                         "(brief.md '세는 빌드는 이름으로 가리킨다').")   # 자세한 순서의 원본은 playtest-verdict references/changes.md다


GAME_DATA_KINDS = tuple(k for k in DATASET_KINDS if k not in ("concepts", "systems", "playtests"))   # 조정하면 바뀌는 게임 데이터
JSON_PATH = re.compile(r"(?<![A-Za-z0-9_./\\-])(?:[A-Za-z]:)?[/\\]?[A-Za-z0-9_.-]+(?:[/\\][A-Za-z0-9_.-]+)*\.json(?![A-Za-z0-9_])",
                       re.ASCII)   # 뒤에 조사가 붙는다(growth.json의). 절대 경로와 ./도 잡는다
POINTS_TO_DATA = ("게임 데이터 파일을 가리킵니다({file}). 그 파일은 다음 조정에서 바뀌어 문장이 다른 빌드를 가리키게 됩니다. "
                  "변경 이름이나 빌드 id(세션의 build 커밋, 판 로그의 game_build 지문)로 가리킵니다.{judged} "
                  "그대로 두려면 컨셉의 acknowledged에 "
                  '{{"criteria_points_to_data": {{"{file}": 까닭}}}}을 적습니다.')
POINTS_TO_DATA_JUDGED = (" 판정한 가설이면 builds를 새로 더하지 않고 사용자와 확인한 뒤 고칩니다"
                         "(playtest-verdict references/changes.md '판정한 가설의 문장을 고칠 때').")   # 가설 문장만 지문에 든다


_KIND_CACHE: dict = {}   # {(파일, 바뀐 때, 크기): 내용으로 본 종류}. 뷰어처럼 검사를 거듭 돌려도 바뀌지 않은 파일은 다시 읽지 않는다


def _rel_path(raw: str, root: Path | None) -> str:
    """같은 파일은 같은 대상(part)이 되게 적는다: 프로젝트 안의 절대 경로는 상대 경로로, ./와 ..는 접는다."""
    rel = raw.replace("\\", "/")
    if root is not None and Path(rel).is_absolute():
        try:
            rel = Path(rel).resolve().relative_to(root.resolve()).as_posix()
        except (OSError, ValueError):   # 프로젝트 밖의 파일은 적힌 그대로 둔다
            pass
    return rel if Path(rel).is_absolute() else posixpath.normpath(rel)


def _data_kind(rel: str, root: Path | None) -> str | None:
    """문장에 적힌 JSON 경로의 데이터 종류. 프로젝트의 파일을 이 도구의 형식으로 읽을 수 있으면 내용으로 본다.
    파일이 없거나, 깨졌거나, 게임이 자기 형식으로 쓴 파일(종류 키가 없음)이면 파일 이름으로 본다."""
    name = Path(rel).stem.lower()
    if root is None:   # 프로젝트를 모르면 작업 폴더의 엉뚱한 파일을 읽지 않는다
        return name
    f = root / rel
    try:
        st = f.stat()
    except OSError:
        return name
    if not f.is_file():
        return name
    key = (str(f.resolve()), st.st_mtime_ns, st.st_size)
    if key not in _KIND_CACHE:
        try:
            _KIND_CACHE[key] = load_dataset(f)[0]
        except (OSError, ValueError, UnicodeDecodeError):   # 깨진 파일은 그 파일의 검사가 알린다
            _KIND_CACHE[key] = None
    return _KIND_CACHE[key] or name


def _data_pointers(text: str, root: Path | None) -> list[str]:
    """판정 기준 문장이 가리키는 게임 데이터 파일(329). 출처 태그 안의 경로는 출처라 뺀다."""
    found: list[str] = []
    for m in JSON_PATH.finditer(provenance.LOOSE_TAG.sub(" ", text)):
        rel = _rel_path(m.group(0), root)
        if rel not in found and _data_kind(rel, root) in GAME_DATA_KINDS:
            found.append(rel)
    return found


def check_brief_numbers(c: dict, errors: list, warnings: list, root: Path | None = None, notes: list | None = None,
                        ack_notes: list | None = None) -> list[str]:
    """브리프 문장 안의 수치 출처 태그를 md와 같은 규칙으로 검사한다. [가정]이 남은 위치를 남은 값과 함께 돌려준다(--fail-on-assumed용).
    태그 형식 오류는 브리프 어디서든 보고한다. 태그 없는 수치는 판정 기준 문장에서만 경고하고, 거기서는 출처가 비어 있는 값이라 게이트에서도 막는다
    (지문은 태그를 보지 않으므로 태그를 지운 것을 지문으로는 알 수 없다).
    root(게임 프로젝트 폴더)가 있으면 [계산]·[측정]의 경로 출처를 md의 --check-paths처럼 확인한다(파일, 플레이 기록의 세션 id).
    notes에는 판정 기준 문장에 [가정]이 남은 칸을 모아 게이트 아래 참고 줄로 낸다. ack_notes에는 예전 값 꼴로 적은 확인을 알린다."""
    assumed = []
    hyps = c["brief"].get("hypotheses") if isinstance(c["brief"].get("hypotheses"), list) else []
    held = []   # [가정]이 남은 판정 기준 칸
    tagged: dict = {}   # {가설 번호: {수치: {칸: {종류}}}} 같은 값이 칸마다 다른 태그인지 본다
    success: dict = {}  # 성공 기준의 {수치: {종류}}. 가설마다 문턱을 다시 적는 칸이라 가설의 같은 값과 견준다
    for path, text in _strings(c["brief"], "brief"):
        if HISTORY_PATH.search(path):   # 고치기 전 문장은 지난 기록이다. 태그·수치·출처를 다시 재지 않고 게이트에도 넣지 않는다
            continue
        criteria_text = _is_criteria_text(path)
        r = provenance.check_text(text, path, base_dirs=[root] if root else None, check_paths=root is not None, bare_numbers=criteria_text)
        for f in r.findings:
            if f.level == "error":
                errors.append({"code": "provenance", "where": c["id"], "message": f"{path}: {f.message}"})
            elif criteria_text:
                warnings.append({"code": "untagged_number", "where": c["id"], "message": f"{path}: {f.message}", **({"values": f.values} if f.values else {})})
        m = CRITERIA_TEXT.match(path)
        for rel in _data_pointers(text, root) if criteria_text else []:
            hid = hyps[int(m.group(1))].get("id") if m and isinstance(hyps[int(m.group(1))], dict) else None
            warnings.append({"code": "criteria_points_to_data", "where": c["id"], "part": rel,
                             "message": f"{path}{f'({hid})' if hid else ''}: " + POINTS_TO_DATA.format(file=rel, judged=POINTS_TO_DATA_JUDGED if m else "")})
        left = [t.near for t in r.tags if t.kind == "assumed"]
        bare = r.untagged if criteria_text else []
        if left or bare:
            parts = ([f"가정: {provenance.few(left)}"] if left else []) + ([f"태그 없음: {provenance.few(bare)}"] if bare else [])
            assumed.append(f"{c['id']}.{path}({'; '.join(parts)})")
        if left and criteria_text:
            held.append(path.removeprefix("brief."))
        for t in r.tags if m or path == SUCCESS_PATH else []:
            if t.value and m:
                tagged.setdefault(int(m.group(1)), {}).setdefault(t.value, {}).setdefault(m.group(2), set()).add(t.kind)
            elif t.value:
                success.setdefault(t.value, set()).add(t.kind)
    for n, values in sorted(tagged.items()):
        hid = hyps[n].get("id") if isinstance(hyps[n], dict) else None
        for value, fields in values.items():
            if value in success:
                fields = {**fields, "success_criteria": success[value]}
            dec = [f for f, kinds in fields.items() if "decided" in kinds]
            asm = [f for f, kinds in fields.items() if "assumed" in kinds and f not in dec]
            if dec and asm:
                warnings.append({"code": "criteria_tag_mismatch", "where": c["id"], "part": _mismatch_part(c, value, ack_notes),
                                 "message": f"brief.hypotheses[{n}]({hid or '이름 없음'}): 같은 값 {josa(value, '이가')} {', '.join(dec)}에서는 [결정], "
                                            f"{', '.join(asm)}에서는 [가정]입니다. 같은 잣대면 태그를 맞춥니다. "
                                            f"뜻이 다른 값이면 컨셉의 acknowledged에 {{\"criteria_tag_mismatch\": {{\"{value}\": 까닭}}}}을 적습니다."})
    if held and notes is not None:
        notes.append(ASSUMED_CRITERIA_NOTE.format(where=f"{c['id']}: {', '.join(held)}"))
    return assumed


def similarity(a: dict, b: dict) -> tuple[float, int]:
    shared = set(a) & set(b)
    if not shared:
        return 0.0, 0
    same = sum(1 for k in shared if a[k].strip().lower() == b[k].strip().lower())
    return same / len(shared), len(shared)


def check_structure(active: list[dict], warnings: list, fixed: dict | None = None) -> dict:
    """구조 중복과 축 쏠림을 본다. 테마·이름은 보지 않는다. 제약으로 고정된 축(fixed)은 비교하지 않는다."""
    fixed = fixed or {}
    sigs = {c["id"]: {k: v for k, v in c["signature"].items() if k not in fixed} for c in active}
    pairs = []
    for i, a in enumerate(active):
        for b in active[i + 1:]:
            ratio, shared = similarity(sigs[a["id"]], sigs[b["id"]])
            if shared >= MIN_SIGNATURE_AXES and ratio >= DUPLICATE_THRESHOLD:
                pairs.append((a["id"], b["id"], round(ratio, 3)))
                same = round(ratio * shared)
                if b.get("origin") == a["id"] or a.get("origin") == b["id"]:
                    variant, original = (b, a) if b.get("origin") == a["id"] else (a, b)
                    warnings.append({"code": "near_duplicate", "where": variant["id"],
                                     "message": f"'{original['id']}'의 변이이고 구조 축 {shared}개 중 {same}개가 같습니다. "
                                                "변이가 원본을 대체하면 원본을 cut으로 두고 notes에 이유를 적으세요. 둘 다 남기려면 인과 관계를 더 바꾸세요."})
                else:
                    warnings.append({"code": "near_duplicate", "where": b["id"],
                                     "message": f"'{a['id']}'와 구조 축 {shared}개 중 {same}개가 같습니다. 테마만 다른 변형일 수 있습니다. 대표 하나만 남기거나 인과 관계를 바꾸세요."})
    coverage: dict = {}
    for c in active:
        for k, v in sigs[c["id"]].items():
            coverage.setdefault(k, set()).add(v.strip().lower())
    if len(active) >= 3:
        for k, vals in sorted(coverage.items()):
            holders = [c for c in active if k in sigs[c["id"]]]
            if len(holders) >= 3 and len(vals) == 1:
                warnings.append({"code": "axis_collapse", "where": k,
                                 "message": f"후보 {len(holders)}개가 '{k}' 축에서 모두 '{next(iter(vals))}'입니다. 이 축은 탐색되지 않았습니다."})
    return {"duplicates": pairs, "axis_coverage": {k: sorted(v) for k, v in sorted(coverage.items())},
            "fixed_axes": dict(sorted(fixed.items()))}


def _approved_criteria(valid: list) -> dict:
    """선택한 컨셉의 가설별 기준 지문 {컨셉.가설: 지문}. 판정 에이전트가 판정할 때 읽은 기준을 판정에 남기려고 쓴다."""
    out = {}
    for c in valid:
        hyps = (c.get("brief") or {}).get("hypotheses") if c.get("status") == "approved" and isinstance(c.get("brief"), dict) else None
        for h in hyps if isinstance(hyps, list) else []:
            if isinstance(h, dict) and isinstance(h.get("id"), str):
                out[f"{c['id']}.{h['id']}"] = criteria_stamp(h)
    return out


def print_extra(report: dict) -> None:
    if report.get("criteria"):
        print("판정 기준 지문: " + " · ".join(f"{k} {v}" for k, v in report["criteria"].items()))
    if report.get("criteria_history"):   # 판정 에이전트가 고치기 전 기준을 찾을 곳
        print("기준 이력: " + " · ".join(f"{k} {x['count']}번({'마지막 ' if x['count'] > 1 else ''}{x['date']} {', '.join(x['fields'])})"
                                       for k, x in report["criteria_history"].items()))


def validate(data: dict, root: Path | None = None) -> dict:
    """root: 데이터 파일의 게임 프로젝트 폴더. 있으면 브리프의 [계산]·[측정] 경로 출처를 확인한다."""
    errors: list = []
    warnings: list = []
    raw = data.get("concepts")
    if not isinstance(raw, list):
        errors.append({"code": "schema", "where": "concepts", "message": "concepts 배열이 필요합니다."})
        raw = []
    ctx = read_constraints(data, errors)
    valid = [c for _, c in check_identity(raw, "concepts", errors) if check_concept(c, c["id"], errors, warnings, ctx)]
    ids = {c["id"] for c in raw if isinstance(c, dict) and isinstance(c.get("id"), str)}
    for c in valid:
        origin = c.get("origin")
        if origin is not None and not isinstance(origin, str):
            errors.append({"code": "schema", "where": c["id"], "message": f"origin은 'root' 또는 원본 컨셉 id(문자열)여야 합니다: {origin!r}"})
        elif origin is not None and origin != "root" and origin not in ids:
            errors.append({"code": "unknown_origin", "where": c["id"], "message": f"origin '{origin}'가 없습니다. 처음 만든 컨셉은 'root'로 둡니다."})
    active = [c for c in valid if is_active(c)]
    for c in [c for c in active if c.get("existing_game")][1:]:
        warnings.append({"code": "existing_game_many", "where": c["id"],
                         "message": "existing_game은 이미 만들고 있는 게임 하나에만 적습니다. 후보에 적으면 후보 칸 검사와 구조 비교를 건너뜁니다. "
                                    "새 후보면 키를 지우고 후보 칸을 채웁니다."})
    for c in active:
        if not _text(c.get("next_test")) and not c.get("existing_game"):
            warnings.append({"code": "next_test_missing", "where": c["id"], "message": "이 가설을 가장 싸게 확인할 다음 시험(next_test)이 없습니다."})
        if any(s.get("result") == "dominates" for s in c.get("stress", [])):
            warnings.append({"code": "dominant_policy", "where": c["id"],
                             "message": "단순 전략이 지배하는 결과가 있습니다. 규칙을 바꾸거나, 증거가 충분하면 hard_reject로 제외하세요."})
    for c in valid:   # 기준 이력은 선택하지 않은(되돌린) 컨셉에도 남는다. 다시 고르면 판정 에이전트가 읽는다
        hyps = c["brief"].get("hypotheses") if isinstance(c.get("brief"), dict) else None
        for n, h in enumerate(hyps if isinstance(hyps, list) else []):
            if isinstance(h, dict):
                check_criteria_history(h, n, c["id"], errors)
    unverified: list = []
    gate_notes: list = []
    ack_notes: list = []   # apply_acknowledged가 이어 붙인다
    for c in valid:
        if c.get("status") == "approved":
            check_brief(c, c["id"], errors, warnings)
            if isinstance(c.get("brief"), dict):
                check_success_covers(c, warnings)
                unverified += check_brief_numbers(c, errors, warnings, root, gate_notes, ack_notes)
    structure = check_structure([c for c in active if "signature" in c], warnings, ctx["fixed"])
    status_counts = {s: 0 for s in STATUSES + ("unspecified",)}
    for c in valid:
        status_counts[_status(c)] += 1
    return {
        "kind": "concepts",
        "count": len(valid),
        "status_counts": status_counts,
        "approved": sorted(c["id"] for c in valid if c.get("status") == "approved"),
        "criteria": _approved_criteria(valid),
        "criteria_history": {f"{c['id']}.{h['id']}": x for c in valid if c.get("status") == "approved" and isinstance(c.get("brief"), dict)
                             for h in (c["brief"].get("hypotheses") if isinstance(c["brief"].get("hypotheses"), list) else [])
                             if isinstance(h, dict) and isinstance(h.get("id"), str) and (x := _history_summary(h))},
        "unverified": unverified,
        "gate_notes": gate_notes,
        "ack_notes": ack_notes,
        "stress_summary": {c["id"]: {r: sum(1 for s in c.get("stress", []) if s.get("result") == r) for r in POLICY_RESULTS} for c in valid},
        **structure,
        "errors": errors,
        "warnings": warnings,
    }


def hypothesis_index(data: dict) -> dict:
    """플레이 기록 검사용: {컨셉 id: {approved, hypotheses: [가설 id 또는 None, ...], samples, criteria(가설별 기준 지문), legacy_criteria(예전 계산의 지문)}}. 형식이 틀린 항목은 건너뛴다.
    concepts 배열 자체가 없으면 None(읽지 못함)을 돌려준다. 빈 결과로 돌려주면 모든 참조가 '없는 컨셉'으로 연쇄 보고된다."""
    if not isinstance(data.get("concepts"), list):
        return None
    out: dict = {}
    for c in data["concepts"]:
        if not (isinstance(c, dict) and isinstance(c.get("id"), str)) or c["id"] in out:
            continue
        hyps = (c.get("brief") or {}).get("hypotheses") if isinstance(c.get("brief"), dict) else None
        hyps = hyps if isinstance(hyps, list) else []
        ids = [h.get("id") if isinstance(h, dict) and isinstance(h.get("id"), str) else None for h in hyps]
        named = [h for h in hyps if isinstance(h, dict) and isinstance(h.get("id"), str)]
        samples = {h["id"]: read_sample(h.get("sample")) for h in named if read_sample(h.get("sample"))}
        criteria = {h["id"]: criteria_stamp(h) for h in named}
        legacy = {h["id"]: [s for s in dict.fromkeys(criteria_stamp(h, f) for f in STAMP_FORMS[1:]) if s != criteria[h["id"]]]
                  for h in named}   # 예전 꼴로 기록한 판정의 지문
        builds = {h["id"]: list(h["builds"]) for h in named if isinstance(h.get("builds"), list) and h["builds"] and all(_text(x) for x in h["builds"])}
        history = {h["id"]: [{"stamp": e["stamp"], "date": e["date"], "fields": list(e["before"]), "after_results": e.get("after_results") is True}
                             for e in h["criteria_history"]]
                   for h in named if _history_summary(h)}   # 형식이 맞는 이력만. 틀린 이력은 컨셉 검사가 오류로 알린다
        out[c["id"]] = {"approved": c.get("status") == "approved", "hypotheses": ids, "samples": samples, "criteria": criteria,
                        "legacy_criteria": {k: v for k, v in legacy.items() if v}, "builds": builds, "history": history}
    return out


def table(data: dict, result: dict, ids: list[str] | None = None) -> str:
    """대화에 붙일 비교표(마크다운). 점수 합계 열은 일부러 두지 않는다. ids를 주면 그 후보만 그 순서로 보인다."""
    rows = ["| id | 이름 | 상태 | 반복 결정 | 숙련 표현 | 단순 전략 결과 | 최대 위험 | 제작 부담(가정) | 다음 시험 |",
            "|---|---|---|---|---|---|---|---|---|"]
    by_id: dict = {}
    for c in data.get("concepts") if isinstance(data.get("concepts"), list) else []:
        if isinstance(c, dict) and isinstance(c.get("id"), str):
            by_id.setdefault(c["id"], c)  # 검사기와 같이 첫 항목을 쓴다. 중복은 duplicate_id 오류로 보고된다.
    order = {"approved": 0, "proposed": 1, "unspecified": 2, "cut": 3}
    shown = result["stress_summary"]
    missing: list = []
    if ids:
        missing = [i for i in ids if i not in shown]
        chosen = [i for i in dict.fromkeys(ids) if i in shown]
    else:
        chosen = sorted(shown, key=lambda i: (order.get(_status(by_id[i]), 2), i))
    for cid in chosen:
        c = by_id[cid]
        st = result["stress_summary"][cid]
        stress = " · ".join(f"{RESULT_LABEL[r]} {n}" for r, n in st.items() if n) or "–"
        cost = c.get("cost")
        cost_txt = f"{COST_LABEL[cost['level']]}: {cost['reason']}" if isinstance(cost, dict) and cost.get("level") in COST_LABEL else "–"
        rows.append("| " + " | ".join(_cell(x) for x in (
            cid, c.get("name"), STATUS_LABEL.get(_status(c), _status(c)) + (" · 기존 게임" if c.get("existing_game") is True else ""), c.get("decision"), c.get("skill_expression"),
            stress, c.get("risk"), cost_txt, c.get("next_test"))) + " |")
    if missing:
        rows += ["", "표에 넣지 못한 id(없거나 형식 오류): " + ", ".join(missing)]
    return "\n".join(rows)


def print_counts(report: dict) -> None:
    sc = report["status_counts"]
    print(f"컨셉 {report['count']}개 · 후보 {sc['proposed']} · 선택 {sc['approved']} · 제외 {sc['cut']}"
          + (f" · 미지정 {sc['unspecified']}" if sc["unspecified"] else "")
          + f" · 오류 {len(report['errors'])} · 경고 {len(report['warnings'])}"
          + (f" · 확인한 경고 {len(report['acknowledged'])}" if report.get("acknowledged") else ""))
