# W9 Distribution Assets: MAREF Skill Marketplace vs MCP Marketplace

> **W9 Deliverable**: 对比评测文章 + 代码对比脚本
> **Paths**: `docs/case-studies/maref-vs-mcp/`

---

## A. GitHub Discussions Post

**Category**: `Ideas & Feedback`
**Title**: `MCP Has a Marketplace, but No Governance — MAREF Has Both`

**Post body**:

---

The Model Context Protocol (MCP) launched its official marketplace in Sept 2025. It quickly became the standard for agent-tool discovery. But there's a design gap that matters for anyone building autonomous agents:

**The MCP Marketplace is a meta-registry that authenticates namespace ownership — not code safety.**

This isn't speculation. Here's what the MCP specification actually says vs. what MAREF actually implements:

### MCP Marketplace
- Registration = GitHub OAuth or DNS proof
- No code scanning, no sandbox, no human review
- Delegates to npm/PyPI/Docker (inheriting their supply chain risks)
- 50+ CVEs catalogued (CVE-2025-6514: CVSS 9.6, 437K downloads)
- OWASP MCP Top 10: avg score 34/100, 84.2% tool poisoning success rate

### MAREF Skill Marketplace
- Three-gate admission: static scan → sandbox test → manual review
- Reputation tracking with decay + security violation penalties
- Version negotiation with 90-day backward compatibility
- Dependency conflict detection
- Runtime governance: `MCPGovernance` pipeline wraps policy + circuit breaker + audit + HITL around every MCP tool call

### The Relationship
MAREF doesn't compete with MCP — it wraps governance around it. The `MCPToA2ABridge` exports MCP tools as governed skills, adding trust to discovery.

**Full article** (code-level, 2000+ words, with tables): [maref-vs-mcp/maref-skill-marketplace-vs-mcp-marketplace.md](https://github.com/maref-org/maref/blob/main/docs/case-studies/maref-vs-mcp/maref-skill-marketplace-vs-mcp-marketplace.md)

**Runnable code comparison** (standard library only): [maref-vs-mcp/code-comparison.py](https://github.com/maref-org/maref/blob/main/docs/case-studies/maref-vs-mcp/code-comparison.py)

```bash
curl -O https://raw.githubusercontent.com/maref-org/maref/main/docs/case-studies/maref-vs-mcp/code-comparison.py
python3 code-comparison.py
```

**Questions for discussion:**
1. Does the MCP ecosystem need a mandatory security gate, or is runtime sandboxing by the host sufficient?
2. MAREF's sandbox Gate 2 is currently a stub (gVisor/Firecracker planned). What's the right sandboxing strategy for agent skills?
3. Should the MCP registry itself adopt static scanning, or is a meta-registry the right design choice?
4. For agent frameworks: is runtime governance (policy + CB + audit) more important than pre-admission gates?

---

**Tags**: `mcp`, `skill-marketplace`, `governance`, `supply-chain-security`, `comparison`

---

## B. 知乎文章摘要

**标题**: MCP 有市场，但没有治理 — MAREF 两者都有

**摘要**:

MCP（Model Context Protocol）是 Anthropic 推出的 Agent-工具通信协议，2025 年 9 月上线官方注册中心后迅速成为行业标准。但 MCP Marketplace 的设计有一个根本性缺口：**它验证的是命名空间所有权，而不是代码安全性。**

这不是猜测，而是可测量的现实：50+ 个 CVE 漏洞（CVE-2025-6514：CVSS 9.6，437K 下载量）、OWASP MCP Top 10 平均得分 34/100、工具投毒成功率 84.2%、200K+ 未沙箱化的 STDIO 实例。

MAREF 的方法不同：它在同一 MCP 协议之上封装了治理层。每个 Skill/工具必须通过三道准入闸门（静态扫描 → 沙箱测试 → 人工审查），运行时通过 MCPGovernance 管道（策略引擎 + 断路器 + HMAC-SHA256 审计 + HITL 路由）执行治理。

本文提供了完整的代码级对比：MCP 的 JSON-RPC 工具注册 vs MAREF 的 SkillManifest 三闸门注册，以及 MCPGovernance 管道的实际运行演示。

**链接**: [完整文章](https://github.com/maref-org/maref/blob/main/docs/case-studies/maref-vs-mcp/maref-skill-marketplace-vs-mcp-marketplace.md)

---

## C. Distribution Checklist

- [ ] **GitHub Discussions**: 发布到 `maref-org/maref` Discussions → Ideas & Feedback
- [ ] **知乎**: 发布中文摘要 → AI/Agent 治理专栏
- [ ] **Twitter/X**: 3-tweet thread:
  - Tweet 1: "MCP Marketplace verifies namespace ownership, not code safety. 50 CVEs later, the gap is measurable."
  - Tweet 2: "MAREF's three-gate admission + MCPGovernance pipeline wraps trust around MCP tool calls."
  - Tweet 3: "They're complementary: MCP handles discovery, MAREF handles trust. Link to code comparison ↓"
- [ ] **Hacker News**: 适合 Show HN / 讨论帖
- [ ] **Reddit r/MachineLearning**: 技术深度帖
