# Meridian

Meridian is a knowledge assistant for pharmaceutical manufacturing documentation. You point it at a pile of PDFs — batch records, SOPs, deviation reports, maintenance logs — and it lets you ask plain-English questions and get answers that are actually grounded in those documents, with sources you can check.

We built this for the Economic Times AI Hackathon.

## The problem we're solving

Pharma manufacturing generates a lot of paperwork: batch manufacturing records, SOPs, CAPAs, equipment maintenance logs, supplier certificates, FDA correspondence. All of it matters for compliance and traceability, but it's scattered across formats and hard to search. If you want to know "why was the preventive maintenance overdue on machine TCM-04," you'd normally have to dig through multiple documents by hand.

Meridian tries to fix that by reading all the documents once, pulling out the structured facts (materials, equipment, operators, SOP references, and how they relate to each other), and then answering questions using that structured knowledge plus the original document text — not just guessing from a language model's general knowledge.

## How it actually works

The pipeline has five stages, and each one lives in its own folder so it's easy to run or debug independently.

**1. Ingestion** (`ingestion/`)
Takes the raw documents, pulls out the text, and splits it into chunks small enough to embed and search individually. Output is `chunks.json`, which every later stage reads from.

**2. Entity extraction** (`entity_extraction/`)
Runs each chunk through Gemini with a prompt that asks it to identify entities — materials, equipment, operators, SOP references — and any relationships between them (e.g. "Material X was used in Batch Y"). These get written into a SQLite database (`meridian.db`). We also do entity resolution here: if the same material shows up as "Microcrystalline Cellulose" on one page and "MCC NF" on another, but they share the same supplier code, we merge them into one entity record instead of creating duplicates.

**3. Knowledge graph** (`knowledge_graph/`)
Reads the relationships out of the entity store and renders them as an interactive graph (using PyVis) so you can visually explore how equipment, materials, and process steps connect to each other.

**4. Vector embeddings** (`vector_embedding/`)
Takes the same chunks from stage 1, embeds them with a sentence-transformer model, and stores them in ChromaDB so we can do semantic search — finding chunks that are conceptually related to a question even if they don't share exact keywords.

**5. Frontend** (`frontend/`)
Two Streamlit apps:
- `streamlit_app.py` — the clean, end-user chat interface. Ask a question, get an answer with sources.
- `admin_app.py` — an internal tool with the same chat, plus the knowledge graph view, an entity browser, and a document library.

## Answering a question: three sources, not one

When you ask a question, Meridian doesn't rely on just one retrieval method. It pulls from three places and combines them:

- **Vector search** (ChromaDB) — finds chunks that are semantically similar to the question.
- **Entity store** (SQLite) — finds exact keyword/code matches, which vector search sometimes misses (e.g. an exact material code like `SUP-1187`).
- **Knowledge graph** — pulls in relationships that help explain *why* things are connected, not just *what* they are.

All three get fed into Gemini along with the question, and the model is instructed to answer only from that context and cite its sources.

## Corrective RAG (CRAG)

This is the part we're most proud of. A plain RAG system just trusts whatever the vector search's top results happen to be — even if they're a bad match for the question. That's a real problem: embeddings can miss on jargon, typos, or questions phrased differently from the source text, and the model will still confidently answer from whatever garbage it was handed.

Our retrieval pipeline (`vector_embedding/src/crag.py`) adds a grading step in between retrieval and answering:

1. Retrieve the top chunks from the vector store, same as normal.
2. Have an LLM grade each chunk against the question: is it `CORRECT`, `AMBIGUOUS`, or `INCORRECT`?
3. Decide what to do based on that, instead of blindly trusting the top results:
   - If most chunks grade `CORRECT`, just answer from them.
   - If the grades are mixed, keep what's good and broaden the search — pull more chunks from the vector store and also check the entity store, to fill in the gaps.
   - If everything grades `INCORRECT` (or the vector store returns nothing at all), throw away those results entirely and fall back to the entity and knowledge-graph stores, which use exact code/keyword matching and often catch what semantic search missed.

The point is: never confidently answer off context that's actually irrelevant, and never give up just because the first search attempt came back weak.

We also had to handle the fact that the Gemini API occasionally returns a `503` when it's under heavy load. The grader retries a couple of times with a short backoff, and if it's still failing after that, it grades the chunk as `AMBIGUOUS` rather than crashing the whole app — same idea for the final answer-generation call.

## Tech stack

- **Python 3.11+**
- **Gemini API** — entity extraction, relevance grading, and final answer generation
- **ChromaDB** — vector store for semantic search
- **Sentence Transformers** (`all-MiniLM-L6-v2`) — embeddings
- **SQLite** — structured entity/relationship store
- **PyVis** — interactive knowledge graph rendering
- **Streamlit** — both frontend apps
- **pytest** — test suite, with the Gemini client mocked so tests run offline

