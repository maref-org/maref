# PERCV Research Protocol

This is an autonomous industry research system driven by the PERCV cycle:
Perceive → Extract → Reduce → Conclude → Validate.

## Ratchet Loop Configuration

```yaml
target_dir: vault/kdps
metric_name: consistency_score
metric_direction: higher_is_better
evaluation_command: uv run percv evaluate
human_gate: true
branch_prefix: percv
models:
  primary: deepseek
  auditor: kimi
  judge: claude
  cn_context: qwen
  global_context: gpt4o
budget:
  monthly_cap: 5000
  warning_at_pct: 80
```

## Research Topics

Define your research topics here:

1. [Topic name]
   - Scope: [Description]
   - Monitoring nodes: [List of sources to monitor]
   - Validation horizon: [e.g. 90 days]

## Agent Pipeline

1. **Scout**: Monitor key nodes, harvest raw signals → vault/signals/
2. **Distiller**: Dual-blind KDP extraction, consensus check → vault/kdps/
3. **Projector**: Hypothesis tree + red-blue adversarial → vault/forecasts/
4. **Validator**: Expired forecast vs actual results → status update
5. **Archivist**: Validated forecast → pattern card → vault/patterns/
6. **Librarian**: RAG search of historical patterns for new forecasts

## Rules

- **One variable per experiment**: Each ratchet iteration changes exactly one thing
  (one prompt template, one threshold, one routing rule)
- **Scalar metric is truth**: consistency_score is the only success criterion
- **Git is state machine**: Every experiment is a commit, only improvements survive
- **Budget is law**: ¥5000/month hard cap, auto-downgrade at 80%
- **NEVER STOP**: The loop runs until human interruption
