import chromadb
from sentence_transformers import SentenceTransformer

CHROMA_DB_PATH = "vector_embedding/output/chroma_db"
COLLECTION_NAME = "meridian_chunks"

def search(query_text, top_k=5):
    model = SentenceTransformer("all-MiniLM-L6-v2")
    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    collection = client.get_collection(name=COLLECTION_NAME)

    query_embedding = model.encode([query_text]).tolist()

    results = collection.query(
        query_embeddings=query_embedding,
        n_results=top_k
    )

    print(f"\nQuery: \"{query_text}\"\n")
    for i in range(len(results["ids"][0])):
        chunk_id = results["ids"][0][i]
        distance = results["distances"][0][i]
        metadata = results["metadatas"][0][i]
        text_preview = results["documents"][0][i][:150]

        print(f"[{i+1}] {chunk_id} (distance={distance:.4f})")
        print(f"    Source: {metadata['document_id']}, page {metadata['page']}")
        print(f"    Preview: {text_preview}...\n")

if __name__ == "__main__":
    test_queries = [
        "overdue preventive maintenance inspection",
        "material used in tablet compression batch",
        "regulatory response to FDA warning letter"
    ]
    for q in test_queries:
        search(q)
        print("-" * 60)