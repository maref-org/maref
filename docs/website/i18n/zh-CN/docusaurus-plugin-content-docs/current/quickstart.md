---
sidebar_position: 2
title: 快速开始
description: 5 分钟上手第一个受治理的多智能体系统
---

# MAREF Quickstart Guide

**5 minutes to your first governed multi-agent system.**

---

## 1. Installation

```bash
git clone https://github.com/maref-org/maref.git
cd maref
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Verify installation:

```bash
maref --help
maref status
```

---

## 2. Quick Tour

### 2.1 Governance Status

```bash
maref status                    # Table view
maref status --verbose          # JSON view
```

### 2.2 Observe State Transitions

```bash
maref observe --count 5
maref observe --interval 0.5 --count 20
```

### 2.3 Trust Engine

```bash
maref trust score --agent agent-1
maref trust score
```

### 2.4 Serve (HTTP API)

```bash
maref serve --port 8000
# http://localhost:8000/health
# http://localhost:8000/agents
# http://localhost:8000/metrics
```

---

## Next Steps

- Read the [Security Whitepaper](https://github.com/maref-org/maref/blob/main/docs/MAREF-Security-Whitepaper.md)
- Run `pytest tests/ -v` for the full test suite
- Join the community at [github.com/maref-org](https://github.com/maref-org)
