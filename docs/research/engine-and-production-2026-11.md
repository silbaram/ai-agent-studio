# 엔진 고르기와 시험판에서 본 게임으로 넘어가기 조사 (2026-11)

조사일: 2026-11-16. 별 수와 최근 활동은 그날 `gh api` 기준이다. 문서만 읽었고 저장소의 코드는 실행하지 않았다. 핵심 인용 세 곳(CCGS `rules/prototype-code.md`, abagames `refining-game-prototypes`, awesome-gamedev `prototype-fast` 109–110)은 원문에서 다시 확인했다.

## 왜 조사했나

우리 스킬은 아이디어 → 약속서(브리프) → 시스템 → 그림 없는 시험판 → 플레이 → 판정까지 다룬다. 가설이 버틴 뒤의 두 단계가 비어 있다.

1. 엔진을 언제, 무엇으로, 누가 정하는가
2. 시험판에서 본 게임으로 어떻게 넘어가는가: 넘어가는 조건, 가져갈 것과 버릴 것, 시험판을 버리고 새로 만들지 키울지, 새 빌드에서 가설을 다시 확인할지

사용자가 정한 방향(2026-11-16): 엔진은 가설이 버틴 뒤 정하는 것이 기본이다(처음부터 정해진 경우는 제약으로 둔다). 시험판은 "버리고 새로"와 "키워 가기" 중 고른다. 본 게임 빌드에서 가설을 작은 표본으로 다시 확인한다.

## AI 에이전트 저장소

