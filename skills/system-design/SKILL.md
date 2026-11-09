---
name: system-design
description: "Lists the systems a game needs with their rules and dependencies, ties each one to the brief's pillars, MVP items and out-of-scope list, and reports what nothing serves, what drifts out of scope, circular dependencies, and the order to build in. Use after a concept has a brief and before implementation, when deciding what systems a game has, what each one does, or what to build first, in any genre and engine."
---

# 시스템 설계

브리프와 구현 사이를 잇는다. 브리프는 무엇을 경험시킬지 말하고, 밸런스와 레벨 스킬은 수치를 다룬다. 이 스킬은 그 사이의 "어떤 시스템이 있고 각각 어떤 규칙으로 움직이며 무엇에 기대는가"를 적는다. 목적은 "이 필러를 맡는 시스템이 있는가", "MVP에 빠진 것이 없는가", "브리프가 뺀 것이 구현으로 새지 않는가", "무엇부터 만드는가"를 감 대신 목록으로 답하는 것이다.

규칙은 사람이 쓰는 글이다. 도구는 연결과 순서만 본다. 규칙이 좋은지, 시스템이 재미있는지는 판정하지 않는다.

## 도구

공용 스킬 [studio-data](../studio-data/SKILL.md)의 `studio.py`로 한다. 이 스킬과 함께 설치한다. 명령은 게임 프로젝트 폴더에서 Claude Code 설치 기준으로 적었다. Codex는 `.agents/skills/…`, Windows PowerShell은 `python3` 대신 `py`([실행 경로](../studio-data/SKILL.md#실행)).

| 명령 | 하는 일 |
|---|---|
| `python3 .claude/skills/studio-data/scripts/studio.py check .` | 형식, 브리프와의 연결, 범위, 의존 관계 검사 |
| `… check . --table systems` | 만드는 순서로 본 시스템 표(마크다운) |
| `… view .` | 시스템 설계 탭 |

데이터는 `design/systems.json` 한 파일이다. 형식은 [references/systems-format.md](references/systems-format.md). 브리프는 [concept-exploration](../concept-exploration/SKILL.md)의 `design/concepts.json`에서 읽는다. 프로젝트 폴더(`check .`)로 검사해야 연결을 확인한다. 컨셉을 함께 넘기지 않으면 `INCOMPLETE`다.

## 절차

### 1. 브리프를 읽는다

승인된 컨셉의 필러, MVP, 범위 밖, 안티필러를 읽는다. 브리프가 없으면 시스템을 적지 않고 [concept-exploration](../concept-exploration/SKILL.md)으로 돌아간다. 승인된 컨셉이 둘 이상이면 최상위 `concept`에 하나를 적는다.

### 2. 시스템을 나눈다

시스템은 혼자 켜고 끌 수 있는 규칙의 묶음이다. 플레이어 조작, 적, 성장, 재화처럼 나눈다. 코드 구조가 아니라 규칙의 단위로 나눈다. 너무 잘게 나누지 않는다. 브리프의 MVP가 7개 이하이므로 시스템도 그 안팎이다.

브리프가 말하지 않아도 다른 시스템이 기대는 기반 시스템(플레이어 이동, 카메라)이 있다. `foundation: true`로 적는다. 필러와 MVP 항목이 없어도 되지만 기대는 시스템이 있어야 한다. 브리프를 고치려고 기반을 MVP에 넣지 않는다.

### 3. 브리프에 잇는다

시스템마다 적는다.

- `pillars`: 이 시스템이 돕는 필러. 브리프의 `name` 그대로 쓴다. 돕는 필러가 없으면 만들 이유를 다시 본다.
- `mvp`: 이 시스템이 맡는 브리프의 MVP 항목. 문구 그대로 쓴다.
- `scope`: `mvp`(이번에 만듦), `later`(나중), `out`(브리프가 뺀 것).
- `out_of_scope`: `scope`가 `out`이면 브리프의 범위 밖 항목을 가리킨다. 자꾸 거론되는 것을 빼 둔 채로 기록한다.

안티필러는 사람이 본다. 시스템을 적을 때 안티필러와 부딪치지 않는지 한 번씩 읽는다. 도구는 뜻을 읽지 못한다.

### 4. 규칙을 적는다

`rules`에 구현할 수 있는 문장으로 적는다. "패링에 성공하면 템포가 한 단계 오른다"처럼 조건과 결과를 쓴다. 수치는 규칙에 적지 않고 데이터 파일에 둔다. 규칙에 수를 꼭 적어야 하면 [numeric-provenance](../numeric-provenance/SKILL.md)의 출처 태그를 붙인다.

### 5. 의존을 적고 순서를 본다

`depends_on`에 이 시스템이 먼저 있어야 하는 시스템을 적는다. 없으면 동작하지 않는 것만 적는다. 그다음 표를 본다.

```bash
python3 .claude/skills/studio-data/scripts/studio.py check . --table systems
```

순서는 의존이 없는 시스템이 1이고, 의존하는 시스템보다 하나 뒤다. 같은 숫자는 나란히 만들 수 있다. 1단계가 시험할 수 없을 만큼 크면 시스템을 나눈다.

### 6. 경고를 처리한다

- `pillar_unserved`: 범위가 MVP인 시스템이 맡지 않는 필러다. 이대로 만들면 그 필러를 시험할 수 없다. 시스템에 잇거나, 필러가 맞는지 사용자와 다시 본다. 일부러 뒤로 미룬 것이면 어느 시스템의 `acknowledged`에든 `{"pillar_unserved": {필러 이름: 이유}}`로 적는다.
- `mvp_unserved`: 어떤 시스템도 맡지 않는 MVP 항목이다. 확인하는 길은 위와 같다.
- `scope_mismatch`: 시스템의 범위가 브리프와 다르다. 브리프를 바꾸는 일이면 사용자에게 묻는다.
- `out_of_scope_claimed`(오류): 범위 밖 항목을 만들 시스템의 항목이나 글에 넣었다. 확인으로 끄지 못한다. 브리프를 바꾸려면 사용자에게 묻는다.
- `scope_dependency`(오류): MVP 시스템이 나중이나 범위 밖 시스템에 기댄다. 그대로면 만들 수 없다. 범위를 맞추거나 의존을 끊는다.
- `dependency_cycle`(오류): 먼저 만들 수 있는 쪽이 없다. 의존을 끊거나 한 시스템으로 합친다.
- `concept_not_approved`: 승인되지 않은 컨셉에 이었다. 브리프가 확정되기 전이라 연결도 확정이 아니다. 선택했던 컨셉을 되돌렸으면([playtest-verdict](../playtest-verdict/SKILL.md)의 '컨셉을 되돌릴 때') 다음 컨셉을 고를 때까지 연결과 데이터를 그대로 두고, 고른 뒤 그 컨셉에 다시 잇는다. 되돌리며 `cut`했으면 같은 경우에 `cut_referenced`가 난다.
- `system_without_pillar`: 필러를 돕지 않는 시스템이다. 기반이면 `foundation`을 적고, 아니면 만들 이유를 다시 본다.
- `foundation_unused`: 기대는 시스템이 없는 기반이다. 의존을 적거나 표시를 뺀다.
- `system_without_rules`: 규칙이 없어 구현할 수 없다.

## 보고

- 만드는 순서 표
- 맡는 시스템이 없는 필러와 MVP 항목
- 범위와 어긋난 시스템, 만들 수 없는 의존
- 오류·경고 수, `INCOMPLETE` 여부
- 사용자가 정해야 할 것: 시스템 나누기, 범위, 브리프를 바꿀지

## 한계

- 규칙의 품질과 재미는 보지 않는다.
- 필러, MVP, 범위 밖은 문구로 잇는다. 브리프 문구를 고치면 여기도 고친다. 고치지 않으면 오류로 알린다.
- 안티필러는 뜻을 읽어야 해서 검사하지 않는다. 범위 밖 항목은 글자 그대로만 찾아서 다른 말로 적은 것은 잡지 못한다.
- 규칙 글의 수치와 출처 태그는 검사하지 않는다.
- 순서는 의존만 본다. 위험한 것부터 만드는 판단이나 프로토타입에 넣을지는 사람이 정한다.
- 시스템과 데이터 파일(전투 계산, 재화 흐름)의 연결은 보지 않는다.

## 다음 단계

OpenSpec으로 구현을 관리하면 [scope-guard](../scope-guard/SKILL.md)로 변경을 시스템에 잇는다. 순서대로 구현하고, 레벨은 [level-design](../level-design/SKILL.md)으로, 수치는 밸런스 스킬로 적는다. 그래픽 없는 프로토타입을 플레이하고 [playtest-verdict](../playtest-verdict/SKILL.md)로 기록한다.

예시: `studio-data/assets/sample-project/design/systems.json` (실제 게임 시스템이 아니다).
