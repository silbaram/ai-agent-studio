# 플레이 기록 형식

게임 프로젝트의 `data/playtests.json` 한 파일에 세션과 판정을 남긴다. 검사: `python3 .claude/skills/studio-data/scripts/studio.py check .`(컨셉 데이터와 함께 검사해야 가설 참조를 확인한다), 보기: `python3 .claude/skills/studio-data/scripts/studio.py view .`.

```json
{
  "playtests": [
    {
      "id": "pt_20261105_1",
      "date": "2026-11-05",
      "concept": "ripening_gems",
      "build": "3f2a9c1",
      "players": ["self", "friend_a"],
      "runs": 6,
      "logs": ["playtests/pt_20261105_1/harvest.csv"],
      "observations": [
        { "hypothesis": "density_timing", "metric": "같은 숙성 단계 수확 비율(설정별)",
          "value": "0.5배 91%, 1배 72%, 2배 64%", "n": 140, "source": "playtests/pt_20261105_1/harvest.csv" }
      ],
      "notes": [
        { "kind": "observation", "text": "friend_a는 2배 설정에서 3단계까지 기다리다 두 번 부화시켰다" },
        { "kind": "preference", "text": "self: 보석 터지는 소리가 좋다" }
      ]
    }
  ],
  "verdicts": [
    { "concept": "ripening_gems", "hypothesis": "density_timing", "result": "holds",
      "sessions": ["pt_20261105_1"], "reason": "1배·2배에서 같은 단계 비율이 80% [가정] 미만",
      "criteria": "9c41e07a", "status": "proposed" }
  ]
}
```

## 세션 (`playtests`)

| 필드 | 필수 | 뜻 |
|---|---|---|
| `id` | 예 | 소문자·숫자·밑줄. `pt_날짜_순번`을 권한다. `[측정: data/playtests.json#id]`의 출처가 된다 |
| `date` | 예 | 달력에 있는 `YYYY-MM-DD` 날짜 |
| `concept` | 예 | 시험한 컨셉 id (`design/concepts.json`). `observations`, `events`, `notes[].hypotheses`가 없는 세션(그레이박스·단계 기록만)은 빼도 된다. 뺀 세션은 판정의 근거가 되지 못한다 |
| `build` | 예 | 빌드를 다시 만들 수 있는 이름. 보통 커밋 해시 |
| `game_build` | 아니오 | 프로토타입이 판 로그에 남긴 빌드 지문(예: `cfg721feeb5`). 가설의 `builds`는 `build`나 이 값과 맞춘다 |
| `players` | 예 | 플레이한 사람 이름 배열. 같은 사람은 같은 이름으로 쓴다(사람 수를 센다). 근거 세션의 빌드가 섞이면 판정 줄에 `빌드 2개(…)`가 붙는다. 합쳐 세도 되는지 판정 `reason`에 적는다 |
| `runs` | 예 | 이 세션의 판 수 합계 |
| `notes[].hypotheses` | 아니오 | 그 메모가 가리키는 가설 id 배열. `deviation`에 적으면 그 가설의 판정에만 절차 이탈로 센다. 없으면 모든 판정에 센다. 없는 가설 id는 `unknown_hypothesis`다 |
| `events` | 아니오 | 가설 `sample.events`의 사건을 이 세션에서 센 건수 `{사건 이름: 0 이상의 정수}`. 이름은 `sample.events`와 같게 쓴다. 적지 않은 세션은 그 사건을 0건으로 센다 |
| `observations` | 아니오 | `[{hypothesis, value, metric, n, source, note}]`. `hypothesis`(가설 id)와 `value`(문자열 또는 수)가 필수. 없고 단계 기록도 없으면 경고. 스크립트로 계산한 값은 그 출력을 세션 폴더에 결과 파일로 남기고 `source`를 그 파일로, `note`를 `[계산: 스크립트]`로 적는다. `value`의 수는 결과 파일의 수를 그대로 옮긴다 |
| `notes` | 아니오 | `[{kind: observation / preference / deviation, text}]`. `deviation`은 가설 `test`의 시험 절차를 어긴 일이다(정한 설정 순서를 지키지 않음, 중간 결과를 본 뒤 플레이함) |
| `logs` | 아니오 | 원본 기록 파일 경로 배열(프로젝트 폴더 기준). 계산 결과 파일은 넣지 않는다 |
| `stage_stats`, `upgrades`, `growth_build`, `groups` | 아니오 | 단계별 판 수와 평균 레벨·길이·처치·수입, 그때 가진 영구 강화, 판 안 성장 빌드, 강화 상태별 묶음. 묶음에는 강화 밖의 시험 조건 `variant`(`{로그 열: 값}`, `runlog --group-by`가 쓴다)와 그 묶음의 판 수 `runs`, 그 묶음을 한 사람 `players`(둘 다 runlog가 쓴다)를 달 수 있다. 가정값을 보정할 때 쓴다([calibration](calibration.md)) |
| `greybox` | 아니오 | 레벨의 그레이박스 확인 기록 `[{check, value, passed, n, source, note}]`. `check`는 `levels.json`의 항목 id다. 재었으면 `value`(수), 재지 못하면 `passed`(true나 false)를 적는다. 둘 중 하나는 필요하다. `n`은 해 본 판 수로 1 이상이다. 해 보지 않았으면 기록을 적지 않는다. 날짜순 마지막 기록이 판정이 된다. 같은 날짜면 세션 id의 순번순이다. 항목 id의 오타는 기록을 버리므로 오류다. 비슷한 이름이 없는 id는 지운 항목의 기록으로 보고 경고한다 |
| `acknowledged` | 아니오 | 확인을 마친 경고 `{경고 코드: 이유}` |

