"""
crag.py
Corrective RAG (CRAG) layer for Meridian.

Plain RAG (see generate_answer.py) retrieves the top-k nearest vector chunks
and hands them straight to the LLM -- it has no idea whether what it fetched
is actually useful. If the embedding model misses (jargon, typos, a question
that doesn't phrase like the source text), the model still gets fed *something*
and answers confidently anyway.

CRAG adds a grading step in between retrieval and generation:

  1. Retrieve top-k chunks from the vector store, same as before.
  2. Grade each chunk's relevance to the question: CORRECT / AMBIGUOUS / INCORRECT.
  3. Decide what to do based on the aggregate grade instead of blindly trusting
     the top-k:
       - mostly CORRECT   -> use the retrieved chunks as-is (fast path).
       - mixed            -> keep the good chunks, but BROADEN: pull a wider
                              vector top_k and cross-check the entity/keyword
                              store to fill the gaps.
       - all INCORRECT    -> the vector query itself was a bad match. Drop it
                              and fall back to the entity + knowledge-graph
                              stores, which use keyword/code matching rather
                              than embeddings and often recover exact-code
                              lookups ("SUP-1187", "SOP-PRD-010") that
                              semantic search misses.

The goal: never silently answer from irrelevant context, and never give up --
broaden the search instead.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

from dotenv import load_dotenv

load_dotenv()

GRADER_MODEL = "gemini-flash-latest"

# A chunk counts as "enough to answer from" once at least this fraction of
# graded chunks come back CORRECT. Below that, we broaden instead of guessing.
CORRECT_RATIO_THRESHOLD = 0.6


class Grade(str, Enum):
    CORRECT = "CORRECT"
    AMBIGUOUS = "AMBIGUOUS"
    INCORRECT = "INCORRECT"


GRADER_SYSTEM_PROMPT = """You are a strict relevance grader for a retrieval-augmented \
question-answering system over pharmaceutical manufacturing documents (batch records, \
SOPs, material specs, FDA letters, sensor logs).

Given a QUESTION and a retrieved CHUNK of text, decide whether the chunk actually \
helps answer the question.

Return ONLY valid JSON, no markdown fences, no commentary:
{"grade": "CORRECT" | "AMBIGUOUS" | "INCORRECT", "reason": "one short sentence"}

Rules:
- CORRECT: the chunk directly contains facts needed to answer the question.
- AMBIGUOUS: the chunk is topically related (same document/material/process) but
  doesn't clearly contain the answer itself.
- INCORRECT: the chunk is unrelated to the question.
- Be strict. A chunk that merely shares a keyword with the question but discusses
  something else is INCORRECT, not AMBIGUOUS.
