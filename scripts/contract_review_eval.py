from __future__ import annotations

import argparse
import json
import time
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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
    required_field = _base_evidence(
        schema_diffs=[
            ReviewEvidenceItem(
                citation="schema-diff:1",
                kind="schema_diff",
                summary="added required field `currency`",
                details={"change_type": "added_required_field", "path": "currency"},
            )
        ]
    ).model_dump()
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
    removed_optional = _base_evidence(
        schema_diffs=[
            ReviewEvidenceItem(
                citation="schema-diff:1",
                kind="schema_diff",
                summary="removed optional field `nickname`",
                details={"change_type": "removed_optional_field", "path": "nickname"},
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
    malformed_payload = _base_evidence(
        validation_failures=[
            ReviewEvidenceItem(
                citation="validation:1",
                kind="validation_error",
                summary="payload rejected because `price` is missing",
                details={"path": "/track", "error_count": 1},
            )
        ]
    ).model_dump()
    webhook_failure = _base_evidence(
        dlq_entries=[
            ReviewEvidenceItem(
                citation="dlq:1",
                kind="dlq_entry",
                summary="consumer=checkout attempts=5 reason=timeout target=http://checkout/webhook",
                details={"attempt_count": 5, "failure_reason": "timeout"},
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
    sparse = _base_evidence(insufficient_evidence=True, notes=["evidence sparse"]).model_dump()
    conflicting = _base_evidence(
        schema_diffs=[
            ReviewEvidenceItem(
                citation="schema-diff:1",
                kind="schema_diff",
                summary="enum contraction on `status`",
                details={"change_type": "enum_contraction", "path": "status"},
            )
        ],
        payload_snapshots=[
            ReviewEvidenceItem(
                citation="snapshot:1",
                kind="payload_snapshot",
                summary="snapshot still shows the removed enum value",
                details={"classification": "RISKY"},
            )
        ],
    ).model_dump()
    drift_dlq = _base_evidence(
        drift_violations=[
            ReviewEvidenceItem(
                citation="drift-violation:1",
                kind="drift_violation",
                summary="severity=BREAKING fingerprint=abc123 path=price",
                details={"severity": "BREAKING", "path": "price"},
            )
        ]
    ).model_dump()
    additive_safe = _base_evidence(
        payload_snapshots=[
            ReviewEvidenceItem(
                citation="snapshot:1",
                kind="payload_snapshot",
                summary="added optional field `promo_code`",
                details={"classification": "SAFE"},
            )
        ]
    ).model_dump()
    additive_risky = _base_evidence(
        schema_diffs=[
            ReviewEvidenceItem(
                citation="schema-diff:1",
                kind="schema_diff",
                summary="added nested object `billing_address`",
                details={"change_type": "nested_shape_change", "path": "billing_address"},
            )
        ]
    ).model_dump()
    subscription_impact = _base_evidence(
        schema_diffs=[
            ReviewEvidenceItem(
                citation="schema-diff:1",
                kind="schema_diff",
                summary="type changed from integer to string for `quantity`",
                details={"change_type": "type_changed", "path": "quantity"},
            )
        ],
        subscriptions=[
            {
                "id": "sub-1",
                "consumer_id": "billing-service",
                "endpoint_id": "endpoint-1",
                "target_url": "http://billing/webhook",
                "severity_threshold": "RISKY",
                "schema_version": 3,
                "active": True,
            }
        ],
    ).model_dump()
    insufficient = _base_evidence(insufficient_evidence=True, notes=["too sparse"]).model_dump()
    return [
        {
            "name": "added_required_field",
            "expected_severity": "breaking",
            "evidence": required_field,
            "evidence_summary": "added required field currency",
            "consumer_impact": "1 active consumer",
        },
        {
            "name": "compatible",
            "expected_severity": "compatible",
            "evidence": compatible,
            "evidence_summary": "safe payload snapshot",
            "consumer_impact": "No active consumers",
        },
        {
            "name": "removed_optional_field",
            "expected_severity": "compatible",
            "evidence": removed_optional,
            "evidence_summary": "removed optional field nickname",
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
            "name": "malformed_payload",
            "expected_severity": "risky",
            "evidence": malformed_payload,
            "evidence_summary": "payload validation failure",
            "consumer_impact": "1 active consumer",
        },
        {
            "name": "webhook_delivery_failure",
            "expected_severity": "risky",
            "evidence": webhook_failure,
            "evidence_summary": "delivery attempts exhausted",
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
            "name": "sparse_evidence",
            "expected_severity": "risky",
            "evidence": sparse,
            "evidence_summary": "evidence sparse",
            "consumer_impact": "No consumers",
        },
        {
            "name": "conflicting_evidence",
            "expected_severity": "breaking",
            "evidence": conflicting,
            "evidence_summary": "conflicting evidence",
            "consumer_impact": "1 active consumer",
        },
        {
            "name": "dlq_backed_issue",
            "expected_severity": "breaking",
            "evidence": drift_dlq,
            "evidence_summary": "drift violation backed by DLQ",
            "consumer_impact": "1 active consumer",
        },
        {
            "name": "enum_removal",
            "expected_severity": "breaking",
            "evidence": enum_removal,
            "evidence_summary": "enum contraction",
            "consumer_impact": "1 active consumer",
        },
        {
            "name": "safe_additive_change",
            "expected_severity": "compatible",
            "evidence": additive_safe,
            "evidence_summary": "optional field added",
            "consumer_impact": "No active consumers",
        },
        {
            "name": "risky_additive_change",
            "expected_severity": "risky",
            "evidence": additive_risky,
            "evidence_summary": "nested object added",
            "consumer_impact": "1 active consumer",
        },
        {
            "name": "subscription_impact",
            "expected_severity": "breaking",
            "evidence": subscription_impact,
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
    parser = argparse.ArgumentParser(description="Evaluate DRIFTGATE contract-review cases.")
    parser.add_argument("--cases", type=Path, help="Optional JSON file of evaluation cases.")
    parser.add_argument("--provider", choices=["disabled", "fake"], default="disabled")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON output.")
    parser.add_argument("--output-dir", type=Path, help="Optional directory for JSON and Markdown artifacts.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    provider = DisabledReviewProvider() if args.provider == "disabled" else FakeReviewProvider()
    metrics = evaluate_contract_review_cases(load_cases(args.cases), provider=provider)
    if args.output_dir is not None:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        json_path = args.output_dir / f"contract_review_eval_{stamp}.json"
        md_path = args.output_dir / f"contract_review_eval_{stamp}.md"
        json_path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        md_path.write_text(
            "\n".join(
                [
                    "# DRIFTGATE Contract Review Evaluation",
                    "",
                    "| metric | value |",
                    "| --- | --- |",
                    *[f"| {key} | {value} |" for key, value in metrics.items()],
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"wrote {json_path}")
        print(f"wrote {md_path}")
    if args.json:
        print(json.dumps(metrics, indent=2, sort_keys=True))
    else:
        print("DRIFTGATE contract-review evaluation")
        for key, value in metrics.items():
            print(f"{key}: {value}")


if __name__ == "__main__":
    main()
