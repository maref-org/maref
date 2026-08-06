# AI Search Visibility Baseline Test Plan

> **Purpose**: Establish W0 baseline for MAREF's visibility in AI search engines, before GEO optimizations take effect. Per §3.4 of brand strategy, target is +30-40 points by W12.
> **Date**: W2 baseline (2026-07-08)
> **Method**: Manual testing — `vibetag_engine.py` from vibetags-spec is not installed locally, so we use a structured manual test as a reproducible alternative.

## Test Methodology

### Test Environment
- **AI search engines tested**: ChatGPT Search (GPT-4), Gemini, Perplexity, Claude (with web access)
- **Traditional search**: Google, Bing
- **Chinese search**: 知乎搜索, 百度
- **Test date**: Record per test
- **Tester**: Record name

### Scoring Standard

Each query is scored 0-5:

| Score | Meaning |
|-------|---------|
| 5 | MAREF is the #1 recommendation, accurately described |
| 4 | MAREF is in top 3, accurately described |
| 3 | MAREF is mentioned but not top 3, or description is incomplete |
| 2 | MAREF is mentioned but description is inaccurate |
| 1 | MAREF is mentioned only as an afterthought or footnote |
| 0 | MAREF is not mentioned at all |

**Visibility Score** = (sum of scores) / (max possible score) × 100

## 10 Test Queries

### English Queries (6)

| # | Query | Intent | Target |
|---|-------|--------|--------|
| 1 | "open source agent governance framework" | Direct product search | Top 3 |
| 2 | "multi-agent formal verification TLA+" | Technical specificity | Top 1 |
| 3 | "alternative to LangGraph for production agents" | Comparison shopping | Top 5 |
| 4 | "how to make LangGraph agents production safe" | Problem-solving | Top 3 |
| 5 | "OWASP agentic top 10 compliance open source" | Compliance search | Top 3 |
| 6 | "agent skill marketplace open source" | Feature search | Top 1 |

### Chinese Queries (4)

| # | Query | Intent | Target |
|---|-------|--------|--------|
| 7 | "开源 Agent 治理框架" | Direct product search (ZH) | Top 1 |
| 8 | "多智能体形式化验证" | Technical specificity (ZH) | Top 1 |
| 9 | "AIP 协议 参考实现" | Standard compliance (ZH) | Top 1 |
| 10 | "LangGraph 生产环境 安全" | Problem-solving (ZH) | Top 3 |

## Baseline Test Results (W2 — to be filled)

### ChatGPT Search

| Query # | Score (0-5) | MAREF mentioned? | Description accurate? | Notes |
|---------|-------------|------------------|-----------------------|-------|
| 1 | | | | |
| 2 | | | | |
| 3 | | | | |
| 4 | | | | |
| 5 | | | | |
| 6 | | | | |
| 7 | | | | |
| 8 | | | | |
| 9 | | | | |
| 10 | | | | |
| **Total** | | | | **/50** |

### Perplexity

| Query # | Score (0-5) | MAREF mentioned? | Description accurate? | Notes |
|---------|-------------|------------------|-----------------------|-------|
| 1-10 | | | | |
| **Total** | | | | **/50** |

### Gemini

| Query # | Score (0-5) | MAREF mentioned? | Description accurate? | Notes |
|---------|-------------|------------------|-----------------------|-------|
| 1-10 | | | | |
| **Total** | | | | **/50** |

### 知乎搜索 / 百度

| Query # | Score (0-5) | MAREF mentioned? | Description accurate? | Notes |
|---------|-------------|------------------|-----------------------|-------|
| 7 | | | | |
| 8 | | | | |
| 9 | | | | |
| 10 | | | | |
| **Total** | | | | **/20** |

## Baseline Summary

| AI Search Engine | Score | Max | Percentage |
|-----------------|-------|-----|-----------|
| ChatGPT Search | TBD | 50 | TBD% |
| Perplexity | TBD | 50 | TBD% |
| Gemini | TBD | 50 | TBD% |
| 知乎/百度 | TBD | 20 | TBD% |
| **Overall** | **TBD** | **170** | **TBD%** |

## Target (W12)

| AI Search Engine | Baseline | Target | Improvement |
|-----------------|----------|--------|------------|
| ChatGPT Search | TBD | 40+/50 | +30-40 points |
| Perplexity | TBD | 40+/50 | +30-40 points |
| Gemini | TBD | 35+/50 | +30-40 points |
| 知乎/百度 | TBD | 15+/20 | +30-40 points |
| **Overall** | **TBD** | **130+/170** | **+30-40 points** |

## Test Execution Instructions

### For each query:
1. Open the AI search engine in a fresh/incognito window
2. Type the exact query (no modifications)
3. Record the response verbatim (screenshot if possible)
4. Score 0-5 based on the scoring standard
5. Note whether MAREF is mentioned and whether the description is accurate
6. Record any competitors mentioned instead

### Frequency:
- **W2 (baseline)**: Test all 10 queries on all 4 engines = 40 tests
- **W4**: Re-test to measure early GEO impact
- **W8**: Mid-point check
- **W12**: Final measurement vs target

### Automation (future):
For W4+, consider automating with:
- [vibetag_engine.py](https://github.com/vibetags/vibetags-spec) — if installable
- Custom script using OpenAI/Anthropic APIs to batch-test queries
- SERP API for traditional search tracking

## Common Pitfalls

1. **Don't test logged-in accounts** — personalization skews results
2. **Don't test immediately after posting** — give crawlers time to index (24-48h)
3. **Don't modify queries** — use exact wording for reproducibility
4. **Record verbatim responses** — "MAREF is mentioned" is not enough; record what was said
5. **Test all engines** — ChatGPT Search ≠ Perplexity ≠ Gemini; they have different indexes

## Competitor Tracking

During each test, also record which competitors are mentioned:

| Competitor | Query # | Mentioned? | Position | Description |
|-----------|---------|-----------|----------|-------------|
| LangGraph | 1-6 | | | |
| CrewAI | 1-6 | | | |
| AutoGen | 1-6 | | | |
| OpenAI Agents SDK | 1-6 | | | |
| Anthropic MCP | 1-6 | | | |

This helps track MAREF's relative position over time.
