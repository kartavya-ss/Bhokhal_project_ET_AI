import os
import sqlite3
import time
from pathlib import Path

import chromadb
from dotenv import load_dotenv
from google import genai
from sentence_transformers import SentenceTransformer

from crag import LLMGraderClient, corrective_retrieve

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[2]
CHROMA_DB_PATH = BASE_DIR / "vector_embedding" / "output" / "chroma_db"
COLLECTION_NAME = "meridian_chunks"
DB_PATH = BASE_DIR / "entity_extraction" / "output" / "meridian.db"

STOPWORDS = {
    "what", "which", "when", "where", "does", "did", "the", "and", "for",
    "with", "was", "were", "have", "has", "this", "that", "used", "how",
    "many", "much", "are", "you", "tell", "about", "show", "list",
}


def extract_keywords(question: str) -> list[str]:
    words = [w.strip("?.,!:;\"'()[]{}\n").lower() for w in question.split()]
    return [w for w in words if len(w) >= 3 and w not in STOPWORDS] or [question]


embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
chroma_client = chromadb.PersistentClient(path=str(CHROMA_DB_PATH))
collection = chroma_client.get_collection(name=COLLECTION_NAME)
api_key = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=api_key) if api_key else None
ANSWER_UNAVAILABLE = "Sorry, the AI service is temporarily unavailable. Please try again in a moment."


def retrieve_vector_chunks(question, top_k=5):
    query_embedding = embedding_model.encode([question]).tolist()
    results = collection.query(query_embeddings=query_embedding, n_results=top_k)

    chunks = []
    for i in range(len(results["ids"][0])):
        chunks.append({
            "chunk_id": results["ids"][0][i],
            "text": results["documents"][0][i],
            "document_id": results["metadatas"][0][i]["document_id"],
            "page": results["metadatas"][0][i]["page"],
        })
    return chunks


def retrieve_entity_context(question, top_k=4):
    keywords = extract_keywords(question)
    clauses = " OR ".join(["e.entity_name LIKE ? OR em.context_snippet LIKE ?"] * len(keywords))
    params = []
    for kw in keywords:
        params.extend([f"%{kw}%", f"%{kw}%"])

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT em.document_id, em.chunk_id, em.page, em.context_snippet,
                   e.entity_name, e.entity_type, e.entity_code, em.attributes_json
            FROM entity_mentions em
            JOIN entities e ON e.entity_id = em.entity_id
            WHERE {clauses}
            LIMIT ?
            """,
            (*params, top_k),
        ).fetchall()

    return [dict(r) for r in rows]


def retrieve_graph_context(question, top_k=4):
    keywords = extract_keywords(question)
    clauses = " OR ".join(["e1.entity_name LIKE ? OR e2.entity_name LIKE ?"] * len(keywords))
    params = []
    for kw in keywords:
        params.extend([f"%{kw}%", f"%{kw}%"])

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT e1.entity_name AS source_name,
                   e1.entity_type AS source_type,
                   r.relationship_type,
                   e2.entity_name AS target_name,
                   e2.entity_type AS target_type,
                   r.document_id,
                   r.chunk_id
            FROM relationships r
            JOIN entities e1 ON e1.entity_id = r.entity_id_1
            JOIN entities e2 ON e2.entity_id = r.entity_id_2
            WHERE {clauses}
            LIMIT ?
            """,
            (*params, top_k),
        ).fetchall()

    return [dict(r) for r in rows]


def build_context_text(question, vector_chunks, entity_rows, graph_rows):
    sections = []

    if vector_chunks:
        vector_block = []
        for chunk in vector_chunks:
            vector_block.append(
                f"[Vector retrieval] {chunk['document_id']} (page {chunk['page']}):\n{chunk['text']}"
            )
        sections.append("VECTOR STORE CONTEXT:\n" + "\n\n---\n\n".join(vector_block))

    if entity_rows:
        entity_block = []
        for row in entity_rows:
            entity_block.append(
                f"[Entity store] {row['document_id']} (page {row['page']}): "
                f"{row['entity_type']}: {row['entity_name']}"
                + (f" ({row['entity_code']})" if row['entity_code'] else "")
                + (f" — {row['context_snippet']}" if row['context_snippet'] else "")
            )
        sections.append("ENTITY STORE CONTEXT:\n" + "\n\n".join(entity_block))

    if graph_rows:
        graph_block = []
        for row in graph_rows:
            graph_block.append(
                f"[Knowledge graph] {row['source_name']} ({row['source_type']}) "
                f"{row['relationship_type']} {row['target_name']} ({row['target_type']}) "
                f"in {row['document_id']}"
            )
        sections.append("KNOWLEDGE GRAPH CONTEXT:\n" + "\n\n".join(graph_block))

    if not sections:
        return "No supporting context was found in the vector store, entity store, or knowledge graph."

    return "\n\n".join(sections)


