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
| `… runlog playtests/세션/runs.csv` | 판별 로그를 세션의 단계 기록으로 모아 출력(강화 상태별 묶음). 파일에 쓰지 않는다 | 로그가 맞는가 |
| `… calibrate data/meta_combat.json` | 가정값과 기록의 차이, 단계 통과율의 예측과 실측, 기록에 맞는 생존 곡선 값 제안 | 재미, 실제 난이도. 파일을 고치지 않는다 |

Claude Code에서는 한 번 `python3 .claude/skills/studio-data/scripts/studio.py setup claude .`를 실행해 판정 에이전트와 훅을 설치한다([setup](../studio-data/SKILL.md#claude-code-연결)). 스킬을 다시 설치한 뒤에도 다시 실행한다.

## 절차

### 1. 플레이 전: 가설에 id와 최소 표본을 단다

`design/concepts.json`에서 시험할 컨셉의 `brief.hypotheses`마다 `id`를 넣는다(소문자·숫자·밑줄, 예: `density_timing`). 기록과 판정은 이 id로 가설을 가리킨다. 문장을 바꿔도 id는 그대로 둔다.

시험 전에 가설마다 최소 표본(`"sample": {"players": 3, "runs": 15}`)과 기록할 값을 사용자와 정한다. 표본은 확정 판정에 필요한 사람 수와 판 수이고, 근거 세션을 합쳐 이보다 적으면 버팀·틀림 판정이 오류다(`verdict_sample_short`). 신호가 드문 사건(사망, 부화)의 건수에 기대면 그 최소 건수를 `sample.events`(`{"death_with_hatch": 6}`)에 적는다. 사건 수가 모자란 버팀은 오류다(`verdict_events_short`). `check`는 id나 표본이 없는 가설을 경고한다. 프로토타입이 기록할 값을 로그로 남기게 하면 옮겨 적는 실수가 줄어든다. 시험 조건(설정)이 여러 가지면 로그에 그 열을 두고 `runlog --group-by`로 나눠 모은다.

표본을 줄이자는 말이 플레이 도중이나 뒤에 나오면 바로 고치지 않는다. 표본은 결과를 보기 전에 정한 값이다. 해 본 뒤에 줄이면 기록만 봐서는 "결과를 보고 멈춘 것"과 구별되지 않는다. 판정에는 새 기준 지문이 찍혀 `verdict_criteria_changed`도 나지 않는다. 먼저 줄이면 잃는 것을 보인다: 설정별 판 수, 사건 수, 지금 표본으로 낼 수 있는 판정(모자라면 모름뿐이다). 줄일지는 가설마다 사용자에게 묻는다. 한 가설 때문에 줄이자는 말을 다른 가설에 넓히지 않는다. 사용자가 줄이기로 한 가설만 결과 파일을 열기 전에 브리프부터 고친다. `sample`의 판 수와 함께 `test`·`failure_signal` 안의 같은 판 수("9판을 합쳐", "설정마다 3판")도 고친다. 그리고 `sample.reduced_from`에 줄이기 전 값과 때를 남긴다(`{"runs": 9, "after_run": 5, "before_results": true, "date": "2026-11-08"}`). 판정 줄에 `6/6판 (9판에서 줄임, 5판째 뒤)`처럼 보인다. 결과 파일을 연 뒤에 줄였으면 `before_results`를 `false`로 적는다. 그 가설은 버팀·틀림이 오류(`verdict_sample_reduced_after_results`)라 모름으로 둔다. 세션 메모에는 표본을 줄인 일을 `deviation`으로 적고 `hypotheses`에 그 가설 id를 적는다(그 가설의 판정에만 절차 이탈로 센다): 몇 판째 뒤에 바꿨는지, 플레이한 사람과 기록하는 에이전트가 각각 요약 값을 보기 전인지 뒤인지. 사용자가 정하지 않은 축소(기록하던 에이전트가 고친 것)는 `reduced_from`으로 남기지 않는다. 결과를 보기 전의 기준으로 되돌리고, 지난 판정의 `cut_reason`과 세션 `deviation`에 그 일을 적는다.

지표의 정의(구간 길이, 문턱, 무엇을 뺄지)는 가설의 `test`가 원본이다. 계산 스크립트에 같은 값을 상수로 두면, 결과 파일 첫머리에 계산에 쓴 정의를 찍게 한다. 한쪽만 바뀌어도 판정 에이전트가 `test`와 견줄 수 있다.

### 2. 플레이한 뒤: 세션을 기록한다

한 번 모여 플레이할 때마다 `data/playtests.json`의 `playtests`에 세션 하나를 넣는다. 형식은 [references/playtest-record.md](references/playtest-record.md).

- 날짜, 플레이한 사람, 빌드(커밋 해시), 판 수
- 가설별 관찰값(`observations`): 가설의 `failure_signal`을 판단하는 데 필요한 값. 로그에서 읽었으면 `source`에 파일을 적는다. 스크립트로 계산한 값(비율, 상관)은 그 출력을 세션 폴더에 결과 파일로 남기고(예: `python3 game/summarize.py playtests/pt_20261107_1 > playtests/pt_20261107_1/summary.txt`) `source`를 그 결과 파일로 둔다. 판정 에이전트는 스크립트를 돌리지 못하므로(훅이 막는다) 결과 파일이 없으면 값을 확인할 수 없다
- 레벨의 그레이박스 확인 기록(`greybox`): `levels.json`의 항목 id마다 잰 값이나 판정. 항목은 `… check . --table levels` 끝의 확인 표에 있다
- 가설의 `sample.events`에 적은 사건을 이 세션에서 센 건수(`events`). 세지 않은 세션은 0건으로 센다
- 그 밖의 관찰과 선호(`notes`). 가설 `test`의 시험 절차를 어긴 일(정한 설정 순서를 지키지 않음, 중간 결과를 본 뒤 플레이함)은 `deviation`으로 적는다. 판정 줄에 근거 세션의 절차 이탈 수가 나온다

관찰값의 수는 결과 파일이나 로그의 수를 반올림하지 않고 그대로 옮긴다. 결과 파일에 없는 수는 경고한다(`value_not_in_source`). 사용자에게 묻지 않고 채운 값이 있으면 그 사실을 보고한다. 로그 파일이 있으면 `logs`에 경로를 적는다. 기록 파일을 지우지 않는다.

**여러 세션을 합쳐야 나오는 값.** 표본을 채우려고 세션을 나눠 했고, 지표가 판을 합쳐 다시 계산해야 하는 값(구간 안 상관, 전체 비율)이면 세션별 결과를 평균 내지 않는다. 근거 세션의 원본 로그를 모두 넣어 한 번 계산하고, 그 결과 파일을 마지막 세션 폴더에 둔다(예: `playtests/pt_20261108_1/summary_pooled.txt`). 관찰값은 마지막 세션에 적고 `note`에 합친 세션 id를 적는다. 판정의 `sessions`에는 합친 세션을 모두 적는다. 이미 기록한 세션은 고치지 않는다.

### 3. 판정한다

- **Claude Code**: 판정 에이전트 `studio-judge`에게 맡긴다. 예: "studio-judge로 ripening_gems의 가설을 판정해 줘". 판정 에이전트는 파일을 고치지 못하고(훅이 막는다), 가설별 제안과 `verdicts`에 넣을 JSON을 돌려준다.
- **Codex 등 판정 에이전트가 없는 환경**: 같은 절차를 직접 따른다. 판정 기준은 [references/playtest-record.md](references/playtest-record.md#판정)이다. 만드는 쪽과 판정하는 쪽이 분리되지 않았다는 사실을 보고에 적는다.

받은 제안을 `verdicts`에 `"status": "proposed"`로 넣고 사용자에게 보여 준다. 사용자가 확인하면 `approved`로 바꾼다. 사용자가 버팀·틀림 제안을 모름으로 낮춰 확정할 수 있다. 예: 기록으로는 지표가 주장한 행동에서 나왔는지 규칙에서 나왔는지 가를 수 없다. 그러면 `result`를 `unknown`으로 고친다. `proposed_result`에는 에이전트가 낸 결과를 남기고, `reason` 앞에 바꾼 까닭과 날짜를 적는다. 판정 줄에 `모름 (확정, 판정 에이전트는 버팀)`처럼 보인다. 모름을 버팀·틀림으로 올리거나 버팀과 틀림을 서로 바꾸면 오류다(`verdict_overrides_proposal`). 그럴 때는 사용자의 까닭을 판정 에이전트에게 주고 다시 판정한다. 다시 판정할 때는 지난 판정을 지우지 않는다. 지난 판정을 먼저 `cut`으로 바꾸고 같은 편집에서 새 판정을 넣는다. 새 판정부터 넣으면 그 사이에 `duplicate_verdict`가 난다.

판정 에이전트는 판정할 때 읽은 가설의 기준 지문(`check`의 `판정 기준 지문:` 줄)을 JSON의 `criteria`에 담아 돌려준다. 그대로 기록한다. 판정 뒤에 가설의 `claim`, `failure_signal`, `test`, `sample`이 바뀌면 `verdict_criteria_changed`가 나고, 확정 판정이어도 게이트를 넘지 못한다. 고치는 순서는 아래 '판정한 가설의 문장을 고칠 때'를 따른다. 출처 태그만 바꾼 것은 바뀐 것이 아니다. `check`가 "예전 꼴" 참고 줄을 내면 그 판정은 태그까지 넣어 계산하던 때의 지문이다. 기준은 그대로이니 줄에 적힌 지문으로 `criteria`를 바꿔 둔다. 지문이 없는 판정(`verdict_criteria_missing`)도 확정해도 게이트를 넘지 못한다. 판정한 뒤 가설을 고치지 않은 것이 확실할 때만 지금 지문을 적는다.

**판정한 가설의 문장을 고칠 때.** 이 순서와 예의 원본은 여기다. 다른 문서는 여기를 가리킨다.

1. 고치기 전에 바꿀 문장을 보이고, 뜻이 같은 고침인지 사용자와 확인한다. 뜻이 같은 고침의 예: 맞춤법, 옮겨 적은 빌드의 게임 수치를 지우고 빌드를 이름으로 가리킴([브리프](../concept-exploration/references/brief.md)의 '세는 빌드는 이름으로 가리킨다').
2. 같은 뜻이면 문장을 고치고, `check`가 알려 주는 새 지문으로 판정의 `criteria`를 한 번에 바꾼다. 결과와 글은 그대로 둔다. 같은 편집에서 가설의 `criteria_history` 끝에 고친 칸의 고치기 전 값과 그때 지문(판정의 예전 `criteria`), 날짜, 까닭과 확인한 사람을 남긴다([브리프](../concept-exploration/references/brief.md)). 판정 에이전트는 git을 볼 수 없어 고치기 전 기준을 여기서 읽는다. 먼저 고치고 나서 물으면 답을 받을 때까지 확정 판정이 게이트를 넘지 못한다. 사이에 나오는 `verdict_criteria_changed`는 이미 확인한 일이면 다시 묻지 않고 지문만 바꾼다.
3. 뜻이 바뀌면 지금 기준으로 다시 판정하고 지난 판정은 `cut`으로 둔다. 다시 시험하려고 기준을 바꾸는 것이면 묻지 않고 아래 '다시 시험할 때'를 따른다.

**이력을 나중에 남길 때.** 기준을 고칠 때 `criteria_history`를 남기지 못했으면(이 칸이 생기기 전의 고침, 빠뜨린 고침) 나중에 더한다. 이력만 더하는 것은 기준도 판정도 바꾸지 않으므로 묻지 않고, 더한 것을 보고한다.

- 판정에 적힌 지문마다(`cut` 판정 포함, 지금 지문은 빼고) 한 항목을 오래된 것부터 둔다. 판정 없이 여러 번 고쳤으면 한 항목으로 합친다.
- `date`는 고친 날이다. `why`에 까닭, 확인한 사람, 나중에 남긴 날을 적는다. 확인한 사람을 기록(`cut_reason`, 커밋 메시지, 작업 기록)에서 찾지 못하면 지어내지 않고 "확인 기록 없음"이라 적고 사용자에게 알린다.
- 고치기 전 값은 그 지문으로 판정한 때의 기준이다. 판정 뒤 처음 기준을 고친 커밋의 부모에서 가져온다(`git show <커밋>^:design/concepts.json`). 사이에 여러 번 고쳤어도 첫 고침의 부모다. `stamp`는 그 커밋에서 바뀐 판정의 예전 `criteria`다. `cut` 판정이면 그 판정의 `criteria`다. `cut_reason`에 글로 옮긴 기준은 고치기 전 문장 그대로가 아니라 `before`에 쓰지 않는다.
- 고치기 전 문장을 찾지 못한 고침이 있으면 그보다 오래된 항목도 넣지 못한다. 이력은 지금 기준에서 거꾸로 되짚기 때문이다. 넣지 못한 고침을 사용자에게 알린다.
- 넣은 뒤 `check`의 "기준 이력" 줄로 확인한다. 값이 틀리면 `criteria_history_mismatch`가 난다.

### 4. 측정값을 올린다

관찰값을 **그대로** 옮긴 수치만 `[가정]`에서 `[측정: data/playtests.json#세션 id]`로 바꾼다. 데이터 파일(아이템·강화·적)은 `provenance`를 `{"kind": "measured", "source": "data/playtests.json#세션 id"}`로 둔다. 한 항목의 값 일부만 기록으로 뒷받침되면 항목 전체를 바꾸지 않고 `provenance.fields`에 그 값만 적는다(`{"kind": "assumed", "fields": {"kills.crawler": {"kind": "measured", "source": "data/playtests.json#pt_20261108_3"}}}`). 게이트 줄에 `zone_1(필드 1/4)`처럼 얼마나 왔는지 보이고, 모든 수치 칸에 가정이 아닌 출처가 붙으면 그 항목은 게이트에서 빠진다.

- 평균·비율을 새로 계산한 값은 `[계산: 스크립트 또는 결과 파일]`이다. 계산한 스크립트가 없으면 올리지 않는다.
- 판정 기준의 문턱값(예: `80% [가정]`)과 `test`의 시험 설계 값(표본, 구간)은 측정값이 아니다. 무엇이 틀림인지를 정하는 잣대라 측정으로 올리지 않는다. 사용자가 그 값을 정했으면 `[결정: 사용자 2026-11-09]`로 바꾼다. 그러면 게이트가 막지 않는다. 에이전트가 정한 값은 `[가정]` 그대로다([numeric-provenance](../numeric-provenance/SKILL.md), [브리프](../concept-exploration/references/brief.md)).
- 판정 글(`reason`, `next_needs`, `cut_reason`)에는 문턱을 잣대 태그 없이 수치만 쓴다("사망 6건이 필요한데"). 출처는 브리프에 있고, 옮겨 적은 태그는 브리프를 고치면 어긋난다. `check`는 `next_needs`, 뷰어는 `reason`과 `next_needs`의 `[가정]`·`[결정]` 태그를 빼고 보인다.
- 올린 뒤 `provenance design/ --check-paths`(md)와 `check .`(컨셉 브리프)로 세션이 실제로 있는지 확인한다.

### 5. 가정값을 보정한다

세션에 단계 기록과 그때 가진 영구 강화를 적었으면 `calibrate`로 기획의 가정값과 비교한다. 평균을 손으로 내지 않는다. 프로토타입의 판별 로그(CSV)를 `runlog`로 모아 세션에 합친다(판 사이에 강화를 사서 상태가 바뀌어도 상태별 묶음으로 나온다). 시간이 다 되면 끝나는 단계(5분 회색 상자)는 `runlog --timed 단계`로 모은다. 빠뜨리면 calibrate가 늘 같은 길이를 비교한다. 형식과 읽는 법은 [references/calibration.md](references/calibration.md).

단계 하나짜리 시험판(5분 회색 상자)도 비교할 수 있다. 판이 끝날 때의 레벨은 `level_end` 열로 남겨 다음 단계의 `level_at`과 견준다. 처치는 실패한 판까지 센 처치 속도(`kill_rate`)로 본다. 시간이 다 되면 끝나는 단계는 기록에 `"timed": true`를 적는다. 시험 조건이 여러 가지면 `--variant 열=값`으로 조건마다 본다. 넘긴 판이 적은 값은 "참고"로 나오므로 그 값으로 원본을 고치지 않는다.

```bash
python3 .claude/skills/studio-data/scripts/studio.py runlog playtests/pt_20261112_1/runs.csv
python3 .claude/skills/studio-data/scripts/studio.py calibrate data/meta_combat.json --out reports/calibrate.json
```

- 가정값 비교: 판 안 성장의 단계별 레벨, 재화 흐름의 길이·처치 수·수입을 기록의 평균과 나란히 놓는다. 시뮬레이터 설정 없이 폴더(`calibrate .`)만 넘겨도 된다.
- 통과율 비교: 그 세션의 강화·레벨로 다시 계산한 예측이 실측의 95% 구간 안인지 본다. 구간이 넓으면 표본이 적은 것이다.
- 생존 곡선 제안: 기록이 지금 값과 구분될 때만 `slope`·`even_margin`을 범위와 함께 제안한다. "제안 없음"이면 바꿀 근거가 없는 것이다. 근거가 모자란 값은 제안하지 않고 이유를 남긴다.
- 제안은 자동으로 적용하지 않는다. 사용자에게 보여 주고 어느 값을 옮길지 정한다. 레벨을 먼저 옮기고 생존 곡선을 옮긴다. 옮긴 값에는 출처를 남긴다(기록을 그대로 옮기면 측정, 평균이나 제안이면 `reports/calibrate.json`을 출처로 한 계산). 기획 목표 범위는 의도이므로 바꾸지 않는다.

### 6. 틀렸으면 되돌아간다

`refuted`가 확정되면 다음 중 하나를 사용자에게 제안한다. 결정은 사용자가 한다. 선택한 컨셉의 가설이 틀림으로 확정된 동안은 `approved_concept_refuted` 경고가 나고 `--fail-on-assumed`가 실패한다. 가설 기준을 고치거나, 다시 판정하거나, 컨셉 상태를 바꾸면 사라진다.

- 가설이 기대는 규칙 하나를 바꿔 다시 시험한다(브리프의 `prototype`과 가설을 고친다). 순서는 아래 "다시 시험할 때"를 따른다.
- 컨셉을 되돌린다(`proposed`, 탈락 사유가 증명되었으면 `hard_reject`와 함께 `cut`). 순서는 아래 "컨셉을 되돌릴 때"를 따른다.
- `unknown`이면 무엇이 부족했는지(표본, 기록하지 못한 값)를 다음 세션 계획으로 남긴다.

**다시 시험할 때.** 이 순서로 한다.

1. 시험판을 만드는 열린 변경이 있으면 먼저 닫는다. 시험판 변경은 메인 스펙에 합치지 않는다([scope-guard](../scope-guard/SKILL.md)). 설계를 먼저 고치면 열린 변경이 `design_changed`로 막혀 닫지 못한다. 닫지 않으려면 규칙을 그 변경 안에서 바꾼다.
2. 브리프의 `prototype`과 가설을 고친다. 기준을 고친 바로 다음 편집에서 지난 판정을 `cut`으로 둔다(지우지 않는다. 가설은 `design/concepts.json`, 판정은 `data/playtests.json`이라 한 편집으로는 못 한다). `cut_reason`에 날짜와 까닭, 바뀐 기준 문장을 적고, 가설의 `criteria_history`에도 고치기 전 값과 지난 판정의 지문을 남긴다. 판정 에이전트는 git을 볼 수 없어서, 고치기 전 기준은 여기에만 남는다. 모름 판정이 남긴 `next_needs`(다음 시험 전에 풀 것)는 새 판정이 나올 때까지 판정 줄 아래에 보인다. 다시 시험하기 전에 그것을 풀었는지 본다. `test` 안의 "지난 9판" 같은 상대 표현은 세션 id로 고친다. 새 기록을 기다리며 확정 판정으로 두면 `verdict_criteria_changed` 경고가 플레이가 끝날 때까지 남는다. 그동안 그 가설은 판정이 없는 것으로 게이트에 남는다.
3. 바꾼 규칙이 지표를 저절로 움직이는지 본다. 예: 적이 밟으면 보석이 깨지는 규칙은 적이 많은 곳의 늦은 수확을 없앤다. 그래서 플레이어가 아무것도 바꾸지 않아도 "몰리면 일찍 줍는다"는 쪽의 상관이 나온다. 프로토타입에 봇이 있으면 기준선을 낸다. 행동은 그대로 두고 규칙만 켠 정책으로 같은 지표를 계산한다. 주장한 행동을 뺀 정책으로도 계산한다. 기준선이 이미 문턱을 넘으면 그 지표로는 가설을 가를 수 없다. 플레이 전에 사용자와 지표나 문턱을 바꾼다([brief](../concept-exploration/references/brief.md)).
4. 모든 가설의 `sample.events`를 새 규칙으로 다시 어림한다. 바꾼 규칙이 다른 가설의 사건을 없앨 수 있다. 예: 보석이 깨져 부화가 없어지면 "부화가 있던 판의 사망"도 생기지 않는다. 그런 가설은 플레이 전에 어떻게 볼지 사용자와 정한다(사건을 바꾼다, 그쪽을 모름으로 둔다).
5. 시스템 설계를 고치고 새 변경으로 시험판에 넣는다.

**컨셉을 되돌릴 때.** 이 순서로 한다.

1. 사용자에게 묻는다: 컨셉을 `proposed`로 둘지, 탈락 사유가 증명되었으면 `hard_reject`와 함께 `cut`으로 둘지([탈락 기준](../concept-exploration/references/stress-policies.md)). 다음 후보는 이때 함께 정하지 않아도 된다.
2. 사용자가 정한 대로 컨셉 상태를 바꾼다. 승인을 내리는 편집은 범위 훅이 사용자에게 확인을 묻는다([scope-guard](../scope-guard/SKILL.md)). 확인 창이 없는 실행에서는 거부된다(`claude -p`의 acceptEdits 모드에서 확인함. 다른 권한 모드는 [scope-guard](../scope-guard/SKILL.md)의 한계). 우회하지 않고, 사용자가 직접 고치거나 대화형 세션에서 허락받는다. 브리프와 판정 기록은 지우지 않는다. 컨셉의 `notes`에 되돌린 까닭과 날짜를 적는다.
3. 상태를 바꾼 뒤에 시험판을 만든 열린 변경을 메인 스펙에 합치지 않고 닫는다(`openspec archive <변경> --skip-specs`, 확인 창이 없는 실행이면 `--yes`를 붙인다. `--yes`는 남은 작업 확인도 건너뛰니, `tasks.md`에 끝나지 않은 작업이 있으면 먼저 사용자에게 알린다). 상태를 바꾸기 전에 닫으면, 사용자가 되돌리지 않기로 했을 때 변경만 닫힌 채 남는다.
4. `design/systems.json`과 `data/`는 다음 컨셉의 시스템 설계까지 지우지 않는다. 지난 시험의 기록이다. 그동안 나는 `concept_not_approved`(`proposed`로 둔 경우)나 `cut_referenced`(`cut`한 경우) 경고는 되돌린 컨셉을 가리킨다는 뜻이다. 다음 컨셉을 고르면 [system-design](../system-design/SKILL.md)에서 그 컨셉에 다시 잇는다. 선택한 컨셉이 없는 동안 `--fail-on-assumed`의 FAIL은 이 기록의 가정 수치 때문이라 할 일이 아니다(`check`가 참고 줄로 알린다).
5. 다른 후보를 고르려면 [concept-exploration](../concept-exploration/SKILL.md)의 선택 단계(7단계)로 돌아간다. 남은 `proposed` 후보를 모두 보이고, 틀린 가설과 결정 구조가 가까운 후보를 따로 짚는다. 3~5개 비교표로 좁힐지는 사용자에게 묻는다. 좁히면 구조 차이로 고르고 재미 순위로 고르지 않는다.

**다른 시스템이 바뀌어 지난 기록과 합치지 않을 때.** 틀림이 아니어도, 가설이 기대지 않는 수치(레벨업 강화 등)가 바뀌어 지난 기록을 함께 세면 안 될 때가 있다. 기준(문턱, 표본)은 그대로 두고 가설에 `builds`(이 가설이 세는 빌드: 세션의 `build` 커밋이나 `game_build` 판 로그의 빌드 지문)를 적는다. 그러면 다른 빌드의 세션으로 낸 버팀·틀림이 오류(`verdict_session_wrong_build`)다. `test` 문장에도 같은 빌드를 적고, 세션을 기록할 때 `game_build`를 함께 적는다. 지난 판정은 위 2번처럼 `cut`으로 둔다.

## 보고

- `check` 결과 그대로: 판정별 버팀·틀림·모름, 그 가설을 관찰한 근거 세션 수·판 수·사람 수와 최소 표본(`9/9판 · 1/1명`), 사건 수, 절차 이탈 수, 오류·경고 수, `INCOMPLETE` 여부
- 확정되지 않은 가설 목록(`--fail-on-assumed`의 gate 줄)
- 이번에 `[측정]`으로 올린 수치와 그 출처
- `calibrate`를 돌렸으면: 쓴 세션과 표본, 표시된 차이, 구간을 벗어난 단계, 제안과 옮긴 값
- 사용자 확인이 필요한 것: 제안 판정의 확정, 틀린 가설 이후의 방향
- 실행하지 못한 검사가 있으면 그 사실

## 한계

- 검사기는 판정이 **증거를 가리키는지**만 본다. 관찰값이 틀렸다는 신호에 해당하는지는 판정 에이전트와 사용자가 본다.
- 표본은 가설의 `sample`에 적은 사람 수, 판 수, 사건 수만 숫자로 막는다. runlog가 쓴 묶음이 없는 세션(관찰값만 있거나 단계 기록을 손으로 쓴 세션)은 손으로 쓴 `runs`와 `players`를 그대로 센다. 사건 수는 버팀만 막는다. 틀림은 사건에 기대지 않는 다른 쪽 신호로 낼 수 있어서 판정 줄에 보이기만 한다. 설정별 판 수는 막지 않으므로 판정 에이전트가 `test`와 견준다.
- 절차 이탈은 적은 것만 센다. 이탈이 판정을 바꾸는지는 판정 에이전트와 사용자가 본다.
- 관찰값과 결과 파일은 수만 맞춰 본다. 수가 있어도 다른 설정이나 다른 칸의 수일 수 있다.
- 보정 값은 기록한 빌드와 플레이어에서 나온 값이다. 보정해도 시뮬레이션 결과로 재미나 실제 난이도를 판정하지 않는다.
- 판정 에이전트와 훅은 Claude Code 전용이다. 훅 입력의 에이전트 이름(`agent_type`)으로 판정 에이전트를 구분한다(Claude Code 2.1.316, WSL에서 확인. Windows는 미확인).

예시: `studio-data/assets/sample-project/data/playtests.json` (실제 플레이 기록이 아니다).
