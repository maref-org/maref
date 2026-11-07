# Dataset Card: maref_redteam_curation

## Summary

- **Run timestamp**: 2026-11-07T09:34:52.152191Z
- **Wall clock time**: 0.0s
- **Pipeline config hash**: `c592e560ea9a5d31`

## Source Documents

  - Unknown

## Pipeline Stages

| Step | Input | Passed | Recovered | Rejected | Forward |
|------|-------|--------|-----------|----------|---------|
| JSONLReader | 204 | 204 | — | 0 | 204 |
| SchemaGate | 204 | 204 | 0 | 0 | 204 |
| ExactDeduplicator | 204 | 204 | — | — | 204 |
| TextCleaner | 204 | 204 | — | — | 204 |
| AlpacaExporter | — | 204 | — | — | 204 |
| ShareGPTExporter | — | 204 | — | — | 204 |

## Gate Pass Rates and Rejection Breakdown

- **JSONLReader**: 204/0 passed (N/A), 0 rejected
- **SchemaGate**: 204/204 passed (100.0%), 0 rejected


**Rejection reasons:**
  - None

## Deduplication

  - exact_duplicates_removed: 0

## Known Limitations

- No MinHash deduplication applied.
- Table extraction requires `extract_tables: true` on the PDF reader and MinerU with GPU support. Disabled by default.
- Token counting uses a whitespace tokenizer by default. For exact LLM context window
  enforcement, enable `use_tiktoken: true` in the SchemaGate config.
- Both within-run (MinHash/Diversity) and cross-run (EmbeddingDeduplicator) deduplication
  are available. Cross-run dedup persists an embedding index across runs; use
  `embedding_reset_index: true` to start fresh.

## Reproduction

```bash
pip install curatorkit
curatorkit run pipeline.yaml --output-dir ./out/
```

## Tool Versions

- **curatorkit**: 0.1.21
- **python**: 3.13.12
