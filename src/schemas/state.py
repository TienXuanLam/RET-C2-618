"""AgentCore Platform v1.0"""

# ADR-005: State must be a flat TypedDict — never Pydantic BaseModel.
# LangGraph checkpoints use msgpack serialization; Pydantic objects
# cause silent corruption.  Extend AgentState with agent-specific
# fields only.  Do NOT add credentials, secrets, or Pydantic models.

from typing import Any

from framework.schemas.agent_state import AgentState


class State(AgentState):
    """Agent state for RetailStaffSOPQuizGeneratorAgent.

    All shared fields (user_input, status, session_id, node_history,
    error_log, hitl_*, etc.) are inherited from AgentState. Fields below
    are specific to the SOP -> compliance quiz pipeline. See docs/02_design.md
    "State Definition" for the field-by-field producer/consumer mapping.

    Every domain field below is effectively optional at runtime (Architect
    review ARCH-0918-20260706, finding RET-C2-618-ARCH-R1-01): each is
    populated incrementally by pre_process/main/post_process, not present
    from initialize() — a checkpoint restored mid-pipeline (e.g. after only
    pre_process has run) legitimately lacks raw_questions/formatted_output/
    etc. TypedDict is not runtime-enforced in Python, so a plain field
    declaration already tolerates a missing key; `total=False` and
    `NotRequired[...]` are not used here because `framework.*` has no
    `py.typed` marker, so mypy treats `AgentState` as `Any` and rejects both
    forms as invalid on a non-TypedDict base (this project's
    `ignore_missing_imports` override for framework.* is required elsewhere
    and cannot be narrowed per-module without breaking other imports).
    """

    # Caller-supplied invocation parameters (copied out of input_context by
    # pre_process; input_context itself remains read-only per ADR on state).
    question_count: int
    format_mix: dict[str, int]  # {"mcq": int, "short_answer": int, "tf": int}
    difficulty_target: str  # "easy" | "medium" | "hard" | "mixed"
    locale: str  # "ja" | "en"

    # Produced by pre_process
    chunks: list[dict[str, Any]]  # [{"chunk_id": int, "text": str, "is_safety_section": bool}, ...]
    safety_flags: list[bool]  # parallel to chunks

    # Produced by main (ToolCallingAgent step)
    raw_questions: list[
        dict[str, Any]
    ]  # [{"question_id", "chunk_id", "format", "text", "options", "source_chunk_ref"}, ...]
    raw_answers: list[dict[str, Any]]  # [{"question_id", "answer"}, ...]
    difficulty_tags: list[dict[str, Any]]  # [{"question_id", "difficulty"}, ...]
    safety_compliance_tags: list[dict[str, Any]]  # [{"question_id", "article", "compliant"}, ...]

    # Produced by post_process
    formatted_output: dict[
        str, Any
    ]  # {"questions": [...], "answer_key": [...], "difficulty": [...], "safety_compliance_tags": [...]}
