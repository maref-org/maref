import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
_DEFAULT_HOME = Path.home() / '.maref'

@dataclass
class MAREFConfig:
    home_dir: Path = field(default_factory=lambda: _DEFAULT_HOME)
    log_dir: Path | None = None
    data_dir: Path | None = None
    audit_path: Path | None = None
    kg_storage_path: Path | None = None
    max_depth: int = 5
    max_trips: int = 10
    governance_enabled: bool = True
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.log_dir is None:
            self.log_dir = self.home_dir / 'logs'
        if self.data_dir is None:
            self.data_dir = self.home_dir / 'data'

    @classmethod
    def from_env(cls) -> MAREFConfig:
        home_raw = os.environ.get('MAREF_HOME')
        home = Path(home_raw) if home_raw else _DEFAULT_HOME
        log_dir = Path(p) if (p := os.environ.get('MAREF_LOG_DIR')) else None
        data_dir = Path(p) if (p := os.environ.get('MAREF_DATA_DIR')) else None
        audit_path = Path(p) if (p := os.environ.get('MAREF_AUDIT_PATH')) else None
        kg_storage_path = Path(p) if (p := os.environ.get('MAREF_KG_PATH')) else None
        try:
            max_depth = int(os.environ.get('MAREF_MAX_DEPTH', '5'))
        except ValueError:
            max_depth = 5
        try:
            max_trips = int(os.environ.get('MAREF_MAX_TRIPS', '10'))
        except ValueError:
            max_trips = 10
        governance_enabled = os.environ.get('MAREF_GOVERNANCE', 'true').lower() != 'false'
        return cls(home_dir=home, log_dir=log_dir, data_dir=data_dir, audit_path=audit_path, kg_storage_path=kg_storage_path, max_depth=max_depth, max_trips=max_trips, governance_enabled=governance_enabled)