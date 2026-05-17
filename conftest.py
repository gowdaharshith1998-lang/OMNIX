"""Root-level conftest: ensure project root is on sys.path so `tests.*` and `src.*` imports resolve in pytest."""
import sys
from pathlib import Path

ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
