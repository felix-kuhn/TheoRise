"""Numbered SQLite migrations applied at startup."""
from __future__ import annotations

MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS llm_cache (
            key TEXT PRIMARY KEY,
            response_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            role TEXT NOT NULL,
            prompt_tokens INTEGER NOT NULL DEFAULT 0,
            completion_tokens INTEGER NOT NULL DEFAULT 0,
            total_tokens INTEGER NOT NULL DEFAULT 0,
            model TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_usage_job_id ON usage (job_id);
        """,
    ),
    (
        2,
        """
        CREATE TABLE IF NOT EXISTS documents (
            doc_id TEXT PRIMARY KEY,
            source_group TEXT NOT NULL CHECK (source_group IN ('A', 'B')),
            doc_type TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            path TEXT NOT NULL DEFAULT '',
            content_hash TEXT NOT NULL DEFAULT '',
            parser_version TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sections (
            section_id TEXT PRIMARY KEY,
            doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
            field_key TEXT,
            heading_path TEXT NOT NULL DEFAULT '',
            ordinal INTEGER NOT NULL DEFAULT 0,
            raw_text TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS chunks (
            chunk_id TEXT PRIMARY KEY,
            doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
            section_id TEXT REFERENCES sections(section_id) ON DELETE SET NULL,
            ordinal INTEGER NOT NULL DEFAULT 0,
            text TEXT NOT NULL DEFAULT '',
            heading_path TEXT NOT NULL DEFAULT '',
            token_count INTEGER NOT NULL DEFAULT 0,
            page_start INTEGER,
            page_end INTEGER,
            bbox_json TEXT,
            speaker TEXT,
            kind TEXT NOT NULL DEFAULT 'chunk',
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS theories (
            doc_id TEXT PRIMARY KEY REFERENCES documents(doc_id) ON DELETE CASCADE,
            name TEXT NOT NULL DEFAULT '',
            acronym TEXT,
            aliases_json TEXT NOT NULL DEFAULT '[]',
            originating_area TEXT,
            level_of_analysis_json TEXT,
            gregor_type TEXT,
            last_updated_text TEXT,
            card_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS constructs (
            construct_id TEXT PRIMARY KEY,
            canonical_name TEXT NOT NULL,
            aliases_json TEXT NOT NULL DEFAULT '[]',
            description TEXT,
            created_by TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS claims (
            claim_id TEXT PRIMARY KEY,
            doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
            chunk_id TEXT REFERENCES chunks(chunk_id) ON DELETE SET NULL,
            text TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'proposition',
            constructs_json TEXT NOT NULL DEFAULT '[]',
            polarity TEXT NOT NULL DEFAULT 'none',
            confidence REAL,
            model TEXT NOT NULL DEFAULT '',
            prompt_version TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS findings (
            finding_id TEXT PRIMARY KEY,
            doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
            chunk_id TEXT REFERENCES chunks(chunk_id) ON DELETE SET NULL,
            text TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'finding',
            constructs_json TEXT NOT NULL DEFAULT '[]',
            polarity TEXT NOT NULL DEFAULT 'none',
            evidence_span TEXT NOT NULL DEFAULT '',
            confidence REAL,
            model TEXT NOT NULL DEFAULT '',
            prompt_version TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS "references" (
            ref_id TEXT PRIMARY KEY,
            doi TEXT,
            title TEXT NOT NULL DEFAULT '',
            authors_json TEXT NOT NULL DEFAULT '[]',
            year INTEGER,
            raw TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS links (
            link_id TEXT PRIMARY KEY,
            source_type TEXT NOT NULL,
            source_id TEXT NOT NULL,
            target_type TEXT NOT NULL,
            target_id TEXT NOT NULL,
            label TEXT NOT NULL,
            confidence REAL,
            rationale TEXT NOT NULL DEFAULT '',
            source_evidence TEXT NOT NULL DEFAULT '',
            target_evidence TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'proposed',
            model TEXT NOT NULL DEFAULT '',
            prompt_version TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            reviewed_at TEXT,
            reviewer_note TEXT
        );

        CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            params_json TEXT NOT NULL DEFAULT '{}',
            progress REAL NOT NULL DEFAULT 0.0,
            message TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            error TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS job_items (
            item_id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
            doc_id TEXT,
            stage TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            error TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS doc_stage_status (
            doc_id TEXT NOT NULL,
            stage TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            fingerprint TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (doc_id, stage)
        );

        CREATE TABLE IF NOT EXISTS index_meta (
            key TEXT PRIMARY KEY,
            value_json TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_documents_hash ON documents (content_hash);
        CREATE INDEX IF NOT EXISTS idx_sections_doc ON sections (doc_id);
        CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks (doc_id);
        CREATE INDEX IF NOT EXISTS idx_claims_doc ON claims (doc_id);
        CREATE INDEX IF NOT EXISTS idx_findings_doc ON findings (doc_id);
        CREATE INDEX IF NOT EXISTS idx_links_source ON links (source_type, source_id);
        CREATE INDEX IF NOT EXISTS idx_links_target ON links (target_type, target_id);

        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            chunk_id UNINDEXED,
            text
        );

        CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
            INSERT INTO chunks_fts(rowid, chunk_id, text)
            VALUES (new.rowid, new.chunk_id, new.text);
        END;

        CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
            DELETE FROM chunks_fts WHERE rowid = old.rowid;
        END;

        CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE OF text ON chunks BEGIN
            UPDATE chunks_fts
            SET chunk_id = new.chunk_id, text = new.text
            WHERE rowid = old.rowid;
        END;
        """,
    ),
]
