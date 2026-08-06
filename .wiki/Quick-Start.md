# Quick Start

## Installation

```bash
pip install maref
```

## 5-Minute Setup

```bash
# 1. Run environment diagnostics
python scripts/check_desktop_env.py

# 2. Launch desktop agent demo (safe dry-run mode)
maref desktop demo

# 3. Start Sidecar service
maref serve --port 8000

# 4. Open GUI
open http://localhost:8000
```

## CLI Usage

```bash
# Governance status
maref status

# Desktop agent demo
maref desktop demo

# Start service with GUI
maref serve --port 8000 --gui
```

## Python API

### Governance State Machine

```python
from maref_lite.governance import GovernanceOverlay
from maref_lite.state_machine import GovernanceState

overlay = GovernanceOverlay()
overlay._state_machine.transition(GovernanceState.OBSERVE)
overlay._state_machine.transition(GovernanceState.ANALYZE)
print(overlay.get_status())
```

### Loop Engineering (v0.36.0-rc)

```python
from maref.loop.convergent import ConvergentLoop
from maref.loop.exploratory import ExploratoryLoop
from maref.loop.interactive import InteractiveLoop
from maref.loop.bridge import LoopGovernanceBridge

async def example():
    loop = ConvergentLoop(
        solve_fn=lambda x: {"score": 0.95, "output": x},
        max_rounds=10,
    )
    bridge = LoopGovernanceBridge()
    result = await bridge.run_governed(loop, "example input")
    print(result.stop_reason, result.rounds_completed)
```

## Full Project Setup

```bash
git clone https://github.com/maref-org/maref.git
cd maref

# Using uv (recommended)
uv venv
source .venv/bin/activate
uv pip install -e ".[all]"

# Run tests
pytest tests/ -v --tb=short

# Launch demo
python examples/simple_integration_demo.py
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Installation fails | `pip install --upgrade pip` and retry |
| Desktop permission denied | Grant accessibility permissions in system settings |
| Port conflict | Use `--port` to specify a different port |
| Dependency conflict | Use `uv venv` for isolated environment |

## Next Steps

- Read the [Architecture](Architecture) overview
- Browse the [API Reference](API-Reference)
- Review the [Competitive Analysis](Competitive-Analysis)
- [docs/development.md](https://github.com/maref-org/maref/blob/main/docs/development.md) for development setup
