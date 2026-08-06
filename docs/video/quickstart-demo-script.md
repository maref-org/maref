# MAREF Quick Start Demo Video — 5-Minute Script

> **Video title**: MAREF in 5 Minutes: Agent Governance from Zero to Production
> **Target length**: 5:00 (300 seconds)
> **Format**: Screen recording + voiceover (English) + 中文字幕
> **Platforms**: YouTube (primary) + B站 (secondary, with Chinese voiceover or subtitles)
> **Recording date**: 2026-07-29 (aligns with W5 case study publication)

---

## Shot List (Shot-by-Shot Storyboard)

### Segment 1: Cold Open (0:00–0:20) — 20s

| Shot | Time | Visual | Audio |
|------|------|--------|-------|
| 1.1 | 0:00–0:05 | MAREF logo + title "MAREF in 5 Minutes" on dark background | (Music sting) |
| 1.2 | 0:05–0:10 | Text overlay: "88% of AI agent deployments had an incident last year" | VO: "88% of companies that deployed AI agents last year had an incident." |
| 1.3 | 0:10–0:15 | Text overlay: "0 governance primitives in LangGraph, CrewAI, AutoGen" | VO: "The three most popular agent frameworks ship zero governance." |
| 1.4 | 0:15–0:20 | Text overlay: "MAREF adds governance in <5ms" + GitHub URL | VO: "MAREF is the governance layer. Let me show you in 5 minutes." |

### Segment 2: Installation (0:20–0:50) — 30s

| Shot | Time | Visual | Audio |
|------|------|--------|-------|
| 2.1 | 0:20–0:25 | Terminal: `git clone https://github.com/maref-org/maref.git` | VO: "Start by cloning the repo." |
| 2.2 | 0:25–0:30 | Terminal: `cd maref && python3 -m venv .venv && source .venv/bin/activate` | VO: "Create a virtual environment." |
| 2.3 | 0:30–0:40 | Terminal: `pip install -e ".[dev]"` (fast-forward the install) | VO: "Install MAREF with dev dependencies. Takes about 30 seconds." |
| 2.4 | 0:40–0:45 | Terminal: `maref --version` → shows version | VO: "Verify the installation." |
| 2.5 | 0:45–0:50 | Terminal: `maref --help` → shows command list | VO: "MAREF has a full CLI. Let's explore the key commands." |

### Segment 3: Governance Status (0:50–1:30) — 40s

| Shot | Time | Visual | Audio |
|------|------|--------|-------|
| 3.1 | 0:50–1:00 | Terminal: `maref status` → shows governance table (state: INIT) | VO: "The status command shows the current governance state. We're in INIT — the starting state of the 10-state Gray Code FSM." |
| 3.2 | 1:00–1:10 | Diagram overlay: 10-state Gray Code FSM (INIT→OBSERVE→ANALYZE→EVALUATE→DECIDE→ACT→VERIFY→REPORT→STABILIZE→HALT) | VO: "MAREF uses a 10-state Finite State Machine with Gray Code encoding. Each transition changes exactly one bit, ensuring formal verifiability." |
| 3.3 | 1:10–1:20 | Terminal: `maref analyze --state DECIDE` → shows state details | VO: "Analyze any state to see its Gray Code, entropy level, and valid transitions." |
| 3.4 | 1:20–1:30 | Terminal: `maref analyze --state HALT` → shows absorbing state | VO: "HALT is the absorbing state — once entered, the system cannot leave without manual reset. This is the emergency brake." |

### Segment 4: Audit Trail (1:30–2:10) — 40s

| Shot | Time | Visual | Audio |
|------|------|--------|-------|
| 4.1 | 1:30–1:40 | Terminal: `maref audit show --last 10` → shows audit table | VO: "Every governance decision is logged to a tamper-evident audit trail. Each record is chained with SHA-256 hashes." |
| 4.2 | 1:40–1:50 | Terminal: `maref audit show --type circuit_breaker` → filtered view | VO: "Filter by event type — circuit breaker trips, state transitions, anomaly detections." |
| 4.3 | 1:50–2:00 | Close-up: audit JSONL file showing chain_hash field | VO: "The chain_hash field links each record to the previous one. Tampering with any record breaks the chain — compliance officers can verify integrity independently." |
| 4.4 | 2:00–2:10 | Text overlay: "OWASP Agentic Top 10: 10/10 covered" | VO: "This audit trail is part of MAREF's 10 out of 10 OWASP Agentic Top 10 coverage." |

