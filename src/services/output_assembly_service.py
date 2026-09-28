"""AgentCore Platform v1.0"""

# Service layer: final JSON payload assembly + schema validation for the
# quiz output. Pure domain logic — no framework imports — called by
# src/nodes/post_process_node.py.

from __future__ import annotations

from typing import Any

_REQUIRED_QUESTION_FIELDS = {"question_id", "chunk_id", "format", "text", "source_chunk_ref"}


def assemble_output(
    raw_questions: list[dict[str, Any]],
    raw_answers: list[dict[str, Any]],
    difficulty_tags: list[dict[str, Any]],
    safety_compliance_tags: list[dict[str, Any]],
) -> dict[str, Any]:
    """Assemble the final structured JSON quiz payload (proposal §4 Step 3).

    Sets `no_safety_sections_detected: true` when no safety-topic question
    was tagged, per proposal §4 notes.
    """
    payload: dict[str, Any] = {
        "questions": raw_questions,
        "answer_key": raw_answers,
        "difficulty": difficulty_tags,
        "safety_compliance_tags": safety_compliance_tags,
    }
    if not safety_compliance_tags:
        payload["no_safety_sections_detected"] = True
    return payload


def validate_output_schema(payload: dict[str, Any]) -> list[str]:
    """Validate required fields are present. Returns a list of error
    messages; empty list means the payload is valid."""
    errors: list[str] = []

    for key in ("questions", "answer_key", "difficulty", "safety_compliance_tags"):
        if key not in payload:
            errors.append(f"OutputNode: missing required field '{key}'")

    for question in payload.get("questions", []):
        missing = _REQUIRED_QUESTION_FIELDS - question.keys()
        if missing:
            errors.append(f"OutputNode: question_id={question.get('question_id')} " f"missing fields {sorted(missing)}")

    return errors
