from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Protocol, TypedDict

import httpx
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.runtime.document_store import DocumentStore
from app.runtime.drift_event_dlq import list_event_dlq
from app.runtime.metrics import (
    CONTRACT_REVIEW_GROUNDING_FAILURE_TOTAL,
    CONTRACT_REVIEW_INSUFFICIENT_EVIDENCE_TOTAL,
    CONTRACT_REVIEW_LATENCY_SECONDS,
    CONTRACT_REVIEW_SCHEMA_VALID_TOTAL,
    CONTRACT_REVIEW_TOTAL,
)
from app.runtime.subscriptions import list_subscriptions


class ReviewDecision(str, Enum):
    APPROVE = "approve"
    NEEDS_CHANGES = "needs_changes"
    BLOCK = "block"


class ReviewSeverity(str, Enum):
    COMPATIBLE = "compatible"
    RISKY = "risky"
    BREAKING = "breaking"


class ContractReviewRequest(BaseModel):
    endpoint_id: str
    evidence_limit: int = Field(default=5, ge=1, le=25)
    review_limit: int = Field(default=10, ge=1, le=25)


class ReviewEvidenceItem(BaseModel):
    citation: str
    kind: str
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)


class ContractReviewEvidence(BaseModel):
    endpoint_id: str
    endpoint_name: str
    namespace: str
    service_name: str
    http_method: str
    route_path: str
    current_version: int | None = None
    schema_diffs: list[ReviewEvidenceItem] = Field(default_factory=list)
    payload_snapshots: list[ReviewEvidenceItem] = Field(default_factory=list)
    validation_failures: list[ReviewEvidenceItem] = Field(default_factory=list)
    dlq_entries: list[ReviewEvidenceItem] = Field(default_factory=list)
    drift_event_dlq_entries: list[ReviewEvidenceItem] = Field(default_factory=list)
    delivery_attempts: list[ReviewEvidenceItem] = Field(default_factory=list)
    subscriptions: list[dict[str, Any]] = Field(default_factory=list)
    drift_violations: list[ReviewEvidenceItem] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    insufficient_evidence: bool = False

    @property
    def citations(self) -> list[str]:
        out: list[str] = []
        for item in (
            self.schema_diffs
            + self.payload_snapshots
            + self.validation_failures
            + self.dlq_entries
            + self.drift_event_dlq_entries
            + self.delivery_attempts
            + self.drift_violations
        ):
            out.append(item.citation)
        return out

    @property
    def evidence_count(self) -> int:
        return len(self.citations)


class ContractReviewOutcome(BaseModel):
    decision: ReviewDecision
    severity: ReviewSeverity
    summary: str = Field(min_length=1)
    consumer_impact: str = Field(min_length=1)
    impacted_consumers: list[str] = Field(default_factory=list)
    severity_explanation: str = Field(default="")
    risk_summary: str = Field(default="")
    rollout_action: str = Field(default="")
    evidence: list[str] = Field(default_factory=list)
    recommended_fixes: list[str] = Field(default_factory=list)
    migration_note: str = Field(min_length=1)
    review_comment: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    insufficient_evidence: bool = False


class ContractReviewRecord(BaseModel):
    review_id: str
    endpoint_id: str
    endpoint_name: str
    provider: str
    model_name: str | None = None
    created_at: str
    latency_seconds: float
    evidence_summary: str
    consumer_impact: str
    context: ContractReviewEvidence
    review: ContractReviewOutcome


class ContractReviewState(TypedDict, total=False):
    request: ContractReviewRequest
    started_at: float
    evidence: ContractReviewEvidence
    evidence_summary: str
    consumer_impact: str
    candidate_review: dict[str, Any]
    review: ContractReviewOutcome
    record: ContractReviewRecord
    provider_name: str
    model_name: str | None
    latency_seconds: float
    errors: list[str]


class ReviewProvider(Protocol):
    provider_name: str
    model_name: str | None

    async def generate(
        self,
        *,
        evidence: ContractReviewEvidence,
        evidence_summary: str,
        consumer_impact: str,
    ) -> ContractReviewOutcome:
        ...


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _truncate(value: Any, limit: int = 240) -> str:
    text_value = json.dumps(value, default=str, ensure_ascii=True) if not isinstance(value, str) else value
    if len(text_value) <= limit:
        return text_value
    return text_value[: limit - 1] + "…"


def _severity_from_evidence(evidence: ContractReviewEvidence) -> ReviewSeverity:
    severity = ReviewSeverity.COMPATIBLE
    for item in evidence.schema_diffs + evidence.drift_violations:
        details = item.details
        item_severity = str(details.get("severity", "")).lower()
        change_type = str(details.get("change_type", "")).lower()
        summary = f"{item.summary} {change_type}".lower()
        if item_severity == ReviewSeverity.BREAKING.value or any(
            token in summary
            for token in (
                "removed required",
                "required field",
                "enum contraction",
                "type changed",
                "nullable field becomes required",
                "removed",
            )
        ):
            return ReviewSeverity.BREAKING
        if item_severity == ReviewSeverity.RISKY.value or any(
            token in summary
            for token in (
                "risky",
                "widening",
                "nullable",
                "added required",
                "nested shape",
            )
        ):
            severity = ReviewSeverity.RISKY
    return severity


def _decision_for_severity(severity: ReviewSeverity, insufficient_evidence: bool) -> ReviewDecision:
    if insufficient_evidence:
        return ReviewDecision.BLOCK
    if severity is ReviewSeverity.BREAKING:
        return ReviewDecision.BLOCK
    if severity is ReviewSeverity.RISKY:
        return ReviewDecision.NEEDS_CHANGES
    return ReviewDecision.APPROVE


def _confidence_for_review(severity: ReviewSeverity, evidence_count: int, insufficient_evidence: bool) -> float:
    if insufficient_evidence:
        return 0.25 if evidence_count else 0.12
    if severity is ReviewSeverity.BREAKING:
        return 0.94 if evidence_count >= 3 else 0.88
    if severity is ReviewSeverity.RISKY:
        return 0.82 if evidence_count >= 2 else 0.74
    return 0.79 if evidence_count >= 2 else 0.68


