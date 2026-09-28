# PB-1 (domain): Answer-grounding enforcement
# Verifies MainNode._extra_security_gate_output() (S-3) is the boundary that
# drops ungrounded LLM-generated answers before they can reach post_process
# or leave the node — proposal §11 Risk #1 (highest-severity risk).

from src.nodes.main_node import MainNode


def _result_with_one_ungrounded_question() -> dict:
    return {
        "raw_questions": [
            {"question_id": 0, "chunk_id": 0, "_grounded": True, "text": "grounded"},
            {"question_id": 1, "chunk_id": 0, "_grounded": False, "text": "hallucinated"},
        ],
        "raw_answers": [
            {"question_id": 0, "answer": "real"},
            {"question_id": 1, "answer": "fabricated"},
        ],
        "difficulty_tags": [
            {"question_id": 0, "difficulty": "medium"},
            {"question_id": 1, "difficulty": "medium"},
        ],
        "safety_compliance_tags": [
            {"question_id": 1, "article": "労働安全衛生法第59条", "compliant": True},
        ],
    }


class TestAnswerGroundingBoundary:
    def test_ungrounded_question_never_crosses_the_node_boundary(self):
        node = MainNode(llm=None)
        gated = node._extra_security_gate_output(_result_with_one_ungrounded_question())

        surviving_ids = {q["question_id"] for q in gated["raw_questions"]}
        assert 1 not in surviving_ids, "ungrounded question_id=1 must be dropped at the S-3 boundary"
        assert surviving_ids == {0}

        # Every dependent array (answers/difficulty/safety tags) must be
        # pruned in lockstep — no orphaned record referencing a dropped
        # question_id should survive the boundary.
        assert {a["question_id"] for a in gated["raw_answers"]} == {0}
        assert {d["question_id"] for d in gated["difficulty_tags"]} == {0}
        assert {t["question_id"] for t in gated["safety_compliance_tags"]} == set()

    def test_internal_grounded_marker_never_leaves_the_node(self):
        node = MainNode(llm=None)
        gated = node._extra_security_gate_output(_result_with_one_ungrounded_question())

        for question in gated["raw_questions"]:
            assert "_grounded" not in question, (
                "_grounded is an internal bookkeeping field — it must not "
                "appear in the result dict returned across the node boundary"
            )
