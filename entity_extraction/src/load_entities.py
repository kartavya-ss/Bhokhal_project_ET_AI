"""
load_entities.py
Loads entity_extraction/output/extracted_entities.json into meridian.db
(entities, entity_mentions, relationships tables). Idempotent: entities are
deduped on (type, normalized_value); mentions/relationships accumulate per run,
so re-running on the same input will duplicate mentions — clear the DB or
filter upstream if you need strict re-run safety.

Usage:
    python load_entities.py --extracted ../output/extracted_entities.json --db ../output/meridian.db
"""

import argparse
import json
import re
import sqlite3


def normalize(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip()).upper()


def get_or_create_entity(conn, entity_type: str, name: str, code: str | None) -> int:
    """Dedup priority: entity_code (most reliable — same material often has
    different surface names across a document, e.g. 'Microcrystalline
    Cellulose' vs 'SP-NF', both MCC-SUP-1187) > normalized name."""
    if code:
        row = conn.execute(
            "SELECT entity_id FROM entities WHERE entity_type = ? AND entity_code = ?",
            (entity_type, code),
        ).fetchone()
        if row:
            return row[0]

    norm = normalize(name)
    row = conn.execute(
        "SELECT entity_id FROM entities WHERE entity_type = ? AND normalized_value = ?",
        (entity_type, norm),
    ).fetchone()
    if row:
        # backfill the code if this mention has one and the stored row doesn't
        if code:
            conn.execute(
                "UPDATE entities SET entity_code = ? WHERE entity_id = ? AND entity_code IS NULL",
                (code, row[0]),
            )
        return row[0]

    cur = conn.execute(
        "INSERT INTO entities (entity_type, entity_name, normalized_value, entity_code) VALUES (?, ?, ?, ?)",
        (entity_type, name, norm, code),
    )
    return cur.lastrowid


def load(extracted_path: str, db_path: str):
    with open(extracted_path, "r", encoding="utf-8") as f:
        chunk_results = json.load(f)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")

    n_entities = n_mentions = n_rels = 0

    for chunk in chunk_results:
        document_id = chunk["document_id"]
        chunk_id = chunk["chunk_id"]
        page = chunk.get("page")

        # ensure document exists (in case build_db.py wasn't run for this doc)
        conn.execute(
            "INSERT OR IGNORE INTO documents (document_id, source_type) VALUES (?, ?)",
            (document_id, "unknown"),
        )

        name_to_id = {}
        for ent in chunk.get("entities", []):
            entity_id = get_or_create_entity(conn, ent["type"], ent["name"], ent.get("code"))
            name_to_id[ent["name"]] = entity_id
            n_entities += 1

            attrs = ent.get("attributes") or {}
            conn.execute(
                """INSERT INTO entity_mentions
                   (entity_id, document_id, chunk_id, page, context_snippet, attributes_json)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (entity_id, document_id, chunk_id, page, ent["name"], json.dumps(attrs)),
            )
            n_mentions += 1

        for rel in chunk.get("relationships", []):
            from_name, to_name = rel.get("from"), rel.get("to")
            if from_name not in name_to_id:
                continue
            from_id = name_to_id[from_name]
            # 'to' may reference an entity in this chunk, or the document itself
            if to_name in name_to_id:
                to_id = name_to_id[to_name]
            elif to_name == document_id:
                to_id = get_or_create_entity(conn, "BATCH_ID", document_id, None)
            else:
                continue  # unresolvable reference, skip rather than guess
            conn.execute(
                """INSERT INTO relationships
                   (entity_id_1, entity_id_2, relationship_type, chunk_id, document_id)
                   VALUES (?, ?, ?, ?, ?)""",
                (from_id, to_id, rel["type"], chunk_id, document_id),
            )
            n_rels += 1

    conn.commit()
    conn.close()
    print(f"Loaded {n_entities} entity mentions ({n_mentions} mention rows), {n_rels} relationships.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--extracted", required=True)
    parser.add_argument("--db", default="../output/meridian.db")
    args = parser.parse_args()
    load(args.extracted, args.db)