`value`에는 해석이 아니라 본 것을 적는다. "개선됨" 대신 "42% → 18%". 사람마다 다르면 사람별로 적는다. 문턱값(`-0.2 [가정]`)은 `value`가 아니라 판정의 `reason`에 적는다.

### 여러 세션을 합친 값

판을 합쳐 다시 계산해야 하는 지표(구간 안 상관, 전체 비율)를 여러 세션에 걸쳐 모았으면, 세션별 결과를 평균 내지 않는다. 근거 세션의 원본 로그를 모두 넣어 한 번 계산하고 결과 파일을 마지막 세션 폴더에 둔다. 관찰값은 마지막 세션에 적고 `note`에 합친 세션 id를 적는다(`[계산: game/summarize.py] pt_a + pt_b 합침`). 판정의 `sessions`에는 합친 세션을 모두 적는다. 앞 세션의 기록은 고치지 않는다.

## 판정 (`verdicts`)

| 필드 | 필수 | 뜻 |
|---|---|---|
| `concept`, `hypothesis` | 예 | 판정하는 가설 (컨셉 id, 가설 id) |
| `result` | 예 | `holds`(버팀) / `refuted`(틀림) / `unknown`(모름) |
| `reason` | 예 | 관찰값을 `failure_signal`에 어떻게 적용했는지. 모름이면 무엇이 부족한지 |
| `sessions` | 버팀·틀림이면 예 | 근거 세션 id 배열. 그 세션에 이 가설의 관찰값이 있어야 한다 |
| `status` | 아니오 | `proposed`(판정 에이전트 제안) / `approved`(사용자 확인) / `cut`(지난 판정) |
| `proposed_result` | 아니오 | 사용자가 제안과 다른 결과로 확정했을 때 판정 에이전트가 낸 결과(`holds` / `refuted` / `unknown`). 버팀·틀림을 모름으로 낮출 때만 쓴다. `reason` 앞에 바꾼 까닭과 날짜를 적는다. 판정 줄에 `모름 (확정, 판정 에이전트는 버팀)`처럼 보인다 |
| `cut_reason` | 아니오 | 지난 판정(`cut`)에 지운 날짜와 까닭. 기준을 고쳐 지웠으면 바뀐 기준 문장(고치기 전 문장)도 적는다([changes](changes.md)). `cut`이 아닌 판정에 쓰면 오류다 |
| `next_needs` | 아니오 | 다음 시험 전에 풀 것(모름 판정에 남긴다). 새 판정이 나올 때까지 `check`의 판정 줄 아래에 "다음 시험 전에 풀 것"으로 보인다. 그 판정을 `cut`으로 돌려도 새 판정이 버팀·틀림이 되기 전까지 "(지난 판정)"으로 남는다 |
| `criteria` | 아니오 | 판정할 때의 가설 기준 지문(소문자 16진수 8자). `claim`, `failure_signal`, `test`, `sample`로 내고, 가설에 `builds`를 적었으면 그것도 넣는다(결과를 본 뒤 세는 빌드를 좁히면 지난 판정이 지금 기준의 판정이 아니다). 문장 안의 출처 태그는 빼고 계산한다. 예전 꼴(태그까지 넣어 계산함)의 지문도 맞는 것으로 보고, `check`가 지금 꼴로 바꿀 지문을 참고 줄로 보인다. `check`가 선택한 컨셉의 가설마다 `판정 기준 지문:` 줄로 보이고, 판정 에이전트가 판정에 담아 돌려준다. 없으면 확정해도 게이트를 넘지 못한다 |

