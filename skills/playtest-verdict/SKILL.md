---
name: playtest-verdict
description: "Records prototype playtest sessions as data, has a read-only judge propose a verdict (holds, refuted, unknown) for each concept hypothesis from those records, promotes measured numbers from assumed to measured with a checkable source, and calibrates assumptions from recorded stage statistics: compares assumed levels, durations, kills, and income with the records, compares simulated stage clear rates with measured ones, and suggests survival curve values. Use after playing a prototype, when deciding whether a concept's hypotheses survived, before turning an assumed number into a measured one, or when checking balance assumptions against real runs."
---

# 플레이 기록과 가설 판정

프로토타입을 플레이한 기록을 데이터로 남기고, 브리프의 가설이 버텼는지 **기록만 보고** 판정한다. 목적은 "해 보니 재미있었다"가 증거처럼 쓰이는 것을 막는 것이다. 재미를 점수로 매기지 않는다.

## 원칙

- **기록이 증거다.** 판정은 `data/playtests.json`에 적힌 관찰값만 근거로 쓴다. 대화에서 들은 인상, 만든 쪽의 설명, 에이전트의 추측은 증거가 아니다.
- **관찰과 선호를 나눈다.** "3판부터 예고를 안 보고 거리만 벌렸다"는 관찰이다. "재미있다", "소리가 좋다"는 선호다. 선호는 `notes`에 `preference`로 남기되 판정 근거로 쓰지 않는다.
- **모르면 unknown이다.** 표본이 계획보다 적거나, 신호가 나왔는지 기록으로 가릴 수 없으면 `unknown`이다. unknown은 실패가 아니다.
- **값을 지어내지 않는다.** 관찰값은 플레이한 사람이 말한 것이나 로그 파일에서 읽은 것만 적는다. 에이전트가 짐작한 값을 관찰값으로 적지 않는다.
- **판정은 따로, 확정은 사용자가.** 판정 에이전트(읽기 전용)가 제안하고, 메인 에이전트가 `proposed`로 기록하고, 사용자가 확인하면 `approved`로 바꾼다.

## 도구

