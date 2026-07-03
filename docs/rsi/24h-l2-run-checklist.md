# 24h L2 Unsupervised Run — Checklist

## Pre-Run
- [ ] Verify all L2 components deployed
- [ ] Run full test suite (`pytest tests/ -v --tb=short`)
- [ ] Check API key quotas (if not using mock mode)
- [ ] Verify disk space (need ~500MB for logs)
- [ ] Set SLACK_WEBHOOK env var (optional)

## Quick Smoke Test (5 min)
```bash
python scripts/run_longevity.py --quick
```

## Full 24h Run
```bash
python scripts/run_longevity.py --l2 --duration 24 --mock
```

or with config:
```bash
python scripts/run_longevity.py --config configs/longevity/24h-l2-run.yaml
```

## Monitoring
- Watch log output: `tail -f logs/longevity*.log`
- Expected checkpoints: 48 (every 30 min)
- Expected improvements: >= 500 rounds

## Post-Run Verification
- [ ] Adoption rate decline < 10%
- [ ] Score decline < 5 points
- [ ] Safety alerts <= 1
- [ ] Human intervention rate <= 2%
- [ ] All L2 quality gates passed
- [ ] Report saved to `docs/rsi/24h-l2-run-report-*.json`

## Failure Recovery
1. Check `docs/rsi/24h-l2-run-report-*.json` for degradation details
2. Identify which dimension(s) degraded
3. Check quality gate scores
4. Run targeted tests on the failing dimension
5. Re-run with fix
