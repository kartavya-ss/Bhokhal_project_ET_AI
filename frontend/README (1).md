# Meridian App

Two Streamlit apps in this folder, serving different audiences:

## `streamlit_app.py` — the actual product
Chat-only. Type a question, get an answer with a minimal source line
(`document (p.N)`) underneath. No sidebar, no metrics, no tabs, no way to
browse the database. This is what an end user (e.g. someone on the plant
floor) should see.

```bash
streamlit run streamlit_app.py
```

## `admin_app.py` — internal tooling (not for end users)
The original 4-tab version: knowledge graph, entity explorer, document
library, plus a debug-style Q&A tab showing sources/entity types/document
counts. Useful for you, your teammate, and hackathon judges who want to see
what's under the hood — but never show this to an actual end user.

```bash
streamlit run admin_app.py
```

## Setup (shared)
```bash
pip install streamlit python-dotenv google-genai pyvis
# .env with GEMINI_API_KEY should exist at meridian/ or entity_extraction/ level
```

## Known limitation (both apps)
Retrieval is currently keyword-based against the SQL entity store — real and
working, but not semantic yet. `retrieve_context()` in `streamlit_app.py` is
the function the hybrid vector+SQL router will extend once that piece is built.