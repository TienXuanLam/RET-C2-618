"""AgentCore Platform v1.0"""

# Service layer: SOP document chunking + safety-topic keyword detection.
# Must NOT contain framework imports (no BaseNode/FunctionNode/AgentState
# here) — pure domain logic called by src/nodes/pre_process_node.py.

from __future__ import annotations

import re
from typing import Any

# Default safety-topic keyword list (PreProcessNode spec).
# Caller may extend via input_context["safety_keywords"] (proposal §11 Risk #2
# mitigation) — the extension list is merged, not replaced, so the statutory
# baseline keywords are never dropped.
DEFAULT_SAFETY_KEYWORDS = ["危険", "安全", "禁止", "取扱注意", "保護具"]

# Section-heading markers used to split a retail SOP into chunks. Retail SOPs
# use structured headings (手順 / 禁止事項 / 緊急対応 etc.) rather than plain
# paragraph breaks — chunking on these boundaries keeps each chunk's content
# semantically coherent for downstream question generation (proposal §5).
_HEADING_PATTERN = re.compile(r"(?m)^(#{1,3}\s+.+|第[0-9一二三四五六七八九十]+条.*|[0-9]+[.\)]\s+.+)$")

# Approximate token-count heuristic (proposal §4: "< 1 question per 200 tokens").
_CHARS_PER_TOKEN_APPROX = 4


def estimate_tokens(text: str) -> int:
    """Rough token estimate for the document-size gate (S-2, 50k token cap)."""
    return max(1, len(text) // _CHARS_PER_TOKEN_APPROX)


def chunk_document(text: str) -> list[dict[str, Any]]:
    """Split SOP text into section-bounded chunks.

    Falls back to a single chunk when no heading markers are found, so short
    or unstructured documents still produce at least one usable chunk.
    """
    matches = list(_HEADING_PATTERN.finditer(text))
    if not matches:
        stripped = text.strip()
        return [{"chunk_id": 0, "text": stripped}] if stripped else []

    chunks: list[dict[str, Any]] = []
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append({"chunk_id": len(chunks), "text": chunk_text})
    return chunks


def detect_safety_sections(chunks: list[dict[str, Any]], extra_keywords: list[str] | None = None) -> list[bool]:
    """Flag chunks containing safety-relevant keywords.

    Returns a bool list parallel to `chunks`. Extra keywords (caller-supplied,
    proposal §11 Risk #2) are merged with the statutory baseline list.
    """
    keywords = list(DEFAULT_SAFETY_KEYWORDS)
    if extra_keywords:
        keywords.extend(k for k in extra_keywords if k not in keywords)

    return [any(kw in chunk["text"] for kw in keywords) for chunk in chunks]
