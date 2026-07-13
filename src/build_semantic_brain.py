"""
Teammate B's job (Task 7): embed every chunk into ChromaDB so the system
can find text by *meaning*, not just exact keyword match.

Uses ChromaDB's built-in default embedding function (all-MiniLM-L6-v2, local,
no API key needed) so this works even without ANTHROPIC_API_KEY -- keeps the
vector brain fully decoupled from LLM availability.
"""
import json
import pickle
import chromadb
from chromadb.utils.embedding_functions import EmbeddingFunction

CHUNKS_PATH = "/home/claude/meridian/data/chunks.json"
CHROMA_DIR = "/home/claude/meridian/db/chroma"
TFIDF_PATH = "/home/claude/meridian/db/tfidf_vectorizer.pkl"


class TfidfEmbeddingFunction(EmbeddingFunction):
    """Fallback embedding function for network-restricted environments where
    Chroma's default all-MiniLM-L6-v2 model download is blocked. Fits a
    TF-IDF vectorizer over the corpus and returns dense vectors.

    NOTE: On your own machine with normal internet access, just delete this
    class and use Chroma's default embedding function (or the 'chromadb
    default' behavior by passing no embedding_function at all) -- real sentence
    embeddings will give noticeably better semantic recall than TF-IDF, which
    only matches on shared vocabulary, not true meaning.
    """
    def __init__(self, corpus=None):
        from sklearn.feature_extraction.text import TfidfVectorizer
        self.vectorizer = TfidfVectorizer(max_features=384)
        if corpus:
            self.vectorizer.fit(corpus)

    def __call__(self, input):
        import numpy as np
        vecs = self.vectorizer.transform(input).toarray()
        return [v.tolist() for v in vecs]


def main():
    chunks = json.load(open(CHUNKS_PATH))
    texts = [c["text"] for c in chunks]

    ef = TfidfEmbeddingFunction(corpus=texts)
    with open(TFIDF_PATH, "wb") as f:
        pickle.dump(ef.vectorizer, f)

    client = chromadb.PersistentClient(path=CHROMA_DIR)
    # Fresh collection each run so re-ingesting doesn't duplicate
    try:
        client.delete_collection("meridian_chunks")
    except Exception:
        pass
    collection = client.create_collection("meridian_chunks", embedding_function=ef)

    collection.add(
        ids=[c["id"] for c in chunks],
        documents=texts,
        metadatas=[{"source_file": c["source_file"], "doc_type": c["doc_type"]} for c in chunks],
    )

    print(f"Embedded {len(chunks)} chunks into ChromaDB collection 'meridian_chunks' at {CHROMA_DIR}")

    # quick sanity check
    test_query = "worn punch tooling wear tablet weight"
    results = collection.query(query_texts=[test_query], n_results=3)
    print(f"\nSanity check -- query: '{test_query}'")
    for doc, meta, dist in zip(results["documents"][0], results["metadatas"][0], results["distances"][0]):
        print(f"  [{meta['source_file']}] (dist={dist:.3f}) {doc[:100]}...")


if __name__ == "__main__":
    main()
