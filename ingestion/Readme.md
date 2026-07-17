# Intelligent Ingestion Pipeline

A robust document ingestion engine designed to extract plain text and structured tables from digital assets, process the content into context-aware chunks, and prepare it for retrieval systems.

## 📁 Project Structure

```text
ingestion/
├── data/               # Raw input files (PDFs, text documents)
├── output/             # Processed pipeline artifacts
│   ├── extracted_documents.json
│   └── chunks.json
├── src/                # Pipeline source code
│   ├── extract_text.py # PDF/Text extraction module
│   └── chunk_text.py   # Sliding-window chunking logic
├── requirements.txt    # Python package dependencies
└── README.md           # Project documentation

## `chunks.json` — Schema (read this carefully)

Each entry is a JSON object with these exact fields:

| Field | Type | Meaning |
|---|---|---|
| `chunk_id` | string | Unique ID for this chunk, e.g. `"DEV-2026-015.pdf_chunk5"` |
| `document_id` | string | Original filename, use this for citations |
| `source_type` | string | File extension (`pdf`, `txt`, `xlsx`, `png`) |
| `page` | integer | Page number within the source document |
| `text` | string | The actual chunk content, ready to embed or extract entities from |

Example:
```json
{
  "chunk_id": "DEV-2026-015.pdf_chunk5",
  "document_id": "DEV-2026-015.pdf",
  "source_type": "pdf",
  "page": 1,
  "text": "[TABLE 2]\n# | CAPA Action | Target Date\n1 | Perform overdue..."
}
```

## Important notes

- **`ai4i2020.csv` is intentionally excluded** from `chunks.json` — it's structured sensor/ML data (10,000 rows), not narrative text. It's better suited for direct loading into the SQL structured store. Raw extracted rows are still available in `extracted_documents.json` if Teammate A wants to load it directly.
- **Tables are tagged with `[TABLE N]` markers** inside the `text` field — rows are pipe-separated (`|`). Table extraction can occasionally misalign cells on complex layouts (known `pdfplumber` limitation) — treat table text as best-effort structured data, not guaranteed perfectly clean.
- **`PID_Purified_Water_System.png` is OCR-extracted** — expect sparse, lower-accuracy text compared to PDF-based chunks, since it's a diagram, not prose.
- **Total: 322 chunks across 17 documents** (as of Day 4).

## Contact
Questions about this output → Teammate C (this branch: `feature/ingestion`)