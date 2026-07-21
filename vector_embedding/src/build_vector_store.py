import json
import chromadb
from sentence_transformers import SentenceTransformer

CHUNKS_FILE = "ingestion/output/chunks.json"
CHROMA_DB_PATH = "vector_embedding/output/chroma_db"
COLLECTION_NAME = "meridian_chunks"

def load_chunks():
    with open(CHUNKS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def build_vector_store():
    print("Loading embedding model (first run downloads it, ~90MB)...")
    model = SentenceTransformer("all-MiniLM-L6-v2")

    chunks = load_chunks()
    print(f"Loaded {len(chunks)} chunks from ingestion pipeline.")

    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    collection = client.get_or_create_collection(name=COLLECTION_NAME)

    texts = [chunk["text"] for chunk in chunks]
    ids = [chunk["chunk_id"] for chunk in chunks]
    metadatas = [
        {
            "document_id": chunk["document_id"],
            "source_type": chunk["source_type"],
            "page": chunk["page"]
        }
        for chunk in chunks
    ]

    print("Generating embeddings for all chunks...")
    embeddings = model.encode(texts, show_progress_bar=True).tolist()

    print("Storing embeddings in ChromaDB...")
    collection.upsert(
        ids=ids,
        embeddings=embeddings,
        documents=texts,
        metadatas=metadatas
    )

    print(f"\nDone. {collection.count()} chunks stored in ChromaDB at '{CHROMA_DB_PATH}'.")

if __name__ == "__main__":
    build_vector_store()