"""컨셉 기록(design/concepts.json)을 결정적으로 검사한다.

재미를 점수로 매기지 않는다. 기록이 빠짐없는지, 구조가 사실상 같은 컨셉이 있는지,
후보들이 한 구조에 몰려 있지 않은지, 선택한 컨셉의 브리프가 반증 가능한 형태인지 본다.
형식: concept-exploration/references/concept-record.md
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata

from . import provenance
from .common import ID_PATTERN, STATUSES, check_identity, is_active, is_int, josa
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
    for f in REQUIRED_TEXT:
        if not _text(c.get(f)):
            errors.append({"code": "missing_field", "where": where, "message": f"{josa(f, '이가')} 비어 있습니다."})
            ok = False
    status = c.get("status")
    if status is not None and status not in STATUSES:
        errors.append({"code": "schema", "where": where, "message": f"status는 {', '.join(STATUSES)} 중 하나입니다: {status!r}"})
        ok = False
    sig = c.get("signature")
    if not isinstance(sig, dict) or not all(isinstance(k, str) and _text(v) for k, v in sig.items()):
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
    """표본을 줄인 기록 {players·runs: 줄이기 전 값, after_run: 몇 판째 뒤에 줄였나, before_results: 결과 파일을 열기 전인가, date}."""
    r = v["reduced_from"]
    bad = sorted(str(k) for k in r if k not in REDUCED_KEYS) if isinstance(r, dict) else []
    if bad:
        return (f"sample.reduced_from에 알 수 없는 키 {', '.join(bad)}.{''.join(_did_you_mean(k, REDUCED_KEYS) for k in bad)} "
                f"쓸 수 있는 키는 {', '.join(REDUCED_KEYS)}입니다")
    if not (isinstance(r, dict) and isinstance(r.get("before_results"), bool)
            and is_int(r.get("after_run"), 0) and isinstance(r.get("date"), str) and DATE.match(r["date"])
            and any(k in r for k in ("players", "runs")) and all(is_int(r[k], 1) for k in ("players", "runs") if k in r)):
        return ("sample.reduced_from은 {runs 또는 players: 줄이기 전 값, after_run: 몇 판째 뒤에 줄였나(0 이상), "
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


def _few(values: list) -> str:
    shown = list(dict.fromkeys(values))
    return "·".join(shown[:4]) + ("…" if len(shown) > 4 else "")


def check_brief_numbers(c: dict, errors: list, warnings: list) -> list[str]:
    """브리프 문장 안의 수치 출처 태그를 md와 같은 규칙으로 검사한다. [가정]이 남은 위치를 남은 값과 함께 돌려준다(--fail-on-assumed용).
    태그 형식 오류는 브리프 어디서든 보고한다. 태그 없는 수치는 판정 기준 문장에서만 경고하고, 거기서는 출처가 비어 있는 값이라 게이트에서도 막는다
    (지문은 태그를 보지 않으므로 태그를 지운 것을 지문으로는 알 수 없다)."""
    assumed = []
    tagged: dict = {}   # {가설 번호: {수치: {칸: {종류}}}} 같은 값이 칸마다 다른 태그인지 본다
    success: dict = {}  # 성공 기준의 {수치: {종류}}. 가설마다 문턱을 다시 적는 칸이라 가설의 같은 값과 견준다
    for path, text in _strings(c["brief"], "brief"):
        criteria_text = _is_criteria_text(path)
        r = provenance.check_text(text, path, bare_numbers=criteria_text)
        for f in r.findings:
            if f.level == "error":
                errors.append({"code": "provenance", "where": c["id"], "message": f"{path}: {f.message}"})
            elif criteria_text:
                warnings.append({"code": "untagged_number", "where": c["id"], "message": f"{path}: {f.message}"})
        left = [t.near for t in r.tags if t.kind == "assumed"]
        bare = r.untagged if criteria_text else []
        if left or bare:
            parts = ([f"가정: {_few(left)}"] if left else []) + ([f"태그 없음: {_few(bare)}"] if bare else [])
            assumed.append(f"{c['id']}.{path}({'; '.join(parts)})")
        m = CRITERIA_TEXT.match(path)
        for t in r.tags if m or path == SUCCESS_PATH else []:
            if t.value and m:
                tagged.setdefault(int(m.group(1)), {}).setdefault(t.value, {}).setdefault(m.group(2), set()).add(t.kind)
            elif t.value:
                success.setdefault(t.value, set()).add(t.kind)
    hyps = c["brief"].get("hypotheses") if isinstance(c["brief"].get("hypotheses"), list) else []
    for n, values in sorted(tagged.items()):
        hid = hyps[n].get("id") if isinstance(hyps[n], dict) else None
        for value, fields in values.items():
            if value in success:
                fields = {**fields, "success_criteria": success[value]}
            dec = [f for f, kinds in fields.items() if "decided" in kinds]
            asm = [f for f, kinds in fields.items() if "assumed" in kinds and f not in dec]
            if dec and asm:
                warnings.append({"code": "criteria_tag_mismatch", "where": c["id"], "part": value,
                                 "message": f"brief.hypotheses[{n}]({hid or '이름 없음'}): 같은 값 {josa(value, '이가')} {', '.join(dec)}에서는 [결정], "
                                            f"{', '.join(asm)}에서는 [가정]입니다. 같은 잣대면 태그를 맞춥니다. "
                                            f"뜻이 다른 값이면 컨셉의 acknowledged에 {{\"criteria_tag_mismatch\": {{\"{value}\": 까닭}}}}을 적습니다."})
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


def validate(data: dict) -> dict:
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
    for c in active:
        if not _text(c.get("next_test")):
            warnings.append({"code": "next_test_missing", "where": c["id"], "message": "이 가설을 가장 싸게 확인할 다음 시험(next_test)이 없습니다."})
        if any(s.get("result") == "dominates" for s in c.get("stress", [])):
            warnings.append({"code": "dominant_policy", "where": c["id"],
                             "message": "단순 전략이 지배하는 결과가 있습니다. 규칙을 바꾸거나, 증거가 충분하면 hard_reject로 제외하세요."})
    unverified: list = []
    for c in valid:
        if c.get("status") == "approved":
            check_brief(c, c["id"], errors, warnings)
            if isinstance(c.get("brief"), dict):
                unverified += check_brief_numbers(c, errors, warnings)
    structure = check_structure(active, warnings, ctx["fixed"])
    status_counts = {s: 0 for s in STATUSES + ("unspecified",)}
    for c in valid:
        status_counts[_status(c)] += 1
    return {
        "kind": "concepts",
        "count": len(valid),
        "status_counts": status_counts,
        "approved": sorted(c["id"] for c in valid if c.get("status") == "approved"),
        "criteria": _approved_criteria(valid),
        "unverified": unverified,
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
        out[c["id"]] = {"approved": c.get("status") == "approved", "hypotheses": ids, "samples": samples, "criteria": criteria,
                        "legacy_criteria": {k: v for k, v in legacy.items() if v}, "builds": builds}
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
            cid, c.get("name"), STATUS_LABEL.get(_status(c), _status(c)), c.get("decision"), c.get("skill_expression"),
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
