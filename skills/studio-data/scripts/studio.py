#!/usr/bin/env python3
"""게임 설계 데이터 공용 도구의 실행 파일. 표준 라이브러리만 사용한다 (Python 3.9 이상).

    python studio.py view <프로젝트 또는 데이터 폴더>     읽기 전용 뷰어 (브라우저)
    python studio.py check <폴더 또는 파일> [--table]     컨셉·아이템·영구 강화·적 검사
    python studio.py simulate <data/meta.json>            메타 성장 시뮬레이션
    python studio.py provenance <design/>                 기획 문서 수치 출처 태그 검사

자세한 옵션: python studio.py <명령> --help
"""
import sys

# 스크립트로 실행하면 Python이 이 파일의 폴더를 모듈 검색 경로에 넣으므로 studio_data를 바로 불러올 수 있다.
from studio_data.cli import main

if __name__ == "__main__":
    sys.exit(main())
