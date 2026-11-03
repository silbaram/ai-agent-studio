# 스탯 예산 형식

게임 프로젝트의 `data/budget.json` 한 파일에 원가, 곡선, 배수, 원형을 둔다. 검사: `python3 .claude/skills/studio-data/scripts/studio.py check .`(아이템·적 데이터와 함께), 초안: `… draft . --archetype <원형> --at <기준 값>`, 보기: `… view .`.

```json
{
  "budget": {
    "items": {
      "costs": { "attack": 1.0, "attack_speed": 20.0, "max_hp": 0.2, "armor": 1.5 },
      "curve": { "by": "tier", "growth": "linear", "base": 8, "rate": 7 },
      "multiplier": { "field": "slot", "values": { "weapon": 1, "armor": 1, "relic": 0.4 } }
    },
    "enemies": {
      "costs": { "hp": 0.1, "damage": 1.0 },
      "curve": { "by": "zone", "growth": "exponential", "base": 10, "rate": 0.5 },
      "multiplier": { "field": "rank", "values": { "normal": 1, "elite": 2.7, "boss": 8.5 } }
    },
    "tolerance": 0.2,
    "provenance": { "kind": "assumed" }
  },
  "archetypes": [
    { "id": "plate", "for": "items", "split": { "max_hp": 0.5, "armor": 0.5 }, "fields": { "slot": "armor" },
      "intent": "체력과 방어를 반씩", "status": "proposed", "provenance": { "kind": "assumed" } }
  ]
}
```

## `budget`

`items`와 `enemies` 중 하나 이상이 필요하다. 쪽마다:

| 키 | 필수 | 뜻 |
|---|---|---|
| `costs` | 예 | `{스탯 이름: 0보다 큰 원가}`. 그 쪽 항목의 `stats` 이름 그대로 |
| `curve.by` | 예 | 곡선의 기준이 되는 항목 필드(예: `tier`, `zone`, `level`) |
| `curve.growth` | 아니오 | `linear`(기본): base + rate × (기준 − 1) / `exponential`: base × (1 + rate)^(기준 − 1) / `table`: `values`에 {기준: 예산} |
| `curve.base`, `curve.rate` | linear·exponential이면 예 | base > 0. exponential은 rate > −1 |
| `multiplier` | 아니오 | `{field: 항목 필드 이름, values: {값: 0보다 큰 배수}}`. 같은 기준 안에서 크기를 나눈다 |

| 키 | 필수 | 뜻 |
|---|---|---|
| `tolerance` | 아니오 | 허용 오차 비율(0 이상 1 미만, 기본 0.2 = ±20%) |
| `provenance` | 아니오 | 곡선·원가의 출처. 없거나 `assumed`면 `--fail-on-assumed`에서 실패 |

곡선 형태 이름(`growth`, `base`, `rate`)은 메타 성장 시뮬레이터의 난이도 곡선([meta-model](../../progression-economy/references/meta-model.md))과 같다.

## `archetypes`

| 키 | 필수 | 뜻 |
|---|---|---|
| `id` | 예 | 소문자·숫자·밑줄 |
| `for` | 예 | `items` / `enemies` |
| `split` | 예 | `{스탯: 비율}`. 합이 1. 모든 스탯에 그 쪽 원가가 있어야 한다 |
| `fields` | 아니오 | 초안에 그대로 넣을 필드(예: `slot`, `rank`). 곡선 기준 필드(`tier` 등)는 넣지 않는다. 기준 값은 `--at`으로 정한다 |
| `name`, `intent`, `status`, `provenance` | 아니오 | 공통 필드 |

## 비교 규칙

- 삭제(`cut`) 항목은 비교하지 않는다. `unique_effect` 아이템은 "판정 제외"다.
- 기준 필드가 없거나 수가 아닌 항목, 원가 없는 스탯이 있는 항목, 배수 표에 그 값이 없는 항목은 비교하지 않고 미확인으로 센다(`INCOMPLETE`). 각각 경고로 이유를 알린다.
- 허용 오차를 넘은 항목은 경고한다. 의도한 예외는 **그 항목의** `acknowledged`에 적는다(`items.json`·`enemies.json` 쪽). 예: `{"over_budget": "보스 직전 보상 아이템"}`.

## 초안 (`draft`)

- 기대 예산 = 곡선(`--at`) × 배수(원형 `fields`나 `--set`으로 정한 배수 필드 값). 스탯 = 기대 예산 × 비율 ÷ 원가.
- 반올림: 10 이상은 정수, 1 이상은 소수 한 자리, 그 아래는 세 자리.
- 출력 항목: `id`, 기준 필드, 원형 `fields`, `--set` 필드, `stats`, `status: proposed`, `provenance: {kind: computed, source: data/budget.json#원형}`, `intent`.
- 파일에 쓰지 않는다. 원형이나 배수 값이 없거나, 기대 예산이 0 이하이거나, `--set`으로 `id`·`stats`·`status`·`provenance`·곡선 기준 필드를 정하려 하면 종료 코드 2.
- 다른 원형이나 다른 쪽(아이템·적)의 오류는 초안을 막지 않는다. 고른 원형과 그 쪽 설정에 오류가 있을 때만 막는다.

## 원가 제안 (`suggested_costs`)

`data/combat.json`이 있고 형식이 맞으면, 전투 단계마다 플레이어·적 스탯 1의 값어치를 잰다.

- 힘 = ln(초당 주는 피해) + ln(버티는 실질 체력)을 그 단계의 적들(적 쪽은 그 단계의 플레이어)에 대해 평균한 값
- 스탯마다 아주 조금 올렸을 때 힘이 얼마나 오르는지를, 공격 1을 올렸을 때와 비교한 비율
- 기획자가 정한 공격 스탯 원가를 곱해 원가 단위로 보여 준다

- 서로 피해를 주고받지 못하는 적(피해 0)은 빼고 잰다. 뺀 수를 함께 보인다.
- 그 쪽이 원가를 정했거나 데이터에서 실제로 쓰는 스탯만 보인다.

전투 공식의 역할(체력·공격·방어·공격 속도·치명)에 연결된 스탯만 잴 수 있다.

## 검사 내용

| 코드 | 수준 | 조건 |
|---|---|---|
| `schema`, `duplicate_id` | 오류 | 형식 위반(원가·곡선·배수·허용 오차·원형), 원형 id 중복, split 합이 1이 아님, split 스탯에 원가 없음 |
| `curve_missing_point` | 오류 | table 곡선에 항목의 기준 값이 없음 |
| `curve_not_positive` | 오류 | 항목의 기준 값에서 기대 예산(곡선 × 배수)이 0 이하 |
| `over_budget`, `under_budget` | 경고 | 예산이 기대 예산의 허용 범위를 벗어남 |
| `stat_without_cost` | 경고 | 원가 없는 스탯이 있어 그 항목들을 비교하지 못함 |
| `multiplier_missing` | 경고 | 배수 표에 항목의 값이 없어 비교하지 못함 |
| `curve_field_missing` | 경고 | 곡선 기준 필드가 없거나 수가 아닌 항목이 있음 |
| `suggestions_unavailable` | 경고 | 전투 계산으로 원가 제안을 만드는 중 오류가 남 |

한쪽(아이템·적) 설정이 틀리면 그쪽만 비교하지 않고, 다른 쪽은 계속 비교한다. 항목의 `acknowledged` 형식 규칙은 다른 검사와 같다(이유를 비우면 확인으로 보지 않는다).
