# Agentic Contract Review

DriftGate now treats contract review as a grounded AI workflow, not a thin wrapper around schema diffs.

## Workflow

1. Evidence bundle collection
2. Schema diff citation synthesis
3. Payload and validation citation synthesis
4. DLQ and delivery-attempt citation synthesis
5. Deterministic heuristic review
6. Optional OpenAI, Gemini, or Ollama review
7. Strict schema validation and grounding checks
8. Document-store persistence of the final review artifact

## Output

- decision
- severity
- confidence
- evidence citations
- impacted consumers
- severity explanation
- risk summary
- migration note
- rollout action
- recommended fixes
- review comment markdown

## Guardrails

- The heuristic reviewer remains the default.
- External model providers are optional and must be enabled explicitly or via keys.
- Model output is rejected when the response schema fails validation.
- Unsupported claims are rejected if they are not grounded in evidence citations.
- The final review artifact is stored in the document store for auditability.
