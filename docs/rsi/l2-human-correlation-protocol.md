# L2 Human-AI Correlation Study Protocol

## Objective
Validate RSI automated scoring against human expert judgment.
Target: Spearman correlation >= 0.7 (L2 acceptance criteria PERCV-RSI-ACCEPT-003).

## Sampling Strategy
- **Sample size**: 50 rounds randomly selected from 500-round RSI run
- **Stratification**: 10 from each of 5 phases (early/mid/late/plateau/recovery)
- **Blinding**: Human reviewers see only the round data, not automated scores

## Scoring Dimensions (6)
1. **Correctness** (0-100): Code correctness of improvements
2. **Testing** (0-100): Test coverage and quality
3. **Code Quality** (0-100): Readability, maintainability, style
4. **Security** (0-100): Safety of changes
5. **Efficiency** (0-100): Resource usage
6. **Adoption** (0-100): Integration success rate

## Review Process
1. Automated scorer evaluates each round (already implemented)
2. Human reviewers (minimum 2, target 3) independently score each round
3. Reviewers use the web-based scoring form at `/review/{round_id}`
4. Scores are collected and correlated against automated scores

## Correlation Analysis
- Primary metric: Spearman rank correlation (per dimension + overall)
- Secondary: Cohen's kappa for inter-rater reliability
- Threshold: Spearman >= 0.7 (overall), kappa >= 0.6

## Pass/Fail Criteria
- PASS: Spearman >= 0.7 on all 6 dimensions + overall
- CONDITIONAL PASS: 5/6 dimensions >= 0.7, overall >= 0.7
- FAIL: Any dimension < 0.5, or overall < 0.7

## Data Collection
- All scores recorded to `vault/rsi-correlation-data.yaml`
- Each entry: round_id, automated_scores (dict), reviewer_scores (list[dict]), mean_human_score, spearman_r