def _citation_lines(items: list[ReviewEvidenceItem]) -> list[str]:
    return [f"[{item.citation}] {item.summary}" for item in items]


def _impacted_consumers(evidence: ContractReviewEvidence) -> list[str]:
    consumers: list[str] = []
    for subscription in evidence.subscriptions:
        if not subscription.get("active", True):
            continue
        consumer_id = str(subscription.get("consumer_id", "")).strip()
        target_url = str(subscription.get("target_url", "")).strip()
        threshold = str(subscription.get("severity_threshold", "unknown")).strip()
        if not consumer_id and not target_url:
            continue
        label = consumer_id or target_url
        if threshold:
            label = f"{label} (threshold={threshold})"
        consumers.append(label)
    return consumers


def _severity_explanation(severity: ReviewSeverity, evidence: ContractReviewEvidence) -> str:
    if severity is ReviewSeverity.BREAKING:
        return (
            "A breaking review means at least one grounded schema diff or drift violation removes a required field, "
            "narrows an enum, or tightens a type in a way that can break existing consumers."
        )
    if severity is ReviewSeverity.RISKY:
        return (
            "A risky review means the collected evidence points to a compatibility change that may require a rollout "
            "plan, version bump, or consumer communication before release."
        )
    if evidence.insufficient_evidence:
        return "The review is conservative because the evidence bundle is sparse."
    return "No grounded diff, validation failure, DLQ item, or delivery failure suggests consumer impact."


def _risk_summary(severity: ReviewSeverity, evidence: ContractReviewEvidence, impacted_consumers: list[str]) -> str:
    if severity is ReviewSeverity.BREAKING:
        return (
            f"{len(impacted_consumers) or len(evidence.subscriptions)} consumer(s) are likely affected and should not "
            "be cut over until the contract is versioned or a compatibility shim is in place."
        )
    if severity is ReviewSeverity.RISKY:
        return (
            f"{len(impacted_consumers) or len(evidence.subscriptions)} consumer(s) may be exposed to a behavior change; "
            "validate the rollout path and keep the previous shape available."
        )
    return "Current evidence does not show an immediate consumer break, but the review remains tied to the collected artifacts."


def _rollout_action(severity: ReviewSeverity, insufficient_evidence: bool) -> str:
    if insufficient_evidence:
        return "Pause rollout until the review has enough citations to justify a decision."
    if severity is ReviewSeverity.BREAKING:
        return "Block rollout, notify impacted consumers, and ship a versioned compatibility path."
    if severity is ReviewSeverity.RISKY:
        return "Roll out behind a guardrail or staged deployment and monitor the evidence trail closely."
    return "Proceed with rollout and keep the evidence bundle attached to the release record."


def _build_migration_note(severity: ReviewSeverity, evidence: ContractReviewEvidence, consumer_impact: str) -> str:
    if severity is ReviewSeverity.BREAKING:
        return (
            f"Hold the change until consumers covered by {len(evidence.subscriptions)} subscription(s) "
            f"and {consumer_impact.lower()} are updated."
        )
    if severity is ReviewSeverity.RISKY:
        return "Ship behind a compatibility check, communicate the change, and keep the old shape alive during rollout."
    return "No migration work is required for the currently collected evidence."


def _build_recommended_fixes(evidence: ContractReviewEvidence) -> list[str]:
    fixes: list[str] = []
    for item in evidence.schema_diffs + evidence.drift_violations:
        details = item.details
        change_type = str(details.get("change_type", "")).lower()
        path = str(details.get("path", item.summary))
        if "removed required" in change_type or "removed required" in item.summary.lower():
            fixes.append(f"Restore `{path}` or version the contract before rollout.")
        elif "new required" in change_type or "added required" in item.summary.lower():
            fixes.append(f"Make `{path}` optional or supply a backward-compatible default.")
        elif "type" in change_type or "type changed" in item.summary.lower():
            fixes.append(f"Preserve the existing type for `{path}` or add coercion on both sides.")
        elif "enum" in change_type or "enum" in item.summary.lower():
            fixes.append(f"Restore removed enum values for `{path}` or add a migration layer.")
        elif "null" in change_type or "nullable" in item.summary.lower():
            fixes.append(f"Keep `{path}` nullable until all consumers can handle the tightened schema.")
        elif "nested" in change_type or "shape" in item.summary.lower():
            fixes.append(f"Document the nested shape change for `{path}` and update payload examples.")
    return list(dict.fromkeys(fixes))


def _build_review_comment(
    *,
    review: ContractReviewOutcome,
    evidence: ContractReviewEvidence,
    evidence_summary: str,
    consumer_impact: str,
) -> str:
    lines = [
        "## DRIFTGATE Contract Review",
        f"- Decision: `{review.decision.value}`",
        f"- Severity: `{review.severity.value}`",
        f"- Confidence: `{review.confidence:.2f}`",
        "",
        f"### Summary\n{review.summary}",
        "",
        f"### Consumer impact\n{consumer_impact}",
        "",
        f"### Severity explanation\n{review.severity_explanation}",
        "",
        f"### Risk summary\n{review.risk_summary}",
        "",
        f"### Rollout action\n{review.rollout_action}",
        "",
        "### Evidence",
    ]
    if review.evidence:
        lines.extend(f"- {line}" for line in review.evidence)
    else:
        lines.append("- No grounded evidence was cited.")
    if evidence_summary:
        lines.extend(["", f"### Evidence summary\n{evidence_summary}"])
    if review.recommended_fixes:
        lines.extend(["", "### Recommended fixes"])
        lines.extend(f"- {item}" for item in review.recommended_fixes)
    if review.impacted_consumers:
        lines.extend(["", "### Impacted consumers"])
        lines.extend(f"- {consumer}" for consumer in review.impacted_consumers)
    lines.extend(["", f"### Migration note\n{review.migration_note}"])
    return "\n".join(lines)