def build_prompt(question, context_text):
    prompt = f"""You are an industrial knowledge assistant for Meridian Pharmaceuticals.
Answer the question ONLY using the evidence in the context below.
Do not use outside knowledge.
If the evidence is incomplete, say so clearly.

For every factual claim, cite the source in this format: (Source: filename, page X)
Use the entity and graph evidence as support when they help explain relationships.

CONTEXT:
{context_text}

QUESTION: {question}

ANSWER:"""
    return prompt


def _entity_rows_as_chunks(rows: list[dict]) -> list[dict]:
    """Adapt entity_mentions rows to the {chunk_id, text, document_id, page}
    shape CRAG grades, so entity-store hits can stand in for vector chunks
    when we broaden."""
    return [
        {
            "chunk_id": r.get("chunk_id"),
            "document_id": r["document_id"],
            "page": r.get("page"),
            "text": r.get("context_snippet") or r["entity_name"],
        }
        for r in rows
    ]


def answer_with_sources(question, top_k=5, use_crag=True):
    graph_rows = retrieve_graph_context(question, top_k=4)

    if use_crag:
        grader = LLMGraderClient(client=client)
        result = corrective_retrieve(
            question,
            retrieve_vector_fn=retrieve_vector_chunks,
            retrieve_entity_fn=lambda q, k: _entity_rows_as_chunks(retrieve_entity_context(q, top_k=k)),
            grader=grader,
            top_k=top_k,
            broaden_top_k=max(top_k * 2, 10),
        )
        vector_chunks = result.chunks
        entity_rows = retrieve_entity_context(question, top_k=4)  # still shown as structured entity evidence
        print(f"[CRAG] action={result.action} correct_ratio={result.correct_ratio:.2f} "
              f"chunks_used={len(vector_chunks)}")
    else:
        vector_chunks = retrieve_vector_chunks(question, top_k)
        entity_rows = retrieve_entity_context(question, top_k=4)

    context_text = build_context_text(question, vector_chunks, entity_rows, graph_rows)

    prompt = build_prompt(question, context_text)
    try:
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model="gemini-flash-latest",
                    contents=prompt,
                )
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(2**attempt)
    except Exception:
        return {
            "answer": ANSWER_UNAVAILABLE,
            "vector_chunks": vector_chunks,
            "entity_rows": entity_rows,
            "graph_rows": graph_rows,
            "crag_action": result.action if use_crag else None,
        }

    return {
        "answer": response.text,
        "vector_chunks": vector_chunks,
        "entity_rows": entity_rows,
        "graph_rows": graph_rows,
        "crag_action": result.action if use_crag else None,
    }


def generate_answer(question, top_k=5, use_crag=True):
    result = answer_with_sources(question, top_k=top_k, use_crag=use_crag)

    print(f"\nQUESTION: {question}\n")
    print(f"ANSWER:\n{result['answer']}\n")
    if result["crag_action"]:
        print(f"[CRAG] action={result['crag_action']}")
    print("Retrieved from:")
    for c in result["vector_chunks"]:
        print(f"  - Vector/broadened: {c['document_id']} (page {c['page']})")
    for e in result["entity_rows"]:
        print(f"  - Entity: {e['document_id']} (page {e['page']}) - {e['entity_type']}: {e['entity_name']}")
    for g in result["graph_rows"]:
        print(f"  - Graph: {g['source_name']} -> {g['target_name']} ({g['relationship_type']})")

    return result


if __name__ == "__main__":
    test_questions = [
        "Why was the preventive maintenance overdue on TCM-04?",
        "What corrective actions were taken after the deviation?",
    ]
    for q in test_questions:
        generate_answer(q)
        print("=" * 70)