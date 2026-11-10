# AGENTS.md

## 목적

게임 프로젝트를 기획부터 완성까지 관리하는 게임 설계 층 스킬을 만든다. 구조와 원칙은 `docs/architecture.md`를 따른다. 스킬은 특정 게임이 아니라 어떤 게임에나 쓰도록 설계하고, 시험 프로젝트는 동작 확인에만 쓴다.

## 저장소 규칙

- 스킬은 `skills/<skill-name>/SKILL.md`를 진입점으로 둔다. 이름은 소문자·숫자·하이픈.
- frontmatter의 `description`은 영어로, "무엇을 하는지 + 언제 쓰는지"를 함께 쓴다. 본문은 한국어.
- 긴 예시·체크리스트는 스킬 안 `references/`로 분리한다. Codex 표시 정보는 `agents/openai.yaml`.
- **파이썬 코드는 `skills/studio-data/scripts/studio_data/` 한 곳에만 둔다.** 실행은 `skills/studio-data/scripts/studio.py`의 하위 명령으로 한다. 다른 스킬에는 `scripts/`를 만들지 않고 절차 문서만 둔다.
- 새 데이터 종류는 `common.DATASET_KINDS`, `datasets.VALIDATORS`, `assets/viewer.html`의 `KINDS`에 함께 등록하고, 예시는 `skills/studio-data/assets/sample-project/`에 둔다.
- 도구는 Python 표준 라이브러리로 작성하고 파일은 UTF-8로 명시해 읽고 쓴다. bash 전용 도구를 추가하지 않는다.
- 스킬을 추가·삭제·이름 변경하면 `README.md`의 스킬 표를 함께 고친다.
- 외부 프로젝트의 문장이나 코드를 가져오면 `THIRD_PARTY.md`에 출처와 라이선스를 적는다.
- 실험 결과물이나 게임 프로젝트를 저장소 루트에 두지 않는다.

## 스킬 문서

- `SKILL.md`에는 늘 밟는 흐름과 원칙만 둔다. 드물게 일어나는 일(기준을 고칠 때, 컨셉을 되돌릴 때)의 순서는 `references/`에 두고, `SKILL.md`에서 "이럴 때 → 읽을 곳" 표로 가리킨다.
- 한 규칙은 한 곳에만 쓴다. 다른 문서는 링크만 둔다. 검사 코드의 조건과 예외는 그 코드 표에만 적는다.
- 이슈 번호와 날짜 같은 경위는 `docs/architecture.md`에 둔다. 스킬 문서에는 지금 할 일만 쓴다. 확인한 환경(버전, 권한 모드)처럼 한계로 알아야 하는 것은 그 기능을 맡은 스킬의 한 곳에 두고 다른 문서는 가리킨다.
- 고칠 때는 문장을 더하기 전에 지우거나 바꿀 문장부터 찾는다.
- 검사기 메시지가 문서를 가리키면 파일과 절 이름을 함께 적는다.

## 검증

변경을 마치기 전에 실행한다.

```bash
python3 -m unittest discover -s tests
```

Windows PowerShell은 `py -m unittest discover -s tests`.

- 검사기나 게이트를 추가하면 그것이 실제로 실패하는 경우를 테스트로 먼저 보인다.
- 실행하지 못한 검증은 실행하지 못했다고 보고한다.
