from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any


class SeverityRank(IntEnum):
    SAFE = 0
    BACKWARD_COMPATIBLE = 1
    FORWARD_COMPATIBLE = 2
    RISKY = 3
    BREAKING = 4


@dataclass(frozen=True)
class SchemaVersionRecord:
    id: str
    endpoint_id: str
    version: int
    fingerprint: str
    canonical_schema: dict[str, Any]
    compatibility_classification: str
    previous_version_id: str | None
    is_current: bool


@dataclass(frozen=True)
class DriftEvent:
    event_id: str
    endpoint_id: str
    endpoint_name: str
    namespace: str
    old_fingerprint: str
    new_fingerprint: str
    old_version: int
    new_version: int
    severity: str
    compatibility_classification: str
    timestamp: str
    schema_diff_summary: list[dict[str, Any]]
    affected_consumer_count: int


def severity_rank(value: str) -> int:
    try:
        return int(SeverityRank[value])
    except KeyError:
        return int(SeverityRank.SAFE)
