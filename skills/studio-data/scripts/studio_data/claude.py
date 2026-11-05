"""Claude Code 연결: setup(판정 에이전트·훅 설치)과 hook(훅 처리기).

setup은 게임 프로젝트의 .claude/agents/studio-judge.md를 쓰고 .claude/settings.json의 hooks에 세 훅을 합쳐 넣는다.
  - PostToolUse: design/·data/ 아래 파일을 고치면 check(데이터) 또는 provenance(md)를 돌려 결과를 에이전트에게 보인다.
  - PreToolUse: 판정 에이전트(studio-judge)가 파일을 쓰거나 check·provenance 밖의 명령을 실행하면 막는다.
  - PreToolUse: 범위를 벗어난 OpenSpec 변경이 있으면 만드는 파일의 편집과 보관을 막고, 범위를 넓히는 설계 편집은 사용자에게 묻는다.
훅 입력 형식은 Claude Code 문서(hooks)를 따른다. 사용자 훅과 다른 설정은 그대로 둔다.
"""
from __future__ import annotations

import io
import json
import os
import re
import shlex
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from . import common as c
from . import datasets, scope

JUDGE = "studio-judge"
MARKER = "<!-- studio-data setup이 만든 파일. 고치려면 스킬 저장소의 assets/claude/studio-judge.md를 고치고 setup을 다시 실행한다. -->"
TEMPLATE = Path(__file__).resolve().parents[2] / "assets/claude/studio-judge.md"
SCRIPT = Path(__file__).resolve().parents[1] / "studio.py"
WRITE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
JUDGE_COMMANDS = ("check", "provenance")
PYTHON = re.compile(r"^(python(3(\.\d+)?)?|py)(\.exe)?$", re.IGNORECASE)
SHELL_META = re.compile(r"[;&|<>`$\n\r]")
WATCHED = ("design", "data")
PLANNING = ("design", "data", "docs", "reports")  # 무엇을 만들지 적는 곳. 나머지는 게임을 만드는 파일로 본다
ARCHIVE = re.compile(r"openspec[^\s;&|]*(?:\s+-\S+)*\s+archive\b"  # openspec archive. npx와 판 지정, 앞의 옵션을 포함한다
                     r"|\b(?:mv|move|Move-Item)\s[^;&|\n]*(?:openspec[/\\]+changes[/\\]|archive[/\\])")  # /opsx:archive는 CLI 대신 폴더를 옮긴다
GUARDED = "|".join(WRITE_TOOLS + ("Bash",))
HOOKS = (("PostToolUse", "Write|Edit|MultiEdit", "post-edit"), ("PreToolUse", GUARDED, "judge-guard"), ("PreToolUse", GUARDED, "scope-guard"))


# ---------- setup ----------
def script_reference(project: Path, script: Path = SCRIPT) -> str:
    """훅 명령에 넣을 studio.py 경로. 프로젝트 안의 설치본이면 $CLAUDE_PROJECT_DIR 기준으로 쓴다."""
    try:
        rel = script.resolve().relative_to(project.resolve())
        return f'"$CLAUDE_PROJECT_DIR/{rel.as_posix()}"'
    except ValueError:
        return f'"{script.resolve().as_posix()}"'


def _is_ours(hook) -> bool:
    cmd = hook.get("command", "") if isinstance(hook, dict) else ""
    return "studio.py" in cmd and any(f" hook {name}" in cmd for _, _, name in HOOKS)


def merge_hooks(settings: dict, python: str, script_ref: str) -> dict:
    """이 도구가 넣은 훅만 지우고 다시 넣는다. 같은 묶음에 있던 다른 훅과 다른 설정 키는 남긴다."""
    hooks = settings.setdefault("hooks", {})
    for event in dict.fromkeys(event for event, _, _ in HOOKS):
        groups = []
        for g in hooks.get(event, []):
            if isinstance(g, dict) and isinstance(g.get("hooks"), list):
                kept = [h for h in g["hooks"] if not _is_ours(h)]
                if kept:
                    groups.append({**g, "hooks": kept})
            else:
                groups.append(g)
        groups += [{"matcher": matcher, "hooks": [{"type": "command", "command": f"{python} {script_ref} hook {name}"}]} for e, matcher, name in HOOKS if e == event]
        hooks[event] = groups
    return settings


