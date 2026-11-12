#!/usr/bin/env python3
"""게임 설계 데이터 공용 도구의 실행 파일. 표준 라이브러리만 사용한다 (Python 3.9 이상).

    python3 studio.py view <프로젝트 또는 데이터 폴더>     읽기 전용 뷰어 (브라우저)
    python3 studio.py check <폴더 또는 파일> [--table]     컨셉·아이템·영구 강화·적·전투 계산·판 안 성장·스탯 예산·강화·합성·재화 흐름·레벨 구성·플레이 기록 검사
    python3 studio.py simulate <data/meta.json>            메타 성장 시뮬레이션
    python3 studio.py hypothesis <컨셉.가설> [프로젝트]     가설 하나의 판정 자료만 모아 출력 (읽기 전용)
    python3 studio.py provenance <design/>                 기획 문서 수치 출처 태그 검사
    python3 studio.py draft <프로젝트> --archetype 원형 --at 3  예산 곡선으로 아이템·적 초안 (파일에 쓰지 않음)
    python3 studio.py setup claude <게임 프로젝트>          판정 에이전트와 훅 설치 (Claude Code)

자세한 옵션: python3 studio.py <명령> --help
"""
import sys

# 스크립트로 실행하면 Python이 이 파일의 폴더를 모듈 검색 경로에 넣으므로 studio_data를 바로 불러올 수 있다.
from studio_data.cli import main

if __name__ == "__main__":
    sys.exit(main())