def _build_heuristic_review(
    *,
    evidence: ContractReviewEvidence,
    evidence_summary: str,
    consumer_impact: str,
    insufficient_reason: str | None = None,
) -> ContractReviewOutcome:
    severity = _severity_from_evidence(evidence)
    insufficient_evidence = evidence.insufficient_evidence or evidence.evidence_count == 0
    model_failed = insufficient_reason is not None and not insufficient_evidence
    decision = _decision_for_severity(severity, insufficient_evidence)
    evidence_items = _citation_lines(
        (evidence.schema_diffs + evidence.payload_snapshots + evidence.validation_failures + evidence.dlq_entries + evidence.delivery_attempts + evidence.drift_violations)[
            : max(1, min(5, evidence.evidence_count))
        ]
    )
    summary = (
        insufficient_reason
        or (
            "No breaking changes were grounded in the collected evidence."
            if severity is ReviewSeverity.COMPATIBLE
            else f"{severity.value.title()} contract changes were grounded in the collected evidence."
        )
    )
    if insufficient_evidence and not insufficient_reason:
        summary = "There is too little supporting evidence to produce a confident contract review."
    if model_failed and insufficient_reason:
        summary = f"{summary} The model failed, so this review was derived directly from grounded evidence."
    review = ContractReviewOutcome(
        decision=decision,
        severity=severity if not insufficient_evidence else ReviewSeverity.RISKY,
        summary=summary,
        consumer_impact=consumer_impact,
        impacted_consumers=_impacted_consumers(evidence),
        severity_explanation=_severity_explanation(severity, evidence),
        risk_summary=_risk_summary(severity, evidence, _impacted_consumers(evidence)),
        rollout_action=_rollout_action(severity, insufficient_evidence),
        evidence=evidence_items,
        recommended_fixes=[] if insufficient_evidence else _build_recommended_fixes(evidence),
        migration_note=_build_migration_note(severity, evidence, consumer_impact),
        review_comment="Draft review",
        confidence=_confidence_for_review(severity, evidence.evidence_count, insufficient_evidence),
        insufficient_evidence=insufficient_evidence,
    )
    review.review_comment = _build_review_comment(
        review=review, evidence=evidence, evidence_summary=evidence_summary, consumer_impact=consumer_impact
    )
    if insufficient_evidence:
        review.review_comment += "\n\n### Note\nInsufficient evidence was returned because the available data was too sparse."
    elif insufficient_reason:
        review.review_comment += f"\n\n### Note\n{insufficient_reason}"
    return review


class DisabledReviewProvider:
    provider_name = "disabled"
    model_name = None

    async def generate(
        self,
        *,
        evidence: ContractReviewEvidence,
        evidence_summary: str,
        consumer_impact: str,
    ) -> ContractReviewOutcome:
        return _build_heuristic_review(
            evidence=evidence,
            evidence_summary=evidence_summary,
            consumer_impact=consumer_impact,
        )


class FakeReviewProvider:
    provider_name = "fake"

    def __init__(
        self,
        outcome: ContractReviewOutcome | None = None,
        *,
        model_name: str | None = "fake",
        outcome_factory: Callable[[ContractReviewEvidence, str, str], ContractReviewOutcome] | None = None,
    ) -> None:
        self.model_name = model_name
        self._outcome = outcome
        self._outcome_factory = outcome_factory

    async def generate(
        self,
        *,
        evidence: ContractReviewEvidence,
        evidence_summary: str,
        consumer_impact: str,
    ) -> ContractReviewOutcome:
        if self._outcome_factory is not None:
            outcome = self._outcome_factory(evidence, evidence_summary, consumer_impact)
            return ContractReviewOutcome.model_validate(outcome)
        if self._outcome is not None:
            return self._outcome.model_copy(deep=True)
        return _build_heuristic_review(
            evidence=evidence,
            evidence_summary=evidence_summary,
            consumer_impact=consumer_impact,
        )


class OllamaReviewProvider:
    provider_name = "ollama"

    def __init__(
        self,
        *,
        base_url: str,
        model_name: str,
        fallback_model_name: str | None,
        timeout_seconds: int,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.fallback_model_name = fallback_model_name
        self.timeout_seconds = timeout_seconds
        self._parser = PydanticOutputParser(pydantic_object=ContractReviewOutcome)
        self._prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are DRIFTGATE's contract review agent. Use only the supplied evidence. "
                    "Return JSON only and never invent facts.",
                ),
                (
                    "human",
                    "Endpoint: {endpoint_name}\n"
                    "Route: {http_method} {route_path}\n"
                    "Diff summary:\n{evidence_summary}\n\n"
                    "Consumer impact:\n{consumer_impact}\n\n"
                    "Evidence JSON:\n{evidence_json}\n\n"
                    "Validation failures:\n{validation_json}\n\n"
                    "DLQ context:\n{dlq_json}\n\n"
                    "{format_instructions}",
                ),
            ]
        )

    async def _call_model(self, model_name: str, evidence: ContractReviewEvidence, evidence_summary: str, consumer_impact: str) -> ContractReviewOutcome:
        prompt = self._prompt.format_messages(
            endpoint_name=evidence.endpoint_name,
            http_method=evidence.http_method,
            route_path=evidence.route_path,
            evidence_summary=evidence_summary,
            consumer_impact=consumer_impact,
            evidence_json=json.dumps(
                [item.model_dump() for item in evidence.schema_diffs + evidence.payload_snapshots + evidence.dlq_entries + evidence.drift_violations],
                ensure_ascii=True,
                indent=2,
                default=str,
            ),
            validation_json=json.dumps(
                [item.model_dump() for item in evidence.validation_failures],
                ensure_ascii=True,
                indent=2,
                default=str,
            ),
            dlq_json=json.dumps(
                [item.model_dump() for item in evidence.dlq_entries + evidence.delivery_attempts],
                ensure_ascii=True,
                indent=2,
                default=str,
            ),
            format_instructions=self._parser.get_format_instructions(),
        )
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": prompt[0].content},
                {"role": "user", "content": prompt[1].content},
            ],
            "stream": False,
            "options": {
                "temperature": 0,
                "num_predict": 1024,
            },
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            res = await client.post(f"{self.base_url}/api/chat", json=payload)
            res.raise_for_status()
            data = res.json()
        content = data.get("message", {}).get("content", "")
        parsed = self._parser.parse(content)
        return ContractReviewOutcome.model_validate(parsed)

    async def generate(
        self,
        *,
        evidence: ContractReviewEvidence,
        evidence_summary: str,
        consumer_impact: str,
    ) -> ContractReviewOutcome:
        try:
            return await self._call_model(self.model_name, evidence, evidence_summary, consumer_impact)
        except Exception:
            if self.fallback_model_name and self.fallback_model_name != self.model_name:
                try:
                    return await self._call_model(self.fallback_model_name, evidence, evidence_summary, consumer_impact)
                except Exception:
                    pass
            return _build_heuristic_review(
                evidence=evidence,
                evidence_summary=evidence_summary,
                consumer_impact=consumer_impact,
                insufficient_reason="Model generation failed; using evidence-only fallback review.",
            )


