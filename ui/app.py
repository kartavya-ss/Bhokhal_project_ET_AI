"""
Task 9 + Task 16: Streamlit UI. Chat box on the left, cited answer below it,
interactive relationship graph on the right -- wired to the same router
Teammate A (you) built in query_engine.py.

Run with: streamlit run app.py
"""
import sys
import os
import streamlit as st
import streamlit.components.v1 as components

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from query_engine import answer_question, find_entities_in_question
from build_graph import build_graph_html
import sqlite3

DB_PATH = "/home/claude/meridian/db/meridian.sqlite"
GRAPH_OUT = "/home/claude/meridian/ui/graph_current.html"

st.set_page_config(page_title="Meridian Industrial Knowledge Intelligence", layout="wide")

st.title("🏭 Meridian Pharmaceuticals — Industrial Knowledge Intelligence Platform")
st.caption("Hybrid RAG: SQLite (hard facts) + ChromaDB (semantic context) + Claude (cited synthesis)")

if "history" not in st.session_state:
    st.session_state.history = []

BENCHMARK_QUESTIONS = [
    "Which deviation report is linked to the failed Batch 2602, and what machine caused it?",
    "What was the root cause of the Batch MP-PCM-2602 failure?",
    "Which SOP covers preventive maintenance for TCM-04, and was it followed?",
    "Who operated Machine TCM-04 and are they trained on it?",
    "Why did Batch 2601 pass when Batch 2602 failed?",
]

col_chat, col_graph = st.columns([3, 2])

with col_chat:
    st.subheader("Ask a question")
    with st.form("question_form", clear_on_submit=False):
        question = st.text_input(
            "e.g. Which deviation report is linked to the failed Batch 2602, and what machine caused it?",
            key="question_input",
        )
        submitted = st.form_submit_button("Ask")

    st.markdown("**Try a benchmark question:**")
    bq_cols = st.columns(len(BENCHMARK_QUESTIONS[:3]))
    for i, bq in enumerate(BENCHMARK_QUESTIONS[:3]):
        if bq_cols[i].button(bq[:30] + "...", key=f"bq_{i}"):
            question = bq
            submitted = True

    if submitted and question:
        with st.spinner("Querying both brains..."):
            result = answer_question(question)
        st.session_state.history.insert(0, result)

    for result in st.session_state.history:
        st.markdown(f"### Q: {result['question']}")
        st.markdown(result["answer"])
        with st.expander(f"🔎 Evidence used ({len(result['facts'])} facts, {len(result['chunks'])} chunks)"):
            st.markdown("**Hard facts (SQLite):**")
            for s_t, s_v, rel, o_t, o_v, src in result["facts"]:
                st.text(f"{s_t}:{s_v} --[{rel}]--> {o_t}:{o_v}   (Source: {src})")
            st.markdown("**Context chunks (ChromaDB):**")
            for c in result["chunks"]:
                st.text(f"[{c['source_file']}] {c['text'][:150]}...")
        st.divider()

with col_graph:
    st.subheader("Knowledge Graph")
    latest_entities = None
    if st.session_state.history:
        conn = sqlite3.connect(DB_PATH)
        latest_entities = find_entities_in_question(st.session_state.history[0]["question"], conn=conn)
        conn.close()

    build_graph_html(GRAPH_OUT, focus_entities=latest_entities if latest_entities else None)
    with open(GRAPH_OUT, "r") as f:
        graph_html = f.read()
    components.html(graph_html, height=520, scrolling=True)

    if not st.session_state.history:
        st.caption("Ask a question to see the relevant entity graph focus in.")
