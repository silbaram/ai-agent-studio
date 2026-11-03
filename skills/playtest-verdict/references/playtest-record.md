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
      "sessions": ["pt_20261105_1"], "reason": "1배·2배에서 같은 단계 비율이 80% [가정] 미만", "status": "proposed" }
  ]
}
```

## 세션 (`playtests`)

| 필드 | 필수 | 뜻 |
|---|---|---|
| `id` | 예 | 소문자·숫자·밑줄. `pt_날짜_순번`을 권한다. `[측정: data/playtests.json#id]`의 출처가 된다 |
| `date` | 예 | `YYYY-MM-DD` |
| `concept` | 예 | 시험한 컨셉 id (`design/concepts.json`) |
| `build` | 예 | 빌드를 다시 만들 수 있는 이름. 보통 커밋 해시 |
| `players` | 예 | 플레이한 사람 이름 배열. 같은 사람은 같은 이름으로 쓴다(사람 수를 센다) |
| `runs` | 예 | 이 세션의 판 수 합계 |
| `observations` | 아니오 | `[{hypothesis, value, metric, n, source, note}]`. `hypothesis`(가설 id)와 `value`(문자열 또는 수)가 필수. 없고 단계 기록도 없으면 경고 |
| `notes` | 아니오 | `[{kind: observation / preference, text}]` |
| `logs` | 아니오 | 원본 기록 파일 경로 배열 |
| `stage_stats`, `upgrades`, `growth_build` | 아니오 | 단계별 판 수와 평균 레벨·길이·처치·수입, 그때 가진 영구 강화, 판 안 성장 빌드. 가정값을 보정할 때 쓴다([calibration](calibration.md)) |
| `acknowledged` | 아니오 | 확인을 마친 경고 `{경고 코드: 이유}` |

`value`에는 해석이 아니라 본 것을 적는다. "개선됨" 대신 "42% → 18%". 사람마다 다르면 사람별로 적는다.

## 판정 (`verdicts`)

| 필드 | 필수 | 뜻 |
|---|---|---|
| `concept`, `hypothesis` | 예 | 판정하는 가설 (컨셉 id, 가설 id) |
| `result` | 예 | `holds`(버팀) / `refuted`(틀림) / `unknown`(모름) |
| `reason` | 예 | 관찰값을 `failure_signal`에 어떻게 적용했는지. 모름이면 무엇이 부족한지 |
| `sessions` | 버팀·틀림이면 예 | 근거 세션 id 배열. 그 세션에 이 가설의 관찰값이 있어야 한다 |
| `status` | 아니오 | `proposed`(판정 에이전트 제안) / `approved`(사용자 확인) / `cut`(지난 판정) |

가설 하나에 `cut`이 아닌 판정은 하나만 둔다. 다시 판정하면 지난 것을 `cut`으로 남긴다.

### 판정

| result | 조건 |
|---|---|
| `holds` | 관찰값이 있고, `failure_signal`이 나오지 않았다 |
| `refuted` | 관찰값에서 `failure_signal`이 나왔다 |
| `unknown` | 관찰값이 없다 / 표본이 가설의 `test`에 적은 계획보다 적다 / 신호가 나왔는지 기록으로 가릴 수 없다 |

판정 기준(`failure_signal`의 문턱값)은 판정하면서 바꾸지 않는다. 바꿔야 한다면 판정과 별도로 브리프를 고치고, 그 사실을 보고한다.

## 검사 내용

| 코드 | 수준 | 조건 |
|---|---|---|
| `schema`, `duplicate_id` | 오류 | 형식 위반, 세션 id 중복 |
| `unknown_concept`, `unknown_hypothesis` | 오류 | 컨셉 데이터에 없는 컨셉·가설 id. 가설에 id가 없으면 그렇게 알린다 |
| `verdict_without_evidence` | 오류 | 버팀·틀림인데 근거 세션이 없음 |
| `unknown_session` | 오류 | 판정이 가리킨 세션이 기록에 없음 |
| `session_concept_mismatch` | 오류 | 판정이 다른 컨셉의 세션을 가리킴 |
| `observation_missing` | 오류 | 버팀·틀림인데 근거 세션에 그 가설의 관찰값이 없음 |
| `duplicate_verdict` | 오류 | 한 가설에 `cut`이 아닌 판정이 둘 이상 |
| `session_without_observations` | 경고 | 세션에 관찰값도 단계 기록도 없음 |
| `stage_counts_mismatch`, `unknown_reference` | 경고 | 단계 기록의 판 수가 이어지지 않음, 지금 데이터에 없는 id([calibration](calibration.md)) |

- 컨셉 데이터를 함께 넘기지 않으면 컨셉·가설 참조를 확인하지 못해 `INCOMPLETE`다. 프로젝트 폴더(`check .`)로 검사한다.
- `--fail-on-assumed`는 선택(approved)한 컨셉의 가설 중 **확정(approved)된 버팀·틀림**이 아닌 것이 있으면 실패한다. 제안 판정과 모름은 확정이 아니다.
- 검사기는 판정이 맞는지 판단하지 않는다. 검사 통과를 판정의 정당성으로 보고하지 않는다.
