from __future__ import annotations

import hashlib
import hmac
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from maref.security.decorators import security_critical


def _new_id(prefix: str='NEG') -> str:
    return f'{prefix}-{uuid.uuid4().hex[:8].upper()}'

def _compute_hash(payload: str, key: bytes) -> str:
    return hmac.new(key, payload.encode('utf-8'), hashlib.sha256).hexdigest()

@dataclass
class GenePattern:
    pattern_id: str
    gene_id: str
    pattern_type: str
    pattern_value: str
    variant_group: str = 'primary'
    match_score: float = 1.0

@dataclass
class GeneVariant:
    variant_id: str
    gene_id: str
    language: str = 'python'
    variant_code: str = ''
    detected_count: int = 0
    last_detected_at: float | None = None

@dataclass
class GeneMapping:
    mapping_id: str
    gene_id: str
    entity_type: str
    entity_id: str
    relation_type: str = 'affected_by'
    confidence: float = 0.8

@dataclass
class NegativeGene:
    gene_id: str
    cwe_id: str
    risk_level: str
    severity: int
    blocked: bool
    title: str
    description: str
    source: str
    first_seen: float
    occurrences: int = 1
    retention_days: int = 730
    hmac_signature: str = ''
    patterns: list[GenePattern] = field(default_factory=list)
    variants: list[GeneVariant] = field(default_factory=list)

    def update_hmac(self, key: bytes) -> None:
        payload = f'{self.gene_id}|{self.cwe_id}|{self.risk_level}|{self.severity}|{int(self.blocked)}|{self.title}|{self.description}|{self.source}|{self.first_seen}|{self.occurrences}|{self.retention_days}'
        self.hmac_signature = _compute_hash(payload, key)

    def verify_hmac(self, key: bytes) -> bool:
        saved = self.hmac_signature
        self.update_hmac(key)
        ok = self.hmac_signature == saved
        self.hmac_signature = saved
        return ok

