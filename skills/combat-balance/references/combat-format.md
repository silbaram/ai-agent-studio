# 전투 계산 형식

게임 프로젝트의 `data/combat.json` 한 파일에 공식, 스탯 역할, 목표 범위, 단계를 둔다. 검사: `python3 .claude/skills/studio-data/scripts/studio.py check .`(아이템·강화·적 데이터와 함께), 보기: `python3 .claude/skills/studio-data/scripts/studio.py view .`.

```json
{
  "combat": {
    "stats": {
      "player": { "hp": "max_hp", "attack": "attack", "defense": "armor", "attack_rate": "attack_speed", "crit_chance": "crit_chance" },
      "enemy": { "hp": "hp", "attack": "damage", "defense": "armor" }
    },
    "defense": { "form": "ratio", "k": 50 },
    "targets": {
      "normal": { "hits_to_kill": [1, 4], "hits_to_die": [10, null] },
      "boss": { "time_to_kill": [30, 90] }
    },
    "provenance": { "kind": "assumed", "note": "공식과 목표 범위는 기획 판단" }
  },
  "stages": [
    { "id": "zone_1", "name": "구역 1 기준", "level": 1, "zone": 1,
      "player": { "base": { "max_hp": 100, "attack": 4, "attack_speed": 1.0 }, "items": ["rusty_sword"], "upgrades": [] },
      "intent": "구역 1 입장 시 흔한 장비", "status": "proposed", "provenance": { "kind": "assumed" } }
  ]
}
```

## `combat`

| 키 | 필수 | 뜻 |
|---|---|---|
| `stats.player`, `stats.enemy` | 예 | 역할 → 그 게임의 스탯 이름. 역할: `hp`, `attack`(필수), `defense`, `attack_rate`, `crit_chance`, `crit_multiplier` |
| `defense` | 예 | 방어 공식. 아래 표 |
| `targets` | 아니오 | `{등급: {지표: [최소, 최대]}}`. 등급은 `normal` / `elite` / `boss`(적 데이터의 `rank`), 한쪽은 `null` 가능 |
| `provenance` | 아니오 | 공식과 목표의 출처. 없거나 `assumed`면 `--fail-on-assumed`에서 실패한다 |

- `attack_rate`는 초당 공격 횟수다. 없으면 시간 지표(`time_to_kill`, `time_to_die`)를 내지 않는다.
- `crit_chance`는 0~1 비율이다. 5처럼 퍼센트로 적으면 오류(`bad_stat`)다. `crit_multiplier`가 없으면 2로 본다. 치명 역할이 없으면 치명은 없다.
- 플레이어와 적이 같은 이름의 스탯을 써도 되고 달라도 된다.
- 역할이 가리키는 이름이 그 쪽 데이터(플레이어: 단계 `base`·아이템·영구 강화, 적: 적 데이터) 어디에도 없으면, 어느 역할도 쓰지 않는 비슷한 이름이 있을 때 `stat_not_found` 경고다. 비슷한 이름도 없으면 `empty_roles`(값이 있는 데이터가 없는 역할)로만 알린다. 아직 값이 없는 스탯이면 `base`에 0으로 적어 둔다.

### 방어 공식 (`defense.form`)

| form | 받는 피해 | 값 |
|---|---|---|
| `flat` | max(min_damage, 공격 − 방어 × factor) | `factor`(기본 1, 0 이상), `min_damage`(기본 1, 0 이상) |
| `ratio` | 공격 × k / (k + 방어) | `k` > 0. 방어가 k일 때 피해가 절반 |
| `level_ratio` | 공격 × k / (k + 방어), k = a × level + b | `a`, `b`. 단계마다 `level` 필요, 모든 단계에서 k > 0 |
| `percent` | 공격 × (1 − min(방어, cap) / 100) | `cap`(0 초과 100 이하). 방어 값이 곧 감소 % |

치명은 방어 전에 곱한다. 한 번의 기대 피해 = (1 − p) × 피해(공격) + p × 피해(공격 × 배율). 고정값 공식에서는 이 순서가 결과를 바꾼다.

## `stages`

