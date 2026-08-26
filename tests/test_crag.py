"""
tests/test_crag.py
Unit tests for the CRAG (Corrective RAG) grading + broadening logic.

No network calls, no real GEMINI_API_KEY required: the Gemini client is
replaced with a mock whose generate_content() returns canned JSON grades,
so these tests run fully offline in CI.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from google.genai.errors import ServerError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vector_embedding" / "src"))

from crag import (  # noqa: E402
    Grade,
    LLMGraderClient,
    corrective_retrieve,
    grade_chunk,
    grade_chunks,
)


def make_chunk(chunk_id, text, document_id="doc.pdf", page=1):
    return {"chunk_id": chunk_id, "text": text, "document_id": document_id, "page": page}


def mock_gemini_client(grade_sequence):
    """
    Builds a fake google.genai client whose .models.generate_content(...)
    returns grades from `grade_sequence` in order, one per call.
    Mirrors the real response shape: an object with a `.text` attribute.
    """
    responses = [
        MagicMock(text=json.dumps({"grade": g, "reason": f"mock reason for {g}"}))
        for g in grade_sequence
    ]
    client = MagicMock()
    client.models.generate_content.side_effect = responses
    return client


# ---------------------------------------------------------------------------
# grade_chunk / grade_chunks
# ---------------------------------------------------------------------------

def test_grade_chunk_parses_correct_grade():
    client = mock_gemini_client(["CORRECT"])
    grader = LLMGraderClient(client=client)
    chunk = make_chunk("c1", "Maize Starch IP was added at 9.20% w/w during granulation.")

    graded = grade_chunk("What material was used in granulation?", chunk, grader)

    assert graded.grade == Grade.CORRECT
    assert graded.chunk is chunk
    client.models.generate_content.assert_called_once()


def test_grade_chunks_grades_each_chunk_independently():
    client = mock_gemini_client(["CORRECT", "INCORRECT", "AMBIGUOUS"])
    grader = LLMGraderClient(client=client)
    chunks = [make_chunk(f"c{i}", f"text {i}") for i in range(3)]

    graded = grade_chunks("some question", chunks, grader)

    assert [g.grade for g in graded] == [Grade.CORRECT, Grade.INCORRECT, Grade.AMBIGUOUS]
    assert client.models.generate_content.call_count == 3


def test_grade_chunk_fails_closed_to_ambiguous_on_malformed_json():
    client = MagicMock()
    client.models.generate_content.return_value = MagicMock(text="not json at all")
    grader = LLMGraderClient(client=client)

    graded = grade_chunk("q", make_chunk("c1", "text"), grader)

    # Malformed grader output should never silently pass through as CORRECT
    # or silently vanish -- it should land as AMBIGUOUS so downstream logic
    # still treats it cautiously.
    assert graded.grade == Grade.AMBIGUOUS


def test_grade_chunk_retries_server_error_then_succeeds(monkeypatch):
    client = MagicMock()
    server_error = ServerError(503, {"error": {"message": "temporarily unavailable"}})
    client.models.generate_content.side_effect = [
        server_error,
        server_error,
        MagicMock(text=json.dumps({"grade": "CORRECT", "reason": "mock reason"})),
    ]
    monkeypatch.setattr("crag.time.sleep", lambda _: None)

    graded = grade_chunk("q", make_chunk("c1", "text"), LLMGraderClient(client=client))

    assert graded.grade == Grade.CORRECT
    assert client.models.generate_content.call_count == 3


def test_grade_chunk_returns_ambiguous_when_server_remains_unavailable(monkeypatch):
    client = MagicMock()
    client.models.generate_content.side_effect = ServerError(
        503, {"error": {"message": "temporarily unavailable"}}
    )
    monkeypatch.setattr("crag.time.sleep", lambda _: None)

    graded = grade_chunk("q", make_chunk("c1", "text"), LLMGraderClient(client=client))

    assert graded.grade == Grade.AMBIGUOUS
    assert "unavailable" in graded.reason
    assert client.models.generate_content.call_count == 3


# ---------------------------------------------------------------------------
# corrective_retrieve: the three CRAG decision paths
# ---------------------------------------------------------------------------

def test_mostly_correct_chunks_are_used_as_is_without_broadening():
    chunks = [make_chunk("c1", "relevant text 1"), make_chunk("c2", "relevant text 2")]
    client = mock_gemini_client(["CORRECT", "CORRECT"])
    grader = LLMGraderClient(client=client)

    vector_fn = MagicMock(return_value=chunks)
    entity_fn = MagicMock(return_value=[])

    result = corrective_retrieve(
        "question", retrieve_vector_fn=vector_fn, retrieve_entity_fn=entity_fn, grader=grader, top_k=2
    )

    assert result.action == "used_as_is"
    assert result.correct_ratio == 1.0
    assert len(result.chunks) == 2
    # Vector store should only be queried once -- no broadening needed.
    vector_fn.assert_called_once_with("question", 2)
    entity_fn.assert_not_called()


def test_all_incorrect_chunks_fall_back_to_entity_store_not_wider_vector_search():
    chunks = [make_chunk("c1", "irrelevant"), make_chunk("c2", "also irrelevant")]
    client = mock_gemini_client(["INCORRECT", "INCORRECT"])
    grader = LLMGraderClient(client=client)

    vector_fn = MagicMock(return_value=chunks)
    entity_fn = MagicMock(return_value=[make_chunk("e1", "SOP-PRD-010 keyword match")])

    result = corrective_retrieve(
        "question", retrieve_vector_fn=vector_fn, retrieve_entity_fn=entity_fn, grader=grader, top_k=2
    )

    assert result.action == "broadened_no_vector"
    assert result.correct_ratio == 0.0
    # Vector store queried once (the initial attempt) -- since the embedding
    # match already failed, we don't waste a second call re-querying it wider.
    assert vector_fn.call_count == 1
    entity_fn.assert_called_once()
    assert any(c["chunk_id"] == "e1" for c in result.chunks)


def test_mixed_grades_keep_good_chunks_and_broaden_both_sources():
    chunks = [make_chunk("c1", "relevant"), make_chunk("c2", "irrelevant"), make_chunk("c3", "irrelevant")]
    client = mock_gemini_client(["CORRECT", "INCORRECT", "INCORRECT"])
    grader = LLMGraderClient(client=client)

    broadened_vector_chunks = [make_chunk("c1", "relevant"), make_chunk("c4", "new relevant chunk")]
    vector_fn = MagicMock(side_effect=[chunks, broadened_vector_chunks])
    entity_fn = MagicMock(return_value=[make_chunk("e1", "entity hit")])

    result = corrective_retrieve(
        "question", retrieve_vector_fn=vector_fn, retrieve_entity_fn=entity_fn, grader=grader,
        top_k=3, broaden_top_k=6,
    )

    assert result.action == "broadened"
    assert 0 < result.correct_ratio < 0.6
    # Broadening should re-query the vector store wider and pull in the
    # entity store, then dedupe (c1 appears in both the initial + broadened
    # vector results but should only show up once).
    assert vector_fn.call_count == 2
    vector_fn.assert_any_call("question", 6)
    entity_fn.assert_called_once_with("question", 6)
    chunk_ids = [c["chunk_id"] for c in result.chunks]
    assert chunk_ids.count("c1") == 1
    assert "c4" in chunk_ids
    assert "e1" in chunk_ids


def test_empty_vector_results_skip_grading_and_go_straight_to_entity_store():
    grader = LLMGraderClient(client=MagicMock())  # should never be called
    vector_fn = MagicMock(return_value=[])
    entity_fn = MagicMock(return_value=[make_chunk("e1", "fallback hit")])

    result = corrective_retrieve(
        "question", retrieve_vector_fn=vector_fn, retrieve_entity_fn=entity_fn, grader=grader, top_k=5
    )

    assert result.action == "broadened_no_vector"
    assert result.correct_ratio == 0.0
    assert result.graded == []
    grader.client.models.generate_content.assert_not_called()
    assert result.chunks == [make_chunk("e1", "fallback hit")]


def test_no_gemini_api_key_and_no_injected_client_raises():
    grader = LLMGraderClient(client=None)
    grader.client = None  # force the "no client" state regardless of env
    with pytest.raises(RuntimeError):
        grader.grade_raw("q", "text")
