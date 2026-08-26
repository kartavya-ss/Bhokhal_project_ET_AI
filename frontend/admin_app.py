"""
streamlit_app.py
Meridian — pharma manufacturing knowledge management UI.

Four tabs:
    1. Ask a Question   — Q&A grounded in the hybrid retrieval pipeline.
    2. Knowledge Graph   — interactive pyvis graph embedded in-app.
    3. Entity Explorer   — browse/search materials, operators, SOPs, etc.
    4. Document Library  — every ingested document with its category tag.

Run:
    streamlit run streamlit_app.py
"""

import json
import os
import sqlite3
import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from pyvis.network import Network

load_dotenv()

DEFAULT_DB_PATH = str(Path(__file__).resolve().parent.parent / "entity_extraction" / "output" / "meridian.db")
VECTOR_SRC = Path(__file__).resolve().parent.parent / "vector_embedding" / "src"
if str(VECTOR_SRC) not in sys.path:
    sys.path.insert(0, str(VECTOR_SRC))
from generate_answer import answer_with_sources  # noqa: E402

st.set_page_config(page_title="Meridian", page_icon="🧪", layout="wide")

# Same palette as knowledge_graph/src/build_graph.py — kept in sync manually.
# Inlined rather than imported: cross-module sys.path imports proved fragile
# depending on the working directory the app is launched from.
TYPE_COLORS = {
    "MATERIAL": "#1D9E75",
    "OPERATOR": "#7F77DD",
    "SOP_REFERENCE": "#D85A30",
    "EQUIPMENT": "#378ADD",
    "PROCESS_STEP": "#D4537E",
    "PARAMETER": "#EF9F27",
    "BATCH_ID": "#888780",
    "TIMESTAMP": "#B4B2A9",
}
DEFAULT_COLOR = "#888780"


def fetch_edges(db_path: str, document_id: str | None):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    query = """
        SELECT e1.entity_id AS src_id, e1.entity_name AS src_name, e1.entity_type AS src_type,
               e2.entity_id AS dst_id, e2.entity_name AS dst_name, e2.entity_type AS dst_type,
               r.relationship_type
        FROM relationships r
        JOIN entities e1 ON e1.entity_id = r.entity_id_1
        JOIN entities e2 ON e2.entity_id = r.entity_id_2
    """
    params = ()
    if document_id:
        query += " WHERE r.document_id = ?"
        params = (document_id,)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return rows


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def get_conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def db_exists(db_path: str) -> bool:
    return Path(db_path).exists()


def render_ask_tab(db_path: str):
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("sources"):
                with st.expander("Sources"):
                    for source_type, sources in msg["sources"].items():
                        st.markdown(f"**{source_type.title()}**")
                        for source in sources:
                            st.json(source)
            if msg.get("crag_action"):
                st.caption(f"CRAG: {msg['crag_action']}")

    question = st.chat_input("Ask about materials, SOPs, operators, batches...")
    if question:
        st.session_state.chat_history.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"):
            with st.spinner("Searching the knowledge store..."):
                result = answer_with_sources(question)
                answer = result["answer"]
            st.markdown(answer)
            with st.expander("Sources"):
                for source_type, sources in {
                    "vector": result["vector_chunks"],
                    "entity": result["entity_rows"],
                    "graph": result["graph_rows"],
                }.items():
                    st.markdown(f"**{source_type.title()}**")
                    if sources:
                        for source in sources:
                            st.json(source)
                    else:
                        st.caption("No sources")
            st.caption(f"CRAG: {result['crag_action']}")

        st.session_state.chat_history.append(
            {
                "role": "assistant",
                "content": answer,
                "sources": {
                    "vector": result["vector_chunks"],
                    "entity": result["entity_rows"],
                    "graph": result["graph_rows"],
                },
                "crag_action": result["crag_action"],
            }
        )


# ---------------------------------------------------------------------------
# Tab 2 — Knowledge Graph
# ---------------------------------------------------------------------------

