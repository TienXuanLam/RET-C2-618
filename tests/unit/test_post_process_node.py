# RET-C2-618 — Unit Tests: PostProcessNode

import pytest

from framework.schemas.agent_status import AgentStatus
from src.nodes.post_process_node import PostProcessNode


def _state(**overrides) -> dict:
    base = {
        "raw_questions": [
            {
                "question_id": 0,
                "chunk_id": 0,
                "format": "mcq",
                "text": "What must be worn when handling 危険物?",
                "options": ["保護具", "Nothing"],
                "source_chunk_ref": 0,
            }
        ],
        "raw_answers": [{"question_id": 0, "answer": "保護具"}],
        "difficulty_tags": [{"question_id": 0, "difficulty": "medium"}],
        "safety_compliance_tags": [
            {"question_id": 0, "article": "労働安全衛生法第59条", "compliant": True}
        ],
    }
    base.update(overrides)
    return base


class TestPostProcessNode:
    def setup_method(self):
        self.node = PostProcessNode()

    def test_success_path_assembles_output(self):
        result = self.node.execute(_state())

        assert result["status"] == AgentStatus.SUCCESS.value
        payload = result["formatted_output"]
        assert len(payload["questions"]) == 1
        assert len(payload["answer_key"]) == 1
        assert "no_safety_sections_detected" not in payload

    def test_no_questions_returns_error(self):
        result = self.node.execute(_state(raw_questions=[]))

        assert result["status"] == AgentStatus.ERROR.value
        assert len(result["error_log"]) > 0

    def test_missing_required_field_returns_error(self):
        state = _state(
            raw_questions=[{"question_id": 0, "chunk_id": 0, "format": "mcq", "text": "Q"}]
            # missing source_chunk_ref
        )
        result = self.node.execute(state)

        assert result["status"] == AgentStatus.ERROR.value
        assert "source_chunk_ref" in result["error_log"][0]

    # --- CG-05 (docs/03_test_spec.md): no-safety-section flag ---

    def test_no_safety_sections_detected_flag_set_when_empty(self):
        result = self.node.execute(_state(safety_compliance_tags=[]))

        assert result["status"] == AgentStatus.SUCCESS.value
        assert result["formatted_output"]["no_safety_sections_detected"] is True

    # --- CG-07 (docs/03_test_spec.md): S-3 PII block ---

    def test_extra_security_gate_output_blocks_email_pii(self):
        result = {
            "formatted_output": {
                "questions": [{"question_id": 0, "text": "Contact staff@example.com for help."}],
                "answer_key": [],
                "difficulty": [],
                "safety_compliance_tags": [],
            }
        }

        with pytest.raises(RuntimeError):
            self.node._extra_security_gate_output(result)

    def test_extra_security_gate_output_allows_clean_text(self):
        result = {
            "formatted_output": {
                "questions": [{"question_id": 0, "text": "保護具を着用してください。"}],
                "answer_key": [],
                "difficulty": [],
                "safety_compliance_tags": [],
            }
        }

        gated = self.node._extra_security_gate_output(result)

        assert gated == result
