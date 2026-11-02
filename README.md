# AI Agent Studio

AI 에이전트와 함께 게임 프로젝트를 기획부터 완성까지 관리하기 위한 스킬과 도구를 만든다.
개발이 처음 의도에서 벗어나지 않도록 수치·판정·범위를 증거와 스크립트로 통제하는 것이 목표다.

> 초기 단계다. 구조와 원칙은 [설계 문서](docs/architecture.md)에 있다.

## 층 구조

| 층 | 담당 |
| --- | --- |
| 수명주기 뼈대 (기획 → 설계 → 태스크 → 구현 → 검증) | 검증된 외부 도구를 시험 후 채택 (spec-kit 또는 OpenSpec 후보) |
| 게임 설계 (컨셉·시스템·레벨·아이템·경제·밸런스·재미 검증) | **이 저장소** |
| 그래픽 (도트·메시·VFX) | [game-art-skills](https://github.com/silbaram/game-art-skills) |

## 포함된 스킬

| 스킬 | 하는 일 |
| --- | --- |
| [numeric-provenance](skills/numeric-provenance/SKILL.md) | 기획 수치를 `[가정]` / `[계산: 출처]` / `[측정: 출처]`로 표시하고, 확정 판정 전에 스크립트로 검사 |

## 사용 예시

```text
$numeric-provenance로 design/economy.md의 모든 수치에 출처 태그를 달아줘.
에이전트가 제안한 값은 가정으로 두고, 확정 판정은 하지 마.
```

검사만 직접 실행할 수도 있다. Python 3.9 이상, 추가 설치는 필요 없다.

```bash
python skills/numeric-provenance/scripts/check_provenance.py design/
```

확정 판정 직전에는 `--fail-on-assumed`를 붙인다. `[가정]`이 하나라도 남으면 실패한다.

## 개발

```bash
python -m unittest discover -s tests
```

저장소 규칙은 [AGENTS.md](AGENTS.md)를 따른다.

## 조사 기록

- [AI 에이전트 프로젝트 수명주기 도구 조사 (2026-11)](docs/research/landscape-2026-11.md)
- [Claude Code Game Studios 분석](docs/research/claude-code-game-studios.md)
- [agentic-gamedev-skills 분석](docs/research/agentic-gamedev-skills.md)

참고한 외부 프로젝트와 고지는 [THIRD_PARTY.md](THIRD_PARTY.md)에 있다.