def render_graph_tab(db_path: str):
    conn = get_conn(db_path)
    doc_ids = [r["document_id"] for r in conn.execute("SELECT document_id FROM documents ORDER BY document_id")]
    conn.close()

    col1, col2 = st.columns([3, 1])
    with col1:
        selected_doc = st.selectbox("Filter to a document (optional)", ["All documents"] + doc_ids)
    with col2:
        st.write("")
        st.write("")
        regenerate = st.button("🔄 Regenerate graph", use_container_width=True)

    doc_filter = None if selected_doc == "All documents" else selected_doc
    cache_key = f"graph_html_{doc_filter}"

    if regenerate or cache_key not in st.session_state:
        rows = fetch_edges(db_path, doc_filter)
        if not rows:
            st.info("No relationships found for this filter. Run load_entities.py first, or pick a different document.")
            return

        net = Network(height="700px", width="100%", directed=True, notebook=False, cdn_resources="in_line")
        net.barnes_hut(gravity=-3000, central_gravity=0.3, spring_length=120, spring_strength=0.04)
        added = set()
        for row in rows:
            for eid, name, etype in [
                (row["src_id"], row["src_name"], row["src_type"]),
                (row["dst_id"], row["dst_name"], row["dst_type"]),
            ]:
                if eid not in added:
                    net.add_node(eid, label=name, title=f"{etype}: {name}",
                                 color=TYPE_COLORS.get(etype, DEFAULT_COLOR), shape="dot", size=18)
                    added.add(eid)
            net.add_edge(row["src_id"], row["dst_id"], label=row["relationship_type"],
                         title=row["relationship_type"], arrows="to")

        net.set_options("""
        { "edges": {"font": {"size": 10}, "smooth": {"type": "continuous"}},
          "nodes": {"font": {"size": 14}},
          "interaction": {"hover": true} }
        """)
        st.session_state[cache_key] = net.generate_html(notebook=False)

    st.iframe(st.session_state[cache_key], height=720)

    with st.expander("Legend"):
        for etype, color in TYPE_COLORS.items():
            st.markdown(f"<span style='color:{color}'>●</span> {etype}", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Tab 3 — Entity Explorer
# ---------------------------------------------------------------------------

def render_entity_explorer(db_path: str):
    conn = get_conn(db_path)
    types_available = [r["entity_type"] for r in conn.execute(
        "SELECT DISTINCT entity_type FROM entities ORDER BY entity_type"
    )]

    col1, col2 = st.columns([1, 2])
    with col1:
        type_filter = st.selectbox("Entity type", ["All"] + types_available)
    with col2:
        name_search = st.text_input("Search by name", "")

    query = """
        SELECT e.entity_id, e.entity_type, e.entity_name, e.entity_code,
               COUNT(em.mention_id) AS mention_count
        FROM entities e
        LEFT JOIN entity_mentions em ON em.entity_id = e.entity_id
        WHERE 1=1
    """
    params = []
    if type_filter != "All":
        query += " AND e.entity_type = ?"
        params.append(type_filter)
    if name_search:
        query += " AND e.entity_name LIKE ?"
        params.append(f"%{name_search}%")
    query += " GROUP BY e.entity_id ORDER BY mention_count DESC"

    rows = conn.execute(query, params).fetchall()
    st.write(f"{len(rows)} entities found")

    for row in rows:
        with st.expander(
            f"**{row['entity_name']}** — {row['entity_type']}"
            + (f" ({row['entity_code']})" if row["entity_code"] else "")
            + f" · {row['mention_count']} mention(s)"
        ):
            mentions = conn.execute(
                """SELECT document_id, chunk_id, page, context_snippet, attributes_json
                   FROM entity_mentions WHERE entity_id = ?""",
                (row["entity_id"],),
            ).fetchall()
            for m in mentions:
                attrs = json.loads(m["attributes_json"] or "{}")
                attr_str = ", ".join(f"{k}={v}" for k, v in attrs.items())
                st.markdown(
                    f"- `{m['document_id']}` / `{m['chunk_id']}` (page {m['page']})"
                    + (f" — {attr_str}" if attr_str else "")
                )
    conn.close()


# ---------------------------------------------------------------------------
# Tab 4 — Document Library
# ---------------------------------------------------------------------------

def render_document_library(db_path: str):
    conn = get_conn(db_path)
    rows = conn.execute(
        """
        SELECT d.document_id, d.source_type, d.document_category, d.num_pages,
               d.ingested_at, COUNT(DISTINCT em.entity_id) AS entity_count
        FROM documents d
        LEFT JOIN entity_mentions em ON em.document_id = d.document_id
        GROUP BY d.document_id
        ORDER BY d.document_id
        """
    ).fetchall()
    conn.close()

    if not rows:
        st.info("No documents loaded yet. Run build_db.py first.")
        return

    category_filter = st.multiselect(
        "Filter by category",
        sorted({r["document_category"] for r in rows}),
        default=[],
    )

    for row in rows:
        if category_filter and row["document_category"] not in category_filter:
            continue
        badge = {"BMR": "🔵", "SOP": "🟢", "sensor_log": "🟡", "unknown": "⚪"}.get(row["document_category"], "⚪")
        st.markdown(
            f"{badge} **{row['document_id']}** — {row['document_category']} · "
            f"{row['source_type']} · {row['num_pages']} page(s) · "
            f"{row['entity_count']} unique entities · ingested {row['ingested_at']}"
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    st.title("🧪 Meridian")
    st.caption("Pharma manufacturing knowledge management")

    with st.sidebar:
        st.header("Configuration")
        db_path = st.text_input("Database path", DEFAULT_DB_PATH)
        if not db_exists(db_path):
            st.error("Database not found at this path. Run build_db.py + load_entities.py first.")
            st.stop()
        else:
            st.success("Connected to meridian.db")

        conn = get_conn(db_path)
        n_docs = conn.execute("SELECT COUNT(*) AS c FROM documents").fetchone()["c"]
        n_entities = conn.execute("SELECT COUNT(*) AS c FROM entities").fetchone()["c"]
        n_rels = conn.execute("SELECT COUNT(*) AS c FROM relationships").fetchone()["c"]
        conn.close()
        st.metric("Documents", n_docs)
        st.metric("Entities", n_entities)
        st.metric("Relationships", n_rels)

        if not os.environ.get("GEMINI_API_KEY"):
            st.warning("GEMINI_API_KEY not set — Q&A tab won't be able to generate answers.")

    tab1, tab2, tab3, tab4 = st.tabs(
        ["💬 Ask a Question", "🕸️ Knowledge Graph", "🔍 Entity Explorer", "📄 Document Library"]
    )
    with tab1:
        render_ask_tab(db_path)
    with tab2:
        render_graph_tab(db_path)
    with tab3:
        render_entity_explorer(db_path)
    with tab4:
        render_document_library(db_path)


if __name__ == "__main__":
    main()
