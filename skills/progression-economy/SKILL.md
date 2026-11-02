---
name: progression-economy
description: "Validates item data and drop tables, and simulates roguelike meta-progression with an explicit abstract model, so that item tiers, dominated items, pity expectations, and runs-to-milestone curves come from deterministic scripts rather than LLM estimates. Use when designing or reviewing items, loot, shops, permanent upgrades, or progression pacing for action roguelikes and other run-based games in any engine."
---

# 아이템·성장 경제

액션 로그라이크 같은 런 기반 게임의 아이템과 메타 성장 수치를 스크립트로 검사한다. 엔진에 묶이지 않도록 데이터는 JSON 또는 CSV로 다룬다. 모든 수치 표기는 [numeric-provenance](../numeric-provenance/SKILL.md)를 따른다.

## 두 도구

| 도구 | 답하는 질문 | 답하지 못하는 질문 |
|---|---|---|
| `scripts/validate_items.py` | 상위 티어가 하위보다 약하지 않은가, 아무도 고르지 않을 열위 아이템이 있는가, 드랍 확률과 천장 기대 시도 수는 얼마인가 | 아이템이 재미있는가, 고유 효과의 실제 가치 |
| `scripts/simulate_meta.py` | 정해 둔 모델에서 몇 번째 런에 강화를 사고 보스를 넘는가, 진척이 멈추는 구간이 있는가 | 실제 조작 난이도, 손맛, 재미 |

시뮬레이터 결과는 **입력 파라미터가 맞다는 가정 아래의 계산값**이다. 생존 기울기나 실력 같은 입력이 `[가정]`이면 결론도 그 가정에 묶인다.

## 작업 순서

1. **데이터를 단일 원본으로 둔다.** 아이템과 강화 수치를 게임이 읽는 JSON/CSV 파일로 관리하면, 엔진과 도구가 같은 파일을 본다. 형식은 [references/data-format.md](references/data-format.md).
2. **아이템을 검사한다.**
   ```bash
   python skills/progression-economy/scripts/validate_items.py data/items.json --out reports/items.json
   ```
   - 오류(형식, 중복 id, 없는 아이템 참조)는 먼저 고친다.
   - 경고(`tier_inversion`, `dominated`)는 의도인지 판단한다. 시작 무기처럼 의도한 열위라면 설계 문서에 이유를 적는다. 의도가 아니면 고친다.
   - 고유 효과 아이템(`unique_effect: true`)은 열위 판정에서 빠지고 "판정 제외"로 표시된다. 판정 불가를 통과로 보고하지 않는다.
3. **메타 성장을 모델링한다.** 모델과 파라미터는 [references/meta-model.md](references/meta-model.md).
   ```bash
   python skills/progression-economy/scripts/simulate_meta.py data/meta.json --out reports/meta.json --csv reports/meta-curve.csv
   ```
4. **결과를 문서에 출처와 함께 적는다.** 결과값은 `[계산: reports/meta.json]`처럼 저장한 파일을 출처로 쓴다. 입력 파라미터 표의 값은 측정 전까지 `[가정]`으로 둔다.
5. **한 번에 하나만 바꾸고 다시 돌린다.** 같은 seed·trials·max_runs로 비교한다. 여러 값을 한꺼번에 바꾸면 어느 변경이 효과를 냈는지 알 수 없다.
6. **플레이 기록이 생기면 보정한다.** 실제 런의 도달 방 분포와 모델의 `survival_at_base_power`, 마일스톤 분포를 비교해 `survival.slope`와 `player.skill`을 맞춘다. 보정 근거가 된 파라미터만 `[측정: 기록 출처]`로 올린다.

## 판정 규칙

- 시뮬레이터 결과만으로 "난이도 적절", "재미있음"을 판정하지 않는다. 경제·성장 곡선의 구조적 문제(너무 이른 완료, 긴 정체, 도달 불가)를 찾는 데 쓴다.
- 도달률이 100%가 아닌 마일스톤은 중앙값만 보고하지 않는다. `reached_fraction`과 "미도달"을 함께 적는다.
- 구매 정책(`listed_order` / `cheapest_first`)에 따라 결론이 달라지면, 그것 자체를 발견으로 보고한다. 한쪽만 골라 보고하지 않는다.
- 숫자를 손으로 조정해 원하는 결과가 나오게 맞추지 않는다. 조정했다면 무엇을 왜 바꿨는지와 바꾸기 전·후 결과를 함께 남긴다.

## 보고

- 실행한 명령, seed, trials, 설정 파일 해시(`config_sha256`)
- 오류·경고 개수와 의도된 예외의 근거
- 마일스톤과 강화별 도달률, p10 / 중앙값 / p90 런
- 가장 큰 구조적 위험 하나와 그것을 확인할 가장 싼 다음 실험
- 결과가 기대는 `[가정]` 입력 목록

Python 3.9 이상, 표준 라이브러리만 쓴다. 예시 데이터는 `assets/sample-items.json`, `assets/sample-meta.json`이며 실제 게임 수치가 아니다.
