"""
query_examples.py
Sanity-check queries against meridian.db. Run after build_db.py + load_entities.py.

Usage:
    python query_examples.py --db ../output/meridian.db
"""

import argparse
import sqlite3


QUERIES = {
    "Entity counts by type": """
        SELECT entity_type, COUNT(*) AS n
        FROM entities GROUP BY entity_type ORDER BY n DESC;
    """,
    "All materials used in a given batch (edit document_id below)": """
        SELECT DISTINCT e.entity_name, e.entity_code, m.attributes_json
        FROM entity_mentions m
        JOIN entities e ON e.entity_id = m.entity_id
        WHERE m.document_id = 'BMR_MP-PCM-2601.pdf' AND e.entity_type = 'MATERIAL';
    """,
    "Which documents mention a given operator (edit name below)": """
        SELECT DISTINCT m.document_id
        FROM entity_mentions m
        JOIN entities e ON e.entity_id = m.entity_id
        WHERE e.entity_type = 'OPERATOR' AND e.entity_name LIKE '%Singh%';
    """,
    "SOPs referenced per document": """
        SELECT m.document_id, e.entity_name, e.entity_code
        FROM entity_mentions m
        JOIN entities e ON e.entity_id = m.entity_id
        WHERE e.entity_type = 'SOP_REFERENCE'
        ORDER BY m.document_id;
    """,
    "Relationship graph edges (for pyvis)": """
        SELECT e1.entity_name AS source, e1.entity_type AS source_type,
               r.relationship_type,
               e2.entity_name AS target, e2.entity_type AS target_type
        FROM relationships r
        JOIN entities e1 ON e1.entity_id = r.entity_id_1
        JOIN entities e2 ON e2.entity_id = r.entity_id_2
        LIMIT 50;
    """,
}


def main(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    for title, sql in QUERIES.items():
        print(f"\n=== {title} ===")
        try:
            rows = conn.execute(sql).fetchall()
            if not rows:
                print("  (no rows)")
            for row in rows[:15]:
                print("  ", dict(row))
        except sqlite3.OperationalError as e:
            print(f"  [skipped] {e}")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="../output/meridian.db")
    args = parser.parse_args()
    main(args.db)