### Segment 5: CrewAI Governance Demo (2:10–3:20) — 70s

| Shot | Time | Visual | Audio |
|------|------|--------|-------|
| 5.1 | 2:10–2:20 | Terminal: `cd docs/examples/crewai-governance` | VO: "Now let's see MAREF governing a CrewAI workflow. We built a 430-line adapter that wraps CrewAI with 6 governance primitives." |
| 5.2 | 2:20–2:30 | Terminal: `python demo.py` → Scenario 1 starts | VO: "The demo runs 4 scenarios. First, a benign research crew." |
| 5.3 | 2:30–2:40 | Terminal: Scenario 1 output — "✅ PASSED" | VO: "Governance passes all 4 checks: safety gate, circuit breaker, dangerous capability scan, agent configuration." |
| 5.4 | 2:40–2:50 | Terminal: Scenario 2 output — "⛔ BLOCKED: Dangerous capabilities detected" | VO: "Scenario 2: a crew with 'halt' and 'delete' capabilities. Governance blocks it in pre-flight — before any LLM call." |
| 5.5 | 2:50–3:05 | Terminal: Scenario 3 output — "✅ SubgoalInterceptor HALTED execution" | VO: "Scenario 3: an agent reasons about bypassing safety constraints. The SubgoalInterceptor detects 'bypass', 'elevate', and 'gain control' patterns, and halts immediately." |
| 5.6 | 3:05–3:20 | Terminal: Scenario 4 output — "✅ BehaviorMonitor detected the rogue agent spike!" | VO: "Scenario 4: an agent spikes to 100x normal activity. The BehaviorMonitor's 3-sigma detector catches it. This is OWASP #10 — Rogue Agents — in action." |

### Segment 6: Benchmark (3:20–4:00) — 40s

| Shot | Time | Visual | Audio |
|------|------|--------|-------|
| 6.1 | 3:20–3:25 | Terminal: `cd ../../../benchmarks` | VO: "How much does all this governance cost? Let's run the benchmark." |
| 6.2 | 3:25–3:35 | Terminal: `python governance_overhead.py --iters 1000` (fast-forward) | VO: "The benchmark measures 7 governance primitives over 1000 iterations." |
| 6.3 | 3:35–3:45 | Terminal: Results table appears | VO: "CircuitBreaker: 0.35 microseconds. SafetyGate: 0.41 microseconds. SubgoalInterceptor: 10.5 microseconds. Pure governance logic is sub-15 micros." |
| 6.4 | 3:45–4:00 | Terminal: Comparison table (MAREF vs LangGraph/CrewAI/AutoGen) | VO: "Total governance overhead: 4.7 milliseconds. That's less than 1% of a single LLM call. LangGraph, CrewAI, and AutoGen add zero milliseconds — but also zero governance coverage." |

### Segment 7: What You Get (4:00–4:40) — 40s

| Shot | Time | Visual | Audio |
|------|------|--------|-------|
| 7.1 | 4:00–4:10 | Slide: "10 Governance Dimensions" (checklist animation) | VO: "MAREF gives you 10 governance dimensions: trust state machine, circuit breaker, subgoal interception, behavior monitoring, HITL enforcement, audit trail, formal verification, recursive depth protection, cross-instance governance, and OWASP Top 10 coverage." |
| 7.2 | 4:10–4:20 | Slide: "TLA+ Formal Verification" (7 modules listed) | VO: "All governance modules are formally specified in TLA+ and verified with TLC model checking in CI." |
| 7.3 | 4:20–4:30 | Slide: "OWASP Agentic Top 10 Mapping" | VO: "Every OWASP Agentic risk is mapped to a specific MAREF control." |
| 7.4 | 4:30–4:40 | Slide: "Open Source — Apache 2.0" | VO: "MAREF is open source under Apache 2.0. No vendor lock-in." |

