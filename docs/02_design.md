# Template Design Specification

## Position in AgentCore Architecture

- **Agent Class**: RetailStaffSOPQuizGeneratorAgent
- **L1 Base**: AgentBaseGraph
- **Three-Layer Separation**:
  - State: flat TypedDict composition (no Pydantic — msgpack incompatible)
  - Node: L1 inheritance (Template Method: `execute(self, state: dict) -> dict` override only)
  - Graph: composition (`register_nodes()` for node substitution)

> **Node mapping note:** The proposal's 3-step pipeline (PreProcessNode →
> MainNode/ToolCallingAgent → OutputNode) maps directly onto `AgentBaseGraph`'s
> three fixed domain slots — `pre_process`, `main`, `post_process`. No step
> requires wrapping in a `GraphNode` subgraph; all three are real `FunctionNode`
> instances registered directly in `register_nodes()`.

## Architecture Overview

### Node Configuration

| Node | Responsibility | Input State | Output State | Inherits/Overrides |
|------|---------------|-------------|--------------|-------------------|
| initialize | Sets `schema_version`, `session_id`, `trust_level` | `input_context` | `session_id`, `correlation_id`, `caller_trust_level` | InitializeNode (default) |
| pre_process | S-2 input validation (size/type); chunk SOP by section boundary; detect safety-topic sections by keyword | `user_input` (document text), `input_context` (question_count, format_mix, difficulty_target, locale) | `chunks`, `safety_flags`, `status` | `FunctionNode` |
| main | Allocate question count per chunk (safety sections ≥ 1); LLM-driven MCQ/SA/T-F generation per chunk; produce answer key, difficulty tag, Article 59 tag for safety chunks | `chunks`, `safety_flags`, `input_context` | `raw_questions`, `raw_answers`, `difficulty_tags`, `safety_compliance_tags`, `status` | `FunctionNode` (ToolCallingAgent pattern) |
| post_process | S-3 output sanitization (PII check on generated questions); assemble + validate structured JSON schema | `raw_questions`, `raw_answers`, `difficulty_tags`, `safety_compliance_tags` | `formatted_output`, `status` | `FunctionNode` |
| finalize | Builds `response_metadata`, `total_time_ms` | `formatted_output` | (response envelope) | FinalizeNode (default) |

### Data Flow

```
START → initialize → pre_process → main → post_process → finalize → END
```

- `main` returns `status=error` on any hard failure (e.g. zero usable
  questions after grounding validation) — routes to `finalize` directly.
- `main` never returns `AgentStatus.RETRY` — there is no partial/soft-failure
  signal distinct from "produced no usable questions" for this template, so
  `max_retry` (`config/config.yaml`) is declared but has no reachable retry
  path in the current implementation.

### State Definition

| Field | Type | Purpose | Required |
|-------|------|---------|----------|
| `question_count` | `int` | Caller-requested total question count (read from `input_context` in `pre_process`, copied into state for `main`) | Yes |
| `format_mix` | `dict` (JSON-serializable: `{"mcq": int, "short_answer": int, "tf": int}`) | Caller-requested format allocation | Yes |
| `difficulty_target` | `str` | `"easy" \| "medium" \| "hard" \| "mixed"` | Yes |
| `locale` | `str` | `"ja" \| "en"`, default `"ja"` | Yes |
| `chunks` | `list[dict]` | Section-bounded document chunks, each `{"chunk_id": int, "text": str, "is_safety_section": bool}` | Set by `pre_process` |
| `safety_flags` | `list[bool]` | Parallel array to `chunks` — `True` where safety keywords matched | Set by `pre_process` |
| `raw_questions` | `list[dict]` | Generated questions, each `{"question_id": int, "chunk_id": int, "format": str, "text": str, "options": list[str] \| None, "source_chunk_ref": int}` | Set by `main` |
| `raw_answers` | `list[dict]` | Answer key, each `{"question_id": int, "answer": str}` | Set by `main` |
| `difficulty_tags` | `list[dict]` | Each `{"question_id": int, "difficulty": str}` | Set by `main` |
| `safety_compliance_tags` | `list[dict]` | Each `{"question_id": int, "article": "労働安全衛生法第59条", "compliant": bool}`; empty list + `no_safety_sections_detected: true` flag (carried in `formatted_output`) when no safety section was found | Set by `main` |
| `formatted_output` | `dict` | Final assembled JSON payload (`questions`, `answer_key`, `difficulty`, `safety_compliance_tags`) — this is the field `post_process` writes and `finalize` reads | Set by `post_process` |

All list/dict fields above are plain (not `Annotated[..., operator.add]`) —
each node fully replaces its own output fields; there is no accumulator
pattern needed since `pre_process` → `main` → `post_process` is a strict
linear handoff, not a fan-in.

> **`total=False` (Architect review ARCH-0918-20260706, finding
> RET-C2-618-ARCH-R1-01):** `State` is declared `class State(AgentState,
> total=False)`. Every domain field above is populated by a specific node
> partway through the pipeline (not all present from `initialize()`), so a
> checkpoint restored mid-pipeline legitimately has some of these fields
> absent — e.g. a checkpoint taken right after `pre_process` has `chunks`/
> `safety_flags` but not yet `raw_questions`/`formatted_output`. The
> "Required" column above describes when each field is populated in the
> normal forward flow, not a hard runtime requirement enforced by the
> TypedDict declaration.

