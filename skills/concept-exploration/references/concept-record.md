# 컨셉 기록 형식

게임 프로젝트의 `design/concepts.json` 한 파일에 모든 후보와 판단을 남긴다. 기획 문서(md)는 컨셉을 `id`로만 언급한다. 검사: `python3 .claude/skills/studio-data/scripts/studio.py check design/`, 보기: `python3 .claude/skills/studio-data/scripts/studio.py view .`.

## 최상위

```json
{
  "constraints": {
    "platform": "PC, 키보드·패드",
    "session": "한 판 15~25분",
    "feeling": "아슬아슬하게 살아남는 긴장",
    "team": "1인, 6개월",
    "engines": ["Godot", "Unity"],
    "avoid": ["PvP", "긴 스토리"],
    "references": ["Hades", "Dead Cells"],
    "assumed": ["한 판 길이는 사용자 미정이라 제안값"]
  },
  "concepts": [ ... ]
}
```

`constraints`는 자유 형식이다. 사용자가 답하지 않아 에이전트가 정한 값은 `assumed`에 적는다. 검사기가 읽는 키는 둘이다.

| 키 | 뜻 |
|---|---|
| `fixed_axes` | 사용자 제약으로 모든 후보가 같은 값을 갖는 축 `{축: 값}`. 겹침·쏠림 비교에서 빠진다. [search-axes.md](search-axes.md#제약으로-고정된-축) |
| `extra_axes` | 표에 없는 축을 새로 쓸 때 그 이름 배열. 없으면 `unknown_axis` 경고 |

파일을 처음 만들 때는 후보가 아직 없어도 `"concepts": []`를 넣는다. 없으면 컨셉 파일로 읽지 못한다(읽기 오류로 알린다).

## 컨셉

| 필드 | 필수 | 뜻 |
|---|---|---|
| `id` | 예 | 소문자·숫자·밑줄. 순위가 바뀌어도 그대로 |
| `name` | 예 | 짧은 이름 |
| `pitch` | 예 | 한 문장 |
| `core_verb` | 예 | 핵심 동사(피한다, 쌓는다, 건다 …) |
| `decision` | 예 | 몇 초마다 다시 내리는 선택 |
| `state_read` | 예 | 그 선택 전에 화면에서 읽는 정보 |
| `skill_expression` | 예 | 숙련자가 단순 전략과 다르게 하는 것 |
| `risk` | 예 | 가장 큰 위험 |
| `signature` | 예 | 구조 축 → 값, 4축 이상. [search-axes.md](search-axes.md) |
| `status` | 아니오 | `proposed`(후보) / `approved`(선택: 프로토타입 대상) / `cut`(제외) |
| `origin` | 아니오 | `root` 또는 변이 원본 id |
| `loop` | 아니오 | `{moment, run, meta}` 초안 |
| `stress` | 아니오 | `[{policy, result, evidence, definition}]`. 목록 밖 전략은 `definition` 필요. [stress-policies.md](stress-policies.md) |
| `hard_reject` | 아니오 | `{type, reason, evidence}`. 있으면 `status`는 `cut` |
| `cost` | 아니오 | `{level: small/medium/large, reason}`. 제작 부담 추정이며 가정이다 |
| `next_test` | 아니오 | 이 가설을 가장 싸게 확인할 시험. 활성 후보에 없으면 경고 |
| `notes` | 아니오 | 변이 이유, 기대 변화, 사용자 의견 |
| `brief` | 선택 시 | `approved`면 필수. [brief.md](brief.md). `proposed`인 컨셉의 브리프는 검사하지 않아 일부만 적어도 된다. `approved`로 바꾸면 전부 검사한다 |
| `existing_game` | 아니오 | `true`면 이미 만들고 있는 게임의 컨셉이다. 후보 칸을 비워도 된다(아래 검사 표). [existing-game.md](existing-game.md) |
| `acknowledged` | 아니오 | 확인을 마친 경고 `{경고 코드: 이유}`. 경고 수에서 빠지고 이유와 함께 따로 보인다 |

## 검사 내용

| 코드 | 수준 | 조건 |
|---|---|---|
| `missing_field`, `schema`, `duplicate_id` | 오류 | 필수 항목 누락, 형식 위반, id 중복. `existing_game`이 `true`면 `pitch`부터 `risk`까지 필수가 아니고, `signature`는 적었을 때만 본다 |
| `signature_missing_axis` | 오류 | 필수 축(`decision`, `information`, `commitment`, `risk_reward`)이 없음. 고정 축은 없어도 됨 |
| `signature_too_small` | 오류 | 비교할 구조 축(고정 축 제외)이 4개 미만 |
| `evidence_missing` | 오류 | `unknown`이 아닌 반증 결과에 근거가 없음 |
| `reject_unsupported` | 오류 | `hard_reject`에 유형·이유·증거 중 하나가 없음 |
| `unknown_origin` | 오류 | `origin`이 없는 컨셉을 가리킴 |
| `brief_missing`, `brief_incomplete` | 오류 | 선택한 컨셉의 브리프가 없거나 빠짐(필러 테스트, 가설의 틀렸다는 신호, MVP 7개 초과 등) |
| `provenance` | 오류 | 선택한 컨셉의 브리프 문장에 출처 태그 형식 오류. 또는 `[계산]`·`[측정]`의 경로 출처가 게임 프로젝트 폴더에 없거나, `data/playtests.json#세션 id`의 세션이 기록에 없음 |
| `unknown_axis` | 경고 | 표에 없는 축 이름(오타일 수 있음). 새 축이면 `constraints.extra_axes`에 적는다 |
| `fixed_axis_mismatch` | 경고 | 제약으로 고정된 축에 다른 값을 적음 |
| `unknown_policy` | 경고 | 목록에 없는 단순 전략인데 `definition`이 없음 |
| `hypothesis_id_missing` | 경고 | 브리프 가설에 `id`가 없음. 기록과 판정은 가설 id로 가리키므로 플레이 전에 단다 |
| `hypothesis_sample_missing` | 경고 | 브리프 가설에 최소 표본 `sample`이 없음. 판정에 필요한 사람 수와 판 수를 플레이 전에 정한다 |
| `untagged_number` | 경고 | 선택한 컨셉의 판정 기준(가설의 `claim`, `failure_signal`, `test`와 `success_criteria`)에 태그 없는 수치. `--fail-on-assumed`에서도 막는다. 메시지는 앞 5개만 보이고, `--json`의 `values`에 전부 있다 |
| `criteria_tag_mismatch` | 경고 | 한 가설의 두 칸(또는 가설과 `success_criteria`)에 같은 수치가 있는데 한쪽은 `[결정]`, 다른 쪽은 `[가정]`. 뜻이 다른 값이면 `acknowledged`에 `{"criteria_tag_mismatch": {"30초": 까닭}}`처럼 그 값만 적는다. 경고가 보인 값을 그대로 쓴다(가운뎃점 목록은 `0.5·1·2배` 전체). 예전 꼴 값(`2배`, `0.3`)으로 적은 확인은 이어 쓰고 참고 줄로 이름을 바꾸라고 알린다 |
| `criteria_history_mismatch` | 오류 | 가설의 `criteria_history`에 적은 고치기 전 값으로 계산한 지문이 적힌 지문과 다름, 또는 기준이 바뀌지 않은 이력(태그·띄어쓰기만 바꿈). 이력은 오래된 것이 앞이다. 범위 훅은 이 오류로 게임 편집을 막지 않는다 |
| `criteria_history_invalid` | 오류 | `criteria_history`의 형식이 틀림(배열이 아님, `date`가 달력에 없는 날, `stamp`가 지문 꼴이 아님, `before`가 비었거나 지문에 드는 칸이 아님, `why`가 빔) |
| `criteria_points_to_data` | 경고 | 판정 기준 문장(`claim`, `failure_signal`, `test`, `success_criteria`)이 게임 데이터 파일의 경로를 적음("값은 data/growth.json의 …"). 종류는 내용으로, 파일이 없거나 게임 고유 형식이면 이름으로 본다. 판정 기록·컨셉·시스템 설계·시뮬레이터 설정·종류를 알 수 없는 JSON은 보지 않는다(출처 태그 안의 경로도). 경고가 없다고 그 파일을 가리켜도 된다는 뜻은 아니다. 그 파일은 다음 조정에서 바뀌어 문장이 다른 빌드를 가리키게 된다. 변경 이름이나 빌드 id(세션의 `build` 커밋, `game_build` 지문)로 가리킨다. 판정한 가설이면 `builds`를 새로 더하지 않고 문장의 변경 이름으로 가리키며(없으면 묻는다), 사용자와 확인한 뒤 고친다. 판정한 가설에 대한 이 안내는 가설 문장의 경고에만 붙는다(`success_criteria`는 지문에 들지 않는다)([playtest-verdict](../../playtest-verdict/references/changes.md#판정한-가설의-문장을-고칠-때)의 '판정한 가설의 문장을 고칠 때'). 그대로 두려면 `acknowledged`에 `{"criteria_points_to_data": {"data/growth.json": 까닭}}` |
| `success_criteria_misses_hypothesis` | 경고 | 선택한 컨셉의 `prototype.success_criteria`가 브리프의 가설 수와 다른 수를 말함("두 가설", "2개 가설", "가설 두 개", "가설 둘". 여럿이면 가장 큰 수. "한 가설"과 "가설 2" 같은 이름표, "가설 1개 이상"처럼 뒤에 이상·넘게·라도·만이 붙은 문턱은 수로 보지 않는다), 또는 가설이 둘 이상인데 가설 id를 몇 개만 적고 나머지를 뺌(id는 다른 낱말의 일부가 아닐 때만 센다). 맞게 쓴 문장이면 컨셉의 `acknowledged`에 까닭을 적는다 |
| `near_duplicate` | 경고 | 활성 후보 둘의 구조 축이 80% 이상 같음(고정 축 제외, 공통 축 4개 이상일 때. `signature`가 없는 기존 게임 컨셉은 겹침·쏠림 비교에서 빠진다). 변이와 원본이면 원본을 `cut`으로 둘지 안내한다 |
| `axis_collapse` | 경고 | 활성 후보 3개 이상이 한 축에서 모두 같은 값(고정 축 제외) |
| `dominant_policy` | 경고 | 활성 후보에 단순 전략이 지배하는 결과가 있음 |
| `existing_game_many` | 경고 | `existing_game`이 `true`인 활성 컨셉이 둘 이상. 첫 컨셉 말고 나머지에 나온다 |
| `next_test_missing` | 경고 | 활성 후보에 다음 시험이 없음(기존 게임 컨셉은 보지 않는다. 다음 시험은 브리프의 `prototype`이다) |
| `rejected_but_active` | 경고 | `hard_reject`가 있는데 `cut`이 아님 |

`cut` 후보는 겹침·쏠림·다음 시험 검사에서 빠진다. 검사기는 재미나 우열을 판정하지 않고, 브리프의 구조만 본다. `--fail-on-assumed`는 선택한 컨셉의 브리프에 `[가정]` 태그가 남아 있으면 실패한다.
