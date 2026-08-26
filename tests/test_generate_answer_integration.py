import importlib
import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock


def load_generate_answer(monkeypatch):
    fake_chromadb = types.ModuleType("chromadb")
    fake_chromadb.PersistentClient = MagicMock()
    fake_sentence_transformers = types.ModuleType("sentence_transformers")
    fake_sentence_transformers.SentenceTransformer = MagicMock()

    fake_google = types.ModuleType("google")
    fake_genai = types.ModuleType("google.genai")
    fake_genai.Client = MagicMock()
    fake_types = types.ModuleType("google.genai.types")
    fake_types.GenerateContentConfig = MagicMock
    fake_genai.types = fake_types
    fake_google.genai = fake_genai

    monkeypatch.setitem(sys.modules, "chromadb", fake_chromadb)
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_sentence_transformers)
    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", fake_types)

    vector_src = Path(__file__).resolve().parents[1] / "vector_embedding" / "src"
    sys.path.insert(0, str(vector_src))
    sys.modules.pop("generate_answer", None)
    return importlib.import_module("generate_answer")


def make_chunk(chunk_id):
    return {
        "chunk_id": chunk_id,
        "text": f"text for {chunk_id}",
        "document_id": "doc.pdf",
        "page": 1,
    }


def configure_module(module, monkeypatch, grades):
    chunks = [make_chunk("c1"), make_chunk("c2")]
    responses = [MagicMock(text=json.dumps({"grade": grade})) for grade in grades]
    responses.append(MagicMock(text="answer"))
    module.client = MagicMock()
    module.client.models.generate_content.side_effect = responses
    monkeypatch.setattr(module, "retrieve_vector_chunks", lambda question, top_k: chunks)
    monkeypatch.setattr(module, "retrieve_entity_context", lambda question, top_k: [])
    monkeypatch.setattr(module, "retrieve_graph_context", lambda question, top_k: [])


def test_answer_with_sources_wires_crag_decisions(monkeypatch):
    module = load_generate_answer(monkeypatch)

    configure_module(module, monkeypatch, ["CORRECT", "CORRECT"])
    correct_result = module.answer_with_sources("question")
    assert correct_result["crag_action"] == "used_as_is"

    configure_module(module, monkeypatch, ["INCORRECT", "INCORRECT"])
    incorrect_result = module.answer_with_sources("question")
    assert incorrect_result["crag_action"] == "broadened_no_vector"

    configure_module(module, monkeypatch, [])
    disabled_result = module.answer_with_sources("question", use_crag=False)
    assert disabled_result["crag_action"] is None