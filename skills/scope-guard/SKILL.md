---
name: scope-guard
description: "Connects OpenSpec changes to the game's brief and system design, and blocks work that leaves the MVP: each change names the systems it covers, stale specs and out-of-scope items are errors, and a hook stops building and archiving until they are fixed and asks the user before scope widens. Use when setting up OpenSpec in a game project, starting a change, or when studio.py scope or the scope hook reports a problem."
---

# 범위 이탈 차단

개발이 브리프에서 벗어나지 않게 한다. OpenSpec은 변경을 명세로 쓰고 닫는 일을 맡는다. 이 스킬은 그 변경이 브리프의 MVP 안에 있는지 기계로 잰다.

OpenSpec만으로는 막지 못한다. 범위 밖 변경도 `validate --strict`와 `archive`를 통과하고, 설계가 바뀌어도 알지 못한다. 근거는 [수명주기 뼈대 시험](https://github.com/silbaram/ai-agent-studio/blob/main/docs/research/lifecycle-trial-2026-11.md)에 있다.

## 도구

공용 스킬 [studio-data](../studio-data/SKILL.md)의 `studio.py`로 한다. 이 스킬과 함께 설치한다. 명령은 게임 프로젝트 폴더에서 Claude Code 설치 기준으로 적었다. Codex는 `.agents/skills/`로 바꾼다.

```bash
python3 .claude/skills/studio-data/scripts/studio.py scope
python3 .claude/skills/studio-data/scripts/studio.py scope --link <변경> <시스템 id> …
```

## 쓰기 전에

`design/systems.json`이 있어야 한다. 없으면 [system-design](../system-design/SKILL.md)을 먼저 쓴다. 시스템 없이는 범위를 잴 수 없다.

OpenSpec을 처음 넣는 프로젝트는 [OpenSpec 설치](references/openspec-setup.md)를 따른다.

## 절차

1. **변경을 시작한다.** `/opsx:propose`로 변경을 만든다. 범위 밖 요청이면 만들기 전에 멈추고 사용자에게 묻는다.
2. **시스템에 잇는다.** 변경을 만들면 바로 `scope --link <변경> <시스템 id>`를 실행한다. 이 변경이 맡는 시스템을 모두 적는다. 줄은 손으로 쓰지 않는다. 동작을 바꾸지 않는 변경(`skip_specs: true`)은 잇지 않아도 된다.
3. **규칙을 가리킨다.** 명세는 `design/systems.json`의 규칙 id를 적고, 뜻을 길게 옮기지 않는다. 수치는 `data/`의 파일을 가리킨다.
4. **만들기 전에 잰다.** `scope`를 돌려 오류가 없게 한다. 오류가 있으면 훅이 게임 파일의 편집을 막는다.
5. **닫는다.** `/opsx:archive`로 닫는다. 오류가 있으면 메인 스펙 편집, `openspec archive`, 변경 폴더를 옮기는 `mv`가 막힌다.

## 오류를 읽는 법

모든 오류는 확인으로 끄지 못한다. 고치거나, 범위를 바꿀지 사용자에게 묻는다.

- `change_without_system`: 어떤 시스템을 다루는지 밝히지 않았다. 잇는다. `skip_specs: true`는 명세가 없는 변경만 면제한다.
- `change_unreadable`: 줄을 손으로 썼다. `--link`로 다시 쓴다.
- `unknown_system`: 시스템 설계에 없는 시스템이다. 새 시스템이 필요하면 설계에 먼저 적는다.
- `system_not_in_mvp`: 나중이나 범위 밖, 삭제된 시스템이다. 이번에 만들 것이 아니다.
- `design_changed`: 명세를 쓴 뒤 규칙이 바뀌었다. 명세를 지금 규칙에 맞춘 뒤 메시지의 명령으로 다시 잇는다. 명세를 고치지 않고 다시 잇지 않는다. `--link`는 적은 시스템으로 줄을 바꾸므로 빠뜨리면 뺀 시스템을 알린다.
- `out_of_scope_in_spec`: 브리프의 범위 밖 문구가 `proposal.md`, `tasks.md`, 명세에 있다. 뺀다. "멀티플레이 없이"처럼 뜻이 반대면 문장을 바꾼다. 하지 않을 일은 `design.md`의 Non-Goals에 적는다. 요구사항을 빼는 `## REMOVED Requirements` 절은 재지 않는다.
- `design_unreadable`, `design_invalid`: 설계나 브리프를 믿을 수 없다. 브리프가 없으면 [concept-exploration](../concept-exploration/SKILL.md)으로 쓰고, 그 밖에는 `studio.py check`로 고친다.

## 훅이 하는 일

`studio.py setup claude`가 설치한다. `openspec/`과 `design/systems.json`이 다 있는 프로젝트에서만 움직인다.

- **막는다.** `scope`에 오류가 있으면 게임을 만드는 파일의 편집, 메인 스펙 편집, `openspec archive`, 변경 폴더를 옮기는 `mv`를 막는다. `scope`가 재지 못해도 막는다. `design`, `data`, `docs`, `reports` 폴더, `openspec`의 나머지, 점으로 시작하는 폴더, 마크다운은 변경을 고칠 수 있게 열어 둔다.
- **메인 스펙의 새 줄을 잰다.** 메인 스펙 편집이 범위 밖 문구를 넣으면 막는다. 있던 줄은 재지 않는다.
- **묻는다.** 범위를 넓히는 편집은 사용자에게 묻는다: 승인됐거나 시스템 설계가 잇는 브리프에 MVP 추가, 범위 밖 항목 제거, 컨셉 승인 추가와 내리기, MVP 시스템 추가, 이을 컨셉 변경. 읽을 수 없는 내용으로 범위 파일을 고치는 편집과 `.claude/settings*.json`, `studio-data`, `scope-guard` 설치본의 편집도 묻는다. 사용자가 허락하면 진행한다. 막힌 에이전트가 브리프나 훅을 고쳐 빠져나가지 못하게 하려는 것이다.

진행 중인 변경이 없고 설계가 멀쩡하면 게임 파일을 막지 않는다. 작은 수정까지 변경을 만들게 하지 않는다. 이때 `scope`의 최종 줄은 PASS가 아니라 `잴 변경 없음`이다.

훅은 프로젝트 전체를 본다. 변경 하나가 틀리면 다른 변경의 일도 막힌다. 급한 수정이 있으면 틀린 변경을 고치거나, 사용자에게 물어 그 변경을 지운다(`git stash -u`로 치워 둘 수 있다).

## 한계

- 범위 밖 문구는 글자 그대로만 찾는다. "온라인 협동 모드"는 "멀티플레이"로 잡지 못한다. 앞에 붙여 쓴 말("온라인멀티플레이")도 못 찾고, 한글 문구는 뒤에 이어진 말("스토리지")에도 걸린다.
- `design.md`와 이미 메인 스펙에 있는 줄은 재지 않는다.
- 변경을 지우면 재지 않는다. 변경 없이 쓴 게임 파일의 내용은 보지 않는다.
- 닫은 뒤에 규칙이 바뀌면 메인 스펙과 어긋나도 모른다. 지문은 진행 중인 변경만 잰다.
- 명세가 규칙 id를 적었는지는 보지 않는다. 지문은 시스템 단위라 어느 규칙이 바뀌었는지 말하지 않는다.
- `data`, `docs` 같은 열어 둔 폴더에 코드를 두면 게임 파일로 보지 않는다.
- `gems`로 이어 놓고 다른 것을 만들면 잡지 못한다. 잇는 말을 믿는다.
- 규칙이 바뀐 것은 알아도, 명세가 정말 맞춰졌는지는 모른다.
- 브리프의 안티필러는 보지 않는다.
- 훅은 `Write`·`Edit`와 위의 셸 명령 모양만 본다. 다른 셸 명령이나 스크립트로 파일을 쓰거나 옮기면 잡지 못한다.
- 훅은 Claude Code에서만 돈다. Codex는 `scope`를 직접 돌린다.
- 사용자가 없는 실행(`claude -p`)에서 묻는 편집은 거부된다.