class OpenAIReviewProvider:
    provider_name = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model_name: str,
        base_url: str,
        timeout_seconds: int,
    ) -> None:
        self.api_key = api_key
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._parser = PydanticOutputParser(pydantic_object=ContractReviewOutcome)
        self._prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are DRIFTGATE's contract review agent. Use only the supplied evidence. "
                    "Return JSON only and never invent facts.",
                ),
                (
                    "human",
                    "Endpoint: {endpoint_name}\n"
                    "Route: {http_method} {route_path}\n"
                    "Diff summary:\n{evidence_summary}\n\n"
                    "Consumer impact:\n{consumer_impact}\n\n"
                    "Evidence JSON:\n{evidence_json}\n\n"
                    "Validation failures:\n{validation_json}\n\n"
                    "DLQ context:\n{dlq_json}\n\n"
                    "{format_instructions}",
                ),
            ]
        )

    async def _call_model(
        self,
        evidence: ContractReviewEvidence,
        evidence_summary: str,
        consumer_impact: str,
    ) -> ContractReviewOutcome:
        prompt = self._prompt.format_messages(
            endpoint_name=evidence.endpoint_name,
            http_method=evidence.http_method,
            route_path=evidence.route_path,
            evidence_summary=evidence_summary,
            consumer_impact=consumer_impact,
            evidence_json=json.dumps(
                [
                    item.model_dump()
                    for item in evidence.schema_diffs
                    + evidence.payload_snapshots
                    + evidence.validation_failures
                    + evidence.dlq_entries
                    + evidence.drift_event_dlq_entries
                    + evidence.delivery_attempts
                    + evidence.drift_violations
                ],
                ensure_ascii=True,
                indent=2,
                default=str,
            ),
            validation_json=json.dumps(
                [item.model_dump() for item in evidence.validation_failures],
                ensure_ascii=True,
                indent=2,
                default=str,
            ),
            dlq_json=json.dumps(
                [item.model_dump() for item in evidence.dlq_entries + evidence.delivery_attempts],
                ensure_ascii=True,
                indent=2,
                default=str,
            ),
            format_instructions=self._parser.get_format_instructions(),
        )
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": prompt[0].content},
                {"role": "user", "content": prompt[1].content},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            res = await client.post(f"{self.base_url}/v1/chat/completions", json=payload, headers=headers)
            res.raise_for_status()
            data = res.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        parsed = self._parser.parse(content)
        return ContractReviewOutcome.model_validate(parsed)

    async def generate(
        self,
        *,
        evidence: ContractReviewEvidence,
        evidence_summary: str,
        consumer_impact: str,
    ) -> ContractReviewOutcome:
        try:
            return await self._call_model(evidence, evidence_summary, consumer_impact)
        except Exception:
            return _build_heuristic_review(
                evidence=evidence,
                evidence_summary=evidence_summary,
                consumer_impact=consumer_impact,
                insufficient_reason="Model generation failed; using evidence-only fallback review.",
            )


class GeminiReviewProvider:
    provider_name = "gemini"

    def __init__(
        self,
        *,
        api_key: str,
        model_name: str,
        base_url: str,
        timeout_seconds: int,
    ) -> None:
        self.api_key = api_key
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._parser = PydanticOutputParser(pydantic_object=ContractReviewOutcome)
        self._prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are DRIFTGATE's contract review agent. Use only the supplied evidence. "
                    "Return JSON only and never invent facts.",
                ),
                (
                    "human",
                    "Endpoint: {endpoint_name}\n"
                    "Route: {http_method} {route_path}\n"
                    "Diff summary:\n{evidence_summary}\n\n"
                    "Consumer impact:\n{consumer_impact}\n\n"
                    "Evidence JSON:\n{evidence_json}\n\n"
                    "Validation failures:\n{validation_json}\n\n"
                    "DLQ context:\n{dlq_json}\n\n"
                    "{format_instructions}",
                ),
            ]
        )

    async def _call_model(
        self,
        evidence: ContractReviewEvidence,
        evidence_summary: str,
        consumer_impact: str,
    ) -> ContractReviewOutcome:
        prompt = self._prompt.format_messages(
            endpoint_name=evidence.endpoint_name,
            http_method=evidence.http_method,
            route_path=evidence.route_path,
            evidence_summary=evidence_summary,
            consumer_impact=consumer_impact,
            evidence_json=json.dumps(
                [
                    item.model_dump()
                    for item in evidence.schema_diffs
                    + evidence.payload_snapshots
                    + evidence.validation_failures
                    + evidence.dlq_entries
                    + evidence.drift_event_dlq_entries
                    + evidence.delivery_attempts
                    + evidence.drift_violations
                ],
                ensure_ascii=True,
                indent=2,
                default=str,
            ),
            validation_json=json.dumps(
                [item.model_dump() for item in evidence.validation_failures],
                ensure_ascii=True,
                indent=2,
                default=str,
            ),
            dlq_json=json.dumps(
                [item.model_dump() for item in evidence.dlq_entries + evidence.delivery_attempts],
                ensure_ascii=True,
                indent=2,
                default=str,
            ),
            format_instructions=self._parser.get_format_instructions(),
        )
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"{prompt[0].content}\n\n{prompt[1].content}"}],
                }
            ],
            "generationConfig": {"temperature": 0, "maxOutputTokens": 1024},
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            res = await client.post(
                f"{self.base_url}/v1beta/models/{self.model_name}:generateContent",
                params={"key": self.api_key},
                json=payload,
            )
            res.raise_for_status()
            data = res.json()
        content = (
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )
        parsed = self._parser.parse(content)
        return ContractReviewOutcome.model_validate(parsed)

    async def generate(
        self,
        *,
        evidence: ContractReviewEvidence,
        evidence_summary: str,
        consumer_impact: str,
    ) -> ContractReviewOutcome:
        try:
            return await self._call_model(evidence, evidence_summary, consumer_impact)
        except Exception:
            return _build_heuristic_review(
                evidence=evidence,
                evidence_summary=evidence_summary,
                consumer_impact=consumer_impact,
                insufficient_reason="Model generation failed; using evidence-only fallback review.",
            )


