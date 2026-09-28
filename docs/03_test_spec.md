# Test Specification

## Test Strategy
- Coverage target: 100% of TC/PB items below; every node covers success + error/edge path
- Test types: Unit (per-node, mocked LLM) / Proof-of-Boundary (framework contract) — no Integration suite in this iteration (see docs/02_design.md Composition Pattern: standalone pipeline, no subgraph to integration-test beyond the 3 unit-tested nodes)
- LLM is injected via `MainNode(llm)` constructor — all unit tests use a `FakeLLM` stub, no real Anthropic API calls

## Framework Compliance Tests (Mandatory)

| TC-ID | Test | Expected Result | Result |
|-------|------|----------------|--------|
| TC-01 | State contract: flat TypedDict | Type check pass, no Pydantic/dataclass | Pass |
| TC-02 | SecurityViolationError fires on invalid input | Error raised | Pass |
| TC-03 | No JWT/Credential in State | CI `gate-credential-scan`: 0 violations | Pass |
| TC-04 | InvocationContext via configurable only | Direct access raises error | N/A — this agent does not call `ctx.secrets.require()` in any node (LLM instance is injected at graph construction, not resolved via secrets inside `execute()`); `ANTHROPIC_API_KEY` is resolved once by `AnthropicClient` outside the node boundary |
| TC-05 | S-4: no duplicate lifecycle events in `execute()` | `node_start` / `node_complete` / `node_error` absent from `execute()` body | 0 duplicates |
| TC-06 | S-2: `_security_gate_input()` not overridden (`FunctionNode` subclass) | `TypeError` raised at class definition if overridden (`@final` enforced by framework) | 0 overrides |
| TC-07 | S-3: `_security_gate_output()` not overridden (`FunctionNode` subclass) | `TypeError` raised at class definition if overridden (`@final` enforced by framework) | 0 overrides |
| TC-08 | `required_trust_level` enforced | Insufficient trust → refused | Pass — manifest declares `VERIFIED_EXTERNAL` at agent level (config/agent.yaml); all 3 domain nodes declare `required_trust_level` explicitly |
| TC-09 | S-2: `_extra_security_gate_input()` non-trivial when domain checks needed | Domain-specific input checks execute correctly (e.g. PII scan on additional fields, consent validation, business rules) | Hook body non-trivial — `PreProcessNode` enforces the 50k-token document size cap and input type check |
| TC-10 | S-3: `_extra_security_gate_output()` non-trivial when domain checks needed | Domain-specific output checks execute correctly (e.g. nested credential scan, PII re-check, content filtering, preservation verification) | Hook body non-trivial — `MainNode` drops ungrounded questions (answer-grounding check); `PostProcessNode` blocks output containing PII-shaped patterns |
| TC-11 | S-4: at least one domain `emit_trace_event()` inside each `execute()` | Domain event emitted on every invocation path | ≥1 per node — `sop_chunked` (pre_process), `llm_call` (main), `output_assembled` (post_process) |

## Proof-of-Boundary Tests (Mandatory)

| PB-ID | Boundary | Test | Expected Result | Result |
|-------|----------|------|----------------|--------|
| PB-1 | BaseNode → EventEmitter | `emit_trace_event()` fires on every invocation path | No silent failures | Pass |
| PB-2 | State serialization | Post-invoke State is primitives only | No Pydantic/dataclass | Pass — all fields are `str`/`int`/`list`/`dict` (docs/02_design.md State Definition); runtime-verified by a msgpack round-trip on `formatted_output` (see `tests/proof_of_boundary/test_pb05_msgpack_roundtrip.py` — file-name suffix `05` is a domain test filename, not a re-numbering of this PB-2 item) |
| PB-3 | Level 2 → External service | Real external service connection | Data retrieved | N/A — this template has no external DB/vector-store dependency; its only external service is the LLM, exercised via `FakeLLM` in unit tests (real connectivity is an STG-stage manual check, not a unit PB) |
| PB-4 | Import isolation | No Level 0 imports | AST scan: 0 violations | Pass |
| PB-5 | Checkpoint safety | No JWT/Pydantic in checkpoint | Inspection pass | Pass |
| PB-6 | Invoke execution order + S-1 trust gate | `__call__()`: S-1 trust gate → S-4 `node_start` → S-2 `_security_gate_input` → `execute()` → S-3 `_security_gate_output` → S-4 `node_complete`; ANONYMOUS caller rejected on every node with `required_trust_level > ANONYMOUS` | Order verified; unauthorized caller rejected | Pass — order in `test_pb_invoke_order.py`; S-1 rejection in `test_pb04_s1_trust_gate.py` (the original unit tests called `execute()` directly, bypassing `__call__()` and never exercising S-1) |

