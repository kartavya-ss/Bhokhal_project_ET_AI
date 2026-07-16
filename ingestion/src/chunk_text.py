import json
import os

INPUT_FILE = "ingestion/output/extracted_documents.json"
OUTPUT_FILE = "ingestion/output/chunks.json"

CHUNK_SIZE = 800       # target max characters per chunk
CHUNK_OVERLAP = 150    # characters repeated between consecutive chunks

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
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        documents = json.load(f)

    all_chunks = []
    for doc in documents:
        doc_chunks = chunk_document(doc)
        all_chunks.extend(doc_chunks)
        print(f"{doc['document_id']}: {len(doc_chunks)} chunk(s)")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, indent=2, ensure_ascii=False)

    print(f"\nDone. {len(all_chunks)} total chunks saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    process_all_chunks()