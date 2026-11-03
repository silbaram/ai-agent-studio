"""테스트가 공용 도구 패키지(skills/studio-data/scripts/studio_data)를 불러오는 곳."""
import io
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "skills/studio-data"
SAMPLE = STUDIO / "assets/sample-project"
sys.path.insert(0, str(STUDIO / "scripts"))

from studio_data import budget, claude, cli, combat, common, concepts, datasets, enemies, items, meta_sim, playtests, provenance, upgrades, viewer  # noqa: E402,F401


def run_cli(*args):
    """studio.py와 같은 진입점으로 실행해 (종료 코드, 표준 출력)을 돌려준다."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main([str(a) for a in args])
    return code, out.getvalue()