**State Constraints (mandatory):**
- Flat TypedDict only (primitives + JSON-serializable types)
- No JWT, API keys, credentials in State (checkpoint DB leakage)
- InvocationContext via `config["configurable"]` only (not in State)
- No Pydantic models, dataclass, arbitrary Python objects (msgpack incompatible)
- No PII expected in SOP source documents; `raw_questions`/`formatted_output`
  are re-checked for PII by the S-3 hook in `post_process` as a
  belt-and-suspenders measure (see Risk #1 in proposal §11 — LLM
  hallucination risk, not PII risk, is the primary concern for this field)

## Framework Utilization

### Shared Components Used
- [x] InvocationContext (correlation_id, session_id; caller-supplied
      `question_count`/`format_mix`/`difficulty_target`/`locale` read from
      `input_context` in `pre_process`)
- [ ] ConnectionPolicy (retry/timeout strategy) — not needed; the LLM call in
      `main` is single-pass with no retry routing (see Data Flow above)
- [x] SecurityViolationError — raised if `pre_process` receives a caller
      below `required_trust_level`
- [x] S-2: `_extra_security_gate_input()` on `pre_process` —
      document size guard (≤ 50k tokens) and content-type guard (reject
      non-text/Markdown/PDF-text-layer input); rejects by setting
      `state["status"] = AgentStatus.ERROR.value`, does not raise
- [x] S-3: `_extra_security_gate_output()` on `post_process` —
      re-scan generated `questions[]`/`answer_key[]` text for PII patterns
      (preservation/filtering hybrid: block if PII found, since no PII is
      expected in SOP-derived content and any match indicates a data leak,
      not a false positive to preserve)
- [x] S-4: `emit_trace_event()` — at least one domain-specific event inside
      each `execute()`:
      - `pre_process`: `sop_chunked` `{chunk_count, safety_section_count}`
      - `main`: `llm_call` `{model, tokens, question_count_generated}`
      - `post_process`: `output_assembled` `{question_count, safety_tag_count}`

> **S-2/S-3 gate behaviour by node type (ADR-017):**
> - `FunctionNode` subclass → framework `@final` gate always runs automatically;
>   extend via `_extra_security_gate_input()` / `_extra_security_gate_output()` only
> - `GraphNode` / `RemoteAgentNode` → deliberate no-op (upstream or remote node's gate already applied)
> - Custom `BaseNode` subclass → must implement `_security_gate_input()` and
>   `_security_gate_output()` directly (`@abstractmethod` — omission raises `TypeError` at instantiation)

All three domain nodes in this template are plain `FunctionNode` subclasses —
no `GraphNode`/`RemoteAgentNode` composition is used, so no no-op gate
override applies.

### Composition Pattern

- **Pattern**: Standalone (all three domain nodes are direct `FunctionNode`
  instances registered in `register_nodes()`; no subgraph, no remote agent
  composition)
- **Composition target**: N/A — this template is itself intended to be
  invoked as a sub-agent step (via `RemoteAgentNode` or direct HTTP call) by
  a parent Cat 2 onboarding orchestrator, but does not itself compose any
  child agent
- **Error propagation strategy**: propagate — `main`'s hard failures
  (`status=error`, e.g. zero usable questions after grounding validation)
  route straight to `finalize` and surface in `error_log`; there is no
  soft-failure retry path (see Data Flow above)

## Import Isolation Confirmation
- [x] Template does not import agenticstar-platform SDK (Level 0)
- [x] Import targets: framework/ and shared/ only (no agents/base/ required)

## Design Decision Record

| Decision | Option A | Option B | Chosen | Rationale |
|----------|----------|----------|--------|-----------|
| L1 base type | AgentBaseGraph | AutonomousBaseGraph | **AgentBaseGraph** | Fixed 3-step pipeline with no self-directed think→act loop; termination is pipeline-determined, not agent-determined (proposal §4 scope, confirmed Cat 2 in §1) |
| Composition pattern | Standalone FunctionNode pipeline | GraphNode-wrapped subgraph per step | **Standalone** | All 3 proposal steps map 1:1 onto the framework's 3 fixed domain slots (`pre_process`/`main`/`post_process`) — no need for an inner subgraph or step-helper indirection |
| Safety-topic detection | Pure keyword regex only | Regex + embedding similarity supplement | **Regex now; embedding supplement deferred** | Proposal §11 Risk #2 flags regex-only as medium risk for novel phrasing (e.g. "感電注意" vs "電気危険"); `safety_keywords` is exposed as an extensible config parameter so callers can widen coverage without a code change, embedding supplement left as a documented future enhancement, not a v1 blocker |
| Answer-key grounding | Trust LLM output as-is | Require `source_chunk_ref` + substring/semantic match validation in `post_process` | **Require grounding validation** | Proposal §11 Risk #1 (LLM hallucinated answer keys) is the highest-severity risk (🔴 High) — every generated question must carry a `source_chunk_ref`, and `post_process` validates the answer text is extractable from that chunk before assembling final output |