| 키 | 필수 | 뜻 |
|---|---|---|
| `id` | 예 | 소문자·숫자·밑줄 |
| `name`, `intent` | 아니오 | 표시 이름, 이 단계가 무엇을 대표하는지 |
| `level` | `level_ratio`면 예 | 수 |
| `player.base` | 예 | `{스탯: 수}`. 아이템·강화 전 기본값 |
| `player.items`, `player.upgrades` | 아니오 | 아이템·영구 강화 id 배열. 원본의 `stats`를 더한다. 삭제(`cut`) 항목은 경고하고 뺀다. 아이템 칸은 강화한 아이템 `{"item": id, "enhance": 강화 id, "level": 단계}`도 된다: 그 아이템 스탯 × (1 + 1~level 단계 `bonus_pct`의 합). 강화는 강화·합성 데이터(`crafting.json`)의 것이고 그 아이템이 대상이어야 한다 |
| `enemies` | 아니오 | 계산할 적 id 배열. 없으면 `zone` |
| `zone` | 아니오 | 적 데이터의 `zone`(처음 나오는 구역)이 이 값인 적(삭제 제외)을 모두 계산 |
| `zone_rule` | 아니오 | `first_seen`(기본): 위와 같다 / `up_to`: `zone`이 이 값 이하인 적, 곧 이 구역까지 나온 적을 모두 계산(앞 구역의 적이 계속 나오는 게임). `up_to`는 `zone`이 수여야 한다 |
| `status`, `provenance`, `acknowledged` | 아니오 | 공통 필드 ([data-format](../../progression-economy/references/data-format.md#공통-필드)) |

`acknowledged`는 단계에 적는다. `{코드: "이유"}`는 그 단계와 그 단계의 모든 행(`단계.적`)에서 난 그 코드 경고에 적용된다(나중에 생기는 다른 적의 경고도 덮는다). `{코드: {적 id: "이유"}}`는 그 적의 행 경고만 덮는다. 의도한 이탈은 적 단위로 확인한다. 공식·목표·역할 쪽 경고(`target_unchecked`, `stat_not_found`)는 단계 확인으로 끌 수 없다.

## 계산 결과 (`check --json`의 `report`)

| 키 | 뜻 |
|---|---|
| `rows` | 단계 × 적마다 `player_hit`(주는 피해/타), `hits_to_kill`, `time_to_kill`, `enemy_hit`(받는 피해/타), `hits_to_die`, `time_to_die`, `out_of_range`(목표를 벗어난 지표) |
| `stages` | 단계마다 합친 플레이어 스탯 |
| `formula` | 기본값을 채운 공식 |
| `unchecked`, `unchecked_kinds` | 함께 검사하지 못한 데이터(아이템·강화·적·강화·합성), 또는 `nothing`(계산한 행이 없음) |
| `empty_roles` | `{player / enemy: [역할]}` 연결은 했지만 그 이름의 값이 있는 데이터가 없는 역할 |
| `unmapped_stats` | `{player / enemy: [스탯]}` 계산한 단계의 데이터에 있는데 어느 역할에도 연결하지 않아 쓰지 않는 스탯 |

타수는 체력 ÷ 기대 피해를 올림한 값, 시간은 타수 ÷ 초당 공격 횟수다.

## 검사 내용

| 코드 | 수준 | 조건 |
|---|---|---|
| `schema`, `duplicate_id` | 오류 | 형식 위반(역할·공식·목표·단계), 단계 id 중복 |
| `unknown_item`, `unknown_upgrade`, `unknown_enemy`, `unknown_enhance` | 오류 | 원본 데이터에 없는 id(강화는 강화·합성 데이터) |
| `missing_stat` | 오류 | 플레이어(합계)나 적에 체력·공격 스탯이 없음 |
| `bad_stat` | 오류 | 계산에 쓸 수 없는 값: 체력 0 이하, 공격 속도 0 이하, 치명 확률 0~1 밖(2 이상이면 퍼센트로 적은 것으로 보고 안내), 치명 배율 1 미만. 기준 장비에 넣지 않은 영구 강화도 하나씩 단계 기준 장비에 더해 보고, 그 강화가 스탯을 깨면 `upgrades:<강화 id>`의 오류다(메타 성장 시뮬레이터가 사면 더하므로) |
| `negative_defense` | 오류 | 비율 공식에서 방어가 음수 |
| `target_out_of_range` | 경고 | 지표가 등급별 목표 범위를 벗어남 |
| `target_unchecked` | 경고 | 시간 목표(`time_to_kill`, `time_to_die`)를 정했는데 그쪽에 공격 속도 값이 없어 검사하지 못함. 등급·지표마다 한 번. 피해 0으로 타수가 없는 경우는 `zero_damage`가 알린다 |
| `zero_damage` | 경고 | 이 단계 기준 장비로 그 적에게 피해를 줄 수 없음, 또는 그 적이 기준 장비에 피해를 줄 수 없음. 그 행의 타수·시간 목표는 검사하지 않는다 |
| `stat_not_found` | 경고 | 역할의 스탯 이름이 그 쪽 데이터에 없고 비슷한 이름이 있음(오타). 이대로면 그 역할은 값이 없는 것으로 계산된다 |
| `cut_referenced` | 경고 | 기준 장비나 단계의 적 목록에 삭제된 아이템·강화·적이 있음. 계산에서 뺀다 |
| `requirement_missing` | 경고 | 기준 장비의 영구 강화가 선행 조건 강화 없이 들어 있음(살 수 없는 조합) |
| `stage_without_enemies` | 경고 | 계산할 적이 없는 단계 |

아이템·강화·적 데이터(강화한 아이템이 있으면 강화·합성 데이터도)를 함께 넘기지 않았거나, 그 파일을 읽지 못했거나 형식이 틀리면 그 단계는 계산하지 않고 미확인으로 센다(`INCOMPLETE`). 없는 id로 연쇄 보고하지 않는다. 오류 없이 계산한 행이 하나도 없으면(빈 `stages`, 모두 삭제, 적 없는 단계뿐) 미확인 1건이다. 통과가 아니다.
