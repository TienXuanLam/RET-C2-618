"""AgentCore Platform v1.0"""

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.quiz_generation_service import (
    ARTICLE_59_LABEL,
    allocate_formats,
    allocate_question_counts,
    build_generation_prompt,
    is_answer_grounded,
    parse_llm_response,
)


class MainNode(FunctionNode):
    """ToolCallingAgent step: LLM-driven quiz generation + Article 59 tagging."""

    # S-1: enforced per-node inside BaseNode.__call__(), not inherited from
    # config/agent.yaml's manifest-level declaration. Set to
    # VERIFIED_EXTERNAL to match the manifest and prevent an ANONYMOUS
    # caller from invoking this LLM-backed generation step directly.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def __init__(self, llm: Any = None) -> None:
        # Default None so framework tooling that dynamically instantiates
        # node classes with no args (e.g. PB-6 invoke-order verification)
        # can construct this node — execute() returns before touching
        # self._llm whenever "chunks" is absent from state.
        self._llm = llm

    def _extra_security_gate_output(self, result: dict[str, Any]) -> dict[str, Any]:
        # S-3: defence-in-depth grounding check. Any question
        # whose answer could not be grounded in its source chunk is dropped
        # here rather than passed downstream — proposal §11 Risk #1 is the
        # highest-severity risk identified for this template.
        questions = result.get("raw_questions")
        if not questions:
            return result

        ungrounded_ids = {q["question_id"] for q in questions if not q.get("_grounded", True)}
        if ungrounded_ids:
            result = dict(result)
            result["raw_questions"] = [q for q in questions if q["question_id"] not in ungrounded_ids]
            result["raw_answers"] = [a for a in result.get("raw_answers", []) if a["question_id"] not in ungrounded_ids]
            result["difficulty_tags"] = [
                d for d in result.get("difficulty_tags", []) if d["question_id"] not in ungrounded_ids
            ]
            result["safety_compliance_tags"] = [
                t for t in result.get("safety_compliance_tags", []) if t["question_id"] not in ungrounded_ids
            ]
        # Strip the internal-only marker before the result leaves this node.
        for q in result.get("raw_questions", []):
            q.pop("_grounded", None)
        return result

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        chunks = state.get("chunks", [])
        safety_flags = state.get("safety_flags", [])
        question_count = state.get("question_count", 0)
        format_mix = state.get("format_mix", {})
        difficulty_target = state.get("difficulty_target", "mixed")
        locale = state.get("locale", "ja")

        if not chunks:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["MainNode: no chunks available from pre_process"],
            }

        per_chunk_counts = allocate_question_counts(chunks, safety_flags, question_count)

        raw_questions: list[dict[str, Any]] = []
        raw_answers: list[dict[str, Any]] = []
        difficulty_tags: list[dict[str, Any]] = []
        safety_compliance_tags: list[dict[str, Any]] = []
        next_question_id = 0
        total_tokens = 0

        for chunk, is_safety, count in zip(chunks, safety_flags, per_chunk_counts):
            if count <= 0:
                continue

            formats = allocate_formats(count, format_mix)
            prompt = build_generation_prompt(chunk, formats, is_safety, difficulty_target, locale)

            raw_response = ""
            if self._llm is not None:
                response = self._llm.complete([{"role": "user", "content": prompt}])
                raw_response = response.get("content", "") if isinstance(response, dict) else str(response)
            total_tokens += len(prompt) // 4 + len(raw_response) // 4
            generated = parse_llm_response(raw_response)

            for item in generated:
                qid = next_question_id
                next_question_id += 1

                answer = item.get("answer", "")
                grounded = is_answer_grounded(answer, chunk["text"])

                raw_questions.append(
                    {
                        "question_id": qid,
                        "chunk_id": chunk["chunk_id"],
                        "format": item.get("format", "mcq"),
                        "text": item.get("text", ""),
                        "options": item.get("options"),
                        "source_chunk_ref": chunk["chunk_id"],
                        "_grounded": grounded,
                    }
                )
                raw_answers.append({"question_id": qid, "answer": answer})
                difficulty_tags.append(
                    {
                        "question_id": qid,
                        "difficulty": item.get("difficulty", difficulty_target),
                    }
                )
                if is_safety:
                    safety_compliance_tags.append(
                        {
                            "question_id": qid,
                            "article": ARTICLE_59_LABEL,
                            "compliant": True,
                        }
                    )

        if not raw_questions:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["MainNode: LLM produced no usable questions"],
            }

        emit_trace_event(
            "llm_call",
            {
                "model": getattr(self._llm, "model_name", "unknown"),
                "tokens": total_tokens,
                "question_count_generated": len(raw_questions),
            },
            state,
        )

        return {
            "raw_questions": raw_questions,
            "raw_answers": raw_answers,
            "difficulty_tags": difficulty_tags,
            "safety_compliance_tags": safety_compliance_tags,
            "status": AgentStatus.SUCCESS.value,
        }
