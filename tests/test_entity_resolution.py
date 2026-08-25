"""
tests/test_entity_resolution.py
Tests for the material/entity dedup logic in load_entities.get_or_create_entity.

Uses a real in-memory SQLite DB (fast, no mocking needed here -- this logic
has no LLM calls) built from the actual schema.sql, so the tests exercise the
real UNIQUE(entity_type, normalized_value) constraint and code-based lookup.
"""

import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "entity_extraction" / "src"))

from load_entities import get_or_create_entity, normalize  # noqa: E402

SCHEMA_PATH = REPO_ROOT / "entity_extraction" / "src" / "schema.sql"


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.executescript(SCHEMA_PATH.read_text())
    yield connection
    connection.close()


def test_same_code_different_surface_names_resolve_to_one_entity(conn):
    # Same material, two different surface forms across a document --
    # e.g. the BMR calls it "Microcrystalline Cellulose" on one page and
    # cites its supplier code "SUP-1187" on another.
    id_1 = get_or_create_entity(conn, "MATERIAL", "Microcrystalline Cellulose", "SUP-1187")
    id_2 = get_or_create_entity(conn, "MATERIAL", "MCC NF", "SUP-1187")

    assert id_1 == id_2
    count = conn.execute("SELECT COUNT(*) FROM entities WHERE entity_type='MATERIAL'").fetchone()[0]
    assert count == 1


def test_same_normalized_name_without_code_dedupes_on_name(conn):
    id_1 = get_or_create_entity(conn, "OPERATOR", "V. Singh", None)
    id_2 = get_or_create_entity(conn, "OPERATOR", "v.  singh", None)  # whitespace/case variant

    assert id_1 == id_2


def test_code_backfills_onto_existing_codeless_entity(conn):
    # First mention has no code, second mention (same normalized name) does --
    # the entity record should pick up the code rather than creating a dupe.
    id_1 = get_or_create_entity(conn, "MATERIAL", "Maize Starch IP", None)
    id_2 = get_or_create_entity(conn, "MATERIAL", "Maize Starch IP", "SUP-1187")

    assert id_1 == id_2
    row = conn.execute(
        "SELECT entity_code FROM entities WHERE entity_id = ?", (id_1,)
    ).fetchone()
    assert row[0] == "SUP-1187"


def test_different_codes_create_distinct_entities(conn):
    id_1 = get_or_create_entity(conn, "MATERIAL", "Lactose Monohydrate", "SUP-2201")
    id_2 = get_or_create_entity(conn, "MATERIAL", "Lactose Monohydrate USP", "SUP-2202")

    assert id_1 != id_2


def test_normalize_collapses_whitespace_and_case():
    assert normalize("  V.   Singh  ") == "V. SINGH"
    assert normalize("SOP-PRD-010") == "SOP-PRD-010"
