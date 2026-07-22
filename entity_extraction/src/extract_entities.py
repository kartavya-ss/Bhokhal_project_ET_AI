"""
extract_entities.py
Runs each chunk from ingestion/output/chunks.json through Gemini to pull out
structured entities + relationships for the pharma-manufacturing knowledge graph.

Domain entity types:
    MATERIAL        - raw materials/excipients (e.g. "Maize Starch IP", code "SUP-1187")
    SOP_REFERENCE    - SOP numbers referenced (e.g. "SOP-PRD-010")
    OPERATOR         - people who performed/checked a step (e.g. "V. Singh")
    EQUIPMENT        - machines/instruments named
    PROCESS_STEP     - named manufacturing steps (e.g. "Binder addition & wet granulation")
    PARAMETER        - numeric process parameters with units (temp, speed, humidity, time)
    BATCH_ID         - batch/document identifiers
    TIMESTAMP        - dates/times recorded in the doc

Output: entity_extraction/output/extracted_entities.json
    [
      {
        "chunk_id": "...",
        "document_id": "...",
        "page": 1,
        "entities": [
          {"type": "MATERIAL", "name": "Maize Starch IP", "code": "SUP-1187",
           "attributes": {"quantity": "9.20", "unit": "%"}}
        ],
        "relationships": [
          {"from": "Maize Starch IP", "to": "BMR_MP-PCM-2601.pdf", "type": "USED_IN"}
        ]
      },
      ...
    ]

Usage:
    export GEMINI_API_KEY=...
    python extract_entities.py --chunks ../../ingestion/output/chunks.json \
                                --out ../output/extracted_entities.json \
                                [--limit 10] [--workers 4]
"""

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from google import genai
from google.genai import types
from google.genai.errors import APIError
from dotenv import load_dotenv

load_dotenv()  # reads .env in the current working directory (or nearest parent)

# "gemini-flash-latest" auto-tracks Google's current recommended Flash model
# (currently Gemini 3.5 Flash as of mid-2026). Pin to a dated model string
# instead if you need output stability across a hackathon demo.
MODEL = "gemini-flash-latest"

SYSTEM_PROMPT = """You extract structured entities and relationships from pharmaceutical \
manufacturing documents (Batch Manufacturing Records, SOPs, material specs, sensor logs).

Return ONLY valid JSON, no markdown fences, no commentary. Schema:
{
  "entities": [
    {"type": "MATERIAL|SOP_REFERENCE|OPERATOR|EQUIPMENT|PROCESS_STEP|PARAMETER|BATCH_ID|TIMESTAMP",
     "name": "surface form as it appears in text",
     "code": "material/SOP code if present, else null",
     "attributes": {"quantity": "...", "unit": "..."}  // omit or {} if not applicable
    }
  ],
  "relationships": [
    {"from": "entity name", "to": "entity name", "type": "USED_IN|OPERATED_BY|GOVERNED_BY|RECORDED_AT|PART_OF_STEP"}
  ]
}

Rules:
- Only extract entities explicitly present in the text. Do not infer or hallucinate.
- If a chunk has no extractable entities, return {"entities": [], "relationships": []}.
- Keep "name" as close to the source text as possible (for citation/grounding).
- Numeric parameters (temperatures, speeds, times, humidity, percentages) are type PARAMETER.
- SOP_REFERENCE is ONLY for standard operating procedure codes, which follow a pattern like
  "SOP-<DEPT>-<NUMBER>" (e.g. "SOP-PRD-010", "SOP-QA-021"). Do NOT tag the document's own
  batch/BMR number as SOP_REFERENCE (e.g. "BMR-PCM500-MP-PCM-2601" is a BATCH_ID, not an SOP).
  Do NOT tag pharmacopoeia or monograph citations (e.g. "IP 2022, Monograph: Paracetamol
  Tablets") as SOP_REFERENCE — skip these entirely, they are not useful entities for this graph.
"""


def build_user_prompt(chunk: dict) -> str:
    return f"""Document: {chunk.get('document_id')}
Page: {chunk.get('page')}
Text:
\"\"\"
{chunk.get('text', '')}
\"\"\"

Extract entities and relationships per the schema."""


def extract_one(client: genai.Client, chunk: dict, max_retries: int = 3) -> dict:
    last_err = None
    for attempt in range(max_retries):
        try:
            resp = client.models.generate_content(
                model=MODEL,
                contents=build_user_prompt(chunk),
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    temperature=0,
                ),
            )
            raw = resp.text.strip()
            parsed = json.loads(raw)
            return {
                "chunk_id": chunk.get("chunk_id"),
                "document_id": chunk.get("document_id"),
                "page": chunk.get("page"),
                "entities": parsed.get("entities", []),
                "relationships": parsed.get("relationships", []),
            }
        except (json.JSONDecodeError, APIError, AttributeError) as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    print(f"  [WARN] failed on {chunk.get('chunk_id')} after {max_retries} attempts: {last_err}")
    return {
        "chunk_id": chunk.get("chunk_id"),
        "document_id": chunk.get("document_id"),
        "page": chunk.get("page"),
        "entities": [],
        "relationships": [],
        "error": str(last_err),
    }


def main(chunks_path: str, out_path: str, limit: int | None, workers: int):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("Set GEMINI_API_KEY in your environment before running this script.")

    client = genai.Client(api_key=api_key)

    with open(chunks_path, "r", encoding="utf-8") as f:
        chunks = json.load(f)
    if limit:
        chunks = chunks[:limit]

    print(f"Extracting entities from {len(chunks)} chunks with {workers} workers...")
    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(extract_one, client, c): c for c in chunks}
        for i, fut in enumerate(as_completed(futures), 1):
            results.append(fut.result())
            if i % 10 == 0 or i == len(chunks):
                print(f"  {i}/{len(chunks)} done")

    # keep output order stable
    order = {c.get("chunk_id"): idx for idx, c in enumerate(chunks)}
    results.sort(key=lambda r: order.get(r["chunk_id"], 0))

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    total_entities = sum(len(r["entities"]) for r in results)
    total_rels = sum(len(r["relationships"]) for r in results)
    errors = sum(1 for r in results if "error" in r)
    print(f"\nDone. {total_entities} entities, {total_rels} relationships extracted.")
    if errors:
        print(f"  {errors} chunks failed and were left empty — check output for 'error' field.")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--chunks", required=True)
    parser.add_argument("--out", default="../output/extracted_entities.json")
    parser.add_argument("--limit", type=int, default=None, help="process only first N chunks (for testing)")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    main(args.chunks, args.out, args.limit, args.workers)