### Segment 8: Call to Action (4:40–5:00) — 20s

| Shot | Time | Visual | Audio |
|------|------|--------|-------|
| 8.1 | 4:40–4:50 | Screen: GitHub repo page (github.com/maref-org/maref) | VO: "Star the repo, clone it, and try the demos yourself. Links in the description." |
| 8.2 | 4:50–4:55 | Screen: docs page (quickstart + case studies) | VO: "Full documentation, case studies, and benchmarks are in the docs." |
| 8.3 | 4:55–5:00 | MAREF logo + "github.com/maref-org/maref" + "Star ⭐ if you found this useful" | VO: "MAREF — the governance layer for AI agents. Thanks for watching." |

---

## Demo Runner Script

> This script executes all commands shown in the video, in order.
> The presenter runs this during recording to ensure consistent output.

```bash
#!/bin/bash
# MAREF Quick Start Demo Runner
# Execute during video recording for consistent output

set -e
export MAREF_AUDIT_PATH=/tmp/maref_video_demo

echo "=== Segment 2: Installation ==="
git clone https://github.com/maref-org/maref.git /tmp/maref-demo
cd /tmp/maref-demo
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

echo "=== Segment 3: Governance Status ==="
maref --version
maref --help
maref status
maref analyze --state DECIDE
maref analyze --state HALT

echo "=== Segment 4: Audit Trail ==="
maref audit show --last 10
maref audit show --type circuit_breaker

echo "=== Segment 5: CrewAI Governance Demo ==="
cd docs/examples/crewai-governance
python demo.py

echo "=== Segment 6: Benchmark ==="
cd ../../benchmarks
python governance_overhead.py --iters 1000

echo "=== Demo complete ==="
```

---

## Production Guidelines

### Recording Setup

