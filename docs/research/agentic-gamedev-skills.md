# agentic-gamedev-skills 분석

- 대상: [abagames/agentic-gamedev-skills](https://github.com/abagames/agentic-gamedev-skills) (MIT)
- 조사일: 2026-11-02, 얕은 클론 기준. 최근 커밋 2026-10-17.
- 방법: README, AGENTS.md, 플러그인 번들 구성과 핵심 스킬 약 6개(exploring-game-design-space, stress-testing-game-concepts, curating-game-concept-portfolio, evaluating-gameplay-balance, refining-game-prototypes, implementing-gameplay-invariants)를 직접 읽었다. 37개 전부를 읽거나 스크립트를 실행하지는 않았다.

## 한 줄 평가

프로세스 관리 틀이 아니라 "증거로 검증하는" 스킬 모음이다. 컨셉과 밸런스 쪽은 CCGS보다 훨씬 깊지만 대상이 미니게임·아케이드라 레벨·아이템·문서 체인은 없다.

## 구성

- 스킬 37개. 본문 25~282줄, 세부는 `references/`로 분리.
- 대상: 원버튼 미니게임, 아케이드, 2인 턴제. 엔진: Godot 4.2+, 웹(crisp-game-lib).
- 정본 스킬 + 번들 JSON에서 Codex·Claude Code용 플러그인 7개를 생성하고 무결성 검사와 CI를 둔다.

## 핵심 원칙

| 원칙 | 내용 |
|---|---|
| 단일 "재미 점수" 금지 | 구조적으로 다른 가설을 여러 개 내고 순위로 고르지 않는다 |
| unknown ≠ 실패 | `fails / weak / unknown / survives`. 확실한 핵심 결함이 있을 때만 hard reject |
| 근거 프로파일 명시 | 시뮬레이션 플레이어를 `oracle / precise / human-limited`로 구분. 난이도 판정은 human-limited에서만 |
| 표본 규율 | 비결정 환경은 n≥3 구간 보고, 변화 주장은 n≥5와 구간 비중첩. 철회도 정상 출력 |
| 무인 실행 | 사람 응답을 지어내지 않고 `review_pending`으로 끝낸다 |
| 비용에 맞는 검증 | 스킬이 언급했다는 이유로 비싼 게이트에 들어가지 않는다 |

## 우리 막힘 지점에 대한 적합도

- 컨셉 구체화: 높음. 탐색 → 반증 → 포트폴리오 선택이 서로 독립적으로 동작하며 ID·서명·출처를 유지해 넘긴다.
- 밸런스: 높음(측정 규율). 다만 점수 기반 아케이드 가정이라 아이템·경제·성장에는 개념만 쓸 수 있다.
- 이탈 방지: 부분적. `refining-game-prototypes`의 "의도 한 문장 → 한 번에 하나 변경 → 같은 조건 재측정 → 유지/되돌림 → 수정 로그" 루프.
- 레벨, 아이템·경제, 기획→스토리 추적: 없음.

## 가져올 것

1. 컨셉 3종의 방법과 기록 형식(안정 ID, 구조 서명, 증거 출처).
2. 밸런스 측정 규율(실행 프로파일, 표본 수, 철회, "조정 대상 파라미터로 정의된 정책 금지").
3. 반복 개선 루프와 수정 로그.
4. 설계 문장을 검증 가능한 불변식으로 바꾸는 방법.
5. "반복 절차는 스킬로, 의무 검사는 스크립트·훅·CI로" 원칙.
6. 정본 하나에서 Codex·Claude 형식을 생성하는 패키징.

## 가져오지 않을 것

에이전트 워크플로 메타 스킬 대부분, 웹 게임 라이브러리·레트로 오디오·타이포그래피 등 미니게임 전용 스킬. 도트 에셋과 게임 필은 game-art-skills가 더 깊다.