가설 하나에 `cut`이 아닌 판정은 하나만 둔다. 다시 판정하면 지난 것을 먼저 `cut`으로 바꾸고 같은 편집에서 새 판정을 넣는다. `cut`인 판정의 `criteria`는 보지 않는다.

### 구조화한 자기 보고

"재미있다"는 선호이고 판정 근거가 아니다. 다만 미리 정한 질문을 판마다 같은 때에 묻고 답을 판 로그에 남기면 관찰값으로 쓸 수 있다(예: 판이 끝날 때 "강해졌다고 느낀 레벨업이 있었나?" O/X). 이것을 구조화한 자기 보고라 한다.

- 질문 문구, 묻는 때, 답의 형식을 가설 `test`에 그대로 적는다. 플레이 도중에 문구를 바꾸지 않는다.
- 같은 질문을 판마다 되풀이하면 한쪽 답으로 기울 수 있고, 시험하는 사람이 가설을 알면 더 그렇다. 이 기울기를 `test`에 적는다.
- 자기 보고만으로 버팀을 내지 않는다. 같은 주장을 재는 행동 지표나 로그 지표가 함께 신호를 내지 않을 때만 버팀이다. 자기 보고가 "아니오"로 많이 나오면 그것만으로도 틀림이 될 수 있다.

### 판정

| result | 조건 |
|---|---|
| `holds` | 관찰값이 있고, `failure_signal`이 나오지 않았다 |
| `refuted` | 관찰값에서 `failure_signal`이 나왔다 |
| `unknown` | 관찰값이 없다 / 표본이 가설의 `sample`(없으면 `test`에 적은 계획)보다 적다 / 사건 수가 `sample.events`보다 적어 그 사건에 기대는 신호를 가릴 수 없다 / 신호가 나왔는지 기록으로 가릴 수 없다 / 버팀·틀림의 근거가 주장한 행동이 아닌 다른 까닭으로도 설명되고 기록으로 둘을 가를 수 없다 |

다른 까닭은 기록이나 브리프에 드러난 것만 쓴다. 예: 다시 시험하려고 넣은 규칙이 지표를 직접 움직인다, `test`에 적힌 기준선(주장한 행동을 뺀 봇의 값)이 이미 문턱을 넘는다. 판정하는 쪽이 짐작한 까닭은 근거가 아니다. 이것은 문턱을 바꾸는 일이 아니다. 문턱은 그대로 적용하고, 그 값이 주장을 시험했는지를 따로 본다. `reason`에 그 까닭과 가르지 못한 점을 적는다.

판정 기준(`failure_signal`의 문턱값)은 판정하면서 바꾸지 않는다. 바꿔야 한다면 판정과 별도로 브리프를 고치고, 그 사실을 보고한다.

## 검사 내용