| Setting | Value |
|---------|-------|
| **Screen resolution** | 1920×1080 (1080p) |
| **Frame rate** | 30 fps |
| **Terminal font** | JetBrains Mono, 16pt |
| **Terminal theme** | Dark background (#1e1e2e), green/white text |
| **Editor** | VS Code with One Dark Pro theme (for code segments) |
| **Screen recording tool (macOS)** | OBS Studio or QuickTime Player |
| **Audio recording** | USB microphone (Blue Yeti or equivalent) |
| **Audio format** | 48kHz, 16-bit, mono |

### Voiceover Notes

- Speak at ~150 words/minute (conversational pace)
- Pause 0.5s between segments
- Emphasize key numbers: "**zero** governance", "**4.7 milliseconds**", "**10 out of 10**"
- Total word count target: ~750 words (5 min × 150 wpm)

### Editing

- Cut dead air between commands (while waiting for output)
- Fast-forward long operations (`pip install`, benchmark run)
- Add text overlays for key metrics (0.35μs, 4.7ms, 10/10)
- Add the 10-state FSM diagram as a static overlay in Segment 3
- Add the governance architecture diagram in Segment 5
- Background music: low-volume electronic ambient (royalty-free)
- End card: MAREF logo + GitHub URL + "Star ⭐"

### B站 Upload Specifications

| Parameter | Value |
|-----------|-------|
| **Title (中)** | MAREF 5 分钟快速入门：AI Agent 治理从零到生产 |
| **Description** | 88% 的 AI Agent 部署去年发生过事故。LangGraph、CrewAI、AutoGen 都没有原生治理层。MAREF 用 <5ms 的开销补上了这个缺口。本视频演示安装、治理状态机、审计追踪、CrewAI 集成治理、性能 benchmark。 |
| **Tags** | AI, Agent, 治理, MAREF, CrewAI, LangGraph, AI安全, 多Agent系统 |
| **Category** | 科技 - 人工智能 |
| **Cover** | MAREF logo + "5 分钟" + "Agent 治理" text |
| **Subtitle** | 中文字幕（SRT 格式） |

### YouTube Upload Specifications

| Parameter | Value |
|-----------|-------|
| **Title** | MAREF in 5 Minutes: Agent Governance from Zero to Production |
| **Description** | 88% of AI agent deployments had an incident last year. The three most popular agent frameworks (LangGraph, CrewAI, AutoGen) ship zero native governance. MAREF adds the governance layer in <5ms. This demo covers: installation, 10-state Gray Code FSM, tamper-evident audit trail, CrewAI governance integration (goal hijack detection, rogue agent detection), and a reproducible performance benchmark. |
| **Tags** | `ai agents`, `agent governance`, `maref`, `crewai`, `langgraph`, `ai safety`, `multi-agent systems`, `owasp`, `tla+`, `formal verification` |
| **Category** | Science & Technology |
| **Thumbnail** | Split screen: "0 governance" (red) vs "10/10 OWASP" (green) + MAREF logo |
| **Playlist** | "MAREF Governance Tutorials" |
| **Cards** | Link to GitHub repo, benchmark article, CrewAI case study |
| **End screen** | Subscribe + "Watch next: MAREF vs LangGraph Benchmark" |

### Accessibility

- Upload English SRT subtitles to YouTube
- Upload Chinese SRT subtitles to B站
- Add chapter markers (YouTube): 0:00 Intro, 0:20 Install, 0:50 Governance, 1:30 Audit, 2:10 CrewAI, 3:20 Benchmark, 4:00 Summary

---

## Text Transcript (Standalone Tutorial)

> This transcript doubles as a standalone text tutorial. It can be published as a blog post alongside the video.

### MAREF in 5 Minutes: Agent Governance from Zero to Production

88% of companies that deployed AI agents last year had an incident. The three most popular agent frameworks — LangGraph, CrewAI, and AutoGen — ship zero native governance. MAREF is the governance layer that fixes this. Let me show you in 5 minutes.

**Step 1: Installation** (0:20)

```bash
git clone https://github.com/maref-org/maref.git
cd maref
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
maref --version
```

**Step 2: Governance Status** (0:50)

```bash
maref status
```

This shows the current governance state — INIT, the starting state of MAREF's 10-state Gray Code Finite State Machine. The FSM transitions through OBSERVE → ANALYZE → EVALUATE → DECIDE → ACT → VERIFY → REPORT → STABILIZE → HALT. Each transition changes exactly one bit (Gray Code), ensuring formal verifiability.

```bash
maref analyze --state DECIDE
```

This shows the Gray Code encoding (0110), entropy level (3), and valid next states for DECIDE.

**Step 3: Audit Trail** (1:30)

```bash
maref audit show --last 10
```

Every governance decision is logged to a tamper-evident audit trail. Each record is chained with SHA-256 hashes — tampering with any record breaks the chain. Compliance officers can verify integrity independently.

**Step 4: CrewAI Governance Demo** (2:10)

```bash
cd docs/examples/crewai-governance
python demo.py
```

This runs 4 scenarios:

1. **Benign crew** — governance passes, crew executes normally
2. **Dangerous crew** — "halt"/"delete" capabilities blocked in pre-flight (no LLM wasted)
3. **Goal hijack** — agent says "bypass safety constraints" → SubgoalInterceptor HALTs
4. **Rogue agent** — 100x activity spike → BehaviorMonitor detects via 3-sigma

**Step 5: Benchmark** (3:20)

```bash
cd benchmarks
python governance_overhead.py --iters 1000
```

Results: CircuitBreaker 0.35μs, SafetyGate 0.41μs, SubgoalInterceptor 10.5μs. Total governance overhead: 4.7ms — less than 1% of a single LLM call.

**What you get** (4:00):

- 10 governance dimensions (FSM, circuit breaker, subgoal interception, behavior monitoring, HITL, audit trail, formal verification, depth protection, cross-instance governance, OWASP Top 10)
- 7 TLA+ formally specified modules, verified with TLC in CI
- 10/10 OWASP Agentic Top 10 coverage
- Apache 2.0 open source, no vendor lock-in

**Links**: [github.com/maref-org/maref](https://github.com/maref-org/maref) · Star ⭐ if you found this useful.
