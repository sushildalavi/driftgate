from __future__ import annotations

import httpx
import pytest

from app.runtime.contract_review import (
    ContractReviewEvidence,
    ContractReviewOutcome,
    DisabledReviewProvider,
    FakeReviewProvider,
    OllamaReviewProvider,
    ReviewDecision,
    ReviewEvidenceItem,
    ReviewSeverity,
    evaluate_contract_review_cases,
)


def _base_evidence(**overrides):
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


@pytest.mark.asyncio
async def test_fake_provider_success() -> None:
    expected = ContractReviewOutcome(
        decision=ReviewDecision.APPROVE,
        severity=ReviewSeverity.COMPATIBLE,
        summary="Compatible",
        consumer_impact="No active consumers",
        evidence=["[snapshot:1] safe snapshot"],
        recommended_fixes=[],
        migration_note="No migration required.",
        review_comment="ok",
        confidence=0.97,
        insufficient_evidence=False,
    )
    provider = FakeReviewProvider(outcome=expected)
    review = await provider.generate(
        evidence=_base_evidence(
            payload_snapshots=[
                ReviewEvidenceItem(
                    citation="snapshot:1",
                    kind="payload_snapshot",
                    summary="safe snapshot",
                    details={"classification": "SAFE"},
                )
            ]
        ),
        evidence_summary="safe snapshot",
        consumer_impact="No active consumers",
    )
    assert review.model_dump() == expected.model_dump()


@pytest.mark.asyncio
async def test_invalid_model_json_falls_back_to_heuristic(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _bad_call(*_args, **_kwargs):
        raise ValueError("invalid json")

    provider = OllamaReviewProvider(
        base_url="http://localhost:11434",
        model_name="qwen2.5-coder:7b",
        fallback_model_name=None,
        timeout_seconds=1,
    )
    monkeypatch.setattr(provider, "_call_model", _bad_call)

    review = await provider.generate(
        evidence=_base_evidence(
            schema_diffs=[
                ReviewEvidenceItem(
                    citation="schema-diff:1",
                    kind="schema_diff",
                    summary="removed required field `price`",
                    details={"change_type": "removed_required_field", "path": "price"},
                )
            ]
        ),
        evidence_summary="removed required field",
        consumer_impact="1 active consumer",
    )

    assert review.insufficient_evidence is False
    assert review.decision is ReviewDecision.BLOCK
    assert review.severity is ReviewSeverity.BREAKING


@pytest.mark.asyncio
async def test_timeout_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _timeout(*_args, **_kwargs):
        raise httpx.TimeoutException("timeout")

    provider = OllamaReviewProvider(
        base_url="http://localhost:11434",
        model_name="qwen2.5-coder:7b",
        fallback_model_name="llama3.1:8b",
        timeout_seconds=1,
    )
    monkeypatch.setattr(provider, "_call_model", _timeout)

    review = await provider.generate(
        evidence=_base_evidence(
            payload_snapshots=[
                ReviewEvidenceItem(
                    citation="snapshot:1",
                    kind="payload_snapshot",
                    summary="safe snapshot",
                    details={"classification": "SAFE"},
                )
            ]
        ),
        evidence_summary="safe snapshot",
        consumer_impact="No active consumers",
    )

    assert review.decision is ReviewDecision.APPROVE
    assert review.severity is ReviewSeverity.COMPATIBLE


@pytest.mark.asyncio
async def test_insufficient_evidence_review() -> None:
    provider = DisabledReviewProvider()
    review = await provider.generate(
        evidence=_base_evidence(insufficient_evidence=True, notes=["too sparse"]),
        evidence_summary="No evidence available",
        consumer_impact="No consumers",
    )
    assert review.insufficient_evidence is True
    assert review.decision is ReviewDecision.BLOCK
    assert review.severity is ReviewSeverity.RISKY


@pytest.mark.asyncio
async def test_breaking_review() -> None:
    provider = DisabledReviewProvider()
    review = await provider.generate(
        evidence=_base_evidence(
            schema_diffs=[
                ReviewEvidenceItem(
                    citation="schema-diff:1",
                    kind="schema_diff",
                    summary="removed required field `price`",
                    details={"change_type": "removed_required_field", "path": "price"},
                )
            ]
        ),
        evidence_summary="removed required field",
        consumer_impact="2 active consumers",
    )
    assert review.decision is ReviewDecision.BLOCK
    assert review.severity is ReviewSeverity.BREAKING
    assert review.evidence == ["[schema-diff:1] removed required field `price`"]


@pytest.mark.asyncio
async def test_compatible_review() -> None:
    provider = DisabledReviewProvider()
    review = await provider.generate(
        evidence=_base_evidence(
            payload_snapshots=[
                ReviewEvidenceItem(
                    citation="snapshot:1",
                    kind="payload_snapshot",
                    summary="safe payload snapshot",
                    details={"classification": "SAFE"},
                )
            ]
        ),
        evidence_summary="safe payload snapshot",
        consumer_impact="No active consumers",
    )
    assert review.decision is ReviewDecision.APPROVE
    assert review.severity is ReviewSeverity.COMPATIBLE
    assert review.evidence == ["[snapshot:1] safe payload snapshot"]


@pytest.mark.asyncio
async def test_evidence_grounding() -> None:
    provider = DisabledReviewProvider()
    review = await provider.generate(
        evidence=_base_evidence(
            schema_diffs=[
                ReviewEvidenceItem(
                    citation="schema-diff:1",
                    kind="schema_diff",
                    summary="enum contraction on `status`",
                    details={"change_type": "enum_contraction", "path": "status"},
                )
            ]
        ),
        evidence_summary="enum contraction",
        consumer_impact="1 active consumer",
    )
    assert review.review_comment
    assert all(item.startswith("[") for item in review.evidence)


def test_evaluation_harness_scores_cases() -> None:
    cases = [
        {
            "evidence": _base_evidence(
                payload_snapshots=[
                    ReviewEvidenceItem(
                        citation="snapshot:1",
                        kind="payload_snapshot",
                        summary="safe payload snapshot",
                        details={"classification": "SAFE"},
                    )
                ]
            ).model_dump(),
            "expected_severity": "compatible",
            "evidence_summary": "safe payload snapshot",
            "consumer_impact": "No active consumers",
        },
        {
            "evidence": _base_evidence(
                schema_diffs=[
                    ReviewEvidenceItem(
                        citation="schema-diff:1",
                        kind="schema_diff",
                        summary="removed required field `price`",
                        details={"change_type": "removed_required_field", "path": "price"},
                    )
                ]
            ).model_dump(),
            "expected_severity": "breaking",
            "evidence_summary": "removed required field",
            "consumer_impact": "2 active consumers",
        },
        {
            "evidence": _base_evidence(insufficient_evidence=True, notes=["too sparse"]).model_dump(),
            "expected_severity": "risky",
            "evidence_summary": "No evidence available",
            "consumer_impact": "No consumers",
        },
    ]

    metrics = evaluate_contract_review_cases(cases, provider=DisabledReviewProvider())

    assert metrics["total_cases"] == 3
    assert metrics["schema_valid_output_rate"] == pytest.approx(1.0)
    assert metrics["correct_severity_rate"] == pytest.approx(1.0)
    assert metrics["evidence_coverage_rate"] == pytest.approx(2 / 3)
    assert metrics["average_generation_latency_ms"] >= 0
    assert metrics["insufficient_evidence_rate"] == pytest.approx(1 / 3)
