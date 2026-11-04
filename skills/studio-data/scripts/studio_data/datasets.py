"""데이터 파일을 찾아 한 번 읽고 종류별 검사기를 돌린다. 뷰어와 check 명령이 함께 쓴다."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import common as c
from . import budget, combat, concepts, crafting, economy, enemies, growth, items, levels, meta_sim, playtests, upgrades

VALIDATORS = {"concepts": concepts, "items": items, "upgrades": upgrades, "enemies": enemies, "combat": combat,
              "growth": growth, "budget": budget, "crafting": crafting, "economy": economy, "levels": levels, "playtests": playtests}
NOT_DATA = ("컨셉·아이템·영구 강화·적·전투 계산·판 안 성장·스탯 예산·강화·합성·재화 흐름·레벨 구성·플레이 기록 데이터가 아닙니다 "
            "(최상위에 concepts / items / upgrades / enemies / levels / playtests 배열이나 combat / growth / budget / crafting / economy 객체가 필요합니다).")
CONFIG_KEYS = (b'"seed"', b'"trials"', b'"max_runs"')  # 시뮬레이터 설정의 필수 키. 하나만으로는 게임 설정과 나눌 수 없어 모두 있을 때만 센다


def _broken_levels(path: Path, raw: bytes) -> bool:
    """읽지 못한 JSON이 레벨 구성으로 보이는가. 이름만으로는 게임 자체의 levels.json과 나눌 수 없어 키로 본다.
    encounters 하나는 게임 파일에도 흔한 키라 levels와 함께 있을 때만 센다. 내용이 없는 levels.json은 게임 파일일 수 없으니 이 형식으로 본다."""
    if path.suffix.lower() != ".json":
        return False
    return b'"threat_budget"' in raw or (b'"levels"' in raw and b'"encounters"' in raw) or (path.stem.lower() == "levels" and not raw.strip())


def _kind_by_name(path: Path) -> str | None:
    """파일 이름이 곧 종류인 JSON(economy.json 등). 깨져서 키를 읽지 못해도 그 종류의 읽기 실패로 알린다. 게임이 자기 형식으로도 쓰는 이름은 뺀다."""
    named = path.stem.lower()
    return named if path.suffix.lower() == ".json" and named in c.DATASET_KINDS and named not in c.FOREIGN_NAMES else None


def read(path: Path) -> dict:
    """파일 하나를 읽어 {name, path, ok, kind, label, version, data | error}를 돌려준다. 예외를 던지지 않는다.
    시뮬레이터 설정이면 config에 내용을 담는다(깨져서 읽지 못했으면 None)."""
    path = Path(path)
    entry: dict = {"name": path.name, "path": str(path), "ok": False, "kind": None, "version": None}
    try:
        raw = path.read_bytes()
    except OSError as exc:
        entry["error"] = f"파일을 읽을 수 없습니다: {exc}"
        return entry
    entry["version"] = hashlib.sha256(raw).hexdigest()[:16]
    try:
        kind, data = c.load_dataset(path)
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        entry["kind"] = c.kind_from_filename(path) or _kind_by_name(path) or ("levels" if _broken_levels(path, raw) else None)
        entry["error"] = f"파일 형식 오류: {exc}"
        if path.suffix.lower() == ".json" and all(k in raw for k in CONFIG_KEYS):
            entry["config"] = None
        return entry
    if kind not in c.DATASET_KINDS:
        entry["meta"] = kind == "meta"
        if entry["meta"]:
            entry["config"] = data
        named = path.stem.lower()
        if kind is None and named in c.DATASET_KINDS and (named not in c.FOREIGN_NAMES or not data):
            # 이름이 concepts.json 같은데 최상위 키가 없으면 건너뛰지 않고 이유를 알린다(예: 제약만 적은 직후).
            entry["kind"] = named
            entry["error"] = (f"최상위에 \"{named}\" 배열이 없어 {c.KIND_LABELS[named]} 파일로 읽지 못했습니다. "
                              f"아직 항목이 없으면 \"{named}\": []를 넣으세요.")
        else:
            entry["error"] = NOT_DATA
        return entry
    entry.update({"ok": True, "kind": kind, "label": c.KIND_LABELS[kind], "data": data})
    return entry


def _wanted_in_folder(entry: dict) -> bool:
    """폴더를 훑을 때 보여 줄 파일: 데이터 파일, 또는 이름에 종류가 드러나는데 읽지 못한 파일(오류를 보여 주려고)."""
    return entry["ok"] or (entry.get("kind") in c.DATASET_KINDS and not entry.get("meta"))


def _files(targets: list[Path]):
    """훑을 파일 (경로, 직접 지정했는가). 파일은 그대로, 폴더는 그 안과 design/·data/ 하위 폴더(한 단계)의 JSON·CSV."""
    for t in (Path(t) for t in targets):
        if t.is_dir():
            for d in [t] + [t / s for s in c.SUBFOLDERS if (t / s).is_dir()]:
                for f in sorted(d.iterdir()):
                    if f.is_file() and f.suffix.lower() in (".json", ".csv"):
                        yield f, False
        elif t.is_file():
            yield t, True


def scan_all(targets: list[Path]) -> tuple[list[dict], list[str]]:
    """_files의 파일 중 데이터 파일을 읽어 (항목, 건너뛴 파일)로 돌려준다. 각 파일은 한 번만 읽는다.
    건너뛴 파일은 폴더를 훑다 뺀 FOREIGN_NAMES 이름의 JSON이다. 게임 자기 파일일 수 있어 오류로 올리지 않지만, 키 오타일 수도 있어 말없이 지나가지 않는다.
    같은 파일을 직접 지정했으면 항목으로 읽었으니 건너뛴 파일이 아니다."""
    entries: list[dict] = []
    seen: set = set()
    passed: dict = {}

    def add(path: Path, explicit: bool) -> None:
        key = path.resolve()
        if key in seen or (key in passed and not explicit):
            return
        entry = read(path)
        if explicit or _wanted_in_folder(entry):
            seen.add(key)
            entries.append(entry)
        elif path.suffix.lower() == ".json" and path.stem.lower() in c.FOREIGN_NAMES:
            passed[key] = str(path)

    for path, explicit in _files(targets):
        add(path, explicit)
    return entries, [p for key, p in passed.items() if key not in seen]


def scan(targets: list[Path]) -> list[dict]:
    return scan_all(targets)[0]


def skipped_note(path: str) -> str:
    """건너뛴 파일을 알리는 문장. check와 뷰어가 같은 문장을 쓴다."""
    return f"{path}: 레벨 구성 형식이 아니라 건너뛰었습니다(최상위에 levels나 threat_budget이 없습니다). 게임 자체 파일이 아니면 키를 확인합니다."


def _config_sourced(config: dict | None) -> bool:
    """설정의 출처가 계산이나 측정인가. 형식은 simulate와 같은 규칙(check_common)으로 본다."""
    prov = (config or {}).get("provenance")
    if not isinstance(prov, dict):
        return False
    entry = {"provenance": dict(prov)}
    return c.check_common(entry, "provenance", []) and entry["provenance"]["kind"] != "assumed"


def unverified_configs(targets: list[Path]) -> list[str]:
    """시뮬레이터 설정 중 출처가 가정이거나, 비어 있거나, 형식이 틀리거나, 깨져서 읽지 못한 것의 경로(--fail-on-assumed).
    데이터 파일이 아니라 scan이 돌려주지 않으므로 같은 파일을 따로 읽는다."""
    out, seen = [], set()
    for path, _ in _files(targets):
        key = path.resolve()
        if key not in seen:
            seen.add(key)
            entry = read(path)
            if "config" in entry and not _config_sourced(entry["config"]):
                out.append(str(path))
    return out


def discover(targets: list[Path]) -> list[Path]:
    return [Path(e["path"]) for e in scan(targets)]


def _index(entries: list[dict], kind: str) -> dict | None:
    """함께 읽은 kind 데이터의 {id: 항목}. 그 종류가 없거나, 읽지 못했거나, 배열 형식이 아닌 파일이 있으면 None(미확인).
    빈 결과로 돌려주면 모든 참조가 '없는 id'로 연쇄 보고된다."""
    if any(not d["ok"] and d.get("kind") == kind for d in entries):
        return None
    loaded = [d for d in entries if d["ok"] and d["kind"] == kind]
    if not loaded or any(not isinstance(d["data"].get(kind), list) for d in loaded):
        return None
    out: dict = {}
    for d in loaded:
        for e in d["data"][kind]:
            if isinstance(e, dict) and isinstance(e.get("id"), str):
                out.setdefault(e["id"], e)  # 검사기와 같이 첫 항목을 쓴다
    return out


_META_CACHE: dict = {}  # meta_config 경로 → (파일 서명, 읽은 결과). 뷰어가 갱신마다 다시 검사해도 바뀌지 않은 설정은 다시 읽지 않는다


def _signature(path: Path) -> tuple | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


def _read_meta(path: Path) -> dict:
    """메타 성장 설정 하나를 읽어 정규화한다. 설정과 그 upgrades_file이 바뀌지 않았으면 앞서 읽은 결과를 쓴다.
    읽지 못하거나 형식이 틀리면 {"error": 이유}. 설정 파일의 문제는 그 설정을 가리킨 곳(재화)의 오류로 보고한다."""
    key = str(path.resolve())
    try:
        raw_bytes = path.read_bytes()
        raw = json.loads(raw_bytes.decode("utf-8"))
    except (OSError, ValueError) as exc:
        _META_CACHE.pop(key, None)
        return {"error": f"{path}: {exc}"}
    ups = raw.get("upgrades_file") if isinstance(raw, dict) else None
    sig = (hashlib.sha256(raw_bytes).hexdigest(), _signature(path.parent / ups) if isinstance(ups, str) else None)
    cached = _META_CACHE.get(key)
    if cached and cached[0] == sig:
        return cached[1]
    try:
        cfg = meta_sim.normalize(raw, base_dir=path.parent)
    except Exception as exc:  # noqa: BLE001 - 남의 파일 형식 문제로 재화 흐름 검사 전체를 멈추지 않는다
        cfg = {"error": f"{path}: {type(exc).__name__ + ': ' if not isinstance(exc, ValueError) else ''}{exc}"}
    _META_CACHE[key] = (sig, cfg)
    return cfg


def _meta_configs(entry: dict) -> dict | None:
    """재화 흐름 파일의 판 사이 재화가 meta_config로 가리키는 메타 성장 설정을 읽는다. {재화: 설정 또는 {"error": 이유}}.
    경로는 그 재화 흐름 파일이 있는 폴더 기준이다(설정 안의 upgrades_file은 설정 파일 폴더 기준)."""
    cur = (entry["data"].get("economy") or {}).get("currencies") if isinstance(entry["data"].get("economy"), dict) else None
    out = {}
    for k, v in (cur.items() if isinstance(cur, dict) else []):
        link = v.get("meta_config") if isinstance(v, dict) else None
        if isinstance(link, str) and link.strip():
            out[k] = _read_meta(Path(entry["path"]).parent / link)
    return out or None


def _choice_items(growth_data: dict | None) -> dict:
    """판 안 성장의 아이템을 주는 레벨업 선택지 {아이템 id: 설명}. 강화·합성의 획득 경로로 센다."""
    choices = (growth_data or {}).get("choices")
    out = {}
    for ch in choices if isinstance(choices, list) else []:
        if isinstance(ch, dict) and isinstance(ch.get("item"), str) and c.is_active(ch):
            out.setdefault(ch["item"], f"레벨업 선택지 {ch.get('id')}")
    return out


def indexes(entries: list[dict]) -> dict:
    """아이템·영구 강화·적의 {id: 항목}(읽지 못했거나 없으면 None). 전투 계산과 메타 성장 시뮬레이터가 같은 규칙으로 참조한다."""
    return {k: _index(entries, k) for k in ("items", "upgrades", "enemies")}


def _ids(raw) -> set | None:
    return {x["id"] for x in raw if isinstance(x, dict) and isinstance(x.get("id"), str)} if isinstance(raw, list) else None


def _stage_refs(combat_data: dict | None, growth_data: dict | None, economy_data: dict | None, by_id: dict) -> dict:
    """플레이 기록의 단계 기록이 가리키는 id. 데이터가 없으면 그 종류는 None(미확인)."""
    cfg = (economy_data or {}).get("economy")
    currencies = cfg.get("currencies") if isinstance(cfg, dict) else None
    return {"stages": _ids((combat_data or {}).get("stages")), "builds": _ids((growth_data or {}).get("builds")),
            "upgrades": set(by_id["upgrades"]) if by_id["upgrades"] is not None else None,
            "enemies": set(by_id["enemies"]) if by_id["enemies"] is not None else None,
            "currencies": set(currencies) if isinstance(currencies, dict) else None}


def _threat_scores(entries: list[dict]) -> dict | None:
    """적 검사가 낸 위협도 {id: 값}(적 색인과 같이 첫 항목을 쓴다). 적이 없거나 검사를 마치지 못한 적 파일이 있으면 None."""
    found = [d for d in entries if d.get("kind") == "enemies"]
    if not found or any("report" not in d for d in found):
        return None
    out: dict = {}
    for d in found:
        for k, v in d["report"]["scores"].items():
            out.setdefault(k, v)
    return out


def _kill_times(entries: list[dict]) -> dict | None:
    """전투 계산이 낸 처치 시간 {단계: {적: 초}}. 전투 계산이 없거나 검사를 마치지 못했으면 None."""
    report = next((d.get("report") for d in entries if d["ok"] and d["kind"] == "combat"), None)
    if report is None:
        return None
    out: dict = {}
    for r in report["rows"]:
        out.setdefault(r["stage"], {})[r["enemy"]] = r["time_to_kill"]
    return out


def validate_all(entries: list[dict]) -> list[dict]:
    """읽은 항목들에 검사 결과(report)를 붙인다. 적의 드랍 테이블은 함께 읽은 아이템 데이터로,
    플레이 기록의 컨셉·가설 참조는 함께 읽은 컨셉 데이터로, 전투 계산은 함께 읽은 아이템·영구 강화·적 데이터로 확인한다.
    스탯 예산은 아이템·적 데이터와 비교하고, 전투 계산이 있으면 그 공식으로 잰 스탯 원가 제안을 붙인다.
    스탯 예산이 있으면 아이템·적 검사도 그 원가를 예산 가중치로 쓴다(같은 '예산'을 두 곳에서 따로 정하지 않는다).
    강화·합성은 아이템 데이터와 드랍 테이블(과 판 안 성장의 아이템 선택지)로 참조·획득 경로를, 스탯 예산이 있으면 가치를 확인한다.
    재화 흐름은 적 보상·드랍 테이블·아이템 가격·영구 강화 비용·강화·합성 비용을 함께 읽은 데이터에서 가져오고,
    전투 단계 연결(combat_stage)과 메타 성장 설정(meta_config)을 맞춰 본다.
    판 안 성장은 전투 계산 파일과 그 참조 데이터로 빌드마다 전투 계산을 다시 한다.
    레벨 구성은 적의 위협도와 전투 단계로 조우를 재고, 재화 흐름의 처치 수와 맞춰 본다. 전투 계산의 처치 시간과 스탯 예산의 적 곡선을 참고 값으로 낸다.
    검사기가 예상하지 못한 예외를 내면 그 파일만 오류로 표시하고 나머지는 계속 검사한다."""
    loaded_items = [d for d in entries if d["ok"] and d["kind"] == "items"]
    broken_items = [d for d in entries if not d["ok"] and d.get("kind") == "items"]
    drop_tables = None
    if loaded_items:
        drop_tables = {}
        for d in loaded_items:
            tables = d["data"].get("drop_tables") or {}
            if isinstance(tables, dict):
                drop_tables.update(tables)
    by_id = indexes(entries)
    budget_data = next((d["data"] for d in entries if d["ok"] and d["kind"] == "budget"), None)
    crafting_data = next((d["data"] for d in entries if d["ok"] and d["kind"] == "crafting"), None)
    budget_settings = budget.read_settings(budget_data, []) if budget_data is not None else None
    costs = {side: spec["costs"] for side, spec in (budget_settings or {}).get("sides", {}).items()}  # 아이템·적 검사의 예산 가중치
    growth_data = next((d["data"] for d in entries if d["ok"] and d["kind"] == "growth"), None)
    suggestions = None
    combat_data = next((d["data"] for d in entries if d["ok"] and d["kind"] == "combat"), None)
    if combat_data is not None and any(d["ok"] and d["kind"] == "budget" for d in entries):  # 쓰는 곳이 있을 때만 잰다
        try:
            suggestions = combat.marginal_costs(combat_data, crafting=crafting_data, **by_id)
        except Exception as exc:  # noqa: BLE001 - 제안은 보조 정보다. 실패는 예산 검사의 경고로 알린다
            suggestions = {"failed": f"{type(exc).__name__}: {exc}"}
    loaded_concepts = [d for d in entries if d["ok"] and d["kind"] == "concepts"]
    broken_concepts = [d for d in entries if not d["ok"] and d.get("kind") == "concepts"]
    hypotheses = None
    for d in loaded_concepts:
        index = concepts.hypothesis_index(d["data"])
        if index is None:
            broken_concepts.append(d)
            continue
        hypotheses = hypotheses or {}
        for cid, info in index.items():
            hypotheses.setdefault(cid, info)
    economy_data = next((d["data"] for d in entries if d["ok"] and d["kind"] == "economy"), None)
    stage_refs = _stage_refs(combat_data, growth_data, economy_data, by_id)
    for d in sorted(entries, key=lambda x: x.get("kind") == "levels"):  # 레벨 구성은 적 검사의 위협도를 쓰므로 마지막에 검사한다
        if not d["ok"]:
            continue
        try:
            if d["kind"] == "items":
                d["report"] = items.validate(d["data"], weights=costs.get("items"))
            elif d["kind"] == "enemies":
                d["report"] = enemies.validate(d["data"], drop_tables, items_unreadable=bool(broken_items), weights=costs.get("enemies"))
            elif d["kind"] == "combat":
                d["report"] = combat.validate(d["data"], crafting=crafting_data, **by_id)
            elif d["kind"] == "budget":
                d["report"] = budget.validate(d["data"], items=by_id["items"], enemies=by_id["enemies"], suggestions=suggestions)
            elif d["kind"] == "crafting":
                d["report"] = crafting.validate(d["data"], items=by_id["items"], drop_tables=drop_tables, budget=budget_settings,
                                                extra_sources=_choice_items(growth_data))
            elif d["kind"] == "growth":
                d["report"] = growth.validate(d["data"], combat=combat_data, crafting=crafting_data, **by_id)
            elif d["kind"] == "economy":
                d["report"] = economy.validate(d["data"], enemies=by_id["enemies"], items=by_id["items"], drop_tables=drop_tables,
                                               upgrades=by_id["upgrades"], crafting=crafting_data, combat=combat_data,
                                               meta=_meta_configs(d))
            elif d["kind"] == "levels":
                enemy_side = (budget_settings or {}).get("sides", {}).get("enemies") or {}
                d["report"] = levels.validate(d["data"], enemies=by_id["enemies"], threat=_threat_scores(entries), combat=combat_data, economy=economy_data,
                                              kill_times=_kill_times(entries), enemy_curve=enemy_side.get("curve"))
                first = next(x for x in entries if x["ok"] and x["kind"] == "levels")
                if d is not first:  # 단계 범위와 처치 수는 파일을 넘어 세지 않는다. 일부만 세어 틀린 결과를 내지 않게 한 파일로 둔다
                    c.add_issue(d["report"]["errors"], "schema", "levels", f"레벨 구성 파일은 하나만 씁니다. {first['name']}에 합칩니다.")
            elif d["kind"] == "playtests":
                d["report"] = playtests.validate(d["data"], hypotheses, concepts_unreadable=bool(broken_concepts), refs=stage_refs)
            else:
                d["report"] = VALIDATORS[d["kind"]].validate(d["data"])
            c.apply_acknowledged(d["kind"], d["data"], d["report"])
        except Exception as exc:  # noqa: BLE001 - 한 파일의 예외가 뷰어·검사 전체를 멈추지 않게 한다
            d.update({"ok": False, "error": f"검사기가 처리하지 못한 형식입니다 ({type(exc).__name__}: {exc}). 이 파일의 형식을 확인하세요."})
            d.pop("report", None)
    return entries


def collect(targets: list[Path]) -> list[dict]:
    return validate_all(scan(targets))
