#!/usr/bin/env python3
"""아이템 데이터 원본을 브라우저에서 보기 좋게 보여 주는 읽기 전용 뷰어.

원본 JSON/CSV를 요청마다 새로 읽고 validate_items.py 검사를 함께 돌린다.
별도 문서를 생성하지 않으므로 동기화 작업이 없다. 파일이 바뀌면 화면이 자동으로 갱신된다.
기본으로 127.0.0.1에만 열린다. 표준 라이브러리만 사용한다.

    python view_items.py data/items.json
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
import validate_items as vi  # noqa: E402

PAGE = HERE.parent / "assets" / "item-viewer.html"


def snapshot(path: Path) -> dict:
    """원본 파일을 읽어 데이터, 검사 결과, 버전(내용 해시)을 돌려준다. 실패해도 예외 대신 오류를 담는다."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return {"ok": False, "path": str(path), "version": None, "error": f"파일을 읽을 수 없습니다: {exc}"}
    version = hashlib.sha256(raw).hexdigest()[:16]
    try:
        data = vi.load(path)
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        return {"ok": False, "path": str(path), "version": version, "error": f"파일 형식 오류: {exc}"}
    report = vi.validate(data)
    return {"ok": True, "path": str(path), "version": version, "data": data, "report": report}


def make_handler(path: Path):
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
            elif route == "/api/items":
                body = json.dumps(snapshot(path), ensure_ascii=False).encode("utf-8")
                self._send(200, body, "application/json; charset=utf-8")
            else:
                self._send(404, b"not found", "text/plain; charset=utf-8")

        def log_message(self, fmt, *args) -> None:  # 요청 로그로 터미널을 채우지 않는다
            pass

    return Handler


def make_server(path: Path, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_handler(path))


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="아이템 데이터 원본을 브라우저에서 봅니다 (읽기 전용).")
    ap.add_argument("path", help="items JSON 또는 CSV")
    ap.add_argument("--port", type=int, default=8765, help="포트 (기본 8765, 0이면 빈 포트 자동 선택)")
    ap.add_argument("--host", default="127.0.0.1", help="기본 127.0.0.1. 다른 기기에 열 때만 바꾸세요.")
    ap.add_argument("--no-browser", action="store_true", help="브라우저를 자동으로 열지 않습니다.")
    args = ap.parse_args(argv)
    path = Path(args.path).resolve()
    if not path.is_file():
        print(f"파일을 찾을 수 없습니다: {args.path}", file=sys.stderr)
        return 2
    try:
        server = make_server(path, args.host, args.port)
    except OSError as exc:
        print(f"서버를 열 수 없습니다 ({args.host}:{args.port}): {exc}. --port로 다른 포트를 지정하세요.", file=sys.stderr)
        return 2
    host, port = server.server_address[:2]
    url = f"http://{'127.0.0.1' if host in ('0.0.0.0', '') else host}:{port}/"
    if args.host not in ("127.0.0.1", "localhost"):
        print(f"주의: {args.host}에 열었습니다. 같은 네트워크의 다른 기기에서 접속할 수 있습니다.")
    print(f"아이템 뷰어: {url}  (원본: {path})")
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