def build_review_provider() -> ReviewProvider:
    provider = os.getenv("AI_PROVIDER", "disabled").strip().lower()
    if provider == "fake":
        return FakeReviewProvider()
    if provider in {"", "disabled", "auto", "openai"} and os.getenv("OPENAI_API_KEY"):
        api_key = os.getenv("OPENAI_API_KEY")
        return OpenAIReviewProvider(
            api_key=api_key,
            model_name=os.getenv("AI_MODEL", "gpt-4.1-mini"),
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com"),
            timeout_seconds=int(os.getenv("AI_TIMEOUT_SECONDS", "20")),
        )
    if provider in {"", "disabled", "auto", "gemini"} and os.getenv("GEMINI_API_KEY"):
        api_key = os.getenv("GEMINI_API_KEY")
        return GeminiReviewProvider(
            api_key=api_key,
            model_name=os.getenv("AI_MODEL", "gemini-2.5-flash"),
            base_url=os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com"),
            timeout_seconds=int(os.getenv("AI_TIMEOUT_SECONDS", "20")),
        )
    if provider in {"ollama", "local"}:
        return OllamaReviewProvider(
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            model_name=os.getenv("AI_MODEL", "qwen2.5-coder:7b"),
            fallback_model_name=os.getenv("AI_FALLBACK_MODEL", "llama3.1:8b") or None,
            timeout_seconds=int(os.getenv("AI_TIMEOUT_SECONDS", "20")),
        )
    if os.getenv("OLLAMA_BASE_URL") and provider in {"", "disabled", "auto"}:
        return OllamaReviewProvider(
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            model_name=os.getenv("AI_MODEL", "qwen2.5-coder:7b"),
            fallback_model_name=os.getenv("AI_FALLBACK_MODEL", "llama3.1:8b") or None,
            timeout_seconds=int(os.getenv("AI_TIMEOUT_SECONDS", "20")),
        )
    return DisabledReviewProvider()


