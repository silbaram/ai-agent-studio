"""게임 설계 데이터(컨셉·아이템·영구 강화·적)를 브라우저에서 보는 읽기 전용 뷰어 서버.

요청마다 원본 파일을 새로 찾아 읽고, 내용이 바뀌었을 때만 검사기를 다시 돌린다. 문서를 생성하지 않으므로 동기화할 것이 없다.
폴더를 주면 그 안과 design/·data/ 하위 폴더의 데이터 파일을 찾는다. 시뮬레이터 설정과 관계없는 JSON은 건너뛴다.
기본으로 127.0.0.1에만 열린다. 같은 HTML(assets/viewer.html)을 파일로 직접 열면 '불러오기'로 원본 값만 볼 수 있다.
"""
from __future__ import annotations

import hashlib
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import datasets

PAGE = Path(__file__).resolve().parents[2] / "assets" / "viewer.html"


def _version(entries: list[dict]) -> str:
    return hashlib.sha256("|".join(f"{d['path']}:{d['version']}" for d in entries).encode("utf-8")).hexdigest()[:16]


def snapshot(targets: list[Path]) -> dict:
    entries = datasets.validate_all(datasets.scan(targets))
    return {"mode": "server", "version": _version(entries), "datasets": entries}


class SnapshotCache:
    """파일 목록과 내용 해시가 그대로면 이전 검사 결과를 다시 쓴다. 뷰어가 1.5초마다 물어도 검사는 바뀔 때만 돈다."""

    def __init__(self, targets: list[Path]):
        self.targets = targets
        self.lock = threading.Lock()
        self.key = None
        self.body = b""
        self.validations = 0

    def body_bytes(self) -> bytes:
        entries = datasets.scan(self.targets)
        key = _version(entries)
        with self.lock:
            if key != self.key:
                datasets.validate_all(entries)
                self.validations += 1
                self.body = json.dumps({"mode": "server", "version": key, "datasets": entries}, ensure_ascii=False).encode("utf-8")
                self.key = key
            return self.body


def make_handler(targets: list[Path]):
    cache = SnapshotCache(targets)

    class Handler(BaseHTTPRequestHandler):
        snapshots = cache

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
                self._send(200, cache.body_bytes(), "application/json; charset=utf-8")
            else:
                self._send(404, b"not found", "text/plain; charset=utf-8")

        def log_message(self, fmt, *args) -> None:  # 요청 로그로 터미널을 채우지 않는다
            pass

    return Handler


def make_server(targets: list[Path], host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_handler([Path(t).resolve() for t in targets]))


def url_of(server: ThreadingHTTPServer) -> str:
    host, port = server.server_address[:2]
    return f"http://{'127.0.0.1' if host in ('0.0.0.0', '') else host}:{port}/"


def serve(server: ThreadingHTTPServer, open_browser: bool = True) -> None:
    if open_browser:
        webbrowser.open(url_of(server))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
