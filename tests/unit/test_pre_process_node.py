# RET-C2-618 — Unit Tests: PreProcessNode

from framework.schemas.agent_status import AgentStatus
from src.nodes.pre_process_node import PreProcessNode, MAX_DOCUMENT_TOKENS

SAMPLE_SOP = """## 手順
Step 1: Open the register drawer.
Step 2: Count the starting cash float.

## 禁止事項
危険物の取り扱いには保護具を必ず着用してください。
"""


def _base_context(**overrides) -> dict:
    ctx = {
        "question_count": 4,
        "format_mix": {"mcq": 4, "short_answer": 0, "tf": 0},
        "difficulty_target": "mixed",
        "locale": "ja",
    }
    ctx.update(overrides)
    return ctx


class TestPreProcessNode:
    def setup_method(self):
        self.node = PreProcessNode()

    def test_success_path_chunks_and_flags_safety_sections(self):
        state = {
            "user_input": SAMPLE_SOP,
            "input_context": _base_context(),
        }
        result = self.node.execute(state)

        assert result["status"] == AgentStatus.SUCCESS.value
        assert len(result["chunks"]) == 2
        assert result["safety_flags"] == [False, True]
        assert result["question_count"] == 4
        assert result["difficulty_target"] == "mixed"
        assert result["locale"] == "ja"

    def test_empty_input_returns_error(self):
        state = {"user_input": "", "input_context": _base_context()}
        result = self.node.execute(state)

        assert result["status"] == AgentStatus.ERROR.value
        assert len(result["error_log"]) > 0

    def test_invalid_difficulty_target_returns_error(self):
        state = {
            "user_input": SAMPLE_SOP,
            "input_context": _base_context(difficulty_target="impossible"),
        }
        result = self.node.execute(state)

        assert result["status"] == AgentStatus.ERROR.value

    def test_invalid_locale_returns_error(self):
        state = {
            "user_input": SAMPLE_SOP,
            "input_context": _base_context(locale="fr"),
        }
        result = self.node.execute(state)

        assert result["status"] == AgentStatus.ERROR.value

    def test_non_positive_question_count_returns_error(self):
        state = {
            "user_input": SAMPLE_SOP,
            "input_context": _base_context(question_count=0),
        }
        result = self.node.execute(state)

        assert result["status"] == AgentStatus.ERROR.value

    def test_unstructured_document_falls_back_to_single_chunk(self):
        state = {
            "user_input": "Just a plain paragraph with no headings at all.",
            "input_context": _base_context(),
        }
        result = self.node.execute(state)

        assert result["status"] == AgentStatus.SUCCESS.value
        assert len(result["chunks"]) == 1
        assert result["safety_flags"] == [False]

    def test_extra_safety_keywords_extend_default_list(self):
        state = {
            "user_input": "感電注意：作業前に必ず電源を切ってください。",
            "input_context": _base_context(safety_keywords=["感電注意"]),
        }
        result = self.node.execute(state)

        assert result["status"] == AgentStatus.SUCCESS.value
        assert result["safety_flags"] == [True]

    # --- CG-04 (docs/03_test_spec.md): S-2 document size gate ---

    def test_extra_security_gate_input_rejects_oversized_document(self):
        oversized_text = "x" * (MAX_DOCUMENT_TOKENS * 4 + 100)  # ~4 chars/token
        state = {"user_input": oversized_text}

        gated_state = self.node._extra_security_gate_input(state)

        assert gated_state["status"] == AgentStatus.ERROR.value
        assert "token" in gated_state["error_log"][0].lower()

    def test_extra_security_gate_input_accepts_normal_document(self):
        state = {"user_input": SAMPLE_SOP}

        gated_state = self.node._extra_security_gate_input(state)

        assert "status" not in gated_state or gated_state.get("status") != AgentStatus.ERROR.value

    def test_extra_security_gate_input_rejects_non_string_input(self):
        state = {"user_input": 12345}

        gated_state = self.node._extra_security_gate_input(state)

        assert gated_state["status"] == AgentStatus.ERROR.value
