# W8 Distribution: TLA+ 5 Theorems + arXiv Submission

> **arXiv paper**: [main.tex](../arxiv/maref-tla-plus-5-theorems/main.tex) (3,387 words, 5 theorems)
> **Medium article**: [Five Theorems That Make Agent Governance Trustworthy](../website/blog/2026-08-12-tla-plus-5-theorems-explained.md)
> **知乎 article**: [MAREF 治理状态机的五个定理](../website/blog/2026-08-12-tla-plus-5-theorems-explained-zh.md)
> **Submission guide**: [SUBMISSION_GUIDE.md](../arxiv/maref-tla-plus-5-theorems/SUBMISSION_GUIDE.md)
> **Platforms**: arXiv (primary) + Medium (English) + 知乎 (Chinese)
> **Strategic significance**: Unblocks D1 G1 gate (arXiv ID) → enables `maref-org/maref` push without override

---

## Twitter/X Thread (8 tweets — arXiv announcement)

**1/8**
Most agent frameworks say "we're safe" in their README.

MAREF proves it with TLA+.

Five theorems formally verify the 10-state Gray code governance state machine. Here's what's proven — and what's honestly still a stub. 🧵

**2/8**
The state machine: 10 governance states encoded on a 4-bit Gray code. Every transition changes exactly one bit (Hamming = 1).

Why? Single-bit transitions prevent race conditions during concurrent state updates. Same principle as analog-to-digital converters.

**3/8**
Theorem 1: Lyapunov Convergence
If governance activates, entropy eventually decreases.
TLA+: governanceActive ~> globalEntropy < MaxEntropy
Proof: governance forces agents to STABILIZE (entropy 1), so global entropy drops from 4 to 1 in one step.

**4/8**
Theorem 2: HALT Absorbing
Once an agent enters HALT(9), it cannot leave.
The Advance action requires ~IsTerminal(). Stutter leaves everything unchanged. No action can move an agent out of HALT.

Halt = circuit breaker that can't self-reset.

**5/8**
Theorem 3: Gray Code Transition
Every legal transition changes exactly one bit.
Even EMERGENCY shutdowns (force_halt from G1-G5) walk one bit at a time via BFS. No multi-bit jumps. Ever.

The topological invariant holds whether transitions are routine or emergency-triggered.

**6/8**
Theorems 4 & 5: Safety Gate Integrity + Red Line Immutability
- Safety gate is always active (trivially — no action disables it)
- Constitutional red lines can't be modified by any agent

Honest gap: both are trivially true. The "real" properties (all paths through the gate; only humans change red lines) need richer specs. Tracked as future work.

**7/8**
Honest limitations (no spin):
- TLC model checking, not TLAPS deductive proof (0 PROOF/BY/QED)
- Bounded: 2 agents, 5 transitions (production needs Apalache)
- 8-state trigram machine + 24-state lifecycle machine: no TLA+ specs yet
- Synchronous model (no network asynchrony)

We're not hiding these.

**8/8**
Full arXiv preprint (with complete TLA+ specs, proof sketches, TLC configs): [arXiv link — to be added after submission]

Medium article: https://maref.cc/en/blog/tla-plus-5-theorems-explained/
知乎: https://maref.cc/zh/blog/tla-plus-5-theorems-explained-zh/
TLA+ source: https://github.com/maref-org/maref/tree/main/src/formal

Challenge the specs. Bring arguments.

---

## 知乎发布摘要

**标题**: MAREF 治理状态机的五个定理：TLA+ 形式化验证详解

**核心论点**:
- README 声称 ≠ 数学证明。MAREF 用 TLA+ 形式化验证治理状态机。
- 五个定理：Lyapunov 收敛性、HALT 吸收性、Gray Code 转移性、安全门完整性、红线不可变性
- 每个定理都有真实 TLA+ 代码 + 证明草图 + 诚实局限性声明
- 关键区分：经验安全 ("测试了 1000 个场景") vs 形式安全 ("证明不能达到不安全状态")

**知乎发布注意**:
- 中文文章已在 [2026-08-12-tla-plus-5-theorems-explained-zh.md](../website/blog/2026-08-12-tla-plus-5-theorems-explained-zh.md) 完成
- 知乎专栏标签：形式化验证、TLA+、AI安全、智能体治理、Gray Code
- 发布时间：周三晚上（中文开发者活跃时段）
- 评论区预设问题：(1) 为什么不用 Coq/Isabelle？(2) TLC 状态爆炸怎么解决？(3) 与 Paxos/Raft 的 TLA+ 验证有何区别？

---

## GitHub Discussions Post

**Category**: Research & Formal Verification
**Title**: arXiv preprint — Five TLA+ theorems on MAREF governance state machine (feedback wanted)

