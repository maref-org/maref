# AG-Conformance v0.1

**A runnable ruler for agent governance evidence — not another runtime.**

Give it a JSONL trace exported by any agent runtime, get a signed verdict against
10 controls: identity, policy binding, explicit decisions, least privilege,
hash chain, payload integrity, human approval, tool supply chain, data
classification, trace completeness.

- Spec: [`SPEC.md`](./SPEC.md)
- Mapping to OWASP ASI / GB/Z 185 / NIST / EU AI Act: [`mapping.csv`](./mapping.csv)
- Examples: [`examples/good_trace.jsonl`](./examples/good_trace.jsonl), [`examples/bad_trace.jsonl`](./examples/bad_trace.jsonl)

## 10-minute quickstart

No install, no network. Python 3.10+ only.

```bash
# 1. self-check: a compliant trace should pass 10/10
python3 scripts/conformance_run.py --demo good

# 2. a violating trace should fail closed (exit code 1)
python3 scripts/conformance_run.py --demo bad

# 3. evaluate your own runtime's trace and sign the report
python3 scripts/conformance_run.py --trace conformance/examples/good_trace.jsonl \
    --out /tmp/report.json --md /tmp/report.md \
    --key "your-hmac-key"

# 4. third party verifies the report without trusting the producer
python3 scripts/conformance_run.py --verify /tmp/report.json --key "your-hmac-key"
```

Expected output on stderr:

```
VERDICT conformant | 10 pass / 0 fail | score 100.0% | signed
```

## Docker

```bash
docker build -f conformance/Dockerfile -t maref-conformance .
docker run --rm -v "$PWD:/work" maref-conformance \
    --trace /work/conformance/examples/good_trace.jsonl --out /work/report.json
```

## What this is not

- Not a certification. OWASP itself says the Agentic Top 10 is not a certifiable standard.
- Not a prompt-injection firewall. TRACE proves what ran; this proves what was allowed and recorded.
- Not a replacement for the runtime. It tests **exported evidence**; a runtime can lie, which is why
  identity, manifest hashes and external anchoring matter.

## Adding a control

1. Add a pure function `check_x(trace, manifest) -> list[Finding]` in
   `src/maref/conformance/controls.py`.
2. Register it in `CONTROLS` with the next `AG-NN` id.
3. Add a failing fixture in `fixtures.py` (semantic violation, valid hash chain).
4. Add one test in `tests/conformance/test_conformance.py`.
5. Update `mapping.csv` and `SPEC.md`.

The suite stays stdlib-only on purpose: it must run anywhere, including against
competitors, without installing MAREF.

## License

Apache-2.0, same as the repository.