## Compliance Gate Tests (Domain-Specific, Mandatory)

These cover the proposal's highest-severity risks (proposal §11) and are
in addition to the framework TC/PB items above.

| CG-ID | Risk Ref | Test | Input | Expected Result |
|-------|----------|------|-------|----------------|
| CG-01 | Risk #1 (LLM hallucinated answer key) | `MainNode._extra_security_gate_output()` drops a question whose answer text has no textual basis in its source chunk | LLM response with an answer not present in the source chunk | Question + its answer/difficulty/safety-tag entries removed from `raw_questions`/`raw_answers`/`difficulty_tags`/`safety_compliance_tags`; remaining grounded questions unaffected |
| CG-02 | Risk #2 (safety keyword miss) | `detect_safety_sections()` honors caller-supplied `safety_keywords` extension | Chunk containing "感電注意" (not in default keyword list) + `input_context["safety_keywords"] = ["感電注意"]` | Chunk flagged `is_safety_section = True` |
| CG-03 | Risk #3 (safety section starved of questions) | `allocate_question_counts()` floor rule | A safety-flagged chunk with proportionally-rounded 0 questions | Chunk receives ≥ 1 question; total allocation still sums to `question_count` |
| CG-04 | Risk #4 (token cap) | `PreProcessNode._extra_security_gate_input()` rejects an oversized document | Document text estimated > 50,000 tokens | `status = error`; `error_log` mentions the token cap and chapter-level splitting guidance |
| CG-05 | Proposal §4 note | No safety sections detected | Document with zero safety-keyword matches | `formatted_output["safety_compliance_tags"] == []` and `formatted_output["no_safety_sections_detected"] is True` |
| CG-06 | Proposal §4 Article 59 tagging | Safety-topic question carries compliance metadata | Chunk flagged `is_safety_section = True` | Every question generated from that chunk has a corresponding entry in `safety_compliance_tags` with `article == "労働安全衛生法第59条"` and `compliant is True` |
| CG-07 | PostProcessNode S-3 | Output blocked when generated question text contains PII-shaped content | Question text containing an email address or JP phone-number pattern | `RuntimeError` raised by `_extra_security_gate_output()`; `__call__()` returns `status = error` |

## Business Logic Tests

| TC-ID | Test | Input | Expected Result | Result |
|-------|------|-------|----------------|--------|
| BL-01 | `chunk_document()` splits on SOP section headings | Text with `##`/numbered-heading structure (手順 / 禁止事項 sections) | Returns one chunk per heading-bounded section, in order | Pass |
| BL-02 | `chunk_document()` fallback for unstructured text | Plain text with no heading markers | Returns a single chunk containing the full stripped text | Pass |
| BL-03 | `PreProcessNode` rejects empty document | `user_input = ""` | `status = error`; `error_log` non-empty | Pass |
| BL-04 | `PreProcessNode` rejects invalid `difficulty_target` | `input_context = {"difficulty_target": "impossible"}` | `status = error` | Pass |
| BL-05 | `MainNode` success path with `FakeLLM` | Valid chunks + safety_flags + question_count | `status = success`; `raw_questions` length > 0 | Pass |
| BL-06 | `MainNode` error when LLM returns unparseable output for every chunk | `FakeLLM` returns non-JSON string | `status = error`; `error_log` mentions no usable questions | Pass |
| BL-07 | `PostProcessNode` assembles valid JSON schema | Valid `raw_questions`/`raw_answers`/`difficulty_tags` | `formatted_output` contains all 4 required top-level keys | Pass |
| BL-08 | `PostProcessNode` rejects incomplete question records | `raw_questions` entry missing `source_chunk_ref` | `status = error`; `error_log` names the missing field | Pass |

## Test Execution Summary
- Execution date: 2026-07-06 (Turn-1 fixes: 2026-07-06)
- Total tests: 11 TC + 6 PB + 7 CG + 8 BL = 32 (doc-level item count); 37 pytest cases executed (some PB items are covered by more than one test function — e.g. PB-6 spans `test_pb_invoke_order.py` + `test_pb04_s1_trust_gate.py`)
- Pass: 37 / Fail: 0 / Skip: 0 (TC-04, PB-3 marked N/A with rationale, not skipped)
- Coverage: All 3 nodes have ≥1 success-path and ≥1 error-path unit test (how-to/write-tests.md requirement)
- Review follow-up: the S-1 trust level finding was fixed; the S-1-gate-untested-via-`__call__()` finding and the msgpack-round-trip finding were addressed by `test_pb04_s1_trust_gate.py` and `test_pb05_msgpack_roundtrip.py`
