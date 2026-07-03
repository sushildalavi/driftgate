from __future__ import annotations

import argparse
import json
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_schema(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        if "components" in payload and isinstance(payload["components"], dict):
            schemas = payload["components"].get("schemas")
            if isinstance(schemas, dict):
                return schemas
        if "schema" in payload and isinstance(payload["schema"], dict):
            return payload["schema"]
    return payload if isinstance(payload, dict) else {}


def _field_type(field_schema: Any) -> str:
    if isinstance(field_schema, dict):
        value = field_schema.get("type")
        if isinstance(value, str):
            return value
    return ""


def diff_openapi_documents(old_payload: Any, new_payload: Any) -> dict[str, Any]:
    old_schemas = _extract_schema(old_payload)
    new_schemas = _extract_schema(new_payload)

    breaking_changes: list[str] = []
    non_breaking_changes: list[str] = []

    old_names = set(old_schemas) if isinstance(old_schemas, dict) else set()
    new_names = set(new_schemas) if isinstance(new_schemas, dict) else set()

    for schema_name in sorted(old_names - new_names):
        breaking_changes.append(f"schema removed: {schema_name}")
    for schema_name in sorted(new_names - old_names):
        non_breaking_changes.append(f"schema added: {schema_name}")

    for schema_name in sorted(old_names & new_names):
        old_schema = old_schemas[schema_name]
        new_schema = new_schemas[schema_name]
        old_props = old_schema.get("properties", {}) if isinstance(old_schema, dict) else {}
        new_props = new_schema.get("properties", {}) if isinstance(new_schema, dict) else {}
        old_required = set(old_schema.get("required", []) or []) if isinstance(old_schema, dict) else set()
        new_required = set(new_schema.get("required", []) or []) if isinstance(new_schema, dict) else set()

        for field in sorted(set(old_props) - set(new_props)):
            breaking_changes.append(f"{schema_name}.{field} removed")
        for field in sorted(set(new_props) - set(old_props)):
            if field in new_required:
                breaking_changes.append(f"{schema_name}.{field} added as required")
            else:
                non_breaking_changes.append(f"{schema_name}.{field} added as optional")

        for field in sorted(set(old_props) & set(new_props)):
            old_type = _field_type(old_props[field])
            new_type = _field_type(new_props[field])
            if old_type and new_type and old_type != new_type:
                breaking_changes.append(f"{schema_name}.{field} type {old_type} -> {new_type}")

        for field in sorted(new_required - old_required):
            breaking_changes.append(f"{schema_name}.{field} became required")
        for field in sorted(old_required - new_required):
            non_breaking_changes.append(f"{schema_name}.{field} no longer required")

    breaking = bool(breaking_changes)
    return {
        "breaking": breaking,
        "breaking_changes": breaking_changes,
        "non_breaking_changes": non_breaking_changes,
    }


@dataclass(frozen=True)
class TraceStep:
    step_name: str
    input_summary: str
    tool_name: str | None
    tool_args_summary: str | None
    output_summary: str
    latency_ms: float | None
    status: str
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _record_step(
    trace: list[TraceStep],
    step_name: str,
    input_summary: str,
    output_summary: str,
    *,
    tool_name: str | None = None,
    tool_args_summary: str | None = None,
    status: str = "ok",
    error: str | None = None,
    latency_ms: float | None = None,
) -> None:
    trace.append(
        TraceStep(
            step_name=step_name,
            input_summary=input_summary,
            tool_name=tool_name,
            tool_args_summary=tool_args_summary,
            output_summary=output_summary,
            latency_ms=latency_ms,
            status=status,
            error=error,
        )
    )


def build_review(old_payload: Any, new_payload: Any) -> dict[str, Any]:
    run_id = uuid.uuid4().hex
    trace: list[TraceStep] = []

    t0 = time.perf_counter()
    diff = diff_openapi_documents(old_payload, new_payload)
    _record_step(
        trace,
        "OpenAPI Diff Agent",
        input_summary=f"old={sorted(_extract_schema(old_payload).keys())}, new={sorted(_extract_schema(new_payload).keys())}",
        output_summary=f"{len(diff['breaking_changes'])} breaking, {len(diff['non_breaking_changes'])} non-breaking",
        tool_name="diff_openapi_documents",
        tool_args_summary=f"run_id={run_id}",
        latency_ms=round((time.perf_counter() - t0) * 1000, 2),
    )

    t1 = time.perf_counter()
    risk_level = "high" if diff["breaking"] else "low"
    _record_step(
        trace,
        "Breaking Change Classifier",
        input_summary=f"breaking={len(diff['breaking_changes'])}",
        output_summary=f"risk_level={risk_level}",
        tool_name="classify_review_risk",
        tool_args_summary=None,
        latency_ms=round((time.perf_counter() - t1) * 1000, 2),
    )

    t2 = time.perf_counter()
    if diff["breaking_changes"]:
        suggested_migration = "Update consumers for the listed breaking changes before merging."
        ci_decision = "fail"
    else:
        suggested_migration = "No migration required for the documented changes."
        ci_decision = "pass"
    _record_step(
        trace,
        "Migration Suggestion Agent",
        input_summary=f"{len(diff['breaking_changes'])} breaking change(s)",
        output_summary=suggested_migration,
        tool_name="suggest_migration",
        tool_args_summary=None,
        latency_ms=round((time.perf_counter() - t2) * 1000, 2),
    )

    t3 = time.perf_counter()
    _record_step(
        trace,
        "CI Gate Agent",
        input_summary=f"risk_level={risk_level}",
        output_summary=f"ci_decision={ci_decision}",
        tool_name="ci_gate",
        tool_args_summary=None,
        latency_ms=round((time.perf_counter() - t3) * 1000, 2),
    )

    breaking_lines = [f"- {item}" for item in diff["breaking_changes"]] or ["- None"]
    non_breaking_lines = [f"- {item}" for item in diff["non_breaking_changes"]] or ["- None"]
    pr_comment = "\n".join(
        [
            "## DRIFTGATE Contract Review",
            f"- CI decision: {ci_decision}",
            f"- Risk level: {risk_level}",
            "",
            "### Breaking changes",
            *breaking_lines,
            "",
            "### Non-breaking changes",
            *non_breaking_lines,
            "",
            f"### Suggested migration\n{suggested_migration}",
        ]
    )

    t4 = time.perf_counter()
    _record_step(
        trace,
        "PR Comment Generator",
        input_summary=f"decision={ci_decision}",
        output_summary="PR comment generated",
        tool_name="generate_pr_comment",
        tool_args_summary=None,
        latency_ms=round((time.perf_counter() - t4) * 1000, 2),
    )

    return {
        "breaking_changes": diff["breaking_changes"],
        "non_breaking_changes": diff["non_breaking_changes"],
        "risk_level": risk_level,
        "suggested_migration": suggested_migration,
        "ci_decision": ci_decision,
        "pr_comment_markdown": pr_comment,
        "trace": [step.to_dict() for step in trace],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the local DRIFTGATE contract review agent.")
    parser.add_argument("--old", required=True)
    parser.add_argument("--new", required=True)
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    review = build_review(_load_json(Path(args.old)), _load_json(Path(args.new)))
    if args.json:
        print(json.dumps(review, indent=2, sort_keys=True))
    else:
        print(review["pr_comment_markdown"])


if __name__ == "__main__":
    main()