| 저장소 | 별 · 최근 · 라이선스 | 엔진 고르기 | 넘어가는 조건 | 버리기/키우기 | 새 빌드에서 다시 확인 | 기계 검사 |
|---|---|---|---|---|---|---|
| [Donchitos/Claude-Code-Game-Studios](https://github.com/Donchitos/Claude-Code-Game-Studios) | 39.6k · 11-09 · MIT | 질문으로 1~2개 추천, 사용자가 고름. `project.yaml`에 기록 | 버티컬 슬라이스에 NO가 하나라도 있으면 FAIL, 하지 않았으면 통과 아님 | 엔진 시험판은 버림. 브라우저 원샷은 복사해서 키우고 같은 시드 재생으로 동일성 확인 | 슬라이스에서 "재미가 살아남았나" 질문 수준 | 셸 가드·재생, 엔진 표 |
| [striderZA/OpenCodeGameStudios](https://github.com/striderZA/OpenCodeGameStudios) | 125 · 11-13 · MIT | CCGS와 같음 + 엔진별 LLM 지식 공백 위험 | ITERATE/PIVOT/PRODUCTIONIZE/KILL을 자유 서술로 | 넘어가면 처음부터 다시 | 없음 | 없음 |
| [abagames/agentic-gamedev-skills](https://github.com/abagames/agentic-gamedev-skills) | 43 · 10-17 · MIT | 없음(플러그인이 곧 엔진) | 없음 | 첫 빌드를 키움 | 규칙이 바뀌면 영향받는 답에 그 답을 얻은 빌드를 붙이고 다시 구함 | 수정 로그 |
| [gamedev-skills/awesome-gamedev-agent-skills](https://github.com/gamedev-skills/awesome-gamedev-agent-skills) | 9.0k · 11-12 · Apache-2.0 | 파일 지문으로 판단, 없으면 Godot 기본 | 시험판 브리프의 KEEP IF / KILL IF | 남기기로 해도 본 프로젝트에서 다시 쓴다(복사 금지) | 없음 | `prototypes/` 밖이 바뀌지 않았는지 확인 |
| [WhiteTowerAI/ohmygame](https://github.com/WhiteTowerAI/ohmygame) | 2.3k · 11-16 · Apache-2.0 | 에이전트가 플랫폼·카메라 등으로 고름, 기록 없음 | 없음 | 해당 없음 | 없음 | 없음 |
| [sickn33/antigravity-awesome-skills](https://github.com/sickn33/antigravity-awesome-skills) `engine-selection` | 49.8k(모음 전체) · 11-15 · MIT | 질문 5개와 결정 트리. 평판 대신 핵심 기믹과 배포 크기로 시험하라고 함 | 없음 | 없음 | 없음 | 없음 |

편집기 조작 MCP 서버(CoplayDev/unity-mcp, Coding-Solo/godot-mcp, Roblox/studio-rust-mcp-server)에는 엔진 선택과 넘어가기 절차가 없다. [OpenDCAI/GameFactory-3A](https://github.com/OpenDCAI/GameFactory-3A)는 처음 요구사항 단계에서 엔진을 정하고 같은 엔진에서 흰 상자 → 에셋 다듬기로 간다.

## AI 아닌 게임 제작 자료

GitHub에 있는 절차 자료는 적다. 큰 학습 목록도 결국 GitHub 밖 사이트를 가리킨다.

| 자료 | 별 · 최근 · 라이선스 | 쓸 만한 것 |
|---|---|---|
| [RikuKat/game-dev-foundry](https://github.com/RikuKat/game-dev-foundry) | 30 · 2026-03 · **없음** | 단계마다 목표·산출물·끝내는 조건·흔한 함정 네 칸. 시험판을 끝내는 조건(재미의 불꽃 하나, 모르는 것과 그 시험 계획), 버티컬 슬라이스에서 핵심 경험·엔진 안에서의 모습·필요한 기술을 실제로 확인. 위험을 분류해 가능성·대응·조기 신호·담당으로 적는 사전 부검(premortem). 라이선스가 없어 문장은 옮기지 않고 구조만 참고한다 |
| [JohnDuncanScott/2d-game-engine-comparison](https://github.com/JohnDuncanScott/2d-game-engine-comparison) | 17 · 2025-05 · MIT | 필수 조건 표에서 하나라도 ❌면 탈락하고 탈락 사유를 남긴다. 남은 후보로 같은 게임을 만들어 걸린 시간과 빌드 크기를 잰다. 주관적 이유(좋아하는 언어 등)는 따로 적는다. 엔진 버전도 기록 |
| [LazyHatGuy/GDDMarkdownTemplate](https://github.com/LazyHatGuy/GDDMarkdownTemplate) | 64 · 2023-02 · 불명확 | 엔진이 "적어 둘 칸"일 뿐 기준이 없는 흔한 예 |
| [kitatus 제작 단계 글](https://github.com/kitatus/kitatus.github.io) | 0 · 라이선스 없음 | 넘어가는 판정이 통과·다시 설계·버림 셋이다. 버티컬 슬라이스에서 앞 단계로 되돌아가는 일이 가장 많다 |
| [UnityTechnologies/open-project-1](https://github.com/UnityTechnologies/open-project-1) | 6.1k · 2021-12 · Apache-2.0 | 엔진 버전을 기계가 읽는 파일(`ProjectVersion.txt`) 하나에 고정 |
| [vhladiienko/awesome-game-production](https://github.com/vhladiienko/awesome-game-production) | 236 · 2026-11 · CC0 | 링크 목록. 쓸 만한 글은 GitHub 밖 |

## 공통으로 보이는 것

- **엔진은 사람이 정하고 기록한다.** 잘된 곳은 이미 있는 엔진 → 경험 → 플랫폼 순으로 한두 개를 추천하고 사용자가 고른다. 못된 곳은 도구 편의(카탈로그가 Godot을 많이 다룸, 자기 도구가 웹을 만듦)로 기본값을 정하거나 기록 없이 고른다.
- **평판 표보다 작은 시험.** 필수 조건으로 거르고, 남은 후보로 같은 작은 과제(핵심 기믹, 배포 크기)를 만들어 본다.
- **엔진 시험판은 버리고 본 게임은 새로 쓴다**가 다수다. 키우는 곳은 원본을 보존하고 동일성 검사를 둔다(CCGS). 코드를 "조금씩 정리해 키우는" 것은 모두 경계한다. 다만 성숙한 자료 중 언제 키워도 되는지 기준을 둔 곳은 없다.
- **넘어가는 조건은 "하나라도 NO면 실패, 안 했으면 통과 아님"**이 가장 분명하다. 반대로 산출물 스무 개짜리 목록이나 근거 없는 "재사용 가능 X%" 칸은 피할 것으로 보인다.
- **새 빌드에서 가설을 하나씩 다시 판정하는 곳은 없다.** CCGS는 "재미가 살아남았나"를 질문 수준으로, abagames는 규칙 변경에 영향받는 답에 빌드를 붙여 다시 구하는 수준이다. 우리가 채울 빈칸이다.

## 우리 스킬에 가져올 것

1. **엔진 결정 기록 하나.** 필수 조건은 브리프의 제약(플랫폼, 입력, 규모)과 가설이 요구하는 것에서 나온다. 후보마다 조건별 통과·실패와 근거를 적고, 하나라도 실패하면 고를 수 없다. 주관적 이유와 엔진별 LLM 지식 공백 위험은 따로 적는다. 고른 엔진은 정확한 버전과 `[결정: 사용자 날짜]`로 남긴다.
2. **엔진 시험(스파이크).** 남은 후보로 같은 작은 과제를 만든다: `data/*.json`을 읽어 핵심 루프 하나를 돌린다. 걸린 시간과 막힌 곳을 적는다. 우리 데이터는 엔진 중립 JSON이라 이 과제가 엔진마다 같다.
3. **넘어가는 조건을 검사기가 본다.** 고른 컨셉의 가설이 모두 확정되었는지(버팀, 또는 사용자가 모름으로 두기로 한 것), 가정이 남지 않았는지는 지금 `check --fail-on-assumed`가 이미 본다. 결과는 진행 · 되돌아가기 · 그만두기 셋이고, 하지 않은 확인은 통과가 아니다.
4. **가져갈 것과 버릴 것 목록.** 가져갈 것: `data/*.json`, 숫자 출처, 브리프와 가설·판정, 시스템 설계, 플레이 기록 형식. 버릴 것: 시험판 코드, 시험용 값과 기록 기능(scope-guard의 지금 규칙과 같다). "키워 가기"를 고르면 원본 시험판을 보존하고, 같은 데이터·같은 시드에서 핵심 수치가 같은지 확인한 뒤에 바꾼다.
5. **판정에 빌드를 붙이고 새 빌드에서 작게 다시 판정.** 시험판 빌드에서 버틴 가설은 본 게임 빌드로 넘어가면 "시험판에서 버팀, 본 게임 빌드 미확인"으로 보인다. 본 게임 빌드의 세션이 작은 표본으로 다시 판정해야 확인된다. 지금 판정과 빌드 지문 규칙에 붙이면 된다.
6. **되돌아가기를 셈한다.** 넘어가기에서 되돌아간 횟수를 남긴다. 되돌아가기를 반복하는 것도 신호다.

## 피할 것

- 도구나 카탈로그 편의로 엔진 기본값을 정하는 것, 기록 없이 에이전트가 고르는 것
- 필수 조건에 주관적 이유를 섞는 것
- 긴 산출물 목록, 근거 없는 재사용 비율
- 한 번만 손으로 만든 버티컬 슬라이스로 제작 속도를 증명했다고 보는 것
- 시험판 코드를 조금씩 정리해 본 게임으로 키우는 것(키운다면 원본 보존과 동일성 검사)
- 라이선스 없는 자료(game-dev-foundry, kitatus)의 문장을 옮기는 것. 구조와 생각만 참고한다
