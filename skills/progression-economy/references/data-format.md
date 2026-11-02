# 아이템 데이터 형식

`validate_items.py`가 읽는 형식이다. JSON 하나에 아이템, 스탯 가중치, 드랍 테이블을 함께 두거나, 아이템만 CSV로 둘 수 있다.

## JSON

```json
{
  "stat_labels": { "attack": "공격력", "attack_speed": "공격 속도" },
  "stat_weights": { "attack": 1.0, "attack_speed": 20.0, "max_hp": 0.2 },
  "items": [
    { "id": "iron_sword", "name": "철검", "slot": "weapon", "tier": 2, "rarity": "uncommon",
      "price": 60, "stats": { "attack": 14 },
      "status": "approved", "provenance": { "kind": "assumed" } },
    { "id": "flame_sword", "name": "화염검", "slot": "weapon", "tier": 2, "rarity": "rare",
      "price": 120, "stats": { "attack": 16 }, "unique_effect": true,
      "effect": "적중 시 3초간 화상", "intent": "중반 화상 빌드의 시작점",
      "status": "proposed", "provenance": { "kind": "assumed", "note": "요청 기반 초안" } }
  ],
  "drop_tables": {
    "chest_normal": {
      "entries": [
        { "rarity": "common", "weight": 70 },
        { "rarity": "rare", "weight": 5 }
      ],
      "pity": { "target_rarity": "rare", "guarantee_after": 30 }
    },
    "boss_reward": {
      "entries": [ { "item": "iron_sword", "weight": 1 } ]
    }
  }
}
```

### 아이템 필드

| 필드 | 필수 | 뜻 |
|---|---|---|
| `id` | 예 | 소문자·숫자·밑줄. 표시 이름(한글 등)은 별도 필드로 둔다 |
| `slot` | 예 | 같은 slot끼리만 열위와 티어를 비교한다 |
| `tier` | 예 | 1 이상의 정수 |
| `rarity` | 아니오 | 드랍 테이블의 `item` 항목이 희귀도를 계산할 때 쓴다 |
| `price` | 아니오 | 있으면 열위 판정에 가격을 반영한다 |
| `stats` | 아니오 | `{스탯 이름: 수}`. 없는 스탯은 0으로 본다 |
| `unique_effect` | 아니오 | `true`면 수치로 비교할 수 없는 효과가 있다는 뜻. 열위 판정에서 제외 |
| `name` | 아니오 | 표시 이름(한글 등). 뷰어에 id와 함께 보인다 |
| `effect` | 아니오 | 효과 설명 문장 |
| `intent` | 아니오 | 이 아이템이 왜 있는가(설계 의도) 한 줄. `cut`이면 뺀 이유 |
| `status` | 아니오 | `proposed`(제안) / `approved`(승인) / `cut`(삭제). `cut`은 티어·열위 비교와 출처 게이트에서 빠진다. 드랍 테이블이 `cut` 아이템을 가리키면 경고 |
| `provenance` | 아니오 | `{"kind": "assumed" 또는 "computed" 또는 "measured", "source": "...", "note": "..."}`. 한글 `가정`/`계산`/`측정`도 된다. `computed`·`measured`는 `source` 필수 |

그 밖의 필드는 무시한다. 최상위의 `stat_labels`, `slot_labels`, `rarity_labels`는 뷰어 표시 이름이다(예: `{"attack": "공격력"}`). 지정하지 않으면 키를 그대로 보여 주고, 흔한 부위·희귀도 키(weapon, rare 등)는 한글로 보여 준다.

### 스탯 가중치

`stat_weights`는 티어 비교에 쓰는 "스탯 예산" 계산용이다. 예산 = Σ(스탯 × 가중치), 지정하지 않은 스탯의 가중치는 1이다. 공격 속도 0.1과 공격력 10을 같은 단위로 비교하려면 가중치가 필요하다. 가중치 자체도 설계 가정이므로 문서에서 `[가정]`으로 표시한다.

### 검사 내용

| 코드 | 수준 | 조건 |
|---|---|---|
| `schema`, `duplicate_id`, `unknown_item` | 오류 | 형식 위반, id 중복, 드랍 테이블이 없는 아이템을 참조 |
| `tier_inversion` | 경고 | slot 안에서 상위 티어의 평균 예산이 하위 티어보다 낮음, 또는 어떤 아이템의 예산이 하위 티어 모든 아이템보다 낮음 |
| `dominated` | 경고 | 같은 slot의 다른 아이템이 모든 스탯에서 같거나 높고, 가격이 같거나 싸고(둘 다 가격이 있을 때), 티어가 같거나 낮으며, 하나 이상에서 더 나음 |
| `pity_target_missing` | 경고 | 천장 대상 희귀도가 테이블에 없음 |
| `provenance` | 오류 | 출처 형식 위반, 또는 `computed`·`measured`인데 `source` 없음 |
| `cut_item_referenced` | 경고 | 드랍 테이블이 삭제(`cut`) 상태 아이템을 가리킴 |

열위 판정은 숫자 스탯만 본다. 같은 수치라도 조작감이나 시너지가 다를 수 있으므로, 경고는 "확인할 것"이지 "삭제할 것"이 아니다.

### 천장 기대값

성공 확률 p, `guarantee_after` = N이면 처음 성공까지의 기대 시도 수는 (1 − (1 − p)^N) / p 이다. 천장이 실제로 발동할 확률은 (1 − p)^(N − 1)이다.

## CSV

아이템만 담는다. 스탯은 `stat.` 접두사 열, 출처는 `provenance_kind`·`provenance_source`·`provenance_note` 열로 쓴다. UTF-8(BOM 허용).

```csv
id,name,slot,tier,rarity,price,stat.attack,stat.armor,unique_effect,status,provenance_kind,provenance_source
iron_sword,철검,weapon,2,uncommon,60,14,,,approved,assumed,
chain_mail,사슬 갑옷,armor,2,uncommon,70,,5,,approved,measured,playtest-2026-11-03
lucky_coin,행운의 동전,relic,1,rare,90,,,true,proposed,assumed,
```

## 엔진과 연결

권장 방식은 이 파일을 게임 데이터의 단일 원본으로 두고 엔진이 직접 읽게 하는 것이다. 그러면 내보내기 단계가 사라지고 도구와 게임이 어긋나지 않는다. 아래는 일반적인 방법이며 이 저장소에서 엔진별로 검증한 것은 아니다.

- **Godot**: `FileAccess`로 읽고 `JSON.parse_string()`으로 파싱한다.
- **Unity**: `TextAsset`으로 불러 `JsonUtility` 또는 JSON 라이브러리로 파싱한다. `JsonUtility`는 최상위 배열을 직접 받지 못하므로 위처럼 객체로 감싼 형식이 맞다.
- **Unreal**: DataTable은 CSV·JSON 가져오기를 지원하지만 열 이름이 행 구조체 필드와 같아야 한다. `stat.attack` 같은 열 이름은 변환이 필요할 수 있다.
- **Roblox**: JSON 문자열을 `HttpService:JSONDecode()`로 읽거나, Rojo 같은 도구로 JSON을 ModuleScript로 동기화한다.
