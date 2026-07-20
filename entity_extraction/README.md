Entity Extraction + Structured Store (Day 2-5)

Pipeline


src/build_db.py — creates meridian.db from schema.sql, populates documents
from ingestion/output/extracted_documents.json (auto-classifies BMR / SOP / sensor_log).
src/extract_entities.py — runs each chunk from ingestion/output/chunks.json through
Gemini (gemini-flash-latest) to pull MATERIAL, SOP_REFERENCE, OPERATOR, EQUIPMENT,
PROCESS_STEP, PARAMETER, BATCH_ID, TIMESTAMP entities + relationships. Requires
GEMINI_API_KEY. Uses response_mime_type="application/json" for guaranteed valid JSON.
src/load_entities.py — loads extracted entities/relationships into SQLite (dedup on
entity_type + normalized name).
src/query_examples.py — sanity-check queries (material lookups, SOP references,
operator search, relationship edges for the pyvis graph).


Setup

bashcd src
pip install google-genai python-dotenv
cp ../.env.example ../.env
# then edit ../.env and paste your real GEMINI_API_KEY

Run order

bashcd src

python build_db.py --extracted-docs ../../ingestion/output/extracted_documents.json --db ../output/meridian.db

python extract_entities.py --chunks ../../ingestion/output/chunks.json \
    --out ../output/extracted_entities.json --limit 10   # drop --limit for full run

python load_entities.py --extracted ../output/extracted_entities.json --db ../output/meridian.db

python query_examples.py --db ../output/meridian.db

Schema

documents -> entity_mentions -> entities, plus relationships between entities.
See src/schema.sql for full DDL.