# 레벨 구성 형식

게임 프로젝트의 `data/levels.json` 한 파일에 위협도 예산과 레벨을 둔다. 검사: `python3 .claude/skills/studio-data/scripts/studio.py check .`(적·전투 계산·스탯 예산·재화 흐름 데이터와 함께), 보기: `… view .`.

레벨 구성 파일은 하나만 쓴다. 둘이면 뒤의 파일이 오류다. 단계 범위와 처치 수를 파일을 넘어 세지 않기 때문이다. 최상위에 `levels`나 `threat_budget`이 있어야 이 형식으로 읽는다. 게임이 자기 형식으로 쓰는 `levels.json`은 건너뛴다. 다만 게임 파일에 최상위 `levels` 키가 있으면 이 형식으로 검사해 오류가 나므로, 그 파일은 `design/`·`data/`와 프로젝트 폴더 바로 아래가 아닌 곳에 둔다.

```json
{
  "threat_budget": {
    "curve": { "growth": "linear", "base": 90, "rate": 60 },
    "roles": { "room": 1, "elite_room": 1.2, "boss_room": 1 },
    "tolerance": 0.25,
    "provenance": { "kind": "assumed" }
  },
  "levels": [
    {
      "id": "crypt",
      "name": "버려진 지하묘지",
      "combat_stage": "zone_1",
      "intent": "느린 적으로 시작해 궁수로 움직임을 강요한다",
      "encounters": [
        { "id": "crypt_skirmish", "role": "room", "repeat": 5, "enemies": { "slime": 6, "skeleton_archer": 4 } },
        { "id": "crypt_lord", "role": "boss_room", "enemies": { "bone_lord": 1 } }
      ],
      "status": "approved",
      "provenance": { "kind": "assumed" }
    }
  ]
}
```

## `threat_budget`

없으면 위협도만 내고 예산과 비교하지 않는다(`INCOMPLETE`). 아래와 곡선에 없는 키는 오류다(`_`로 시작하는 키와 `note`는 메모로 둔다). 곡선의 기준은 전투 단계의 순서로 정해져 있어 스탯 예산의 `by`를 쓰지 않는다.

| 키 | 필수 | 뜻 |
|---|---|---|
| `curve` | 예 | `{growth, base, rate}`. `linear`: base + rate × (순서 − 1), `exponential`: base × (1 + rate)^(순서 − 1). 순서는 전투 계산의 삭제되지 않은 단계 순서(1부터). `table`: `{growth: "table", values: {단계 id: 값}}`. 표에 없는 단계는 오류다 |
| `roles` | 예 | `{역할 이름: 0보다 큰 배수}` |
| `tolerance` | 아니오 | 0 이상 1 미만의 비율(기본 0.2). 위협도와 처치 수에 함께 쓴다 |
| `provenance` | 아니오 | 예산의 출처. 가정이거나 비어 있으면 `--fail-on-assumed`에서 실패한다 |

## `levels`

아래에 없는 키는 오류다(`_`로 시작하는 키는 메모로 둔다).

| 키 | 필수 | 뜻 |
|---|---|---|
| `id` | 예 | 소문자·숫자·밑줄 |
| `name`, `intent`, `note` | 아니오 | 이름, 의도, 메모 |
| `combat_stage` | 아니오 | 이어지는 전투 단계 id. 없으면 레벨 id와 같은 단계 |
| `encounters` | 예 | 조우 배열. 판에서 지나는 순서대로 |
| `status`, `provenance`, `acknowledged` | 아니오 | 다른 데이터와 같다. 경고는 레벨에서 `{코드: {조우나 적 id: 이유}}`로 확인한다. 단계 전체의 경고(`kills_differ`, `enemy_unplaced`)는 그 단계의 어느 레벨에서든 확인할 수 있다 |

한 전투 단계의 레벨은 한 판에 모두 지나는 것으로 센다. 대체 맵(한 판에 그중 하나만 나옴)은 조우의 `repeat`를 나오는 확률로 나눠 적는다. 셋 중 하나가 나오면 `repeat`는 1/3배다.

