"""
streamlit_app.py
Meridian — end-user chat interface. Ask a question, get an answer. Nothing else.

No document counts, no entity browser, no knowledge graph — those are internal
tooling now living in admin_app.py. This file is the actual product surface.

Run:
    streamlit run streamlit_app.py
"""

import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

DB_PATH = str(Path(__file__).resolve().parent.parent / "entity_extraction" / "output" / "meridian.db")
VECTOR_SRC = Path(__file__).resolve().parent.parent / "vector_embedding" / "src"
if str(VECTOR_SRC) not in sys.path:
    sys.path.insert(0, str(VECTOR_SRC))
from generate_answer import answer_with_sources  # noqa: E402

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
            result = answer_with_sources(question)
        answer = result["answer"]
        st.markdown(answer)
        source_rows = result["vector_chunks"] + result["entity_rows"] + result["graph_rows"]
        sources_label = ", ".join(
            f"{row.get('document_id', row.get('source_name', 'graph'))} (p.{row.get('page', '?')})"
            for row in source_rows[:5]
        ) or None
        if sources_label:
            st.markdown(
                f'<div class="meridian-sources">Sources: {sources_label}</div>',
                unsafe_allow_html=True,
            )

    st.session_state.chat_history.append(
        {"role": "assistant", "content": answer, "sources_label": sources_label}
    )