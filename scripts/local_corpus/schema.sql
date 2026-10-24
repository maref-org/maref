CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run (
    id          INTEGER PRIMARY KEY,
    source      TEXT NOT NULL,
    started_at  REAL NOT NULL,
    finished_at REAL,
    rows_in     INTEGER DEFAULT 0,
    rows_new    INTEGER DEFAULT 0,
    status      TEXT DEFAULT 'running',
    error       TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS event (
    id              INTEGER PRIMARY KEY,
    source          TEXT NOT NULL,
    source_event_id TEXT NOT NULL,
    session_id      TEXT NOT NULL,
    agent_id        TEXT DEFAULT '',
    model           TEXT DEFAULT '',
    ts              REAL NOT NULL,
    kind            TEXT NOT NULL,
    tool            TEXT DEFAULT '',
    verdict         TEXT DEFAULT '',
    risk            REAL DEFAULT 0.0,
    error_class     TEXT DEFAULT '',
    error_sig       TEXT DEFAULT '',
    payload_hash    TEXT DEFAULT '',
    snippet         TEXT DEFAULT '',
    redaction_count INTEGER DEFAULT 0,
    UNIQUE(source, source_event_id)
);

CREATE INDEX IF NOT EXISTS idx_event_session_ts ON event(session_id, ts);
CREATE INDEX IF NOT EXISTS idx_event_source_ts ON event(source, ts);

CREATE TABLE IF NOT EXISTS episode (
    id               TEXT PRIMARY KEY,
    runtime          TEXT NOT NULL,
    agent_id         TEXT DEFAULT '',
    model            TEXT DEFAULT '',
    session_id       TEXT NOT NULL,
    task_class       TEXT DEFAULT '',
    started_at       REAL NOT NULL,
    ended_at         REAL,
    failure_sig      TEXT NOT NULL,
    failure_event_id TEXT NOT NULL,
    error_class      TEXT DEFAULT '',
    tool             TEXT DEFAULT '',
    severity         TEXT DEFAULT 'medium',
    outcome          TEXT DEFAULT 'unknown',
    label_status     TEXT DEFAULT 'pending',
    snippet          TEXT DEFAULT '',
    fix_json         TEXT DEFAULT '{}',
    versions_json    TEXT DEFAULT '{}',
    UNIQUE(session_id, failure_event_id)
);

CREATE INDEX IF NOT EXISTS idx_episode_sig ON episode(failure_sig);
CREATE INDEX IF NOT EXISTS idx_episode_status ON episode(label_status);

CREATE TABLE IF NOT EXISTS signature (
    sig             TEXT PRIMARY KEY,
    first_seen      REAL NOT NULL,
    last_seen       REAL NOT NULL,
    count           INTEGER DEFAULT 0,
    runtimes_json   TEXT DEFAULT '[]',
    example_episode TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS family (
    id                TEXT PRIMARY KEY,
    error_class       TEXT NOT NULL,
    anchor            TEXT NOT NULL,
    episode_count     INTEGER DEFAULT 0,
    signatures        INTEGER DEFAULT 0,
    runtimes_json     TEXT DEFAULT '[]',
    example_episode   TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS cluster (
    id                TEXT PRIMARY KEY,
    error_class       TEXT NOT NULL,
    label             TEXT DEFAULT '',
    signatures        INTEGER DEFAULT 0,
    episode_count     INTEGER DEFAULT 0,
    runtimes_json     TEXT DEFAULT '[]',
    signatures_json   TEXT DEFAULT '[]',
    example_episode   TEXT DEFAULT '',
    family_id         TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS label (
    episode_id         TEXT PRIMARY KEY REFERENCES episode(id),
    root_cause         TEXT DEFAULT '',
    fix_type           TEXT DEFAULT '',
    fix_ref            TEXT DEFAULT '',
    severity           TEXT DEFAULT '',
    reusable           INTEGER DEFAULT 0,
    notes              TEXT DEFAULT '',
    labeled_by         TEXT DEFAULT '',
    labeled_at         REAL,
    llm_suggestion_json TEXT DEFAULT '{}',
    agree_with_llm     INTEGER
);

CREATE TABLE IF NOT EXISTS redaction_log (
    id              INTEGER PRIMARY KEY,
    source          TEXT NOT NULL,
    source_event_id TEXT NOT NULL,
    rule            TEXT NOT NULL,
    matched_hash    TEXT NOT NULL,
    at              REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_redaction_source ON redaction_log(source, source_event_id);
