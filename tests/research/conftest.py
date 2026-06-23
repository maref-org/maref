import sys
from pathlib import Path

SRC = str(Path(__file__).resolve().parent.parent.parent / "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)
for mod in list(sys.modules.keys()):
    if mod == "research" or mod.startswith("research."):
        del sys.modules[mod]
