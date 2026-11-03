# 강화·합성 형식

게임 프로젝트의 `data/crafting.json` 한 파일에 강화와 합성을 둔다. 검사: `python3 .claude/skills/studio-data/scripts/studio.py check .`(아이템 데이터와 함께), 보기: `… view .`.

```json
{
  "crafting": {
    "other_sources": { "rusty_sword": "시작 장비" },
    "provenance": { "kind": "assumed" }
  },
  "enhance": [
    { "id": "weapon_plus", "applies_to": { "slot": "weapon" },
      "levels": [
        { "cost": 50, "bonus_pct": 0.1 },
        { "cost": 100, "success": 0.8, "bonus_pct": 0.1 },
        { "cost": 200, "success": 0.6, "on_fail": "down", "bonus_pct": 0.15 }
      ], "status": "proposed", "provenance": { "kind": "assumed" } }
  ],
  "recipes": [
    { "id": "forge_iron", "inputs": [{ "item": "rusty_sword", "count": 1 }, { "item": "whetstone", "count": 2 }],
      "output": { "item": "iron_sword" }, "cost": 30 },
    { "id": "merge_t1", "inputs": [{ "match": { "tier": 1, "slot": "weapon" }, "count": 2 }],
      "output": { "match": { "tier": 2, "slot": "weapon" } } }
  ]
}
```

## `crafting`

| 키 | 필수 | 뜻 |
|---|---|---|
| `other_sources` | 아니오 | `{아이템 id: 얻는 곳}`. 드랍·합성 밖에서 얻는 아이템(시작 장비, 상점, 퀘스트) |
| `provenance` | 아니오 | 강화·합성 수치의 출처. 없거나 `assumed`면 `--fail-on-assumed`에서 실패 |

## 강화 (`enhance`)

| 키 | 필수 | 뜻 |
|---|---|---|
| `id` | 예 | 소문자·숫자·밑줄 |
| `applies_to` / `items` | 둘 중 하나만 | 대상: `{필드: 값}` 조건(삭제 제외 모든 맞는 아이템) 또는 아이템 id 배열. 둘을 함께 쓰면 오류 |
| `levels` | 예 | 단계 배열(첫 칸이 +1). 단계마다 `cost`(0 이상), `success`(0 초과 1 이하, 기본 1), `on_fail`(`keep` / `down` / `destroy`, 기본 `keep`), `bonus_pct`(0 이상, 기본 0) |
| `replace_cost` | 파괴가 있으면 예 | 파괴된 아이템을 다시 구하는 비용 |
| `name`, `intent`, `status`, `provenance`, `acknowledged` | 아니오 | 공통 필드 |

### 기대 비용

한 단계(k → k+1)를 오르는 기대 비용 x_k:

| 실패 시 | x_k |
|---|---|
| `keep` | 비용 ÷ 성공률 |
| `down` | (비용 + (1 − 성공률) × x_{k−1}) ÷ 성공률. 첫 단계는 `keep`과 같다 |
| `destroy` | (비용 + (1 − 성공률) × (replace_cost + x_0 + … + x_{k−1})) ÷ 성공률 |

0단계에서 +n까지의 기대 비용은 x_0 + … + x_{n−1}이다. 기대 시도 수는 같은 식에서 비용을 1, `replace_cost`를 0으로 둔 값이다. `bonus_pct`는 누적된다.

## 합성 (`recipes`)

| 키 | 필수 | 뜻 |
|---|---|---|
| `id` | 예 | 소문자·숫자·밑줄 |
| `inputs` | 예 | 재료 배열. 칸마다 `item`(id) 또는 `match`(`{필드: 값}`, 맞는 것 아무거나 하나), `count`(1 이상 정수, 기본 1) |
| `output` | 예 | `item` 또는 `match`(맞는 것 중 균등하게 하나), `count`(기본 1) |
| `cost` | 아니오 | 합성 비용(0 이상, 기본 0) |
| `success` | 아니오 | 성공 확률(0 초과 1 이하, 기본 1) |
| `name`, `intent`, `status`, `provenance`, `acknowledged` | 아니오 | 공통 필드 |

- **가치 비율** = 결과 수 × 결과 예산 × 성공률 ÷ Σ(재료 수 × 재료 예산). `match` 재료 칸은 맞는 것 중 **가장 싼** 아이템(플레이어는 싼 것을 넣는다), `match` 결과 칸은 맞는 아이템 예산의 **평균**(무작위로 하나가 나온다). 고유 효과(`unique_effect`) 아이템이나 원가 없는 스탯이 끼면 비교하지 않고 이유를 `value_note`에 적는다. 스탯 예산(`budget.json`의 items)이 있을 때만 계산하고, 하지 않았으면 `value_skipped`에 이유를 적는다.
- **특정 결과까지**: 결과가 n가지면 특정 하나를 얻기까지 기대 합성 n ÷ (결과 수 × 성공률)회, 재료는 그 횟수 × 재료 수 합계.

## 검사 내용

| 코드 | 수준 | 조건 |
|---|---|---|
| `schema`, `duplicate_id` | 오류 | 형식 위반(단계·재료·결과·확률·비용·other_sources), id 중복, 파괴 단계인데 `replace_cost` 없음 |
| `unknown_item` | 오류 | 아이템 데이터에 없는 id |
| `match_empty` | 오류 | `applies_to`·`match` 조건에 맞는 아이템이 없음 |
| `value_loop` | 오류 | 재료가 한 종류인 합성을 돌면 아이템이 늘어나는 고리. 무작위 결과를 거치면 결과마다 처음 재료로 돌아오는 최선 수율의 평균으로 본다 |
| `cut_referenced` | 경고 | 삭제된 아이템을 재료·결과로 씀. 그 합성은 계산에서 뺀다 |
| `recipe_loses_value` | 경고 | 가치 비율이 허용 오차(`budget.json`의 tolerance, 기본 0.2) 아래 |
| `enhance_overtakes_tier` | 경고 | 최고 단계까지 강화하면 같은 대상 안 다음 티어의 기대 예산을 허용 오차 넘게 넘음 |
| `unobtainable` | 경고 | 드랍·합성 결과·other_sources 어디서도 얻을 수 없는 활성 아이템. 일부러 얻는 곳이 없으면(시즌 보상 등) 그 아이템의 `acknowledged`에 `{"unobtainable": "이유"}` |

아이템 데이터를 함께 넘기지 않았거나 읽지 못하면 참조·가치·획득 경로를 확인하지 않고 미확인으로 센다(`INCOMPLETE`).
