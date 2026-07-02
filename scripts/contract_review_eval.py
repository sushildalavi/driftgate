from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.runtime.contract_review import (
    ContractReviewEvidence,
    DisabledReviewProvider,
    FakeReviewProvider,
    ReviewEvidenceItem,
    evaluate_contract_review_cases,
)


def _base_evidence(**overrides: Any) -> ContractReviewEvidence:
    evidence = {
        "endpoint_id": "endpoint-1",
        "endpoint_name": "shop POST /webhooks/shop",
        "namespace": "gateway",
        "service_name": "shop",
        "http_method": "POST",
        "route_path": "/webhooks/shop",
        "current_version": 3,
        "schema_diffs": [],
        "payload_snapshots": [],
        "validation_failures": [],
        "dlq_entries": [],
        "delivery_attempts": [],
        "subscriptions": [],
        "drift_violations": [],
        "notes": [],
        "insufficient_evidence": False,
    }
    evidence.update(overrides)
    return ContractReviewEvidence.model_validate(evidence)


def default_cases() -> list[dict[str, Any]]:
    compatible = _base_evidence(
        payload_snapshots=[
            ReviewEvidenceItem(
                citation="snapshot:1",
                kind="payload_snapshot",
                summary="safe payload snapshot",
                details={"classification": "SAFE"},
            )
        ]
    ).model_dump()
    risky = _base_evidence(
        schema_diffs=[
            ReviewEvidenceItem(
                citation="schema-diff:1",
                kind="schema_diff",
                summary="nullable change on `score`",
                details={"change_type": "nullable_change", "path": "score"},
            )
        ]
    ).model_dump()
    breaking = _base_evidence(
        schema_diffs=[
            ReviewEvidenceItem(
                citation="schema-diff:1",
                kind="schema_diff",
                summary="removed required field `price`",
                details={"change_type": "removed_required_field", "path": "price"},
            )
        ]
    ).model_dump()
    enum_removal = _base_evidence(
        schema_diffs=[
            ReviewEvidenceItem(
                citation="schema-diff:1",
                kind="schema_diff",
                summary="enum contraction on `status`",
                details={"change_type": "enum_contraction", "path": "status"},
            )
        ]
    ).model_dump()
    type_change = _base_evidence(
        schema_diffs=[
            ReviewEvidenceItem(
                citation="schema-diff:1",
                kind="schema_diff",
                summary="type changed from integer to string for `quantity`",
                details={"change_type": "type_changed", "path": "quantity"},
            )
        ]
    ).model_dump()
    insufficient = _base_evidence(insufficient_evidence=True, notes=["too sparse"]).model_dump()
    return [
        {
            "name": "compatible",
            "expected_severity": "compatible",
            "evidence": compatible,
            "evidence_summary": "safe payload snapshot",
            "consumer_impact": "No active consumers",
        },
        {
            "name": "risky",
            "expected_severity": "risky",
            "evidence": risky,
            "evidence_summary": "nullable change on score",
            "consumer_impact": "1 active consumer",
        },
        {
            "name": "breaking_field_removal",
            "expected_severity": "breaking",
            "evidence": breaking,
            "evidence_summary": "removed required field",
            "consumer_impact": "2 active consumers",
        },
        {
            "name": "enum_removal",
            "expected_severity": "breaking",
            "evidence": enum_removal,
            "evidence_summary": "enum contraction",
            "consumer_impact": "1 active consumer",
        },
        {
            "name": "type_change",
            "expected_severity": "breaking",
            "evidence": type_change,
            "evidence_summary": "type change",
            "consumer_impact": "1 active consumer",
        },
        {
            "name": "insufficient_evidence",
            "expected_severity": "risky",
            "evidence": insufficient,
            "evidence_summary": "no evidence available",
            "consumer_impact": "No consumers",
        },
    ]


def load_cases(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return default_cases()
    return json.loads(path.read_text(encoding="utf-8"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate DriftGate contract-review cases.")
    parser.add_argument("--cases", type=Path, help="Optional JSON file of evaluation cases.")
    parser.add_argument("--provider", choices=["disabled", "fake"], default="disabled")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON output.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    provider = DisabledReviewProvider() if args.provider == "disabled" else FakeReviewProvider()
    metrics = evaluate_contract_review_cases(load_cases(args.cases), provider=provider)
    if args.json:
        print(json.dumps(metrics, indent=2, sort_keys=True))
    else:
        print("DriftGate contract-review evaluation")
        for key, value in metrics.items():
            print(f"{key}: {value}")


if __name__ == "__main__":
    main()
