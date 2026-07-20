"""
streamlit_app.py
Meridian — end-user chat interface. Ask a question, get an answer. Nothing else.

No document counts, no entity browser, no knowledge graph — those are internal
tooling now living in admin_app.py. This file is the actual product surface.

Run:
    streamlit run streamlit_app.py
"""

import os
import sqlite3
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

DB_PATH = str(Path(__file__).resolve().parent.parent / "entity_extraction" / "output" / "meridian.db")

st.set_page_config(page_title="Meridian", page_icon="🧪", layout="centered")

# Hide every trace of Streamlit chrome — sidebar, menu, footer, header —
# so this reads as a standalone product, not a dev tool.
st.markdown("""
<style>
    #MainMenu, header, footer, [data-testid="stSidebar"], [data-testid="collapsedControl"] {
        visibility: hidden;
        display: none;
    }
    .block-container {
        padding-top: 3rem;
        max-width: 720px;
    }
    .meridian-title {
        font-size: 2rem;
        font-weight: 700;
        margin-bottom: 0.1rem;
    }
    .meridian-subtitle {
        color: #8a8a8a;
        font-size: 0.95rem;
        margin-bottom: 2rem;
    }
    .meridian-sources {
        font-size: 0.8rem;
        color: #8a8a8a;
        margin-top: 0.3rem;
    }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Retrieval + answer generation
# (Same interim SQL-grounded approach as before — this is the seam where the
# hybrid vector+SQL router plugs in later. Nothing about the UI below depends
# on how this function works internally.)
# ---------------------------------------------------------------------------

STOPWORDS = {
    "what", "which", "when", "where", "does", "did", "the", "and", "for",
    "with", "was", "were", "have", "has", "this", "that", "used", "how",
    "many", "much", "are", "you", "tell", "about", "show", "list",
}


def extract_keywords(question: str) -> list[str]:
    words = [w.strip("?.,!:;\"'()").lower() for w in question.split()]
    return [w for w in words if len(w) >= 4 and w not in STOPWORDS] or [question]


def retrieve_context(question: str, db_path: str, top_k: int = 12) -> list[dict]:
    keywords = extract_keywords(question)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    clauses = " OR ".join(["e.entity_name LIKE ? OR em.context_snippet LIKE ?"] * len(keywords))
    params = []
    for kw in keywords:
        params.extend([f"%{kw}%", f"%{kw}%"])

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
    conn.close()
    return [dict(r) for r in rows]


def generate_answer(question: str, context_rows: list[dict]) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return "Something's not configured correctly on our end — please contact support."

    if not context_rows:
        return "I couldn't find anything related to that in the available records."

    context_text = "\n".join(
        f"- [{r['document_id']} / {r['chunk_id']} / page {r['page']}] "
        f"{r['entity_type']}: {r['entity_name']}"
        + (f" ({r['entity_code']})" if r["entity_code"] else "")
        + (f" — context: {r['context_snippet']}" if r["context_snippet"] else "")
        for r in context_rows
    )

    client = genai.Client(api_key=api_key)
    system_prompt = (
        "You answer questions about pharmaceutical manufacturing records using ONLY "
        "the structured entity data provided below. If the context doesn't contain "
        "the answer, say so directly — never guess or use outside knowledge. Answer "
        "in plain, direct prose. Do not mention databases, entities, or internal "
        "system details — just answer as if you know the manufacturing records."
    )
    resp = client.models.generate_content(
        model="gemini-flash-latest",
        contents=f"Context:\n{context_text}\n\nQuestion: {question}",
        config=types.GenerateContentConfig(system_instruction=system_prompt, temperature=0.2),
    )
    return resp.text


def format_sources(context_rows: list[dict]) -> str:
    """A minimal, non-technical source line — document + page only, no entity
    types, no chunk IDs, no counts. Just enough for audit trust in a pharma
    context without looking like a debug panel."""
    seen = []
    for r in context_rows:
        label = f"{r['document_id']} (p.{r['page']})"
        if label not in seen:
            seen.append(label)
    return ", ".join(seen[:5])


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

st.markdown('<div class="meridian-title">🧪 Meridian</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="meridian-subtitle">Ask anything about your manufacturing records.</div>',
    unsafe_allow_html=True,
)

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

if not Path(DB_PATH).exists():
    st.info("Meridian is still getting set up — check back shortly.")
    st.stop()

for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"], avatar="🧪" if msg["role"] == "assistant" else None):
        st.markdown(msg["content"])
        if msg.get("sources_label"):
            st.markdown(
                f'<div class="meridian-sources">Sources: {msg["sources_label"]}</div>',
                unsafe_allow_html=True,
            )

question = st.chat_input("Message Meridian...")
if question:
    st.session_state.chat_history.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant", avatar="🧪"):
        with st.spinner("Thinking..."):
            context_rows = retrieve_context(question, DB_PATH)
            answer = generate_answer(question, context_rows)
        st.markdown(answer)
        sources_label = format_sources(context_rows) if context_rows else None
        if sources_label:
            st.markdown(
                f'<div class="meridian-sources">Sources: {sources_label}</div>',
                unsafe_allow_html=True,
            )

    st.session_state.chat_history.append(
        {"role": "assistant", "content": answer, "sources_label": sources_label}
    )