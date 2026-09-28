# PB-3 (domain): Safety-section minimum-question floor
# Verifies allocate_question_counts() never starves a safety-flagged chunk
# to zero questions, even when its proportional share rounds down to 0 —
# proposal §11 Risk #3.

from src.services.quiz_generation_service import allocate_question_counts


class TestSafetySectionFloor:
    def test_short_safety_chunk_still_gets_at_least_one_question(self):
        chunks = [
            {"chunk_id": 0, "text": "x" * 2000},  # long, non-safety
            {"chunk_id": 1, "text": "危険"},  # very short, safety-flagged
        ]
        safety_flags = [False, True]

        allocation = allocate_question_counts(chunks, safety_flags, question_count=5)

        assert allocation[1] >= 1, "safety-flagged chunk must receive >= 1 question"
        assert sum(allocation) == 5, "total allocation must still equal question_count"

    def test_allocation_sums_to_question_count_with_multiple_safety_chunks(self):
        chunks = [{"chunk_id": i, "text": "危険" if i % 2 else "x" * 500} for i in range(6)]
        safety_flags = [i % 2 == 1 for i in range(6)]

        allocation = allocate_question_counts(chunks, safety_flags, question_count=6)

        assert sum(allocation) == 6
        for flagged, count in zip(safety_flags, allocation):
            if flagged:
                assert count >= 1
