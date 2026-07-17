import json

CHUNKS_FILE = "ingestion/output/chunks.json"
REQUIRED_FIELDS = {"chunk_id", "document_id", "source_type", "page", "text"}

def verify_chunks():
    with open(CHUNKS_FILE, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    print(f"Total chunks: {len(chunks)}")

    errors = 0
    seen_ids = set()

    for chunk in chunks:
        missing = REQUIRED_FIELDS - chunk.keys()
        if missing:
            print(f"MISSING FIELDS in {chunk.get('chunk_id', 'UNKNOWN')}: {missing}")
            errors += 1

        if not chunk.get("text", "").strip():
            print(f"EMPTY TEXT in {chunk.get('chunk_id', 'UNKNOWN')}")
            errors += 1

        if chunk["chunk_id"] in seen_ids:
            print(f"DUPLICATE chunk_id: {chunk['chunk_id']}")
            errors += 1
        seen_ids.add(chunk["chunk_id"])

    if errors == 0:
        print("All chunks passed validation. Ready for handoff.")
    else:
        print(f"{errors} issue(s) found — fix before handoff.")

if __name__ == "__main__":
    verify_chunks()