from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _metric(metrics: dict[str, Any], key: str, stat: str) -> Any:
    value = metrics.get(key, {})
    if isinstance(value, dict):
        return value.get(stat)
    return None


def _sidecar_paths(path: Path) -> list[Path]:
    return [
        path.with_name(f"{path.stem}.state.json"),
        path.with_name(f"{path.stem}.db.json"),
        path.with_name(f"{path.stem}.snapshot.json"),
    ]


def _load_sidecar(path: Path) -> dict[str, Any]:
    for candidate in _sidecar_paths(path):
        if candidate.exists():
            return _load_json(candidate)
    return {}


def _extract_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    metrics = payload.get("metrics")
    if isinstance(metrics, dict):
        return metrics
    return payload if isinstance(payload, dict) else {}


def _metric_number(metrics: dict[str, Any], key: str, stat: str, default: float = 0.0) -> float:
    value = _metric(metrics, key, stat)
    if isinstance(value, (int, float)):
        return float(value)
    return default


def _state_summary(state: dict[str, Any]) -> str:
    if not state:
        return "n/a"
    ordered_keys = [
        "endpoint_count",
        "snapshot_count",
        "schema_version_count",
        "webhook_outbox_pending_count",
        "webhook_delivery_dlq_count",
        "drift_event_dlq_count",
        "webhook_delivery_attempts_count",
        "contract_review_count",
        "contract_review_insufficient_evidence_count",
    ]
    parts: list[str] = []
    for key in ordered_keys:
        if key in state:
            parts.append(f"{key}={state[key]}")
    extra_keys = sorted(k for k in state.keys() if k not in ordered_keys)
    for key in extra_keys:
        value = state[key]
        if isinstance(value, (str, int, float, bool)):
            parts.append(f"{key}={value}")
    return ", ".join(parts) if parts else "n/a"


def summarize_artifact(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    metrics = _extract_metrics(payload)
    state = payload.get("state") if isinstance(payload.get("state"), dict) else _load_sidecar(path)
    http_reqs = metrics.get("http_reqs", {})
    duration = metrics.get("http_req_duration", {})
    failed = metrics.get("http_req_failed", {})
    vus = metrics.get("vus", metrics.get("vus_max", {}))
    checks = metrics.get("checks", {})
    error_classes = {
        "transport": int(_metric_number(metrics, "request_error_transport_total", "value")),
        "validation": int(_metric_number(metrics, "request_error_validation_total", "value")),
        "client": int(_metric_number(metrics, "request_error_client_total", "value")),
        "server": int(_metric_number(metrics, "request_error_server_total", "value")),
    }
    return {
        "artifact": path.name,
        "vus": vus.get("value") if isinstance(vus, dict) else None,
        "requests": http_reqs.get("count") if isinstance(http_reqs, dict) else None,
        "failed_checks": checks.get("fails", 0) if isinstance(checks, dict) else 0,
        "p50_latency_ms": duration.get("med") if isinstance(duration, dict) else None,
        "p95_latency_ms": duration.get("p(95)") if isinstance(duration, dict) else None,
        "p99_latency_ms": duration.get("p(99)") if isinstance(duration, dict) else None,
        "error_rate": failed.get("value") if isinstance(failed, dict) else None,
        "throughput_rps": http_reqs.get("rate") if isinstance(http_reqs, dict) else None,
        "error_classes": error_classes,
        "state_summary": _state_summary(state if isinstance(state, dict) else {}),
        "state": state if isinstance(state, dict) else {},
    }


def render_markdown(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# DRIFTGATE Benchmark Summary",
        "",
        "| artifact | VUs | requests | failed checks | p50 latency ms | p95 latency ms | p99 latency ms | error rate | throughput rps | error classes | state snapshot |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        classes = row.get("error_classes", {})
        class_summary = ", ".join(f"{key}:{value}" for key, value in classes.items()) if classes else "n/a"
        row_data = {
            "artifact": row.get("artifact", "n/a"),
            "vus": row.get("vus", "n/a"),
            "requests": row.get("requests", "n/a"),
            "failed_checks": row.get("failed_checks", 0),
            "p50_latency_ms": row.get("p50_latency_ms", "n/a"),
            "p95_latency_ms": row.get("p95_latency_ms", "n/a"),
            "p99_latency_ms": row.get("p99_latency_ms", "n/a"),
            "error_rate": row.get("error_rate", "n/a"),
            "throughput_rps": row.get("throughput_rps", "n/a"),
            "state_summary": row.get("state_summary", "n/a"),
        }
        lines.append(
            "| {artifact} | {vus} | {requests} | {failed_checks} | {p50_latency_ms} | {p95_latency_ms} | {p99_latency_ms} | {error_rate} | {throughput_rps} | {class_summary} | {state_summary} |".format(
                **row_data,
                class_summary=class_summary,
            )
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Summarize DRIFTGATE k6 benchmark artifacts.")
    parser.add_argument(
        "--artifacts",
        nargs="+",
        default=["docs/benchmarks/k6_smoke.json", "docs/benchmarks/k6_50vus.json"],
    )
    parser.add_argument("--output", default="")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    rows = [summarize_artifact(Path(path)) for path in args.artifacts]
    markdown = render_markdown(rows)
    if args.output:
        Path(args.output).write_text(markdown + "\n", encoding="utf-8")
    else:
        print(markdown)


if __name__ == "__main__":
    main()
