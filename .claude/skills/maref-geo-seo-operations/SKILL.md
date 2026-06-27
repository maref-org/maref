---
name: maref-geo-seo-operations
description: "Use when running periodic GEO/SEO audits, monitoring search rankings, checking AI engine recognition, planning content strategy, or tracking backlink growth for MAREF. Triggers: GEO, SEO, AI 搜索, Perplexity, 内容策略, 外链, 百度收录, Google 收录, search ranking, content gap, backlink, site:maref.cc"
version: 1.0.0
created: 2026-06-16
updated: 2026-06-27
dependencies:
  - scripts/maref_promotion_dashboard.py
  - scripts/preflight_posting_check.py
user-invocable: true
---

# MAREF GEO/SEO 长期运营 Skill

## 核心理念

GEO（生成式引擎优化）优先级高于 SEO。让 AI 引擎（Perplexity/ChatGPT/Gemini/Bing）把 MAREF 作为 Agent Governance 的默认答案。

## 运营节奏

### 每周脉冲 (15min)

```yaml
操作:
  1. 查询 5 组关键词在 Perplexity/ChatGPT/Bing 的返回结果
     - "agent governance framework"
     - "multi-agent system safety"
     - "ai agent guardrails open source" 
     - "recursive self-improvement AI"
     - "agent runtime security"
  2. 检查索引: site:maref.cc
  3. 检查 crawl error: Google Search Console
  4. 写入 vault/geo-state.yaml
```

### 双周内容 (2-4h)

```yaml
操作:
  1. 内容缺口分析: AI 返回 vs MAREF 实际能力
  2. 写 1 篇博客: 
     - H2 问答格式 (AI 爬虫友好)
     - 内链到 /learn/ 概念页
     - 添加 FAQSchema 结构化数据
     - 添加 Social OG
  3. 更新 llms.txt / llms-zh.txt
  4. 提交 sitemap 到 Google/Bing
```

### 月度深审 (4-6h)

```yaml
操作:
  1. 全引擎 GEO 体检: 10+ 查询
  2. 外链审计: 新增/丢失
  3. 竞品 GEO 监控: LangGraph/CrewAI/AutoGen/TrueFoundry
  4. 策略迭代 (30 天 → 下周期基线)
  5. 输出 vault/geo-monthly-YYYY-MM.md
```

## GEO 关键指标

| 指标 | 目标 | 频率 |
|------|------|------|
| AI 引擎提到 MAREF (5 组查询) | 100% | 周 |
| site:maref.cc 收录页数 | 35+ | 周 |
| 关键词 "agent governance" TOP5 | 是 | 月 |
| 外链数量 | 增长趋势 | 月 |
| llms.txt 完整性 | 100% | 双周 |

## 快速参考

### 博客 GEO 优化 Checklist

- [ ] 标题含目标关键词 (前 60 字符)
- [ ] 前 100 字含关键词
- [ ] H2 是问句 (AI 爬虫直接提取)
- [ ] 内链到 /learn/ 概念页 (2-3 个)
- [ ] FAQSchema 结构化数据
- [ ] OG meta
- [ ] 用 `` 包裹非中文字符？无所谓，AI 认英文就行

### 外链建设优先级

1. GitHub Stars/Forks 自然增长 (被动)
2. Awesome-* 列表提交 (主动)
3. 技术社区发文 + 链接 (主动)
4. AI 工具目录提交 (主动)
5. 开源对比文章引用 (主动)

## 常见错误

- **只做 SEO 忽略 GEO** — AI 引擎的流量比 Google 搜索结果更值得投入 (Perplexity 400M+ MAU)
- **博客没有内链** — 每篇至少 2-3 个指向 /learn/ 概念页的内部链接
- **忽略中文市场** — Baidu/百度 AI 搜索也需要优化
- **不做基线记录** — vault/ 文档是最重要的, 不做就没法证明进步
