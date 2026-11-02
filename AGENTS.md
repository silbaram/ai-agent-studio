# AGENTS.md

## 목적

게임 프로젝트를 기획부터 완성까지 관리하는 게임 설계 층 스킬을 만든다. 구조와 원칙은 `docs/architecture.md`를 따른다.

## 저장소 규칙

- 스킬은 `skills/<skill-name>/SKILL.md`를 진입점으로 둔다. 이름은 소문자·숫자·하이픈.
- frontmatter의 `description`은 영어로, "무엇을 하는지 + 언제 쓰는지"를 함께 쓴다. 본문은 한국어.
- 긴 예시·체크리스트는 스킬 안 `references/`로 분리한다. 스크립트는 `scripts/`, Codex 표시 정보는 `agents/openai.yaml`.
- 도구는 Python 표준 라이브러리로 작성하고 파일은 UTF-8로 명시해 읽고 쓴다. bash 전용 도구를 추가하지 않는다.
- 스킬을 추가·삭제·이름 변경하면 `README.md`의 스킬 표를 함께 고친다.
- 외부 프로젝트의 문장이나 코드를 가져오면 `THIRD_PARTY.md`에 출처와 라이선스를 적는다.
- 실험 결과물이나 게임 프로젝트를 저장소 루트에 두지 않는다.

## 검증

변경을 마치기 전에 실행한다.

```bash
python -m unittest discover -s tests
```

- 검사기나 게이트를 추가하면 그것이 실제로 실패하는 경우를 테스트로 먼저 보인다.
- 실행하지 못한 검증은 실행하지 못했다고 보고한다.
