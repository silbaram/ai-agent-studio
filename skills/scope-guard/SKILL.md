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
python3 .claude/skills/studio-data/scripts/studio.py scope --link <변경> <시스템 id> … --refresh
```

## 쓰기 전에

`design/systems.json`이 있어야 한다. 없으면 [system-design](../system-design/SKILL.md)을 먼저 쓴다. 시스템 없이는 범위를 잴 수 없다.

OpenSpec을 처음 넣는 프로젝트는 [OpenSpec 설치](references/openspec-setup.md)를 따른다.

## 절차

1. **변경을 시작한다.** `/opsx:propose`로 변경을 만든다. 범위 밖 요청이면 만들기 전에 멈추고 사용자에게 묻는다. propose는 계획만 하고 멈추라고 한다. 사용자가 범위 안의 구현까지 시켰으면("고치고 테스트를 통과시켜") 명령 이름을 쓰지 않았어도 propose 뒤에 apply로 이어 간다. 계획만 시켰으면 멈춘다. 게임 파일은 Write/Edit로만 고친다. 셸의 파이썬·sed로 쓰면 훅이 그 편집을 재지 못한다.
2. **시스템에 잇는다.** 변경을 만들면 바로 `scope --link <변경> <시스템 id>`를 실행한다. 이 변경이 맡는 시스템을 모두 적는다. 새로 적은 시스템은 지금 규칙의 지문을 찍고, 이미 이은 시스템은 지문을 그대로 둔다. 뺀 시스템의 지문은 `x-studio-dropped` 줄에 남아 다시 이으면 되살아난다. 두 줄은 손으로 쓰지 않는다(훅이 막는다). 동작을 바꾸지 않는 변경(`skip_specs: true`)은 잇지 않아도 된다.
3. **규칙을 가리킨다.** 명세는 `design/systems.json`의 규칙 id를 적고, 뜻을 길게 옮기지 않는다. 수치는 `data/`의 파일을 가리킨다.
4. **만들기 전에 잰다.** `scope`를 돌려 오류가 없게 한다. 오류가 있으면 훅이 게임 파일의 편집을 막는다.
5. **닫는다.** 명세를 고쳤으면 작업이 모두 끝난(`[x]`) 상태여도 닫기 전에 `/opsx:update`로 그 명세의 작업을 더하고 `/opsx:apply`로 만든다. 그대로 닫으면 만들지 않은 요구사항이 메인 스펙에 병합된다. 검사기는 이것을 보지 않는다. `/opsx:archive`로 닫는다. 오류가 있으면 메인 스펙 편집, `openspec archive`, 변경 폴더를 옮기는 `mv`가 막힌다.
   - **버릴 시험판(회색 상자, 프로토타입)을 만든 변경은 메인 스펙에 합치지 않는다.** 시험판의 요구사항(5분 판, 기록 내려받기, 요약 스크립트, 시험용 수치)은 본 게임의 기준이 아니다. 합치면 다음 변경이 그것을 지켜야 할 명세로 읽는다. `/opsx:archive`가 동기화를 물으면 "Archive without syncing"을 고른다. 명령으로 닫으면 `openspec archive <변경> --skip-specs`다. 시험판 변경을 만들 때 `proposal.md`에 "시험판: 닫을 때 메인 스펙에 합치지 않는다"를 적어 두면 닫을 때 잊지 않는다. 이미 합쳐졌으면 사용자에게 알리고, 다음 변경에서 그 명세를 지울지 정한다.

## 오류를 읽는 법

모든 오류는 확인으로 끄지 못한다. 고치거나, 범위를 바꿀지 사용자에게 묻는다.

- `change_without_system`: 어떤 시스템을 다루는지 밝히지 않았다. 잇는다. `skip_specs: true`는 명세가 없는 변경만 면제한다.
- `change_unreadable`: 줄을 손으로 썼다. `--link`로 다시 쓴다.
- `unknown_system`: 시스템 설계에 없는 시스템이다. 새 시스템이 필요하면 설계에 먼저 적는다.
- `system_not_in_mvp`: 나중이나 범위 밖, 삭제된 시스템이다. 이번에 만들 것이 아니다.
- `design_changed`: 명세를 쓴 뒤 규칙이 바뀌었다. 명세를 지금 규칙에 맞춘 뒤 메시지의 명령(`--link … --refresh`)으로 지문을 새로 찍는다. 그냥 `--link`는 이미 이은 시스템의 지문을 바꾸지 않으므로 이 오류가 남는다. 다른 오류를 풀려고 다시 이어도 바뀐 규칙이 조용히 받아들여지지 않게 하려는 것이다. 명세를 고치지 않고 `--refresh`하지 않는다. `--link`는 적은 시스템으로 줄을 바꾸므로 빠뜨리면 뺀 시스템을 알린다.
- `rule_of_unlinked_system`: `proposal.md`, `tasks.md`, 명세가 `시스템.규칙`(예: `level_up.level`)으로 잇지 않은 시스템의 규칙을 가리킨다. proposal에 그 시스템이 없거나 브리프의 `prototype.scope` 밖이면 그 줄을 뺀다. 그 시스템도 다루기로 했으면 메시지의 명령으로 이은 시스템을 모두 적어 다시 잇는다. 잇지 않으면 그 규칙이 바뀌어도 `design_changed`가 나지 않는다.
- `unknown_rule`: 설계에 있는 시스템 뒤에, 그 시스템의 규칙과 비슷하지만 설계에 없는 id를 썼다(`gems.ripne`). 오타면 고친다. 새 규칙이면 설계에 먼저 적는다. 비슷한 규칙이 없는 이름(`weapons.fire_rate`)은 데이터 칸일 수 있어 보지 않는다. 파일 이름(`gems.json`)도 보지 않는다. 대문자로 써도(`Gems.Ripen`) 같은 규칙으로 읽는다.
- `rule_in_non_goals`: 변경의 `design.md` Non-Goals에 적은 규칙을 `proposal.md`, `tasks.md`, 명세가 가리킨다. 하지 않을 일이면 그 줄을 뺀다. 하기로 바뀌었으면 Non-Goals에서 빼고 범위가 넓어지는지 사용자에게 묻는다.
- `out_of_scope_in_spec`: 브리프의 범위 밖 문구가 `proposal.md`, `tasks.md`, 명세에 있다. 뺀다. "멀티플레이 없이"처럼 뜻이 반대면 문장을 바꾼다. 하지 않을 일은 `design.md`의 Non-Goals에 적는다. 요구사항을 빼는 `## REMOVED Requirements` 절은 재지 않는다.
- `design_unreadable`, `design_invalid`: 설계나 브리프를 믿을 수 없다. 브리프가 없으면 [concept-exploration](../concept-exploration/SKILL.md)으로 쓰고, 그 밖에는 `studio.py check`로 고친다.

