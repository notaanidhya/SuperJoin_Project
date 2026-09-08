CREATE TABLE IF NOT EXISTS documents (
    document_id     TEXT PRIMARY KEY,
    filename        TEXT NOT NULL,
    filepath        TEXT NOT NULL,
    total_pages     INTEGER NOT NULL,
    status          TEXT NOT NULL DEFAULT "indexed",
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS document_chunks (
    chunk_id        TEXT PRIMARY KEY,
    document_id     TEXT NOT NULL,
    page_number     INTEGER NOT NULL,
    chunk_index     INTEGER NOT NULL,
    text            TEXT NOT NULL,
    section_header  TEXT,
    is_table        BOOLEAN NOT NULL DEFAULT 0,
    char_start      INTEGER NOT NULL,
    char_end        INTEGER NOT NULL,
    FOREIGN KEY(document_id) REFERENCES documents(document_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS facts (
    fact_id         TEXT PRIMARY KEY,
    document_id     TEXT NOT NULL,
    chunk_id        TEXT NOT NULL,
    page_number     INTEGER NOT NULL,
    section_header  TEXT,
    fact_type       TEXT NOT NULL,
    subject         TEXT NOT NULL,
    predicate       TEXT NOT NULL,
    object_value    TEXT NOT NULL,
    numeric_value   REAL,
    unit            TEXT,
    period          TEXT,
    scope           TEXT,
    verbatim_quote  TEXT NOT NULL,
    confidence      REAL NOT NULL,
    qualifiers      TEXT,
    grounding_verified BOOLEAN NOT NULL DEFAULT 0,
    char_offset_in_chunk INTEGER,
    embedding_blob  BLOB,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(document_id) REFERENCES documents(document_id) ON DELETE CASCADE,
    FOREIGN KEY(chunk_id) REFERENCES document_chunks(chunk_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS relationships (
    relationship_id TEXT PRIMARY KEY,
    fact_a_id       TEXT NOT NULL,
    fact_b_id       TEXT NOT NULL,
    relationship    TEXT NOT NULL,
    confidence      REAL NOT NULL,
    explanation     TEXT NOT NULL,
    reconciliation_context TEXT,
    detected_by     TEXT DEFAULT "auto",
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(fact_a_id) REFERENCES facts(fact_id) ON DELETE CASCADE,
    FOREIGN KEY(fact_b_id) REFERENCES facts(fact_id) ON DELETE CASCADE,
    UNIQUE(fact_a_id, fact_b_id)
);

CREATE INDEX IF NOT EXISTS idx_chunks_doc ON document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_facts_doc ON facts(document_id);
CREATE INDEX IF NOT EXISTS idx_facts_subject ON facts(subject);
CREATE INDEX IF NOT EXISTS idx_facts_predicate ON facts(predicate);
CREATE INDEX IF NOT EXISTS idx_relationships_a ON relationships(fact_a_id);
CREATE INDEX IF NOT EXISTS idx_relationships_b ON relationships(fact_b_id);