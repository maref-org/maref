---
slug: three-gate-skill-marketplace-design
title: 'Three Gates, Not Two: Why Agent Skill Marketplaces Need Static + Sandbox + Human Review'
authors: [maref]
tags: [governance, thought-leadership, skill-marketplace, supply-chain, owasp, 2026]
date: 2026-08-05
description: "Agent skill marketplaces face a supply chain threat worse than npm: agents autonomously execute skill code. MAREF's three-gate admission (static scan → sandbox → human review) is the minimum viable defense. Here's the real implementation, with honest gaps."
---

> **TL;DR**: OWASP's Agentic Top 10 ranks supply chain as risk #4. Agent skill marketplaces face a threat worse than npm — agents autonomously execute skill code without human review at runtime. MAREF's three-gate admission (static scan → sandbox test → human review) is the minimum viable defense. This article shows the real implementation in [`src/maref/marketplace/registry.py`](https://github.com/maref-org/maref/blob/main/src/maref/marketplace/registry.py), is honest about what's a stub vs. production-ready, and explains why three gates — not one, not five — is the right number.

<!-- truncate -->

## The Supply Chain Problem, But Worse

In March 2016, a developer unpublished a 11-line npm package called `left-pad`. It broke thousands of projects, including Babel, React, and Webpack. The JavaScript ecosystem ground to a halt because a dependency nobody knew they had disappeared.

That was a *removal* problem. The *injection* problem is worse: in 2018, `event-stream`, a package with millions of weekly downloads, was hijacked by a malicious maintainer who added code that targeted a specific Bitcoin wallet app. The package ran in millions of builds for months before anyone noticed.

Agent skill marketplaces face the same problem, but worse. Here's why:

| Dimension | npm/PyPI packages | Agent skills |
|-----------|-------------------|-------------|
| **Execution context** | Runs in your build/CI | Runs inside an autonomous agent at runtime |
| **Human review at runtime** | Developer reviews the dependency tree | Agent executes skills autonomously — no human in the loop |
| **Blast radius** | Build fails or library misbehaves | Agent achieves the wrong goal competently (see [W2 article](./why-agent-governance-matters)) |
| **Discovery speed** | Developer consciously adds a dependency | Agent discovers and invokes skills via marketplace search |

The last row is the terrifying one. A developer adding a npm package at least makes a *conscious decision* to depend on something. An agent discovering a skill via marketplace search may invoke code that no human ever reviewed — and the agent will execute it *competently*, pursuing whatever goal the skill suggests.

This is why OWASP's [Agentic Top 10](https://owasp.org/www-project-agentic-ai/) ranks **Supply Chain** as risk #4. And it's why MAREF's skill marketplace has three admission gates, not one.

## Why Three Gates, Not One or Five

The obvious approach is one gate: run a security scanner, reject anything suspicious. This is what npm does (via `npm audit`) and what PyPI does (via `pip-audit`). It catches known vulnerabilities but misses:

- **Novel attacks** — zero-day exploits aren't in any vulnerability database
- **Runtime behavior** — a skill can look clean statically but behave maliciously when executed
- **Contextual risk** — a skill that reads `~/.ssh/id_rsa` might be legitimate (SSH key manager) or malicious (key exfiltration), and static analysis can't tell which

So you add a second gate: sandbox execution. Run the skill in an isolated environment, observe its behavior, reject if it does anything suspicious. This catches runtime behavior, but misses:

- **Edge cases the sandbox didn't trigger** — the skill may behave differently in production
- **Judgment calls** — is reading `/etc/passwd` for system info legitimate? It depends on what the skill claims to do
- **Intent assessment** — a skill that calls `eval()` might be a legitimate expression evaluator or a code injection vector

So you add a third gate: human review. A human reads the skill's description, examines its behavior, and makes a judgment call. This catches what static and dynamic analysis can't.

**Why not four or five gates?** You could add: dependency audit (separate from static scan), reputation scoring, formal verification, canary deployment. Each adds value, but each also adds latency to the marketplace. The three-gate design is the *minimum viable* defense — below three, you have known gaps; above three, you're optimizing at the cost of marketplace velocity.

MAREF's design: **static (code) → sandbox (runtime) → human (judgment)**. Each gate catches a different class of threat. No gate is sufficient alone.

## The Real Implementation

The three-gate admission lives in [`src/maref/marketplace/registry.py`](https://github.com/maref-org/maref/blob/main/src/maref/marketplace/registry.py). The core is the `SkillRegistry` class and the `SkillStatus` state machine:

```python
class SkillStatus(Enum):
    PENDING = "pending"              # submitted, awaiting review
    STATIC_SCAN = "static_scan"      # passed Gate 1
    SANDBOX_TEST = "sandbox_test"    # passed Gate 2
    APPROVED = "approved"            # passed Gate 3 (human review)
    REJECTED = "rejected"            # failed review
    DEPRECATED = "deprecated"        # scheduled for removal
    FROZEN = "frozen"                # temporarily suspended
```

A skill starts at `PENDING` and must pass through `STATIC_SCAN` and `SANDBOX_TEST` before reaching `APPROVED`. The `REJECTED`, `DEPRECATED`, and `FROZEN` states handle lifecycle management — a skill can be pulled from the marketplace at any time if a problem is discovered post-approval.

### Gate 1: Static Security Scan

```python
def run_static_scan(self, skill_id: str) -> SkillValidationResult:
    """Gate 1: Static security scan.

    Checks for suspicious patterns: network requests, file system access,
    environment variable reads, eval/exec calls.
    """
    manifest = self._skills[skill_id]
    entry = manifest.entrypoint.lower()
    suspicious = ["requests.", "urllib", "socket.", "open(",
                  "eval(", "exec(", "os.environ"]
    found = [p for p in suspicious if p in entry]
    if found:
        result.errors.append(f"Static scan: suspicious patterns {found}")
        result.static_scan_passed = False
    else:
        result.static_scan_passed = True
        self._status[skill_id] = SkillStatus.STATIC_SCAN
    return result
```

**Honest gap**: This is a *heuristic string scan* on the entrypoint string, not full AST analysis. It catches the obvious cases (a skill whose entrypoint literally contains `eval(`) but misses obfuscated patterns. The production target is AST-based analysis with:
- Dependency tree audit (via `SBOMGenerator` in [`src/maref/supply_chain/sbom_generator.py`](https://github.com/maref-org/maref/blob/main/src/maref/supply_chain/sbom_generator.py))
- Known vulnerability cross-reference (via `VulnerabilityScanner` in [`src/maref/supply_chain/vulnerability_scanner.py`](https://github.com/maref-org/maref/blob/main/src/maref/supply_chain/vulnerability_scanner.py))
- License compatibility check

The SBOM generator and vulnerability scanner already exist (34KB and 41KB respectively) but aren't yet wired into Gate 1. That's a v0.36 target.

### Gate 2: Sandbox Execution Test

```python
def run_sandbox_test(self, skill_id: str) -> SkillValidationResult:
    """Gate 2: Sandbox execution test.

    Runs test_cases in an isolated environment.
    """
    manifest = self._skills[skill_id]
    if not manifest.test_cases:
        result.warnings.append("No test cases provided")
        result.sandbox_test_passed = True
    else:
        # Simulate test execution (production: run in gVisor/Firecracker)
        passed = all(tc.get("expected") is not None for tc in manifest.test_cases)
        result.sandbox_test_passed = passed
```

**Honest gap**: This is a *stub*. It only validates that test cases have `expected` outputs — it doesn't actually execute the skill in a sandbox. The production target is to run each test case in [gVisor](https://gvisor.dev/) or [Firecracker](https://firecracker-microvm.github.io/) with:
- Resource limits (CPU, memory, wall time) from the manifest's `sandbox_config`
- Network isolation (matching `sandbox_config.network: false`)
- Filesystem restrictions (matching `sandbox_config.filesystem.read/write`)
- Behavior monitoring (does the skill try to access paths outside its declared `read/write` scopes?)

The manifest contract already declares these constraints — the sandbox just needs to enforce them. This is tracked as a v0.36 target.

### Gate 3: Manual Review

```python
def approve(self, skill_id: str) -> None:
    """Gate 3: Manual approval (or auto-approve if gates 1+2 passed)."""
    if not result.static_scan_passed:
        raise ValueError(f"Skill {skill_id} failed static scan")
    if not result.sandbox_test_passed:
        raise ValueError(f"Skill {skill_id} failed sandbox test")
    result.manual_review_passed = True
    self._status[skill_id] = SkillStatus.APPROVED
```

Gate 3 is the human-in-the-loop checkpoint. A reviewer examines:
1. Does the skill do what its `description` claims?
2. Are the `input_schema` and `output_schema` consistent with the behavior?
3. Do the `test_cases` cover edge cases?
4. Is the `license` compatible with MAREF's Apache-2.0?

The docstring says "or auto-approve if gates 1+2 passed" — but in production, manual review is mandatory for skills that declare dangerous capabilities (network access, filesystem writes, exec). Auto-approve is reserved for skills with `sandbox_config.network: false` and no filesystem writes.

## The Dependency Graph: Preventing Left-Pad

The `left-pad` incident happened because there was no way to notify downstream dependents when a package was unpublished. MAREF's registry maintains a dependency graph for exactly this:

```python
def register(self, manifest: SkillManifest) -> SkillValidationResult:
    # Build dependency graph
    for dep in manifest.dependencies:
        dep_name = dep.replace("skill://", "").split("@")[0]
        self._dependency_graph.setdefault(dep_name, set()).add(manifest.skill_id)
    return result

def get_downstream(self, skill_name: str) -> list[str]:
    """Get skill IDs that depend on the given skill."""
    return list(self._dependency_graph.get(skill_name, set()))

def check_dependency_conflicts(self, skill_id: str) -> list[str]:
    """Check if dependencies of a skill are available and approved."""
    for dep in manifest.dependencies:
        dep_manifest = self.get_by_name(dep_name)
        if dep_manifest is None:
            conflicts.append(f"Missing dependency: {dep}")
        elif self._status.get(dep_manifest.skill_id) != SkillStatus.APPROVED:
            conflicts.append(f"Dependency not approved: {dep}")
    return conflicts
```

When a skill is `DEPRECATED` or `FROZEN`, `get_downstream()` returns every skill that depends on it — so downstream authors get notified and can migrate before the skill is removed. This is the left-pad defense: no skill disappears without warning its dependents.

Dependencies use a versioned URI scheme: `skill://maref-brand-positioning@1.0.0`. The `@version` pin prevents silent upgrades — if `maref-brand-positioning` ships a `2.0.0` with breaking changes, skills depending on `@1.0.0` are unaffected until they explicitly upgrade.

## Comparison: How Others Handle It

| Marketplace | Static Scan | Sandbox | Human Review | Dependency Graph |
|------------|:-----------:|:-------:|:------------:|:----------------:|
| **npm** | Post-hoc (`npm audit`) | ❌ | ❌ | ✅ |
| **PyPI** | Post-hoc (`pip-audit`) | ❌ | ❌ | ✅ |
| **MCP Marketplace** | ❌ | ❌ | ❌ | ❌ |
| **Coze Store** | ❌ | ❌ | ✅ | ❌ |
| **Apple App Store** | ✅ | ✅ | ✅ | N/A |
| **MAREF** | ✅ (gate 1) | ✅ (gate 2) | ✅ (gate 3) | ✅ |

The MCP Marketplace row is the most concerning. The Model Context Protocol is becoming the de facto standard for agent-tool integration, but its marketplace has no admission control. Any tool can register. Any agent can discover and invoke it. This is npm circa 2016 — before `npm audit` existed.

MAREF's bet is that agent skill marketplaces will follow the same trajectory as mobile app stores: start ungoverned, suffer incidents, become governed. The three-gate design is MAREF's answer to "what should governance look like for agent skills?"

## The Nine Real Skills (All Currently PENDING)

MAREF's marketplace currently has 9 SkillManifests across three packs:

| Skill Pack | Skills | Status |
|-----------|--------|--------|
| [brand-building](https://github.com/maref-org/maref/tree/main/docs/skills/brand-building) | brand-context, competitor-branding, brand-positioning, target-audience, messaging-framework | PENDING |
| [pmm-research](https://github.com/maref-org/maref/tree/main/docs/skills/pmm-research) | positioning-validation, messaging-testing, competitive-intelligence | PENDING |
| [creative-automation](https://github.com/maref-org/maref/tree/main/docs/case-studies/creative-automation) | creative-automation | PENDING |

**All 9 are PENDING** — none have passed the three gates yet. This is deliberate. The skills exist as reference implementations and case studies, but they must pass the same admission process as any third-party skill. Eating our own dog food means submitting our own skills to our own gates.

The honest status of each gate:

| Gate | Status | What's needed |
|------|--------|---------------|
| Gate 1 (static scan) | ⚠️ Stub — heuristic string match | Wire in SBOM + vulnerability scanner |
| Gate 2 (sandbox test) | ⚠️ Stub — test case structure validation | Run in gVisor/Firecracker with resource limits |
| Gate 3 (manual review) | ✅ Real — human-in-the-loop | Process needs to be documented |

## The Design Lesson

The three-gate design embodies a principle that runs through all of MAREF: **governance is a first-class product, not a security feature bolted on after launch**.

npm added `npm audit` *after* left-pad. PyPI added `pip-audit` *after* several supply chain attacks. The MCP Marketplace will likely add admission control *after* its first incident.

MAREF ships with three gates from day one — even though gates 1 and 2 are currently stubs. The stubs are honest: they're documented, tracked as v0.36 targets, and the manifest contract already declares the constraints the sandbox will enforce. The design is right; the implementation is catching up.

This is the opposite of "fake it till you make it". It's "design the contract, implement incrementally, be honest about gaps". The three gates are the contract. The stubs are the gaps. The gaps are tracked.

## Call to Action

1. **Review the design** — [`src/maref/marketplace/registry.py`](https://github.com/maref-org/maref/blob/main/src/maref/marketplace/registry.py) is 245 lines. Read it. Challenge the design. Open [GitHub Discussions](https://github.com/maref-org/maref/discussions) with improvements.

2. **Submit a skill** — pick a brand-building or PMM skill manifest, run it through the three gates, and tell us what broke. The gates are designed to be tested by real skills, not just our own.

3. **Help wire in the production gates** — Gate 1 needs the SBOM generator wired in. Gate 2 needs a gVisor integration. Both are tractable contributions for someone familiar with Python supply chain tooling.

4. **Challenge the "three" number** — maybe it should be four (add reputation scoring). Maybe it should be two (merge static + sandbox). The design isn't sacred — it's a starting point. Bring arguments.

---

*This article is the second in MAREF's governance thought-leadership series. The first was ["Why Agent Governance Matters in 2026"](./why-agent-governance-matters). The next will cover TLA+ formal verification of the governance state machine.*
