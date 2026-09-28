"""AgentCore Platform v1.0"""

# Node contract:
#  - Extend FunctionNode; implement execute(state) -> dict
#  - Return ONLY the fields this node changes (never full state)
#  - Return AgentStatus enum constants — never plain strings
#  - Read input_context via state.get("input_context", {}) — read-only
#  - Never import from mediator/, api/, or other agents

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.sop_chunk_service import (
    chunk_document,
    detect_safety_sections,
    estimate_tokens,
)

# S-2: reject documents larger than this token estimate rather than
# truncating silently — truncation could drop a safety section without
# the caller knowing (proposal §11 Risk #4).
MAX_DOCUMENT_TOKENS = 50_000

_VALID_DIFFICULTIES = {"easy", "medium", "hard", "mixed"}
_VALID_LOCALES = {"ja", "en"}


class PreProcessNode(FunctionNode):
    """Validate SOP input, chunk by section, detect safety-topic sections."""

    # S-1: explicit by design, not inherited implicitly. The framework
    # enforces required_trust_level per-node inside BaseNode.__call__() —
    # it is not inherited from config/agent.yaml's manifest-level
    # declaration. Set to VERIFIED_EXTERNAL to match the manifest and
    # prevent an ANONYMOUS caller from invoking this node directly.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def _extra_security_gate_input(self, state: dict[str, Any]) -> dict[str, Any]:
        # S-2: document size + type guard. Must not raise — reject via status.
        document_text = state.get("user_input", "")
        if not isinstance(document_text, str):
            state = dict(state)
            state["status"] = AgentStatus.ERROR.value
            state["error_log"] = ["PreProcessNode: user_input must be text (str)"]
            return state

        if estimate_tokens(document_text) > MAX_DOCUMENT_TOKENS:
            state = dict(state)
            state["status"] = AgentStatus.ERROR.value
            state["error_log"] = [
                f"PreProcessNode: document exceeds {MAX_DOCUMENT_TOKENS} token "
                "cap — split into chapter-level segments before invoking "
                "(see docs/07_operation_guide.md)"
            ]
            return state

        return state

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        document_text = state.get("user_input", "").strip()
        input_context = state.get("input_context", {})  # read-only

        if not document_text:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["PreProcessNode: document_content is empty or missing"],
            }

        difficulty_target = input_context.get("difficulty_target", "mixed")
        if difficulty_target not in _VALID_DIFFICULTIES:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": [f"PreProcessNode: invalid difficulty_target '{difficulty_target}'"],
            }

        locale = input_context.get("locale", "ja")
        if locale not in _VALID_LOCALES:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": [f"PreProcessNode: invalid locale '{locale}'"],
            }

        question_count = input_context.get("question_count", 0)
        if not isinstance(question_count, int) or question_count <= 0:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["PreProcessNode: question_count must be a positive int"],
            }

        format_mix = input_context.get("format_mix", {"mcq": question_count, "short_answer": 0, "tf": 0})

        chunks = chunk_document(document_text)
        if not chunks:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["PreProcessNode: no usable content after chunking"],
            }

        safety_flags = detect_safety_sections(chunks, extra_keywords=input_context.get("safety_keywords"))

        emit_trace_event(
            "sop_chunked",
            {
                "chunk_count": len(chunks),
                "safety_section_count": sum(safety_flags),
            },
            state,
        )

        return {
            "chunks": chunks,
            "safety_flags": safety_flags,
            "question_count": question_count,
            "format_mix": format_mix,
            "difficulty_target": difficulty_target,
            "locale": locale,
            "status": AgentStatus.SUCCESS.value,
        }
