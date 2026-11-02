"""데이터 파일을 찾아 읽고 종류별 검사기를 돌린다. 뷰어와 check 명령이 함께 쓴다."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import common as c
from . import concepts, enemies, items, upgrades

VALIDATORS = {"concepts": concepts, "items": items, "upgrades": upgrades, "enemies": enemies}
NOT_DATA = "컨셉·아이템·영구 강화·적 데이터가 아닙니다 (최상위에 concepts / items / upgrades / enemies 배열이 필요합니다)."


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
        entry["error"] = NOT_DATA
        return entry
    entry.update({"ok": True, "kind": kind, "label": c.KIND_LABELS[kind], "data": data})
    return entry


def validate_all(entries: list[dict]) -> list[dict]:
    """읽은 항목들에 검사 결과(report)를 붙인다. 적의 드랍 테이블은 함께 읽은 아이템 데이터로 확인한다."""
    loaded_items = [d for d in entries if d["ok"] and d["kind"] == "items"]
    drop_tables = None
    if loaded_items:
        drop_tables = {}
        for d in loaded_items:
            tables = d["data"].get("drop_tables") or {}
            if isinstance(tables, dict):
                drop_tables.update(tables)
    for d in entries:
        if not d["ok"]:
            continue
        if d["kind"] == "enemies":
            d["report"] = enemies.validate(d["data"], drop_tables)
        else:
            d["report"] = VALIDATORS[d["kind"]].validate(d["data"])
    return entries


def collect(targets: list[Path]) -> list[dict]:
    return validate_all([read(p) for p in c.discover([Path(t) for t in targets])])
