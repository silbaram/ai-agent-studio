# AI Agent Studio

AI 에이전트와 함께 게임에 등장하는 요소들의 **밸런스를 기획**하는 스킬과 도구를 만든다.
아이템 종류·스탯, 강화, 합성, 몹 종류·스탯, 재화와 가격을 단일 원본 데이터로 두고, 에이전트가 감으로 정한 숫자가 검증된 숫자처럼 쓰이지 않도록 계산과 출처 태그로 확인한다.

> 초기 단계다. 구조·원칙·로드맵은 [설계 문서](docs/architecture.md)에 있다. 개발 과정 관리(일정, 범위, 수명주기, 그래픽 인계)는 다루지 않는다.

## 지금 할 수 있는 것과 앞으로

| 지금 | 다음 ([로드맵](docs/architecture.md#로드맵)) |
| --- | --- |
| 아이템·영구 강화·적 데이터의 단일 원본, 티어 역전·열위·드랍 천장·강화 사슬·위협도 검사, 메타 성장 시뮬레이션, 수치 출처 검사, 뷰어 | 공통 스탯과 전투 공식으로 처치 시간·버티는 타격 수 계산, 예산 곡선에서 표 제안, 아이템 강화와 합성, 재화 흐름 |

## 포함된 스킬

| 스킬 | 하는 일 |
| --- | --- |
| [studio-data](skills/studio-data/SKILL.md) | **공용 도구.** 실행 파일 `studio.py` 하나로 검사(check)·뷰어(view)·시뮬레이션(simulate)·수치 출처 검사(provenance)·Claude Code 연결(setup). 다른 스킬과 함께 설치 |
| [progression-economy](skills/progression-economy/SKILL.md) | 아이템·영구 강화·적 데이터의 단일 원본 관리와 뷰어, 티어 역전·완전 열위·드랍 천장·강화 사슬·적 위협도 진행 검사, 로그라이크 메타 성장 시뮬레이션 |
| [numeric-provenance](skills/numeric-provenance/SKILL.md) | 기획 수치를 `[가정]` / `[계산: 출처]` / `[측정: 출처]`로 표시하고, 확정 판정 전에 스크립트로 검사 |
| [concept-exploration](skills/concept-exploration/SKILL.md) | *보류.* 막연한 방향을 구조가 다른 게임 가설로 펼치고, 단순 전략으로 반증하고, 고른 안을 브리프로 정리 |
| [playtest-verdict](skills/playtest-verdict/SKILL.md) | *보류.* 플레이 기록을 데이터로 남기고, 읽기 전용 판정 에이전트가 기록만 보고 가설을 판정, 측정값을 `[측정]`으로 올림. 밸런스 수치를 실측으로 보정할 때 쓴다 |

*보류*: 고치지만 넓히지 않는다. 밸런스 기획과 직접 관계없는 단계라 [설계 문서](docs/architecture.md#보류-지우지-않고-넓히지-않는다)에 이유를 적었다.

첫 대상은 **액션 로그라이크 + 메타 성장형** 게임이다. 데이터는 JSON/CSV로 다뤄 Godot·Unity·Unreal·Roblox 어디에도 묶이지 않는다.

## 설치

**스킬을 사용할 게임 프로젝트 폴더에서** 실행한다. 다섯 스킬을 모두 설치한다. `studio-data`가 빠지면 다른 스킬의 검사와 뷰어가 동작하지 않는다.

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
- Node.js 없이 설치하려면 이 저장소의 `skills/` 안 다섯 폴더를 위 표의 설치 위치로 그대로 복사한다.

Claude Code는 설치한 뒤 한 번 더 실행한다. `npx skills`는 스킬만 설치하므로, 판정 에이전트와 훅은 이 명령이 게임 프로젝트의 `.claude/agents/`와 `.claude/settings.json`에 넣는다. 스킬을 다시 설치한 뒤에도 다시 실행한다. 자세한 내용은 [studio-data의 Claude Code 연결](skills/studio-data/SKILL.md#claude-code-연결).

```bash
python3 .claude/skills/studio-data/scripts/studio.py setup claude .
```

설치 후 도구는 설치 위치에서 실행한다. 예를 들어 Claude Code에서 게임 프로젝트의 데이터를 뷰어로 보려면 게임 프로젝트 폴더에서 다음을 실행한다(Windows는 아래 표 참고).

```bash
python3 .claude/skills/studio-data/scripts/studio.py view .
```

설치 직후처럼 데이터 파일이 아직 없어도 뷰어는 열린다. 화면에 지켜보는 위치가 안내되고, 컨셉 탐색 등으로 `design/concepts.json` 같은 파일이 생기면 새로고침 없이 자동으로 나타난다.

### Windows에서 쓸 때 (PowerShell과 WSL)

Windows에서는 어느 터미널을 쓰는지에 따라 명령이 다르다. 프롬프트가 `PS C:\...>`이면 PowerShell, `사용자@PC이름:/mnt/c/...$`이면 WSL(Windows 안의 리눅스)이다.

| | PowerShell | WSL |
| --- | --- | --- |
| Python 실행 | `py` | `python3` |
| 경로 구분자 | `\` (`/`도 대체로 된다) | `/`만. `\`는 경로로 읽히지 않는다 |
| Python이 없을 때 | [python.org](https://www.python.org/downloads/)에서 설치 | `sudo apt install python3` |
| 뷰어 열기 | 브라우저가 자동으로 열린다 | 자동으로 열리지 않을 수 있다. 아래처럼 `--no-browser`로 켜고 Windows 브라우저에서 `http://localhost:8765/`를 연다 |

PowerShell:

```bash
py .claude\skills\studio-data\scripts\studio.py view .
```

WSL:

```bash
python3 .claude/skills/studio-data/scripts/studio.py view . --no-browser
```

- WSL2는 기본 설정에서 `localhost`를 Windows로 전달하므로 Windows 브라우저에서 바로 열린다. 열리지 않으면 `--port`로 다른 포트를 지정해 본다.
- 설치(`npx skills add`)와 실행은 같은 쪽(PowerShell 또는 WSL)에서 하는 것이 헷갈리지 않는다. 같은 폴더라도 PowerShell에서는 `C:\Users\...`, WSL에서는 `/mnt/c/Users/...`로 보인다.
- Claude Code나 Codex를 WSL에서 실행했다면, 에이전트가 도구를 실행할 때도 `python3`과 `/` 경로를 쓴다.

## 사용 예시

밸런스 데이터를 다루는 예시가 먼저, 보류한 스킬의 예시가 뒤에 있다.

```text
$progression-economy로 2구역에 나올 정예 적을 하나 추가해줘.
제안 상태로 넣고 검사 경고가 있으면 알려줘. 바뀐 행만 보여줘.
```

```text
$numeric-provenance로 design/economy.md의 모든 수치에 출처 태그를 달아줘.
에이전트가 제안한 값은 가정으로 두고, 확정 판정은 하지 마.
```

```text
$concept-exploration으로 액션 로그라이크에 성장 요소가 있는 게임 컨셉을 찾아줘.
1인 개발, 한 판 20분 안팎. 재미 점수로 고르지 말고 구조가 다른 후보를 비교표로 보여줘.
```

```text
$playtest-verdict로 오늘 플레이한 것을 기록해줘. 나, 친구 2명이 각각 3판씩 했고 빌드는 지금 커밋이야.
관찰값은 내가 말한 것과 로그 파일에 있는 것만 적고, 판정은 studio-judge에게 맡겨서 제안만 보여줘.
```

도구는 모두 `studio.py` 하나로 실행한다. 아래는 이 저장소를 받은 폴더에서 예시 프로젝트로 바로 해 보는 명령이다. 게임 프로젝트에 설치했다면 경로 앞부분을 설치 위치(`.claude/skills/...` 또는 `.agents/skills/...`)로 바꾼다. Windows PowerShell은 `python3` 대신 `py`.

스킬 문서(SKILL.md)의 명령은 게임 프로젝트에 Claude Code로 설치한 기준(`python3 .claude/skills/studio-data/scripts/studio.py`)으로 적혀 있다.

```bash
python3 skills/studio-data/scripts/studio.py view skills/studio-data/assets/sample-project
python3 skills/studio-data/scripts/studio.py check skills/studio-data/assets/sample-project --table
python3 skills/studio-data/scripts/studio.py simulate skills/studio-data/assets/sample-project/data/meta.json
python3 skills/studio-data/scripts/studio.py provenance design/
```

`view`는 프로젝트의 `design/`·`data/`에 있는 컨셉·아이템·영구 강화·적·플레이 기록을 브라우저에서 탭으로 보여 주는 읽기 전용 뷰어다. 문서를 따로 생성하지 않으므로 동기화할 것이 없고, 원본을 고치면 화면이 자동으로 갱신된다. Python 없이 `skills/studio-data/assets/viewer.html`을 직접 열어 '불러오기'로 볼 수도 있지만, 그때는 검사·계산 없이 원본 값만 보인다.

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
