#!/usr/bin/env python3
"""Launch the product CLI pinned by this workspace."""
from pathlib import Path
import sys

if sys.version_info < (3, 10):
    print("mosaico: this workspace requires Python 3.10 or newer", file=sys.stderr)
    raise SystemExit(3)

TOOLS_ROOT = Path(__file__).resolve().parent / "submodule/esp-mosaico-utils/mosaico-tools"
if not (TOOLS_ROOT / "tools/mosaico_cli/cli.py").is_file():
    print("mosaico: initialize tools with 'git submodule update --init submodule/esp-mosaico-utils'", file=sys.stderr)
    raise SystemExit(3)
sys.path.insert(0, str(TOOLS_ROOT / "tools"))
if sys.argv[1:3] == ["game", "install"]:
    sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
    from game_store import main as install_game

    raise SystemExit(install_game(
        sys.argv[3:], repository=Path(__file__).resolve().parent, tool_root=TOOLS_ROOT,
    ))
from mosaico_cli.cli import main

if __name__ == "__main__":
    raise SystemExit(main(tool_root=TOOLS_ROOT))
