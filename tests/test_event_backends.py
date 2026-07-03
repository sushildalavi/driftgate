from __future__ import annotations

import json

import pytest

from app.runtime.event_backends import AzureServiceBusEventBackend, build_event_backend
from app.runtime.models import DriftEvent


class FakeSender:
    def __init__(self) -> None:
        self.messages = []

    async def send_messages(self, message):
        self.messages.append(message)


@pytest.mark.asyncio
async def test_azure_service_bus_backend_uses_sender():
    sender = FakeSender()
    backend = AzureServiceBusEventBackend(sender)
    event = DriftEvent(
        event_id="e2",
        endpoint_id="ep",
        endpoint_name="svc POST /x",
        namespace="ns",
        old_fingerprint="old",
        new_fingerprint="new",
        old_version=1,
        new_version=2,
        severity="BREAKING",
        compatibility_classification="BREAKING",
        timestamp="2026-05-27T00:00:00Z",
        schema_diff_summary=[],
        affected_consumer_count=0,
    )
    await backend.publish_drift_detected(event)
    assert sender.messages


def test_factory_requires_sender_for_service_bus(monkeypatch):
    monkeypatch.setenv("EVENT_BACKEND", "azure_service_bus")
    with pytest.raises(RuntimeError, match="service_bus_sender"):
        build_event_backend()