## 훅이 하는 일

`studio.py setup claude`가 설치한다. `openspec/`과 `design/systems.json`이 다 있는 프로젝트에서만 움직인다.

- **막는다.** `scope`에 오류가 있으면 게임을 만드는 파일의 편집, 메인 스펙 편집, `openspec archive`, 변경 폴더를 옮기는 `mv`를 막는다. `scope`가 재지 못해도 막는다. `design`, `data`, `docs`, `reports`, `playtests` 폴더, `openspec`의 나머지, 점으로 시작하는 폴더, 마크다운은 변경을 고치고 플레이 기록을 남길 수 있게 열어 둔다.
- **지문 줄을 지킨다.** 진행 중인 변경의 `.openspec.yaml`에서 `x-studio-systems`나 `x-studio-dropped` 줄을 손으로 바꾸거나 지우는 편집을 막는다. 다른 키는 열어 둔다.
- **메인 스펙의 새 줄을 잰다.** 메인 스펙 편집이 범위 밖 문구를 넣으면 막는다. 있던 줄은 재지 않는다.
- **묻는다.** 범위를 넓히는 편집은 사용자에게 묻는다: 승인됐거나 시스템 설계가 잇는 브리프에 MVP 추가, 범위 밖 항목 제거, 컨셉 승인 추가와 내리기, MVP 시스템 추가, 이을 컨셉 변경. 읽을 수 없는 내용으로 범위 파일을 고치는 편집과 `.claude/settings*.json`, `studio-data`, `scope-guard` 설치본의 편집도 묻는다. 사용자가 허락하면 진행한다. 막힌 에이전트가 브리프나 훅을 고쳐 빠져나가지 못하게 하려는 것이다.

