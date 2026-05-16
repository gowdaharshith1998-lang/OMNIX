#!/usr/bin/env python3
"""Direct script wrapper for the packaged OMNIX CLI."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# If this file is imported as `omnix` from the repository root, expose the real
# package path so submodule imports such as `omnix.cli` still resolve.
if __name__ == "omnix":
    __path__ = [str(_SRC / "omnix")]  # type: ignore[name-defined]

from omnix.cli import main


if __name__ == "__main__":
    main()
