# 시스템 설계 형식

게임 프로젝트의 `design/systems.json` 한 파일에 시스템을 둔다. 검사: `python3 .claude/skills/studio-data/scripts/studio.py check .`(컨셉 데이터와 함께), 표: `… check . --table systems`, 보기: `… view .`.

```json
{
  "concept": "parry_tempo",
  "systems": [
    {
      "id": "tempo",
      "name": "템포",
      "intent": "패링 성공이 판의 속도를 올린다",
      "scope": "mvp",
      "pillars": ["용기에 대한 보상"],
      "mvp": ["템포 3단계"],
      "rules": [{ "id": "tempo_up", "text": "패링에 성공하면 템포가 한 단계 오른다" }],
      "depends_on": ["combat_input"],
      "status": "approved"
    }
  ]
}
```

## 최상위

아래에 없는 키는 오류다(`_`로 시작하는 키와 `note`는 메모로 둔다).

| 키 | 필수 | 뜻 |
|---|---|---|
| `concept` | 아니오 | 잇는 컨셉 id. 없으면 승인된 컨셉 하나다. 승인된 컨셉이 하나가 아니면 필요하다 |
| `systems` | 예 | 시스템 배열 |

## `systems`

아래에 없는 키는 오류다(`_`로 시작하는 키는 메모로 둔다).

| 키 | 필수 | 뜻 |
|---|---|---|
| `id` | 예 | 소문자·숫자·밑줄 |
| `name`, `intent`, `note` | 아니오 | 이름, 의도, 메모 |
| `scope` | 예 | `mvp`(이번에 만듦), `later`(나중), `out`(브리프가 뺀 것) |
| `foundation` | 아니오 | `true`면 기반 시스템이다. 브리프의 필러나 MVP를 직접 맡지 않지만 다른 시스템이 기댄다(플레이어 이동). 필러와 MVP 항목이 없어도 되고, 기대는 시스템이 없으면 경고한다 |
| `pillars` | 아니오 | 돕는 필러. 브리프 `pillars`의 `name` 그대로 |
| `mvp` | 아니오 | 맡는 MVP 항목. 브리프 `mvp`의 문구 그대로 |
| `out_of_scope` | 아니오 | 가리키는 범위 밖 항목. 브리프 `out_of_scope`의 문구 그대로 |
| `rules` | 아니오 | 규칙 `{id, text, note}` 배열. `id`는 시스템 안에서 겹치지 않는다 |
| `depends_on` | 아니오 | 먼저 있어야 하는 시스템 id 배열 |
| `status` | 아니오 | `proposed`, `approved`, `cut`. `cut`은 계산에서 뺀다 |
| `acknowledged` | 아니오 | 확인한 경고 `{코드: 이유}`나 `{코드: {대상: 이유}}`. 오류는 확인으로 끄지 못한다 |

시스템과 규칙은 설계 결정이라 `--fail-on-assumed`에 걸지 않는다.

## 계산

- **만드는 순서**: 의존이 없으면 1, 있으면 의존하는 시스템의 가장 큰 순서 + 1이다. 범위 밖 시스템과 순환에 걸리거나 매달린 시스템은 순서가 없다. 표는 순서, 범위, id 순이다.
- **필러와 MVP를 맡는다**: 범위가 `mvp`인 시스템만 센다. `later`로 미룬 시스템은 지금 만들 것을 맡지 못한다.

## 검사

| 코드 | 수준 | 조건 |
|---|---|---|
| `schema`, `duplicate_id` | 오류 | 형식 위반, 모르는 키, 시스템이나 규칙의 id 중복. 승인된 컨셉이 하나가 아닌데 `concept`이 없음 |
| `unknown_concept` | 오류 | 컨셉 데이터에 없는 컨셉 |
| `brief_missing` | 오류 | 컨셉에 브리프가 없음 |
| `unknown_pillar`, `unknown_mvp`, `unknown_out_of_scope` | 오류 | 브리프에 없는 문구 |
| `unknown_system` | 오류 | `depends_on`이 없는 시스템을 가리킴 |
| `cut_referenced` | 경고 | 삭제된 시스템에 의존함, 삭제된 컨셉에 이음. 되돌리며 `cut`한 컨셉이면 다음 컨셉을 고를 때까지 그대로 둔다 |
| `pillar_unserved` | 경고 | 범위가 `mvp`인 시스템이 맡지 않는 필러. 일부러 미룬 것이면 어느 시스템에서든 `{"pillar_unserved": {필러 이름: 이유}}`로 확인한다 |
| `mvp_unserved` | 경고 | 범위가 `mvp`인 시스템이 맡지 않는 MVP 항목. 확인은 `pillar_unserved`와 같다 |
| `out_of_scope_claimed` | 오류 | `out`이 아닌 시스템이 브리프의 범위 밖 항목을 맡거나, 이름·의도·규칙 글에 그 문구가 있음. 확인으로 끄지 못한다 |
| `scope_dependency` | 오류 | `mvp`가 `later`나 `out`에, `later`가 `out`에 의존함. 그대로면 만들 수 없다 |
| `dependency_cycle` | 오류 | 시스템이 서로 의존함. 순환을 이루는 시스템을 말한다 |
| `concept_not_approved` | 경고 | 승인되지 않은 컨셉에 이음. 되돌린 컨셉이면 다음 컨셉을 고를 때까지 그대로 둔다 |
| `foundation_unused` | 경고 | 기반 시스템인데 기대는 시스템이 없음 |
| `scope_mismatch` | 경고 | `mvp`인데 MVP 항목이 없음(기반 시스템 제외), `mvp`가 아닌데 MVP 항목을 맡음, `out`인데 범위 밖 항목이 없음 |
| `system_without_pillar` | 경고 | `out`이 아닌데 필러가 없음(기반 시스템 제외) |
| `system_without_rules` | 경고 | `out`이 아닌데 규칙이 없음 |

형식 오류로 빠진 시스템이 있으면 그 시스템에 대한 의존을 없는 시스템으로 말하지 않고, `pillar_unserved`와 `mvp_unserved`를 보지 않는다.

미확인(`INCOMPLETE`): 컨셉을 함께 읽지 않음, 컨셉 파일을 읽지 못함, 계산한 시스템이 하나도 없음.

`design/systems.json`은 내용과 상관없이 이 형식으로 읽는다. 키가 틀리면 형식 오류나 읽기 오류다. 다른 자리의 `systems.json`은 엔진이나 게임의 파일일 수 있어, 최상위 `concept`가 있거나 `scope`를 적은 항목이 있을 때만 이 형식으로 읽고 그 밖에는 건너뛰며 `check`와 뷰어가 알린다. 내용이 없거나 문법이 깨진 `systems.json`은 읽기 오류다. 시스템 설계 파일은 하나만 쓴다. 둘이면 뒤의 파일이 오류다.
