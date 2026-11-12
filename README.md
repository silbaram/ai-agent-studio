# AI Agent Studio

AI 에이전트와 함께 게임 프로젝트를 기획부터 완성까지 관리하기 위한 스킬과 도구를 만든다.
개발이 처음 의도에서 벗어나지 않도록 수치·판정·범위를 증거와 스크립트로 통제하는 것이 목표다.

> 구조·원칙·로드맵은 [설계 문서](docs/architecture.md)에 있다. 컨셉부터 밸런스 기획, 레벨 설계, 재미 검증, OpenSpec 연결까지 로드맵의 0~5단계를 1차로 마쳤고, 실시간 액션 로그라이크(새로 만드는 게임)와 턴제 택틱스(이미 만든 게임) 두 시험 프로젝트에서 확인했다. 그래픽 층과의 연결은 보류 중이다.

처음이면 [쉬운 안내](docs/guide.md)부터 읽는다. 무엇을 막으려는 도구인지, 큰 흐름, 스킬마다 쉬운 설명, 꼭 알아 둘 말, 처음 따라 하기가 있다.

## 층 구조

| 층 | 담당 |
| --- | --- |
| 수명주기 뼈대 (기획 → 설계 → 태스크 → 구현 → 검증) | [OpenSpec](https://github.com/Fission-AI/OpenSpec). `scope-guard`로 설계 층에 잇는다 |
| 게임 설계 (컨셉·시스템·레벨·아이템·경제·밸런스 기획·재미 검증) | **이 저장소** |
| 그래픽 (도트·메시·VFX) | [game-art-skills](https://github.com/silbaram/game-art-skills) |

## 포함된 스킬

| 스킬 | 하는 일 |
| --- | --- |
| [studio-data](skills/studio-data/SKILL.md) | **공용 도구.** 실행 파일 `studio.py` 하나로 검사(check)·뷰어(view)·시뮬레이션(simulate)·플레이 기록 보정(calibrate)·수치 출처 검사(provenance)·Claude Code 연결(setup). 다른 스킬과 함께 설치 |
| [concept-exploration](skills/concept-exploration/SKILL.md) | 막연한 방향을 구조가 다른 게임 가설로 펼치고, 단순 전략으로 반증하고, 고른 안을 필러·가설·최소 프로토타입이 있는 브리프로 정리 |
| [system-design](skills/system-design/SKILL.md) | 게임의 시스템과 규칙, 의존 관계를 적어 브리프의 필러·MVP·범위 밖에 잇고, 맡는 시스템이 없는 것과 범위 이탈, 의존 순환, 만드는 순서를 찾음 |
| [scope-guard](skills/scope-guard/SKILL.md) | OpenSpec 변경을 브리프와 시스템 설계에 잇고, MVP 밖의 일과 낡은 명세를 찾아 훅으로 막으며, 범위를 넓히는 편집은 사용자에게 묻기 |
| [numeric-provenance](skills/numeric-provenance/SKILL.md) | 기획 수치를 `[가정]` / `[계산: 출처]` / `[측정: 출처]`로 표시하고, 확정 판정 전에 스크립트로 검사 |
| [progression-economy](skills/progression-economy/SKILL.md) | 아이템·영구 강화·적 데이터의 단일 원본 관리와 뷰어(레벨마다 강해지는 적은 한 행과 성장으로), 티어 역전·완전 열위·드랍 천장·강화 사슬·적 위협도 진행 검사, 로그라이크 메타 성장 시뮬레이션 |
| [run-growth](skills/run-growth/SKILL.md) | 레벨업 선택지와 빌드 정책(우선순위·고르게)으로 단계별로 얻는 스탯을 시뮬레이션해 전투 계산에 더하고, 빌드끼리 처치·버팀을 비교해 모든 곳에서 밀리는 빌드를 찾음. 경험치 곡선을 적으면 단계별 도달 레벨을 가정과 견줌 |
| [stat-budget](skills/stat-budget/SKILL.md) | 티어·구역별 스탯 예산 곡선과 원가로 아이템·적의 넘침·모자람을 찾고, 원형(아키타입)으로 새 항목 초안을 만들고, 전투 공식으로 스탯 원가를 제안 |
| [crafting-balance](skills/crafting-balance/SKILL.md) | 강화 단계별 기대 비용·시도(실패 시 유지·하락·파괴), 합성의 가치 비율과 무작위 합성의 특정 결과까지 기대 횟수, 아이템 증식 고리, 얻을 수 없는 아이템 |
| [economy-flow](skills/economy-flow/SKILL.md) | 단계별 수입(처치 보상·드랍 판매·기타)과 구매 계획(아이템·강화·합성·영구 강화 가격)을 이어 구매 시점, 메타 재화의 판 수, 판 끝에 남는 재화를 계산 |
| [combat-balance](skills/combat-balance/SKILL.md) | 플레이어·아이템·강화·적을 하나의 스탯과 방어 공식(고정값·비율·레벨 비율·퍼센트 중 선택, 방어 무시)으로 잇고, 단계·적마다 처치·버팀 타수와 시간을 계산해 목표 이탈을 찾음. 단계마다 다른 목표와 직업·무기별 변형 단계도 다룸 |
| [level-design](skills/level-design/SKILL.md) | 레벨을 조우(방·웨이브)의 순서로 적고(순서를 고르는 스테이지는 갈래로), 조우의 위협도를 곡선 예산과 비교하며, 놓은 적을 전투 단계와, 처치 수와 시각을 재화 흐름과 맞춰 보고, 쉬는 곳·보상 사이의 부담과 강한 조우의 연속을 찾고, 레벨마다 그레이박스 확인 목록을 플레이 기록과 이음 |
| [playtest-verdict](skills/playtest-verdict/SKILL.md) | 프로토타입 플레이를 데이터로 기록하고, 읽기 전용 판정 에이전트가 기록만 보고 가설을 버팀·틀림·모름으로 판정, 측정값을 세션 출처와 함께 `[측정]`으로 올림. 봇이 돈 판은 따로 표시해 판정과 측정에서 뺌 |

특정 장르를 전제하지 않는다. 데이터는 JSON/CSV로 다뤄 Godot·Unity·Unreal·Roblox·웹 어디에도 묶이지 않는다. 새로 시작하는 게임도, 이미 만들고 있는 게임도 쓸 수 있다. 이미 만든 게임은 컨셉 후보를 만들지 않고 지금 게임을 브리프로 적는 데서 시작한다.

## 설치

**스킬을 사용할 게임 프로젝트 폴더에서** 실행한다. 열세 스킬을 모두 설치한다. `studio-data`가 빠지면 다른 스킬의 검사와 뷰어가 동작하지 않는다.

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
- Node.js 없이 설치하려면 이 저장소의 `skills/` 안 열세 폴더를 위 표의 설치 위치로 그대로 복사한다.

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

보통 순서: 컨셉 탐색 → 프로토타입 플레이와 가설 판정 → 데이터·수치 관리.

```text
$concept-exploration으로 액션 로그라이크에 성장 요소가 있는 게임 컨셉을 찾아줘.
1인 개발, 한 판 20분 안팎. 재미 점수로 고르지 말고 구조가 다른 후보를 비교표로 보여줘.
```

이미 만들고 있는 게임이면 이렇게 시작한다.

```text
$concept-exploration으로 지금 만들고 있는 이 게임을 정리해줘. 새 후보는 만들지 말고,
게임 코드에 흩어진 수치를 데이터 파일로 옮기는 방법도 제안해줘.
```

```text
$numeric-provenance로 design/economy.md의 모든 수치에 출처 태그를 달아줘.
에이전트가 제안한 값은 가정으로 두고, 확정 판정은 하지 마.
```

```text
$playtest-verdict로 오늘 플레이한 것을 기록해줘. 나, 친구 2명이 각각 3판씩 했고 빌드는 지금 커밋이야.
관찰값은 내가 말한 것과 로그 파일에 있는 것만 적고, 판정은 studio-judge에게 맡겨서 제안만 보여줘.
```

```text
$combat-balance로 구역마다 기준 장비를 정하고, 일반·정예·보스를 몇 대에 잡고 몇 대 맞으면 죽는지 표로 보여줘.
방어 공식은 이 게임에 맞는 형태를 추천하고 이유를 말해줘. 목표 범위를 벗어난 칸만 따로 짚어줘.
```

```text
$stat-budget으로 아이템 티어별 예산 곡선을 지금 데이터에 맞춰 제안하고, 곡선을 벗어난 아이템을 알려줘.
그다음 티어 3 공속 무기 초안을 하나 만들어서 제안 상태로 넣어줘. 원가 제안과 지금 원가가 크게 다르면 짚어줘.
```

```text
$crafting-balance로 무기 강화 +1~+5를 설계해줘. +4부터는 실패하면 한 단계 떨어지게 하고, 단계별 기대 비용 표를 보여줘.
1티어 무기 2개를 합쳐 2티어 무작위 하나를 주는 합성도 넣고, 손해인지와 특정 무기를 얻기까지 평균 몇 번인지 알려줘.
```

```text
$economy-flow로 구역마다 평범하게 깼을 때의 골드 수입을 정리하고, 철검 구입과 무기 +3 강화를 언제 할 수 있는지 보여줘.
영구 강화 2단계를 몇 번째 판에 사는지도 알려주고, 판 끝에 골드가 너무 남으면 짚어줘.
```

```text
$level-design으로 구역 1을 방 순서로 구성해줘. 평범한 방의 위협도를 기준으로 예산 곡선을 제안하고,
예산을 벗어난 방과 재화 흐름의 처치 수와 어긋나는 적을 짚어줘.
```

```text
$run-growth로 레벨업 선택지 6개와 빌드 3개(공격 위주, 버티기, 고르게)를 정의하고,
구역마다 빌드별로 정예와 보스를 몇 대에 잡는지 비교해줘. 모든 곳에서 밀리는 빌드나 아무도 안 고르는 선택지가 있으면 알려줘.
```

```text
$progression-economy로 2구역에 나올 정예 적을 하나 추가해줘.
제안 상태로 넣고 검사 경고가 있으면 알려줘. 바뀐 행만 보여줘.
```

도구는 모두 `studio.py` 하나로 실행한다. 아래는 이 저장소를 받은 폴더에서 예시 프로젝트로 바로 해 보는 명령이다. 게임 프로젝트에 설치했다면 경로 앞부분을 설치 위치(`.claude/skills/...` 또는 `.agents/skills/...`)로 바꾼다. Windows PowerShell은 `python3` 대신 `py`.

스킬 문서(SKILL.md)의 명령은 게임 프로젝트에 Claude Code로 설치한 기준(`python3 .claude/skills/studio-data/scripts/studio.py`)으로 적혀 있다.

```bash
python3 skills/studio-data/scripts/studio.py view skills/studio-data/assets/sample-project
python3 skills/studio-data/scripts/studio.py check skills/studio-data/assets/sample-project --table
python3 skills/studio-data/scripts/studio.py simulate skills/studio-data/assets/sample-project/data/meta.json
python3 skills/studio-data/scripts/studio.py simulate skills/studio-data/assets/sample-project/data/meta_combat.json
python3 skills/studio-data/scripts/studio.py calibrate skills/studio-data/assets/sample-project/data/meta_combat.json
python3 skills/studio-data/scripts/studio.py provenance design/
```

`view`는 프로젝트의 `design/`·`data/`에 있는 컨셉·시스템 설계·아이템·영구 강화·적·전투 계산·판 안 성장·스탯 예산·강화·합성·재화 흐름·레벨 구성·플레이 기록을 브라우저에서 탭으로 보여 주는 읽기 전용 뷰어다. 문서를 따로 생성하지 않으므로 동기화할 것이 없고, 원본을 고치면 화면이 자동으로 갱신된다. Python 없이 `skills/studio-data/assets/viewer.html`을 직접 열어 '불러오기'로 볼 수도 있지만, 그때는 검사·계산 없이 원본 값만 보인다.

확정 판정 직전에는 `check`와 `provenance`에 `--fail-on-assumed`를 붙인다. 가정인 수치가 하나라도 남으면 실패한다.
시뮬레이터는 추상 모델(`meta.json`)과 전투 계산 모델(`meta_combat.json`: 전투 계산·판 안 성장·재화 흐름 데이터로 판을 돌린다)이 있다. 어느 쪽이든 결과는 가정 아래의 계산값이며 실제 난이도나 재미 판정이 아니다.

## 개발

```bash
python3 -m unittest discover -s tests
```

저장소 규칙은 [AGENTS.md](AGENTS.md)를 따른다.

## 조사 기록

- [AI 에이전트 프로젝트 수명주기 도구 조사 (2026-11)](docs/research/landscape-2026-11.md)
- [Claude Code Game Studios 분석](docs/research/claude-code-game-studios.md)
- [agentic-gamedev-skills 분석](docs/research/agentic-gamedev-skills.md)
- [방어 공식 조사 (2026-11)](docs/research/defense-formulas-2026-11.md)

참고한 외부 프로젝트와 고지는 [THIRD_PARTY.md](THIRD_PARTY.md)에 있다.
