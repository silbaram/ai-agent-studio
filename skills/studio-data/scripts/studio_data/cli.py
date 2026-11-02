"""studio.py의 하위 명령: view / check / simulate / provenance.

종료 코드
  0  통과
  1  오류, 또는 --strict 경고, 또는 --fail-on-assumed 가정 항목
  2  사용법 오류(경로 없음, 읽을 수 없는 파일, 데이터 없음, 설정 오류, 서버를 열 수 없음)
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import asdict
from pathlib import Path

from . import concepts, datasets, enemies, items, meta_sim, provenance, upgrades, viewer

EXTRA_PRINTERS = {"items": items.print_extra, "upgrades": upgrades.print_extra, "enemies": enemies.print_extra}
TABLE_PRINTERS = {"concepts": concepts.table}
COUNT_PRINTERS = {"concepts": concepts.print_counts}


def _missing(paths: list[str]) -> list[str]:
    return [p for p in paths if not Path(p).exists()]


# ---------- view ----------
def cmd_view(args) -> int:
    missing = _missing(args.paths)
    if missing:
        print("경로를 찾을 수 없습니다: " + ", ".join(missing), file=sys.stderr)
        return 2
    targets = [Path(p).resolve() for p in args.paths]
    found = datasets.discover(targets)
    if not found:
        print("컨셉·아이템·영구 강화·적 데이터 파일을 찾지 못했습니다.", file=sys.stderr)
        return 2
    try:
        server = viewer.make_server(targets, args.host, args.port)
    except OSError as exc:
        print(f"서버를 열 수 없습니다 ({args.host}:{args.port}): {exc}. --port로 다른 포트를 지정하세요.", file=sys.stderr)
        return 2
    if args.host not in ("127.0.0.1", "localhost"):
        print(f"주의: {args.host}에 열었습니다. 같은 네트워크의 다른 기기에서 접속할 수 있습니다.")
    print(f"데이터 뷰어: {viewer.url_of(server)}")
    for f in found:
        print(f"  - {f}")
    print("파일을 고치면 화면이 자동으로 갱신됩니다. 종료: Ctrl+C")
    viewer.serve(server, open_browser=not args.no_browser)
    return 0


# ---------- check ----------
def _print_data_counts(entry: dict) -> None:
    """출처 필드가 있는 데이터(아이템·영구 강화·적)의 개수 요약."""
    r = entry["report"]
    sc = r["status_counts"]
    tail = f"오류 {len(r['errors'])} · 경고 {len(r['warnings'])}"
    pc = r["provenance_counts"]
    print(f"상태: 제안 {sc['proposed']} · 승인 {sc['approved']} · 삭제 {sc['cut']} · 미지정 {sc['unspecified']}")
    print(f"출처(삭제 제외): 가정 {pc['assumed']} · 계산 {pc['computed']} · 측정 {pc['measured']} · 미지정 {pc['unspecified']}")
    print(f"{entry['label']} {r['count']}개 · {tail}")


def cmd_check(args) -> int:
    missing = _missing(args.paths)
    if missing:
        print("경로를 찾을 수 없습니다: " + ", ".join(missing), file=sys.stderr)
        return 2
    entries = datasets.collect([Path(p) for p in args.paths])
    if not entries:
        print("컨셉·아이템·영구 강화·적 데이터 파일을 찾지 못했습니다.", file=sys.stderr)
        return 2
    unreadable = [d for d in entries if not d["ok"]]
    errors = sum(len(d["report"]["errors"]) for d in entries if d["ok"])
    warnings = sum(len(d["report"]["warnings"]) for d in entries if d["ok"])
    gated = {d["path"]: d["report"]["unverified"] for d in entries
             if d["ok"] and args.fail_on_assumed and d["report"].get("unverified")}
    failed = bool(errors) or (args.strict and bool(warnings)) or bool(gated)
    status = "unreadable" if unreadable else ("fail" if failed else "pass")
    payload = {
        "status": status,
        "fail_on_assumed": args.fail_on_assumed,
        "datasets": [{k: d.get(k) for k in ("path", "kind", "ok", "error", "report") if k in d} for d in entries],
    }
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for d in entries:
            print(f"== {d['path']} ({d.get('label') or '읽기 실패'})")
            if not d["ok"]:
                print(f"error [unreadable] {d['error']}")
                continue
            r = d["report"]
            for e in r["errors"]:
                print(f"error [{e['code']}] {e['where']}: {e['message']}")
            for w in r["warnings"]:
                print(f"warning [{w['code']}] {w['where']}: {w['message']}")
            if d["kind"] in EXTRA_PRINTERS:
                EXTRA_PRINTERS[d["kind"]](r)
            if args.table and d["kind"] in TABLE_PRINTERS:
                print(TABLE_PRINTERS[d["kind"]](d["data"], r))
            if d["path"] in gated:
                print("gate: 출처가 가정이거나 비어 있는 항목: " + ", ".join(gated[d["path"]]))
            if d["kind"] in COUNT_PRINTERS:
                COUNT_PRINTERS[d["kind"]](r)
            else:
                _print_data_counts(d)
        print(f"전체: 파일 {len(entries)}개 · 오류 {errors} · 경고 {warnings}"
              + (f" · 읽기 실패 {len(unreadable)}" if unreadable else "") + f" → {status.upper()}")
    if unreadable:
        return 2
    return 1 if failed else 0


# ---------- simulate ----------
def cmd_simulate(args) -> int:
    try:
        cfg, result = meta_sim.run_config(args.config)
    except meta_sim.ConfigError as exc:
        print(f"설정 오류: {exc}", file=sys.stderr)
        return 2
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.csv:
        Path(args.csv).parent.mkdir(parents=True, exist_ok=True)
        with open(args.csv, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["run", "median_depth", "median_bank", "median_meta_power"])
            w.writeheader()
            w.writerows(result["curve"])
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    print(f"시행 {cfg['trials']} · 최대 런 {cfg['max_runs']} · 구매 정책 {cfg['purchase_policy']} · seed {cfg['seed']}")
    for mid, d in result["milestones"].items():
        print(f"마일스톤 {mid}: {meta_sim.fmt_dist(d)}")
    for uid, d in result["upgrades"].items():
        print(f"강화 {uid}: {meta_sim.fmt_dist(d)}")
    if result["all_upgrades_bought"]:
        print(f"전체 강화 구매: {meta_sim.fmt_dist(result['all_upgrades_bought'])}")
    s = result["longest_stall_runs"]
    print(f"가장 긴 정체(목표가 남은 상태에서 구매도 최고 기록 갱신도 없는 연속 런): 중앙 {s['median']} / p90 {s['p90']} / 최대 {s['max']}")
    print("주의: 추상 모델 결과입니다. 실제 난이도·재미 판정이 아닙니다.")
    if args.out:
        print(f"문서 인용: [계산: {args.out}]")
    return 0


# ---------- provenance ----------
def cmd_provenance(args) -> int:
    try:
        reports = provenance.check_paths_cli(args.paths, args.check_paths)
    except FileNotFoundError as exc:
        print(f"경로를 찾을 수 없습니다: {exc}", file=sys.stderr)
        return 2
    summary = provenance.summarize(reports)
    gate_failed = args.fail_on_assumed and summary["counts"]["assumed"] > 0
    status = "fail" if summary["errors"] or gate_failed else "pass"
    if args.json:
        print(json.dumps({
            "status": status,
            "summary": summary,
            "fail_on_assumed": args.fail_on_assumed,
            "files": [{"path": r.path, "counts": r.counts,
                       "assumed_lines": [t.line for t in r.tags if t.kind == "assumed"],
                       "findings": [asdict(f) for f in r.findings]} for r in reports],
        }, ensure_ascii=False, indent=2))
    else:
        for r in reports:
            for f in r.findings:
                print(f"{r.path}:{f.line}: {f.level}: {f.message}")
            if args.fail_on_assumed:
                for t in r.tags:
                    if t.kind == "assumed":
                        print(f"{r.path}:{t.line}: gate: [가정]이 남아 있습니다.")
        n = summary["counts"]
        print(f"파일 {summary['files']}개 · 가정 {n['assumed']} · 계산 {n['computed']} · 측정 {n['measured']} · 오류 {summary['errors']} → {status.upper()}")
    return 0 if status == "pass" else 1


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="studio.py", description="게임 설계 데이터 공용 도구 (컨셉·아이템·영구 강화·적·수치 출처).")
    sub = ap.add_subparsers(dest="command", required=True, metavar="명령")

    v = sub.add_parser("view", help="데이터를 브라우저에서 봅니다 (읽기 전용, 자동 갱신).")
    v.add_argument("paths", nargs="+", help="프로젝트·데이터 폴더 또는 파일. 폴더는 그 안과 design/·data/를 찾습니다.")
    v.add_argument("--port", type=int, default=8765, help="포트 (기본 8765, 0이면 빈 포트 자동 선택)")
    v.add_argument("--host", default="127.0.0.1", help="기본 127.0.0.1. 다른 기기에 열 때만 바꾸세요.")
    v.add_argument("--no-browser", action="store_true", help="브라우저를 자동으로 열지 않습니다.")
    v.set_defaults(func=cmd_view)

    k = sub.add_parser("check", help="컨셉·아이템·영구 강화·적 데이터를 검사합니다.")
    k.add_argument("paths", nargs="+", help="프로젝트·데이터 폴더 또는 파일")
    k.add_argument("--strict", action="store_true", help="경고도 실패로 처리합니다.")
    k.add_argument("--fail-on-assumed", action="store_true", help="삭제되지 않은 항목 중 출처가 가정이거나 비어 있는 것이 있으면 실패합니다 (확정 판정 전 게이트).")
    k.add_argument("--table", action="store_true", help="컨셉 비교표(마크다운)를 출력합니다. 파일로 저장하지 않습니다.")
    k.add_argument("--json", action="store_true", help="결과를 JSON으로 출력합니다.")
    k.add_argument("--out", help="JSON 보고서를 이 경로에 저장합니다. 문서에서 [계산: 이 경로]로 인용합니다.")
    k.set_defaults(func=cmd_check)

    s = sub.add_parser("simulate", help="로그라이크 메타 성장을 추상 모델로 시뮬레이션합니다.")
    s.add_argument("config", help="모델 설정 JSON (예: data/meta.json)")
    s.add_argument("--out", help="결과 JSON 저장 경로. 문서에서 [계산: 이 경로]로 인용합니다.")
    s.add_argument("--csv", help="런별 중앙값 곡선을 CSV로 저장합니다.")
    s.add_argument("--json", action="store_true", help="결과 JSON을 표준 출력으로 냅니다.")
    s.set_defaults(func=cmd_simulate)

    p = sub.add_parser("provenance", help="기획 문서(md)의 수치 출처 태그를 검사합니다.")
    p.add_argument("paths", nargs="+", help="검사할 .md 파일 또는 폴더")
    p.add_argument("--fail-on-assumed", action="store_true", help="[가정] 태그가 하나라도 남아 있으면 실패합니다.")
    p.add_argument("--check-paths", action="store_true", help="[계산]/[측정] 출처가 경로처럼 보이면 실제 파일 존재를 확인합니다.")
    p.add_argument("--json", action="store_true", help="결과를 JSON으로 출력합니다.")
    p.set_defaults(func=cmd_provenance)
    return ap


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    args = build_parser().parse_args(argv)
    return args.func(args)
