# 데이터 형식

아이템, 영구 강화, 적을 종류별 파일 하나씩(`data/items.json`, `data/upgrades.json`, `data/enemies.json`)에 둔다. 프로젝트 배치와 종류 판별 규칙은 [studio-data](../../studio-data/SKILL.md#프로젝트-배치)를 따른다. CSV는 파일 이름에 `item` / `upgrade` / `enem`이 들어가야 종류를 알 수 있다.

## 공통 필드

세 종류 모두 아래 필드를 쓸 수 있다.

| 필드 | 필수 | 뜻 |
|---|---|---|
| `id` | 예 | 소문자·숫자·밑줄. 같은 파일 안에서 중복 금지. 표시 이름(한글 등)은 `name`에 |
| `name` | 아니오 | 표시 이름. 뷰어에 id와 함께 보인다 |
| `stats` | 아니오 | `{스탯 이름: 수}` |
| `effect` | 아니오 | 숫자로 표현하기 어려운 효과 설명 |
| `intent` | 아니오 | 왜 있는가(설계 의도) 한 줄. `cut`이면 뺀 이유 |
| `status` | 아니오 | `proposed`(제안) / `approved`(승인) / `cut`(삭제). `cut`은 비교·합계·시뮬레이션·게이트에서 빠진다 |
| `provenance` | 아니오 | `{"kind": "assumed" 또는 "computed" 또는 "measured", "source": "...", "note": "..."}`. 한글 `가정`/`계산`/`측정`도 된다. `computed`·`measured`는 `source` 필수 |
| `acknowledged` | 아니오 | 확인을 마친 경고 `{경고 코드: 확인한 이유}`. 이 항목에 난 그 코드의 경고는 경고 수와 `--strict`에서 빠지고, '확인한 경고'로 이유와 함께 따로 보인다. 오류에는 쓰지 못한다. 예: `{"tier_inversion": "초반 함정 아이템으로 의도"}` |

최상위의 `*_labels`(`stat_labels`, `slot_labels`, `rarity_labels`, `track_labels`, `zone_labels`)는 뷰어 표시 이름이다(예: `{"attack": "공격력"}`). 지정하지 않으면 키를 그대로 보여 주고, 흔한 부위·희귀도·등급 키는 한글로 보여 준다.

## 아이템 (`items`)

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

공통 필드에 더해:

| 필드 | 필수 | 뜻 |
|---|---|---|
| `slot` | 예 | 같은 slot끼리만 열위와 티어를 비교한다 |
| `tier` | 예 | 1 이상의 정수 |
| `rarity` | 아니오 | 드랍 테이블의 `item` 항목이 희귀도를 계산할 때 쓴다 |
| `price` | 아니오 | 있으면 열위 판정에 가격을 반영한다 |
| `unique_effect` | 아니오 | `true`/`false`(불리언). `true`면 수치로 비교할 수 없는 효과가 있다는 뜻. 티어 비교와 열위 판정에서 제외("판정 제외"로 표시). 문자열 `"false"`처럼 불리언이 아니면 형식 오류다 |

`stats`에 없는 스탯은 0으로 본다. 드랍 테이블이 `cut` 아이템을 가리키면 경고한다. 그 밖의 필드는 무시한다.

### 스탯 가중치

`stat_weights`는 티어 비교에 쓰는 "스탯 예산" 계산용이다. 예산 = Σ(스탯 × 가중치), 지정하지 않은 스탯의 가중치는 1이다. 공격 속도 0.1과 공격력 10을 같은 단위로 비교하려면 가중치가 필요하다. 가중치 자체도 설계 가정이므로 문서에서 `[가정]`으로 표시한다. [stat-budget](../../stat-budget/SKILL.md)의 `data/budget.json`이 있으면 그 원가(`budget.items.costs`)가 원본이고 `stat_weights` 대신 쓴다. 비율이 다르면 `weights_ignored` 경고가 난다.

### 검사 내용

| 코드 | 수준 | 조건 |
|---|---|---|
| `schema`, `duplicate_id`, `unknown_item` | 오류 | 형식 위반, id 중복, 드랍 테이블이 없는 아이템을 참조 |
| `tier_inversion` | 경고 | slot 안에서 상위 티어의 평균 예산이 하위 티어보다 낮음, 또는 어떤 아이템의 예산이 하위 티어 모든 아이템보다 낮음(고유 효과 아이템은 제외) |
| `dominated` | 경고 | 같은 slot의 다른 아이템이 모든 스탯에서 같거나 높고, 가격이 같거나 싸고(둘 다 가격이 있을 때), 티어가 같거나 낮으며, 하나 이상에서 더 나음 |
| `pity_target_missing` | 경고 | 천장 대상 희귀도가 테이블에 없음 |
| `provenance` | 오류 | 출처 형식 위반, 또는 `computed`·`measured`인데 `source` 없음 |
| `cut_item_referenced` | 경고 | 드랍 테이블이 삭제(`cut`) 상태 아이템을 가리킴 |
| `item_unchecked` | 경고 | 드랍 테이블이 형식 오류가 있는 아이템을 가리켜 확률을 계산하지 못함. 그 아이템의 오류를 먼저 고친다 |
| `weights_ignored` | 경고 | `budget.json`이 있는데 `stat_weights`가 그 원가와 비율이 달라 무시함(원가를 쓴다) |

열위 판정은 숫자 스탯만 본다. 같은 수치라도 조작감이나 시너지가 다를 수 있으므로, 경고는 "확인할 것"이지 "삭제할 것"이 아니다.

### 천장 기대값

성공 확률 p, `guarantee_after` = N이면 처음 성공까지의 기대 시도 수는 (1 − (1 − p)^N) / p 이다. 천장이 실제로 발동할 확률은 (1 − p)^(N − 1)이다.

## 영구 강화 (`upgrades`)

```json
{
  "track_labels": { "weapon": "무기" },
  "upgrades": [
    { "id": "weapon_1", "name": "무기 숙련 I", "track": "weapon", "level": 1,
      "cost": 40, "power": 2.0, "stats": { "attack": 2 },
      "status": "approved", "provenance": { "kind": "assumed" } },
    { "id": "weapon_2", "name": "무기 숙련 II", "track": "weapon", "level": 2,
      "cost": 110, "power": 2.5, "requires": ["weapon_1"], "stats": { "attack": 3 },
      "status": "approved", "provenance": { "kind": "assumed" } }
  ]
}
```

| 필드 | 필수 | 뜻 |
|---|---|---|
| `cost` | 예 | 0 이상의 수. 메타 재화 가격 |
| `power` | 아니오 | 메타 성장 시뮬레이터의 추상 힘 증가량. 없으면 `power_missing` 경고, 시뮬레이터는 실행 거부 |
| `requires` | 아니오 | 선행 강화 id 배열. CSV에서는 `;`로 구분 |
| `track` | 아니오 | 묶음(뷰어에서 표를 나누는 기준) |
| `level` | 아니오 | 트랙 안 단계(정수). 뷰어 정렬에 쓴다 |
| `stats` | 아니오 | 게임에서 실제로 주는 효과(예: `max_hp: 10`). `power`와 별개다 |

| 코드 | 수준 | 조건 |
|---|---|---|
| `unknown_requirement` | 오류 | 없는 강화를 선행 조건으로 가리킴 |
| `requirement_cycle` | 오류 | 선행 조건이 순환함 |
| `requires_cut` | 오류 | 활성 강화가 삭제(`cut`)된 강화를 선행 조건으로 가리켜 살 수 없음 |
| `cost_inversion` | 경고 | 선행 조건보다 싸게 책정됨 |
| `power_missing` | 경고 | 활성 강화에 `power`가 없음 |
| `requirement_unchecked` | 경고 | 선행 조건 강화에 형식 오류가 있어 확인하지 못함('없는 선행 조건'으로 잘못 보고하지 않는다). 그 강화의 오류를 먼저 고친다 |

보고서에는 트랙별·전체 총비용과 power(삭제 제외), 선행 사슬 깊이, 효율(power ÷ cost)이 들어간다.

## 적 (`enemies`)

```json
{
  "threat_weights": { "hp": 0.1, "damage": 1.0, "speed": 2.0 },
  "zone_labels": { "1": "버려진 지하묘지" },
  "enemies": [
    { "id": "slime", "name": "슬라임", "rank": "normal", "zone": 1,
      "stats": { "hp": 30, "damage": 4, "speed": 1.0 }, "reward": 2, "drop_table": "chest_normal",
      "status": "approved", "provenance": { "kind": "assumed" } }
  ]
}
```

| 필드 | 필수 | 뜻 |
|---|---|---|
| `rank` | 예 | `normal`(일반) / `elite`(정예) / `boss`(보스) |
| `zone` | 예 | 처음 나오는 구역(1 이상의 정수). 뷰어에서 표를 나누는 기준. 전투 계산의 단계가 `zone`으로 적을 고를 때 기본은 이 값이 같은 적만이다(앞 구역의 적이 계속 나오면 그 단계에 `zone_rule: "up_to"`) |
| `reward` | 아니오 | 처치 보상(0 이상). 어느 재화인지는 [economy-flow](../../economy-flow/SKILL.md)의 `economy.kill_reward`가 정한다 |
| `drop_table` | 아니오 | 아이템 데이터의 `drop_tables` id |
| `growth`, `level` | 아니오 | 레벨로 자라는 적의 레벨당 상승치(`{스탯: 수}`, `stats`에 있는 스탯만)와 `stats`의 레벨(기본 1). `level_of` 행이 쓴다 |
| `level_of` | 아니오 | 같은 적의 다른 레벨. 기본 적 id와 `level`만 적는다(`{"id": "slime_l3", "level_of": "slime", "level": 3}`). 스탯은 기본 적의 `stats` + `growth` × (레벨 차이)로 계산하고, 적지 않은 칸(이름·등급·구역·보상·드랍·상태·출처)은 기본 적에서 받는다. 구역처럼 다른 칸은 그 행에 적는다. `stats`는 적지 않는다. 다른 데이터(전투 계산·레벨 구성·재화 흐름)는 이 행의 id로 가리킨다 |
| `template` | 아니오 | `true`면 틀로만 쓰는 기본 적이다. 그 레벨로는 게임에 나오지 않고 `level_of` 행의 기본으로만 쓴다. 적 목록·위협도·구역별 평균·다른 데이터의 참조에 들지 않는다(다른 데이터가 틀 id를 가리키면 `unknown_enemy` 오류이고, 그 틀의 레벨 행을 안내한다). `growth`가 필요하고, `rank`·`zone`은 틀이나 각 `level_of` 행에 적는다. 기본 적이 그 레벨로 실제로 나오면 `template` 없이 둔다 |

위협도 = Σ(스탯 × `threat_weights`), 지정하지 않은 스탯의 가중치는 1이다. 가중치는 설계 가정이며 실제 난이도 판정이 아니다. `data/budget.json`이 있으면 그 원가(`budget.enemies.costs`)를 `threat_weights` 대신 쓴다.

| 코드 | 수준 | 조건 |
|---|---|---|
| `unknown_drop_table` | 오류 | 아이템 데이터에 없는 드랍 테이블을 가리킴 (`check`나 뷰어가 아이템 파일을 함께 읽은 경우) |
| `unknown_enemy` | 오류 | `level_of`가 기본 적(`level_of`가 없는 행)을 가리키지 않음 |
| `schema` | 오류 | 형식 위반. `growth`에 `stats`에 없는 스탯이 있음(오타). `template`이 `true`/`false`가 아님, 틀에 `growth`가 없음, `level_of` 행에 `template: true`. 기본 적(틀 포함)에 적힌 등급·구역·보상·드랍·레벨·스탯이 틀리면 기본 적에서 한 번만 알린다. `level_of` 행: `stats`를 적음, `level`이 1 이상의 정수가 아님, 기본 적에 `growth`가 없음. 기본 적의 형식 오류 때문에 계산하지 못한 행은 따로 알리지 않는다 |
| `level_duplicate` | 경고 | 틀이 아닌 기본 적과 레벨이 같은 `level_of` 행(같은 적을 두 번 센다). 다른 데이터가 기본 적을 가리키게 하고 그 행을 지우거나, 기본 적을 틀로 둔다 |
| `zone_inversion` | 경고 | 같은 등급의 평균 위협도가 다음 구역에서 줄어듦 |
| `rank_inversion` | 경고 | 같은 구역에서 상위 등급 평균 위협도가 하위 등급보다 높지 않음 |
| `weights_ignored` | 경고 | `budget.json`이 있는데 `threat_weights`가 그 원가와 비율이 달라 무시함(원가를 쓴다) |

`level_of` 행을 하나라도 계산하지 못하면 다른 데이터(전투 계산·레벨 구성·재화 흐름 등)의 적 참조는 없는 적으로 보고하지 않고 미확인으로 둔다(`INCOMPLETE`). 적 파일의 오류를 먼저 고친다.

아이템 파일 없이 적 파일만 검사하거나 아이템 파일을 읽지 못하면 드랍 테이블 참조는 `drop_table_not_checked`에 "미확인"으로 남고, 이유(아이템 데이터 없음 / 아이템 파일 읽기 실패)가 함께 표시된다. 미확인이 있으면 `check`의 최종 판정은 PASS가 아니라 INCOMPLETE다.

## 효과가 규칙인 콘텐츠

카드처럼 효과가 규칙이라 스탯으로 비교할 수 없는 콘텐츠는 아이템(`items`) 형식에 넣어 목록·상태·출처·뷰어를 쓴다. 비교는 시뮬레이터로 한다([판정 규칙](../SKILL.md#판정-규칙)).

| 칸 | 넣는 값 |
|---|---|
| `slot` | 계열과 사용 비용(에너지 등)을 함께 쓴다(예: `charge-1`). 열위 판정은 `price`만 보고 `cost` 같은 게임 고유 칸은 무시하므로, 비용이 다른 카드를 같은 slot에 두면 `dominated`가 잘못 난다 |
| `tier` | 필수 칸이라 티어가 없으면 모두 `1`. 그러면 `tier_inversion`은 나지 않는다 |
| `unique_effect` | 키워드·연계처럼 효과가 규칙인 카드는 `true`(열위 판정에서 빠진다) |
| `stats` | 숫자로 적을 수 있는 효과(피해, 방어)만 |

판단에 쓰지 않는 가중치(`stat_weights`, `threat_weights`)는 만들지 않는다(없으면 1). 적도 같다. 그래도 가중치 1로 더한 위협도에서 `zone_inversion`·`rank_inversion`이, 같은 slot 카드에서 `dominated`가 날 수 있다. 시뮬레이터 결과로 실제로 약한지 보고, 아니면 사용자와 확인한 뒤 `acknowledged`에 "규칙 콘텐츠, 시뮬레이터로 비교"처럼 까닭을 적는다([확인한 경고](../SKILL.md#작업-순서)).

## CSV

스탯은 `stat.` 접두사 열, 적의 레벨당 상승치는 `growth.` 접두사 열(`template` 열은 `true`/`false`), 출처는 `provenance_kind`·`provenance_source`·`provenance_note` 열로 쓴다. 강화의 `requires`는 `;`로 구분한다. UTF-8(BOM 허용). 드랍 테이블, 가중치, 표시 이름은 CSV로 담을 수 없으므로 필요하면 JSON을 쓴다.

아이템 예:

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