## `encounters`

조우 id는 파일 전체에서 겹치지 않는다. 아래에 없는 키는 오류다(`_`로 시작하는 키는 메모로 둔다).

| 키 | 필수 | 뜻 |
|---|---|---|
| `id` | 예 | 소문자·숫자·밑줄 |
| `name`, `intent`, `note` | 아니오 | 이름, 의도, 메모 |
| `role` | 예산이 있으면 예 | `threat_budget.roles`의 역할 |
| `enemies` | 예 | `{적 id: 0보다 큰 수}`. 한 번 만날 때 나오는 수(평균이면 소수) |
| `repeat` | 아니오 | 한 판에서 만나는 횟수(기본 1, 평균이면 소수) |

## 계산

- **조우의 위협도**: Σ(적 수 × 적의 위협도). 적의 위협도는 적 검사의 값이다. 스탯 예산이 있으면 그 적 원가, 없으면 `threat_weights`로 낸다. `repeat`는 곱하지 않는다.
- **예산**: 곡선 값 × 역할 배수. 범위는 ±`tolerance`다.
- **한 판 위협도**: Σ(조우의 위협도 × `repeat`).
- **처치 수**: Σ(적 수 × `repeat`). 한 전투 단계의 레벨을 모두 더해 재화 흐름의 `kills`와 비교한다. 재화 흐름의 단계는 `combat_stage`로, 없으면 같은 id로 잇는다.

## 검사

| 코드 | 수준 | 조건 |
|---|---|---|
| `schema` | 오류 | 형식 위반, 레벨·조우·예산·곡선의 모르는 키, 레벨 구성 파일이 둘 이상 |
| `duplicate_id` | 오류 | 조우 id가 겹침 |
| `unknown_role` | 오류 | `roles`에 없는 역할 |
| `unknown_enemy` | 오류 | 적 데이터에 없는 id |
| `unknown_stage` | 오류 | 전투 계산에 없는 단계 |
| `curve_missing_point` | 오류 | `table` 곡선에 그 단계가 없음 |
| `curve_not_positive` | 오류 | 그 단계의 곡선 값이 0 이하 |
| `cut_referenced` | 경고 | 삭제된 적이나 단계를 가리킴. 계산에서 뺀다 |
| `over_budget`, `under_budget` | 경고 | 위협도가 예산 범위 밖 |
| `enemy_not_in_stage` | 경고 | 전투 단계에 나오지 않는 적을 놓음 |
| `enemy_unplaced` | 경고 | 전투 단계의 적이 어떤 조우에도 없음 |
| `kills_differ` | 경고 | 조우의 처치 수가 재화 흐름과 허용 오차를 넘게 다름 |
| `kills_not_linked` | 경고 | 처치 수가 있는 재화 흐름 단계가 어떤 레벨이나 전투 단계와도 이어지지 않아 맞춰 보지 못함. 일부러 그렇다면 아무 레벨의 `acknowledged`에 `{"kills_not_linked": {재화 흐름 단계 id: 이유}}`로 적는다 |

형식이 틀렸거나 없는 적을 가리키는 조우가 있는 단계, 형식이 틀려 빠진 레벨이 있는 단계는 `enemy_unplaced`, `enemy_not_in_stage`, `kills_differ`를 보지 않는다. 일부만 세어 틀린 경고를 내지 않기 위해서다. 어느 단계인지 알 수 없는 레벨이 있으면 모든 단계에서 보지 않고 `kills_not_linked`도 내지 않는다. 조우가 빠진 레벨의 한 판 위협도는 내지 않는다.

미확인(`INCOMPLETE`): 적이나 전투 계산을 함께 읽지 않음, 적 검사를 마치지 못함, `threat_budget`이 없음, 조우가 없는 전투 단계가 있음, 계산한 조우가 하나도 없음. 재화 흐름은 레벨이 가리키는 데이터가 아니므로 없어도 미확인이 아니다.
