# PB-5 (domain): msgpack round-trip verification for formatted_output
# Confirms at runtime — not just by static type inspection — that the
# nested list[dict] structure produced by post_process survives LangGraph's
# msgpack checkpoint serialization.

import msgpack

from src.services.output_assembly_service import assemble_output


def _sample_formatted_output() -> dict:
    raw_questions = [
        {
            "question_id": 0,
            "chunk_id": 0,
            "format": "mcq",
            "text": "What must be worn when handling 危険物?",
            "options": ["保護具", "Nothing", "Gloves only", "Mask only"],
            "source_chunk_ref": 0,
        },
        {
            "question_id": 1,
            "chunk_id": 1,
            "format": "short_answer",
            "text": "What time does the register drawer open?",
            "options": None,
            "source_chunk_ref": 1,
        },
    ]
    raw_answers = [
        {"question_id": 0, "answer": "保護具"},
        {"question_id": 1, "answer": "9am"},
    ]
    difficulty_tags = [
        {"question_id": 0, "difficulty": "medium"},
        {"question_id": 1, "difficulty": "easy"},
    ]
    safety_compliance_tags = [
        {"question_id": 0, "article": "労働安全衛生法第59条", "compliant": True},
    ]
    return assemble_output(raw_questions, raw_answers, difficulty_tags, safety_compliance_tags)


class TestMsgpackRoundtrip:
    def test_formatted_output_survives_msgpack_roundtrip(self):
        payload = _sample_formatted_output()

        packed = msgpack.packb(payload, use_bin_type=True)
        unpacked = msgpack.unpackb(packed, raw=False)

        # msgpack returns plain dict/list on unpack, matching the original
        # nested list[dict] structure produced by assemble_output().
        assert unpacked == payload

    def test_no_safety_sections_variant_survives_roundtrip(self):
        payload = assemble_output(
            raw_questions=[{"question_id": 0, "chunk_id": 0, "format": "tf", "text": "Q", "options": None, "source_chunk_ref": 0}],
            raw_answers=[{"question_id": 0, "answer": "True"}],
            difficulty_tags=[{"question_id": 0, "difficulty": "easy"}],
            safety_compliance_tags=[],
        )

        packed = msgpack.packb(payload, use_bin_type=True)
        unpacked = msgpack.unpackb(packed, raw=False)

        assert unpacked == payload
        assert unpacked["no_safety_sections_detected"] is True

    def test_japanese_text_survives_roundtrip_unmangled(self):
        payload = _sample_formatted_output()

        packed = msgpack.packb(payload, use_bin_type=True)
        unpacked = msgpack.unpackb(packed, raw=False)

        assert unpacked["safety_compliance_tags"][0]["article"] == "労働安全衛生法第59条"
        assert "保護具" in unpacked["questions"][0]["options"]
