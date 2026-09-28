"""AgentCore Platform v1.0"""

# Service layer: question-count allocation, LLM prompt construction, and
# answer-key grounding validation for the quiz generation step. Pure domain
# logic — no framework imports — called by src/nodes/main_node.py.

from __future__ import annotations

import json
from typing import Any

ARTICLE_59_LABEL = "労働安全衛生法第59条"

_MIN_CHUNK_TOKENS_FOR_SPLIT = 50  # heuristic threshold for "very short section"


def allocate_question_counts(chunks: list[dict[str, Any]], safety_flags: list[bool], question_count: int) -> list[int]:
    """Allocate the total question_count across chunks.

    Proportional to chunk length, with a hard floor: every safety-flagged
    chunk gets >= 1 question regardless of its proportional share (proposal
    §11 Risk #3 mitigation — a short but safety-critical section must not be
    starved to zero).
    """
    if not chunks:
        return []

    lengths = [max(1, len(c["text"])) for c in chunks]
    total_length = sum(lengths)

    raw_shares = [round(question_count * (length / total_length)) for length in lengths]

    # Enforce the safety-section floor.
    allocation = [max(1, share) if safety_flags[i] else share for i, share in enumerate(raw_shares)]

    # Reconcile rounding drift against question_count without violating the
    # safety floor: adjust only non-safety chunks first.
    diff = question_count - sum(allocation)
    non_safety_idx = [i for i, flag in enumerate(safety_flags) if not flag]
    idx_cycle = non_safety_idx or list(range(len(allocation)))
    i = 0
    while diff != 0 and idx_cycle:
        target = idx_cycle[i % len(idx_cycle)]
        if diff > 0:
            allocation[target] += 1
            diff -= 1
        elif allocation[target] > (1 if safety_flags[target] else 0):
            allocation[target] -= 1
            diff += 1
        i += 1
        if i > 10_000:  # pragma: no cover - safety valve, should never trigger
            break

    return allocation


def allocate_formats(count: int, format_mix: dict[str, int]) -> list[str]:
    """Expand a {"mcq": n, "short_answer": n, "tf": n} mix into a flat list
    of `count` format labels, proportional to the requested mix."""
    total_requested = sum(format_mix.values()) or 1
    labels = []
    for fmt, share in format_mix.items():
        labels.extend([fmt] * round(count * (share / total_requested)))
    # Truncate/pad to exactly `count` — allocation rounding may drift by 1-2.
    if len(labels) > count:
        labels = labels[:count]
    while len(labels) < count:
        labels.append(next(iter(format_mix), "mcq"))
    return labels


def build_generation_prompt(
    chunk: dict[str, Any],
    formats: list[str],
    is_safety_section: bool,
    difficulty_target: str,
    locale: str,
) -> str:
    """Build the LLM prompt for one chunk's question batch.

    Explicitly instructs the model to ground every answer in the source
    chunk and to keep output locale-consistent (proposal §11 Risks #1, #5).
    """
    safety_instruction = (
        f"This section discusses safety-related procedures. Tag every "
        f"question generated from it with the compliance article "
        f"'{ARTICLE_59_LABEL}'.\n"
        if is_safety_section
        else ""
    )
    return (
        f"You are generating a staff training quiz from a retail SOP excerpt.\n"
        f"Source chunk (chunk_id={chunk['chunk_id']}):\n---\n{chunk['text']}\n---\n\n"
        f"{safety_instruction}"
        f"Generate {len(formats)} question(s) with formats: {formats}.\n"
        f"Difficulty target: {difficulty_target}.\n"
        f"Output locale: {locale} — do not mix languages in question text.\n"
        f"Every answer MUST be directly supported by the source chunk text above "
        f"— do not invent facts not present in the source.\n"
        f"Respond as a JSON array of objects with fields: "
        f"format, text, options (list or null for non-MCQ), answer, difficulty."
    )


def parse_llm_response(raw_response: str) -> list[dict[str, Any]]:
    """Parse the LLM's JSON array response. Returns [] on malformed output
    rather than raising — the caller (MainNode) decides retry vs error."""
    try:
        parsed = json.loads(raw_response)
    except (json.JSONDecodeError, TypeError):
        return []
    return parsed if isinstance(parsed, list) else []


def is_answer_grounded(answer: str, source_chunk_text: str) -> bool:
    """Best-effort grounding check (proposal §11 Risk #1 mitigation):
    reject an answer key that cannot be found in its source chunk at all.

    This is a substring check, not semantic verification — it catches
    fabricated answers with no textual basis while allowing paraphrase.
    """
    if not answer:
        return False
    return answer.strip() in source_chunk_text or any(
        token in source_chunk_text for token in answer.split() if len(token) > 1
    )
