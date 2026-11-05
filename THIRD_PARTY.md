# 외부 프로젝트 참고와 고지

현재 이 저장소에는 외부 프로젝트의 코드나 문장을 복사한 부분이 없다. 아래 프로젝트는 분석하고 아이디어를 참고했으며, 문장과 코드는 독립적으로 작성했다.
코드나 문장을 가져오는 시점에 해당 항목에 가져온 파일과 라이선스 전문 위치를 추가한다.

| 프로젝트 | 라이선스 | 참고한 내용 |
| --- | --- | --- |
| [Donchitos/Claude-Code-Game-Studios](https://github.com/Donchitos/Claude-Code-Game-Studios) | MIT | 산출물 체인, 완료 판정 순서, NOT ASSESSED 원칙, 수치 단일 출처 개념. `concept-exploration`의 필러 설계 테스트, 안티필러, MVP 개수 제한, 위험한 것부터 만드는 순서. `playtest-verdict`의 "PASS를 지어내지 않는다"와, 그 프로젝트에 읽기 전용 리뷰어가 없다는 약점에서 얻은 판정 에이전트 권한 분리 |
| [Fission-AI/OpenSpec](https://github.com/Fission-AI/OpenSpec) | MIT | 수명주기 뼈대로 쓰는 외부 도구. 설치하지 않고 함께 배포하지 않으며, `scope-guard`가 폴더 구조와 `.openspec.yaml`을 읽는다 |
| [abagames/agentic-gamedev-skills](https://github.com/abagames/agentic-gamedev-skills) | MIT | 증거 상태 구분(unknown ≠ 실패), 시뮬레이션 실행 프로파일, 표본 규율, 반복 개선 루프. `concept-exploration`의 재미 점수 없는 구조 탐색, 단순 전략 반증, 증명된 결함만 탈락, 구조 서명으로 중복 정리, 인과 관계 하나를 바꾸는 변이, 사용자 응답을 지어내지 않는 선택 대기. `playtest-verdict`의 unknown ≠ 실패, 표본 수를 함께 보고하는 규율 |

조사 범위와 방법은 `docs/research/`에 있다.
