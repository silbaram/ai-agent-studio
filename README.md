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
| [studio-data](skills/studio-data/SKILL.md) | **공용 도구.** 실행 파일 `studio.py` 하나로 검사(check)·뷰어(view)·시뮬레이션(simulate)·수치 출처 검사(provenance). 다른 스킬과 함께 설치 |
| [concept-exploration](skills/concept-exploration/SKILL.md) | 막연한 방향을 구조가 다른 게임 가설로 펼치고, 단순 전략으로 반증하고, 고른 안을 필러·가설·최소 프로토타입이 있는 브리프로 정리 |
| [numeric-provenance](skills/numeric-provenance/SKILL.md) | 기획 수치를 `[가정]` / `[계산: 출처]` / `[측정: 출처]`로 표시하고, 확정 판정 전에 스크립트로 검사 |
| [progression-economy](skills/progression-economy/SKILL.md) | 아이템·영구 강화·적 데이터의 단일 원본 관리와 뷰어, 티어 역전·완전 열위·드랍 천장·강화 사슬·적 위협도 진행 검사, 로그라이크 메타 성장 시뮬레이션 |

첫 대상은 **액션 로그라이크 + 메타 성장형** 게임이다. 데이터는 JSON/CSV로 다뤄 Godot·Unity·Unreal·Roblox 어디에도 묶이지 않는다.

## 설치

**스킬을 사용할 게임 프로젝트 폴더에서** 실행한다. 네 스킬을 모두 설치한다. `studio-data`가 빠지면 다른 스킬의 검사와 뷰어가 동작하지 않는다.

필요한 것:

- [Node.js](https://nodejs.org/): 설치 명령(`npx skills`)에만 쓴다.
- Python 3.9 이상: 설치 후 도구(`studio.py`)를 실행할 때 쓴다. 추가 패키지는 필요 없다.

사용하는 호스트의 명령 하나만 실행한다.

Claude Code:

```bash
npx skills add silbaram/ai-agent-studio --skill '*' --agent claude-code --copy
```

Codex:

```bash
npx skills add silbaram/ai-agent-studio --skill '*' --agent codex --copy
```

| 호스트 | 설치 위치 (게임 프로젝트 기준) |
| --- | --- |
| Claude Code | `.claude/skills/<스킬 이름>/` |
| Codex | `.agents/skills/<스킬 이름>/` |

- `--copy`는 독립 사본을 만든다. 이 저장소가 갱신돼도 설치본은 자동으로 바뀌지 않는다.
- **갱신하려면 같은 명령을 다시 실행한다.** 기존 설치본을 덮어쓰므로, 설치본을 직접 고쳤다면 그 내용은 사라진다. 고칠 것이 있으면 설치본이 아니라 이 저장소를 고친다.
- 받아 둔 이 저장소의 로컬 사본(작업 중인 브랜치 등)으로 설치하려면 `silbaram/ai-agent-studio` 대신 그 폴더 경로를 쓴다.
- Node.js 없이 설치하려면 이 저장소의 `skills/` 안 네 폴더를 위 표의 설치 위치로 그대로 복사한다.

설치 후 도구는 설치 위치에서 실행한다. 예를 들어 Claude Code에서 게임 프로젝트의 데이터를 뷰어로 보려면 게임 프로젝트 폴더에서 다음을 실행한다(Windows는 `python` 대신 `py`).

```bash
python .claude/skills/studio-data/scripts/studio.py view .
```

뷰어는 프로젝트의 `design/`·`data/`에 데이터 파일이 하나 이상 있어야 열린다. 설치 직후에는 아직 파일이 없으므로, 컨셉 탐색 등으로 `design/concepts.json` 같은 파일이 생긴 뒤 실행한다.

## 사용 예시

보통 순서: 컨셉 탐색 → 프로토타입으로 가설 확인 → 데이터·수치 관리.

```text
$concept-exploration으로 액션 로그라이크에 성장 요소가 있는 게임 컨셉을 찾아줘.
1인 개발, 한 판 20분 안팎. 재미 점수로 고르지 말고 구조가 다른 후보를 비교표로 보여줘.
```

```text
$numeric-provenance로 design/economy.md의 모든 수치에 출처 태그를 달아줘.
에이전트가 제안한 값은 가정으로 두고, 확정 판정은 하지 마.
```

```text
$progression-economy로 2구역에 나올 정예 적을 하나 추가해줘.
제안 상태로 넣고 검사 경고가 있으면 알려줘. 바뀐 행만 보여줘.
```

도구는 모두 `studio.py` 하나로 실행한다. 아래는 이 저장소를 받은 폴더에서 예시 프로젝트로 바로 해 보는 명령이다. 게임 프로젝트에 설치했다면 경로 앞부분을 설치 위치(`.claude/skills/...` 또는 `.agents/skills/...`)로 바꾼다.

```bash
python skills/studio-data/scripts/studio.py view skills/studio-data/assets/sample-project
python skills/studio-data/scripts/studio.py check skills/studio-data/assets/sample-project --table
python skills/studio-data/scripts/studio.py simulate skills/studio-data/assets/sample-project/data/meta.json
python skills/studio-data/scripts/studio.py provenance design/
```

`view`는 프로젝트의 `design/`·`data/`에 있는 컨셉·아이템·영구 강화·적 데이터를 브라우저에서 탭으로 보여 주는 읽기 전용 뷰어다. 문서를 따로 생성하지 않으므로 동기화할 것이 없고, 원본을 고치면 화면이 자동으로 갱신된다. Python 없이 `skills/studio-data/assets/viewer.html`을 직접 열어 '불러오기'로 볼 수도 있지만, 그때는 검사·계산 없이 원본 값만 보인다.

확정 판정 직전에는 `check`와 `provenance`에 `--fail-on-assumed`를 붙인다. 가정인 수치가 하나라도 남으면 실패한다.
시뮬레이터는 추상 모델이다. 결과는 경제·성장 곡선의 구조를 보는 용도이며 실제 난이도나 재미 판정이 아니다.

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
