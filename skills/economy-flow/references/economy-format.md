# 재화 흐름 형식

게임 프로젝트의 `data/economy.json` 한 파일에 재화, 단계별 수입, 구매 계획을 둔다. 검사: `python3 .claude/skills/studio-data/scripts/studio.py check .`(적·아이템·영구 강화·강화·합성 데이터와 함께), 보기: `… view .`.

```json
{
  "economy": {
    "currencies": { "gold": { "name": "골드" }, "soul": { "name": "영혼", "carry": true, "meta_config": "meta.json" } },
    "kill_reward": "gold",
    "sell": { "currency": "gold", "ratio": 0.5 },
    "prices": { "items": "gold", "enhance": "gold", "recipes": "gold", "upgrades": "soul" },
    "time_unit": "초",
    "leftover_max": 0.35,
    "provenance": { "kind": "assumed" }
  },
  "stages": [
    { "id": "zone_1", "combat_stage": "zone_1", "duration": 300, "kills": { "slime": 40 }, "drops": { "chest_normal": 2 }, "income": { "soul": 8 } }
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
| `currencies` | 예 | `{재화 id: {name, carry, meta_config}}`. `carry: true`면 판 사이에 남는 재화(판 수로 계산). `meta_config`는 판 사이 재화에만: 이 재화를 시뮬레이션하는 메타 성장 설정 파일(`simulate`의 설정, 이 파일이 있는 폴더 기준 경로). 적으면 한 판 수입과 영구 강화 구매 순서를 그 설정과 맞춰 본다 |
| `kill_reward` | `kills`를 쓰면 예 | 적 데이터 `reward`의 재화. 적 데이터에는 재화 단위가 없고, 어느 재화인지는 여기서 정한다 |
| `sell` | `drops`를 쓰면 예 | `{currency, ratio}`. 드랍 아이템 가격 중 판매로 받는 비율(0~1) |
| `prices` | 출처 가격을 쓰면 예 | 가격 출처별 재화: `items`, `enhance`, `recipes`, `upgrades`. 재화 이름이 틀리면 그 출처를 쓰는 구매만 빼고 나머지는 계산한다 |
| `time_unit` | 아니오 | 단계 길이와 구매 시점의 단위 이름(기본 "초") |
| `leftover_max` | 아니오 | 판 끝에 남아도 되는 수입 비율(0~1). 넘으면 경고 |
| `purchase_timing` | 아니오 | `any`(기본): 돈이 모이는 시점에 산다 / `stage_end`: 돈이 모인 단계가 끝날 때 산다(라운드 사이의 상점). 구매 시점이 그 단계의 끝이 되고 `target`도 그 시점으로 잰다 |
| `provenance` | 아니오 | 수입·구매 계획의 출처. 없거나 `assumed`면 `--fail-on-assumed`에서 실패 |

## `stages` (한 판의 순서대로)

| 키 | 필수 | 뜻 |
|---|---|---|
| `id` | 예 | 소문자·숫자·밑줄. 전투 계산의 단계와 같은 id일 필요는 없다 |
| `combat_stage` | 아니오 | 이 단계와 같은 구간인 전투 계산의 단계 id. 적으면 그 단계가 있는지, 처치를 센 적이 그 전투 단계에 나오는지(전투 계산과 같은 규칙: 목록 또는 구역, 삭제된 적 제외) 확인한다(구간을 두 파일에 따로 정의하므로, 같은 구간이면 이어 둔다) |
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
- 영구 강화는 계획에서 선행 조건(`requires`)보다 앞에 있으면 `requirement_missing` 경고. 같은 영구 강화를 두 번 사면 `duplicate_purchase` 경고.
- 같은 강화의 구매는 `from`이 앞 구매의 `level`과 이어져야 한다(처음은 0). 건너뛰거나 겹치면 `enhance_gap` 경고.
- 형식 오류나 미확인(함께 읽지 않은 데이터) 때문에 가격을 내지 못한 구매가 있으면, 그 재화의 뒤 구매는 시점·판 수·목표를 내지 않고(`blocked`에 그 구매 id), 그 재화의 남는 양도 내지 않는다. 빼고 세면 시점이 앞당겨지고 남는 재화가 부풀려진다. 재화 이름이 틀린 구매(가격 출처의 재화 오타 등)는 가장 비슷한 재화(오타 추정)를 막고, 비슷한 재화도 없으면 모든 재화를 막는다.
- 삭제(`cut`)된 아이템·강화·합성·영구 강화를 사면 `cut_referenced` 경고를 내고 계획에서 뺀다(재화를 쓰지 않는다).
- 판 사이 재화: (앞선 구매의 합 + 이 가격) ÷ 한 판 수입의 올림. 한 판 수입이 0이면 살 수 없다.
- 판 끝에 남는 재화: 판 안 재화마다 한 판 수입 − 산 것의 합. 그 비율이 `leftover_max`를 넘으면 경고.
- 단계 하나를 계산하지 못하면(형식 오류·미확인) 그 뒤 단계의 누적 수입은 내지 않는다(`cumulative`가 null).

## 메타 성장 설정과 맞춰 보기 (`meta_config`)

판 사이 재화는 메타 성장 시뮬레이터(`simulate`)의 설정에도 수입(추상 모델은 방마다 `per_room`과 보너스 방, 전투 계산 모델은 단계별 `per_stage`)과 구매 순서(구매 정책)가 있다. 두 곳에 따로 적으면, 시뮬레이터의 판 수와 이 계산의 판 수가 다를 때 원인이 "지는 판"인지 "수입·순서 정의가 다름"인지 알 수 없다. `meta_config`를 적으면:

- 한 판 수입(이 파일의 단계 수입 합)과 설정의 "끝까지 깬 판" 수입이 다르면 `meta_income_differs` 경고. 설정이 `economy` 연결로 이 재화의 수입을 읽으면 같은 원본이라 비교하지 않는다.
- 이 계획의 영구 강화 구매 순서와 시뮬레이터가 정책대로 사는 순서(재화가 충분할 때)가 다르면 `meta_order_differs` 경고. 둘에 함께 나오는 강화만 비교한다. 설정의 구매 정책이 `economy`(이 구매 계획 순서)면 비교하지 않는다.
- 설정 파일을 읽지 못하거나 형식이 틀리면 그 재화(`economy.currencies.<재화>`)의 `schema` 오류다. 재화 흐름의 다른 계산은 계속한다. 설정과 그 `upgrades_file`이 바뀌지 않았으면 다시 읽지 않는다.

가장 간단한 방법은 시뮬레이터 설정(전투 계산 모델)이 이 파일을 원본으로 읽게 하는 것이다: `"economy": {"file": "economy.json", "currency": "<이 재화>"}`, `"purchase_policy": "economy"`([meta-model](../../progression-economy/references/meta-model.md#재화-흐름과-같은-원본-쓰기)). 그러면 판 수의 차이는 지는 판 때문이다.

## 검사 내용

| 코드 | 수준 | 조건 |
|---|---|---|
| `schema`, `duplicate_id` | 오류 | 형식 위반(재화·단계·처치·드랍·수입·가격·목표), id 중복, 없는 재화, 가격 출처의 재화가 정해지지 않음, 강화 단계 범위 밖 |
| `unknown_enemy`, `unknown_drop_table`, `unknown_item`, `unknown_upgrade`, `unknown_enhance`, `unknown_recipe` | 오류 | 원본에 없는 id |
| `price_missing` | 오류 | 가격 출처에 가격(`price`·`cost`)이 없음 |
| `rarity_empty` | 오류 | 드랍 테이블의 희귀도 칸에 해당하는 활성 아이템이 없음 |
| `price_source_invalid` | 오류 | 가격으로 쓰는 강화·합성의 형식이 틀려 가격을 계산하지 않음(강화·합성 검사 결과를 먼저 고친다) |
| `unknown_stage` | 오류 | `after`에 적은 단계가 없음, 또는 `combat_stage`가 전투 계산에 없음 |
| `requirement_missing` | 경고 | 영구 강화를 선행 조건보다 먼저 사는 계획(형식 오류로 빠진 앞 구매도 계획에 있는 것으로 본다) |
| `duplicate_purchase` | 경고 | 같은 영구 강화를 두 번 삼 |
| `enhance_gap` | 경고 | 같은 강화의 구매가 앞 구매의 단계와 이어지지 않음(건너뜀·겹침) |
| `kill_not_in_stage` | 경고 | `combat_stage`로 이은 전투 단계에 나오지 않는 적의 처치를 셈. 그 적이 앞 구역에서 처음 나온 적이면 전투 단계에 `zone_rule: "up_to"`(앞 구역의 적이 모두 이어질 때)나 `enemies` 목록(일부만 이어질 때)을 안내한다. 적마다 한 줄이다. 플레이어 행동으로만 나오는 적이면 단계에 넣지 않고 재화 흐름 단계의 `acknowledged`에 `{"kill_not_in_stage": {적 id: 이유}}`로 적는다. 이유만 적으면 그 단계의 적을 모두 덮는다 |
| `meta_income_differs`, `meta_order_differs` | 경고 | `meta_config`의 설정과 한 판 수입·영구 강화 구매 순서가 다름 |
| `reward_missing` | 경고 | 처치를 센 적에 `reward`가 없어 0으로 셈 |
| `cut_referenced` | 경고 | 삭제된 적의 처치를 셈(수입에서 뺀다), 삭제된 항목을 삼(계획에서 뺀다), 또는 삭제된 전투 단계에 이음 |
| `unaffordable` | 경고 | 한 판 수입(판 사이 재화는 판 사이 수입)으로 살 수 없음 |
| `target_out_of_range` | 경고 | 구매 시점이나 판 수가 목표를 벗어남 |
| `currency_piles_up` | 경고 | 판 끝에 남는 재화의 비율이 `leftover_max`를 넘음 |
| `gear_before_purchase` | 경고 | 전투 단계의 기준 장비가 구매 계획보다 앞섬. 아이템 구매와, 강화한 장비는 그 단계에 처음 닿는 강화 구매를 본다. 합성으로 얻는 장비는 보지 않는다. 단계 안에서 사면 그 단계부터, `stage_end`면 다음 단계부터 쓴다고 본다. 드랍으로 먼저 얻으면 구매의 `acknowledged`에 `{"gear_before_purchase": {전투 단계 id: 이유}}`로 적는다 |

쓰는 데이터(적·아이템·영구 강화·강화·합성, `combat_stage`를 쓰면 전투 계산, `meta_config`를 쓰면 그 설정)를 함께 넘기지 않았거나 읽지 못하면 그 부분은 계산하지 않고 미확인으로 센다(`INCOMPLETE`). 앞 단계가 미확인이면 구매 시점과 판 수, 남는 재화도 내지 않는다. 오류 없이 계산한 단계가 하나도 없으면(빈 `stages`, 모두 삭제) 미확인 1건이다. 통과가 아니다. 미확인 때문에 시점·판 수·남는 양을 다 내지 못한 재화는 결과의 `unchecked_currencies`에 남는다(메타 성장 시뮬레이터가 연결한 재화에 닿는 미확인인지 이것으로 본다).
