import os
import chromadb
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
from google import genai

load_dotenv()

CHROMA_DB_PATH = "vector_embedding/output/chroma_db"
COLLECTION_NAME = "meridian_chunks"

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
collection = chroma_client.get_collection(name=COLLECTION_NAME)


def retrieve_chunks(question, top_k=5):
    query_embedding = embedding_model.encode([question]).tolist()
    results = collection.query(query_embeddings=query_embedding, n_results=top_k)

    chunks = []
    for i in range(len(results["ids"][0])):
        chunks.append({
            "chunk_id": results["ids"][0][i],
            "text": results["documents"][0][i],
            "document_id": results["metadatas"][0][i]["document_id"],
            "page": results["metadatas"][0][i]["page"],
        })
    return chunks


def build_prompt(question, chunks):
    context_blocks = []
    for c in chunks:
        context_blocks.append(
            f"[Source: {c['document_id']}, page {c['page']}]\n{c['text']}"
        )
    context_text = "\n\n---\n\n".join(context_blocks)

    prompt = f"""You are an industrial knowledge assistant for Meridian Pharmaceuticals.
Answer the question ONLY using the context below. Do not use outside knowledge.
If the context doesn't contain enough information to answer, say so clearly.

For every claim you make, cite the source in this format: (Source: filename, page X)

CONTEXT:
{context_text}

QUESTION: {question}

ANSWER:"""
    return prompt


def generate_answer(question, top_k=5):
    chunks = retrieve_chunks(question, top_k)
    prompt = build_prompt(question, chunks)

    response = client.models.generate_content(
        model="gemini-flash-latest",
        contents=prompt
    )

    print(f"\nQUESTION: {question}\n")
    print(f"ANSWER:\n{response.text}\n")
    print("Retrieved from:")
    for c in chunks:
        print(f"  - {c['document_id']} (page {c['page']})")


if __name__ == "__main__":
    test_questions = [
        "Why was the preventive maintenance overdue on TCM-04?",
        "What corrective actions were taken after the deviation?",
    ]
    for q in test_questions:
        generate_answer(q)
        print("=" * 70)