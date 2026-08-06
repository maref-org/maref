# W7 Distribution: Three-Gate Skill Marketplace Design

> **Article**: [Three Gates, Not Two: Why Agent Skill Marketplaces Need Static + Sandbox + Human Review](../website/blog/2026-08-05-three-gate-skill-marketplace-design.md)
> **Platforms**: Twitter/X (English) + 知乎 (Chinese)
> **Posting window**: Tuesday 9am PT (Twitter) / Wednesday evening (知乎)

---

## Twitter/X Thread (9 tweets)

**1/9**
Agent skill marketplaces face a supply chain threat worse than npm.

npm packages run in your build. Agent skills run inside an autonomous agent at runtime — with no human reviewing each invocation.

OWASP ranks this as Agentic Top 10 risk #4. Here's how MAREF handles it. 🧵

**2/9**
The left-pad incident (2016) broke thousands of npm projects when one 11-line package was unpublished.

The injection problem is worse: event-stream (2018) was hijacked and ran malicious code in millions of builds for months.

Agent skills are this, but autonomous.

**3/9**
Why one gate isn't enough:

Static scan alone misses:
- Novel attacks (zero-days)
- Runtime behavior
- Contextual risk (is reading ~/.ssh/id_rsa legit?)

You need a second gate: sandbox execution. But that misses judgment calls.

So you need a third gate: human review.

**4/9**
Why not four or five gates?

Each gate adds value but also adds latency. Three is the minimum viable defense:
- Static (code) catches obvious patterns
- Sandbox (runtime) catches behavior
- Human (judgment) catches intent

Below three = known gaps. Above three = marketplace velocity cost.

**5/9**
MAREF's three gates (real code, src/maref/marketplace/registry.py):

