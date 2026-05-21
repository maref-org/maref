import os
from pathlib import Path

ASSET_BASE = os.environ.get(
    "MAREF_ASSET_BASE",
    str(Path.home() / "ai-native-ip")
)
