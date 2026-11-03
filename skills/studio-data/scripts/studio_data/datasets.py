"""데이터 파일을 찾아 한 번 읽고 종류별 검사기를 돌린다. 뷰어와 check 명령이 함께 쓴다."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import common as c
from . import budget, combat, concepts, crafting, economy, enemies, growth, items, meta_sim, playtests, upgrades

VALIDATORS = {"concepts": concepts, "items": items, "upgrades": upgrades, "enemies": enemies, "combat": combat,
              "growth": growth, "budget": budget, "crafting": crafting, "economy": economy, "playtests": playtests}
NOT_DATA = ("컨셉·아이템·영구 강화·적·전투 계산·판 안 성장·스탯 예산·강화·합성·재화 흐름·플레이 기록 데이터가 아닙니다 "
            "(최상위에 concepts / items / upgrades / enemies / playtests 배열이나 combat / growth / budget / crafting / economy 객체가 필요합니다).")


def read(path: Path) -> dict:
    """파일 하나를 읽어 {name, path, ok, kind, label, version, data | error}를 돌려준다. 예외를 던지지 않는다."""
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
        entry["kind"] = c.kind_from_filename(path)
        entry["error"] = f"파일 형식 오류: {exc}"
        return entry
    if kind not in c.DATASET_KINDS:
        entry["meta"] = kind == "meta"
        named = path.stem.lower()
        if kind is None and named in c.DATASET_KINDS:
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


def scan(targets: list[Path]) -> list[dict]:
    """파일은 그대로, 폴더는 그 안과 design/·data/ 하위 폴더(한 단계)를 훑는다. 각 파일은 한 번만 읽는다."""
    entries: list[dict] = []
    seen: set = set()

    def add(path: Path, explicit: bool) -> None:
        key = path.resolve()
        if key in seen:
            return
        entry = read(path)
        if explicit or _wanted_in_folder(entry):
            seen.add(key)
            entries.append(entry)

    for t in (Path(t) for t in targets):
        if t.is_dir():
            for d in [t] + [t / s for s in c.SUBFOLDERS if (t / s).is_dir()]:
                for f in sorted(d.iterdir()):
                    if f.is_file() and f.suffix.lower() in (".json", ".csv"):
                        add(f, explicit=False)
        elif t.is_file():
            add(t, explicit=True)
    return entries


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


def validate_all(entries: list[dict]) -> list[dict]:
    """읽은 항목들에 검사 결과(report)를 붙인다. 적의 드랍 테이블은 함께 읽은 아이템 데이터로,
    플레이 기록의 컨셉·가설 참조는 함께 읽은 컨셉 데이터로, 전투 계산은 함께 읽은 아이템·영구 강화·적 데이터로 확인한다.
    스탯 예산은 아이템·적 데이터와 비교하고, 전투 계산이 있으면 그 공식으로 잰 스탯 원가 제안을 붙인다.
    스탯 예산이 있으면 아이템·적 검사도 그 원가를 예산 가중치로 쓴다(같은 '예산'을 두 곳에서 따로 정하지 않는다).
    강화·합성은 아이템 데이터와 드랍 테이블(과 판 안 성장의 아이템 선택지)로 참조·획득 경로를, 스탯 예산이 있으면 가치를 확인한다.
    재화 흐름은 적 보상·드랍 테이블·아이템 가격·영구 강화 비용·강화·합성 비용을 함께 읽은 데이터에서 가져오고,
    전투 단계 연결(combat_stage)과 메타 성장 설정(meta_config)을 맞춰 본다.
    판 안 성장은 전투 계산 파일과 그 참조 데이터로 빌드마다 전투 계산을 다시 한다.
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
    for d in entries:
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
