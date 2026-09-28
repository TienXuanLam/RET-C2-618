# PB-2 (domain): S-3 PII output block
# Verifies PostProcessNode._extra_security_gate_output() actually blocks
# (raises), not merely redacts, when generated question text contains a
# PII-shaped pattern — SOP-derived content is not expected to contain PII,
# so any match indicates a real leak (docs/02_design.md Security Design).

import pytest

from src.nodes.post_process_node import PostProcessNode


def _payload_with_text(text: str) -> dict:
    return {
        "formatted_output": {
            "questions": [{"question_id": 0, "text": text}],
            "answer_key": [],
            "difficulty": [],
            "safety_compliance_tags": [],
        }
    }


class TestPiiOutputBoundary:
    def test_email_pattern_blocks_output_at_the_boundary(self):
        node = PostProcessNode()
        with pytest.raises(RuntimeError):
            node._extra_security_gate_output(_payload_with_text("Email hr@example.com for details."))

    def test_jp_phone_pattern_blocks_output_at_the_boundary(self):
        node = PostProcessNode()
        with pytest.raises(RuntimeError):
            node._extra_security_gate_output(_payload_with_text("Call 090-1234-5678 for help."))

    def test_clean_sop_derived_text_passes_the_boundary_unchanged(self):
        node = PostProcessNode()
        payload = _payload_with_text("危険物の取り扱いには保護具を必ず着用してください。")

        gated = node._extra_security_gate_output(payload)

        assert gated == payload
