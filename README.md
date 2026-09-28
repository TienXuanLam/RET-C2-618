# RET-C2-618 — RetailStaffSOPQuizGeneratorAgent

> **Category**: Cat 2 (orchestrates multiple steps to accomplish a specific use case)
> **Industry**: RET
> **Inherits**: ToolCallingAgent (Level 2)
> **Status**: Draft

## Overview

Generates a compliance-tagged quiz from a retail SOP / policy document. Accepts
document text plus invocation parameters (question count, format mix, difficulty,
locale), chunks the document by section boundaries, detects safety-relevant
sections (危険 / 安全 / 禁止 / 取扱注意 / 保護具), and dispatches to an LLM-driven
ToolCallingAgent that produces MCQ / short-answer / T-F questions with answer
keys and difficulty tags. Safety-topic questions are flagged with 労働安全衛生法
Article 59 compliance metadata. Output is a structured JSON payload
(`questions[]`, `answer_key[]`, `difficulty[]`, `safety_compliance_tags[]`)
intended for retail HR onboarding/recertification pipelines.

## Why This Template Exists

This template is **one production unit of the Agent 1000 line** — not a standalone
deliverable. The project goal is to make us *capable of producing* 1,000+ templates
per FY26 September capacity. That capability is what unlocks AGENTIC STAR as the
global de facto platform for enterprise agent development.

Of every design decision in this template, ask:

> "Does this make the next template faster, or only this one better?"

If your answer is the latter, reconsider — generalize at Level 2, or refactor the
pattern. A template that is technically beautiful but cannot be replicated quickly
across industries fails the mission. See the project charter for the three-layer
vision and full purpose context.

## Requirements

- Python 3.11+
- An `ANTHROPIC_API_KEY` secret for LLM-backed quiz generation

### Behaviour without the platform

Without `ANTHROPIC_API_KEY` configured, the standalone server still boots
(`_llm` degrades to `None`), but every invocation returns `status=error`
("LLM produced no usable questions") since no questions can be generated —
there is no deterministic fallback path for this template.

## Quick Start

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,anthropic]"
python -m pytest tests/ -v
```

## Project Structure

```
config/
  agent.yaml          # AgentRegistry manifest
  config.yaml         # runtime parameters
deploy/
  invoke_payload.json # sample /invoke payload
  local-stg.yml       # local STG-equivalent deploy config
src/
  api/server.py       # standalone HTTP entry point
  graph/graph.py       # AgentBaseGraph wiring
  nodes/               # pre_process / main / post_process
  schemas/state.py     # flat TypedDict state
  services/            # pure domain logic (chunking, prompting, assembly)
tests/
  unit/                # per-node unit tests
  proof_of_boundary/   # framework-contract boundary tests
docs/
  02_design.md         # design specification
  03_test_spec.md      # test specification
cli.py                 # Marketplace Pod entrypoint
```

## Customising

- `config/config.yaml`: `max_retry`, `memory_enabled`, `timeout_s`.
- `input_context.safety_keywords`: extend the statutory baseline safety-topic
  keyword list per invocation without a code change.
- `config/agent.yaml`'s `requires.secrets`/`requires.extras`: adjust if the
  LLM provider changes.

## License

MIT — see [LICENSE](LICENSE).

## Status of this repository

This is a template under active development within the Agent 1000 line. It is
provided as-is, with no warranty, and may change without notice.