진행 중인 변경이 없고 설계가 멀쩡하면 게임 파일을 막지 않는다. 작은 수정까지 변경을 만들게 하지 않는다. 이때 `scope`의 최종 줄은 PASS가 아니라 `잴 변경 없음`이다.

훅은 프로젝트 전체를 본다. 변경 하나가 틀리면 다른 변경의 일도 막힌다. 급한 수정이 있으면 틀린 변경을 고치거나, 사용자에게 물어 그 변경을 지운다(`git stash -u`로 치워 둘 수 있다).

## 한계

- 범위 밖 문구는 글자 그대로만 찾는다. "온라인 협동 모드"는 "멀티플레이"로 잡지 못한다. 앞에 붙여 쓴 말("온라인멀티플레이")도 못 찾고, 한글 문구는 뒤에 이어진 말("스토리지")에도 걸린다.
- `design.md`와 이미 메인 스펙에 있는 줄은 재지 않는다.
- 변경을 지우면 재지 않는다. 변경 폴더를 지우고 다시 만들거나 셸로 지문 줄을 고치면 뺀 시스템의 지문도 사라진다. 변경 없이 쓴 게임 파일의 내용은 보지 않는다.
- 닫은 뒤에 규칙이 바뀌면 메인 스펙과 어긋나도 모른다. 지문은 진행 중인 변경만 잰다.
- 명세가 규칙 id를 적었는지는 보지 않는다. 적은 `시스템.규칙` 중 설계에 있는 시스템의 것만 본다. 파일 확장자로 보이는 뒤쪽(`gems.json`, `gems.md`)은 규칙으로 보지 않는다. 지문은 시스템 단위라 어느 규칙이 바뀌었는지 말하지 않는다.
- Non-Goals는 `design.md`에서 `## Non-Goals` 제목이면 다음 제목 전까지, `**Non-Goals:**` 이름표면 바로 뒤의 목록까지만 읽는다. 없는 규칙 id는 실제 규칙과 비슷할 때만 잡는다(`meta_upgrades.refund`처럼 비슷한 규칙이 없으면 지나간다). 브리프 `prototype.scope`의 글("메타 성장 제외")은 읽지 못한다.
- 명세를 고친 뒤 작업이 모두 끝난 상태인지는 보지 않는다(절차 5단계).
- `data`, `docs` 같은 열어 둔 폴더에 코드를 두면 게임 파일로 보지 않는다.
- `gems`로 이어 놓고 다른 것을 만들면 잡지 못한다. 잇는 말을 믿는다.
- 훅은 시스템을 더하는 `--link`를 묻지 않는다. MVP 안의 시스템이면 브리프 `prototype.scope` 밖이어도 이어진다. 더한 시스템이 이번 프로토타입 범위인지는 사람이 본다.
- 규칙이 바뀐 것은 알아도, 명세가 정말 맞춰졌는지는 모른다.
- 브리프의 안티필러는 보지 않는다.
- 훅은 `Write`·`Edit`와 위의 셸 명령 모양만 본다. 다른 셸 명령이나 스크립트로 파일을 쓰거나 옮기면 잡지 못한다.
- 훅은 Claude Code에서만 돈다. Codex는 `scope`를 직접 돌린다.
- 사용자가 없는 실행(`claude -p`)에서 묻는 편집은 거부된다. acceptEdits 모드에서 확인했다. bypassPermissions 같은 다른 모드에서 묻는 편집이 어떻게 되는지는 확인하지 않았다.
- 묻는 창에는 훅이 적은 이유가 나오지 않는다. 보통 편집 확인과 바뀌는 내용만 보인다. 편집 자동 허용 모드에서 이 창이 뜨면 범위를 건드리는 편집이다. 기본 모드에서는 다른 편집과 구별되지 않으니 바뀌는 내용을 읽고 정한다.
