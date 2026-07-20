import json
import os

INPUT_FILE = "ingestion/output/extracted_documents.json"
OUTPUT_FILE = "ingestion/output/chunks.json"

CHUNK_SIZE = 800       # target max characters per chunk
CHUNK_OVERLAP = 150    # characters repeated between consecutive chunks

EXCLUDED_DOCUMENTS = ["ai4i2020.csv"]  # Structured ML data, belongs in SQL store, not chunked text
def split_into_paragraphs(text):
    """Split text on blank lines/double newlines — respects natural document structure."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    return paragraphs

def chunk_paragraph(paragraph, chunk_size, overlap):
    """If a single paragraph is too long, break it further with overlap."""
    if len(paragraph) <= chunk_size:
        return [paragraph]

    chunks = []
    start = 0
    while start < len(paragraph):
        end = start + chunk_size
        chunks.append(paragraph[start:end])
        start = end - overlap  # step back by 'overlap' so chunks share context
    return chunks

def chunk_document(document):
    """Turn one document's pages into a list of chunk records with metadata."""
    all_chunks = []
    chunk_counter = 1

    for page in document["pages"]:
        paragraphs = split_into_paragraphs(page["text"])

        for para in paragraphs:
            sub_chunks = chunk_paragraph(para, CHUNK_SIZE, CHUNK_OVERLAP)

            for sub_chunk in sub_chunks:
                all_chunks.append({
                    "chunk_id": f"{document['document_id']}_chunk{chunk_counter}",
                    "document_id": document["document_id"],
                    "source_type": document["source_type"],
                    "page": page["page"],
                    "text": sub_chunk
                })
                chunk_counter += 1

    return all_chunks

def process_all_chunks():
    """Main orchestrator: Reads extracted text, chunks it, and saves the output."""
    if not os.path.exists(INPUT_FILE):
        print(f"Error: Could not find input file at {INPUT_FILE}. Make sure you ran extract_text.py first!")
        return

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        documents = json.load(f)
        
    all_chunks = []
    for doc in documents:
        # Check if the document should be excluded from text chunking
        if doc["document_id"] in EXCLUDED_DOCUMENTS:
            print(f"Skipping {doc['document_id']} — structured data, not suited for chunking")
            continue
            
        doc_chunks = chunk_document(doc)
        all_chunks.extend(doc_chunks)
        print(f"{doc['document_id']}: {len(doc_chunks)} chunk(s)")
        
    # Ensure the output directory exists
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, indent=2, ensure_ascii=False)
        
    print(f"\nDone. {len(all_chunks)} total chunks saved to {OUTPUT_FILE}")
if __name__ == "__main__":
    process_all_chunks()