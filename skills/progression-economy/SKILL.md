---
name: progression-economy
description: "Keeps items, permanent upgrades, and enemies in single-source JSON/CSV data, shows them in a read-only local viewer, validates them with deterministic scripts (tier inversions, dominated items, pity expectations, upgrade cost chains, enemy threat progression, cross-file drop-table references), and simulates roguelike meta-progression with an explicit abstract model. Use when designing, adding, or reviewing items, loot, shops, permanent upgrades, enemies, or progression pacing for action roguelikes and other run-based games in any engine."
---

# 아이템·강화·적 데이터와 성장 경제

액션 로그라이크 같은 런 기반 게임의 아이템, 영구 강화, 적 데이터를 한 곳에서 관리하고 스크립트로 검사한다. 엔진에 묶이지 않도록 데이터는 JSON 또는 CSV로 다룬다. 모든 수치 표기는 [numeric-provenance](../numeric-provenance/SKILL.md)를 따른다.

## 도구

| 도구 | 답하는 질문 | 답하지 못하는 질문 |
|---|---|---|
| `scripts/view_data.py` | 원본 데이터를 종류별 탭과 묶음(부위·트랙·구역)별 표로 보고, 검사 경고가 난 항목을 바로 찾는다 | (읽기 전용 뷰어. 수정은 원본에서) |
| `scripts/validate_items.py` | 상위 티어가 하위보다 약하지 않은가, 아무도 고르지 않을 열위 아이템이 있는가, 드랍 확률과 천장 기대 시도 수는 얼마인가 | 아이템이 재미있는가, 고유 효과의 실제 가치 |
| `scripts/validate_upgrades.py` | 선행 조건이 끊기거나 순환하지 않는가, 다음 단계가 더 싸게 책정되지 않았는가, 트랙별 총비용·power는 얼마인가 | 강화가 체감되는가 |
| `scripts/validate_enemies.py` | 구역이 오를수록, 등급(일반 → 정예 → 보스)이 오를수록 위협도가 줄지 않는가, 드랍 테이블이 아이템 데이터에 있는가 | 패턴이 공정한가, 실제 난이도 |
| `scripts/simulate_meta.py` | 정해 둔 모델에서 몇 번째 런에 강화를 사고 보스를 넘는가, 진척이 멈추는 구간이 있는가 | 실제 조작 난이도, 손맛, 재미 |

점수(아이템)와 위협도(적)는 Σ(스탯 × 가중치)다. 가중치는 설계 가정이고, 같은 묶음 안에서만 비교한다. 시뮬레이터 결과는 **입력 파라미터가 맞다는 가정 아래의 계산값**이다.

## 단일 원본 규칙

- 아이템, 영구 강화, 적의 수치·효과·의도·상태·출처는 **종류별 원본 파일 한 곳**에만 쓴다. 권장 배치는 `data/items.json`, `data/upgrades.json`, `data/enemies.json`. 형식은 [references/data-format.md](references/data-format.md).
- 시뮬레이터 설정(`data/meta.json`)은 강화 목록을 직접 담지 않고 `"upgrades_file": "upgrades.json"`으로 원본을 가리킨다.
- 기획 문서(md)는 항목을 `id`로만 언급한다. 공격력·가격·체력 같은 수치를 md에 옮겨 적지 않는다. 옮겨 적으면 원본을 고칠 때 어긋난다.
- 보기 좋은 정리가 필요하면 문서를 생성하지 않고 뷰어로 원본을 본다.
  ```bash
  python skills/progression-economy/scripts/view_data.py data/
  ```
  - **서버 모드(기본)**: 브라우저가 열리고, 폴더 안 데이터 파일을 매번 다시 읽고 검사기를 함께 돌린다. 원본을 고치거나 새 파일을 넣으면 화면이 자동으로 갱신된다. 시뮬레이터 설정과 관계없는 JSON은 건너뛴다. 기본으로 이 컴퓨터(127.0.0.1)에서만 열린다.
  - **파일 모드(보조)**: `assets/data-viewer.html`을 직접 열고 '불러오기'로 JSON을 고른다. 원본에 적힌 값만 보여 주며 검사·점수·확률 계산은 하지 않는다. 화면에 "검사 없음"이 표시된다. Chrome·Edge는 고른 파일이 바뀌면 다시 읽는다. 검사 규칙을 JavaScript로 복제하지 않기 위해 이렇게 나눴다.

## 항목 추가·변경 요청

"이런 아이템(강화, 적)이 있으면 좋겠어" 같은 요청은 다음 순서로 처리한다.

