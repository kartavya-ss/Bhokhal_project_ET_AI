"""
tests/test_extract_entities.py
Tests for the Gemini-based entity extraction, using a mocked genai client so
these run offline without GEMINI_API_KEY or any network access.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "entity_extraction" / "src"))

from extract_entities import extract_one  # noqa: E402


def mock_client(response_json: dict):
    client = MagicMock()
    client.models.generate_content.return_value = MagicMock(text=json.dumps(response_json))
    return client


def test_extract_one_returns_parsed_entities_and_relationships():
    chunk = {
        "chunk_id": "chunk_0001",
        "document_id": "BMR_MP-PCM-2601.pdf",
        "page": 3,
        "text": "Maize Starch IP (SUP-1187) 9.20% w/w added per SOP-PRD-010.",
    }
    client = mock_client({
        "entities": [
            {"type": "MATERIAL", "name": "Maize Starch IP", "code": "SUP-1187",
             "attributes": {"quantity": "9.20", "unit": "%"}},
            {"type": "SOP_REFERENCE", "name": "SOP-PRD-010", "code": "SOP-PRD-010", "attributes": {}},
        ],
        "relationships": [
            {"from": "Maize Starch IP", "to": "BMR_MP-PCM-2601.pdf", "type": "USED_IN"},
        ],
    })

    result = extract_one(client, chunk)

    assert result["chunk_id"] == "chunk_0001"
    assert len(result["entities"]) == 2
    assert result["entities"][0]["type"] == "MATERIAL"
    assert result["relationships"][0]["type"] == "USED_IN"
    assert "error" not in result
    client.models.generate_content.assert_called_once()


def test_extract_one_returns_empty_lists_for_chunk_with_no_entities():
    chunk = {"chunk_id": "c2", "document_id": "doc.pdf", "page": 1, "text": "Page intentionally blank."}
    client = mock_client({"entities": [], "relationships": []})

    result = extract_one(client, chunk)

    assert result["entities"] == []
    assert result["relationships"] == []


def test_extract_one_retries_then_gives_up_gracefully_on_bad_json(monkeypatch):
    chunk = {"chunk_id": "c3", "document_id": "doc.pdf", "page": 1, "text": "some text"}
    client = MagicMock()
    client.models.generate_content.return_value = MagicMock(text="not valid json")
    monkeypatch.setattr("extract_entities.time.sleep", lambda *_: None)  # skip real retry delays

    result = extract_one(client, chunk, max_retries=2)

    assert result["entities"] == []
    assert result["relationships"] == []
    assert "error" in result
    assert client.models.generate_content.call_count == 2
