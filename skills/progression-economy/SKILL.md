---
name: progression-economy
description: "Keeps items, permanent upgrades, and enemies in single-source JSON/CSV data, shows them in a read-only local viewer, validates them with deterministic scripts (tier inversions, dominated items, pity expectations, upgrade cost chains, enemy threat progression, cross-file drop-table references), and simulates roguelike meta-progression either with an explicit abstract model or from the combat data (permanent upgrade stats and in-run growth added to the combat calculation per stage, with income and purchase order read from the economy plan). Use when designing, adding, or reviewing items, loot, shops, permanent upgrades, enemies, or progression pacing for action roguelikes and other run-based games in any engine."
license: MIT
---

# 아이템·강화·적 데이터와 성장 경제

액션 로그라이크 같은 런 기반 게임의 아이템, 영구 강화, 적 데이터를 한 곳에서 관리하고 스크립트로 검사한다. 엔진에 묶이지 않도록 데이터는 JSON 또는 CSV로 다룬다. 모든 수치 표기는 [numeric-provenance](../numeric-provenance/SKILL.md)를, 데이터는 [데이터 공통 규칙](../studio-data/references/data-rules.md)을, 판단은 [밸런스 공통 원칙](../studio-data/SKILL.md#밸런스-공통-원칙)을 따른다.

## 도구

명령은 공용 스킬 [studio-data](../studio-data/SKILL.md)의 `studio.py`로 하고, Claude Code 설치 기준으로 적었다(다른 설치는 [실행](../studio-data/SKILL.md#실행)).

| 도구 | 답하는 질문 | 답하지 못하는 질문 |
|---|---|---|
| `studio.py view` | 원본 데이터를 종류별 탭과 묶음(부위·트랙·구역)별 표로 보고, 검사 경고가 난 항목을 바로 찾는다 | (읽기 전용 뷰어. 수정은 원본에서) |
| `studio.py check` (아이템) | 상위 티어가 하위보다 약하지 않은가, 아무도 고르지 않을 열위 아이템이 있는가, 드랍 확률과 천장 기대 시도 수는 얼마인가 | 아이템이 재미있는가, 고유 효과의 실제 가치 |
| `studio.py check` (영구 강화) | 선행 조건이 끊기거나 순환하지 않는가, 다음 단계가 더 싸게 책정되지 않았는가, 트랙별 총비용·power는 얼마인가 | 강화가 체감되는가 |
| `studio.py check` (적) | 구역이 오를수록, 등급(일반 → 정예 → 보스)이 오를수록 위협도가 줄지 않는가, 드랍 테이블이 아이템 데이터에 있는가 | 패턴이 공정한가, 실제 난이도 |
| `studio.py simulate` | 정해 둔 모델에서 몇 번째 런에 강화를 사고 보스를 넘는가, 진척이 멈추는 구간이 있는가 | 실제 조작 난이도, 손맛, 재미 |

점수(아이템)와 위협도(적)는 Σ(스탯 × 가중치)다. 가중치는 설계 가정이고, 같은 묶음 안에서만 비교한다. 아이템을 갖춘 플레이어가 적을 몇 번·몇 초에 잡는지처럼 **요소 사이**를 계산하려면 [combat-balance](../combat-balance/SKILL.md)를 쓴다. 같은 원본 데이터를 그대로 참조한다. 티어·구역을 넘어 곡선으로 비교하거나 새 항목을 곡선에서 만들려면 [stat-budget](../stat-budget/SKILL.md)을 쓴다. `data/budget.json`이 있으면 가중치 대신 그 원가로 점수를 낸다. 아이템 강화와 합성, 아이템을 얻는 경로는 [crafting-balance](../crafting-balance/SKILL.md)가, 판 안의 수입과 구매 시점은 [economy-flow](../economy-flow/SKILL.md)가 다룬다. 메타 성장 시뮬레이터의 판 수와 economy-flow의 판 수가 무엇을 세는지는 [재화 흐름 형식](../economy-flow/references/economy-format.md#메타-성장-설정과-맞춰-보기-meta_config)에 있다.

## 원본 파일

- 아이템, 영구 강화, 적은 종류별 원본 파일 한 곳(`data/items.json`, `data/upgrades.json`, `data/enemies.json`)에 둔다. 형식은 [references/data-format.md](references/data-format.md). md에는 `id`만 적는 것 등 지킬 규칙은 [단일 원본 규칙](../studio-data/references/data-rules.md#단일-원본-규칙).
- 카드·스킬처럼 효과가 규칙인 콘텐츠를 아이템 칸에 맞추는 법은 [효과가 규칙인 콘텐츠](references/data-format.md#효과가-규칙인-콘텐츠).
- 시뮬레이터 설정(`data/meta.json`)은 강화 목록을 직접 담지 않고 `"upgrades_file": "upgrades.json"`으로 원본을 가리킨다.

## 항목 추가·변경 요청

"이런 아이템(강화, 적)이 있으면 좋겠어" 같은 요청은 다음 순서로 처리한다.

1. 요청을 해당 원본 파일의 항목으로 바꾼다. `data/budget.json`이 있으면 [stat-budget 4단계](../stat-budget/SKILL.md#4-새-항목은-초안에서-시작한다)의 `draft`로 시작하고 출처도 그쪽대로 적는다. 없으면 `status: "proposed"`, `provenance: {"kind": "assumed", "note": "요청 기반 초안"}`로 넣는다. 수치는 에이전트 제안이므로 가정이다.
2. 숫자로 비교할 수 없는 효과는 `effect`에 적는다(아이템은 `unique_effect: true`도 붙인다). 왜 넣는지 `intent`에 한 줄로 적는다.
3. `python3 .claude/skills/studio-data/scripts/studio.py check .`로 검사한다. 적의 드랍 테이블 참조까지 확인된다. 경고가 나오면 함께 보고한다.
4. 대화에는 **새로 추가되거나 바뀐 행만** 표로 보여 준다. 전체 목록은 뷰어로 안내한다.
5. 사용자가 승인하면 `approved`로 바꾼다. 거절하면 지우지 말고 `cut`으로 두고 `intent`에 뺀 이유를 남긴다.
6. 사용자 승인 없이 `approved`로 바꾸지 않는다.

## 작업 순서

1. **데이터를 단일 원본으로 둔다.** 수치가 게임 코드에만 있으면 다른 점검 전에 [데이터로 옮긴다](../studio-data/references/data-rules.md#수치를-코드에서-데이터로-옮기기).
2. **검사한다.**
   ```bash
   python3 .claude/skills/studio-data/scripts/studio.py check . --out reports/data-check.json
   ```
   - 폴더를 주면 아이템·강화·적을 한 번에 검사하고, 적의 드랍 테이블은 함께 읽은 아이템 데이터로 확인한다.
   - 오류는 먼저 고친다. 경고는 의도인지 판단한다. 의도가 아니면 고치고, 의도라면 사용자와 확인한 뒤 그 항목의 `acknowledged`에 적는다([확인한 경고](../studio-data/SKILL.md#실행)). 코드와 조건은 [data-format의 검사 내용](references/data-format.md#검사-내용).
   - 고유 효과 아이템의 티어·열위처럼 판정할 수 없는 것은 "판정 제외"로, 함께 읽지 못한 참조는 "미확인"으로 표시된다.
   - 확정 판정 전에는 `--fail-on-assumed`를 붙인다. 삭제되지 않은 항목 중 출처가 가정이거나 비어 있는 것이 있으면 실패한다.
3. **메타 성장을 모델링한다.** 모델과 파라미터는 [references/meta-model.md](references/meta-model.md).
   ```bash
   python3 .claude/skills/studio-data/scripts/studio.py simulate data/meta.json --out reports/meta.json --csv reports/meta-curve.csv
   ```
   전투 계산(`data/combat.json`)이 있으면 추상 "힘" 대신 **전투 계산 모델**(`"model": "combat"`)을 쓴다. 영구 강화의 `stats`와 판 안 성장의 레벨업을 전투 계산에 더해 단계마다 생존을 정하고, 수입·구매 순서를 재화 흐름에서 읽을 수 있다([meta-model](references/meta-model.md#전투-계산-모델)).
   ```bash
   python3 .claude/skills/studio-data/scripts/studio.py simulate data/meta.json --compare-policies --out reports/meta-policies.json
   ```
4. **결과를 문서에 출처와 함께 적는다.** 결과값은 `[계산: reports/meta.json]`처럼 저장한 파일을 출처로 쓴다. 데이터 파일의 수치는 md 태그 대신 각 항목의 `provenance` 필드로 표시한다.
5. **하나만 바꾸고 같은 seed·trials·max_runs로 다시 돌린다**([공통 원칙](../studio-data/SKILL.md#밸런스-공통-원칙)).
6. **플레이 기록이 생기면 보정한다.** 전투 계산 모델은 `calibrate`가 기록의 단계 통과율과 비교해 `slope`·`even_margin`을 제안한다([playtest-verdict](../playtest-verdict/references/calibration.md)). 추상 모델은 실제 런의 도달 방 분포와 `survival_at_base_power`, 마일스톤 분포를 손으로 비교해 `survival.slope`와 `player.skill`을 맞춘다. 보정 근거가 된 파라미터만 `[측정: 기록 출처]`로 올린다.

## 판정 규칙

[밸런스 공통 원칙](../studio-data/SKILL.md#밸런스-공통-원칙)에 더해:

- 피해·방어가 덱 구성이나 키워드 같은 규칙에서 나오면 [효과가 규칙인 콘텐츠의 비교](../studio-data/references/data-rules.md#효과가-규칙인-콘텐츠의-비교)를 따른다.
- 도달률이 100%가 아닌 마일스톤은 중앙값만 보고하지 않는다. `reached_fraction`과 "미도달"을 함께 적는다.
- 구매 정책(`listed_order` / `cheapest_first`)에 따라 결론이 달라지면, 그것 자체를 발견으로 보고한다. 한쪽만 골라 보고하지 않는다([`--compare-policies`](references/meta-model.md#추상-모델)).

## 보고

- 첫 줄은 지금 위치, 정할 것도 [이 모양](../studio-data/references/telling-the-user.md)대로
- 실행한 명령, seed, trials, 설정 파일 해시(`config_sha256`)와 강화 파일 해시(`upgrades_file.sha256`)
- 오류·경고 개수와 의도된 예외의 근거
- 마일스톤과 강화별 도달률, p10 / 중앙값 / p90 런
- 가장 큰 구조적 위험 하나와 그것을 확인할 가장 싼 다음 실험
- 결과가 기대는 `[가정]` 입력 목록

예시 데이터는 `studio-data/assets/sample-project/data/`에 있으며 실제 게임 수치가 아니다.
