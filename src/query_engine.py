"""
The Router (Task 13) + Answer Prompt (Task 11).

Given a user question:
  1. Decide whether it needs the relational brain (SQLite), the semantic brain
     (ChromaDB), or both -- default to both, since merging is usually correct
     and heuristic misses are worse than one extra query.
  2. Pull hard facts from SQLite for any entities mentioned/implied.
  3. Pull contextual chunks from ChromaDB by meaning.
  4. Feed both into Claude with a strict "always cite source_file" system prompt.
"""
import re
import json
import sqlite3
import pickle
import chromadb
import anthropic
from chromadb.utils.embedding_functions import EmbeddingFunction

DB_PATH = "/home/claude/meridian/db/meridian.sqlite"
CHROMA_DIR = "/home/claude/meridian/db/chroma"
TFIDF_PATH = "/home/claude/meridian/db/tfidf_vectorizer.pkl"

ENTITY_PATTERNS = {
    "Machine": r"\bTCM-\d{2}\b",
    "Batch": r"\bMP-PCM-\d{4}\b",
    "SOP": r"\bENG-\d{3}\b|\bQA-\d{3}\b",
    "Deviation": r"\bDEV-\d{4}-\d{3}\b",
}
KNOWN_PEOPLE = ["Priya Nair", "Rajesh Kumar", "Anita Desai", "Suresh Iyer"]

SQL_TRIGGER_WORDS = [
    "which", "who", "when", "what machine", "what batch", "linked", "related",
    "history", "record", "certified", "trained", "operated", "supervised",
]
VECTOR_TRIGGER_WORDS = [
    "why", "how", "root cause", "reason", "explain", "context", "describe",
]


class LoadedTfidfEmbeddingFunction(EmbeddingFunction):
    """Loads the same fitted vectorizer used at ingestion time, so query-time
    embeddings live in the same vector space as the stored chunks."""
    def __init__(self, vectorizer):
        self.vectorizer = vectorizer

    def __call__(self, input):
        return [v.tolist() for v in self.vectorizer.transform(input).toarray()]


def find_entities_in_question(question, conn=None):
    found = []
    for etype, pattern in ENTITY_PATTERNS.items():
        for m in set(re.findall(pattern, question, flags=re.IGNORECASE)):
            found.append((etype, m.upper()))
    for name in KNOWN_PEOPLE:
        if name.lower() in question.lower():
            found.append(("Person", name))

    # Casual references: "Batch 2602", "TCM04", "machine 4" etc. Resolve against
    # the actual entity table so partial/loosely-formatted mentions still hit.
    if conn is not None and not any(t in ("Batch", "Machine") for t, _ in found):
        bare_numbers = re.findall(r"\b(\d{2,4})\b", question)
        for num in bare_numbers:
            cur = conn.execute(
                "SELECT entity_type, entity_value FROM entities WHERE entity_value LIKE ?",
                (f"%{num}%",),
            )
            found.extend(cur.fetchall())
    return list(set(found))


def query_relational_brain(question, conn):
    """Pull all relationships touching any entity mentioned in the question.
    If no entities are named explicitly, widen to the most-connected entities
    (a cheap proxy for 'what's this question probably about')."""
    entities = find_entities_in_question(question, conn=conn)
    facts = []

    if entities:
        for etype, evalue in entities:
            cur = conn.execute(
                """SELECT subject_type, subject_value, relation, object_type, object_value, source_file
                   FROM relationships
                   WHERE subject_value = ? OR object_value = ?""",
                (evalue, evalue),
            )
            facts.extend(cur.fetchall())
    else:
        # No explicit entity in the question -- return a small general sample
        # so the router still has *some* hard-fact grounding to offer.
        cur = conn.execute(
            """SELECT subject_type, subject_value, relation, object_type, object_value, source_file
               FROM relationships LIMIT 10"""
        )
        facts.extend(cur.fetchall())

    # de-dupe
    seen = set()
    unique_facts = []
    for f in facts:
        if f not in seen:
            seen.add(f)
            unique_facts.append(f)
    return unique_facts


def query_semantic_brain(question, collection, n_results=4):
    results = collection.query(query_texts=[question], n_results=n_results)
    hits = []
    for doc, meta, dist in zip(results["documents"][0], results["metadatas"][0], results["distances"][0]):
        hits.append({"text": doc, "source_file": meta["source_file"], "distance": dist})
    return hits


ANSWER_SYSTEM_PROMPT = """You are the Industrial Knowledge Intelligence assistant for Meridian Pharmaceuticals.
You answer questions about batches, machines, deviations, and maintenance by combining two sources:

1. HARD FACTS -- exact relationships pulled from a relational database (100% reliable, structured).
2. CONTEXT CHUNKS -- relevant passages retrieved from source documents (may include reasoning, narrative, root-cause explanations).

Rules:
- Base your answer ONLY on the HARD FACTS and CONTEXT CHUNKS provided below. Do not invent facts.
- ALWAYS cite the source_file for every specific claim, inline, like this: (Source: filename.pdf)
- If the hard facts and context together tell a root-cause chain (e.g. batch -> machine -> missed maintenance),
  walk through that chain explicitly and cite each link.
- If the provided sources don't contain the answer, say so plainly instead of guessing.
- Be concise and factual -- this is for a quality/compliance audit context, not casual conversation.
"""


def answer_question(question):
    conn = sqlite3.connect(DB_PATH)
    facts = query_relational_brain(question, conn)

    chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)
    with open(TFIDF_PATH, "rb") as f:
        vectorizer = pickle.load(f)
    ef = LoadedTfidfEmbeddingFunction(vectorizer)
    collection = chroma_client.get_collection("meridian_chunks", embedding_function=ef)
    chunks = query_semantic_brain(question, collection)

    facts_str = "\n".join(
        f"- {s_t}:{s_v} --[{rel}]--> {o_t}:{o_v}  (Source: {src})"
        for s_t, s_v, rel, o_t, o_v, src in facts
    ) or "(no structured facts matched)"

    chunks_str = "\n\n".join(
        f"[Source: {c['source_file']}]\n{c['text']}" for c in chunks
    )

    user_prompt = f"""Question: {question}

HARD FACTS (from SQLite knowledge graph):
{facts_str}

CONTEXT CHUNKS (from semantic search over source documents):
{chunks_str}

Answer the question, citing sources inline as instructed."""

    client = anthropic.Anthropic()
    try:
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            system=ANSWER_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        answer = resp.content[0].text
    except Exception as e:
        answer = (
            f"[LLM call failed: {e}]\n\n"
            f"Raw retrieved evidence (so you can see the router worked even without the API key):\n\n"
            f"HARD FACTS:\n{facts_str}\n\nCONTEXT:\n{chunks_str}"
        )

    return {
        "question": question,
        "facts": facts,
        "chunks": chunks,
        "answer": answer,
    }


if __name__ == "__main__":
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else \
        "Which deviation report is linked to the failed Batch 2602, and what machine caused it?"
    result = answer_question(q)
    print("QUESTION:", result["question"])
    print("\n--- ANSWER ---")
    print(result["answer"])
