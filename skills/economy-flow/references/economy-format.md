# 재화 흐름 형식

게임 프로젝트의 `data/economy.json` 한 파일에 재화, 단계별 수입, 구매 계획을 둔다. 검사: `python3 .claude/skills/studio-data/scripts/studio.py check .`(적·아이템·영구 강화·강화·합성 데이터와 함께), 보기: `… view .`.

```json
{
  "economy": {
    "currencies": { "gold": { "name": "골드" }, "soul": { "name": "영혼", "carry": true } },
    "kill_reward": "gold",
    "sell": { "currency": "gold", "ratio": 0.5 },
    "prices": { "items": "gold", "enhance": "gold", "recipes": "gold", "upgrades": "soul" },
    "time_unit": "초",
    "leftover_max": 0.35,
    "provenance": { "kind": "assumed" }
  },
  "stages": [
    { "id": "zone_1", "duration": 300, "kills": { "slime": 40 }, "drops": { "chest_normal": 2 }, "income": { "soul": 8 } }
  ],
  "purchases": [
    { "id": "buy_iron_sword", "price": { "item": "iron_sword" }, "target": [60, 300] },
    { "id": "weapon_plus_3", "price": { "enhance": "weapon_plus", "level": 3, "from": 2 } },
    { "id": "meta_weapon_1", "price": { "upgrade": "weapon_1" }, "target": [1, 2] }
  ]
}
```

## `economy`

| 키 | 필수 | 뜻 |
|---|---|---|
| `currencies` | 예 | `{재화 id: {name, carry}}`. `carry: true`면 판 사이에 남는 재화(판 수로 계산) |
| `kill_reward` | `kills`를 쓰면 예 | 적 데이터 `reward`의 재화 |
| `sell` | `drops`를 쓰면 예 | `{currency, ratio}`. 드랍 아이템 가격 중 판매로 받는 비율(0~1) |
| `prices` | 출처 가격을 쓰면 예 | 가격 출처별 재화: `items`, `enhance`, `recipes`, `upgrades` |
| `time_unit` | 아니오 | 단계 길이와 구매 시점의 단위 이름(기본 "초") |
| `leftover_max` | 아니오 | 판 끝에 남아도 되는 수입 비율(0~1). 넘으면 경고 |
| `provenance` | 아니오 | 수입·구매 계획의 출처. 없거나 `assumed`면 `--fail-on-assumed`에서 실패 |

## `stages` (한 판의 순서대로)

| 키 | 필수 | 뜻 |
|---|---|---|
| `id` | 예 | 소문자·숫자·밑줄 |
| `duration` | 예 | 0보다 큰 길이(`time_unit`) |
| `kills` | 아니오 | `{적 id: 기대 처치 수}`. 처치 수 × `reward` |
| `drops` | 아니오 | `{드랍 테이블 id: 기대 드랍 횟수}`. 횟수 × 판매 기대값 × `sell.ratio` |
| `income` | 아니오 | `{재화: 양}`. 그 밖의 수입 |
| `name`, `intent`, `status`, `provenance`, `acknowledged` | 아니오 | 공통 필드 |

드랍 한 번의 판매 기대값 = Σ(칸 가중치 비율 × 가격). 아이템 칸은 그 아이템 `price`, 희귀도 칸은 그 희귀도 활성 아이템 `price`의 평균이다. 삭제된 아이템 칸은 나오지 않으므로 빼고 나머지 가중치로 나눈다. 가격이 없는 아이템이 끼면 `price_missing`, 희귀도에 활성 아이템이 하나도 없으면 `rarity_empty` 오류다.

## `purchases` (사는 순서대로)

