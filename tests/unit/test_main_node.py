# RET-C2-618 — Unit Tests: MainNode

import json

from framework.schemas.agent_status import AgentStatus
from src.nodes.main_node import MainNode


class FakeLLM:
    """Returns one canned question per prompt, grounded in the source chunk."""

    def __init__(self, response=None):
        self._response = response
        self.calls = []

    def complete(self, messages, **kwargs):
        self.calls.append(messages)
        if self._response is not None:
            return {"content": self._response}
        return {
            "content": json.dumps([
                {
                    "format": "mcq",
                    "text": "What must be worn when handling 危険物?",
                    "options": ["保護具", "Nothing", "Gloves only", "Mask only"],
                    "answer": "保護具",
                    "difficulty": "medium",
                }
            ])
        }


def _state(**overrides) -> dict:
    base = {
        "chunks": [{"chunk_id": 0, "text": "危険物の取り扱いには保護具を必ず着用してください。"}],
        "safety_flags": [True],
        "question_count": 1,
        "format_mix": {"mcq": 1, "short_answer": 0, "tf": 0},
        "difficulty_target": "medium",
        "locale": "ja",
    }
    base.update(overrides)
    return base


class TestMainNode:
    def test_success_path_tags_safety_question(self):
        node = MainNode(llm=FakeLLM())
        result = node.execute(_state())

        assert result["status"] == AgentStatus.SUCCESS.value
        assert len(result["raw_questions"]) == 1
        assert result["raw_answers"][0]["answer"] == "保護具"
        assert len(result["safety_compliance_tags"]) == 1
        assert result["safety_compliance_tags"][0]["article"] == "労働安全衛生法第59条"

    def test_no_chunks_returns_error(self):
        node = MainNode(llm=FakeLLM())
        result = node.execute(_state(chunks=[], safety_flags=[]))

        assert result["status"] == AgentStatus.ERROR.value
        assert len(result["error_log"]) > 0

    def test_unparseable_llm_response_returns_error(self):
        node = MainNode(llm=FakeLLM(response="not valid json"))
        result = node.execute(_state())

        assert result["status"] == AgentStatus.ERROR.value

    def test_non_safety_chunk_produces_no_compliance_tag(self):
        node = MainNode(llm=FakeLLM())
        state = _state(
            chunks=[{"chunk_id": 0, "text": "Open the register drawer at 9am."}],
            safety_flags=[False],
        )
        result = node.execute(state)

        assert result["status"] == AgentStatus.SUCCESS.value
        assert result["safety_compliance_tags"] == []

    # --- CG-01 (docs/03_test_spec.md): S-3 answer-grounding gate ---

    def test_extra_security_gate_output_drops_ungrounded_question(self):
        node = MainNode(llm=FakeLLM())
        result_with_marker = {
            "raw_questions": [
                {"question_id": 0, "chunk_id": 0, "_grounded": True, "text": "grounded Q"},
                {"question_id": 1, "chunk_id": 0, "_grounded": False, "text": "hallucinated Q"},
            ],
            "raw_answers": [
                {"question_id": 0, "answer": "ok"},
                {"question_id": 1, "answer": "made up"},
            ],
            "difficulty_tags": [
                {"question_id": 0, "difficulty": "medium"},
                {"question_id": 1, "difficulty": "medium"},
            ],
            "safety_compliance_tags": [],
        }

        gated = node._extra_security_gate_output(result_with_marker)

        assert [q["question_id"] for q in gated["raw_questions"]] == [0]
        assert [a["question_id"] for a in gated["raw_answers"]] == [0]
        assert "_grounded" not in gated["raw_questions"][0]

    def test_extra_security_gate_output_passthrough_when_no_questions(self):
        node = MainNode(llm=FakeLLM())
        result = {"status": AgentStatus.ERROR.value}

        gated = node._extra_security_gate_output(result)

        assert gated == result