def setup(project: Path, python: str) -> tuple[int, list[str]]:
    """(종료 코드, 출력 줄). 실패하면 아무 파일도 쓰지 않는다."""
    settings_path = project / ".claude/settings.json"
    agent_path = project / ".claude/agents" / f"{JUDGE}.md"
    settings: dict = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return 2, [f"{c.josa(settings_path, '을를')} 읽지 못했습니다 ({exc}). 형식을 고친 뒤 다시 실행하세요. 아무것도 바꾸지 않았습니다."]
        if not isinstance(settings, dict) or not isinstance(settings.get("hooks", {}), dict):
            return 2, [f"{settings_path}의 최상위나 hooks가 객체가 아닙니다. 아무것도 바꾸지 않았습니다."]
    if agent_path.exists() and MARKER not in agent_path.read_text(encoding="utf-8"):
        return 2, [f"{c.josa(agent_path, '이가')} 이미 있고 setup이 만든 파일이 아닙니다. 덮어쓰지 않았습니다. 옮기거나 지운 뒤 다시 실행하세요."]
    template = TEMPLATE.read_text(encoding="utf-8")
    script_ref = script_reference(project)
    merge_hooks(settings, python, script_ref)
    agent_path.parent.mkdir(parents=True, exist_ok=True)
    agent_path.write_text(template.rstrip("\n") + "\n\n" + MARKER + "\n", encoding="utf-8")
    settings_path.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0, [f"판정 에이전트: {agent_path}",
               f"훅: {settings_path} (PostToolUse 데이터 검사, PreToolUse 판정 에이전트 쓰기 차단과 범위 이탈 차단)",
               f"훅 명령: {python} {script_ref} hook …",
               "Claude Code를 다시 시작하거나 /hooks에서 확인하면 적용됩니다. 스킬을 다시 설치한 뒤에는 setup도 다시 실행합니다."]


# ---------- hook: judge-guard ----------
def _allowed_command(command: str) -> bool:
    """판정 에이전트가 실행할 수 있는 명령: python studio.py check|provenance (파일을 쓰는 --out 제외, 셸 연결 없음)."""
    if SHELL_META.search(command):
        return False
    try:
        tokens = shlex.split(command.replace("\\", "/"))
    except ValueError:
        return False
    if len(tokens) < 3 or not PYTHON.match(Path(tokens[0]).name) or not tokens[1].endswith("studio.py"):
        return False
    # argparse는 줄인 옵션(--ou)도 받으므로 --o로 시작하는 것은 모두 막는다.
    return tokens[2] in JUDGE_COMMANDS and not any(t.startswith("--o") for t in tokens[3:])


def judge_guard(payload_text: str) -> tuple[int, str]:
    """(종료 코드, 에이전트에게 보일 메시지). 2면 도구 호출을 막는다. 판정 에이전트가 아니면 관여하지 않는다."""
    try:
        payload = json.loads(payload_text)
    except ValueError:
        return 0, ""
    if not isinstance(payload, dict) or payload.get("agent_type") != JUDGE:
        return 0, ""
    tool = payload.get("tool_name")
    if tool in WRITE_TOOLS:
        return 2, f"판정 에이전트는 파일을 고치지 않습니다({tool} 차단). 판정 제안은 보고로 돌려주고, 기록은 메인 에이전트가 사용자 확인을 받아 남깁니다."
    if tool == "Bash":
        command = (payload.get("tool_input") or {}).get("command", "")
        if not (isinstance(command, str) and _allowed_command(command)):
            return 2, ("판정 에이전트는 studio.py check / provenance만 실행합니다(--out 제외, 셸 연결 없음). "
                       "파일은 Read·Grep·Glob으로 읽습니다.")
    return 0, ""


# ---------- 훅 입력 ----------
def _payload(text: str) -> dict | None:
    """훅 입력. 읽지 못하면 None이고 세션을 멈추지 않는다."""
    try:
        payload = json.loads(text)
    except ValueError:
        return None
    tool_input = (payload.get("tool_input") or {}) if isinstance(payload, dict) else None
    return {**payload, "tool_input": tool_input} if isinstance(tool_input, dict) else None


