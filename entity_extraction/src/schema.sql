-- Meridian Knowledge Graph Schema
-- Domain: pharma manufacturing (BMRs, SOPs, material specs, sensor/process logs)

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS documents (
    document_id     TEXT PRIMARY KEY,      -- e.g. "BMR_MP-PCM-2601.pdf"
    source_type     TEXT NOT NULL,         -- pdf, csv, docx, etc.
    document_category TEXT,                -- BMR, SOP, sensor_log, spec_sheet, unknown
    num_pages       INTEGER,
    ingested_at     TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS entities (
    entity_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type     TEXT NOT NULL,         -- MATERIAL, OPERATOR, SOP_REFERENCE, EQUIPMENT,
                                            -- PROCESS_STEP, PARAMETER, BATCH_ID, TIMESTAMP, ORG
    entity_name     TEXT NOT NULL,         -- raw surface form, e.g. "Maize Starch IP"
    normalized_value TEXT,                 -- canonical/cleaned form for joins, e.g. "MAIZE_STARCH_IP"
    entity_code     TEXT,                  -- material/SOP code if present, e.g. "SUP-1187", "SOP-PRD-010"
    UNIQUE(entity_type, normalized_value)
);

CREATE TABLE IF NOT EXISTS entity_mentions (
    mention_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id       INTEGER NOT NULL REFERENCES entities(entity_id),
    document_id     TEXT NOT NULL REFERENCES documents(document_id),
    chunk_id        TEXT NOT NULL,
    page            INTEGER,
    context_snippet TEXT,                  -- short surrounding text for grounding/citation
    attributes_json TEXT                   -- e.g. {"quantity": "18.50", "unit": "kg"}
);

CREATE TABLE IF NOT EXISTS relationships (
    relationship_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id_1        INTEGER NOT NULL REFERENCES entities(entity_id),
    entity_id_2        INTEGER NOT NULL REFERENCES entities(entity_id),
    relationship_type  TEXT NOT NULL,      -- USED_IN, OPERATED_BY, GOVERNED_BY, RECORDED_AT, PART_OF_STEP
    chunk_id           TEXT,
    document_id        TEXT REFERENCES documents(document_id),
    confidence         REAL DEFAULT 1.0
);

CREATE INDEX IF NOT EXISTS idx_mentions_entity ON entity_mentions(entity_id);
CREATE INDEX IF NOT EXISTS idx_mentions_doc    ON entity_mentions(document_id);
CREATE INDEX IF NOT EXISTS idx_entities_type   ON entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_rel_e1          ON relationships(entity_id_1);
CREATE INDEX IF NOT EXISTS idx_rel_e2          ON relationships(entity_id_2);