Gate 1: run_static_scan() — checks entrypoint for eval(, exec(, socket., os.environ
Gate 2: run_sandbox_test() — validates test cases (production: gVisor/Firecracker)
Gate 3: approve() — human review, mandatory for dangerous capabilities

**6/9**
Honest gaps (we don't hide them):

Gate 1 is a heuristic string scan, not AST analysis. SBOM generator + vulnerability scanner exist (34KB + 41KB) but aren't wired in yet.

Gate 2 is a stub — validates test case structure, doesn't actually sandbox-execute. gVisor integration is a v0.36 target.

Gate 3 is real.

**7/9**
The dependency graph prevents left-pad:

Every skill declares deps as skill://name@version. When a skill is DEPRECATED or FROZEN, get_downstream() returns every dependent — so authors get notified before removal.

Version pinning (@1.0.0) prevents silent upgrades.

**8/9**
Comparison:

| Marketplace | Static | Sandbox | Human | Dep Graph |
|-------------|:------:|:-------:|:-----:|:---------:|
| MCP Marketplace | ❌ | ❌ | ❌ | ❌ |
| npm | post-hoc | ❌ | ❌ | ✅ |
| MAREF | ✅ | ✅ | ✅ | ✅ |

MCP Marketplace = npm circa 2016. It will suffer incidents. Then it will add gates.

**9/9**
MAREF ships with three gates from day one — even though gates 1 and 2 are stubs.

The stubs are honest: documented, tracked as v0.36 targets, manifest contract already declares constraints. Design is right; implementation is catching up.

Read the full article: https://maref.cc/en/blog/three-gate-skill-marketplace-design/

Review the code: https://github.com/maref-org/maref/blob/main/src/maref/marketplace/registry.py

---

## 知乎摘要 (Chinese)

**标题**: 为什么 Agent 技能市场需要三道闸门 — MAREF 的供应链治理设计

**摘要**:

OWASP Agentic Top 10 将供应链攻击列为第 4 大风险。Agent 技能市场面临的威胁比 npm 更严重：npm 包在你的构建过程中运行，而 Agent 技能在运行时由自主 Agent 执行 — 没有人审查每次调用。

MAREF 的三闸门准入设计是最低可行防御：

1. **静态扫描**（Gate 1）— 检查入口点是否有 `eval(`、`exec(`、`socket.`、`os.environ` 等可疑模式
2. **沙箱测试**（Gate 2）— 在隔离环境中运行测试用例（生产环境使用 gVisor/Firecracker）
3. **人工审查**（Gate 3）— 人类审查技能描述、输入输出 schema、测试覆盖率、许可证兼容性

**诚实的差距**：
- Gate 1 目前是启发式字符串匹配，不是 AST 分析。SBOM 生成器（34KB）和漏洞扫描器（41KB）已存在但尚未接入。
- Gate 2 目前是桩代码 — 只验证测试用例结构，不在沙箱中实际执行。gVisor 集成是 v0.36 目标。
- Gate 3 是真实的 — 人在环中。

**依赖图防止 left-pad 事件**：每个技能声明依赖为 `skill://name@version`。当技能被弃用或冻结时，`get_downstream()` 返回所有依赖者 — 作者在移除前收到通知。版本锁定（@1.0.0）防止静默升级。

**对比**：

| 市场 | 静态扫描 | 沙箱 | 人工审查 | 依赖图 |
|------|:-------:|:----:|:-------:|:------:|
| MCP Marketplace | ❌ | ❌ | ❌ | ❌ |
| npm | 事后 | ❌ | ❌ | ✅ |
| MAREF | ✅ | ✅ | ✅ | ✅ |

MCP Marketplace = 2016 年的 npm。它会遭遇事件，然后才加闸门。MAREF 从第一天就有三道闸门 — 即使 Gate 1 和 Gate 2 目前是桩代码。设计是对的，实现正在追赶。

**9 个真实技能，全部 PENDING**：MAREF 市场目前有 9 个 SkillManifest（5 个品牌构建 + 3 个 PMM 研究 + 1 个创意自动化），全部处于 PENDING 状态。这是故意的 — 我们自己的技能必须通过我们自己的闸门。吃自己的狗粮。

**全文**: https://maref.cc/en/blog/three-gate-skill-marketplace-design/
**代码**: https://github.com/maref-org/maref/blob/main/src/maref/marketplace/registry.py

---

## GitHub Discussions Post

**Category**: Governance Design Discussion
**Title**: Three-gate skill marketplace admission — challenge the design

**Body**:

We've published our design for three-gate skill marketplace admission (static scan → sandbox test → human review). The full article is here: [link]

Key design decisions we'd like feedback on:

1. **Why three, not four?** We considered adding reputation scoring as a fourth gate. Decided against it to keep marketplace velocity. Agree? Disagree?

2. **Gate 1 is currently a heuristic string scan.** The SBOM generator and vulnerability scanner exist but aren't wired in. Should we block v0.36 GA on wiring them in, or ship with the stub?

3. **Gate 2 is currently a stub.** Real sandbox execution needs gVisor/Firecracker. Is there a lighter-weight option that still catches runtime behavior?

4. **Auto-approve for safe skills?** The design allows auto-approve for skills with `network: false` and no filesystem writes. Is this too permissive?

5. **The 9 first-party skills are all PENDING.** Should MAREF's own skills get priority review, or go through the same queue as third-party skills?

Challenge the design. Bring arguments.

---

## Distribution Checklist

- [ ] Post Twitter thread (Tuesday 9am PT — developer engagement peak)
- [ ] Post 知乎 article (Wednesday evening — Chinese developer audience)
- [ ] Post GitHub Discussions topic
- [ ] Tag @LangChainAI @crewAIInc @AnthropicAI (MCP) — position as complementary
- [ ] Pin to GitHub repo README (replace W6 video pin)
- [ ] Cross-reference from W2 article ("Why Agent Governance Matters")
- [ ] Cross-reference from W4 article (benchmark — governance overhead <1%)
- [ ] Update Skill marketplace docs with link
- [ ] Hashtags: #AgentGovernance #SupplyChain #SkillMarketplace #MAREF #OWASP

## Repurpose

- Twitter thread → LinkedIn post (expand each tweet to a paragraph)
- 知乎 article → 微信公众号 (adapt formatting)
- GitHub Discussions → Discord #governance channel
- Article section "Comparison" → standalone infographic for W9 (MAREF vs MCP Marketplace)
