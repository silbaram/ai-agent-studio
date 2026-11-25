---
name: content-ideas
description: "Proposes game content (classes, skills, cards, enemies, items) with the user. It first proposes design laws from genre research, each with sources, the pillar it serves and whether it is required, then offers two or three structurally different sets that follow the accepted laws, refines one with the user, and hands on only pillar-level claims as hypotheses, new rules to system design and numbers to data as [가정]. Use when the user asks what classes, skills, cards or other content a game should have, when the user throws a seed idea for a new kind of content, or before editing the brief or adding a hypothesis because of a new content direction."
license: MIT
---

# 내용 제안

게임에 넣을 내용(직업, 스킬, 카드 계열, 적, 아이템)을 함께 짠다. 에이전트는 장르를 조사해 좋은 내용이 지키는 **법칙**을 먼저 제안하고, 그 법칙을 따르는 안을 낸다. 사용자는 법칙과 안을 고치고 고른다.

## 원칙

- **법칙 먼저.** 안을 고칠 때 취향 대신 "어느 법칙에 어긋나나"로 이야기하려고 법칙을 먼저 맞춘다.
- **사용자의 씨앗이 중심이다.** 사용자가 던진 아이디어는 한 벌의 중심에 두고 갈아 치우지 않는다. 바꾸자는 제안은 다른 벌로 따로 내고, 까닭을 법칙으로 댄다.
- **구조가 달라야 다른 안이다.** 이름과 테마만 다른 벌은 같은 벌이다([컨셉 탐색의 원칙](../concept-exploration/SKILL.md#원칙)과 같은 기준).
- **재미를 판정하지 않는다.** 어느 법칙을 따르는지, 어떤 위험이 있는지만 말한다.
- **고르는 것은 사용자다.** 추천은 받아들인 법칙으로 까닭을 댈 수 있을 때만 한다. 댈 수 없으면(벌들의 법칙 대조가 같다) 추천 줄은 [정할 것](../studio-data/references/telling-the-user.md#정할-것)의 추천하지 않는 곳 문장으로 쓴다.
- **기록은 한 곳.** `design/content/<주제>.md` 하나다. 밸런스 수치는 적지 않는다. 모양은 [references/record.md](references/record.md).

## 쓰지 않을 때

- 게임 자체의 아이디어를 찾는다: [concept-exploration](../concept-exploration/SKILL.md)
- 이미 정한 내용의 숫자를 정한다: [stat-budget](../stat-budget/SKILL.md), [combat-balance](../combat-balance/SKILL.md)
- 이미 정한 내용을 시스템 규칙으로 적는다: [system-design](../system-design/SKILL.md)

## 이럴 때 읽을 곳

| 이럴 때 | 읽을 곳 |
|---|---|
| 같은 주제에 내용을 더한다(셋째 직업) | [다시 열 때](references/record.md#다시-열-때) |
| 받아들인 법칙을 바꾸자는 말이 나왔다 | [법칙을 바꿀 때](references/record.md#법칙을-바꿀-때) |
| 웹 조사를 할 수 없다 | [조사를 못 할 때](references/research.md#조사를-못-할-때) |
| 다른 스킬의 브리프 편집 중에 불려 왔다 | [그 절](references/when-called.md#다른-스킬의-편집-중에-불려-왔을-때) |
| 본 게임을 만드는 중에 불려 왔다 | [그 절](references/when-called.md#본-게임에서-불려-왔을-때) |

## 흐름

### 1. 무엇을 정하는지 맞춘다

- [`check .`](../studio-data/SKILL.md)로 먼저 판정과 경고를 본다. 판정의 원본은 `data/playtests.json`이고 `design/production.md`가 아니다. 판정이 있으면 [그 절](references/when-called.md#가설에-판정이-있을-때)을 따른다.
- 내용의 종류, 이번에 정할 개수(열어 두면 벌마다 다르다), 정하지 않을 것을 사용자와 맞춘다.
- 사용자가 씨앗을 던졌으면 사용자의 말 그대로 먼저 적는다.
- 브리프(필러, 안티필러, MVP, 범위 밖), `design/systems.json`, `data/`를 읽는다. 브리프가 없으면 법칙을 필러에 대지 못한다고 말하고 [concept-exploration](../concept-exploration/SKILL.md)부터 권한다.
- 정하려는 내용이 브리프의 MVP 밖이거나 범위 밖 목록에 걸리면 처음에 그렇다고 말한다. 범위를 넓힐지, 나중 것으로 두고 짤지는 사용자가 정한다. 나중 것이면 5단계에서 시스템은 `scope: later`로만 적고 가설과 수치는 더하지 않는다.

### 2. 조사하고 법칙을 제안한다

- 장르와 비슷한 게임을 조사해 법칙 다섯에서 일곱 개를 제안한다. 조사하는 법은 [references/research.md](references/research.md)에 있다.
- 법칙마다 [법칙의 틀](references/research.md#법칙이란)을 모두 채운다. 걸러지는 예를 댈 수 없는 법칙은 아무것도 거르지 못하므로 내지 않는다.
- 필러나 안티필러와 부딪는 법칙은 빼지 않고 부딪는다고 표시한다. 이 게임에서는 필러가 이긴다.
- 사용자가 받아들이고 고치고 빼고 더한다. 받아들인 법칙만 쓴다.

### 3. 법칙을 따르는 벌을 낸다

- 두세 벌을 낸다. 벌끼리는 구조가 다르다. 갈리는 축의 예: 동사, 위험을 지는 쪽, 공유하는 것, 열어 둔 개수.
- 씨앗이 있으면 첫 벌은 씨앗 벌이다. 씨앗 벌은 필수 법칙을 어겨도 낸다. 어긴 곳은 충돌로 표시하고, 씨앗과 법칙 중 무엇을 고칠지 사용자가 정한다. 씨앗에 항목만 더한 것은 구조가 같아 씨앗 벌의 변형으로 그 안에 적는다. 나머지 벌은 씨앗과 다른 축으로 가른다.
- 벌의 항목 표와 법칙 대조 줄은 [벌의 모양](references/record.md#벌의-모양)대로 적는다. 법칙을 일부러 어긴 곳도 그 모양대로 표시한다.

### 4. 같이 다듬는다

- 사용자가 고르거나 섞거나 고친다. 바뀐 곳마다 받아들인 법칙에 대 보고, 어긋나면 어느 법칙인지 말한다.
- 안 대신 법칙을 고칠 수도 있다. [법칙을 바꿀 때](references/record.md#법칙을-바꿀-때)를 따른다.
- 다시 보일 때는 바뀐 줄만.

### 5. 가르고 넘긴다

**브리프를 먼저 맞춘다.** 범위는 1단계에서 정한 대로 [concept-exploration](../concept-exploration/SKILL.md)에서 고친다. 고른 벌이 필러를 바꾸면 사용자에게 묻는다. 필러 이름을 바꾸면 `design/systems.json`의 `pillars`도 함께 고친다. OpenSpec을 쓰면 [scope-guard](../scope-guard/SKILL.md)가 그 변경을 본다. 그다음 고른 벌을 넷으로 가른다. 무거운 검증 길은 첫째에만 쓴다.

1. **필러를 건드리는 주장.** 플레이어가 이렇게 할 것이라는 주장이고, 필러가 거기에 기대며, 틀리면 이 내용을 다시 짜야 하는 것이다. 예: "직업마다 이동의 역할이 다르다". 브리프에 이미 있는 가설이 같은 행동을 보면 새 가설을 만들지 않고 그 가설로 시험한다. 없을 때만 [가설의 모양](../concept-exploration/references/brief.md#가설-hypotheses-1개-이상)대로 더하자고 사용자에게 묻는다. 여럿이면 가장 위험한 하나부터 권한다.
2. **새 규칙.** [system-design](../system-design/SKILL.md)의 `rules`로 옮긴다.
3. **수치.** 체력, 속도, 쿨다운 같은 값이다. `data/`에 `[가정]`으로 둔다([numeric-provenance](../numeric-provenance/SKILL.md#태그)). 티어 곡선이 있으면 [stat-budget](../stat-budget/SKILL.md)의 초안으로 시작한다.
4. **나머지.** 생김새, 이름, 화면에서 무엇으로 구분되는지 같은 것이다. 기록에만 남기고 가설로 만들지 않는다. 화면 구분은 나중에 [art-handoff](../art-handoff/SKILL.md)가 모은다.

넘긴 곳은 기록의 '넘긴 곳'에 적는다.

## 보고

- 첫 줄은 지금 위치, 정할 것도 [이 모양](../studio-data/references/telling-the-user.md)대로
- 2단계: 법칙마다 틀대로, 조사하지 못했으면 그 사실
- 3·4단계: 벌마다 항목 표와 법칙 대조 줄, 씨앗 벌의 충돌
- 5단계: 넷으로 가른 목록, 사용자에게 물을 브리프 변경, 기록 파일 경로

## 한계

- 검사기가 없다. `check`는 기록 파일을 보지 않는다.
- 법칙은 장르의 통념이다. 이 게임에서 맞는지는 플레이가 가린다.
- 출처의 질은 에이전트가 고른다.
