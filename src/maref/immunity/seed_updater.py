import json
import time
from typing import TYPE_CHECKING, Any
from maref.immunity.negative_gene_bank import GenePattern, GeneVariant, NegativeGene, _new_id
if TYPE_CHECKING:
    from maref.immunity.negative_gene_bank import NegativeGeneBank
SUPPORTED_SOURCES = frozenset({'mitre_cwe', 'maraf_cwe', 'owasp', 'veracode', 'custom'})

class CWEImportError(Exception):
    ...

def seed_from_cwe_json(bank: NegativeGeneBank, json_path: str, source_name: str='mitre_cwe', source_url: str='', merge: bool=False) -> dict[str, Any]:
    """Import CWE patterns from a JSON file into the NegativeGeneBank.

    Parameters
    ----------
    bank : NegativeGeneBank
        The gene bank to import into.
    json_path : str
        Path to the CWE JSON file.
    source_name : str
        Source identifier (must be in SUPPORTED_SOURCES).
    source_url : str
        Optional URL for provenance tracking.
    merge : bool
        If True, update existing genes by cwe_id instead of replacing.

    Returns
    -------
    dict with keys:
        - imported: number of new genes added
        - updated: number of existing genes updated (merge=True only)
        - skipped: number of entries skipped (invalid or duplicate)
        - total_genes: total genes in the bank after import
        - source_id: the gene_sources record ID
    """
    if source_name not in SUPPORTED_SOURCES:
        raise CWEImportError(f"Unknown source '{source_name}'. Supported: {sorted(SUPPORTED_SOURCES)}")
    with open(json_path, encoding='utf-8') as f:
        data = json.load(f)
    entries: list[dict[str, Any]]
    if isinstance(data, list):
        entries = data
    elif isinstance(data, dict) and 'genes' in data:
        entries = data['genes']
    elif isinstance(data, dict) and 'cwe_entries' in data:
        entries = data['cwe_entries']
    else:
        raise CWEImportError("Unknown JSON structure. Expected a list of gene entries, or a dict with 'genes'/'cwe_entries' key.")
    imported = 0
    updated = 0
    skipped = 0
    now = time.time()
    for entry in entries:
        cwe_id = entry.get('cwe_id', '')
        if not cwe_id:
            skipped += 1
            continue
        title = entry.get('title') or entry.get('name', '')
        desc = entry.get('description', '')
        risk = entry.get('risk_level', 'MEDIUM').upper()
        if risk not in ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW'):
            risk = 'MEDIUM'
        severity = entry.get('severity', 5)
        blocked = entry.get('blocked', True)
        raw_patterns = entry.get('patterns', [])
        raw_variants = entry.get('variants', [])
        patterns = [GenePattern(pattern_id='', gene_id='', pattern_type=p.get('type', 'regex'), pattern_value=p.get('value', ''), variant_group=p.get('group', 'primary'), match_score=p.get('score', 1.0)) for p in raw_patterns]
        variants = [GeneVariant(variant_id='', gene_id='', language=v.get('language', 'python'), variant_code=v.get('code', '')) for v in raw_variants]
        existing = bank.query_by_cwe(cwe_id)
        if existing and merge:
            for gene in existing:
                new_patterns_added = 0
                if gene.patterns:
                    existing_pattern_vals = {p.pattern_value for p in gene.patterns}
                    for p in patterns:
                        if p.pattern_value not in existing_pattern_vals:
                            gene.patterns.append(p)
                            new_patterns_added += 1
                for v in variants:
                    gene.variants.append(v)
                bank.update_gene(gene)
                updated += 1
        elif existing:
            skipped += 1
            continue
        else:
            gene = NegativeGene(gene_id=_new_id(), cwe_id=cwe_id, risk_level=risk, severity=severity, blocked=blocked, title=title, description=desc, source=source_name, first_seen=now, patterns=patterns, variants=variants)
            bank.store_gene(gene)
            imported += 1
    total = bank.gene_count()
    src_id = bank.record_source_import(source_name, source_url, total)
    return {'imported': imported, 'updated': updated, 'skipped': skipped, 'total_genes': total, 'source_id': src_id}

def get_import_history(bank: NegativeGeneBank) -> list[dict[str, Any]]:
    """Retrieve the import history from gene_sources table."""
    return bank.get_import_history()

def export_genes_to_json(bank: NegativeGeneBank, json_path: str, cwe_filter: str | None=None) -> int:
    """Export the NegativeGeneBank to a CWE JSON file.

    Parameters
    ----------
    bank : NegativeGeneBank
    json_path : str
        Output file path.
    cwe_filter : str | None
        Optional CWE ID prefix filter (e.g. "CWE-79").

    Returns
    -------
    Number of exported genes.
    """
    genes = bank.query_by_cwe(cwe_filter) if cwe_filter else bank.query_all(limit=10000)
    entries = []
    for g in genes:
        entry = {'cwe_id': g.cwe_id, 'title': g.title, 'description': g.description, 'risk_level': g.risk_level, 'severity': g.severity, 'blocked': g.blocked, 'source': g.source, 'patterns': [{'type': p.pattern_type, 'value': p.pattern_value, 'group': p.variant_group, 'score': p.match_score} for p in g.patterns], 'variants': [{'language': v.language, 'code': v.variant_code} for v in g.variants]}
        entries.append(entry)
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump({'genes': entries, 'exported_at': time.time(), 'count': len(entries)}, f, indent=2, ensure_ascii=False)
    return len(entries)