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

from studio_data import budget, calibrate, claude, cli, combat, common, concepts, crafting, datasets, economy, enemies, growth, items, levels, meta_sim, playtests, provenance, systems, upgrades, viewer  # noqa: E402,F401


CHANGES = ROOT / "skills/playtest-verdict/references/changes.md"   # 기준과 컨셉을 바꾸는 순서의 원본


def changes_section(title: str) -> str:
    """changes.md에서 '## title' 절 하나(다음 '## ' 제목 전까지)를 돌려준다."""
    text = CHANGES.read_text(encoding="utf-8")
    start = text.index(f"\n## {title}\n")
    end = text.find("\n## ", start + 1)
    return text[start:end if end != -1 else len(text)]


LEVEL = ROOT / "skills/level-design"


def level_guide() -> str:
    """레벨 구성의 할 일: SKILL.md와 게임 형태별로 적는 법(references/game-shapes.md)."""
    return "\n".join((LEVEL / rel).read_text(encoding="utf-8") for rel in ("SKILL.md", "references/game-shapes.md"))


def level_format() -> str:
    """레벨 구성의 데이터 형식, 계산, 검사 표(references/levels-format.md)."""
    return (LEVEL / "references/levels-format.md").read_text(encoding="utf-8")


def run_cli(*args):
    """studio.py와 같은 진입점으로 실행해 (종료 코드, 표준 출력)을 돌려준다."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main([str(a) for a in args])
    return code, out.getvalue()
