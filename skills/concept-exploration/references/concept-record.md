# 컨셉 기록 형식

게임 프로젝트의 `design/concepts.json` 한 파일에 모든 후보와 판단을 남긴다. 기획 문서(md)는 컨셉을 `id`로만 언급한다. 검사: `check_concepts.py`.

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

`constraints`는 자유 형식이다. 사용자가 답하지 않아 에이전트가 정한 값은 `assumed`에 적는다.

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
| `stress` | 아니오 | `[{policy, result, evidence}]`. [stress-policies.md](stress-policies.md) |
| `hard_reject` | 아니오 | `{type, reason, evidence}`. 있으면 `status`는 `cut` |
| `cost` | 아니오 | `{level: small/medium/large, reason}`. 제작 부담 추정이며 가정이다 |
| `next_test` | 아니오 | 이 가설을 가장 싸게 확인할 시험. 활성 후보에 없으면 경고 |
| `notes` | 아니오 | 변이 이유, 기대 변화, 사용자 의견 |
| `brief` | 선택 시 | `approved`면 필수. [brief.md](brief.md) |

## 검사 내용

| 코드 | 수준 | 조건 |
|---|---|---|
| `missing_field`, `schema`, `duplicate_id` | 오류 | 필수 항목 누락, 형식 위반, id 중복 |
| `signature_too_small` | 오류 | 구조 축이 4개 미만 |
| `evidence_missing` | 오류 | `unknown`이 아닌 반증 결과에 근거가 없음 |
| `reject_unsupported` | 오류 | `hard_reject`에 유형·이유·증거 중 하나가 없음 |
| `unknown_origin` | 오류 | `origin`이 없는 컨셉을 가리킴 |
| `brief_missing`, `brief_incomplete` | 오류 | 선택한 컨셉의 브리프가 없거나 빠짐(필러 테스트, 가설의 틀렸다는 신호, MVP 7개 초과 등) |
| `near_duplicate` | 경고 | 활성 후보 둘의 구조 축이 80% 이상 같음(공통 축 4개 이상일 때) |
| `axis_collapse` | 경고 | 활성 후보 3개 이상이 한 축에서 모두 같은 값 |
| `dominant_policy` | 경고 | 활성 후보에 단순 전략이 지배하는 결과가 있음 |
| `next_test_missing` | 경고 | 활성 후보에 다음 시험이 없음 |
| `rejected_but_active` | 경고 | `hard_reject`가 있는데 `cut`이 아님 |

`cut` 후보는 겹침·쏠림·다음 시험 검사에서 빠진다. 검사기는 재미나 우열을 판정하지 않는다.
