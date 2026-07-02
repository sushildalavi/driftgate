# Portfolio Proof

## What the project does

DriftGate monitors API drift, infers schema changes, and surfaces runtime guard and dashboard workflows for API reliability.

## Why it is technically impressive

- It combines scheduled monitoring, runtime guardrails, and an Angular dashboard.
- The repo includes simulation and benchmark material.
- The work is directly relevant to platform and API reliability roles.

## Architecture summary

- API samples -> monitor worker -> schema inference -> severity classification -> guard state and dashboard.

## How to run locally

- `docker compose up -d --build`
  - `curl -X POST http://localhost:18080/api/monitor/run-once -H "X-SCHEMAPILOT-ADMIN-SECRET: dev-secret"`

## How to test

- `pytest`
- `npm run build` in `frontend/`
- `docker compose config`

## How to benchmark or evaluate

- Review `docs/BENCHMARKS.md`
- Review `docs/REGRESSION_EVALUATION.md`

## Verified metrics only

- No canonical benchmark summary was extracted in this pass.

## Current limitations

- Benchmark summaries still need machine-readable parsing.
- Contract-check and OpenAPI diff docs are not yet first-class portfolio artifacts.

## Future improvements

- Add OpenAPI diff and contract-check tooling.
- Add SDK examples for Python and JavaScript.
- Add a parsed benchmark summary report from existing k6 artifacts.

## Resume bullets

- Built an API drift monitoring system with scheduled inference and runtime guard behavior.
- Combined schema inference, severity classification, and dashboarding into one reliability workflow.
- Prepared the system for contract checking and benchmark-driven review.

## Verification Log

- `python3 /Users/sushildalavi/Desktop/Github/driftgate/scripts/contract_check.py --old /Users/sushildalavi/Desktop/Github/driftgate/tests/fixtures/openapi_old.json --new /Users/sushildalavi/Desktop/Github/driftgate/tests/fixtures/openapi_new.json` - pass - 2026-06-17 - Correctly flagged a breaking diff and exited nonzero as expected.
- `python3 -m pytest /Users/sushildalavi/Desktop/Github/driftgate/tests/test_openapi_diff.py /Users/sushildalavi/Desktop/Github/driftgate/tests/test_benchmark_summary.py` - pass - 2026-06-17 - Verified diff and benchmark parsers.