def _project(payload: dict, project: Path | None) -> Path:
    return Path(project or os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or ".").resolve()


def _target(payload: dict, project: Path) -> tuple[Path, Path] | None:
    """편집 대상의 (절대 경로, 프로젝트 기준 경로). 대상이 없거나 프로젝트 밖이면 None."""
    target = payload["tool_input"].get("file_path") or payload["tool_input"].get("notebook_path")
    if not isinstance(target, str) or not target:
        return None
    path = Path(target)
    path = (path if path.is_absolute() else project / path).resolve()
    try:
        rel = path.relative_to(project)
    except ValueError:
        return None
    return (path, rel) if rel.parts else None


# ---------- hook: scope-guard ----------
def _builds_game(rel: Path) -> bool:
    """게임을 만드는 파일인가. 메인 스펙은 보관의 결과이고, 그 밖의 계획 파일은 변경을 고칠 수 있게 열어 둔다."""
    if rel.parts[:2] == ("openspec", "specs"):
        return True
    return rel.parts[0] not in PLANNING and rel.parts[0] != "openspec" and not rel.parts[0].startswith(".") and rel.suffix.lower() != ".md"


def _gate(project: Path) -> tuple[int, str, str]:
    try:
        errors = scope.check(project)["errors"]
    except Exception as exc:  # 훅이 죽어도 Claude Code는 막지 않는다. 재지 못한 것을 통과시키지 않는다
        return 2, "", f"범위를 재지 못해 막았습니다: {exc!r}. studio.py scope로 원인을 봅니다.\n"
    if not errors:
        return 0, "", ""
    lines = "\n".join(f"[{e['code']}] {e['where']}: {e['message']}" for e in errors)
    return 2, "", f"범위를 벗어난 변경이 있어 막았습니다.\n{lines}\n변경을 고친 뒤 studio.py scope로 확인합니다. 시스템은 studio.py scope --link로 잇습니다. 범위를 바꾸는 일은 사용자에게 묻습니다.\n"


def _edited_text(path: Path, tool: str, tool_input: dict) -> str | None:
    """편집이 끝난 뒤의 글. 알 수 없으면 None이고, 그 편집은 도구와 check 훅에 맡긴다."""
    if tool == "Write":
        content = tool_input.get("content")
        return content if isinstance(content, str) else None
    text = path.read_text(encoding="utf-8-sig")
    edits = tool_input.get("edits") if tool == "MultiEdit" else [tool_input]
    for edit in edits if isinstance(edits, list) else [None]:
        old, new = (edit.get("old_string"), edit.get("new_string")) if isinstance(edit, dict) else (None, None)
        if not (isinstance(old, str) and isinstance(new, str)):
            return None
        text = text.replace(old, new) if edit.get("replace_all") else text.replace(old, new, 1)
    return text


def _sets_scope(rel: Path) -> bool:
    """범위를 정하는 파일인가. 컨셉은 check가 찾는 자리면 어디든, 시스템 설계는 design/에만 둔다."""
    name, parent = rel.name.lower(), rel.parent.as_posix()
    return (name == "systems.json" and parent == "design") or (name == "concepts.json" and parent in (".", *c.SUBFOLDERS))


def _ask_if_widened(project: Path, path: Path, tool: str, tool_input: dict) -> tuple[int, str, str]:
    """범위를 정하는 파일의 편집. 처음 쓰는 파일은 읽히지 않고, 넓힐 것도 없다."""
    try:
        after_text = _edited_text(path, tool, tool_input)
        if after_text is None:
            return 0, "", ""
        before, after = json.loads(path.read_text(encoding="utf-8-sig")), json.loads(after_text)
    except (OSError, ValueError):
        return 0, "", ""
    found = scope.widened(path.stem.lower(), before, after, scope.concept_in_use(project)) if isinstance(before, dict) and isinstance(after, dict) else []
    if not found:
        return 0, "", ""
    reason = "범위를 넓히는 편집입니다. 사용자가 정할 일입니다: " + "; ".join(found)
    return 0, json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask", "permissionDecisionReason": reason}}), ""


