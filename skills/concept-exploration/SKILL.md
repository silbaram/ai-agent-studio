---
name: concept-exploration
description: "Explores game concepts as testable mechanic hypotheses instead of ranked pitches: gathers constraints, generates structurally varied concepts, removes only demonstrated dead ends and structural duplicates, attacks survivors with simple-play strategies, keeps every concept in one concepts.json record, and turns the user's chosen concept into a falsifiable brief with pillars, anti-pillars, a core loop, hypotheses, and the smallest prototype. Use when the user has only a vague genre or feeling, wants concept ideas, needs to compare or choose concepts, or wants a chosen concept sharpened before prototyping."
---

# 컨셉 탐색

막연한 방향("액션 로그라이크에 성장 요소")을 **시험할 수 있는 게임 가설** 몇 개로 바꾸고, 사용자가 고른 하나를 프로토타입할 수 있는 브리프로 다듬는다.

## 원칙

- **재미를 점수로 매기지 않는다.** "가장 재미있어 보이는 안"을 고르지 않는다. 남은 컨셉은 증명된 재미가 아니라 시험할 가치가 있는 가설이다.
- **테마보다 구조.** 이름·배경·그림이 달라도 반복해서 내리는 결정이 같으면 같은 게임이다. 다양성은 구조로 센다.
- **증명된 결함으로만 탈락시킨다.** 낯설다, 설명하기 어렵다, 위험하다는 탈락 사유가 아니다. 모르는 것은 실패가 아니라 `unknown`이다.
- **결정은 사용자가 한다.** 에이전트는 후보·근거·다음 시험을 제시하고, 선택과 승인은 사용자가 한다. 선호는 증거가 아니다.
- **기록은 한 곳.** 모든 후보와 판단은 `design/concepts.json`에 남긴다. 탈락한 안도 지우지 않고 `cut`과 이유를 남긴다. 형식은 [references/concept-record.md](references/concept-record.md).

## 쓰지 않을 때

- 이미 컨셉이 정해졌고 수치·데이터를 다룰 때: [progression-economy](../progression-economy/SKILL.md)
- 기획 문서 수치의 출처 표시: [numeric-provenance](../numeric-provenance/SKILL.md)

## 흐름

### 1. 제약 모으기

다섯 개 이하로 묻는다. 사용자가 모르면 기본값을 제안하고 가정으로 표시한다.

- 플랫폼·입력(키보드, 패드, 터치)과 한 판 길이
- 원하는 감정이나 긴장(예: "아슬아슬하게 살아남는 느낌")
- 제작 규모(인원, 기간)와 엔진 후보
- 피하고 싶은 것(장르, 메커니즘, 분위기)
- 좋아하는 참고 게임 — 영감용이며 베끼지 않는다

답을 `concepts.json`의 `constraints`에 적는다.

### 2. 탐색 범위 나누기

[references/search-axes.md](references/search-axes.md)의 구조 축(반복 결정, 정보, 확약, 위험-보상, 공간, 압박, 성장)을 보고 후보들이 서로 다른 칸에 놓이도록 미리 나눈다. 첫 연상에 쏠리지 않게 하기 위해서다.

### 3. 첫 후보 만들기

기본 12개(사용자가 짧게 원하면 6개). 각 후보마다 반드시 적는다.

- 한 문장 피치, 핵심 동사
- **반복 결정**: 플레이어가 몇 초마다 다시 내리는 선택
- **결정 전에 읽는 정보**: 그 선택을 위해 화면에서 무엇을 보는가
- **숙련 표현**: 잘하는 사람이 단순한 전략과 어떻게 다르게 하는가
- 구조 축 값(`signature`, 4개 이상), 가장 큰 위험

이 단계에서는 업그레이드·상점·스토리·연출을 붙여 약한 안을 살리지 않는다.

### 4. 싸게 반증하기

[references/stress-policies.md](references/stress-policies.md)의 단순 전략(가만히 있기, 한 버튼 반복, 항상 도망, 항상 돌진 등)으로 각 후보를 공격한다. 전략마다 `dominates`(단순 전략이 이김) / `competitive` / `loses` / `unknown`을 적고, `unknown`이 아니면 근거를 적는다.

- 핵심 루프가 성립하지 않는다는 **증명된 결함**이 있을 때만 `hard_reject`로 제외한다(유형·이유·증거 필수).
- 단순 전략이 이기지만 규칙 하나로 고칠 수 있으면 제외하지 말고 다음 단계에서 변이한다.

### 5. 겹치는 후보 정리

```bash
python skills/concept-exploration/scripts/check_concepts.py design/concepts.json --table
```

검사기가 구조 축이 거의 같은 후보(`near_duplicate`)와 모든 후보가 같은 값에 몰린 축(`axis_collapse`)을 알려 준다. 겹치는 묶음에서는 대표 하나만 남기고 나머지는 `cut`으로 둔다.

### 6. 변이하기 (최대 2회)

유망하지만 약한 후보는 **인과 관계 하나**를 바꾼다(정보 구조, 확약, 위험-보상 결합, 공간 위상 등). 새 후보의 `origin`에 원래 id를 적고, 무엇이 달라질 것으로 기대하는지 `notes`에 적는다. 새 후보가 기존 구조와 겹치기만 하거나, 결정 없이 규칙만 늘어나면 멈춘다.

### 7. 후보 제시와 선택

3~5개를 비교표로 보여 준다(`--table` 출력). 합계 점수 열은 없다. 각 후보마다 다음을 말한다.

- 왜 남았는가, 가장 강한 구조적 근거
- 가장 큰 위험과 아직 모르는 것
- 그것을 확인할 가장 작은 시험과 제작 부담(가정)

추천을 요청받으면 "가장 재미있을 안"이 아니라 **적은 비용으로 가장 많이 배울 수 있는 안**을 먼저 시험하자고 제안한다. 선택은 사용자가 한다. 사용자 응답 없이 진행하는 작업이면 모든 후보를 `proposed`로 두고 "선택 대기"로 끝낸다. 응답을 지어내지 않는다.

### 8. 선택한 컨셉을 브리프로

사용자가 고른 후보를 `approved`로 바꾸고 `brief`를 채운다. 작성법은 [references/brief.md](references/brief.md).

- 경험 목표 한 문장
- 필러 2~5개. 각각 "A와 B 중 이 게임은 __를 고른다" 형태의 설계 테스트
- 안티필러(이 게임이 하지 않을 것) 1개 이상
- 루프: 30초 / 한 판 / 판 사이 성장
- 반증 가능한 가설 1개 이상: 주장, 틀렸다는 신호, 확인 방법
- 가장 작은 프로토타입: 범위, 기간(일), 성공 기준
- MVP 7개 이하, 범위 밖 목록 1개 이상

검사기는 `approved` 컨셉의 브리프가 빠짐없는지 확인한다. 통과하지 못하면 프로토타입 단계로 넘기지 않는다.

## 보고

- `--table` 비교표와 검사 결과(오류·경고 수)
- 사용자가 결정해야 할 것 한 가지
- 다음 시험 하나와 그 시험이 어떤 결과면 무엇을 바꿀지

## 다음 단계

프로토타입 결과로 가설을 판정한다. 틀렸다는 신호가 나오면 브리프를 고치거나 다른 후보로 돌아간다. 가설이 버티면 아이템·강화·적 데이터를 [progression-economy](../progression-economy/SKILL.md)로 시작한다.

검사 스크립트는 Python 3.9 이상, 표준 라이브러리만 쓴다. 예시는 `assets/sample-concepts.json`이며 실제 기획안이 아니다.
