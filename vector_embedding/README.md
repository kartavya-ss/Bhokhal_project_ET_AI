# Vector Embedding Pipeline

This folder turns the chunked ingestion output into a persistent semantic search index using ChromaDB and Sentence Transformers.

## Purpose

The vector embedding layer provides retrieval for question answering over Meridian knowledge documents.

It does three main jobs:

1. Build a vector database from the ingestion chunks
2. Search the stored embeddings for the most relevant chunks
3. Feed those retrieved chunks into Gemini for grounded answer generation

## Folder Structure

```text
vector_embedding/
├── requirements.txt          # Python dependencies
├── output/
│   └── chroma_db/            # Persistent ChromaDB storage
└── src/
    ├── build_vector_store.py # Create or refresh the vector store
    ├── query_store.py        # Run sample semantic searches
    └── generate_answer.py    # Retrieve context + answer questions with Gemini
```

## Data Flow

The workflow depends on the ingestion pipeline output:

- Input: `ingestion/output/chunks.json`
- Indexed collection: `meridian_chunks`
- Local storage location: `vector_embedding/output/chroma_db`

## Setup

From the repository root, install dependencies:

```bash
pip install -r vector_embedding/requirements.txt
```

The embedding model is downloaded automatically on first use.

## Environment Variables

`generate_answer.py` expects a Gemini API key in your environment:

```bash
GEMINI_API_KEY=your_key_here
```

You can keep this in a `.env` file at the repository root or in the relevant project directory.

## Usage

### 1. Build the vector store

```bash
python vector_embedding/src/build_vector_store.py
```

This loads `chunks.json`, creates embeddings with `all-MiniLM-L6-v2`, and stores them in ChromaDB.

### 2. Run semantic search examples

```bash
python vector_embedding/src/query_store.py
```

This prints a few sample retrieval results and their similarity distances.

### 3. Generate grounded answers

```bash
python vector_embedding/src/generate_answer.py
```

The script:

- encodes the user question
- retrieves the top matching chunks from ChromaDB
- constructs a grounded prompt for Gemini
- prints the final answer with source references

## Notes

- The embedding store is persistent and stored locally under `vector_embedding/output/chroma_db`.
- `build_vector_store.py` uses `upsert`, so rerunning it refreshes the index for the same collection.
- Retrieval is semantic and source-aware, making it suitable for grounded Q&A over the Meridian technical knowledge base.

## Expected Output

After indexing, the vector database should contain all ingestion chunks available in `chunks.json`, with metadata including:

- `document_id`
- `source_type`
- `page`

This allows the retrieval step to return relevant document fragments with traceable source information.
