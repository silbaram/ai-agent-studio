#!/usr/bin/env python3
"""게임 데이터 원본(아이템·영구 강화·적)을 브라우저에서 보는 읽기 전용 뷰어.

요청마다 원본 파일을 새로 읽고 검사기(validate_items / validate_upgrades / validate_enemies)를 함께 돌린다.
별도 문서를 생성하지 않으므로 동기화 작업이 없다. 파일이 바뀌면 화면이 자동으로 갱신된다.
폴더를 주면 그 안(하위 폴더 제외)의 데이터 파일을 매번 다시 찾는다. 시뮬레이터 설정 파일은 건너뛴다.
기본으로 127.0.0.1에만 열린다. 표준 라이브러리만 사용한다.

    python view_data.py data/
    python view_data.py data/items.json data/enemies.json

같은 HTML(assets/data-viewer.html)을 파일로 직접 열면 '불러오기' 버튼으로 원본 값만 볼 수 있다.
그 경우 검사·계산은 하지 않는다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _common as c  # noqa: E402
import validate_enemies as ve  # noqa: E402
import validate_items as vi  # noqa: E402
import validate_upgrades as vu  # noqa: E402

PAGE = HERE.parent / "assets" / "data-viewer.html"
VALIDATORS = {"items": vi, "upgrades": vu, "enemies": ve}
LABELS = {"items": "아이템", "upgrades": "영구 강화", "enemies": "적"}


def _candidate(path: Path) -> bool:
    """폴더 탐색 시 데이터 파일로 볼지 정한다. 깨진 파일도 이름에 종류가 드러나면 포함해 오류를 보여 준다."""
    try:
        kind, _ = c.load_dataset(path)
    except (OSError, ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return c.kind_from_filename(path) is not None
    return kind in c.DATASET_KINDS


def discover(targets: list[Path]) -> list[Path]:
    files: list[Path] = []
    for t in targets:
        if t.is_dir():
            files.extend(f for f in sorted(t.iterdir())
                         if f.is_file() and f.suffix.lower() in (".json", ".csv") and _candidate(f))
        elif t.is_file():
            files.append(t)
    seen, out = set(), []
    for f in files:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return out


def _read(path: Path) -> dict:
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
        entry["error"] = "아이템·영구 강화·적 데이터가 아닙니다 (최상위에 items / upgrades / enemies 배열이 필요합니다)."
        return entry
    entry.update({"ok": True, "kind": kind, "label": LABELS[kind], "data": data})
    return entry


def snapshot(targets: list[Path]) -> dict:
    datasets = [_read(p) for p in discover(targets)]
    loaded_items = [d for d in datasets if d["ok"] and d["kind"] == "items"]
    drop_tables = None
    if loaded_items:
        drop_tables = {}
        for d in loaded_items:
            tables = d["data"].get("drop_tables") or {}
            if isinstance(tables, dict):
                drop_tables.update(tables)
    for d in datasets:
        if not d["ok"]:
            continue
        if d["kind"] == "enemies":
            d["report"] = ve.validate(d["data"], drop_tables)
        else:
            d["report"] = VALIDATORS[d["kind"]].validate(d["data"])
    version = hashlib.sha256("|".join(f"{d['path']}:{d['version']}" for d in datasets).encode("utf-8")).hexdigest()[:16]
    return {"mode": "server", "version": version, "datasets": datasets}


def make_handler(targets: list[Path]):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            route = self.path.split("?", 1)[0]
            if route == "/":
                try:
                    self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
                except OSError:
                    self._send(500, "뷰어 페이지 파일이 없습니다.".encode("utf-8"), "text/plain; charset=utf-8")
            elif route == "/api/data":
                body = json.dumps(snapshot(targets), ensure_ascii=False).encode("utf-8")
                self._send(200, body, "application/json; charset=utf-8")
            else:
                self._send(404, b"not found", "text/plain; charset=utf-8")

        def log_message(self, fmt, *args) -> None:  # 요청 로그로 터미널을 채우지 않는다
            pass

    return Handler


def make_server(targets: list[Path], host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_handler([Path(t).resolve() for t in targets]))


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="게임 데이터 원본(아이템·영구 강화·적)을 브라우저에서 봅니다 (읽기 전용).")
    ap.add_argument("paths", nargs="+", help="데이터 폴더 또는 JSON/CSV 파일")
    ap.add_argument("--port", type=int, default=8765, help="포트 (기본 8765, 0이면 빈 포트 자동 선택)")
    ap.add_argument("--host", default="127.0.0.1", help="기본 127.0.0.1. 다른 기기에 열 때만 바꾸세요.")
    ap.add_argument("--no-browser", action="store_true", help="브라우저를 자동으로 열지 않습니다.")
    args = ap.parse_args(argv)
    targets = [Path(p).resolve() for p in args.paths]
    missing = [str(p) for p in targets if not p.exists()]
    if missing:
        print("경로를 찾을 수 없습니다: " + ", ".join(missing), file=sys.stderr)
        return 2
    found = discover(targets)
    if not found:
        print("아이템·영구 강화·적 데이터 파일을 찾지 못했습니다.", file=sys.stderr)
        return 2
    try:
        server = make_server(targets, args.host, args.port)
    except OSError as exc:
        print(f"서버를 열 수 없습니다 ({args.host}:{args.port}): {exc}. --port로 다른 포트를 지정하세요.", file=sys.stderr)
        return 2
    host, port = server.server_address[:2]
    url = f"http://{'127.0.0.1' if host in ('0.0.0.0', '') else host}:{port}/"
    if args.host not in ("127.0.0.1", "localhost"):
        print(f"주의: {args.host}에 열었습니다. 같은 네트워크의 다른 기기에서 접속할 수 있습니다.")
    print(f"데이터 뷰어: {url}")
    for f in found:
        print(f"  - {f}")
    print("파일을 고치면 화면이 자동으로 갱신됩니다. 종료: Ctrl+C")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
