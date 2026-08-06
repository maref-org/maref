# RSI Longevity Test Suite

Tests the RSI system's ability to sustain quality over extended periods.

## Quick Smoke Test
```bash
pytest tests/longevity/ -v
```

## Full 24h Regression Test
```bash
pytest tests/longevity/ --run-longevity -v
```

> **Warning**: The full 24h test may consume significant LLM API quota.
> Use `--mock` mode (default) for budget-friendly runs.

## 7-Day Stability Test
```bash
# Quick smoke
pytest tests/longevity/test_7d_stability.py -v

# Full 168h run
pytest tests/longevity/test_7d_stability.py --run-longevity -v
```

## Test Metrics
- Experiment count
- Adoption rate (keep ratio)
- Average score
- Safety alert count
- Human intervention rate
- Self-heal rate
- Degradation detection
