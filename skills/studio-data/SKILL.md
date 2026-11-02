---
name: studio-data
description: "Shared tooling for the game-design skills: one entry script (studio.py) and one Python package that validate concept records, items, permanent upgrades, and enemies, simulate roguelike meta-progression, check numeric provenance tags in design docs, and serve a read-only browser viewer that shows all of a project's design data with validation results. Use when viewing, checking, or simulating game design data, or when another skill in this repository tells you to run a check."
---

# 게임 설계 데이터 공용 도구

다른 스킬([concept-exploration](../concept-exploration/SKILL.md), [progression-economy](../progression-economy/SKILL.md), [numeric-provenance](../numeric-provenance/SKILL.md))은 절차만 담고, 실행하는 도구는 모두 이 스킬에 있다. 이 스킬을 다른 스킬과 같은 부모 폴더에 함께 설치한다.

## 실행

실행 파일은 `scripts/studio.py` 하나다. Python 3.9 이상, 추가 설치는 필요 없다. 아래 경로는 이 저장소 기준이며, 게임 프로젝트에 설치하면 `.claude/skills/studio-data/scripts/studio.py`(Claude Code) 또는 `.agents/skills/studio-data/scripts/studio.py`(Codex)가 된다.

| 명령 | 하는 일 |
|---|---|
| `python skills/studio-data/scripts/studio.py view .` | 프로젝트의 설계 데이터를 브라우저에서 본다 (읽기 전용, 자동 갱신) |
| `python skills/studio-data/scripts/studio.py check .` | 컨셉·아이템·영구 강화·적 데이터를 한 번에 검사한다 |
| `python skills/studio-data/scripts/studio.py simulate data/meta.json` | 메타 성장을 추상 모델로 시뮬레이션한다 |
| `python skills/studio-data/scripts/studio.py provenance design/` | 기획 문서(md)의 수치 출처 태그를 검사한다 |

옵션은 `studio.py <명령> --help`로 본다. 종료 코드는 0 통과, 1 오류(또는 `--strict` 경고, `--fail-on-assumed` 가정), 2 사용법 오류(경로 없음, 읽을 수 없는 파일, 데이터 없음, 설정 오류)다.

## 프로젝트 배치

```
<게임 프로젝트>/
├─ design/
│  └─ concepts.json   컨셉 후보와 선택한 컨셉의 브리프
└─ data/
   ├─ items.json      아이템, 드랍 테이블
   ├─ upgrades.json   영구 강화
   ├─ enemies.json    적
   └─ meta.json       시뮬레이터 설정 (upgrades.json을 가리킴)
```

`view`와 `check`에 폴더를 주면 그 폴더와 바로 아래 `design/`, `data/`에서 데이터 파일을 찾는다. 종류는 JSON 최상위 키(`concepts` / `items` / `upgrades` / `enemies`)로 판단한다. 키의 형식이 틀려도 그 종류로 보고 형식 오류를 보고한다(건너뛰지 않는다). 시뮬레이터 설정과 관계없는 JSON은 건너뛴다. 파일을 직접 줄 수도 있다. 적의 드랍 테이블은 함께 읽은 아이템 데이터로 확인한다.

예시 프로젝트: `assets/sample-project/` (실제 기획이 아니다).

## 뷰어

- **서버 모드(기본)**: `studio.py view <폴더>`. 화면이 1.5초마다 원본을 다시 읽고, 내용이 바뀌었을 때만 다시 검사한다. 한 파일의 형식 때문에 검사기가 처리하지 못해도 그 파일만 오류로 표시되고 나머지는 계속 보인다. 탭은 컨셉, 아이템, 영구 강화, 적. 컨셉 탭은 제약, 선택한 컨셉의 브리프, 후보 비교표를 보여 준다. 문서를 생성하지 않으므로 동기화할 것이 없다. 기본으로 127.0.0.1에서만 열린다. 터미널을 닫으면 뷰어도 꺼진다.
- **파일 모드(보조)**: `assets/viewer.html`을 직접 열고 '불러오기'로 JSON을 고른다. 원본에 적힌 값만 보여 주며 검사·점수·확률 계산은 하지 않는다. 검사 규칙은 파이썬에만 있고 JavaScript로 복제하지 않는다.

## 코드 구조

모든 파이썬 코드는 `scripts/studio_data/` 패키지에 있다.

| 모듈 | 역할 |
|---|---|
| `common` | 읽기, 종류 판별, 공통 필드(id·상태·출처) 검사 |
| `datasets` | 파일 찾기(각 파일은 한 번만 읽음) → 종류별 검사, 파일 간 참조 확인, 검사기 예외를 파일 단위로 격리 |
| `concepts`, `items`, `upgrades`, `enemies` | 종류별 검사 규칙 |
| `meta_sim` | 메타 성장 시뮬레이터 |
| `provenance` | md 수치 출처 태그 검사 |
| `viewer` | 뷰어 서버 (내용이 바뀔 때만 다시 검사) |
| `cli` | `studio.py`의 하위 명령 |

새 데이터 종류를 추가할 때는 `common.DATASET_KINDS`, `datasets.VALIDATORS`, `assets/viewer.html`의 `KINDS`에 함께 등록한다.
