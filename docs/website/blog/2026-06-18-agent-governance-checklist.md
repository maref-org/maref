---
slug: agent-governance-checklist
title: '10 Questions to Ask Before Deploying AI Agents in Production'
authors: [maref]
tags: [governance, best-practices, production, ai-safety]
date: 2026-06-18
---

Before you let AI agents run in production, ask these 10 questions.

<!-- truncate -->

## 1. Can your agent delete or modify data without approval?

If your agent has write access to databases, file systems, or APIs, what stops it from deleting production data? Meta's alignment director lost hundreds of emails because her agent ignored three "STOP" commands. Without a circuit breaker, a single hallucinated write operation can cascade into irreversible data loss. MAREF's CircuitBreaker trips after 3 consecutive anomalies and auto-halts the agent before damage propagates.

## 2. Do you know exactly which agent did what?

Every action must be cryptographically attributable to a specific agent identity. Without per-agent signing, you cannot audit, trace, or prove compliance to auditors. In a multi-agent system, a rogue action from any agent implicates the entire deployment. MAREF signs every action with the agent's unique identity key, producing a tamper-evident audit trail that satisfies SOC 2 and ISO 27001 requirements.

## 3. What happens when your agent enters an infinite loop?

Agents that call tools in a loop can rack up API costs, lock database connections, and degrade system performance. A finance agent stuck in a reconciliation loop once generated $12,000 in API bills overnight. MAREF enforces execution deadlines and budget caps per agent invocation, terminating runaway loops preemptively.

## 4. Can your agent escalate its own privileges?

A coding agent tasked with fixing a bug might install a new package, which then grants it root access. Without privilege confinement, agents can self-escalate beyond their intended scope. MAREF runs each agent inside a capability-scoped sandbox with a TrustBoundaryManager that rejects any cross-domain call not explicitly authorized.

## 5. Is every inter-agent call authorized?

In a multi-agent topology, Agent A should not be able to impersonate Agent B or access resources assigned to Agent C. Without explicit authorization between agents, lateral movement becomes trivial. MAREF's TrustBoundaryManager requires every cross-agent call to pass an authorization check against the policy matrix, and all denied attempts are logged with full context.

## 6. Do you have a kill switch that actually works?

A "stop button" in the UI is useless when the agent ignores it. The agent must respect a hard abort signal at the infrastructure layer, not a polite request in a chat prompt. MAREF implements a hardware-enforced kill switch via its ControlPlane API, which forcibly terminates the agent process and revokes all session tokens within 500ms.

## 7. Can you replay and verify any past decision?

When an agent makes a wrong decision, you need to understand why. Without full input/output capture, root-cause analysis is guesswork. MAREF records every prompt, tool call, tool output, and decision trace in an append-only log, enabling deterministic replay of any agent session.

## 8. Are your secrets protected from the agent itself?

If the agent has access to an API key, nothing stops it from exfiltrating that key through a tool output. Traditional secret injection gives agents direct access to credentials. MAREF uses a proxy-based credential broker that never exposes raw secrets to the agent runtime — the agent requests an action, and the broker signs the request with the credential without the agent ever seeing it.

## 9. How do you test governance rules before deploying them?

Writing governance policies directly in production is risky. A misconfigured rate limit can block all agents; a missing permission can silently allow destructive operations. MAREF provides a simulation mode where you can dry-run governance rules against recorded traffic before deploying them to production agents.

## 10. Does your compliance team understand what the agent is doing?

If your governance is only machine-readable, your compliance and legal teams cannot audit the system without engineering translation. MAREF generates human-readable governance reports with natural-language summaries of every agent action, permission decision, and policy violation, bridging the gap between infrastructure and compliance.

## Summary

If you cannot answer all 10 questions today, you are not ready to deploy AI agents in production. MAREF Lite provides a single-command starting point with 12 pre-configured governance rules that address every question above — instant protection without sacrificing flexibility.