| 코드 | 수준 | 조건 |
|---|---|---|
| `schema`, `duplicate_id` | 오류 | 형식 위반, 세션 id 중복 |
| `unknown_concept`, `unknown_hypothesis` | 오류 | 컨셉 데이터에 없는 컨셉·가설 id. 가설에 id가 없으면 그렇게 알린다 |
| `verdict_without_evidence` | 오류 | 버팀·틀림인데 근거 세션이 없음 |
| `unknown_session` | 오류 | 판정이 가리킨 세션이 기록에 없음 |
| `session_concept_mismatch` | 오류 | 판정이 다른 컨셉의 세션이나 `concept` 없이 적은 세션을 가리킴 |
| `observation_missing` | 오류 | 버팀·틀림인데 근거 세션에 그 가설의 관찰값이 없음 |
| `duplicate_verdict` | 오류 | 한 가설에 `cut`이 아닌 판정이 둘 이상 |
| `verdict_session_wrong_build` | 오류 | 버팀·틀림인데, 가설의 `builds`가 있고 근거 세션의 `build`와 `game_build`가 어느 것도 거기에 없음 |
| `verdict_sample_reduced_after_results` | 오류 | 버팀·틀림인데, 가설의 `sample.reduced_from.before_results`가 `false`(결과 파일을 연 뒤에 표본을 줄임). 모름으로 두거나 원래 표본을 채운다 |
| `verdict_session_before_reduction` | 오류 | 버팀·틀림인데, 근거 세션 중 가설의 `sample.reduced_from.date`보다 앞선 날짜의 세션이 있고 근거 표본이 줄이기 전 표본(`reduced_from`의 `runs`·`players`)에 못 미침. 그 세션의 결과는 줄이기 전에 나와 있었다. 줄인 뒤의 세션으로 채우거나 줄이기 전 표본을 채우고, 못 하면 모름으로 둔다. 같은 날의 세션은 보지 않는다(그날 줄이기 전에 마친 세션은 [changes](changes.md#표본을-줄이자는-말이-나올-때) 5번) |
| `verdict_overrides_proposal` | 오류 | `proposed_result`와 다른 `result`가 모름이 아님(모름을 버팀·틀림으로 올렸거나 버팀과 틀림을 바꿈). 사용자의 까닭을 판정 에이전트에게 주고 다시 판정한다. `cut`인 판정은 보지 않는다 |
| `verdict_sample_short` | 오류 | 버팀·틀림인데, 그 가설을 관찰한 근거 세션을 합친 사람 수나 판 수가 가설의 `sample`보다 적음. 제안(`proposed`)이어도 오류다. `sample`이 없는 가설은 보지 않는다. runlog가 쓴 묶음(모든 묶음에 `runs`나 `players`가 있음)이 있는 세션은 묶음의 판 수 합과 사람을 넘겨 세지 않는다. 손으로 쓴 단계 기록은 로그가 아니라 세지 않는다 |
| `verdict_events_short` | 오류 | 버팀인데, 근거 세션의 `events`를 합친 사건 수가 가설의 `sample.events`보다 적음. 세지 않은 세션은 0건이다. 근거 세션이 하나도 그 사건을 세지 않았으면(나중에 `sample.events`를 더함) 판정 줄과 메시지에 `미집계/6`으로 쓴다. 틀림은 사건에 기대지 않는 쪽 신호로 낼 수 있어 막지 않고 판정 줄에 보인다 |
| `verdict_criteria_missing` | 경고 | `cut`이 아닌 판정에 `criteria`가 없음. 확정 판정이어도 `--fail-on-assumed`를 넘지 못한다. 메시지가 지금 지문을 알려 주지만, 판정한 뒤 가설을 고치지 않았을 때만 그 값을 적는다 |
| `player_name_variants` | 경고 | 앞 세션(날짜순)과 대소문자·공백만 다른 이름. 표본은 두 사람으로 센다. 다른 사람이 맞으면 세션의 `acknowledged`에 이유를 적는다 |
| `unknown_event` | 경고 | 세션 `events`의 사건 이름이 그 컨셉의 어느 가설 `sample.events`에도 없음(오타). 그 건수는 어떤 판정에도 세지 않는다. 비슷한 이름을 알려 준다 |
| `verdict_criteria_changed` | 경고 | 판정 뒤에 가설 기준이 바뀜. 확정 판정이어도 `--fail-on-assumed`를 넘지 못한다. 뜻이 같은 고침이면 `criteria`를 새 지문으로 고치고, 뜻이 바뀌었으면 다시 판정하고 지난 것은 `cut`으로 둔다. 가리는 순서와 예는 [changes](changes.md#판정한-가설의-문장을-고칠-때)의 '판정한 가설의 문장을 고칠 때'. 다시 시험하려고 기준을 바꿨으면 새 기록을 기다리지 않고 기준을 고친 편집에서 바로 `cut`으로 둔다 |
| `approved_concept_refuted` | 경고 | 선택(approved)한 컨셉의 가설이 틀림으로 확정됨. 가설 기준을 고치거나, 다시 판정하거나, 컨셉 상태를 바꾸면 사라진다. 승인을 내리는 편집은 범위 훅이 사용자에게 묻는다([changes](changes.md#컨셉을-되돌릴-때)의 '컨셉을 되돌릴 때') |
| `value_not_in_source` | 경고 | `[계산: …]` 관찰값의 `value`에 있는 수가 `source` 결과 파일에 없음. 수는 값으로 맞춘다(1과 1.0은 같다). 낱말에 붙은 수(`pt_2`, `v1.2`)는 보지 않는다 |
| `session_beyond_records` | 경고 | 세션의 `runs`가 묶음 `runs`의 합보다 많거나, `players`에 묶음의 `players`에 없는 사람이 있음. 표본은 로그에 남은 판과 사람만 센다. 로그에 남기지 못한 판·사람이 맞으면 세션의 `acknowledged`에 이유를 적고, 그러면 세션 값을 센다 |
| `source_missing` | 경고 | `logs`나 `source`의 파일이 프로젝트에 없음. 확장자로 끝나는 것만 파일로 본다(URL, `#` 앵커, 말은 보지 않는다). `./`와 역슬래시는 같은 경로로 읽고, 경로는 프로젝트 폴더(`data/playtests.json`이면 그 위 폴더) 기준이다 |
| `computed_without_output` | 경고 | 관찰값의 `note`가 `[계산: …]`인데 `source`가 없거나 `logs`의 원본 기록임(`./`, 역슬래시, 앞뒤 공백이 달라도 같은 파일로 본다). 계산 출력을 결과 파일로 남겨 `source`로 둔다. 결과 파일은 `logs`에 넣지 않는다 |
| `session_without_observations` | 경고 | 세션에 관찰값, 단계 기록, 묶음(`groups`), 그레이박스 기록(`greybox`)이 모두 없음 |
| `stage_counts_mismatch`, `unknown_reference` | 경고 | 단계 기록의 판 수가 이어지지 않음, 지금 데이터에 없는 id([calibration](calibration.md)) |

- 컨셉 데이터를 함께 넘기지 않으면 컨셉·가설 참조를 확인하지 못해 `INCOMPLETE`다. 프로젝트 폴더(`check .`)로 검사한다.
- `--fail-on-assumed`는 선택(approved)한 컨셉의 가설 중 **확정(approved)된 버팀·틀림**이 아닌 것이 있으면 실패한다. 제안 판정, 모름, 기준 지문이 없거나 기준이 바뀐 판정은 확정이 아니다. 확정 판정인데 지문 때문에 걸린 가설은 게이트 줄에 `(지문 없음)`, `(기준 바뀜)`으로 까닭이 붙는다. `--json`에서는 `unverified`가 가설 키 그대로이고 까닭은 `unverified_reasons`에 있다. 틀림으로 확정된 가설이 있어도 실패한다(그 위에서 다음 단계로 가지 않는다).
- 검사기는 판정이 맞는지 판단하지 않는다. 검사 통과를 판정의 정당성으로 보고하지 않는다.