def _row_to_dict(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    if isinstance(row, dict):
        return dict(row)
    return {key: row[key] for key in row.keys()}


async def _fetch_endpoint_metadata(db: AsyncSession, endpoint_id: str) -> dict[str, Any] | None:
    row = await db.execute(
        text(
            """
            SELECT id::text, namespace, service_name, http_method, route_path, endpoint_name, created_at
            FROM contract_registry_endpoints
            WHERE id = CAST(:endpoint_id AS uuid)
            """
        ),
        {"endpoint_id": endpoint_id},
    )
    item = row.first()
    if item is None:
        return None
    return {
        "id": item[0],
        "namespace": item[1],
        "service_name": item[2],
        "http_method": item[3],
        "route_path": item[4],
        "endpoint_name": item[5],
        "created_at": item[6].isoformat(),
    }


async def _fetch_schema_versions(
    db: AsyncSession, endpoint_id: str, limit: int
) -> list[dict[str, Any]]:
    rows = await db.execute(
        text(
            """
            SELECT id::text, version, fingerprint, canonical_schema, compatibility_classification,
                   previous_version_id::text, is_current, created_at
            FROM contract_schema_versions
            WHERE endpoint_id = CAST(:endpoint_id AS uuid)
            ORDER BY version DESC
            LIMIT :limit
            """
        ),
        {"endpoint_id": endpoint_id, "limit": limit},
    )
    out: list[dict[str, Any]] = []
    for row in rows.fetchall():
        out.append(
            {
                "id": row[0],
                "version": row[1],
                "fingerprint": row[2],
                "canonical_schema": row[3],
                "compatibility_classification": row[4],
                "previous_version_id": row[5],
                "is_current": row[6],
                "created_at": row[7].isoformat(),
            }
        )
    return out


async def _fetch_drift_violations(db: AsyncSession, endpoint_id: str, limit: int) -> list[ReviewEvidenceItem]:
    rows = await db.execute(
        text(
            """
            SELECT id::text, observed_fingerprint, severity, diff_payload, detected_at
            FROM contract_drift_violations
            WHERE endpoint_id = CAST(:endpoint_id AS uuid)
            ORDER BY detected_at DESC
            LIMIT :limit
            """
        ),
        {"endpoint_id": endpoint_id, "limit": limit},
    )
    out: list[ReviewEvidenceItem] = []
    for index, row in enumerate(rows.fetchall(), start=1):
        payload = row[3] or {}
        out.append(
            ReviewEvidenceItem(
                citation=f"drift-violation:{index}",
                kind="drift_violation",
                summary=(
                    f"severity={row[2]} fingerprint={row[1]} path={payload.get('path', '[unknown]')}"
                ),
                details={
                    "id": row[0],
                    "observed_fingerprint": row[1],
                    "severity": str(row[2]).upper(),
                    "diff_payload": payload,
                    "detected_at": row[4].isoformat(),
                },
            )
        )
    return out


async def _fetch_doc_items(
    document_store: DocumentStore | None,
    *,
    kind: str,
    endpoint_id: str,
    limit: int,
) -> list[dict[str, Any]]:
    if document_store is None:
        return []
    if kind == "schema_diffs":
        items = await document_store.list_schema_diffs(limit=limit * 2)
    elif kind == "payload_snapshots":
        items = await document_store.list_payload_snapshots(limit=limit * 2)
    elif kind == "validation_errors":
        items = await document_store.list_validation_errors(limit=limit * 2)
    elif kind == "replay_artifacts":
        items = await document_store.list_replay_artifacts(limit=limit * 2)
    elif kind == "contract_reviews":
        items = await document_store.list_contract_reviews(limit=limit * 2, endpoint_id=endpoint_id)
    else:
        items = []
    if kind == "validation_errors":
        return items[:limit]
    filtered: list[dict[str, Any]] = []
    for item in items:
        if str(item.get("endpoint_id")) == endpoint_id:
            filtered.append(item)
    return filtered[:limit]


def _schema_diff_summary(items: list[ReviewEvidenceItem]) -> str:
    if not items:
        return "No schema diff documents were found for this endpoint."
    return "; ".join(item.summary for item in items[:5])


def _consumer_impact_summary(evidence: ContractReviewEvidence) -> str:
    active_subscriptions = [item for item in evidence.subscriptions if item.get("active", True)]
    affected = len(active_subscriptions)
    dlq_count = len(evidence.dlq_entries)
    failed_attempts = sum(int(item.details.get("attempt_count", 0)) for item in evidence.delivery_attempts)
    threshold_labels = sorted(
        {str(item.get("severity_threshold", "unknown")) for item in active_subscriptions if item.get("severity_threshold")}
    )
    parts = [f"{affected} active consumer(s) are subscribed to this endpoint"]
    if threshold_labels:
        parts.append(f"thresholds: {', '.join(threshold_labels)}")
    if dlq_count:
        parts.append(f"{dlq_count} DLQ item(s) already exist for this endpoint")
    if failed_attempts:
        parts.append(f"{failed_attempts} recorded delivery attempt(s) failed")
    return "; ".join(parts)


def _evidence_context_summary(evidence: ContractReviewEvidence) -> str:
    sections = [
        f"endpoint={evidence.endpoint_name}",
        f"route={evidence.http_method} {evidence.route_path}",
        f"current_version={evidence.current_version if evidence.current_version is not None else 'unknown'}",
        f"schema_diffs={len(evidence.schema_diffs)}",
        f"payload_snapshots={len(evidence.payload_snapshots)}",
        f"validation_failures={len(evidence.validation_failures)}",
        f"dlq_entries={len(evidence.dlq_entries)}",
        f"delivery_attempts={len(evidence.delivery_attempts)}",
        f"drift_violations={len(evidence.drift_violations)}",
    ]
    if evidence.notes:
        sections.append("notes=" + " | ".join(evidence.notes))
    return "; ".join(sections)


async def collect_contract_evidence(
    db: AsyncSession,
    *,
    document_store: DocumentStore | None,
    request: ContractReviewRequest,
) -> ContractReviewEvidence:
    endpoint = await _fetch_endpoint_metadata(db, request.endpoint_id)
    if endpoint is None:
        raise ValueError("endpoint not found")

    schema_versions = await _fetch_schema_versions(db, request.endpoint_id, request.review_limit)
    current_version = next((item["version"] for item in schema_versions if item["is_current"]), None)
    schema_diffs = await _fetch_doc_items(
        document_store,
        kind="schema_diffs",
        endpoint_id=request.endpoint_id,
        limit=request.evidence_limit,
    )
    payload_snapshots = await _fetch_doc_items(
        document_store,
        kind="payload_snapshots",
        endpoint_id=request.endpoint_id,
        limit=request.evidence_limit,
    )
    validation_failures = await _fetch_doc_items(
        document_store,
        kind="validation_errors",
        endpoint_id=request.endpoint_id,
        limit=request.evidence_limit,
    )
    replay_artifacts = await _fetch_doc_items(
        document_store,
        kind="replay_artifacts",
        endpoint_id=request.endpoint_id,
        limit=request.evidence_limit,
    )
    reviews = await _fetch_doc_items(
        document_store,
        kind="contract_reviews",
        endpoint_id=request.endpoint_id,
        limit=request.review_limit,
    )
    drift_violations = await _fetch_drift_violations(db, request.endpoint_id, request.evidence_limit)
    subscriptions = await list_subscriptions(db, request.endpoint_id)

    dlq_rows = await db.execute(
        text(
            """
            SELECT id::text, event_id::text, consumer_id, target_url, failure_reason, attempt_count,
                   created_at, last_attempt_at, payload
            FROM webhook_delivery_dlq
            WHERE endpoint_id = CAST(:endpoint_id AS uuid)
            ORDER BY last_attempt_at DESC
            LIMIT :limit
            """
        ),
        {"endpoint_id": request.endpoint_id, "limit": request.evidence_limit},
    )
    dlq_entries: list[ReviewEvidenceItem] = []
    for index, row in enumerate(dlq_rows.fetchall(), start=1):
        dlq_entries.append(
            ReviewEvidenceItem(
                citation=f"dlq:{index}",
                kind="dlq_entry",
                summary=(
                    f"consumer={row[2]} attempts={row[5]} reason={row[4]} target={row[3]}"
                ),
                details={
                    "id": row[0],
                    "event_id": row[1],
                    "consumer_id": row[2],
                    "target_url": row[3],
                    "failure_reason": row[4],
                    "attempt_count": row[5],
                    "created_at": row[6].isoformat(),
                    "last_attempt_at": row[7].isoformat(),
                    "payload": row[8],
                },
            )
        )

    drift_event_rows = await list_event_dlq(db, limit=request.evidence_limit * 2)
    drift_event_dlq_entries: list[ReviewEvidenceItem] = []
    for index, item in enumerate(
        [row for row in drift_event_rows if str(row.get("endpoint_id")) == request.endpoint_id],
        start=1,
    ):
        drift_event_dlq_entries.append(
            ReviewEvidenceItem(
                citation=f"drift-event-dlq:{index}",
                kind="drift_event_dlq",
                summary=(
                    f"publisher={item.get('publisher_name', 'unknown')} attempts={item.get('attempt_count', 0)} "
                    f"reason={item.get('failure_reason', 'unknown')}"
                ),
                details=dict(item),
            )
        )

    attempts_rows = await db.execute(
        text(
            """
            SELECT id::text, event_id::text, consumer_id, target_url, success, failure_reason, attempt_count, attempted_at
            FROM webhook_delivery_attempts
            WHERE endpoint_id = CAST(:endpoint_id AS uuid)
            ORDER BY attempted_at DESC
            LIMIT :limit
            """
        ),
        {"endpoint_id": request.endpoint_id, "limit": request.evidence_limit * 2},
    )
    delivery_attempts: list[ReviewEvidenceItem] = []
    for index, row in enumerate(attempts_rows.fetchall(), start=1):
        delivery_attempts.append(
            ReviewEvidenceItem(
                citation=f"attempt:{index}",
                kind="delivery_attempt",
                summary=(
                    f"consumer={row[2]} success={bool(row[4])} attempts={row[6]} reason={row[5] or 'ok'}"
                ),
                details={
                    "id": row[0],
                    "event_id": row[1],
                    "consumer_id": row[2],
                    "target_url": row[3],
                    "success": bool(row[4]),
                    "failure_reason": row[5],
                    "attempt_count": row[6],
                    "attempted_at": row[7].isoformat(),
                },
            )
        )

    notes: list[str] = []
    if validation_failures:
        notes.append("validation failures are captured from /track request validation")
    if not schema_diffs and not drift_violations:
        notes.append("no schema diff documents or drift violations were found")
    if not payload_snapshots:
        notes.append("no payload snapshots were stored for this endpoint")
    if drift_event_dlq_entries:
        notes.append(f"{len(drift_event_dlq_entries)} drift-event DLQ item(s) exist for this endpoint")
    if reviews:
        notes.append(f"{len(reviews)} prior contract review result(s) already exist")
    if replay_artifacts:
        notes.append(f"{len(replay_artifacts)} replay artifact(s) exist for this endpoint")

    insufficient = not (
        schema_diffs
        or drift_violations
        or payload_snapshots
        or validation_failures
        or dlq_entries
        or drift_event_dlq_entries
    )
    if insufficient:
        notes.append("available evidence is too sparse for a strong review")

    evidence = ContractReviewEvidence(
        endpoint_id=endpoint["id"],
        endpoint_name=endpoint["endpoint_name"],
        namespace=endpoint["namespace"],
        service_name=endpoint["service_name"],
        http_method=endpoint["http_method"],
        route_path=endpoint["route_path"],
        current_version=current_version,
        schema_diffs=[
            ReviewEvidenceItem(
                citation=f"schema-diff:{index}",
                kind="schema_diff",
                summary=(
                    f"{item.get('classification', 'unknown')} diff at {item.get('path', '[unknown]')} "
                    f"message={_truncate(item.get('message', item.get('diffs', [])), 180)}"
                ),
                details=dict(item),
            )
            for index, item in enumerate(schema_diffs, start=1)
        ],
        payload_snapshots=[
            ReviewEvidenceItem(
                citation=f"snapshot:{index}",
                kind="payload_snapshot",
                summary=(
                    f"source={item.get('source', 'unknown')} classification={item.get('classification', 'unknown')} "
                    f"fingerprint={str(item.get('fingerprint', ''))[:12]}"
                ),
                details=dict(item),
            )
            for index, item in enumerate(payload_snapshots, start=1)
        ],
        validation_failures=[
            ReviewEvidenceItem(
                citation=f"validation:{index}",
                kind="validation_error",
                summary=(
                    f"path={item.get('path', '[unknown]')} errors={_truncate(item.get('errors', []), 180)}"
                ),
                details=dict(item),
            )
            for index, item in enumerate(validation_failures, start=1)
        ],
        dlq_entries=dlq_entries,
        drift_event_dlq_entries=drift_event_dlq_entries,
        delivery_attempts=delivery_attempts,
        subscriptions=subscriptions,
        drift_violations=drift_violations,
        notes=notes,
        insufficient_evidence=insufficient,
    )
    return evidence


def _build_graph(provider: ReviewProvider, *, db: AsyncSession, document_store: DocumentStore | None):
    graph: StateGraph[ContractReviewState] = StateGraph(ContractReviewState)

    async def _collect(state: ContractReviewState) -> ContractReviewState:
        request = state["request"]
        evidence = await collect_contract_evidence(db, document_store=document_store, request=request)
        return {
            "evidence": evidence,
            "provider_name": provider.provider_name,
            "model_name": provider.model_name,
        }

    async def _summarize(state: ContractReviewState) -> ContractReviewState:
        evidence = state["evidence"]
        diff_summary = _schema_diff_summary(evidence.schema_diffs + evidence.drift_violations)
        return {"evidence_summary": diff_summary}

    async def _impact(state: ContractReviewState) -> ContractReviewState:
        evidence = state["evidence"]
        return {"consumer_impact": _consumer_impact_summary(evidence)}

    async def _generate(state: ContractReviewState) -> ContractReviewState:
        evidence = state["evidence"]
        if evidence.insufficient_evidence:
            review = _build_heuristic_review(
                evidence=evidence,
                evidence_summary=state.get("evidence_summary", ""),
                consumer_impact=state.get("consumer_impact", ""),
                insufficient_reason="Insufficient evidence to produce a grounded contract review.",
            )
        else:
            review = await provider.generate(
                evidence=evidence,
                evidence_summary=state.get("evidence_summary", ""),
                consumer_impact=state.get("consumer_impact", ""),
            )
        return {"candidate_review": review.model_dump()}

    async def _validate(state: ContractReviewState) -> ContractReviewState:
        candidate = state["candidate_review"]
        try:
            review = ContractReviewOutcome.model_validate(candidate)
            CONTRACT_REVIEW_SCHEMA_VALID_TOTAL.labels(provider=state.get("provider_name", "unknown")).inc()
            return {"review": review}
        except ValidationError:
            CONTRACT_REVIEW_GROUNDING_FAILURE_TOTAL.labels(provider=state.get("provider_name", "unknown")).inc()
            review = _build_heuristic_review(
                evidence=state["evidence"],
                evidence_summary=state.get("evidence_summary", ""),
                consumer_impact=state.get("consumer_impact", ""),
                insufficient_reason="Model output failed schema validation; using evidence-only fallback review.",
            )
            return {"review": review}

    async def _ground(state: ContractReviewState) -> ContractReviewState:
        review = state["review"]
        evidence = state["evidence"]
        citations = set(evidence.citations)
        if review.insufficient_evidence:
            CONTRACT_REVIEW_INSUFFICIENT_EVIDENCE_TOTAL.labels(provider=state.get("provider_name", "unknown")).inc()
        if not review.evidence or any(
            not any(citation in evidence_line for citation in citations) for evidence_line in review.evidence
        ):
            CONTRACT_REVIEW_GROUNDING_FAILURE_TOTAL.labels(provider=state.get("provider_name", "unknown")).inc()
            review = _build_heuristic_review(
                evidence=evidence,
                evidence_summary=state.get("evidence_summary", ""),
                consumer_impact=state.get("consumer_impact", ""),
                insufficient_reason="Generated evidence lacked grounded citations; using evidence-only fallback review.",
            )
        return {"review": review}

    async def _persist(state: ContractReviewState) -> ContractReviewState:
        start = state.get("started_at", time.perf_counter())
        latency_seconds = time.perf_counter() - start
        review = state["review"]
        evidence = state["evidence"]
        record = ContractReviewRecord(
            review_id=uuid.uuid4().hex,
            endpoint_id=evidence.endpoint_id,
            endpoint_name=evidence.endpoint_name,
            provider=state.get("provider_name", provider.provider_name),
            model_name=state.get("model_name", provider.model_name),
            created_at=_now_iso(),
            latency_seconds=latency_seconds,
            evidence_summary=state.get("evidence_summary", ""),
            consumer_impact=state.get("consumer_impact", ""),
            context=evidence,
            review=review,
        )
        if document_store is not None:
            await document_store.store_contract_review(
                endpoint_id=evidence.endpoint_id,
                endpoint_name=evidence.endpoint_name,
                provider=record.provider,
                model_name=record.model_name,
                evidence_summary=record.evidence_summary,
                consumer_impact=record.consumer_impact,
                review=record.review.model_dump(),
                context=record.context.model_dump(),
                source="runtime-contract-review",
            )
        CONTRACT_REVIEW_TOTAL.labels(
            decision=review.decision.value,
            severity=review.severity.value,
            provider=record.provider,
        ).inc()
        CONTRACT_REVIEW_LATENCY_SECONDS.observe(latency_seconds)
        return {"record": record, "latency_seconds": latency_seconds}

    graph.add_node("collect_contract_evidence", _collect)
    graph.add_node("summarize_schema_diff", _summarize)
    graph.add_node("assess_consumer_impact", _impact)
    graph.add_node("generate_review", _generate)
    graph.add_node("validate_schema", _validate)
    graph.add_node("verify_evidence_grounding", _ground)
    graph.add_node("persist_review", _persist)

    graph.add_edge(START, "collect_contract_evidence")
    graph.add_edge("collect_contract_evidence", "summarize_schema_diff")
    graph.add_edge("summarize_schema_diff", "assess_consumer_impact")
    graph.add_edge("assess_consumer_impact", "generate_review")
    graph.add_edge("generate_review", "validate_schema")
    graph.add_edge("validate_schema", "verify_evidence_grounding")
    graph.add_edge("verify_evidence_grounding", "persist_review")
    graph.add_edge("persist_review", END)
    return graph.compile()


@dataclass(slots=True)
class ContractReviewService:
    provider: ReviewProvider | None = None

    def _provider(self) -> ReviewProvider:
        return self.provider or build_review_provider()

    async def review(
        self,
        db: AsyncSession,
        *,
        document_store: DocumentStore | None,
        request: ContractReviewRequest,
    ) -> ContractReviewRecord:
        provider = self._provider()
        graph = _build_graph(provider, db=db, document_store=document_store)
        state: ContractReviewState = {
            "request": request,
            "started_at": time.perf_counter(),
        }
        result = await graph.ainvoke(state)
        return result["record"]

    async def history(
        self,
        document_store: DocumentStore | None,
        *,
        endpoint_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        if document_store is None:
            return []
        return await document_store.list_contract_reviews(limit=limit, endpoint_id=endpoint_id)


def build_contract_review_service(provider: ReviewProvider | None = None) -> ContractReviewService:
    return ContractReviewService(provider=provider)


def evaluate_contract_review_cases(
    cases: list[dict[str, Any]],
    provider: ReviewProvider | None = None,
) -> dict[str, Any]:
    review_provider = provider or FakeReviewProvider()
    valid_outputs = 0
    correct_severity = 0
    evidence_coverage = 0
    unsupported_claims = 0
    migration_plans = 0
    insufficient_count = 0
    total_confidence = 0.0
    total_latency = 0.0
    for case in cases:
        evidence = ContractReviewEvidence.model_validate(case["evidence"])
        evidence_summary = case.get("evidence_summary", "")
        consumer_impact = case.get("consumer_impact", "")
        start = time.perf_counter()
        import asyncio

        outcome = asyncio.run(
            review_provider.generate(
                evidence=evidence,
                evidence_summary=evidence_summary,
                consumer_impact=consumer_impact,
            )
        )
        elapsed = time.perf_counter() - start
        total_latency += elapsed
        try:
            validated = ContractReviewOutcome.model_validate(outcome)
            valid_outputs += 1
        except ValidationError:
            continue
        if str(validated.severity.value) == str(case.get("expected_severity", validated.severity.value)):
            correct_severity += 1
        if validated.evidence:
            evidence_coverage += 1
        if any(
            not any(citation in evidence_line for citation in evidence.citations)
            for evidence_line in validated.evidence
        ):
            unsupported_claims += 1
        if validated.migration_note.strip():
            migration_plans += 1
        total_confidence += validated.confidence
        if validated.insufficient_evidence:
            insufficient_count += 1
    total = len(cases) or 1
    return {
        "total_cases": len(cases),
        "schema_valid_output_rate": valid_outputs / total,
        "correct_severity_rate": correct_severity / total,
        "evidence_coverage_rate": evidence_coverage / total,
        "unsupported_claim_rate": unsupported_claims / total,
        "migration_plan_rate": migration_plans / total,
        "average_generation_latency_ms": (total_latency / total) * 1000.0,
        "average_confidence": total_confidence / total if cases else 0.0,
        "insufficient_evidence_rate": insufficient_count / total,
    }
