---
name: art-handoff
description: "Collects what the design layer knows that the art side needs: what players must tell apart on screen (from the hypothesis word table, play questions and the information the rules show before a choice), which hypotheses lean on each item, and the list of things to draw copied from data ids. Writes design/art-handoff.md and has the user decide whether art direction comes before or after the main-build recheck. Use after the engine is chosen and before building the main-game screen for the recheck (production-handoff step 7), or when a rule or data change adds, removes or renames something players must read. It does not choose style, palette or colors."
---

# 그림에 넘길 것

설계 층이 아는 것 중 그림을 그리는 쪽이 알아야 할 것을 `design/art-handoff.md` 한 파일에 모은다. 그림체와 색은 정하지 않는다. 그것은 그림 쪽의 일이다(game-art-skills를 쓰면 그 `art-direction` 스킬). 이 스킬은 절차 문서이고 검사기가 없다.

도구 명령은 게임 프로젝트 폴더에서 Claude Code 설치 기준(`.claude/skills/…`)으로 적었다. Codex는 `.agents/skills/…`, Windows PowerShell은 `python3` 대신 `py`([실행 경로](../studio-data/SKILL.md#실행)).

## 원칙

- **읽힘은 가설에서 나온다.** 판정이 기댄 정보를 그림이 가리거나 바꾸면, 그 판정은 옛 화면의 것이 된다. 그래서 항목마다 기대는 가설을 적는다.
- **그릴 것은 데이터에서 옮긴다.** 카드, 적, 아이템은 `data/*.json`의 id를 옮겨 적는다. 손으로 세거나 기억으로 적지 않는다.
- **지금 것만 적는다.** 시험판 화면에서 지금 무엇으로 구분되는지(글자, 색, 모양)를 적고, 새 색이나 그림을 제안하지 않는다.
- **사람이 정한다.** 그림 방향을 다시 확인 전에 정할지 뒤에 정할지, 읽힘이 바뀐 뒤 다시 확인할지는 사용자가 정한다.

## 쓰지 않을 때

- 가설이 아직 판정되지 않았다: 시험판은 회색 상자로 충분하다. [playtest-verdict](../playtest-verdict/SKILL.md)로 먼저 판정한다.
- 엔진을 아직 정하지 않았다: [production-handoff](../production-handoff/SKILL.md)의 1~4단계를 먼저 한다.

## 이럴 때 읽을 곳

| 이럴 때 | 읽을 곳 |
|---|---|
| `design/art-handoff.md`를 쓸 때 | [references/handoff-record.md](references/handoff-record.md) |
| 그림이나 화면이 바뀌어 읽혀야 하는 것의 색, 단서, 놓이는 곳이 달라졌을 때 | [references/after-art-change.md](references/after-art-change.md) |

## 흐름

### 1. 읽혀야 하는 것을 모은다

플레이어가 화면에서 알아보고 서로 구분해야 하는 것이다. 세 곳에서 모은다.

- **가설:** [playtest-verdict 1단계](../playtest-verdict/SKILL.md#1-플레이-전-가설에-id와-최소-표본을-단다)의 '플레이어가 판단해야 하는 말'에서 만든 말 인용 표의 말과 그 화면 문구, 그리고 플레이 중 묻는 질문이 기대는 말. 표가 없으면 그 절대로 지금 만든다. "없음"으로 남은 말은 사용자가 정할 때까지 항목에 넣고 지금 단서를 "없음"으로 적는다.
- **규칙:** `design/systems.json`의 시스템에서 플레이어가 고르기 전에 보는 정보(적의 다음 행동, 남은 자원, 카드의 계열).
- **시험판 화면:** 지금 색, 글자, 모양으로 구분해 보이는 것. 위 둘에서 나오지 않으면 그림에 넘길지 사용자에게 묻는다.

항목마다 id, 뜻, 묶음(서로 구분해야 하는 것끼리 같은 이름), 놓이는 곳(화면의 어디, 무엇 위에), 언제 보여야 하나(예: 카드를 고르기 전), 지금 단서, 출처를 적는다. 형식은 [handoff-record.md](references/handoff-record.md).

### 2. 기대는 가설을 잇는다

항목마다 그 읽힘에 판정이 기대는 가설 id를 적는다. 이 스킬을 쓸 때는 원래 가설만 있다. 7단계에서 `_main` 가설을 더하면 그 원래 가설이 적힌 항목마다 `_main` id도 더한다. 1단계에서 가설의 말로 모은 항목은 그 가설이다. 규칙이나 화면에서 모은 항목은 그 가설의 `test`가 그 정보를 보고 하는 선택이나 대답을 세는지 보고 정한다. 기대는 가설이 없으면 "없음"이라고 적는다. 그런 항목은 그림이 바꿔도 다시 확인할 까닭이 없다.

### 3. 그릴 것을 데이터에서 옮긴다

`data/*.json`에서 화면에 하나씩 그려지는 항목(카드, 적, 아이템처럼 `id`가 있는 배열)을 파일, 배열 경로, `id` 목록으로 옮긴다. 개수를 따로 적지 않는다(데이터가 바뀌면 틀린다). 데이터에 안 쓰는 항목 표시(`status` 같은 칸)가 있으면 그 값을 함께 옮긴다. 데이터 밖에서 그릴 것(예고 아이콘, 화면 틀, 배경)은 1단계 항목과 규칙에서 따로 적는다. 여러 항목이 같은 그림을 나눠 쓰면(계열마다 같은 테두리) 묶어 적는다.

### 4. 그림 방향을 언제 정할지 사용자가 정한다

production-handoff 7단계의 다시 확인 화면과 그림 방향의 순서다. 두 길을 보이고 사용자가 고른다. 고른 길은 기록에 `[결정: 사용자 날짜]`로 적는다.

- **다시 확인 전:** 그림 방향(의미 색과 단서)을 먼저 정하고, 7단계 화면에 그 색과 단서를 넣어 다시 확인한다. 정한 색과 단서는 game-art-skills를 쓰면 그 파일(`art/direction.json`)을 가리키고, 쓰지 않으면 항목마다 기록의 '정한 색과 단서'에 적는다. 다시 확인이 바뀐 읽힘까지 함께 본다. 최종 그림은 그 뒤에 그려도 색과 단서를 지키면 된다.
- **다시 확인 뒤:** 7단계 화면은 지금 단서로 만든다. 뒤에 그림이 기대는 가설이 있는 항목을 바꾸면 [그림이 바뀌었을 때](references/after-art-change.md)를 따른다.

7단계를 이미 마쳤으면 다시 확인 뒤 길만 남는다.

### 5. 넘긴다

- game-art-skills를 쓰면 `art-direction`에 이 파일을 준다. 1단계 항목은 그쪽의 의미(`meanings`)가 된다: id → `id`, 뜻 → `what`, 묶음 → `group`, 놓이는 곳 → `on`(그쪽에서 배경 색 이름으로 고른다), 지금 단서 → `cue`의 출발점, 출처와 기대는 가설 → `source`.
- 사람에게 맡기면 이 파일을 그대로 준다.

## 보고

- 읽혀야 하는 것 표와 그중 기대는 가설이 있는 항목
- 말 인용 표에서 "없음"으로 남아 사용자가 정할 말
- 그릴 것 표(데이터 파일과 배열 경로)
- 사용자가 정할 것 한 가지(4단계의 순서, 또는 정할 말)

## 한계

- 검사기가 없다. 항목을 빠뜨렸는지, 기대는 가설이 맞는지는 도구가 보지 않는다.
- 사운드와 손맛(진동, 화면 흔들림)은 다루지 않는다.
- 그림 쪽 스킬은 이 파일을 스스로 읽지 않는다. 넘길 때 에이전트가 옮긴다.
