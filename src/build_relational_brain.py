"""
Teammate A's job (Task 5, 8, 10): build the SQLite 'hard facts' brain.

Strategy (faster + more reliable than pure LLM extraction for a hackathon):
  1. Regex pass over every chunk to pull out known entity patterns
     (Batch IDs, Machine IDs, SOP numbers, Deviation numbers, known employee names).
  2. One Claude API call per chunk (batched) to extract RELATIONSHIPS between
     the entities found in that chunk, as strict JSON.
  3. INSERT everything into SQLite: entities table + relationships table.

This gives a real knowledge graph: Batch -> made_on -> Machine, Person -> operated -> Machine,
Machine -> covered_by -> SOP, Deviation -> caused_by -> RootCause, etc.
"""
import os
import re
import json
import sqlite3
import anthropic

DB_PATH = "/home/claude/meridian/db/meridian.sqlite"
CHUNKS_PATH = "/home/claude/meridian/data/chunks.json"

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# ---------------------------------------------------------------------------
# Known entity patterns (regex). This is fast, deterministic, and free --
# no need to burn LLM calls just to find "TCM-04" in text.
# ---------------------------------------------------------------------------
PATTERNS = {
    "Machine": r"\bTCM-\d{2}\b",
    "Batch": r"\bMP-PCM-\d{4}\b",
    "SOP": r"\bENG-\d{3}\b|\bQA-\d{3}\b",
    "Deviation": r"\bDEV-\d{4}-\d{3}\b",
}

KNOWN_PEOPLE = ["Priya Nair", "Rajesh Kumar", "Anita Desai", "Suresh Iyer"]


def extract_entities(text):
    found = []
    for etype, pattern in PATTERNS.items():
        for m in set(re.findall(pattern, text)):
            found.append((etype, m))
    for name in KNOWN_PEOPLE:
        if name in text:
            found.append(("Person", name))
    return found


def init_db(conn):
    cur = conn.cursor()
    cur.executescript("""
    DROP TABLE IF EXISTS entities;
    DROP TABLE IF EXISTS relationships;
    DROP TABLE IF EXISTS chunk_entities;

    CREATE TABLE entities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_type TEXT NOT NULL,
        entity_value TEXT NOT NULL,
        UNIQUE(entity_type, entity_value)
    );

    CREATE TABLE relationships (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject_type TEXT,
        subject_value TEXT,
        relation TEXT,
        object_type TEXT,
        object_value TEXT,
        source_chunk_id TEXT,
        source_file TEXT
    );

    CREATE TABLE chunk_entities (
        chunk_id TEXT,
        entity_type TEXT,
        entity_value TEXT,
        source_file TEXT
    );
    """)
    conn.commit()


def upsert_entity(conn, etype, evalue):
    conn.execute(
        "INSERT OR IGNORE INTO entities (entity_type, entity_value) VALUES (?, ?)",
        (etype, evalue),
    )


RELATION_PROMPT = """You are extracting factual relationships from a pharmaceutical manufacturing document chunk.

Known entities already detected in this chunk: {entities}

Text chunk:
\"\"\"{text}\"\"\"

Identify explicit factual relationships between the known entities above, based ONLY on what the text states.
Use relation names from this fixed vocabulary where possible: made_on, operated_by, supervised_by, caused_by,
missed_maintenance_for, covered_by_sop, raised_by, inspected_by, root_cause_of, certified_for, references.

Respond with ONLY a JSON array (no prose, no markdown fences) of objects like:
[{{"subject_type": "Batch", "subject_value": "MP-PCM-2602", "relation": "made_on", "object_type": "Machine", "object_value": "TCM-04"}}]

If no clear relationship exists between the known entities, return an empty array [].
"""


def extract_relationships_llm(client, chunk_text, entities):
    if len(entities) < 2:
        return []
    entity_str = ", ".join(f"{t}:{v}" for t, v in entities)
    prompt = RELATION_PROMPT.format(entities=entity_str, text=chunk_text)
    try:
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        raw = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
        return json.loads(raw)
    except Exception as e:
        print(f"  [!] LLM relation extraction failed ({e}); using rule-based fallback")
        return extract_relationships_rulebased(chunk_text, entities)


# ---------------------------------------------------------------------------
# Rule-based fallback: keyword-triggered relations near known entity pairs.
# Used automatically when no ANTHROPIC_API_KEY is available (e.g. this sandbox),
# and can be used as the *primary* method if you'd rather skip LLM calls
# entirely for cost/speed in the actual hackathon build.
# ---------------------------------------------------------------------------
RULES = [
    # (trigger keywords in chunk, subject_type, object_type, relation)
    (["compression machine", "machine:"], "Batch", "Machine", "made_on"),
    (["operator of record", "operator"], "Person", "Machine", "operated_by"),
    (["shift supervisor", "supervisor"], "Person", "Person", "supervised_by"),
    (["worn punch", "degraded punch", "root cause", "wear and tear"], "Deviation", "Machine", "root_cause_of"),
    (["missed", "never completed", "not completed", "not performed"], "Machine", "SOP", "missed_maintenance_for"),
    (["reference sop", "per sop", "sop:", "sop eng"], "Machine", "SOP", "covered_by_sop"),
    (["raised by", "flagged", "raising a deviation"], "Person", "Deviation", "raised_by"),
    (["inspected", "inspection"], "Person", "Machine", "inspected_by"),
    (["certified for", "training"], "Person", "Machine", "certified_for"),
    (["reference deviation", "logged as", "dev-"], "Batch", "Deviation", "references"),
]


def extract_relationships_rulebased(chunk_text, entities):
    text_lower = chunk_text.lower()
    by_type = {}
    for etype, evalue in entities:
        by_type.setdefault(etype, []).append(evalue)

    results = []
    seen = set()
    for keywords, subj_type, obj_type, relation in RULES:
        if not any(kw in text_lower for kw in keywords):
            continue
        subs = by_type.get(subj_type, [])
        objs = by_type.get(obj_type, [])
        for s in subs:
            for o in objs:
                if s == o:
                    continue
                key = (subj_type, s, relation, obj_type, o)
                if key in seen:
                    continue
                seen.add(key)
                results.append({
                    "subject_type": subj_type, "subject_value": s,
                    "relation": relation,
                    "object_type": obj_type, "object_value": o,
                })
    return results


def main():
    chunks = json.load(open(CHUNKS_PATH))
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    client = anthropic.Anthropic()

    total_relations = 0
    for c in chunks:
        entities = extract_entities(c["text"])
        for etype, evalue in entities:
            upsert_entity(conn, etype, evalue)
            conn.execute(
                "INSERT INTO chunk_entities (chunk_id, entity_type, entity_value, source_file) VALUES (?, ?, ?, ?)",
                (c["id"], etype, evalue, c["source_file"]),
            )

        relations = extract_relationships_llm(client, c["text"], entities)
        for r in relations:
            conn.execute(
                """INSERT INTO relationships
                   (subject_type, subject_value, relation, object_type, object_value, source_chunk_id, source_file)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    r.get("subject_type"), r.get("subject_value"),
                    r.get("relation"),
                    r.get("object_type"), r.get("object_value"),
                    c["id"], c["source_file"],
                ),
            )
            total_relations += 1
        conn.commit()
        print(f"{c['id']}: {len(entities)} entities, {len(relations)} relation(s)")

    conn.commit()
    print(f"\nDone. {total_relations} relationships stored in {DB_PATH}")


if __name__ == "__main__":
    main()
