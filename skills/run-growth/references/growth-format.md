# 판 안 성장 형식

게임 프로젝트의 `data/growth.json` 한 파일에 단계별 레벨, 레벨업 선택지, 빌드를 둔다. 검사: `python3 .claude/skills/studio-data/scripts/studio.py check .`(전투 계산 데이터와 함께), 보기: `… view .`.

```json
{
  "growth": {
    "level_at": { "zone_1": 4, "zone_2": 9, "zone_3": 14 },
    "offers": 3,
    "trials": 1000,
    "seed": 7,
    "provenance": { "kind": "assumed" }
  },
  "choices": [
    { "id": "sharpen", "stats": { "attack": 2 }, "max_picks": 6 },
    { "id": "vigor", "stats": { "max_hp": 12 } }
  ],
  "builds": [
    { "id": "blade", "priority": ["sharpen", "vigor"] },
    { "id": "balanced", "priority": ["sharpen", "vigor"], "pick": "spread" }
  ]
}
```

## `growth`

| 키 | 필수 | 뜻 |
|---|---|---|
| `level_at` | 예 | `{전투 단계 id: 레벨}`. 1 이상의 정수. 레벨 1에서 시작해 그 단계까지 그 레벨이 된다. 전투 계산에 없는 단계면 오류, 삭제된 단계면 경고하고 뺀다 |
| `offers` | 예 | 레벨업마다 제시하는 선택지 수(1 이상). 선택지 수 이상이면 모두 제시 |
| `trials` | 아니오 | 반복 시뮬레이션 횟수(기본 1000, 최대 20000). 검사와 뷰어 갱신마다 다시 돈다 |
| `seed` | 아니오 | 난수 시드(기본 7). 같으면 결과가 같다 |
| `provenance` | 아니오 | 레벨·선택지의 출처. 없거나 `assumed`면 `--fail-on-assumed`에서 실패 |

## `choices`

| 키 | 필수 | 뜻 |
|---|---|---|
| `id` | 예 | 소문자·숫자·밑줄 |
| `stats` | 예 | `{스탯 이름: 수}` 하나 이상. 플레이어 스탯 이름(전투 계산의 역할 연결과 같은 이름). 전투 계산이 쓰지 않는 이름이면 경고 |
| `max_picks` | 아니오 | 최대 선택 횟수(1 이상). 닿으면 더는 제시되지 않는다 |
| `name`, `intent`, `status`, `provenance`, `acknowledged` | 아니오 | 공통 필드 |

## `builds`

| 키 | 필수 | 뜻 |
|---|---|---|
| `id` | 예 | 소문자·숫자·밑줄 |
| `priority` | 예 | 선택지 id 배열 |
| `pick` | 아니오 | `priority`(기본): 제시된 것 중 목록 앞쪽 / `spread`: 목록 중 지금까지 가장 적게 고른 것(같으면 앞쪽) |
| `name`, `intent`, `status`, `provenance`, `acknowledged` | 아니오 | 공통 필드 |

목록에 있는 것이 하나도 제시되지 않으면 제시된 것 중 `choices` 순서로 첫째를 고른다.

## 계산

1. 시행마다 레벨 1에서 시작해, 단계 순서(전투 계산의 단계 순서)대로 `level_at`까지 레벨업한다.
2. 레벨업마다 최대 횟수에 닿지 않은 선택지 중 `offers`개를 무작위로 제시하고, 빌드 규칙으로 하나를 고른다.
3. 단계마다 평균 선택 횟수와, 그만큼 더해진 스탯(평균)을 낸다.
4. 시행마다 그 시행의 스탯을 전투 계산의 그 단계 기준 장비에 더해 처치·버팀을 계산하고, 시행 전체로 평균한다. 평균 스탯으로 한 번 계산하지 않는다(타수는 올림이라 평균 스탯으로 구하면 기대값과 다르다). 같은 선택 결과는 한 번만 계산한다.
5. 시행 중 하나라도 스탯이 전투 계산에 쓸 수 없는 값(치명 확률이 1을 넘는 등)이 되면 그 빌드는 `build_invalid` 오류로 알리고 비교에서 뺀다.
6. 빌드 둘을 (단계, 적)마다 맞춰 지표별로 비교한다. 처치 타수·시간은 적을수록, 버티는 타수·시간은 많을수록 낫다. 한 빌드가 모든 곳에서 같거나 낫고 어딘가에서 나으면 진 빌드에 `build_dominated`.

## 검사 내용

| 코드 | 수준 | 조건 |
|---|---|---|
| `schema`, `duplicate_id` | 오류 | 형식 위반(레벨·제시 수·시행·선택지 스탯·최대 횟수·빌드 규칙), id 중복 |
| `unknown_stage` | 오류 | `level_at`의 단계가 전투 계산에 없음 |
| `unknown_choice` | 오류 | 빌드의 `priority`에 없는 선택지 |
| `build_invalid` | 오류 | 빌드의 성장 스탯이 전투 계산에 쓸 수 없는 값이 됨. 그 빌드는 비교에서 뺀다 |
| `level_decreases` | 경고 | 뒤 단계의 레벨이 앞 단계보다 낮음 |
| `stat_not_in_combat` | 경고 | 선택지의 스탯을 전투 계산이 쓰지 않음(오타이거나 전투 밖 효과). 의도면 그 선택지의 `acknowledged` |
| `cut_referenced` | 경고 | `level_at`이 삭제된 전투 단계를 가리킴. 계산에서 뺀다 |
| `nothing_to_compare` | 경고 | 삭제되지 않은 선택지나 빌드가 없어 아무것도 계산하지 않음 |
| `build_dominated` | 경고 | 다른 빌드가 모든 단계·적·지표에서 같거나 나음 |

전투 계산이 없거나 그 검사에 오류·미확인이 있으면 계산하지 않고 미확인으로 센다(`INCOMPLETE`).