"""


class LLMGraderClient:
    """
    Wraps whatever LLM client does the grading call.

    Kept as a thin protocol-like wrapper (rather than importing google.genai
    directly into corrective_retrieve) specifically so tests can inject a
    fake client and never touch the network / real API key.
    """

    def __init__(self, client=None, model: str = GRADER_MODEL):
        self.model = model
        if client is not None:
            self.client = client
        else:
            from google import genai  # imported lazily so tests don't need it installed as a hard dep

            api_key = os.environ.get("GEMINI_API_KEY")
            self.client = genai.Client(api_key=api_key) if api_key else None

    def grade_raw(self, question: str, chunk_text: str) -> str:
        if self.client is None:
            raise RuntimeError(
                "No GEMINI_API_KEY set and no client injected into LLMGraderClient."
            )
        from google.genai import types

        resp = self.client.models.generate_content(
            model=self.model,
            contents=f'QUESTION: {question}\n\nCHUNK:\n"""\n{chunk_text}\n"""',
            config=types.GenerateContentConfig(
                system_instruction=GRADER_SYSTEM_PROMPT,
                response_mime_type="application/json",
                temperature=0,
            ),
        )
        return resp.text.strip()


@dataclass
class GradedChunk:
    chunk: dict
    grade: Grade
    reason: str = ""


def grade_chunk(question: str, chunk: dict, grader: LLMGraderClient) -> GradedChunk:
    raw = grader.grade_raw(question, chunk.get("text", ""))
    try:
        parsed = json.loads(raw)
        grade = Grade(parsed["grade"])
        reason = parsed.get("reason", "")
    except (json.JSONDecodeError, KeyError, ValueError):
        # Fail closed: if the grader response is malformed, treat the chunk
        # as AMBIGUOUS rather than silently trusting or silently dropping it.
        grade, reason = Grade.AMBIGUOUS, "grader returned unparsable output"
    return GradedChunk(chunk=chunk, grade=grade, reason=reason)


def grade_chunks(question: str, chunks: list[dict], grader: LLMGraderClient) -> list[GradedChunk]:
    return [grade_chunk(question, c, grader) for c in chunks]


def _dedupe(chunks: list[dict]) -> list[dict]:
    """Vector + entity retrieval can surface the same chunk twice once we
    start broadening across both stores; keep first occurrence only."""
    seen = set()
    out = []
    for c in chunks:
        key = c.get("chunk_id") or (c.get("document_id"), c.get("page"), c.get("text", "")[:50])
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


@dataclass
class CragResult:
    chunks: list[dict]
    action: str  # "used_as_is" | "broadened" | "broadened_no_vector"
    correct_ratio: float
    graded: list[GradedChunk] = field(default_factory=list)


def corrective_retrieve(
    question: str,
    retrieve_vector_fn: Callable[[str, int], list[dict]],
    retrieve_entity_fn: Callable[[str, int], list[dict]],
    grader: LLMGraderClient,
    top_k: int = 5,
    broaden_top_k: int = 12,
) -> CragResult:
    """
    Corrective RAG retrieval.

    retrieve_vector_fn(question, top_k)  -> list of chunk dicts from the vector store
    retrieve_entity_fn(question, top_k)  -> list of chunk-like dicts from the entity/
                                             keyword store (used only when broadening)
    """
    initial_chunks = retrieve_vector_fn(question, top_k)

    if not initial_chunks:
        # Nothing came back at all -- don't even bother grading, go straight
        # to the entity/keyword store.
        broadened_entities = retrieve_entity_fn(question, broaden_top_k)
        return CragResult(
            chunks=_dedupe(broadened_entities),
            action="broadened_no_vector",
            correct_ratio=0.0,
            graded=[],
        )

    graded = grade_chunks(question, initial_chunks, grader)
    correct = [g.chunk for g in graded if g.grade == Grade.CORRECT]
    ambiguous = [g.chunk for g in graded if g.grade == Grade.AMBIGUOUS]
    correct_ratio = len(correct) / len(graded)

    if correct_ratio >= CORRECT_RATIO_THRESHOLD:
        return CragResult(
            chunks=_dedupe(correct + ambiguous),
            action="used_as_is",
            correct_ratio=correct_ratio,
            graded=graded,
        )

    if correct_ratio == 0.0:
        # The vector query missed entirely -- re-querying the same vector
        # store wider is unlikely to help much (it's the same embedding
        # mismatch). Fall back to keyword/code matching instead.
        broadened_entities = retrieve_entity_fn(question, broaden_top_k)
        return CragResult(
            chunks=_dedupe(ambiguous + broadened_entities),
            action="broadened_no_vector",
            correct_ratio=correct_ratio,
            graded=graded,
        )

    # Partial signal: keep what's good, broaden both sources to fill gaps.
    broadened_vector = retrieve_vector_fn(question, broaden_top_k)
    broadened_entities = retrieve_entity_fn(question, broaden_top_k)
    return CragResult(
        chunks=_dedupe(correct + ambiguous + broadened_vector + broadened_entities),
        action="broadened",
        correct_ratio=correct_ratio,
        graded=graded,
    )