class NegativeGeneBank:
    """SQLite-persisted, HMAC-protected repository of known AI error patterns."""
    _SCHEMA_VERSION = '1.1'
    _CREATE_TABLES = "\n    CREATE TABLE IF NOT EXISTS meta (\n        key   TEXT PRIMARY KEY,\n        value TEXT NOT NULL\n    );\n\n    CREATE TABLE IF NOT EXISTS negative_genes (\n        gene_id        TEXT PRIMARY KEY,\n        cwe_id         TEXT NOT NULL,\n        risk_level     TEXT NOT NULL CHECK(risk_level IN ('CRITICAL','HIGH','MEDIUM','LOW')),\n        severity       INTEGER NOT NULL CHECK(severity BETWEEN 1 AND 10),\n        blocked        INTEGER NOT NULL DEFAULT 1,\n        title          TEXT NOT NULL,\n        description    TEXT NOT NULL,\n        source         TEXT NOT NULL,\n        first_seen     REAL NOT NULL,\n        occurrences    INTEGER NOT NULL DEFAULT 1,\n        retention_days INTEGER NOT NULL DEFAULT 730,\n        hmac_signature TEXT NOT NULL DEFAULT '',\n        created_at     REAL NOT NULL,\n        updated_at     REAL NOT NULL\n    );\n    CREATE INDEX IF NOT EXISTS idx_genes_cwe ON negative_genes(cwe_id);\n    CREATE INDEX IF NOT EXISTS idx_genes_risk ON negative_genes(risk_level);\n    CREATE INDEX IF NOT EXISTS idx_genes_blocked ON negative_genes(blocked);\n    CREATE INDEX IF NOT EXISTS idx_genes_source ON negative_genes(source);\n\n    CREATE TABLE IF NOT EXISTS gene_patterns (\n        pattern_id    TEXT PRIMARY KEY,\n        gene_id       TEXT NOT NULL REFERENCES negative_genes(gene_id) ON DELETE CASCADE,\n        pattern_type  TEXT NOT NULL CHECK(pattern_type IN ('regex','ast_node','ast_call','import_name','function_name','string_content','semgrep')),\n        pattern_value TEXT NOT NULL,\n        variant_group TEXT NOT NULL DEFAULT 'primary',\n        match_score   REAL NOT NULL DEFAULT 1.0 CHECK(match_score BETWEEN 0 AND 1)\n    );\n    CREATE INDEX IF NOT EXISTS idx_patterns_gene ON gene_patterns(gene_id);\n    CREATE INDEX IF NOT EXISTS idx_patterns_type ON gene_patterns(pattern_type);\n\n    CREATE TABLE IF NOT EXISTS gene_variants (\n        variant_id      TEXT PRIMARY KEY,\n        gene_id         TEXT NOT NULL REFERENCES negative_genes(gene_id) ON DELETE CASCADE,\n        language        TEXT NOT NULL DEFAULT 'python',\n        variant_code    TEXT NOT NULL,\n        detected_count  INTEGER NOT NULL DEFAULT 0,\n        last_detected_at REAL,\n        created_at      REAL NOT NULL DEFAULT (unixepoch())\n    );\n    CREATE INDEX IF NOT EXISTS idx_variants_gene ON gene_variants(gene_id);\n\n    CREATE TABLE IF NOT EXISTS gene_mappings (\n        mapping_id    TEXT PRIMARY KEY,\n        gene_id       TEXT NOT NULL REFERENCES negative_genes(gene_id) ON DELETE CASCADE,\n        entity_type   TEXT NOT NULL CHECK(entity_type IN ('knowledge_node','capability','agent_profile','experience_entry')),\n        entity_id     TEXT NOT NULL,\n        relation_type TEXT NOT NULL DEFAULT 'affected_by',\n        confidence    REAL NOT NULL DEFAULT 0.8 CHECK(confidence BETWEEN 0 AND 1),\n        created_at    REAL NOT NULL DEFAULT (unixepoch())\n    );\n    CREATE INDEX IF NOT EXISTS idx_mappings_gene ON gene_mappings(gene_id);\n    CREATE INDEX IF NOT EXISTS idx_mappings_entity ON gene_mappings(entity_type, entity_id);\n\n    CREATE TABLE IF NOT EXISTS gene_sources (\n        source_id      TEXT PRIMARY KEY,\n        source_name    TEXT NOT NULL UNIQUE,\n        source_url     TEXT,\n        import_date    REAL NOT NULL DEFAULT (unixepoch()),\n        gene_count     INTEGER NOT NULL DEFAULT 0,\n        schema_version TEXT NOT NULL DEFAULT '1.0',\n        hmac_signature TEXT NOT NULL DEFAULT ''\n    );\n    CREATE INDEX IF NOT EXISTS idx_genes_cwe_risk ON negative_genes(cwe_id, risk_level);\n    CREATE INDEX IF NOT EXISTS idx_genes_source_first_seen ON negative_genes(source, first_seen);\n    CREATE INDEX IF NOT EXISTS idx_genes_risk_blocked ON negative_genes(risk_level, blocked);\n    CREATE INDEX IF NOT EXISTS idx_patterns_type_value ON gene_patterns(pattern_type, pattern_value);\n    "

    def __init__(self, db_path: str=':memory:', hmac_key: bytes | None=None) -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute('PRAGMA journal_mode=WAL')
        self._conn.execute('PRAGMA foreign_keys=ON')
        self._hmac_key = hmac_key or os.urandom(32)
        self._init_schema()
        self._seed_version()

    def _init_schema(self) -> None:
        for statement in self._CREATE_TABLES.split(';'):
            stmt = statement.strip()
            if stmt:
                self._conn.execute(stmt + ';')
        self._conn.commit()

    def _seed_version(self) -> None:
        cur = self._conn.execute("SELECT value FROM meta WHERE key='schema_version'")
        row = cur.fetchone()
        if row is None:
            self._conn.execute('INSERT INTO meta (key, value) VALUES (?, ?)', ('schema_version', self._SCHEMA_VERSION))
            self._conn.commit()

    @security_critical
    def store_gene(self, gene: NegativeGene) -> str:
        gene.gene_id = gene.gene_id or _new_id()
        gene.update_hmac(self._hmac_key)
        now = time.time()
        with self._conn:
            self._conn.execute('INSERT OR REPLACE INTO negative_genes\n                   (gene_id,cwe_id,risk_level,severity,blocked,title,description,\n                    source,first_seen,occurrences,retention_days,hmac_signature,created_at,updated_at)\n                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (gene.gene_id, gene.cwe_id, gene.risk_level, gene.severity, int(gene.blocked), gene.title, gene.description, gene.source, gene.first_seen, gene.occurrences, gene.retention_days, gene.hmac_signature, now, now))
            for p in gene.patterns:
                p.pattern_id = p.pattern_id or _new_id('PAT')
                p.gene_id = gene.gene_id
                self._conn.execute('INSERT OR REPLACE INTO gene_patterns\n                       (pattern_id,gene_id,pattern_type,pattern_value,variant_group,match_score)\n                       VALUES (?,?,?,?,?,?)', (p.pattern_id, p.gene_id, p.pattern_type, p.pattern_value, p.variant_group, p.match_score))
            for v in gene.variants:
                v.variant_id = v.variant_id or _new_id('VAR')
                v.gene_id = gene.gene_id
                self._conn.execute('INSERT OR REPLACE INTO gene_variants\n                       (variant_id,gene_id,language,variant_code,detected_count,last_detected_at,created_at)\n                       VALUES (?,?,?,?,?,?,?)', (v.variant_id, v.gene_id, v.language, v.variant_code, v.detected_count, v.last_detected_at or now, now))
        return gene.gene_id

    def get_gene(self, gene_id: str) -> NegativeGene | None:
        row = self._conn.execute('SELECT * FROM negative_genes WHERE gene_id=?', (gene_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_gene(row)

    @security_critical
    def update_gene(self, gene: NegativeGene) -> None:
        gene.update_hmac(self._hmac_key)
        now = time.time()
        with self._conn:
            self._conn.execute('UPDATE negative_genes SET\n                   cwe_id=?,risk_level=?,severity=?,blocked=?,title=?,description=?,\n                   source=?,occurrences=?,retention_days=?,hmac_signature=?,updated_at=?\n                   WHERE gene_id=?', (gene.cwe_id, gene.risk_level, gene.severity, int(gene.blocked), gene.title, gene.description, gene.source, gene.occurrences, gene.retention_days, gene.hmac_signature, now, gene.gene_id))

    @security_critical
    def delete_gene(self, gene_id: str) -> bool:
        c = self._conn.execute('DELETE FROM negative_genes WHERE gene_id=?', (gene_id,))
        return c.rowcount > 0

    def query_all(self, limit: int=1000, offset: int=0) -> list[NegativeGene]:
        rows = self._conn.execute('SELECT * FROM negative_genes ORDER BY gene_id LIMIT ? OFFSET ?', (limit, offset)).fetchall()
        return [self._row_to_gene(r) for r in rows]

    def query_by_cwe(self, cwe_id: str) -> list[NegativeGene]:
        rows = self._conn.execute('SELECT * FROM negative_genes WHERE cwe_id=?', (cwe_id,)).fetchall()
        return [self._row_to_gene(r) for r in rows]

    def query_by_pattern(self, keyword: str, limit: int=50) -> list[NegativeGene]:
        rows = self._conn.execute('SELECT DISTINCT ng.* FROM negative_genes ng\n               JOIN gene_patterns gp ON ng.gene_id=gp.gene_id\n               WHERE gp.pattern_value LIKE ?\n               LIMIT ?', (f'%{keyword}%', limit)).fetchall()
        return [self._row_to_gene(r) for r in rows]

    def query_by_risk(self, risk_level: str, blocked_only: bool=True) -> list[NegativeGene]:
        sql = 'SELECT * FROM negative_genes WHERE risk_level=?'
        params: list[Any] = [risk_level.upper()]
        if blocked_only:
            sql += ' AND blocked=1'
        rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_gene(r) for r in rows]

    def query_by_source(self, source: str) -> list[NegativeGene]:
        rows = self._conn.execute('SELECT * FROM negative_genes WHERE source=?', (source,)).fetchall()
        return [self._row_to_gene(r) for r in rows]

    def search(self, keyword: str, limit: int=20) -> list[NegativeGene]:
        like = f'%{keyword}%'
        rows = self._conn.execute('SELECT DISTINCT ng.* FROM negative_genes ng\n               LEFT JOIN gene_patterns gp ON ng.gene_id=gp.gene_id\n               WHERE ng.title LIKE ? OR ng.description LIKE ? OR gp.pattern_value LIKE ?\n               LIMIT ?', (like, like, like, limit)).fetchall()
        return [self._row_to_gene(r) for r in rows]

    def count_by_cwe(self) -> dict[str, int]:
        rows = self._conn.execute('SELECT cwe_id, COUNT(*) FROM negative_genes GROUP BY cwe_id ORDER BY COUNT(*) DESC').fetchall()
        return dict(rows)

    def count_by_risk(self) -> dict[str, int]:
        rows = self._conn.execute('SELECT risk_level, COUNT(*) FROM negative_genes GROUP BY risk_level').fetchall()
        return dict(rows)

    def count_by_source(self) -> dict[str, int]:
        rows = self._conn.execute('SELECT source, COUNT(*) FROM negative_genes GROUP BY source').fetchall()
        return dict(rows)

    def gene_count(self) -> int:
        row = self._conn.execute('SELECT COUNT(*) FROM negative_genes').fetchone()
        return row[0] if row else 0

    def top_blocked_patterns(self, limit: int=20) -> list[tuple[str, int]]:
        rows = self._conn.execute('SELECT gp.pattern_value, COUNT(DISTINCT ng.gene_id)\n               FROM gene_patterns gp\n               JOIN negative_genes ng ON gp.gene_id=ng.gene_id\n               WHERE ng.blocked=1\n               GROUP BY gp.pattern_value\n               ORDER BY COUNT(DISTINCT ng.gene_id) DESC\n               LIMIT ?', (limit,)).fetchall()
        return [(r[0], r[1]) for r in rows]

    def verify_integrity(self) -> tuple[bool, list[str]]:
        tampered: list[str] = []
        for row in self._conn.execute('SELECT * FROM negative_genes').fetchall():
            gene = self._row_to_gene(row)
            if not gene.verify_hmac(self._hmac_key):
                tampered.append(gene.gene_id)
        return (len(tampered) == 0, tampered)

    def purge_stale(self) -> int:
        cutoff = time.time() - 730 * 86400
        result = self._conn.execute('DELETE FROM negative_genes WHERE first_seen < ?', (cutoff,))
        return result.rowcount

    def register_variant(self, gene_id: str, variant: GeneVariant) -> None:
        variant.variant_id = variant.variant_id or _new_id('VAR')
        variant.gene_id = gene_id
        with self._conn:
            self._conn.execute('INSERT OR REPLACE INTO gene_variants\n                   (variant_id,gene_id,language,variant_code,detected_count,last_detected_at,created_at)\n                   VALUES (?,?,?,?,?,?,?)', (variant.variant_id, variant.gene_id, variant.language, variant.variant_code, variant.detected_count, variant.last_detected_at, time.time()))
            row = self._conn.execute('SELECT * FROM negative_genes WHERE gene_id=?', (gene_id,)).fetchone()
            if row is not None:
                gene = self._row_to_gene(row)
                gene.update_hmac(self._hmac_key)
                self._conn.execute('UPDATE negative_genes SET hmac_signature=?, updated_at=? WHERE gene_id=?', (gene.hmac_signature, time.time(), gene_id))

    def increment_occurrence(self, gene_id: str) -> None:
        row = self._conn.execute('SELECT * FROM negative_genes WHERE gene_id=?', (gene_id,)).fetchone()
        if row is None:
            return
        gene = self._row_to_gene(row)
        gene.occurrences += 1
        gene.update_hmac(self._hmac_key)
        self._conn.execute('UPDATE negative_genes SET occurrences=?, hmac_signature=?, updated_at=? WHERE gene_id=?', (gene.occurrences, gene.hmac_signature, time.time(), gene_id))

    def record_source_import(self, source_name: str, source_url: str='', gene_count: int=0) -> str:
        """Record a CWE source import in the gene_sources table. Returns source_id."""
        src_id = f'SRC-{uuid.uuid4().hex[:12].upper()}'
        self._conn.execute('INSERT OR REPLACE INTO gene_sources\n               (source_id, source_name, source_url, import_date, gene_count, schema_version)\n               VALUES (?, ?, ?, ?, ?, ?)', (src_id, source_name, source_url, time.time(), gene_count, self._SCHEMA_VERSION))
        self._conn.commit()
        return src_id

    def get_import_history(self) -> list[dict[str, Any]]:
        """Retrieve the import history from gene_sources table."""
        rows = self._conn.execute('SELECT source_id, source_name, source_url, import_date, gene_count, schema_version FROM gene_sources ORDER BY import_date DESC').fetchall()
        return [{'source_id': r[0], 'source_name': r[1], 'source_url': r[2], 'import_date': r[3], 'gene_count': r[4], 'schema_version': r[5]} for r in rows]

    def get_gene_lifecycle(self, gene_id: str) -> dict[str, Any] | None:
        """Get the full lifecycle audit for a single gene."""
        gene = self.get_gene(gene_id)
        if not gene:
            return None
        return {'gene_id': gene.gene_id, 'cwe_id': gene.cwe_id, 'risk_level': gene.risk_level.value if hasattr(gene.risk_level, 'value') else gene.risk_level, 'severity': gene.severity, 'blocked': gene.blocked, 'title': gene.title, 'source': gene.source, 'first_seen': gene.first_seen, 'occurrences': gene.occurrences, 'pattern_count': len(gene.patterns), 'variant_count': len(gene.variants), 'hmac_valid': gene.verify_hmac(self._get_hmac_key()) if hasattr(gene, 'verify_hmac') else 'unknown'}

    def get_lifecycle_summary(self) -> dict[str, Any]:
        """Aggregate lifecycle summary across all genes."""
        total = self.gene_count()
        cwe_dist = self.count_by_cwe()
        risk_dist = self.count_by_risk()
        return {'total_genes': total, 'by_cwe': cwe_dist, 'by_risk': risk_dist, 'total_patterns': 'see query_all'}

    def _get_hmac_key(self) -> bytes:
        return self._hmac_key

    def close(self) -> None:
        self._conn.close()

    def _row_to_gene(self, row: sqlite3.Row | tuple) -> NegativeGene:
        values = tuple(row) if isinstance(row, sqlite3.Row) else row
        gene = NegativeGene(gene_id=values[0], cwe_id=values[1], risk_level=values[2], severity=values[3], blocked=bool(values[4]), title=values[5], description=values[6], source=values[7], first_seen=values[8], occurrences=values[9], retention_days=values[10], hmac_signature=values[11])
        for pr in self._conn.execute('SELECT * FROM gene_patterns WHERE gene_id=?', (gene.gene_id,)).fetchall():
            gene.patterns.append(GenePattern(pattern_id=pr[0], gene_id=pr[1], pattern_type=pr[2], pattern_value=pr[3], variant_group=pr[4], match_score=pr[5]))
        for vr in self._conn.execute('SELECT * FROM gene_variants WHERE gene_id=?', (gene.gene_id,)).fetchall():
            gene.variants.append(GeneVariant(variant_id=vr[0], gene_id=vr[1], language=vr[2], variant_code=vr[3], detected_count=vr[4], last_detected_at=vr[5]))
        return gene

    def __enter__(self) -> NegativeGeneBank:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
