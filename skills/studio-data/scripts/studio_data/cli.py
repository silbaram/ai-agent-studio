"""studio.py의 하위 명령: view / check / simulate / provenance / draft / setup / hook.

종료 코드
  0  통과. check는 미확인 참조가 있으면 최종 줄이 INCOMPLETE다(종료 코드는 0, --strict·--fail-on-assumed면 1).
  1  오류, 또는 --strict 경고, 또는 --fail-on-assumed 가정 항목
  2  사용법 오류(경로 없음, 읽을 수 없는 파일, check할 데이터 없음, provenance할 md 없음, 설정 오류, 서버를 열 수 없음)
     view는 데이터가 아직 없어도 열리고, 파일이 생기면 화면에 자동으로 나타난다.
hook은 Claude Code 훅 규약을 따른다: 0 통과, 2 차단(PreToolUse) 또는 에이전트에게 오류 보이기(PostToolUse).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

from . import budget, claude, combat, concepts, crafting, datasets, economy, enemies, growth, items, meta_sim, playtests, provenance, upgrades, viewer
from . import common as c

EXTRA_PRINTERS = {"items": items.print_extra, "upgrades": upgrades.print_extra, "enemies": enemies.print_extra,
                  "combat": combat.print_extra, "budget": budget.print_extra, "crafting": crafting.print_extra,
                  "economy": economy.print_extra, "growth": growth.print_extra, "playtests": playtests.print_extra}
TABLE_PRINTERS = {"concepts": concepts.table, "combat": combat.table, "budget": budget.table, "crafting": crafting.table,
                  "economy": economy.table, "growth": growth.table}
COUNT_PRINTERS = {"concepts": concepts.print_counts, "combat": combat.print_counts, "budget": budget.print_counts,
                  "crafting": crafting.print_counts, "economy": economy.print_counts, "growth": growth.print_counts,
                  "playtests": playtests.print_counts}
GATE_LABELS = {"playtests": "판정이 확정되지 않은 가설(버팀·틀림 확정이 아님): "}


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
    try:
        server = viewer.make_server(targets, args.host, args.port)
    except OSError as exc:
        print(f"서버를 열 수 없습니다 ({args.host}:{args.port}): {exc}. --port로 다른 포트를 지정하세요.", file=sys.stderr)
        return 2
    if args.host not in ("127.0.0.1", "localhost"):
        print(f"주의: {args.host}에 열었습니다. 같은 네트워크의 다른 기기에서 접속할 수 있습니다.")
    print(f"데이터 뷰어: {viewer.url_of(server)}", flush=True)  # 백그라운드로 띄운 쪽이 주소를 바로 읽게 한다(--port 0이면 출력이 유일한 단서)
    if found:
        for f in found:
            print(f"  - {f}")
        print("파일을 고치면 화면이 자동으로 갱신됩니다. 종료: Ctrl+C")
    else:
        print("아직 데이터 파일이 없습니다. 지켜보는 위치:")
        for w in viewer.watched_folders(targets):
            print(f"  - {w}")
        print("design/concepts.json, data/items.json 같은 파일이 생기면 화면에 자동으로 나타납니다. 종료: Ctrl+C")
    sys.stdout.flush()
    viewer.serve(server, open_browser=not args.no_browser)
    return 0


# ---------- check ----------
def _print_data_counts(entry: dict) -> None:
    """출처 필드가 있는 데이터(아이템·영구 강화·적)의 개수 요약."""
    r = entry["report"]
    sc = r["status_counts"]
    tail = f"오류 {len(r['errors'])} · 경고 {len(r['warnings'])}"
    if r.get("acknowledged"):
        tail += f" · 확인한 경고 {len(r['acknowledged'])}"
    pc = r["provenance_counts"]
    print(f"상태: 제안 {sc['proposed']} · 승인 {sc['approved']} · 삭제 {sc['cut']} · 미지정 {sc['unspecified']}")
    print(f"출처(삭제 제외): 가정 {pc['assumed']} · 계산 {pc['computed']} · 측정 {pc['measured']} · 미지정 {pc['unspecified']}")
    print(f"{entry['label']} {r['count']}개 · {tail}")


def _table_kinds(args) -> set | None:
    """--table의 종류 목록. 값 없이 쓰면 모든 표(None). 모르는 종류면 ValueError.
    `check --table .`처럼 플래그를 경로 앞에 쓰면 argparse가 경로를 종류로 읽는다. 종류가 아니고 있는 경로면 경로로 돌려놓는다."""
    raw = args.table
    if raw is None or raw == "all":
        return None
    kinds = {k.strip() for k in raw.split(",") if k.strip()}
    unknown = sorted(kinds - set(TABLE_PRINTERS))
    if unknown and Path(raw).exists():
        args.paths.insert(0, raw)
        return None
    if unknown:
        hint = "".join(c.did_you_mean(k, TABLE_PRINTERS) for k in unknown)
        raise ValueError(f"--table에 모르는 종류: {', '.join(unknown)}.{hint} 표가 있는 종류: {', '.join(TABLE_PRINTERS)}. "
                         "검사할 경로는 --table 앞에 적습니다.")
    return kinds


def cmd_check(args) -> int:
    try:
        table_kinds = _table_kinds(args)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if not args.paths:
        print("검사할 프로젝트·데이터 폴더나 파일을 적으세요 (예: check . --table).", file=sys.stderr)
        return 2
    missing = _missing(args.paths)
    if missing:
        print("경로를 찾을 수 없습니다: " + ", ".join(missing), file=sys.stderr)
        return 2
    entries = datasets.collect([Path(p) for p in args.paths])
    if not entries:
        print("컨셉·아이템·영구 강화·적·전투 계산·판 안 성장·스탯 예산·강화·합성·재화 흐름·플레이 기록 데이터 파일을 찾지 못했습니다.", file=sys.stderr)
        return 2
    unreadable = [d for d in entries if not d["ok"]]
    reports = [d["report"] for d in entries if d["ok"]]
    errors = sum(len(r["errors"]) for r in reports)
    warnings = sum(len(r["warnings"]) for r in reports)
    acknowledged = sum(len(r.get("acknowledged", [])) for r in reports)
    unchecked = sum(r.get("unchecked", 0) for r in reports)
    gated = {d["path"]: d["report"]["unverified"] for d in entries
             if d["ok"] and args.fail_on_assumed and d["report"].get("unverified")}
    failed = (bool(errors) or (args.strict and bool(warnings)) or bool(gated)
              or ((args.strict or args.fail_on_assumed) and bool(unchecked)))
    # 미확인이 남으면 통과(PASS)로 쓰지 않는다. 검사하지 못한 것을 통과로 옮겨 적지 않게 한다.
    status = "unreadable" if unreadable else ("fail" if failed else ("incomplete" if unchecked else "pass"))
    ids = [s.strip() for s in args.ids.split(",") if s.strip()] if args.ids else None
    payload = {
        "status": status,
        "fail_on_assumed": args.fail_on_assumed,
        "unchecked": unchecked,
        "acknowledged": acknowledged,
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
            for a in r.get("acknowledged", []):
                print(f"확인한 경고 [{a['code']}] {a['where']}: {a['reason']}")
            if d["kind"] in EXTRA_PRINTERS:
                EXTRA_PRINTERS[d["kind"]](r)
            if args.table and d["kind"] in TABLE_PRINTERS and (table_kinds is None or d["kind"] in table_kinds):
                print(TABLE_PRINTERS[d["kind"]](d["data"], r, ids))
            if d["path"] in gated:
                print("gate: " + GATE_LABELS.get(d["kind"], "출처가 가정이거나 비어 있는 항목: ") + ", ".join(gated[d["path"]]))
            if d["kind"] in COUNT_PRINTERS:
                COUNT_PRINTERS[d["kind"]](r)
            else:
                _print_data_counts(d)
        print(f"전체: 파일 {len(entries)}개 · 오류 {errors} · 경고 {warnings}"
              + (f" · 확인한 경고 {acknowledged}" if acknowledged else "")
              + (f" · 미확인 {unchecked}" if unchecked else "")
              + (f" · 읽기 실패 {len(unreadable)}" if unreadable else "") + f" → {status.upper()}")
        if unchecked and not unreadable:
            print("미확인 항목이 있어 통과로 보고하지 않습니다. 함께 검사할 데이터를 넘기거나 읽기 오류를 고치세요.")
    if unreadable:
        return 2
    return 1 if failed else 0


# ---------- simulate ----------
def _write_curve_csv(path: str, rows: list[dict], with_policy: bool) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    # 추상 모델은 메타 힘(median_meta_power), 전투 계산 모델은 산 강화 수(median_upgrades_owned)
    fields = list(rows[0]) if rows else (["policy"] if with_policy else []) + ["run", "median_depth", "median_bank"]
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def _compare_policies(args) -> int:
    """같은 설정 파일로 구매 정책만 바꿔 돌려 나란히 보여 준다. 파일을 복사하거나 고치지 않는다."""
    results = {}
    try:
        cfg = meta_sim.load_config(args.config)  # 정책 목록만 정한다(시뮬레이션은 정책마다 한 번)
        policies = meta_sim.POLICIES + ((meta_sim.ECONOMY_POLICY,) if "economy" in cfg else ())  # 재화 흐름 연결이 있으면 그 계획 순서도
        for policy in policies:
            cfg, results[policy] = meta_sim.run_config(args.config, policy)
    except meta_sim.ConfigError as exc:
        print(f"설정 오류: {exc}", file=sys.stderr)
        return 2
    payload = {"compare_policies": list(policies), "results": results}
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.csv:
        _write_curve_csv(args.csv, [{"policy": p, **row} for p, r in results.items() for row in r["curve"]], True)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    width = max(len(p) for p in results)
    print(f"구매 정책 비교 · {_model_label(cfg)} · 시행 {cfg['trials']} · 최대 런 {cfg['max_runs']} · seed {cfg['seed']} (설정 파일은 그대로, 정책만 바꿈)")
    first = results[meta_sim.POLICIES[0]]
    sections = [(f"마일스톤 {mid}", lambda r, mid=mid: r["milestones"][mid]) for mid in first["milestones"]]
    sections += [(f"강화 {uid}", lambda r, uid=uid: r["upgrades"][uid]) for uid in first["upgrades"]]
    if first["all_upgrades_bought"]:
        sections.append(("전체 강화 구매", lambda r: r["all_upgrades_bought"]))
    for title, pick in sections:
        print(title)
        for policy, r in results.items():
            print(f"  {policy:<{width}}  {meta_sim.fmt_dist(pick(r))}")
    print("가장 긴 정체(연속 런)")
    for policy, r in results.items():
        s = r["longest_stall_runs"]
        print(f"  {policy:<{width}}  중앙 {s['median']} / p90 {s['p90']} / 최대 {s['max']}")
    print("정책에 따라 결론이 다르면 그 자체를 발견으로 보고합니다. 한쪽만 골라 보고하지 않습니다.")
    print(_caution(cfg))
    if args.out:
        print(f"문서 인용: [계산: {args.out}]")
    return 0


def _model_label(cfg: dict) -> str:
    return f"전투 계산 모델({Path(cfg['combat_file']).name})" if cfg["model"] == "combat" else "추상 모델"


def _caution(cfg: dict) -> str:
    if cfg["model"] == "combat":
        return ("주의: 전투 계산의 기대값과 생존 곡선 가정(slope·even_margin·skill)에서 나온 결과입니다. "
                "실제 난이도·재미 판정이 아닙니다. 플레이 기록으로 보정하기 전에는 가정입니다.")
    return "주의: 추상 모델 결과입니다. 실제 난이도·재미 판정이 아닙니다."


def _print_combat_overview(result: dict) -> None:
    for s in result["survival_by_stage"]:
        f = lambda m: "피해를 받지 않음" if m is None else f"{m:g}배"  # noqa: E731
        rank = combat.RANK_LABEL.get(s["rank"], s["rank"] or "등급 없음")
        growth = (f"여유 {f(s['margin_growth'])} → 통과 {s['p_growth']:.0%} (강화 없이 판 안 성장 평균: 첫 판) · "
                  if result.get("growth_build") else "")
        print(f"단계 {s['stage']} (정하는 적 {s['decided_by']}, {rank}): 여유 {f(s['margin_none'])} → 통과 {s['p_none']:.0%} (강화·성장 없음) · "
              f"{growth}여유 {f(s['margin_all'])} → 통과 {s['p_all']:.0%} (계획한 강화 모두 + 판 안 성장 평균) · 재화 {result['stage_income'][s['stage']]:g}")
    if result["upgrades_without_combat_effect"]:
        print("전투 계산에 효과가 없는 강화(전투 역할에 연결된 스탯이 없음): " + ", ".join(result["upgrades_without_combat_effect"]))


def cmd_simulate(args) -> int:
    if args.compare_policies:
        return _compare_policies(args)
    try:
        cfg, result = meta_sim.run_config(args.config, args.policy)
    except meta_sim.ConfigError as exc:
        print(f"설정 오류: {exc}", file=sys.stderr)
        return 2
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.csv:
        _write_curve_csv(args.csv, result["curve"], False)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    override = " (--policy로 바꿈)" if args.policy else ""
    print(f"{_model_label(cfg)} · 시행 {cfg['trials']} · 최대 런 {cfg['max_runs']} · 구매 정책 {cfg['purchase_policy']}{override} · seed {cfg['seed']}"
          + (f" · 판 안 성장 빌드 {cfg['build']}" if cfg.get("build") else ""))
    if cfg["model"] == "combat":
        _print_combat_overview(result)
    for mid, d in result["milestones"].items():
        print(f"마일스톤 {mid}: {meta_sim.fmt_dist(d)}")
    plan = set(meta_sim.targets(cfg))
    for uid, d in result["upgrades"].items():
        print(f"강화 {uid}: " + (meta_sim.fmt_dist(d) if uid in plan else "구매 계획에 없음(사지 않음)"))
    if result["all_upgrades_bought"]:
        label = "계획한 강화 모두 구매" if cfg["purchase_policy"] == meta_sim.ECONOMY_POLICY else "전체 강화 구매"
        print(f"{label}: {meta_sim.fmt_dist(result['all_upgrades_bought'])}")
    s = result["longest_stall_runs"]
    print(f"가장 긴 정체(목표가 남은 상태에서 구매도 최고 기록 갱신도 없는 연속 런): 중앙 {s['median']} / p90 {s['p90']} / 최대 {s['max']}")
    print(_caution(cfg))
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
    if not reports:
        if args.json:
            print(json.dumps({"status": "no_files", "paths": args.paths}, ensure_ascii=False, indent=2))
        print("검사할 md 파일을 찾지 못했습니다: " + ", ".join(args.paths)
              + ". 아무것도 검사하지 않았으므로 통과가 아닙니다. 경로를 확인하세요.", file=sys.stderr)
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
        print(f"파일 {summary['files']}개 · 가정 {n['assumed']} · 계산 {n['computed']} · 측정 {n['measured']} · 오류 {summary['errors']}"
              + (f" · 경고 {summary['warnings']}" if summary["warnings"] else "") + f" → {status.upper()}")
    return 0 if status == "pass" else 1


# ---------- draft ----------
def _value(raw: str):
    """--set 값: 정수·실수, true/false/null은 JSON 값, 나머지는 문자열."""
    if raw in ("true", "false", "null"):
        return json.loads(raw)
    for cast in (int, float):
        try:
            return cast(raw)
        except ValueError:
            pass
    return raw


def cmd_draft(args) -> int:
    path = Path(args.path)
    if not path.exists():
        print(f"경로를 찾을 수 없습니다: {path}", file=sys.stderr)
        return 2
    found = [d for d in datasets.scan([path]) if d["ok"] and d["kind"] == "budget"]
    if not found:
        print("스탯 예산 데이터(data/budget.json, 최상위 budget 객체)를 찾지 못했습니다.", file=sys.stderr)
        return 2
    fields = {}
    for pair in args.set or []:
        key, sep, raw = pair.partition("=")
        if not sep or not key.strip():
            print(f"--set은 필드=값 형식입니다: {pair}", file=sys.stderr)
            return 2
        fields[key.strip()] = _value(raw.strip())
    # 초안이 들어갈 원본의 id와 겹치지 않게 한다. 폴더를 넘기면 그 안의 아이템·적 데이터를 본다
    side = next((a.get("for") for a in found[0]["data"].get("archetypes") or [] if isinstance(a, dict) and a.get("id") == args.archetype), None)
    existing = {e["id"] for d in datasets.scan([path]) if d["ok"] and d["kind"] == side and isinstance(d["data"].get(side), list)
                for e in d["data"][side] if isinstance(e, dict) and isinstance(e.get("id"), str)}
    try:
        entry, info = budget.draft(found[0]["data"], args.archetype, args.at, args.id, fields, existing=existing)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f"# {found[0]['name']} · 원형 {args.archetype} · 기대 예산 {info['expected']:g} (곡선 {info['curve']:g} × 배수 {info['multiplier']:g})."
          " 파일에 쓰지 않았습니다. 제안 상태로 원본에 넣고 check로 확인하세요.")
    print(json.dumps(entry, ensure_ascii=False, indent=2))
    return 0


# ---------- setup / hook (Claude Code) ----------
def cmd_setup(args) -> int:
    project = Path(args.project)
    if not project.is_dir():
        print(f"게임 프로젝트 폴더를 찾을 수 없습니다: {project}", file=sys.stderr)
        return 2
    code, lines = claude.setup(project.resolve(), args.python)
    for line in lines:
        print(line, file=sys.stderr if code else sys.stdout)
    return code


def cmd_hook(args) -> int:
    payload = sys.stdin.buffer.read().decode("utf-8", errors="replace") if hasattr(sys.stdin, "buffer") else sys.stdin.read()
    if args.event == "judge-guard":
        code, message = claude.judge_guard(payload)
        out, err = "", message
    else:
        code, out, err = claude.post_edit(payload)
    if out:
        sys.stdout.write(out)
    if err:
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
        sys.stderr.write(err if err.endswith("\n") else err + "\n")
    return code


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="studio.py", description="게임 설계 데이터 공용 도구 (컨셉·아이템·영구 강화·적·수치 출처).")
    sub = ap.add_subparsers(dest="command", required=True, metavar="명령")

    v = sub.add_parser("view", help="데이터를 브라우저에서 봅니다 (읽기 전용, 자동 갱신).")
    v.add_argument("paths", nargs="+", help="프로젝트·데이터 폴더 또는 파일. 폴더는 그 안과 design/·data/를 찾습니다.")
    v.add_argument("--port", type=int, default=8765, help="포트 (기본 8765, 0이면 빈 포트 자동 선택)")
    v.add_argument("--host", default="127.0.0.1", help="기본 127.0.0.1. 다른 기기에 열 때만 바꾸세요.")
    v.add_argument("--no-browser", action="store_true", help="브라우저를 자동으로 열지 않습니다.")
    v.set_defaults(func=cmd_view)

    k = sub.add_parser("check", help="컨셉·아이템·영구 강화·적·전투 계산·판 안 성장·스탯 예산·강화·합성·재화 흐름·플레이 기록 데이터를 검사합니다.")
    k.add_argument("paths", nargs="*", help="프로젝트·데이터 폴더 또는 파일 (하나 이상)")
    k.add_argument("--strict", action="store_true", help="경고도 실패로 처리합니다.")
    k.add_argument("--fail-on-assumed", action="store_true", help="삭제되지 않은 항목 중 출처가 가정이거나 비어 있는 것, 판정이 확정되지 않은 가설이 있으면 실패합니다 (확정 판정 전 게이트).")
    k.add_argument("--table", nargs="?", const="all", metavar="종류,...",
                   help="컨셉 비교표, 전투 계산표, 빌드 비교표, 예산 비교표, 강화·합성 표, 재화 흐름 표(마크다운)를 출력합니다. "
                        "종류를 쉼표로 고를 수 있습니다(예: --table combat,growth). 파일로 저장하지 않습니다.")
    k.add_argument("--ids", help="--table에 보일 컨셉 id만 쉼표로 고릅니다 (예: a,b,c). 적은 순서대로 보입니다.")
    k.add_argument("--json", action="store_true", help="결과를 JSON으로 출력합니다.")
    k.add_argument("--out", help="JSON 보고서를 이 경로에 저장합니다. 문서에서 [계산: 이 경로]로 인용합니다.")
    k.set_defaults(func=cmd_check)

    s = sub.add_parser("simulate", help="로그라이크 메타 성장을 추상 모델로 시뮬레이션합니다.")
    s.add_argument("config", help="모델 설정 JSON (예: data/meta.json)")
    s.add_argument("--out", help="결과 JSON 저장 경로. 문서에서 [계산: 이 경로]로 인용합니다.")
    s.add_argument("--csv", help="런별 중앙값 곡선을 CSV로 저장합니다.")
    s.add_argument("--json", action="store_true", help="결과 JSON을 표준 출력으로 냅니다.")
    pol = s.add_mutually_exclusive_group()
    pol.add_argument("--policy", choices=meta_sim.ALL_POLICIES,
                     help="설정 파일을 고치지 않고 구매 정책만 바꿔 실행합니다. economy는 재화 흐름의 구매 계획 순서(economy 연결이 있을 때).")
    pol.add_argument("--compare-policies", action="store_true", help="모든 구매 정책으로 돌려 나란히 보여 줍니다. --out에는 정책별 결과를 함께 저장합니다.")
    s.set_defaults(func=cmd_simulate)

    p = sub.add_parser("provenance", help="기획 문서(md)의 수치 출처 태그를 검사합니다.")
    p.add_argument("paths", nargs="+", help="검사할 .md 파일 또는 폴더")
    p.add_argument("--fail-on-assumed", action="store_true", help="[가정] 태그가 하나라도 남아 있으면 실패합니다.")
    p.add_argument("--check-paths", action="store_true", help="[계산]/[측정] 출처가 경로처럼 보이면 실제 파일 존재를 확인합니다.")
    p.add_argument("--json", action="store_true", help="결과를 JSON으로 출력합니다.")
    p.set_defaults(func=cmd_provenance)

    d = sub.add_parser("draft", help="스탯 예산의 곡선과 원형으로 아이템·적 초안 하나를 만듭니다 (파일에 쓰지 않음).")
    d.add_argument("path", help="게임 프로젝트 폴더 또는 budget.json")
    d.add_argument("--archetype", required=True, help="원형 id (budget.json의 archetypes)")
    d.add_argument("--at", type=float, required=True, help="곡선 기준 값 (예: 티어 3, 구역 2)")
    d.add_argument("--id", help="초안 항목 id (기본: 원형_기준값)")
    d.add_argument("--set", action="append", metavar="필드=값", help="초안에 넣을 필드. 배수 필드(예: rank=elite)도 여기서 정합니다. 여러 번 쓸 수 있습니다.")
    d.set_defaults(func=cmd_draft)

    u = sub.add_parser("setup", help="게임 프로젝트에 판정 에이전트와 훅을 설치합니다 (Claude Code).")
    u.add_argument("host", choices=("claude",), help="연결할 호스트. 지금은 claude(Claude Code)만 지원합니다.")
    u.add_argument("project", nargs="?", default=".", help="게임 프로젝트 폴더 (기본: 현재 폴더)")
    u.add_argument("--python", default="py" if os.name == "nt" else "python3", help="훅이 쓸 파이썬 실행 이름 (기본: Windows py, 그 밖 python3)")
    u.set_defaults(func=cmd_setup)

    h = sub.add_parser("hook", help="Claude Code 훅 처리기. setup이 settings.json에 등록하며 직접 실행하지 않습니다.")
    h.add_argument("event", choices=("post-edit", "judge-guard"))
    h.set_defaults(func=cmd_hook)
    return ap


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    args = build_parser().parse_args(argv)
    return args.func(args)
