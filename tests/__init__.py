"""Make `import helpers` and `import badcop` work whether tests run via discover or as a package."""
import sys
from pathlib import Path

_here = Path(__file__).resolve().parent
for p in (_here, _here.parent / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