| 키 | 필수 | 뜻 |
|---|---|---|
| `id` | 예 | 소문자·숫자·밑줄 |
| `price` | 예 | `{amount, currency}` 또는 `{item}` / `{enhance, level, from}` / `{recipe}` / `{upgrade}` 중 하나 |
| `target` | 아니오 | 의도한 시점 [최소, 최대]. 판 안 재화는 `time_unit`, 판 사이 재화는 판 수. 한쪽은 `null`, 둘 다 있으면 최소 ≤ 최대 |
| `after` | 아니오 | 판 안 재화 구매만: 이 단계가 시작되기 전에는 살 수 없음(상점·제작대가 그 단계부터 열릴 때) |
| `name`, `intent`, `status`, `provenance`, `acknowledged` | 아니오 | 공통 필드 |

| price | 가격 |
|---|---|
| `{"item": id}` | 아이템 `price` |
| `{"enhance": id, "level": n, "from": m}` | 강화 `id`의 +m → +n 기대 비용(0 ≤ m < n ≤ 단계 수, m 기본 0). 계산은 [crafting-format](../../crafting-balance/references/crafting-format.md#기대-비용) |
| `{"recipe": id}` | 합성 `cost` ÷ `success` |
| `{"upgrade": id}` | 영구 강화 `cost` |

- 판 안 재화: 누적 수입이 앞선 구매의 합 + 이 가격에 닿는 시점, `after` 단계가 시작하는 시점, 바로 앞 구매 시점 중 가장 늦은 때(계획 순서대로 산다). 살 수 없으면 `unaffordable` 경고를 내고, 남는 재화 계산에서 뺀다.
- 영구 강화는 계획에서 선행 조건(`requires`)보다 앞에 있으면 `requirement_missing` 경고.
- 삭제(`cut`)된 아이템·강화·합성·영구 강화를 사면 `cut_referenced` 경고를 내고 계획에서 뺀다(재화를 쓰지 않는다).
- 판 사이 재화: (앞선 구매의 합 + 이 가격) ÷ 한 판 수입의 올림. 한 판 수입이 0이면 살 수 없다.
- 판 끝에 남는 재화: 판 안 재화마다 한 판 수입 − 산 것의 합. 그 비율이 `leftover_max`를 넘으면 경고.

## 검사 내용

| 코드 | 수준 | 조건 |
|---|---|---|
| `schema`, `duplicate_id` | 오류 | 형식 위반(재화·단계·처치·드랍·수입·가격·목표), id 중복, 없는 재화, 가격 출처의 재화가 정해지지 않음, 강화 단계 범위 밖 |
| `unknown_enemy`, `unknown_drop_table`, `unknown_item`, `unknown_upgrade`, `unknown_enhance`, `unknown_recipe` | 오류 | 원본에 없는 id |
| `price_missing` | 오류 | 가격 출처에 가격(`price`·`cost`)이 없음 |
| `rarity_empty` | 오류 | 드랍 테이블의 희귀도 칸에 해당하는 활성 아이템이 없음 |
| `price_source_invalid` | 오류 | 가격으로 쓰는 강화·합성의 형식이 틀려 가격을 계산하지 않음(강화·합성 검사 결과를 먼저 고친다) |
| `unknown_stage` | 오류 | `after`에 적은 단계가 없음 |
| `requirement_missing` | 경고 | 영구 강화를 선행 조건보다 먼저 사는 계획 |
| `reward_missing` | 경고 | 처치를 센 적에 `reward`가 없어 0으로 셈 |
| `cut_referenced` | 경고 | 삭제된 적의 처치를 셈(수입에서 뺀다), 또는 삭제된 항목을 삼(계획에서 뺀다) |
| `unaffordable` | 경고 | 한 판 수입(판 사이 재화는 판 사이 수입)으로 살 수 없음 |
| `target_out_of_range` | 경고 | 구매 시점이나 판 수가 목표를 벗어남 |
| `currency_piles_up` | 경고 | 판 끝에 남는 재화의 비율이 `leftover_max`를 넘음 |

쓰는 데이터(적·아이템·영구 강화·강화·합성)를 함께 넘기지 않았거나 읽지 못하면 그 부분은 계산하지 않고 미확인으로 센다(`INCOMPLETE`). 앞 단계가 미확인이면 구매 시점과 판 수, 남는 재화도 내지 않는다.
