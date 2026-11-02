# 메타 성장 모델

`simulate_meta.py`의 모델과 설정 형식이다. 이 모델은 일부러 단순하다. 실제 전투를 재현하지 않고, 경제와 성장 곡선의 구조를 보는 데만 쓴다.

## 모델

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

"힘"은 공격력, 체력, 회피를 하나로 뭉친 추상값이다. 실제 게임의 어떤 수치와 일대일로 대응하지 않는다.

## 설정

```json
{
  "seed": 7, "trials": 300, "max_runs": 60, "rooms": 30,
  "difficulty": { "growth": "linear", "base": 10, "rate": 1.2 },
  "player": { "base_power": 12, "power_per_room": 0.8, "skill": 1.5, "skill_spread": 0.8 },
  "survival": { "slope": 0.35, "floor": 0.0, "ceiling": 0.995 },
  "currency": { "per_room": 2, "bonus_rooms": { "10": 15, "20": 30, "30": 60 }, "keep_on_death": 1.0 },
  "purchase_policy": "listed_order",
  "upgrades": [
    { "id": "vitality_1", "cost": 20, "power": 1.5 },
    { "id": "vitality_2", "cost": 70, "power": 2.0, "requires": ["vitality_1"] }
  ],
  "milestones": [ { "id": "boss_1", "clear_room": 10 } ]
}
```

| 키 | 필수 | 비고 |
|---|---|---|
| `seed`, `trials`, `max_runs`, `rooms` | 예 | 정수. 같은 seed면 결과가 같다 |
| `difficulty.base`, `difficulty.rate` | 예 | `growth`는 기본 linear |
| `player.base_power` | 예 | `power_per_room`, `skill`, `skill_spread`는 기본 0 |
| `survival.slope` | 예 | 클수록 힘 차이에 민감. `floor`·`ceiling` 기본 0·1 |
| `currency.per_room` | 예 | `bonus_rooms` 기본 없음, `keep_on_death` 기본 1 |
| `upgrades` | 아니오 | `requires`에 없는 id나 순환이 있으면 오류 |
| `milestones` | 아니오 | `clear_room`은 1 ~ `rooms` |

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

## 한계

- 방마다 독립적인 생존 확률을 쓴다. 체력이 누적으로 깎이는 구조, 회복, 빌드 시너지, 런 내 아이템 선택은 모델에 없다.
- 구매 정책 두 가지는 실제 플레이어 행동의 근사다.
- 입력 파라미터가 `[가정]`인 동안 결과는 그 가정 아래의 계산값이다. 실제 플레이 기록으로 `slope`와 `skill`을 보정하기 전에는 난이도 판정에 쓰지 않는다.
