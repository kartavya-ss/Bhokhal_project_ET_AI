# Meridian

Meridian turns pharmaceutical manufacturing paperwork — batch records, SOPs, deviation reports, FDA letters, maintenance logs — into something you can actually ask questions of. Instead of digging through PDFs by hand, you ask something like *"why was the preventive maintenance overdue on TCM-04?"* and get an answer grounded in the actual documents, with sources attached.

Built for the Economic Times AI Hackathon.

## Why this exists

Pharma manufacturing generates a huge amount of documentation, and almost all of it matters for compliance and traceability. The problem isn't a lack of records — it's that they're scattered across PDFs, spreadsheets, and scanned images, in different formats, with no easy way to search across all of them or trace an answer back to its source.

Meridian's approach: read every document once, extract the structured facts (what materials, equipment, operators, and SOPs are mentioned, and how they relate to each other), and combine that with semantic search over the raw text. When you ask a question, the answer comes from actual retrieved evidence, not just a language model guessing.

## How the pipeline works

There are five stages, each in its own folder, each producing an output the next stage reads:

```
ingestion  →  entity_extraction  →  knowledge_graph
                     ↓
              vector_embedding  →  frontend
```

### 1. Ingestion (`ingestion/`)
Reads the raw source files in `ingestion/data/` — PDFs, a spreadsheet, a CSV, even a P&ID diagram image — and pulls text out of each one (OCR via `pytesseract` for scanned/image content). That gets split into smaller chunks small enough to embed and search individually.

- `extract_text.py` → writes `ingestion/output/extracted_documents.json`
- `chunk_text.py` → reads that, writes `ingestion/output/chunks.json`
- `verify_output.py` → sanity-checks the chunks (no missing fields, no empty text, no duplicate IDs) before handing off to the next stage

### 2. Entity extraction (`entity_extraction/`)
Sends each chunk to Gemini with a prompt asking it to pull out entities — materials, equipment, operators, SOP references — and any relationships between them (e.g. "Material X was used in Batch Y"). Everything lands in a SQLite database, `meridian.db`.

This is also where entity resolution happens: if "Microcrystalline Cellulose" shows up on one page and "MCC NF" on another, but they share the same supplier code, they get merged into a single entity record instead of creating two. Materials get deduplicated by code first, falling back to a normalized name match when there's no code to go on.

- `build_db.py` — creates the SQLite schema
- `extract_entities.py` — runs the chunks through Gemini
- `load_entities.py` — writes the extracted entities/relationships into the database, handling the dedup logic
- `query_examples.py` — a few example SQL queries against the finished store, useful for sanity-checking what got extracted

### 3. Knowledge graph (`knowledge_graph/`)
Reads the relationships out of the entity store and renders them as an interactive graph with PyVis — open the output HTML file in a browser and you can visually explore how equipment, materials, and process steps connect.

### 4. Vector embeddings (`vector_embedding/`)
Takes the same chunks from ingestion, embeds them with a sentence-transformer model (`all-MiniLM-L6-v2`), and stores the vectors in ChromaDB for semantic search — finding chunks that are conceptually relevant to a question even when the wording doesn't match exactly.

This is also where the actual question-answering logic lives (`generate_answer.py`), which is where things get more interesting — see below.

### 5. Frontend (`frontend/`)
Two Streamlit apps, same underlying pipeline, different audiences:
- **`streamlit_app.py`** — the clean, end-user chat interface. Ask a question, get an answer with sources.
- **`admin_app.py`** — the internal tool: the same chat, plus the interactive knowledge graph, an entity browser, and a document library.

## Answering a question: three sources, combined

A question doesn't just hit one retrieval method. Meridian pulls from three places and merges the results before generating an answer:

| Source | What it's good at |
|---|---|
| **Vector search** (ChromaDB) | Semantic matches — finds conceptually related text even without exact keyword overlap |
| **Entity store** (SQLite) | Exact code/keyword matches — catches things like `SUP-1187` that embeddings can miss |
| **Knowledge graph** | Relationships — helps explain *why* things are connected, not just *what* they are |

All three get assembled into context and handed to Gemini, which is instructed to answer only from that evidence and cite where each claim comes from.

## Corrective RAG (CRAG)

This is the part of the project I spent the most time on, so I want to explain it properly rather than just name-drop it.

A standard RAG pipeline retrieves the top-k nearest chunks from the vector store and hands them straight to the model — no questions asked. That's a real weakness: if the embedding model misses (jargon, typos, a question phrased differently than the source text), the model still gets fed *something*, and it'll answer confidently off irrelevant context rather than admitting it doesn't know.

`vector_embedding/src/crag.py` adds a grading step in between retrieval and generation:

