"""Claude Code 연결: setup(판정 에이전트·훅 설치)과 hook(훅 처리기).

setup은 게임 프로젝트의 .claude/agents/studio-judge.md를 쓰고 .claude/settings.json의 hooks에 세 훅을 합쳐 넣는다.
  - PostToolUse: design/·data/ 아래 파일을 고치면 check(데이터) 또는 provenance(md)를 돌려 결과를 에이전트에게 보인다.
  - PreToolUse: 판정 에이전트(studio-judge)가 파일을 쓰거나 check·provenance 밖의 명령을 실행하면 막는다.
  - PreToolUse: 범위를 벗어난 OpenSpec 변경이 있으면 만드는 파일의 편집과 보관을 막고, 범위를 넓히는 설계 편집은 사용자에게 묻는다.
훅 입력 형식은 Claude Code 문서(hooks)를 따른다. 사용자 훅과 다른 설정은 그대로 둔다.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shlex
import tempfile
import time
from collections import Counter
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path, PurePosixPath

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
PLANNING = ("design", "data", "docs", "reports", "playtests")  # 무엇을 만들지 적는 곳과 플레이 기록. 나머지는 게임을 만드는 파일로 본다
OPENSPEC_ARCHIVE = r"openspec[^\s;&|]*(?:\s+-\S+)*\s+archive\b"  # openspec archive. npx와 판 지정, 앞의 옵션을 포함한다
MOVE = re.compile(r"\b(?:mv|move|Move-Item)\s[^;&|\n]*(?:openspec[/\\]+changes[/\\]|(?-i:archive)[/\\])", re.IGNORECASE)  # /opsx:archive는 CLI 대신 폴더를 옮긴다. 대소문자를 가리지 않는 것은 openspec 쪽만이다
ARCHIVE = re.compile(OPENSPEC_ARCHIVE + "|" + MOVE.pattern, re.IGNORECASE)
TEXT_ONLY = {"grep", "egrep", "fgrep", "echo", "printf"}   # 인자를 글로만 다루는 명령. 그 인자 속 글은 보관이 아니다
GIT_TEXT_ONLY = {"commit", "log", "show"}                 # git 바로 뒤에 올 때만. 앞에 옵션(-c, -C)이 있으면 보지 않는다
PIPE_TEXT_ONLY = {"head", "tail", "wc", "sort", "uniq", "cat", "grep", "egrep", "fgrep"}   # 받은 글을 실행하지 않는 파이프 뒤 명령
UNSURE = re.compile(r"\$\(|`|[<>]\(|\\[\s;&|'\"]")   # 명령 치환, 프로세스 치환(따옴표 안에서도 실행된다), 셸마다 다르게 읽는 이스케이프
HELP = {"--help", "-h"}
GUARDED = "|".join(WRITE_TOOLS + ("Bash",))
SELF = (".claude/settings.json", ".claude/settings.local.json", ".claude/skills/studio-data", ".claude/skills/scope-guard")  # 고치면 범위 훅이 꺼진다
STATE_DIR = Path(tempfile.gettempdir()) / "studio-data-hook"   # 세션마다 이미 보인 경고. 게임 프로젝트에는 쓰지 않는다
HOOKS = (("PostToolUse", "Write|Edit|MultiEdit", "post-edit"), ("PreToolUse", GUARDED, "judge-guard"), ("PreToolUse", GUARDED, "scope-guard"),
         ("SessionStart", "compact|clear|resume", "session-start"))   # 압축·지움·이어 열기 뒤에는 경고를 다시 모두 보인다


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
               f"훅: {settings_path} (PostToolUse 데이터 검사, PreToolUse 판정 에이전트 쓰기 차단과 범위 이탈 차단, SessionStart 경고 다시 보이기)",
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
def _folded(rel: Path) -> PurePosixPath:
    """경로를 맞춰 볼 꼴. 대소문자를 가리지 않는 파일 시스템에서 Design/systems.json은 design/systems.json이다."""
    return PurePosixPath(*(part.casefold() for part in rel.parts))


def _builds_game(rel: PurePosixPath) -> bool:
    """게임을 만드는 파일인가. 메인 스펙은 보관의 결과이고, 그 밖의 계획 파일은 변경을 고칠 수 있게 열어 둔다."""
    if rel.parts[:2] == ("openspec", "specs"):
        return True
    return rel.parts[0] not in PLANNING and rel.parts[0] != "openspec" and not rel.parts[0].startswith(".") and rel.suffix.lower() != ".md"


def _gate(project: Path) -> tuple[int, str, str]:
    try:
        errors = scope.check(project)["errors"]
    except Exception as exc:  # 훅이 죽어도 Claude Code는 막지 않는다. 재지 못한 것을 통과시키지 않는다
        return 2, "", f"범위를 재지 못해 막았습니다: {exc!r}. {scope.CMD} scope로 원인을 봅니다.\n"
    if not errors:
        return 0, "", ""
    lines = "\n".join(f"[{e['code']}] {e['where']}: {e['message']}" for e in errors)
    return 2, "", f"범위를 벗어난 변경이 있어 막았습니다.\n{lines}\n변경을 고친 뒤 {scope.CMD} scope로 확인합니다. 시스템은 {scope.CMD} scope --link로 잇습니다. 범위를 바꾸는 일은 사용자에게 묻습니다.\n"


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


def _sets_scope(rel: PurePosixPath) -> bool:
    """범위를 정하는 파일인가. 컨셉은 check가 찾는 자리면 어디든, 시스템 설계는 design/에만 둔다."""
    name, parent = rel.name.lower(), rel.parent.as_posix()
    return (name == "systems.json" and parent == "design") or (name == "concepts.json" and parent in (".", *c.SUBFOLDERS))


def _is_change_meta(rel: PurePosixPath) -> bool:
    """진행 중인 변경의 메타데이터(openspec/changes/<변경>/.openspec.yaml). 보관한 변경은 한 단계 더 깊어 여기에 들지 않는다."""
    return len(rel.parts) == 4 and rel.parts[:2] == ("openspec", "changes") and rel.name == scope.META


def _guard_meta(path: Path, tool: str, tool_input: dict) -> tuple[int, str, str]:
    """시스템 줄과 뺀 시스템 줄은 scope --link만 쓴다. 손으로 지우고 다시 이으면 바뀐 규칙이 새 지문으로 덮인다. 다른 키는 열어 둔다."""
    before = path.read_text(encoding="utf-8-sig", errors="replace") if path.is_file() else ""
    try:
        after = _edited_text(path, tool, tool_input)
    except (OSError, UnicodeDecodeError):
        after = None
    if after is not None and scope.meta_lines(after) == scope.meta_lines(before):
        return 0, "", ""
    return 2, "", (f"{scope.KEY} 줄은 {scope.CMD} scope --link로만 씁니다. 손으로 지우거나 고친 뒤 다시 이으면 바뀐 규칙이 새 지문으로 덮입니다. "
                   f"시스템을 바꾸려면 {scope.CMD} scope --link <변경> <시스템 id> …를, 명세를 바뀐 규칙에 맞춘 뒤에는 --refresh를 붙여 씁니다.\n")


def _ask(reason: str) -> tuple[int, str, str]:
    return 0, json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask", "permissionDecisionReason": reason}}), ""


def _json_object(text: str) -> dict | None:
    try:
        data = json.loads(text.lstrip("\ufeff"))
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _ask_if_widened(project: Path, path: Path, tool: str, tool_input: dict) -> tuple[int, str, str]:
    """범위를 정하는 파일의 편집. 처음 쓰는 파일은 넓힐 것이 없다. 읽지 못하는 내용은 넓혔는지 모르므로 묻는다.
    넘기면 깨뜨렸다가 넓히는 두 번의 편집이 묻지 않고 지나간다."""
    unreadable = f"범위를 정하는 파일을 읽을 수 없는 내용으로 다룹니다. 넓히는지 알 수 없어 사용자가 정합니다: {path.name}"
    try:
        after_text = _edited_text(path, tool, tool_input)
        before_text = path.read_text(encoding="utf-8-sig")
    except OSError:
        return 0, "", ""
    except ValueError:
        return _ask(unreadable)
    if after_text is None:
        return 0, "", ""
    before, after = _json_object(before_text), _json_object(after_text)
    if before is None or after is None:
        return _ask(unreadable)
    found = scope.widened(path.stem.lower(), before, after, scope.concept_in_use(project))
    return _ask("범위를 넓히는 편집입니다. 사용자가 정할 일입니다: " + "; ".join(found)) if found else (0, "", "")


def _guards_itself(rel: PurePosixPath) -> bool:
    text = rel.as_posix()
    return any(text == x or text.startswith(x + "/") for x in SELF)


def _check_main_spec(project: Path, path: Path, tool: str, tool_input: dict) -> tuple[int, str, str]:
    """메인 스펙에 새로 들어오는 줄을 잰다. 있던 줄을 재면 범위를 줄인 뒤 그 요구사항을 빼는 변경까지 막힌다."""
    try:
        after = _edited_text(path, tool, tool_input)
        before = path.read_text(encoding="utf-8-sig") if path.is_file() else ""
    except (OSError, ValueError):
        return 0, "", ""
    found = scope.added_out_of_scope(project, before, after) if after is not None else []
    if not found:
        return 0, "", ""
    return 2, "", f"[out_of_scope_in_spec] {path.name}: 브리프가 범위 밖이라고 한 항목을 메인 스펙에 넣습니다: {', '.join(found)}. 빼거나, 브리프를 바꿀지 사용자에게 묻습니다.\n"


def _segments(command: str) -> list[tuple[str, str]] | None:
    """셸 연결(; & | 줄바꿈)로 나눈 (앞의 연결 기호, 명령). 따옴표 안은 나누지 않는다. 따옴표가 닫히지 않으면 None."""
    out, sep, buf, quote, i = [], "", "", None, 0
    while i < len(command):
        ch = command[i]
        if ch == "\\" and quote != "'":
            buf, i = buf + command[i:i + 2], i + 2
            continue
        if quote:
            quote = None if ch == quote else quote
        elif ch in "'\"":
            quote = ch
        elif ch in ";&|\n\r":
            run = re.match(r"[;&|\n\r]+", command[i:]).group(0)
            out.append((sep, buf))
            sep, buf, i = run, "", i + len(run)
            continue
        buf += ch
        i += 1
    return None if quote else out + [(sep, buf)]


def _unquoted(command: str) -> str:
    """따옴표 밖의 글. 따옴표 안의 >는 글이고 밖의 >는 출력을 파일로 보낸다."""
    out, quote, i = "", None, 0
    while i < len(command):
        ch = command[i]
        if ch == "\\" and quote != "'":
            i += 2
            continue
        if quote:
            quote = None if ch == quote else quote
        elif ch in "'\"":
            quote = ch
        else:
            out += ch
        i += 1
    return out


def _writes_file(command: str) -> bool:
    """출력을 파일로 보내는가(>, >>, &>). 2>&1처럼 흐름만 잇는 것은 뺀다. 파일에 쓴 보관 명령은 나중에 실행할 수 있다."""
    return ">" in re.sub(r"\d*>&\d+", "", _unquoted(command))


def _words(text: str) -> list[str] | None:
    try:
        return shlex.split(text)
    except ValueError:
        return None


def _text_only(words: list[str] | None) -> bool:
    """인자를 글로만 다루는 명령인가. 명령 이름이 맨 앞에 그대로 있을 때만 믿는다(환경 변수, 경로, sudo 앞붙임은 보지 않는다)."""
    if not words:
        return False
    return words[0] in TEXT_ONLY or (words[0] == "git" and len(words) > 1 and words[1] in GIT_TEXT_ONLY)


def _asks_help(text: str) -> bool:
    """openspec … archive 뒤에 --help나 -h가 있어 도움말만 내는가. 명령 글을 한 인자로 넘기는 꼴(bash -c "…"), 주석(#), -- 뒤는 믿지 않는다."""
    words = _words(text)
    if not words or MOVE.search(text) or any(re.search(r"\s", w) or w.startswith("#") for w in words):
        return False
    for i, word in enumerate(words):
        if word.casefold() != "archive" or i == 0:
            continue
        program = next((w for w in reversed(words[:i]) if not w.startswith("-")), "")
        if "openspec" in program.casefold():
            rest = words[i + 1:]
            return bool(HELP & set(rest[:rest.index("--")] if "--" in rest else rest))
    return False


def _archives(command: str) -> bool:
    """변경을 보관하거나 옮기는 명령인가. 글을 찾거나 찍기만 하는 명령의 인자와 도움말은 뺀다.
    명령 치환이 있거나, 출력을 파일로 보내거나, 파이프가 글을 실행할 수 있는 명령으로 가면 빼지 않는다. 모르면 보관으로 본다."""
    command = re.sub(r"\\\r?\n", " ", command)   # 줄 잇기
    if not ARCHIVE.search(command):
        return False
    segments = _segments(command)
    if segments is None:
        return True
    lenient = not UNSURE.search(command) and not _writes_file(command) and all(
        (_words(text) or [""])[0] in PIPE_TEXT_ONLY for sep, text in segments if "|" in sep and sep != "||")
    for _, text in segments:
        if ARCHIVE.search(text) and not (lenient and _text_only(_words(text))) and not _asks_help(text):
            return True
    return False


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
        return _gate(project) if isinstance(command, str) and _archives(command) else (0, "", "")
    target = _target(payload, project) if tool in WRITE_TOOLS else None
    if target is None:
        return 0, "", ""
    path, rel = target
    key = _folded(rel)
    if _is_change_meta(key):
        return _guard_meta(path, tool, tool_input)
    if _sets_scope(key):
        return _ask_if_widened(project, path, tool, tool_input)
    if _guards_itself(key):
        return _ask(f"범위 훅과 검사 도구를 바꾸는 편집입니다. 사용자가 정할 일입니다: {rel.as_posix()}")
    if not _builds_game(key):
        return 0, "", ""
    result = _gate(project)
    return _check_main_spec(project, path, tool, tool_input) if result[0] == 0 and key.parts[:2] == ("openspec", "specs") else result


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


STATE_DAYS = 7   # 이보다 오래된 세션 기록은 지운다


def _session_key(project: Path, session: str) -> str:
    return hashlib.sha256(f"{project.resolve()}\n{session}".encode("utf-8")).hexdigest()[:16]


def _state_dir() -> Path | None:
    """세션 기록 폴더. 남이 만든 폴더면 쓰지 않는다(None: 경고를 모두 보인다). 내 폴더인데 남이 읽을 수 있으면 막는다."""
    try:
        STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
        if hasattr(os, "getuid"):
            st = STATE_DIR.stat()
            if st.st_uid != os.getuid():
                return None
            if st.st_mode & 0o077:
                os.chmod(STATE_DIR, 0o700)
    except OSError:
        return None
    return STATE_DIR


def _prune(folder: Path) -> None:
    cutoff = time.time() - STATE_DAYS * 86400
    for f in folder.glob("*.json"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
        except OSError:
            pass


def _diff(before: list[str], now: list[str]) -> tuple[list[str], list[str], list[str]]:
    """(새 경고, 바뀐 경고, 풀린 경고). 같은 줄이 여러 번이면 그 수로 견준다.
    파일·코드·대상이 같고 글만 다른 줄(수치가 바뀜)은 새 경고와 풀린 경고 대신 바뀐 경고 하나로 본다."""
    new, gone, changed = _minus(now, before), _minus(before, now), []
    for w in list(new):
        k = _warning_key(w)
        twin = next((g for g in gone if k and _warning_key(g) == k), None)
        if twin is not None:
            gone.remove(twin)
            new.remove(w)
            changed.append(w)
    return new, changed, gone


def _minus(lines: list[str], other: list[str]) -> list[str]:
    """lines에서 other에 있는 줄을 그 수만큼 뺀다. 순서는 lines대로다."""
    left, out = Counter(other), []
    for w in lines:
        if left[w] > 0:
            left[w] -= 1
        else:
            out.append(w)
    return out


def _warning_key(line: str) -> str | None:
    """check 경고 줄 '파일: [코드] 대상: 글'의 '파일: [코드] 대상'. 다른 꼴이면 None."""
    parts = line.split(": ", 2)
    return ": ".join(parts[:2]) if len(parts) == 3 and parts[1].startswith("[") else None


def _seen(payload: dict, project: Path, topic: str, warnings: list[str]) -> tuple[list[str], list[str], list[str]] | None:
    """이 세션의 이 에이전트에게 이 주제(check, 문서 하나)의 경고를 보인 적이 있으면 _diff의 결과. 지금 목록을 기록한다.
    하위 에이전트는 세션 id가 같아도 따로 센다. 세션 id가 없거나, 처음이거나, 기록을 읽고 쓰지 못하면 None이다. 그때는 경고를 모두 보인다."""
    session = payload.get("session_id")
    if not (isinstance(session, str) and session):
        return None
    folder = _state_dir()
    if folder is None:
        return None
    agent = payload.get("agent_id") or payload.get("agent_type") or "main"
    agent_key = hashlib.sha256(str(agent).encode("utf-8")).hexdigest()[:8]
    path = folder / f"{_session_key(project, session)}-{agent_key}.json"
    try:
        state = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, ValueError):
        state = {}
    state = state if isinstance(state, dict) else {}
    before = state.get(topic)
    state[topic] = warnings
    tmp = path.with_name(f"{path.stem}.{os.getpid()}.tmp")
    try:   # 다른 편집의 훅이 반쯤 쓴 파일을 읽지 않게 바꿔 끼운다
        tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        return None
    _prune(folder)
    if not (isinstance(before, list) and all(isinstance(w, str) for w in before)):
        return None
    return _diff(before, warnings)


def _warning_lines(warnings: list[str], seen: tuple[list[str], list[str], list[str]] | None, again: str) -> list[str]:
    """보일 경고 줄. 이미 보인 경고는 파일별 개수로만 적는다. again: 전부 다시 보는 명령."""
    if seen is None:
        return warnings
    new, changed, gone = seen
    out = [line for title, lines in (("새 경고", new), ("바뀐 경고", changed), ("풀린 경고", gone)) if lines
           for line in [f"{title} {len(lines)}개:"] + lines]
    rest = list((Counter(warnings) - Counter(new + changed)).elements())
    if rest:
        files = Counter(w.split(": [", 1)[0] for w in rest if ": [" in w)
        where = f"({', '.join(f'{k} {n}' for k, n in sorted(files.items()))})" if files else ""
        out.append(f"다시 적지 않음: 이 세션에서 이미 보인 경고 {len(rest)}개{where}. 전부 보려면 `{again}`")
    return out


def session_start(payload_text: str, project: Path | None = None) -> tuple[int, str, str]:
    """대화를 압축하거나 지우거나 이어 열면 앞서 보인 경고가 맥락에 없을 수 있다. 그 세션의 기록을 지워 다음 편집에 모두 보인다."""
    payload = _payload(payload_text)
    session = payload.get("session_id") if payload else None
    if not (isinstance(session, str) and session):
        return 0, "", ""
    for f in STATE_DIR.glob(f"{_session_key(_project(payload, project), session)}-*.json"):
        try:
            f.unlink()
        except OSError:
            pass
    return 0, "", ""


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
        title, topic, again = "studio.py check", "check", f"{scope.CMD} check ."
    elif suffix == ".md":
        code, out = _run(["provenance", str(path), "--json"])
        try:
            result = json.loads(out)
        except ValueError:
            return 0, "", ""
        findings = [f for fr in result.get("files", []) for f in fr.get("findings", [])]
        errors = [f"{rel.as_posix()}:{f['line']}: {f['message']}" for f in findings if f["level"] == "error"]
        warnings = [f"{rel.as_posix()}:{f['line']}: {f['message']}" for f in findings if f["level"] != "error"]
        title, topic, again = "studio.py provenance", f"provenance:{rel.as_posix()}", f"{scope.CMD} provenance {rel.as_posix()}"
    else:
        return 0, "", ""
    seen = _seen(payload, project, topic, warnings)
    shown = _warning_lines(warnings, seen, again)
    if errors:
        return 2, "", f"{title}: 오류 {len(errors)}개 (편집은 이미 반영됨, 고쳐야 합니다)\n" + "\n".join(errors + shown + notes) + "\n"
    if warnings or notes or (seen and seen[2]):
        same = " · 지난 편집과 같습니다" if seen is not None and warnings and not any(seen) else ""
        context = f"{title}: 경고 {len(warnings)}개{same}\n" + "\n".join(shown + notes)
        out = json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": context}})
        return 0, out, ""
    return 0, "", ""
