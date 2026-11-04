# 메타 성장 모델

`studio.py simulate`의 모델과 설정 형식이다. 모델은 두 가지다.

- **추상 모델**(기본, `model` 없음 또는 `"abstract"`): 방마다 추상 "힘"과 난이도 곡선으로 생존을 정한다. 전투 데이터가 아직 없을 때 경제·성장 곡선의 구조를 본다.
- **전투 계산 모델**(`"model": "combat"`): [combat-balance](../../combat-balance/SKILL.md)의 단계를 차례로 지나며, 그 판까지 산 영구 강화의 스탯과 [run-growth](../../run-growth/SKILL.md)의 레벨업 선택을 기준 장비에 더해 처치·버팀으로 생존을 정한다. 전투 데이터가 있으면 이쪽을 쓴다. 아래 [전투 계산 모델](#전투-계산-모델) 절.

## 추상 모델

한 **시행(trial)**은 플레이어 한 명의 경력이다. 시행마다 최대 `max_runs`번 런을 한다.

1. 런 시작 시 힘 = `base_power` + 산 강화의 `power` 합.
2. 방 r(1부터)을 순서대로 지난다. 난이도는
   - linear: `base + rate × (r − 1)`
   - exponential: `base × (1 + rate)^(r − 1)`
3. 방을 통과할 확률은 `clamp(sigmoid(slope × (힘 − 난이도) + skill), floor, ceiling)`.
4. 통과하면 재화 `per_room`과 해당 방의 `bonus_rooms` 보상을 얻고, 힘이 `power_per_room`만큼 오른다(런 내 성장).
5. 실패하면 런이 끝나고, 그 런에서 얻은 재화의 `keep_on_death` 비율만 남는다.
6. 런이 끝나면 구매 정책에 따라 영구 강화를 산다.
   - `listed_order`: 목록 순서대로 산다. 다음 강화를 살 수 없으면 그 뒤 강화도 사지 않고 저축한다.
   - `cheapest_first`: 선행 조건을 만족한 것 중 가장 싼 것부터 산다.
7. 시행마다 `skill`은 평균 `skill`, 표준편차 `skill_spread`의 정규분포에서 한 번 뽑는다. 플레이어 간 실력 차이를 흉내 낸다.

설정 파일을 고치지 않고 구매 정책만 바꾸려면 `--policy cheapest_first`, 두 정책을 한 번에 돌려 나란히 보려면 `--compare-policies`를 쓴다. 같은 seed·trials·max_runs로 돌고, 결과에 설정 파일 해시가 그대로 남는다.

"힘"은 공격력, 체력, 회피를 하나로 뭉친 추상값이다. 실제 게임의 어떤 수치와 일대일로 대응하지 않는다.

## 방이 아닌 게임에 맞추기

모델 단위는 방(room)이지만 실제 방일 필요는 없다. 웨이브·시간 생존형(서바이버라이크)은 "방"을 **같은 길이의 시간 구간이나 웨이브 하나**로 본다.

- 20분 판을 1분 단위로 보면 `rooms`는 20, 10분에 나오는 보스는 `milestones`의 `clear_room` 10, 그 보상은 `bonus_rooms`의 `"10"`이다.
- `power_per_room`은 구간 하나에서 레벨업·장비로 얻는 힘의 평균, `per_room`은 구간당 메타 재화다.
- 난이도가 시간에 따라 급해지면 `growth: exponential`을 쓴다.
- 대응 규칙("1방 = 1분" 등) 자체가 가정이다. 기획 문서에 `[가정]`으로 적고, 결과를 인용할 때 함께 밝힌다.

## 설정

```json
{
  "seed": 7, "trials": 300, "max_runs": 60, "rooms": 30,
  "difficulty": { "growth": "linear", "base": 10, "rate": 1.2 },
  "player": { "base_power": 12, "power_per_room": 0.8, "skill": 1.5, "skill_spread": 0.8 },
  "survival": { "slope": 0.35, "floor": 0.0, "ceiling": 0.995 },
  "currency": { "per_room": 2, "bonus_rooms": { "10": 15, "20": 30, "30": 60 }, "keep_on_death": 1.0 },
  "purchase_policy": "listed_order",
  "upgrades_file": "upgrades.json",
  "milestones": [ { "id": "boss_1", "clear_room": 10 } ]
}
```

모델에 없는 키는 설정 오류다(오타 안내, 종료 코드 2). `_`로 시작하는 키(`_note`)는 메모로 둔다.

| 키 | 필수 | 비고 |
|---|---|---|
| `seed`, `trials`, `max_runs`, `rooms` | 예 | 정수. 같은 seed면 결과가 같다 |
| `difficulty.base`, `difficulty.rate` | 예 | `growth`는 기본 linear |
| `player.base_power` | 예 | `power_per_room`, `skill`, `skill_spread`는 기본 0 |
| `survival.slope` | 예 | 클수록 힘 차이에 민감. `floor`·`ceiling` 기본 0·1 |
| `currency.per_room` | 예 | `bonus_rooms` 기본 없음, `keep_on_death` 기본 1 |
| `upgrades_file` | 아니오 | 영구 강화 원본 파일 경로(설정 파일 폴더 기준). **권장.** `studio.py check` 기준으로 강화 데이터에 오류가 있거나 활성 강화에 `power`가 없으면 실행을 거부한다. `cut` 강화는 빠지고, 목록 순서는 파일 순서다. 결과에 파일 경로와 해시가 남는다 |
| `upgrades` | 아니오 | 빠른 실험용 인라인 목록(`id`, `cost`, `power`, `requires`, 전투 계산 모델이면 `stats`). `upgrades_file`과 함께 쓸 수 없다. `requires`에 없는 id나 순환이 있으면 오류 |
| `purchase_policy` | 아니오 | `listed_order`(기본), `cheapest_first`, `economy`(재화 흐름의 구매 계획 순서. 아래 `economy` 연결이 필요) |
| `economy` | 아니오 | `{file: 재화 흐름 파일, currency: 판 사이 재화 id}`. 구매 정책 `economy`가 그 파일의 구매 계획에서 이 재화로 사는 영구 강화 순서를 쓴다. 전투 계산 모델은 단계별 수입도 여기서 읽는다(추상 모델은 순서만). 재화 흐름에 오류가 있거나 이 재화의 수입·구매가 미확인이면 실행을 거부한다. 다른 재화만 미확인(예: 골드로 사는 합성의 데이터가 없음)이면 그대로 쓴다 |
| `milestones` | 아니오 | `clear_room`은 1 ~ `rooms` |
| `provenance` | 아니오 | 설정 수치(생존 곡선 등)의 출처. 데이터 파일과 같은 형식이다. 보정값이면 `{"kind": "computed", "source": "reports/calibrate.json"}`로 적고, 결과와 주의 문구에 그 출처가 나온다. 없거나 `assumed`거나 형식이 틀리면 `check --fail-on-assumed`에서 실패한다 |

## 출력

| 키 | 뜻 |
|---|---|
| `survival_at_base_power` | 영구 강화 없이 런 내 성장만 있을 때 방별 통과 확률. 난이도 곡선이 어디서 가팔라지는지 본다 |
| `milestones`, `upgrades` | 처음 도달·구매한 런 번호의 분포. `reached_fraction`과 p10 / 중앙값 / p90. 백분위가 미도달 구간에 걸리면 `null` |
| `all_upgrades_bought` | 모든 강화를 산 런의 분포 |
| `longest_stall_runs` | 아직 얻을 것이 남았는데 강화 구매도 최고 기록 갱신도 없는 연속 런의 최대 길이 |
| `curve` | 런 번호별 도달 방, 보유 재화, 메타 힘의 중앙값. `--csv`로 저장 가능 |
| `config_sha256` | 설정 파일 해시. 결과를 인용할 때 어떤 설정이었는지 확인용 |

## 읽는 법

- **정체가 길다**: 강화 가격 간격이 재화 획득보다 빠르게 벌어지거나, 난이도 곡선의 벽을 강화로 넘기 어렵다. `survival_at_base_power`에서 확률이 급락하는 방을 함께 본다.
- **너무 빨리 끝난다**: 모든 강화와 클리어가 몇 런 만에 끝나면 메타 성장이 동기 부여 역할을 하기 전에 소진된다.
- **p10과 p90이 크게 벌어진다**: 실력 차이(`skill_spread`)에 결과가 민감하다. 의도라면 괜찮고, 아니라면 보정 장치(실패 시 재화 보존 등)를 검토한다.
- **도달률이 100% 미만**: `max_runs` 안에 못 가는 플레이어가 있다. 그 비율 자체가 결과다.

## 전투 계산 모델

```json
{
  "model": "combat", "seed": 7, "trials": 200, "max_runs": 40,
  "combat_file": "combat.json",
  "growth_file": "growth.json", "build": "balanced",
  "survival": { "slope": 3.0, "even_margin": { "normal": 1.0, "elite": 0.4, "boss": 0.12 }, "floor": 0.0, "ceiling": 0.99 },
  "player": { "skill": 0.5, "skill_spread": 0.5 },
  "currency": { "keep_on_death": 1.0 },
  "economy": { "file": "economy.json", "currency": "soul" },
  "purchase_policy": "economy",
  "upgrades_file": "upgrades.json",
  "stat_effects": { "soul_gain": { "income_pct": 0.1 } },
  "milestones": [ { "id": "first_clear", "clear_stage": "zone_3" } ]
}
```

판은 방 대신 전투 계산의 단계를 순서대로 지난다. 단계마다:

1. 플레이어 = 그 단계의 기준 장비(`base`·`items`, 강화한 아이템 포함) + **그 판까지 산 영구 강화의 `stats`** + **그 판의 레벨업 선택**(빌드 정책으로 판마다 새로 뽑음). 전투 계산의 단계에 적은 `player.upgrades`는 쓰지 않는다(그 대신 실제로 산 강화를 더한다).
2. 적마다 처치·버팀을 계산하고, **여유** = 버티는 시간 ÷ 처치 시간을 낸다. 어느 쪽이든 공격 속도가 없으면 버티는 타수 ÷ 처치 타수다(양쪽 공격 빈도가 같다고 보는 셈이라, 플레이어 공격 속도만 있는 게임은 그만큼 어긋난다). 피해를 줄 수 없는 적은 0, 피해를 주지 않는 적은 무한대.
3. 적마다 **기준 대비 여유** = 여유 ÷ 그 적 등급의 `even_margin`. 가장 작은 적이 그 단계를 정한다(출력의 `decided_by`).
4. 넘길 확률 = `clamp(sigmoid(slope × ln(기준 대비 여유) + skill), floor, ceiling)`. 여유가 기준과 같으면 평균 실력(skill 0)의 플레이어가 절반의 확률로 넘긴다.
5. 넘기면 그 단계의 재화를 얻는다(`stat_effects`의 `income_pct`가 있으면 그만큼 더). 실패하면 판이 끝나고 그 판 재화의 `keep_on_death`만 남는다. 판이 끝나면 구매 정책대로 영구 강화를 산다.

| 키 | 필수 | 비고 |
|---|---|---|
| `model` | 예 | `"combat"`. `rooms`·`difficulty`는 쓰지 않는다. 모델에 없는 키는 설정 오류다(오타 안내). `_`로 시작하는 키(`_note`)는 메모로 둔다 |
| `combat_file` | 예 | 전투 계산 파일(설정 파일 폴더 기준). 같은 폴더의 아이템·적·강화·합성 데이터와 함께 `check`와 같은 규칙으로 검사하고, 오류·미확인이 있으면 실행을 거부한다 |
| `stages` | 아니오 | 판에서 지나는 전투 단계 id 순서. 없으면 전투 계산의 활성 단계 전부(파일 순서) |
| `growth_file`, `build` | 아니오 | 판 안 성장 파일과 빌드 id. 둘을 함께 쓴다. 레벨은 그 빌드의 단계별 레벨(`level_at`)이고, 레벨이 없는 단계는 앞 단계의 레벨을 잇는다 |
| `survival.slope` | 예 | 여유 차이에 얼마나 민감한가. `ln(여유)`에 곱한다 |
| `survival.even_margin` | 아니오 | 평균 실력이 절반의 확률로 넘기는 여유(기본 1). 수 하나(모든 등급) 또는 등급별 `{normal, elite, boss}`(없는 등급은 1). 기대값 계산에는 회피가 없으므로 피하며 싸우는 액션 게임은 1보다 훨씬 작고, 보스는 설계상(오래 싸우며 몇 대만 맞는다) 특히 작다 |
| `player.skill`, `player.skill_spread` | 아니오 | 추상 모델과 같다(기본 0) |
| `currency.per_stage` | `economy`가 없으면 예 | `{전투 단계 id: 판 사이 재화}`. 없으면 `economy` 연결의 수입을 쓴다: 재화 흐름 단계의 그 재화 수입을 그 단계의 `combat_stage`로 모은다(`combat_stage`가 없는 단계에 수입이 있으면 오류) |
| `upgrades_file` | 예(권장) | 영구 강화의 `stats`를 전투 계산에 더한다. `power`는 쓰지 않는다 |
| `stat_effects` | 아니오 | 전투 역할에 연결되지 않은 강화 스탯을 잇는 가정 `{스탯: {income_pct, levels}}`. 스탯 이름은 영구 강화가 가진 스탯이어야 하고(오타 안내), 전투 역할에 연결된 스탯은 이미 생존에 들어가므로 쓰지 않는다(두 번 계산되므로 오류). `income_pct`: 스탯 1당 판 사이 재화 수입 +비율(0.1 = +10%), `levels`: 스탯 1당 판 안 레벨업 +횟수(모든 단계, 합을 내림. `growth_file`이 필요). 수집·숙성·경험치처럼 전투 밖에서 돕는 강화에 쓴다 |
| `milestones` | 아니오 | `clear_stage`: 그 단계까지 넘기면 도달 |

추가 출력:

| 키 | 뜻 |
|---|---|
| `survival_by_stage` | 단계마다 세 경우의 그 단계를 정한 적과 여유·넘길 확률(평균 실력): 영구 강화·판 안 성장 없이(`decided_by`·`rank`, `margin_none`, `p_none`), 첫 판의 새 플레이어 = 영구 강화 없이 판 안 성장 평균(`decided_by_growth`, `margin_growth`, `p_growth`. 성장 설정이 없으면 앞과 같다), 계획한 강화를 모두 사고 판 안 성장 평균(`decided_by_all`, `margin_all`, `p_all`). 어디가 벽인지, 강화로 넘을 수 있는 벽인지 본다. 피해를 받지 않는 적의 여유는 `null` |
| `stage_income` | 단계마다 넘기면 얻는 판 사이 재화 |
| `upgrades_without_combat_effect` | 스탯이 전투 역할에도 `stat_effects`에도 연결되지 않아 이 모델에서 비용만 드는 강화(편의·슬롯 등) |
| `inputs` | 함께 읽어 계산에 쓴 파일(전투 계산·판 안 성장·재화 흐름·아이템·영구 강화·적·강화·합성)의 경로와 SHA-256. 결과를 인용할 때 어느 데이터에서 나왔는지 확인한다 |
| `curve` | 추상 모델의 `median_meta_power` 대신 `median_upgrades_owned`(산 강화 수) |

구매 정책 `economy`면 재화 흐름의 구매 계획에 없는 강화는 사지 않고, `all_upgrades_bought`는 계획한 강화를 모두 산 판이다.

`check`의 전투 계산 검사가 모든 활성 영구 강화를 단계 기준 장비에 하나씩 더해 보므로, 혼자서 스탯을 깨는 강화(치명 확률 2 등)는 계획에 없어도 오류다. 구매 정책으로 살 수 있는 강화를 모두 산 상태의 스탯이 계산에 쓸 수 없는 값이면 실행 전에 거부한다(비싸서 닿지 않는 강화도). 판 안 성장까지 더한 조합은 판마다 뽑으므로, 쓸 수 없는 판이 나오면 그 단계·영구 강화·레벨업 선택을 적고 멈춘다.

### 생존 곡선의 처음 값

`slope`·`even_margin`·`skill`은 처음에는 근거가 없는 가정이다. 예시 값을 그대로 옮기지 말고 이렇게 시작한다.

1. `even_margin`을 비우고(기본 1) 한 번 돌린다. `survival_by_stage`에서 단계마다 그 단계를 정한 적(`decided_by_growth`와 그 적의 등급)과 첫 판의 새 플레이어의 여유(`margin_growth`: 영구 강화 없이 판 안 성장 평균)를 본다. 판 안 성장을 설정하지 않았으면 `margin_none`과 같다. `margin_none`(성장도 없음)으로 맞추면 실제 첫 판보다 어려운 상태에 맞춘 것이 된다.
2. 등급마다 "새 플레이어가 첫 판에 절반쯤 넘기길 바라는" 단계의 `margin_growth`를 그 등급의 `even_margin`으로 둔다(예: 첫 보스 단계의 보스 여유). 바라는 확률이 절반이 아니면 `skill`로 옮긴다(+1이면 약 73%). 정예나 보스가 단계를 정하는데 그 등급의 기준을 비워 두면 `simulate`가 참고 줄을 낸다. 여유는 버티는 타수 ÷ 처치 타수라 그 등급은 설계대로여도 작게 나오므로, 기준을 잡기 전의 낮은 통과율로 적을 고치지 않는다.
3. 계획한 강화를 모두 산 뒤(`p_all`) 그 단계를 얼마나 넘기길 바라는지로 `slope`를 정한다. 클수록 강화의 효과가 크게 보인다.
4. 정한 값과 이유를 설정의 `_note`나 기획 문서에 `[가정]`으로 적는다. 플레이 기록이 생기면 `calibrate`로 보정한다([playtest-verdict](../../playtest-verdict/references/calibration.md), 로드맵 B5c).

### 재화 흐름과 같은 원본 쓰기

[economy-flow](../../economy-flow/SKILL.md)의 판 사이 재화에 `meta_config`로 이 설정을 이어 두면, 재화 흐름 검사가 두 정의를 맞춰 본다. 이 설정이 `economy` 연결로 수입을 읽고 구매 정책이 `economy`이면 수입과 순서가 같은 원본이라 비교할 것이 없다. 이렇게 두면 시뮬레이터의 판 수와 재화 흐름의 판 수(매 판 끝까지 깬 최소값) 차이는 지는 판 때문이다.

## 한계

- 방(단계)마다 독립적인 생존 확률을 쓴다. 체력이 누적으로 깎이는 구조, 회복은 모델에 없다. 추상 모델에는 빌드 시너지와 런 내 아이템 선택도 없다.
- 전투 계산 모델의 생존은 단계에서 기준 대비 가장 어려운 적과의 1대1 기대값 여유로 정한다. 적 무리, 회피, 조작은 `even_margin`·`slope`·`skill`이라는 가정에 뭉쳐 있다.
- 전투 밖 강화의 효과는 `stat_effects`로 적은 가정(수입 비율, 레벨업 횟수)만큼만 계산한다. 적지 않으면 비용만 든다.
- 구매 정책 두 가지는 실제 플레이어 행동의 근사다.
- 입력 파라미터가 `[가정]`인 동안 결과는 그 가정 아래의 계산값이다. 실제 플레이 기록으로 `slope`·`even_margin`·`skill`을 보정하기 전에는 난이도 판정에 쓰지 않는다.