1. **Retrieve** the top vector chunks, same as a normal RAG pipeline would.
2. **Grade** each chunk against the question using an LLM relevance evaluator — `CORRECT`, `AMBIGUOUS`, or `INCORRECT`.
3. **Decide instead of guessing:**
   - Mostly `CORRECT` → use the chunks as-is, answer normally.
   - Mixed grades → keep what's good, and **broaden** the search: pull a wider set of vector results and also check the entity store to fill in the gaps.
   - All `INCORRECT`, or nothing retrieved at all → drop the vector results entirely and fall back to the entity + knowledge-graph stores, which use exact code/keyword matching and often catch what semantic search missed completely.

The idea is simple even if the implementation has a few moving parts: never confidently answer from context that's actually irrelevant, and never give up just because the first retrieval attempt came back weak — broaden instead.

**Handling a flaky API.** Gemini occasionally returns a `503` when it's under heavy load, and a naive implementation would just crash the whole app on that. The grader retries a couple of times with a short backoff, and if it's still failing after that, it grades the chunk as `AMBIGUOUS` rather than propagating the error — the same pattern is applied to the final answer-generation call in `generate_answer.py`, so a transient outage degrades gracefully instead of taking the app down.

## Tech stack

- **Python 3.11+**
- **Gemini API** (`google-genai`) — entity extraction, CRAG relevance grading, final answer generation
- **ChromaDB** — vector store for semantic search
- **Sentence Transformers** (`all-MiniLM-L6-v2`) — embeddings
- **SQLite** — the structured entity/relationship store
- **PyVis** / **NetworkX** — interactive knowledge graph rendering
- **Streamlit** — both frontend apps
- **pytest** — test suite, fully mocked so it runs offline

## Running it

Everything below assumes you're running commands **from the repo root** unless a step says otherwise.

**1. Install dependencies**
```bash
pip install -r requirements.txt
```

**2. Add your API key**

Copy `.env.example` to `.env` and drop your Gemini key in:
```
GEMINI_API_KEY=your_actual_key
```

**3. Run the pipeline, stage by stage**

```bash
# ingestion (run from repo root)
python ingestion/src/extract_text.py
python ingestion/src/chunk_text.py
python ingestion/src/verify_output.py

# entity extraction (these scripts default to writing into ../output/,
# so run them from inside entity_extraction/src/)
cd entity_extraction/src
python build_db.py --extracted-docs ../../ingestion/output/extracted_documents.json
python extract_entities.py --chunks ../../ingestion/output/chunks.json
python load_entities.py --extracted ../output/extracted_entities.json
cd ../..

# knowledge graph (same story — run from its own src/ folder)
cd knowledge_graph/src
python build_graph.py --db ../../entity_extraction/output/meridian.db
cd ../..

# vector store (back to repo root)
python vector_embedding/src/build_vector_store.py
```

> Heads up: the entity-extraction and knowledge-graph scripts use relative default paths (`../output/...`), so they expect to be run from inside their own `src/` folder — while the ingestion and vector-embedding scripts expect to be run from the repo root. Not the most elegant thing about this codebase, but that's genuinely how it's wired right now, so the commands above reflect that rather than paper over it.

**4. Launch the app**
```bash
streamlit run frontend/admin_app.py       # full internal tool: chat + graph + entity browser
# or
streamlit run frontend/streamlit_app.py   # clean, end-user chat only
```

**5. Run the tests**
```bash
pytest
```
Every test mocks the Gemini client, so this runs fully offline — no API key or network access needed. It covers entity extraction parsing, entity-resolution/dedup logic, all three CRAG decision paths (used-as-is, broadened, broadened-no-vector), and the retry/fallback behavior when the Gemini API is unavailable.

## What each output file is

| File | What it is |
|---|---|
| `ingestion/output/chunks.json` | Every document, split into searchable chunks |
| `entity_extraction/output/meridian.db` | The structured entity + relationship store |
| `knowledge_graph/output/knowledge_graph.html` | The interactive graph — open it directly in a browser |
| `vector_embedding/output/chroma_db/` | The vector index used for semantic search |

## Known rough edges

Being upfront about a few things rather than pretending this is polished:

- The mixed cwd assumptions between pipeline stages (noted above) are the kind of thing that should get cleaned up with `pathlib`-based absolute paths at some point.
- There's no true "router" that decides which of the three retrieval sources to prioritize per query type — right now all three always run, and CRAG only affects the vector-search portion.
- Retrieval scoring is fairly basic; there's no reranking step after the initial retrieval.

## Where this could go next

- A router that weighs vector, entity, and graph evidence differently depending on what kind of question is being asked
- Reranking retrieved chunks before they go to the model, instead of using raw similarity order
- Multi-document summarization — e.g. "summarize every deviation report tied to Batch X"
- Moving from a local Streamlit demo to an actual deployed API

## In short

Meridian takes scattered pharmaceutical manufacturing documents and turns them into something queryable: a structured entity store, a visual relationship graph, semantic search, and a Corrective RAG layer that checks its own retrieval before answering instead of guessing. Built end-to-end for the Economic Times AI Hackathon.