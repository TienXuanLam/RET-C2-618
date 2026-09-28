"""AgentCore Platform v1.0"""

import re
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.output_assembly_service import assemble_output, validate_output_schema

# S-3 domain check: SOP-derived quiz content is not expected to contain
# personal information. Any match here indicates a real data leak (e.g. LLM
# echoing an example name/phone number), not a false positive to preserve —
# so this hook blocks rather than redacts.
_PII_PATTERNS = [
    re.compile(r"\b\d{3}-\d{4}-\d{4}\b"),  # JP phone number shape
    re.compile(r"[\w.+-]{1,64}@[\w-]{1,63}(?:\.[\w-]{1,63}){1,4}"),  # email address
]


class PostProcessNode(FunctionNode):
    """Assemble + validate the final structured JSON quiz output."""

    # S-1: enforced per-node inside BaseNode.__call__(), not inherited from
    # config/agent.yaml's manifest-level declaration. Set to
    # VERIFIED_EXTERNAL to match the manifest and prevent an ANONYMOUS
    # caller from invoking this node directly.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def _extra_security_gate_output(self, result: dict[str, Any]) -> dict[str, Any]:
        formatted_output = result.get("formatted_output")
        if not formatted_output:
            return result

        for question in formatted_output.get("questions", []):
            text = question.get("text", "")
            if any(p.search(text) for p in _PII_PATTERNS):
                raise RuntimeError(
                    "PostProcessNode: S-3 blocked output — possible PII " "detected in generated question text"
                )
        return result

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        raw_questions = state.get("raw_questions", [])
        raw_answers = state.get("raw_answers", [])
        difficulty_tags = state.get("difficulty_tags", [])
        safety_compliance_tags = state.get("safety_compliance_tags", [])

        if not raw_questions:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["PostProcessNode: no questions to assemble"],
            }

        formatted_output = assemble_output(raw_questions, raw_answers, difficulty_tags, safety_compliance_tags)

        schema_errors = validate_output_schema(formatted_output)
        if schema_errors:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": schema_errors,
            }

        emit_trace_event(
            "output_assembled",
            {
                "question_count": len(formatted_output["questions"]),
                "safety_tag_count": len(formatted_output["safety_compliance_tags"]),
            },
            state,
        )

        return {
            "formatted_output": formatted_output,
            "status": AgentStatus.SUCCESS.value,
        }