1. 요청을 해당 원본 파일의 항목으로 바꾼다. `status: "proposed"`, `provenance: {"kind": "assumed", "note": "요청 기반 초안"}`로 넣는다. 수치는 에이전트 제안이므로 가정이다.
2. 숫자로 비교할 수 없는 효과는 `effect`에 적는다(아이템은 `unique_effect: true`도 붙인다). 왜 넣는지 `intent`에 한 줄로 적는다.
3. 해당 검사기를 돌린다. 적은 `--items data/items.json`으로 드랍 테이블 참조까지 확인한다. 경고가 나오면 함께 보고한다.
4. 대화에는 **새로 추가되거나 바뀐 행만** 표로 보여 준다. 전체 목록은 뷰어로 안내한다.
5. 사용자가 승인하면 `approved`로 바꾼다. 거절하면 지우지 말고 `cut`으로 두고 `intent`에 뺀 이유를 남긴다. `cut` 항목은 비교, 합계, 시뮬레이션, 게이트에서 빠진다.
6. 사용자 승인 없이 `approved`로 바꾸지 않는다.

## 작업 순서

1. **데이터를 단일 원본으로 둔다.** 게임이 읽는 JSON/CSV 파일을 도구도 그대로 읽는다.
2. **검사한다.**
   ```bash
   python skills/progression-economy/scripts/validate_items.py data/items.json --out reports/items.json
   python skills/progression-economy/scripts/validate_upgrades.py data/upgrades.json --out reports/upgrades.json
   python skills/progression-economy/scripts/validate_enemies.py data/enemies.json --items data/items.json --out reports/enemies.json
   ```
   - 오류(형식, 중복 id, 없는 참조, 순환, 삭제된 선행 조건)는 먼저 고친다.
   - 경고(`tier_inversion`, `dominated`, `cost_inversion`, `power_missing`, `zone_inversion`, `rank_inversion`)는 의도인지 판단한다. 의도라면 해당 항목의 `intent`에 이유를 적는다. 의도가 아니면 고친다.
   - 판정할 수 없는 것(고유 효과 아이템의 열위, `--items` 없이 본 적의 드랍 테이블)은 "판정 제외" 또는 "미확인"으로 표시된다. 통과로 보고하지 않는다.
   - 확정 판정 전에는 `--fail-on-assumed`를 붙인다. 삭제되지 않은 항목 중 출처가 가정이거나 비어 있는 것이 있으면 실패한다.
3. **메타 성장을 모델링한다.** 모델과 파라미터는 [references/meta-model.md](references/meta-model.md).
   ```bash
   python skills/progression-economy/scripts/simulate_meta.py data/meta.json --out reports/meta.json --csv reports/meta-curve.csv
   ```
   강화 데이터에 오류가 있거나 활성 강화에 `power`가 없으면 시뮬레이터가 실행을 거부한다.
4. **결과를 문서에 출처와 함께 적는다.** 결과값은 `[계산: reports/meta.json]`처럼 저장한 파일을 출처로 쓴다. 데이터 파일의 수치는 md 태그 대신 각 항목의 `provenance` 필드로 표시한다.
5. **한 번에 하나만 바꾸고 다시 돌린다.** 같은 seed·trials·max_runs로 비교한다. 여러 값을 한꺼번에 바꾸면 어느 변경이 효과를 냈는지 알 수 없다.
6. **플레이 기록이 생기면 보정한다.** 실제 런의 도달 방 분포와 모델의 `survival_at_base_power`, 마일스톤 분포를 비교해 `survival.slope`와 `player.skill`을 맞춘다. 보정 근거가 된 파라미터만 `[측정: 기록 출처]`로 올린다.

## 판정 규칙

- 검사기와 시뮬레이터 결과만으로 "난이도 적절", "재미있음"을 판정하지 않는다. 구조적 문제(역전, 끊긴 사슬, 너무 이른 완료, 긴 정체, 도달 불가)를 찾는 데 쓴다.
- 도달률이 100%가 아닌 마일스톤은 중앙값만 보고하지 않는다. `reached_fraction`과 "미도달"을 함께 적는다.
- 구매 정책(`listed_order` / `cheapest_first`)에 따라 결론이 달라지면, 그것 자체를 발견으로 보고한다. 한쪽만 골라 보고하지 않는다.
- 숫자를 손으로 조정해 원하는 결과가 나오게 맞추지 않는다. 조정했다면 무엇을 왜 바꿨는지와 바꾸기 전·후 결과를 함께 남긴다.

## 보고

- 실행한 명령, seed, trials, 설정 파일 해시(`config_sha256`)와 강화 파일 해시(`upgrades_file.sha256`)
- 오류·경고 개수와 의도된 예외의 근거
- 마일스톤과 강화별 도달률, p10 / 중앙값 / p90 런
- 가장 큰 구조적 위험 하나와 그것을 확인할 가장 싼 다음 실험
- 결과가 기대는 `[가정]` 입력 목록

Python 3.9 이상, 표준 라이브러리만 쓴다. 예시 데이터는 `assets/sample-items.json`, `assets/sample-upgrades.json`, `assets/sample-enemies.json`, `assets/sample-meta.json`이며 실제 게임 수치가 아니다.
