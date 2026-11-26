from __future__ import annotations

from pathlib import Path

from scripts.summarize_benchmarks import render_markdown, summarize_artifact


def test_summarize_artifact_extracts_k6_metrics():
    row = summarize_artifact(Path(__file__).resolve().parents[1] / "docs/benchmarks/k6Baseline50Vus.json")
    assert row["requests"] == 5000
    assert row["throughput_rps"] > 0


def test_summarize_artifact_reads_k6_counter_totals(tmp_path):
    artifact = tmp_path / "run.json"
    artifact.write_text('{"metrics": {"request_error_server_total": {"count": 3, "rate": 0.5}}}')
    assert summarize_artifact(artifact)["error_classes"]["server"] == 3


def test_render_markdown_includes_artifact_name():
    markdown = render_markdown(
        [
            {
                "artifact": "k6Baseline50Vus.json",
                "vus": 50,
                "requests": 5000,
                "p95_latency_ms": 1664.8998104999996,
                "error_rate": 0,
                "throughput_rps": 68.84,
            }
        ]
    )
    assert "k6Baseline50Vus.json" in markdown
