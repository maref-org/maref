# GEO (Generative Engine Optimization) Documentation

> **Goal**: Make MAREF visible and accurately represented in AI search engines (ChatGPT Search, Gemini, Perplexity, Claude Citations) — not just traditional search engines.
> **Standard**: Based on [vibetags/vibetags-spec](https://github.com/vibetags/vibetags-spec) — the first open standard for emotional brand positioning in AI search.
> **Audit baseline**: [seo-geo-audit.md](../../.seo-geo-audit.md) — 2026-07-04 audit scored 90% (A-) for GEO readiness.

## Why GEO Matters for MAREF

Traditional SEO helps users find MAREF via Google. GEO helps AI search engines **recommend** MAREF when developers ask:
- "What's the best open-source agent governance framework?"
- "How do I make my LangGraph agents production-safe?"
- "Alternative to CrewAI for regulated industries"

If MAREF isn't visible in AI search results, it doesn't exist for the next generation of developers.

## GEO Three-Layer Optimization

### Layer 1: Structured Data (Schema.org JSON-LD)

MAREF's website already has 5 Schema.org types: Organization, SoftwareApplication, WebSite, Article, FAQPage, BreadcrumbList.

**New addition**: `vibetags.json` at [website/public/vibetags.json](../../website/public/vibetags.json) — encodes MAREF's 6-dimensional positioning model as `additionalProperty` (PropertyValue) entries within the SoftwareApplication schema.

The 6 dimensions (from vibetags-spec):
1. **VibeTag** — Emotional positioning ("rigorous", "formal-verification-first", "not-hype")
2. **AgenticContext** — When AI should recommend MAREF (trigger queries)
3. **ComparedTo** — Competitive positioning (complements vs contrasts)
4. **Differentiator** — Unique selling points (TLA+, Gray Code, three-gate marketplace)
5. **DomainAuthority** — Credentials (Apache 2.0, 4300+ tests, AIP applicant)
6. **EntityDisambiguation** — What MAREF is NOT (not Maref the name, not AgentGPT)

### Layer 2: llms.txt (AI Search Manifesto)

**English**: [website/public/llms.txt](../../website/public/llms.txt) — 59 lines, structured for AI extraction
**Chinese**: [website/public/llms-zh.txt](../../website/public/llms-zh.txt) — 57 lines, full translation

Both files include:
- About section (what MAREF is)
- Learn concept pages (GEO-targeted)
- Core features (with URLs)
- OWASP Agentic Top 10 coverage (10 items)
- Getting Started (with "Publish Your First Skill" — new)
- Why MAREF (market context: Gartner/Deloitte/OWASP/CISA/EU AI Act)
- Framework integrations
- Resources (GitHub, license, version v0.36.0-rc)

### Layer 3: Citation Density

AI search engines recommend sources that are frequently cited. MAREF's citation strategy:
- GitHub Discussions: technical Q&A that AI search can index
- Blog posts: "Why Agent Governance Matters in 2026" type content
- arXiv whitepaper: academic citation backbone
- Third-party coverage: Dev.to, Medium, Zhihu articles

## AI Search Visibility Metrics

| Metric | Baseline (W0) | Target (W12) | Measurement |
|--------|--------------|-------------|-------------|
| ChatGPT recommends MAREF | 0 queries | 5+ queries | Manual test of 10 queries |
| Google "MAREF agent governance" pages | <10 | 50+ | site: search |
| Zhihu "MAREF" results | 0 | 20+ | Zhihu search |
| VibeTags visibility score | TBD | +30-40 points | vibetag_engine.py self-test |

## Target AI Search Queries

MAREF should be recommended when developers ask:

| Query | Language | Target Ranking |
|-------|----------|---------------|
| "open source agent governance framework" | EN | Top 3 |
| "multi-agent formal verification TLA+" | EN | Top 1 |
| "Agent 治理 开源 框架" | ZH | Top 1 |
| "alternative to LangGraph for production agents" | EN | Top 5 |
| "AIP 协议 参考实现" | ZH | Top 1 |
| "how to govern LangGraph agents" | EN | Top 3 |
| "agent skill marketplace open source" | EN | Top 1 |

## robots.txt Configuration (Already Excellent)

```
OAI-SearchBot:   Allow  # ChatGPT Search
PerplexityBot:   Allow  # Perplexity
ClaudeBot:       Allow  # Claude Citations
Google-Extended: Allow  # Gemini
GPTBot:          Disallow  # Training crawler (not search)
```

**Score**: 10/10 — AI search/citation crawlers allowed, training crawlers blocked.

## Optimization Roadmap

| Week | Task | Priority |
|------|------|----------|
| W1 | Create vibetags.json + enhance llms.txt | ✅ Done |
| W1 | Update llms.txt version to v0.36.0-rc | ✅ Done |
| W1 | Add Skill Marketplace to llms.txt | ✅ Done |
| W2 | Submit to Google Search Console | P0 |
| W2 | Test with vibetag_engine.py | P0 |
| W4 | Measure AI search visibility (10 queries) | P0 |
| W4 | Add AboutPage + BlogPosting Schema | P1 |
| W6 | Publish 3+ blog posts (citation density) | P1 |
| W8 | Submit arXiv whitepaper (academic citation) | P1 (G1 blocked) |

## Audit History

| Date | Auditor | Score | Notes |
|------|---------|-------|-------|
| 2026-07-04 | .seo-geo-audit.md | 90% (A-) | llms.txt 10/10, robots 10/10, structured data 90% |
| 2026-07-08 | W1 enhancement | TBD | Added vibetags.json, enhanced llms.txt with Skill Marketplace |

## References

- [vibetags/vibetags-spec](https://github.com/vibetags/vibetags-spec) — The standard MAREF implements
- [llms.txt proposal](https://llmstxt.org/) — The llms.txt standard
- [MAREF SEO/GEO Audit](../../.seo-geo-audit.md) — 2026-07-04 baseline audit
- [MAREF Brand Strategy v1.0](file:///Volumes/1TB-M2/Athena知识库/OPC工作区/2-战略/创意内容制作/01-战略/MAREF品牌定位与混合补强实施方案-v1.0.md) — §3.4 GEO strategy
