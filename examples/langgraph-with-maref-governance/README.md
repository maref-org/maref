# LangGraph + MAREF Governance Example

Demonstrates how to add MAREF governance to an existing LangGraph agent without modifying agent code.

## Quick Start

```bash
pip install -r requirements.txt
python main.py
```

## How It Works

`GovernedAgent` wraps LangGraph nodes with MAREF governance checks:
- Token budget enforcement
- Human-in-the-loop approval for dangerous operations
- Automatic audit logging