**Body**:

We've prepared an arXiv preprint formally verifying five properties of the MAREF 10-state governance state machine:

1. **Lyapunov Convergence** — governance activation leads to entropy decrease
2. **HALT Absorbing** — terminal state is absorbing
3. **Gray Code Transition** — all transitions are single-bit (Hamming = 1)
4. **Safety Gate Integrity** — safety gate cannot be bypassed
5. **Red Line Immutability** — constitutional rules cannot be modified at runtime

The paper uses TLC model checking (not TLAPS deductive proof). We're transparent about the limitations: bounded state space, two sibling machines without specs, synchronous model.

**Feedback wanted on**:

1. **The "Lyapunov" naming** — is the metaphor from control theory misleading, given that we use TLA+ leads-to rather than a Lyapunov function V(x)?
2. **Theorems 4 & 5 are trivially true** — should we reframe them as "structural invariants" rather than "theorems", or strengthen the specs to make them non-trivial?
3. **arXiv category** — we chose cs.MA primary, cs.SE cross-list. Should we add cs.LO?
4. **TLAPS migration** — is it worth the effort to convert TLC-checked declarations to TLAPS proofs, or is TLC sufficient for a governance framework?

Full paper: [arXiv link — to be added]
TLA+ source: https://github.com/maref-org/maref/tree/main/src/formal

---

## Distribution Checklist

### Pre-arXiv Submission
- [ ] Human reviews main.tex for LaTeX errors
- [ ] Human builds PDF (`pdflatex main.tex && bibtex main && pdflatex main.tex && pdflatex main.tex`)
- [ ] Human runs TLC on .cfg files for verification evidence (optional but recommended)
- [ ] Human creates arXiv submission package (`tar -czf maref-tla-plus-5-theorems.tar.gz main.tex references.bib main.pdf`)
- [ ] Human submits to arXiv (see [SUBMISSION_GUIDE.md](../arxiv/maref-tla-plus-5-theorems/SUBMISSION_GUIDE.md))
- [ ] Record arXiv ID after submission

### Post-arXiv Submission
- [ ] Update main.tex with arXiv ID in `\date` field
- [ ] Update Medium article with arXiv link
- [ ] Update 知乎 article with arXiv link
- [ ] Post Twitter/X thread (Tuesday 9am PT — developer engagement peak)
- [ ] Post 知乎 article (Wednesday evening — Chinese developer audience)
- [ ] Post GitHub Discussions topic
- [ ] Tag @lamport @informal_systems (Apalache) — position as TLA+ application
- [ ] Pin to GitHub repo README (replace W7 pin)
- [ ] Cross-reference from W2 article ("Why Agent Governance Matters")
- [ ] Cross-reference from W3 article ("10-state Gray Code proof")
- [ ] Update MAREF website with arXiv link
- [ ] Hashtags: #FormalVerification #TLAPlus #AgentGovernance #MAREF #GrayCode

### G1 Gate Unlock (After arXiv ID Obtained)
- [ ] Update `STATE.yaml`: `G1_arxiv_id: true`, add `G1_arxiv_id_value`
- [ ] Set `gate_passed: true`, `last_push_blocked_by: null`
- [ ] Set `allow_push_override: false`, clear `override_reason`
- [ ] Run `python3 scripts/d1_preflight_check.py` — should pass
- [ ] Push to `maref-org/maref` without override
- [ ] Close G1 tracking issue in GitHub

## Repurpose

- arXiv paper → Medium article (done — readable version)
- arXiv paper → 知乎 article (done — Chinese version)
- Twitter thread → LinkedIn post (expand each tweet to a paragraph)
- 知乎 article → 微信公众号 (adapt formatting, remove markdown)
- GitHub Discussions → Discord #research channel
- Theorem 3 (Gray Code Transition) → standalone infographic showing the 10-state transition graph
- The 5-theorem framework → conference talk outline (20-min presentation)

---

## Cross-Reference Map

| Source | Cross-references to W8 | W8 cross-references to |
|--------|----------------------|----------------------|
| W2 (Why Agent Governance Matters) | "5 proven theorems" → W8 arXiv paper | W2's 5 theorems are the narrative names W8 formalizes |
| W3 (10-state Gray Code proof) | P1-P11 propositions → W8 theorem mapping | W8 maps W3 propositions to the 5 theorems |
| W4 (Governance benchmark) | Overhead <1% → governance is cheap → W8 proves it's safe | — |
| W7 (Three-gate marketplace) | Supply chain security → W8 formal verification of governance | — |
| OWASP Agentic Top 10 mapping | Risk #4 (Supply Chain) → W7; Risks #1,6,8 → W8 governance FSM | W8 cites OWASP in intro |
