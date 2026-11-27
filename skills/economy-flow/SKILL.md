---
name: economy-flow
description: "Models currency income per stage (kills times enemy rewards, expected sell value of drops, other income) and an ordered purchase plan whose prices come from item prices, expected enhancement costs, crafting costs, permanent upgrade costs, or fixed amounts, then computes when each purchase becomes affordable within a run, which run a carried meta currency affords it, and how much currency is left over. Use when tuning rewards, prices, shop or upgrade pacing, or checking for currency piling up or running short, in any genre and engine."
license: MIT
---

# 재화 흐름

재화가 어디서 얼마나 들어오고(수입), 무엇에 언제 쓰이며(지출), 판이 끝날 때 얼마나 남는지를 계산한다. 목적은 "보상을 올리면 상점 아이템을 몇 초 일찍 사나", "영구 강화 2단계는 몇 번째 판에 사나", "골드가 남아도나"를 감 대신 계산으로 답하는 것이다.

계산은 **기대값**이다(넣지 않는 것은 [한계](#한계)). [밸런스 공통 원칙](../studio-data/SKILL.md#밸런스-공통-원칙)을 따른다.

## 도구

명령은 공용 스킬 [studio-data](../studio-data/SKILL.md)의 `studio.py`로 하고, Claude Code 설치 기준으로 적었다(다른 설치는 [실행](../studio-data/SKILL.md#실행)).

| 명령 | 하는 일 |
|---|---|
| `python3 .claude/skills/studio-data/scripts/studio.py check .` | 형식·참조 검사, 단계별·누적 수입, 구매 시점(판 안) 또는 판 수(판 사이 재화), 판 끝에 남는 재화 |
| `… check . --table economy` | 단계 수입 표와 구매 계획 표(마크다운) |
| `… view .` | 재화 흐름 탭: 단계별 수입(출처별), 구매 계획(목표 이탈·살 수 없음 강조), 남는 재화 |

데이터는 `data/economy.json` 한 파일이다. 형식은 [references/economy-format.md](references/economy-format.md). 적 보상·드랍 테이블·아이템 가격은 [progression-economy](../progression-economy/SKILL.md)의 원본에서, 강화·합성 비용은 [crafting-balance](../crafting-balance/SKILL.md)에서 그대로 가져온다. 여러 파일에 적는 사실의 원본은 [같은 사실의 원본](../studio-data/references/data-rules.md#같은-사실의-원본).

## 절차

### 1. 재화를 정한다

`economy.currencies`에 재화를 적는다. 판이 끝나면 사라지는 재화(골드 등)와 판 사이에 남는 재화(`carry: true`, 메타 재화)를 구분한다. 처치 보상(`kill_reward`, 적 데이터 `reward`의 재화는 여기서 정한다), 드랍을 팔 때의 재화와 비율(`sell`), 가격 출처별 재화(`prices`: 아이템·강화·합성·영구 강화)를 정한다.

메타 성장 시뮬레이터(`simulate`)의 설정 파일이 있으면 그 판 사이 재화에 `meta_config`로 잇거나, 시뮬레이터가 이 파일을 원본으로 읽게 한다([메타 성장 설정과 맞춰 보기](references/economy-format.md#메타-성장-설정과-맞춰-보기-meta_config)).

### 2. 단계를 적는다

단계는 구역·레벨·웨이브·시간 구간 중 그 게임이 한 판을 나누는 단위다. 전투 계산의 단계와 같은 구간이면 `combat_stage`에 그 단계 id를 적어 잇는다(처치를 센 적이 그 전투 단계에 나오는지 확인한다). 단계마다:

- `duration`: 길이(`time_unit`, 기본 초). 방 단위 게임이면 방 수로 써도 된다.
- `kills`: 적 id별 기대 처치 수. 적 데이터의 `reward`를 곱한다.
- `drops`: 드랍 테이블별 기대 드랍 횟수. 아이템 가격 × 판매 비율의 기대값을 곱한다.
- `income`: 그 밖의 수입(상자, 퀘스트, 판 사이 재화 지급 등) `{재화: 양}`.

처치 수와 드랍 횟수는 에이전트가 정하면 가정이다. 사용자에게 "한 판을 평범하게 깨면 이 정도"가 맞는지 확인한다. 레벨을 조우로 적었으면([level-design](../level-design/SKILL.md)) 조우로 센 처치 수와 맞춰 본다(`kills_differ`). 플레이 기록이 있으면 그 값으로 바꾸고 출처를 남긴다([playtest-verdict](../playtest-verdict/SKILL.md)).

### 3. 구매 계획을 적는다

플레이어가 보통 사는 순서대로 `purchases`에 적는다. 가격은 직접 적거나 아이템·강화·합성·영구 강화의 원본에서 가져온다. 의도한 시점은 `target`에, 상점이나 제작대가 늦게 열리면 그 단계나 시각을 `after`에 적는다. 키는 [형식의 purchases](references/economy-format.md#purchases-사는-순서대로)에 있다.

### 4. 계산하고 읽는다

```bash
python3 .claude/skills/studio-data/scripts/studio.py check . --table economy
```

- `requirement_missing`·`duplicate_purchase`·`enhance_gap`: 살 수 없거나 겹치는 계획이다. 순서와 단계를 고친다.
- 시점이 "앞 구매를 계산하지 못해 미확인"이면 앞의 오류·미확인 구매부터 고친다.
- `unaffordable`·`target_out_of_range`: 구매 순서·가격·수입·목표 중 무엇을 고칠지 사용자와 정한다.
- `currency_piles_up`: 쓸 곳이 모자라거나 수입이 많다.
- 판 사이 재화의 판 수를 메타 성장 시뮬레이터의 판 수와 견주기 전에 [메타 성장 설정과 맞춰 보기](references/economy-format.md#메타-성장-설정과-맞춰-보기-meta_config)를 읽는다.

구매 시점과 판 수의 계산은 [형식의 purchases](references/economy-format.md#purchases-사는-순서대로), 코드마다의 조건은 [검사 내용](references/economy-format.md#검사-내용)에 있다.

## 보고

- 첫 줄은 지금 위치, 정할 것도 [이 모양](../studio-data/references/telling-the-user.md)대로
- 단계별 수입과 출처(처치·드랍 판매·기타), 한 판 총수입
- 구매별 시점이나 판 수, 목표 이탈과 살 수 없는 구매
- 판 끝에 남는 재화와 그 비율
- 오류·경고 수, `INCOMPLETE` 여부
- 사용자가 정해야 할 것: 처치 수·드랍 횟수 가정, 구매 순서, 목표 시점

## 한계

- 기대값만 낸다. 운에 따른 분산(드랍이 몰리거나 안 나오는 판)은 없다.
- 합성 가격은 재화 비용만 센다. 재료 아이템을 사는 비용은 따로 구매로 적는다.
- 드랍 판매 기대값은 희귀도 칸이면 그 희귀도 아이템 가격의 평균이다(천장은 반영하지 않는다).
- 단계 안에서는 수입이 고르게 들어온다고 본다. 라운드 사이에만 사는 게임의 `purchase_timing`은 [게임 형태별](../level-design/references/game-shapes.md#라운드로-나뉜-게임의-단계)대로 적는다.
- 단계의 누적은 적은 순서대로 지난다고 본다. 스테이지를 골라서 하는 게임은 대표 경로 하나를 순서로 적는다([게임 형태별](../level-design/references/game-shapes.md#스테이지-선택형)).

예시: `studio-data/assets/sample-project/data/economy.json` (실제 게임 수치가 아니다).