검사는 공용 스킬 [studio-data](../studio-data/SKILL.md)의 `studio.py`로 한다. 이 스킬과 함께 설치한다. 명령은 게임 프로젝트 폴더에서 Claude Code 설치 기준으로 적었다. Codex는 `.agents/skills/…`, Windows PowerShell은 `python3` 대신 `py`([실행 경로](../studio-data/SKILL.md#실행)).

| 명령 | 확인하는 것 | 확인하지 않는 것 |
|---|---|---|
| `python3 .claude/skills/studio-data/scripts/studio.py check .` | 판정이 근거 세션을 가리키는가, 그 세션이 있고 그 가설을 관찰했는가, 가설·컨셉 id가 맞는가, 세션의 판 수·사람 수 | 관찰값이 정말 틀렸다는 신호에 해당하는가 |
| `… check . --fail-on-assumed` | 선택한 컨셉의 가설 중 확정된 버팀·틀림이 아닌 것이 남았는가 | 가설이 좋은 가설인가 |
| `… provenance design/ --check-paths` | md의 `[측정: data/playtests.json#세션 id]` 세션이 실제 기록에 있는가. 컨셉 브리프의 같은 태그는 `check`가 본다 | 측정값을 옮겨 적을 때 틀리지 않았는가 |
| `… hypothesis <컨셉>.<가설>` | 가설 하나의 기준·기준 이력·판정·근거 세션의 그 가설 관찰값과 메모, 그 가설의 `check` 줄만 모아 출력. 기록 전체를 읽지 않고 판정·기록할 때 먼저 본다. 파일에 쓰지 않는다 | 관찰값이 맞는가 |
| `… runlog playtests/세션/runs.csv` | 판별 로그를 세션의 단계 기록으로 모아 출력(강화 상태별 묶음). 파일에 쓰지 않는다 | 로그가 맞는가 |
| `… calibrate data/meta_combat.json` | 가정값과 기록의 차이, 단계 통과율의 예측과 실측, 기록에 맞는 생존 곡선 값 제안 | 재미, 실제 난이도. 파일을 고치지 않는다 |

Claude Code에서는 한 번 `python3 .claude/skills/studio-data/scripts/studio.py setup claude .`를 실행해 판정 에이전트와 훅을 설치한다([setup](../studio-data/SKILL.md#claude-code-연결)). 스킬을 다시 설치한 뒤에도 다시 실행한다.

## 절차

### 1. 플레이 전: 가설에 id와 최소 표본을 단다

`design/concepts.json`에서 시험할 컨셉의 `brief.hypotheses`마다 `id`를 넣는다(소문자·숫자·밑줄, 예: `density_timing`). 기록과 판정은 이 id로 가설을 가리킨다. 문장을 바꿔도 id는 그대로 둔다.

시험 전에 가설마다 최소 표본(`"sample": {"players": 3, "runs": 15}`)과 기록할 값을 사용자와 정한다. 근거 세션을 합쳐 이보다 적으면 버팀·틀림 판정이 오류다(`verdict_sample_short`). 신호가 드문 사건(사망, 부화)의 건수에 기대면 그 최소 건수를 `sample.events`(`{"death_with_hatch": 6}`)에 적는다. 프로토타입이 기록할 값을 로그로 남기게 하면 옮겨 적는 실수가 줄어든다. 시험 조건(설정)이 여러 가지면 로그에 그 열을 두고 `runlog --group-by`로 나눠 모은다.

표본은 결과를 보기 전에 정한 값이다. 플레이 도중이나 뒤에 표본을 줄이자는 말이 나오면 바로 고치지 않는다. 가설마다 사용자에게 묻고, 결과 파일을 열기 전에 [표본을 줄이자는 말이 나올 때](references/changes.md#표본을-줄이자는-말이-나올-때)를 따른다.

판정 기준 문장에 남은 `[가정]` 잣대(문턱, 구간)도 플레이 전에 정한다. 결과를 본 뒤에 정하면 표본을 줄이는 것과 같은 문제가 생긴다. `check . --fail-on-assumed`의 컨셉 gate 줄이 남은 칸(`brief.hypotheses[…]`, `brief.prototype.success_criteria`)을 가리킨다. 그 줄은 값을 줄여 보이므로(`외 N개`), 사용자에게는 `hypothesis <컨셉>.<가설>`의 가설 문장과 브리프의 `success_criteria` 문장을 통째로 보이고 정하게 한다. 데이터 파일의 gate 줄(적 체력, 카드 피해)은 플레이로 맞출 값이라 여기서 정하지 않는다. 사용자가 정한 값만 바꾸는 법은 [4단계](#4-측정값을-올린다). 정하지 않은 채 플레이했는지는 2단계가 확인한다.

지표의 정의(구간 길이, 문턱, 무엇을 뺄지)는 가설의 `test`가 원본이다. 계산 스크립트에 같은 값을 상수로 두면, 결과 파일 첫머리에 계산에 쓴 정의를 찍게 한다. 한쪽만 바뀌어도 판정 에이전트가 `test`와 견줄 수 있다.

### 2. 플레이한 뒤: 세션을 기록한다

한 번 모여 플레이할 때마다 `data/playtests.json`의 `playtests`에 세션 하나를 넣는다. 형식은 [references/playtest-record.md](references/playtest-record.md).

- 날짜, 플레이한 사람, 빌드(커밋 해시), 판 수, 원본 로그 파일 경로(`logs`)
- 가설별 관찰값(`observations`): 가설의 `failure_signal`을 판단하는 데 필요한 값. 로그에서 읽었으면 `source`에 파일을 적는다. 스크립트로 계산한 값(비율, 상관)은 그 출력을 세션 폴더에 결과 파일로 남기고(예: `python3 game/summarize.py playtests/pt_20261107_1 > playtests/pt_20261107_1/summary.txt`) `source`를 그 결과 파일로 둔다. 판정 에이전트는 스크립트를 돌리지 못하므로(훅이 막는다) 결과 파일이 없으면 값을 확인할 수 없다
- 레벨의 그레이박스 확인 기록(`greybox`): `levels.json`의 항목 id마다 잰 값이나 판정. 항목은 `… check . --table levels`의 그레이박스 확인 표에 있다
- 가설의 `sample.events`에 적은 사건을 이 세션에서 센 건수(`events`)
- 그 밖의 관찰과 선호(`notes`). 시험 절차를 어긴 일은 `deviation`으로 적는다(무엇이 이탈인지는 [기록 형식](references/playtest-record.md)의 `notes`)

기록하기 전에 가설마다 `hypothesis <컨셉>.<가설>`로 지난 판정이 남긴 "다음 시험 전에 풀 것"과 판정 기준 문장에 남은 `[가정]` 잣대(1단계)를 본다. 플레이 전에 정했어야 할 것(지난 판정이 정하라고 한 것, 남은 잣대)이 있으면 플레이 전에 정했는지 묻고 답을 세션 `notes`에 적는다. 묻지 못했거나 정하지 않고 플레이했으면 `deviation`으로 적는다.

관찰값의 수는 결과 파일이나 로그의 수를 반올림하지 않고 그대로 옮긴다. 사용자에게 묻지 않고 채운 값이 있으면 그 사실을 보고한다. 기록 파일을 지우지 않는다. 여러 세션을 합쳐 다시 계산해야 나오는 값은 [형식](references/playtest-record.md#여러-세션을-합친-값)을 따른다.

### 3. 판정한다

- **Claude Code**: 판정 에이전트 `studio-judge`에게 맡긴다. 예: "studio-judge로 ripening_gems의 가설을 판정해 줘". 판정 에이전트는 파일을 고치지 못하고(훅이 막는다), 가설별 제안과 `verdicts`에 넣을 JSON을 돌려준다.
- **Codex 등 판정 에이전트가 없는 환경**: 같은 절차를 직접 따른다. 판정 기준은 [references/playtest-record.md](references/playtest-record.md#판정)이다. 만드는 쪽과 판정하는 쪽이 분리되지 않았다는 사실을 보고에 적는다.

받은 제안을 `verdicts`에 `"status": "proposed"`로 넣고 사용자에게 보여 준다. 사용자가 확인하면 `approved`로 바꾼다. 사용자는 버팀·틀림 제안을 모름으로 낮춰 확정할 수 있다(에이전트의 결과는 `proposed_result`에 남긴다). 모름을 버팀·틀림으로 올리거나 버팀과 틀림을 바꾸려면 사용자의 까닭을 판정 에이전트에게 주고 다시 판정한다. 다시 판정할 때는 지난 판정을 지우지 않는다. 지난 판정을 먼저 `cut`으로 바꾸고 같은 편집에서 새 판정을 넣는다. 이때 cut_reason에 그때 상태(확정·제안)를 적는다. 사용자가 새 제안을 받아들이지 않으면 새 제안을 지우고, 지난 판정의 `status`를 `cut_reason`에 적힌 상태로 되돌리고 `cut_reason`을 지운다.

판정 에이전트가 돌려준 기준 지문(`criteria`)을 그대로 기록한다. 판정 뒤에 가설 기준이 바뀌면 `verdict_criteria_changed`, 지문이 없으면 `verdict_criteria_missing`이고, 둘 다 확정해도 게이트를 넘지 못한다. 기준을 고친 것이면 [판정한 가설의 문장을 고칠 때](references/changes.md#판정한-가설의-문장을-고칠-때)를 따른다. 출처 태그만 바꾼 것은 바뀐 것이 아니다. `check`가 "예전 꼴" 참고 줄을 내면 그 줄의 지문으로 `criteria`를 바꿔 둔다. 지문이 없는 판정에는 판정한 뒤 가설을 고치지 않은 것이 확실할 때만 지금 지문을 적는다.

### 4. 측정값을 올린다

관찰값을 **그대로** 옮긴 수치만 `[가정]`에서 `[측정: data/playtests.json#세션 id]`로 바꾼다. 데이터 파일(아이템·강화·적)은 `provenance`를 `{"kind": "measured", "source": "data/playtests.json#세션 id"}`로 둔다. 한 항목의 값 일부만 기록으로 뒷받침되면 항목 전체를 바꾸지 않고 `provenance.fields`에 그 값만 적는다(`{"kind": "assumed", "fields": {"kills.crawler": {"kind": "measured", "source": "data/playtests.json#pt_20261108_3"}}}`). 모든 수치 칸에 가정이 아닌 출처가 붙으면 그 항목은 게이트에서 빠진다.

- 평균·비율을 새로 계산한 값은 `[계산: 스크립트 또는 결과 파일]`이다. 계산한 스크립트가 없으면 올리지 않는다.
- 판정 기준의 문턱값(예: `80% [가정]`)과 `test`의 시험 설계 값(표본, 구간)은 측정값이 아니다. 무엇이 틀림인지를 정하는 잣대라 측정으로 올리지 않는다. 사용자가 그 값을 정했으면 `[결정: 사용자 2026-11-09]`로 바꾼다. 에이전트가 정한 값은 `[가정]` 그대로다([numeric-provenance](../numeric-provenance/SKILL.md), [브리프](../concept-exploration/references/brief.md)).
- 판정 글(`reason`, `next_needs`, `cut_reason`)에는 문턱을 잣대 태그 없이 수치만 쓴다("사망 6건이 필요한데"). 출처는 브리프에 있고, 옮겨 적은 태그는 브리프를 고치면 어긋난다.
- 올린 뒤 `provenance design/ --check-paths`(md)와 `check .`(컨셉 브리프)로 세션이 실제로 있는지 확인한다.

### 5. 가정값을 보정한다

세션에 단계 기록과 그때 가진 영구 강화를 적었으면 `calibrate`로 기획의 가정값과 비교한다. 평균을 손으로 내지 않는다. 프로토타입의 판별 로그(CSV)는 `runlog`로 모아 세션에 합친다. 시간이 다 되면 끝나는 단계(5분 회색 상자)는 `runlog --timed 단계`로 모은다. 형식, 시험 조건별로 보기, 읽는 법, 제안을 옮기는 순서는 [references/calibration.md](references/calibration.md).

```bash
python3 .claude/skills/studio-data/scripts/studio.py runlog playtests/pt_20261112_1/runs.csv
python3 .claude/skills/studio-data/scripts/studio.py calibrate data/meta_combat.json --out reports/calibrate.json
```

제안은 자동으로 적용하지 않는다. 사용자에게 보여 주고 어느 값을 옮길지 정한다. 레벨을 먼저 옮기고 생존 곡선을 옮긴다. 옮긴 값에는 출처를 남긴다. 기획 목표 범위는 의도이므로 바꾸지 않는다.

### 6. 틀렸으면 되돌아간다

`refuted`가 확정되면 다음 중 하나를 사용자에게 제안한다. 결정은 사용자가 한다. 선택한 컨셉의 가설이 틀림으로 확정된 동안은 `approved_concept_refuted` 경고가 나고 `--fail-on-assumed`가 실패한다.

- 가설이 기대는 규칙 하나를 바꿔 다시 시험한다. 순서는 [다시 시험할 때](references/changes.md#다시-시험할-때).
- 컨셉을 되돌린다(`proposed`, 탈락 사유가 증명되었으면 `hard_reject`와 함께 `cut`). 순서는 [컨셉을 되돌릴 때](references/changes.md#컨셉을-되돌릴-때).
- `unknown`이면 무엇이 부족했는지(표본, 기록하지 못한 값)를 다음 세션 계획으로 남긴다.

## 기준이나 컨셉을 바꿀 때

순서는 [references/changes.md](references/changes.md)에 있다. 해당하는 절을 읽고 따른다.

| 이럴 때 | 읽을 절 |
|---|---|
| 플레이 도중이나 뒤에 표본을 줄이자는 말이 나왔다 | [표본을 줄이자는 말이 나올 때](references/changes.md#표본을-줄이자는-말이-나올-때) |
| 판정한 가설의 문장을 고친다(맞춤법, 옮겨 적은 수치나 데이터 파일 경로 지우기) | [판정한 가설의 문장을 고칠 때](references/changes.md#판정한-가설의-문장을-고칠-때) |
| 기준을 고칠 때 `criteria_history`를 남기지 못했다 | [이력을 나중에 남길 때](references/changes.md#이력을-나중에-남길-때) |
| 틀림 뒤 규칙 하나를 바꿔 다시 시험한다 | [다시 시험할 때](references/changes.md#다시-시험할-때) |
| 선택한 컨셉을 되돌린다 | [컨셉을 되돌릴 때](references/changes.md#컨셉을-되돌릴-때) |
| 다른 시스템이 바뀌어 지난 기록을 함께 세면 안 된다 | [다른 시스템이 바뀌어 지난 기록과 합치지 않을 때](references/changes.md#다른-시스템이-바뀌어-지난-기록과-합치지-않을-때) |

## 보고

- `check` 결과 그대로: 판정별 버팀·틀림·모름, 그 가설을 관찰한 근거 세션 수·판 수·사람 수와 최소 표본(`9/9판 · 1/1명`), 사건 수, 절차 이탈 수, 오류·경고 수, `INCOMPLETE` 여부
- 확정되지 않은 가설 목록(`--fail-on-assumed`의 gate 줄)
- 이번에 `[측정]`으로 올린 수치와 그 출처
- `calibrate`를 돌렸으면: 쓴 세션과 표본, 표시된 차이, 구간을 벗어난 단계, 제안과 옮긴 값
- 사용자 확인이 필요한 것: 제안 판정의 확정, 틀린 가설 이후의 방향
- 실행하지 못한 검사가 있으면 그 사실

## 한계

- 검사기는 판정이 **증거를 가리키는지**만 본다. 관찰값이 틀렸다는 신호에 해당하는지는 판정 에이전트와 사용자가 본다.
- 표본은 가설의 `sample`에 적은 사람 수, 판 수, 사건 수만 숫자로 막는다. 설정별 판 수는 막지 않으므로 판정 에이전트가 `test`와 견준다. 세는 방법은 [형식](references/playtest-record.md#검사-내용)의 `verdict_sample_short`, `verdict_events_short`.
- 절차 이탈은 적은 것만 센다. 이탈이 판정을 바꾸는지는 판정 에이전트와 사용자가 본다.
- 관찰값과 결과 파일은 수만 맞춰 본다. 수가 있어도 다른 설정이나 다른 칸의 수일 수 있다.
- 보정 값은 기록한 빌드와 플레이어에서 나온 값이다. 보정해도 시뮬레이션 결과로 재미나 실제 난이도를 판정하지 않는다.
- 판정 에이전트와 훅은 Claude Code 전용이다. 훅 입력의 에이전트 이름(`agent_type`)으로 판정 에이전트를 구분한다(확인한 범위는 [studio-data](../studio-data/SKILL.md#claude-code-연결)).

예시: `studio-data/assets/sample-project/data/playtests.json` (실제 플레이 기록이 아니다).
