---
name: production-milestones
description: "Guides the real game from production start to a release candidate in three milestones: alpha (every MVP system built and the main-build verdicts final), beta (content grown to a planned count while held verdicts stay current, then a content freeze and a polish pass that turns the remaining [가정] numbers into measured or decided values) and release candidate (a short gate sized for a free release, with extra lines when selling). Held verdicts carry a fingerprint of the game data; when it changes, the same-seed bots are rerun and the user either has a person play again or carries the verdict over. Records each milestone in design/production.md. Use after production-handoff ends with proceed, when adding cards, enemies or levels to the real game, when check reports verdict_data_changed or verdict_data_missing, or when the user asks whether the game is ready to release."
license: MIT
---

# 본 게임 완성까지

[production-handoff](../production-handoff/SKILL.md)의 넘어가기 판정이 "진행"이면 본 게임을 만든다. 이 스킬은 그 뒤부터 출시 후보까지를 세 이정표(알파, 베타, 출시 후보)로 나눈다. 절차 문서다(도구가 보는 것은 아래 '한계'). 나머지 확인을 건너뛰면 아무도 알려 주지 않는다.

도구 명령은 게임 프로젝트 폴더에서 Claude Code 설치 기준(`.claude/skills/…`)으로 적었다. Codex는 `.agents/skills/…`, Windows PowerShell은 `python3` 대신 `py`([실행 경로](../studio-data/SKILL.md#실행)).

## 원칙

- **사람이 정한다.** 이정표를 넘을지, 콘텐츠를 몇 개까지 늘릴지, 낡은 판정을 이어 갈지, 언제 콘텐츠를 동결할지, 무료로 낼지 팔지는 사용자가 정한다. 에이전트는 확인 결과와 한두 개의 추천을 내놓는다.
- **판정은 지금 데이터의 것이어야 한다.** 버팀 판정에는 판정할 때의 게임 데이터 지문(`data`)을 남긴다. 그 뒤 카드, 적, 수치가 바뀌면 `check`가 알리고 게이트가 막는다.
- **봇은 사람의 판정을 대신하지 않는다.** 같은 시드로 봇을 다시 돌린 결과는 사람이 다시 플레이할지 정하는 근거일 뿐이다. 이어 간 판정의 근거는 사람이 플레이한 세션 그대로다.
- **하지 않은 확인은 통과가 아니다.** 확인하지 못한 줄은 `[?]`로 적는다. `[?]`가 하나라도 있으면 그 이정표를 넘지 않는다.
- **기록은 한 곳.** 이정표는 `design/production.md` 끝에 이어 쓴다. 형식은 [references/milestone-record.md](references/milestone-record.md).

## 쓰지 않을 때

- 아직 본 게임으로 넘어가지 않았다: [production-handoff](../production-handoff/SKILL.md)를 먼저 한다.
- 다시 확인(`_main`)에서 틀림이 나왔다: [규칙을 바꿀 때](../production-handoff/references/rule-change.md)를 따른다.
- 시험판에서 규칙을 바꿔 다시 시험한다: [다시 시험할 때](../playtest-verdict/references/changes.md#다시-시험할-때).

## 이럴 때 읽을 곳

| 이럴 때 | 읽을 곳 |
|---|---|
| 콘텐츠를 더할 때, `check`가 `verdict_data_changed`나 `verdict_data_missing`을 낼 때 | [references/content-growth.md](references/content-growth.md) |
| 새 종류의 내용(새 직업, 새 카드 계열)을 넣거나, 무엇을 더할지 정한다 | [content-ideas](../content-ideas/SKILL.md)의 [본 게임에서 불려 왔을 때](../content-ideas/references/when-called.md#본-게임에서-불려-왔을-때) |
| 출시 후보 게이트를 볼 때 | [references/release-gate.md](references/release-gate.md) |
| `design/production.md`에 이정표를 적을 때 | [references/milestone-record.md](references/milestone-record.md) |

## 흐름

| 단계 | 끝내는 조건 | 사용자가 정하는 것 |
|---|---|---|
| 1. 알파 | MVP 시스템이 모두 본 게임에 있다. 버틴 가설의 판정이 지금 데이터의 것이다 | 진행 / 되돌아가기 / 그만두기 |
| 2. 콘텐츠 늘리기 | 계획한 수와 데이터의 수가 같다. 낡은 판정이 없다 | 계획한 수, 낡은 판정마다 다시 플레이 / 이어 감 |
| 3. 베타 | 콘텐츠를 동결했다. 숫자의 `[가정]`이 남지 않았다 | 동결, 남은 `[가정]` 값 |
| 4. 출시 후보 | 출시 게이트의 모든 줄이 통과다 | 무료 / 판매, 출시 / 되돌아가기 / 그만두기 |

되돌아가면 앞 단계로 간다. 되돌아간 횟수를 기록에 센다. 되풀이되면 그 자체를 사용자에게 알린다.

### 1. 알파: 기능 완료

새 시스템을 더 만들지 않아도 되는 때다. 아래를 하나씩 확인하고 기록의 '알파' 표에 적는다.

```bash
python3 .claude/skills/studio-data/scripts/studio.py check . --fail-on-assumed
```

- `design/systems.json`의 MVP 시스템마다 본 게임에서 그것을 만든 곳(OpenSpec 변경 이름이나 코드 경로)을 적는다. 찾지 못하면 `[?]`다. production.md의 '가설 없이 만드는 MVP 시스템'도 같이 본다.
- 플레이 기록의 gate 줄이 [넘어갈 준비](../production-handoff/SKILL.md#1-넘어갈-준비가-됐는지-본다)의 첫 두 줄을 지킨다. 이제는 `_main` 가설도 남지 않는다. 숫자의 `[가정]` 줄은 거기서처럼 조건이 아니고 3단계에서 다듬는다.
- 가설에 `(데이터 지문 없음)`이나 `(플레이 때 지문 없음)`이 붙었으면 [지문 없는 판정](references/content-growth.md#지문-없는-판정)을, `(데이터 바뀜)`이면 [낡은 판정 풀기](references/content-growth.md#낡은-판정-풀기)를 따른다.

### 2. 콘텐츠를 늘린다

1. **계획한 수.** 콘텐츠 종류(카드, 적, 레벨, 아이템)마다 지금 수와 출시 때 수를 사용자와 정해 `[결정: 사용자 날짜]`로 적는다. 근거는 브리프의 범위와 한 판 길이에서 찾는다. 지금 수는 손으로 세지 않는다. `check`가 개수를 보이는 데이터 종류(아이템, 적, 레벨 등)는 그 수를 옮기고, `check`가 모르는 게임 고유 파일은 게임 쪽 스크립트로 세어 결과 파일을 남기고 `[계산: 스크립트]`로 적는다.
2. **묶음으로 더한다.** 한 번에 한 종류를 몇 개씩 더한다. 새 항목의 숫자는 지금의 밸런스 스킬로 정한다([stat-budget](../stat-budget/SKILL.md)의 초안, [combat-balance](../combat-balance/SKILL.md)의 처치 시간, [level-design](../level-design/SKILL.md)). 목표 범위가 없는 값은 판정하지 않고 `[가정]`으로 둔다.
3. **묶음마다 `check`를 본다.** 데이터가 바뀌었으므로 버틴 가설의 판정이 `(데이터 바뀜)`으로 게이트에 걸린다. 다음 묶음으로 가기 전에 [낡은 판정 풀기](references/content-growth.md#낡은-판정-풀기)로 푼다. 묶음을 여럿 쌓은 뒤 한꺼번에 풀면 어느 묶음이 재미를 바꿨는지 가를 수 없다.
4. **항목별로 센다.** 판 로그에 고른 것이 남으면 [항목별로 세기](references/content-growth.md#항목별로-세기)대로 한 번도 고르지 않은 항목과 늘 고른 항목을 보인다. 이것은 판정이 아니라 사용자에게 보이는 참고다.

계획한 수에 닿고 낡은 판정이 없으면 베타로 간다.

### 3. 베타: 콘텐츠 동결과 다듬기

사용자가 콘텐츠 동결을 정한다(`[결정: 사용자 날짜]`). 동결 뒤에는 새 항목을 더하지 않고 고침과 숫자 다듬기만 한다. 새 항목이 필요하면 2단계로 되돌아간다.

- **다듬기는 숫자를 정하는 일이다.** `check --fail-on-assumed`의 데이터 파일 gate 줄(숫자의 `[가정]`)이 빌 때까지, 값마다 플레이 기록에서 잰 `[측정]`([playtest-verdict 4단계](../playtest-verdict/SKILL.md#4-측정값을-올린다), [보정](../playtest-verdict/references/calibration.md))이나 사용자가 정한 `[결정]`으로 바꾼다. 값을 바꾸면 2단계와 같이 낡은 판정을 푼다(출처만 바꾼 것은 판정을 낡게 하지 않는다).
- **화면과 소리만 다듬었으면 규칙이 그대로인지 본다.** 같은 시드·같은 봇의 결과가 다듬기 전과 같아야 한다. 다르면 다듬기가 규칙을 건드렸다.
- **다듬기 목록의 줄마다 어디서 나왔는지 적는다.** 검사 줄, 플레이 메모, 사용자의 말 중 하나다. 그것이 없는 줄은 넣지 않는다.
- **다른 사람의 플레이.** 처음 보는 사람이 막히는 곳(관찰)과 가설의 수치(판 로그)를 나눠 적는다. 관찰은 세션 `notes`의 `observation`이고 판정의 근거가 아니다. 몇 명에게 받을지는 사용자가 정한다. 설계자 혼자 했으면 그것을 한계로 기록에 남긴다. 모집할 길(브라우저 빌드 링크, 플랫폼의 시험 기능)은 알리기만 한다.

### 4. 출시 후보

사용자가 출시 목표(무료 공개 / 판매)를 정한다. [출시 게이트](references/release-gate.md)의 줄마다 통과, 실패, `[?]`를 근거와 함께 적는다. 판매면 '판매할 때 더하는 것'도 본다. 실패나 `[?]`가 하나라도 있으면 출시 후보가 아니다.

결과는 셋 중 하나이고 사용자가 정한다: **출시**, **되돌아가기**(막힌 줄을 풀러 앞 단계로), **그만두기**.

## 출시 뒤

운영(시즌, 이벤트)은 다루지 않는다. 패치도 2단계처럼 낡은 판정을 풀고 출시 게이트를 다시 지난 뒤 낸다. 플레이 기록을 밖으로 받으면 동의한 사람의 것만 받는다.

## 보고

- 첫 줄은 지금 위치, 정할 것도 [이 모양](../studio-data/references/telling-the-user.md)대로
- 지금 이정표와 끝내는 조건마다 결과(`[?]`는 그렇다고)
- 낡은 판정마다 회귀 결과와 제안(다시 플레이 / 이어 감)
- 사용자가 정할 것 한 가지(흐름 표의 '사용자가 정하는 것' 중 지금 차례인 것)

## 한계

- 도구가 보는 것은 버팀 판정의 데이터 지문과 이어 간 판정([검사 내용](../playtest-verdict/references/playtest-record.md#검사-내용)), 숫자 출처 게이트뿐이다. 시스템을 만들었는지, 계획한 수, 출시 게이트의 줄은 도구가 보지 않는다.
- 데이터 지문은 데이터 파일만 본다([판정의 `data`](../playtest-verdict/references/playtest-record.md#판정-verdicts)). 규칙 코드만 바꾸면 알지 못한다([규칙 코드도 적을 수 있다](references/content-growth.md#판정의-데이터-지문), [규칙을 바꿀 때](../production-handoff/references/rule-change.md)).
- 엔진별 빌드, 스토어 등록, 플랫폼 심사 절차는 다루지 않는다.