## Running it yourself

**1. Install dependencies**
```bash
python -m pip install -r requirements.txt
```

**2. Set your API key**

Copy `.env.example` to `.env` and put your Gemini key in it:
```
GEMINI_API_KEY=your_actual_key
```

**3. Run the pipeline in order**
```bash
# ingest documents into chunks.json
cd ingestion/src && python ingest.py

# extract entities + build the SQLite store
cd ../../entity_extraction/src
python build_db.py
python extract_entities.py --chunks ../../ingestion/output/chunks.json
python load_entities.py

# build the knowledge graph
cd ../../knowledge_graph/src
python build_graph.py --db ../../entity_extraction/output/meridian.db

# build the vector index
cd ../../vector_embedding/src
python build_vector_store.py
```

**4. Launch the app**
```bash
cd frontend
streamlit run admin_app.py       # full internal tool: chat + graph + entity browser
# or
streamlit run streamlit_app.py   # clean, end-user chat only
```

**5. Run the tests**
```bash
python -m pytest -q
```
Every test mocks the Gemini client, so this runs fully offline — no API key or network access needed. The suite covers entity extraction parsing, entity-resolution/dedup logic, all three CRAG decision paths, and the retry/fallback behavior when the Gemini API is unavailable.

## Module details

### Ingestion

The ingestion stage extracts text and tables into `ingestion/output/extracted_documents.json`, then creates `ingestion/output/chunks.json`. Each chunk contains `chunk_id`, `document_id`, `source_type`, `page`, and `text`. Tables use `[TABLE N]` markers and pipe-separated rows. The included sensor CSV is intentionally kept as structured data rather than narrative chunks.

Run it from the repository root:

```bash
python ingestion/src/extract_text.py
python ingestion/src/chunk_text.py
```

### Entity extraction and SQLite schema

The entity stage uses Gemini to extract materials, SOP references, operators, equipment, process steps, parameters, batch IDs, timestamps, and relationships. The SQLite schema is `documents -> entity_mentions -> entities`, with a separate `relationships` table.

```bash
python entity_extraction/src/build_db.py --extracted-docs ingestion/output/extracted_documents.json --db entity_extraction/output/meridian.db
python entity_extraction/src/extract_entities.py --chunks ingestion/output/chunks.json --out entity_extraction/output/extracted_entities.json
python entity_extraction/src/load_entities.py --extracted entity_extraction/output/extracted_entities.json --db entity_extraction/output/meridian.db
python entity_extraction/src/query_examples.py --db entity_extraction/output/meridian.db
```

### Knowledge graph

The graph stage reads relationships from `meridian.db` and writes a self-contained PyVis HTML export:

```bash
python knowledge_graph/src/build_graph.py --db entity_extraction/output/meridian.db --out knowledge_graph/output/knowledge_graph.html
```

Open the generated HTML directly in a browser.

### Vector search and CRAG

The vector stage indexes `ingestion/output/chunks.json` in ChromaDB. `generate_answer.py` combines vector chunks, SQLite entity matches, and knowledge-graph relationships. CRAG grades vector chunks before answer generation and broadens retrieval when the vector results are weak.

```bash
python vector_embedding/src/build_vector_store.py
python vector_embedding/src/query_store.py
python vector_embedding/src/generate_answer.py
```

### Outputs

| Path | Purpose |
|---|---|
| `ingestion/output/chunks.json` | Chunked document text |
| `entity_extraction/output/meridian.db` | Entity and relationship store |
| `knowledge_graph/output/knowledge_graph.html` | Interactive graph export |
| `vector_embedding/output/chroma_db/` | Persistent vector index |

## What each output file is

| File | What it is |
|---|---|
| `ingestion/output/chunks.json` | Document text, split into chunks |
| `entity_extraction/output/meridian.db` | The structured entity + relationship store |
| `knowledge_graph/output/knowledge_graph.html` | The interactive graph you can open in a browser |
| `vector_embedding/output/chroma_db/` | The vector index used for semantic search |

## Where this could go next

- A smarter router that picks between vector, entity, and graph retrieval based on the *type* of question, instead of always querying all three
- Better reranking of retrieved chunks before they're handed to the model
- Multi-document summarization — e.g. "summarize every deviation report for Batch X"
- Turning this into a proper deployed API instead of a local Streamlit demo

## Summary

Meridian takes scattered pharmaceutical manufacturing documents and turns them into something you can actually query — with structured facts, a visual relationship graph, semantic search, and a Corrective RAG layer that checks its own retrieval before answering instead of guessing. Built end-to-end for the Economic Times AI Hackathon.