def scope_guard(payload_text: str, project: Path | None = None) -> tuple[int, str, str]:
    """(종료 코드, 표준 출력, 표준 오류). OpenSpec과 시스템 설계가 다 있는 프로젝트에서만 관여한다."""
    payload = _payload(payload_text)
    if payload is None:
        return 0, "", ""
    project = _project(payload, project)
    if scope.missing(project):
        return 0, "", ""
    tool, tool_input = payload.get("tool_name"), payload["tool_input"]
    if tool == "Bash":
        command = tool_input.get("command")
        return _gate(project) if isinstance(command, str) and ARCHIVE.search(command) else (0, "", "")
    target = _target(payload, project) if tool in WRITE_TOOLS else None
    if target is None:
        return 0, "", ""
    path, rel = target
    if _sets_scope(rel):
        return _ask_if_widened(project, path, tool, tool_input)
    return _gate(project) if _builds_game(rel) else (0, "", "")


# ---------- hook: post-edit ----------
def _run(argv: list[str]) -> tuple[int, str]:
    from . import cli  # cli가 이 모듈을 불러오므로 순환을 피해 여기서 불러온다

    out = io.StringIO()
    with redirect_stdout(out), redirect_stderr(io.StringIO()):
        code = cli.main(argv)
    return code, out.getvalue()


def _check_lines(payload: dict) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    for d in payload.get("datasets", []):
        name = Path(d["path"]).name
        if not d.get("ok"):
            errors.append(f"{name}: [unreadable] {d.get('error')}")
            continue
        r = d.get("report") or {}
        errors += [f"{name}: [{e['code']}] {e['where']}: {e['message']}" for e in r.get("errors", [])]
        warnings += [f"{name}: [{w['code']}] {w['where']}: {w['message']}" for w in r.get("warnings", [])]
    if payload.get("unchecked"):
        warnings.append(f"미확인 참조 {payload['unchecked']}건: 함께 검사할 데이터가 없거나 읽지 못했습니다(INCOMPLETE).")
    return errors, warnings


def post_edit(payload_text: str, project: Path | None = None) -> tuple[int, str, str]:
    """(종료 코드, 표준 출력, 표준 오류). 오류는 2와 표준 오류로, 경고는 additionalContext로 에이전트에게 보인다."""
    payload = _payload(payload_text)
    if payload is None:
        return 0, "", ""
    project = _project(payload, project)
    target = _target(payload, project)
    if target is None:
        return 0, "", ""
    path, rel = target
    at_root = len(rel.parts) == 1 and path.suffix.lower() == ".json" and path.stem.lower() in c.FOREIGN_NAMES  # check는 프로젝트 바로 아래의 levels.json도 읽는다
    if (rel.parts[0] not in WATCHED and not at_root) or not path.is_file():
        return 0, "", ""
    notes: list = []
    suffix = path.suffix.lower()
    if suffix in (".json", ".csv"):
        code, out = _run(["check", str(project), "--json"])
        try:
            result = json.loads(out)
        except ValueError:
            return 0, "", ""  # 검사할 데이터가 없다(예: 시뮬레이터 설정만 고침)
        errors, warnings = _check_lines(result)
        # 건너뛴 파일이 게임 자기 파일일 수 있어 그 파일을 고칠 때만 알린다. 다른 편집마다 되풀이하지 않는다
        notes = [datasets.skipped_note(rel.as_posix()) for p in result.get("skipped", []) if Path(p).resolve() == path]
        title = "studio.py check"
    elif suffix == ".md":
        code, out = _run(["provenance", str(path), "--json"])
        try:
            result = json.loads(out)
        except ValueError:
            return 0, "", ""
        findings = [f for fr in result.get("files", []) for f in fr.get("findings", [])]
        errors = [f"{rel.as_posix()}:{f['line']}: {f['message']}" for f in findings if f["level"] == "error"]
        warnings = [f"{rel.as_posix()}:{f['line']}: {f['message']}" for f in findings if f["level"] != "error"]
        title = "studio.py provenance"
    else:
        return 0, "", ""
    if errors:
        return 2, "", f"{title}: 오류 {len(errors)}개 (편집은 이미 반영됨, 고쳐야 합니다)\n" + "\n".join(errors + warnings + notes) + "\n"
    if warnings or notes:
        context = f"{title}: 경고 {len(warnings)}개\n" + "\n".join(warnings + notes)
        out = json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": context}})
        return 0, out, ""
    return 0, "", ""
