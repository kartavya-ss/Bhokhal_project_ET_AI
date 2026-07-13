# Meridian Industrial Knowledge Intelligence Platform

Solo-built hybrid RAG system: SQLite (hard facts) + ChromaDB (semantic search) + Claude (cited synthesis).

## Setup

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your_key_here   # required for relationship extraction + answer synthesis
sudo apt install tesseract-ocr           # required for P&ID image OCR (Linux)
```

## Run the pipeline (in order)

```bash
cd src
python3 generate_sample_data.py     # OR: drop your real 18 files into ../data/ instead
python3 ingest.py                   # extract + chunk all files -> data/chunks.json
python3 build_relational_brain.py   # entities + relationships -> db/meridian.sqlite
python3 build_semantic_brain.py     # embeddings -> db/chroma/
python3 run_benchmarks.py           # sanity-check your benchmark questions
```

## Run the UI

```bash
cd ui
streamlit run app.py
```

## Swapping in your real 18 files

1. Delete everything in `data/` except leave the folder.
2. Drop your real PDFs, xlsx, txt, and P&ID image(s) into `data/`.
3. Re-run `ingest.py` -> `build_relational_brain.py` -> `build_semantic_brain.py`.
4. If your entity naming conventions differ from `MP-PCM-####` / `TCM-##` / `ENG-###`,
   update the regex patterns in `build_relational_brain.py` (PATTERNS dict) and
   `query_engine.py` (ENTITY_PATTERNS dict) to match, and update KNOWN_PEOPLE with real names.

## Notes on this sandbox build

- Relationship extraction auto-uses Claude when `ANTHROPIC_API_KEY` is set; falls back to
  a rule-based keyword matcher otherwise (see `extract_relationships_rulebased` in
  `build_relational_brain.py`). The rule-based version is actually decent for a demo but
  the LLM version handles phrasing you didn't anticipate -- use it with your key.
- Vector embeddings use a TF-IDF fallback (`TfidfEmbeddingFunction` in `build_semantic_brain.py`)
  because this sandbox's network couldn't download Chroma's default sentence-transformer model.
  On your own machine, just remove the custom embedding_function args and let Chroma use its
  default -- you'll get real semantic embeddings instead of keyword-overlap TF-IDF, which
  will meaningfully improve recall on paraphrased questions.
