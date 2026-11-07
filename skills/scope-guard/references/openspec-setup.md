# OpenSpec 설치

게임 프로젝트에 OpenSpec을 넣고 설계 층에 잇는다. 시험한 판은 1.16.0이다.

Node.js 22.12 이상이 필요하다.

```bash
npm install -g @fission-ai/openspec@latest
```

사용 통계가 기본으로 켜져 있다. 명령 이름과 판만 보낸다고 하지만, 끄려면 셸 설정에 넣는다.

```bash
export OPENSPEC_TELEMETRY=0
```

프로젝트 폴더에서 초기화한다. Codex를 쓰면 `--tools codex`다.

```bash
openspec init --tools claude --language ko
```

`--language ko`는 문서를 한국어로 쓰게 한다. 제목(`## ADDED Requirements`, `### Requirement:`)과 `SHALL`, `WHEN`, `THEN`은 영어로 둔다. 도구의 형식 검사가 이 글자들을 찾는다.

`openspec/config.yaml`의 `context:` 블록에서 `init`이 적은 줄 아래에 이것을 더한다. 들여쓰기를 맞춘다. `<컨셉 id>`와 수치 폴더는 게임에 맞춘다.

```yaml
  이 게임의 기준은 design/concepts.json의 승인된 컨셉(<컨셉 id>) 브리프와 design/systems.json이다.
  변경을 만들면 바로 python3 .claude/skills/studio-data/scripts/studio.py scope --link <변경> <시스템 id>로 시스템에 잇는다.
  브리프의 out_of_scope에 든 것은 만들지 않는다. 요청이 그렇다면 멈추고 사용자에게 묻는다.
  명세는 design/systems.json의 규칙 id를 적고 뜻을 길게 옮기지 않는다.
  수치의 원본은 data/의 파일이다. 명세에 수치를 베끼지 않고 파일을 가리킨다.
  태스크를 시작하기 전과 변경을 닫기 전에 python3 .claude/skills/studio-data/scripts/studio.py scope를 돌린다.
  요구사항 설명마다 SHALL이나 MUST를 한 번 넣는다. 한국어 문장이면 끝에 (SHALL)을 붙인다. 예: 보석은 숙성 시간이 지나면 다음 단계로 익어야 한다(SHALL).
  사용자가 한 요청에서 /opsx:propose와 /opsx:apply(또는 /opsx:update와 /opsx:apply)를 이름으로 함께 시켰으면 그 요청을 확인으로 보고 이어서 한다. 범위를 넓히는 일은 따로 묻는다.
```

마지막 두 줄은 OpenSpec 스킬의 기본 동작을 이 프로젝트에 맞게 바꾼다. 기본은 계획을 쓴 뒤 구현 요청을 다시 기다리고, 고칠 때마다 확인을 받는다. 사용자가 두 단계를 한 요청에 적었는데 기다리면 사용자가 없는 실행(`claude -p`)은 일을 끝내지 못한다. 한 단계씩 확인받고 싶으면 이 줄을 넣지 않는다. 이 줄이 OpenSpec 스킬의 기본 동작보다 앞서는지는 아직 실제 세션으로 확인하지 않았다. 확인 전에 쓴 시험 세션은 이 줄 없이도 사용자의 지시를 따라 이어서 했다. `--strict`는 요구사항마다 `SHALL`이나 `MUST`가 없으면 실패하므로 첫 줄은 그대로 둔다.

훅을 설치한다. 스킬을 다시 설치한 뒤에도 실행한다.

```bash
python3 .claude/skills/studio-data/scripts/studio.py setup claude .
```

Claude Code를 다시 시작하면 적용된다.

## OpenSpec의 함정

- `validate`를 통과해도 `archive`가 실패할 수 있다. 없는 요구사항의 `MODIFIED`는 `validate`가 INFO로만 알린다.
- `archive --yes`는 미완료 태스크가 있어도 병합한다. 터미널이 없는 에이전트 실행에서는 `--yes` 없이 멈추므로 CLI 대신 `/opsx:archive`로 닫는다.
- `SHALL`은 글자 검사다. 한국어 문장 끝에 `(SHALL)`을 붙이면 통과한다.
- 변경 삭제 명령이 없다. 폴더를 지운다.
- 보관한 변경은 `openspec show`로 읽지 못한다. `openspec/changes/archive/`의 파일을 읽는다.
