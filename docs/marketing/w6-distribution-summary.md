# W6 Distribution Summary

> **Week**: W6 (2026-07-09)
> **Deliverables**: Quick Start video script + creative-automation case study + PMM positioning validation report
> **Platforms**: B站 + YouTube (video) · GitHub Discussions + Twitter/X (case studies)

---

## Deliverable 1: 5-Minute Quick Start Demo Video

**Asset**: [`docs/video/quickstart-demo-script.md`](../video/quickstart-demo-script.md)

### B站 (Chinese audience)
- **Title**: MAREF 5 分钟快速上手 — Agent 治理操作系统 Demo
- **Category**: 科技 - 人工智能
- **Tags**: MAREF, Agent治理, 多Agent系统, TLA+, 开源框架, AI安全
- **Subtitles**: SRT (Chinese) — included in script
- **Description template**: included in script

### YouTube (English audience)
- **Title**: MAREF Quick Start — 5-Minute Demo of Agent Governance OS
- **Tags**: agent governance, multi-agent, TLA+, open source, AI safety, LangGraph, CrewAI
- **Chapter markers**: 8 segments (included in script)
- **Cards**: link to GitHub repo, quickstart docs

### Distribution checklist
- [ ] Record screencast per storyboard (8 segments, 0:00-5:00)
- [ ] Record voiceover (~750 words, 150 wpm)
- [ ] Edit: cut dead air, fast-forward installs
- [ ] Export 1920×1080 30fps MP4
- [ ] Generate SRT subtitles (Chinese for B站, English for YouTube)
- [ ] Upload to B站 with Chinese title/tags
- [ ] Upload to YouTube with English title/tags + chapter markers
- [ ] Pin video to GitHub repo README
- [ ] Post trailer clip to Twitter/X (30s, cold-open segment)

---

## Deliverable 2: Creative-Automation Case Study

**Asset**: [`docs/case-studies/creative-automation/README.md`](../case-studies/creative-automation/README.md)

### Twitter/X Thread (5 tweets)

**1/5**
We adapted @alexbeattie's creative-automation-pipeline as a MAREF Skill — adding 4 governance primitives without changing the deterministic composition contract.

The result: brand config is code, drift is contained, every asset is reproducible. 🧵

**2/5**
The upstream pipeline builds deterministic image prompts from brand_profile.yaml + locale + channel. Excellent design, but no governance layer:

- No audit trail
- No safety gate
- No circuit breaker
- No tamper-evidence

A drifted brand_profile can silently produce hundreds of off-brand images.

**3/5**
The MAREF adaptation adds:
1. SafetyGate — restricted_phrases become deny-rules
2. CircuitBreaker — 3 consecutive blocks HALT the profile
3. AuditTrail — SHA-256 hash chain
4. Version pinning — profile_version pinned in every audit record

**4/5**
We hit a real governance-precision bug: the brand voice said "no 'revolutionary' claims" — and SafetyGate blocked it because "revolutionary" appeared in the prompt.

Same family as the W5 "rm" in "information" bug. Fix: don't mention banned words in descriptions of what to avoid.

**5/5**
The demo runs 4 scenarios with no LLM API key:
- Benign brief composes ✓
- Restricted phrase blocked ✓
- CircuitBreaker HALTs after 3 blocks ✓
- Audit trail tamper-evident ✓

Governance overhead: <0.001% of image-gen time.

https://github.com/maref-org/maref/tree/main/docs/case-studies/creative-automation

### GitHub Discussions post
- **Category**: Show & Tell
- **Title**: Case Study — Governing a Creative-Automation Pipeline with MAREF
- **Body**: Summary of the case study + link to full README + demo reproduction instructions

---

## Deliverable 3: MAREF Positioning Validation Report

**Asset**: [`docs/case-studies/maref-positioning-validation-report.md`](../case-studies/maref-positioning-validation-report.md)

### Twitter/X Thread (4 tweets)

**1/4**
We ate our own dog food: ran MAREF's PMM Research Skills against MAREF's own positioning.

3 studies, 21 questions, 1 honest report. 🧵

**2/4**
Positioning scorecard (self-assessment, 1-5):
- Competitive alternatives: 5/5 (names LangGraph, CrewAI, AutoGen)
- Value resonance: 5/5 (concrete verbs: verify, audit, govern)
- Market category: 5/5 ("OS")
- Differentiation: 5/5 (TLA+ formal verification)
- Adoption barriers: 3/5 ⚠️ (requires real panel study)

**3/4**
The Skills surfaced 5 landmine questions sales must prepare for:
- "If LangGraph adds governance, why do I need MAREF?"
- "TLA+ sounds academic — show me a production incident it would have prevented"
- "Do we have to rip out our existing stack?"

**4/4**
Honest limitation: this is self-assessment mode, NOT market validation. The Skills support panel_study mode with real persona responses — we'll re-run when we have a Ditto API key.

The easiest person to fool with a PMM study is yourself.

https://github.com/maref-org/maref/tree/main/docs/case-studies

### 知乎 summary (Chinese)
- **Title**: MAREF 定位验证报告 — 用自己的 PMM Skill 验证自己的定位
- **Summary**: 我们用 MAREF 的 3 个 PMM 研究 Skill（定位验证、信息测试、竞争情报）对 MAREF 自身的定位进行了自评估。定位结构得分 4.5/5，但采纳障碍维度只有 3/5 — 需要真实用户面板才能验证。诚实地标注了"自评估 ≠ 市场验证"。

---

## Cross-Promotion

- Pin the video to GitHub repo README
- Link the creative-automation case study from the Skill marketplace docs
- Link the positioning validation report from the brand-building skills README
- Reference both case studies in the W7 "Skill 市场的三 gates 准入设计" article (next week)

## Distribution Checklist

- [ ] Record and upload video to B站 + YouTube
- [ ] Post creative-automation Twitter thread (Tuesday 9am PT)
- [ ] Post GitHub Discussions "Show & Tell" for creative-automation
- [ ] Post positioning validation Twitter thread (Thursday 9am PT)
- [ ] Post 知乎 summary (positioning validation, Chinese)
- [ ] Update README with video link
- [ ] Update Skill marketplace docs with case study links
