# AI 에이전트 프로젝트 수명주기 도구 조사 (2026-11)

- 조사일: 2026-11-02. 스타 수는 GitHub 검색 API에서 읽은 그 시점 값이다.
- 상위 6개(superpowers, spec-kit, OpenSpec, BMAD-METHOD, get-shit-done, ccpm)는 README와 저장소 구조를 확인했다. 실제 설치·사용 시험은 하지 않았다.
- 스타 수는 인기 지표일 뿐 품질이나 게임 개발 적합도를 보장하지 않는다.

## 일반 개발용

| 프로젝트 | 스타 | 특징 |
|---|---:|---|
| [obra/superpowers](https://github.com/obra/superpowers) | 310,671 | 방법론을 스킬 15개로 구현. 질문 → 설계 승인 → 계획 → 서브에이전트 구현 → 완료 전 검증. 16개 환경 지원 |
| [github/spec-kit](https://github.com/github/spec-kit) | 145,045 | 스펙 → 계획 → 구현. 확장·프리셋·워크플로·번들·카탈로그로 프로세스 조립. Python/uv. 한국어 README |
| [Fission-AI/OpenSpec](https://github.com/Fission-AI/OpenSpec) | 73,618 | 변경 단위 폴더(제안·스펙·설계·태스크). "fluid not rigid". npm CLI |
| [bmad-code-org/BMAD-METHOD](https://github.com/bmad-code-org/BMAD-METHOD) | 54,867 | 애자일 역할(분석가·PM·아키텍트·UX·개발). v6.12 안정, v7 알파. API의 라이선스 표기가 NOASSERTION이라 확인 필요 |
| [open-gsd/gsd-core](https://github.com/open-gsd/gsd-core) | 11,135 | 원본 gsd-build/get-shit-done(64,181)에서 이전. 메타 프롬프트·컨텍스트 엔지니어링 |
| [eyaltoledano/claude-task-master](https://github.com/eyaltoledano/claude-task-master) | 28,290 | 태스크 분해·추적. 마지막 갱신 2026-04 |
| [automazeio/ccpm](https://github.com/automazeio/ccpm) | 8,425 | PRD → 에픽 → GitHub 이슈, 워크트리 병렬 실행 |

ruflo(80,552)와 paperclip(109,937)은 에이전트 대량 실행·운영 도구라 수명주기 관리와는 문제가 달라 자세히 보지 않았다.

## 게임 전용

| 프로젝트 | 스타 | 비고 |
|---|---:|---|
| Donchitos/Claude-Code-Game-Studios | 32,389 | [분석](claude-code-game-studios.md) |
| wellingfeng/UltraGameStudio | 328 | |
| MRCalderon3D/everything-game-dev-code | 101 | 다중 엔진 스캐폴드 |
| AlterLab-IEU/AlterLab_GameForge | 51 | |
| abagames/agentic-gamedev-skills | 38 | [분석](agentic-gamedev-skills.md) |
| CodePhobiia/claude-roblox-game-studio | 17 | Roblox 전용 |
| chenhangcuisg-code/gat | 11 | Godot 전체 사이클 |

게임 전용은 CCGS 외에 사용 이력이 쌓인 대안이 없다. CCGS 포크가 다수다.

## 인기 프로젝트의 공통점

1. 가볍다. 단계를 강제하지 않고 필요한 만큼만 쓴다.
2. 산출물이 저장소 파일로 남아 대화가 끊겨도 이어진다.
3. 여러 에이전트 환경(Claude Code, Codex 등)을 지원한다.
4. 확장 구조가 있다(spec-kit의 확장·프리셋·번들).
5. 완료 전 검증, TDD, 리뷰 같은 실행 규율이 핵심이다.
6. 서로 조합해서 쓴다(예: OpenSpec + Superpowers를 합친 spec-superflow).

## 결론

수명주기 뼈대는 검증된 일반 프레임워크를 쓰고, 일반 프레임워크가 다루지 않는 게임 설계 층(재미·레벨·밸런스·아이템)만 직접 만든다. 뼈대 후보는 spec-kit과 OpenSpec이며 실제 시험 후 결정한다. → [architecture.md](../architecture.md)
