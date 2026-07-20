"""
build_db.py
Initializes meridian.db from schema.sql and populates the `documents` table
from ingestion/output/extracted_documents.json.

Usage:
    python build_db.py --extracted-docs ../../ingestion/output/extracted_documents.json --db ../output/meridian.db
"""

import argparse
import json
import re
import sqlite3
from pathlib import Path


def classify_document(document_id: str, first_page_text: str) -> str:
    """Best-effort heuristic classification. Cheap and deterministic —
    keeps LLM calls focused on entity extraction, not document typing."""
    doc_id_upper = document_id.upper()
    text_upper = (first_page_text or "")[:500].upper()

    if "BMR" in doc_id_upper or "BATCH MANUFACTURING RECORD" in text_upper:
        return "BMR"
    if re.search(r"\bSOP\b", doc_id_upper) or "STANDARD OPERATING PROCEDURE" in text_upper:
        return "SOP"
    if document_id.lower().endswith(".csv"):
        return "sensor_log"
    return "unknown"


def build_db(extracted_docs_path: str, db_path: str, schema_path: str):
    with open(extracted_docs_path, "r", encoding="utf-8") as f:
        documents = json.load(f)

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    with open(schema_path, "r", encoding="utf-8") as f:
        conn.executescript(f.read())

    inserted = 0
    for doc in documents:
        document_id = doc["document_id"]
        source_type = doc.get("source_type", "unknown")
        pages = doc.get("pages", [])
        first_page_text = pages[0]["text"] if pages else ""
        category = classify_document(document_id, first_page_text)

        conn.execute(
            """INSERT OR IGNORE INTO documents
               (document_id, source_type, document_category, num_pages)
               VALUES (?, ?, ?, ?)""",
            (document_id, source_type, category, len(pages)),
        )
        inserted += 1

    conn.commit()
    count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    conn.close()
    print(f"Processed {inserted} documents from extracted_documents.json")
    print(f"documents table now has {count} rows -> {db_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--extracted-docs", required=True)
    parser.add_argument("--db", default="../output/meridian.db")
    parser.add_argument("--schema", default="schema.sql")
    args = parser.parse_args()
    build_db(args.extracted_docs, args.db, args.schema)
