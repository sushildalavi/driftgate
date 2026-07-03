from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import psycopg2

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.summarize_benchmarks import render_markdown, summarize_artifact


def _load_state(
    *,
    dsn: str,
    route_path: str,
    service_name: str,
    namespace: str,
    http_method: str,
) -> dict[str, Any]:
    with psycopg2.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id::text
                FROM contract_registry_endpoints
                WHERE namespace = %s
                  AND service_name = %s
                  AND http_method = %s
                  AND route_path = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (namespace, service_name, http_method, route_path),
            )
            row = cur.fetchone()
            if row is None:
                return {
                    "endpoint_count": 0,
                    "snapshot_count": 0,
                    "schema_version_count": 0,
                    "webhook_outbox_pending_count": 0,
                    "webhook_delivery_dlq_count": 0,
                    "drift_event_dlq_count": 0,
                    "webhook_delivery_attempts_count": 0,
                }
            endpoint_id = row[0]

            def _count(sql: str, params: tuple[Any, ...] = ()) -> int:
                cur.execute(sql, params)
                value = cur.fetchone()[0]
                return int(value or 0)

            return {
                "endpoint_count": 1,
                "snapshot_count": _count(
                    "SELECT COUNT(*) FROM schema_snapshots WHERE endpoint_id = %s",
                    (endpoint_id,),
                ),
                "schema_version_count": _count(
                    "SELECT COUNT(*) FROM contract_schema_versions WHERE endpoint_id = %s",
                    (endpoint_id,),
                ),
                "webhook_outbox_pending_count": _count(
                    "SELECT COUNT(*) FROM webhook_outbox WHERE endpoint_id = %s AND status = 'PENDING'",
                    (endpoint_id,),
                ),
                "webhook_delivery_dlq_count": _count(
                    "SELECT COUNT(*) FROM webhook_delivery_dlq WHERE endpoint_id = %s",
                    (endpoint_id,),
                ),
                "drift_event_dlq_count": _count(
                    "SELECT COUNT(*) FROM drift_event_dlq WHERE endpoint_id = %s",
                    (endpoint_id,),
                ),
                "webhook_delivery_attempts_count": _count(
                    "SELECT COUNT(*) FROM webhook_delivery_attempts WHERE endpoint_id = %s",
                    (endpoint_id,),
                ),
            }


def _build_command(
    *,
    script: str,
    output_path: Path,
    track_url: str,
    route_path: str,
    service_name: str,
    namespace: str,
    http_method: str,
    vus: int | None,
    total_requests: int | None,
    duration: str | None,
) -> list[str]:
    env_args = [
        "-e",
        f"TRACK_URL={track_url}",
        "-e",
        f"ROUTE_PATH={route_path}",
        "-e",
        f"SERVICE_NAME={service_name}",
        "-e",
        f"NAMESPACE={namespace}",
        "-e",
        f"HTTP_METHOD={http_method}",
    ]
    if vus is not None:
        env_args.extend(["-e", f"K6_VUS={vus}"])
    if total_requests is not None:
        env_args.extend(["-e", f"K6_TOTAL_REQUESTS={total_requests}"])
    if duration is not None:
        env_args.extend(["-e", f"K6_DURATION={duration}"])
    if shutil.which("k6"):
        command = ["k6", "run", *env_args, "--summary-export", str(output_path), script]
    else:
        command = [
            "docker",
            "run",
            "--rm",
            "-i",
            "-v",
            f"{ROOT}:/workspace",
            "-w",
            "/workspace",
            "grafana/k6:latest",
            "run",
            *env_args,
            "--summary-export",
            f"/workspace/{output_path.relative_to(ROOT)}",
            f"/workspace/{script}",
        ]
    return command


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a DRIFTGATE k6 benchmark and emit derived docs.")
    parser.add_argument("--script", default="k6/track_profile.js")
    parser.add_argument("--name", default="")
    parser.add_argument("--output-dir", default="docs/benchmarks")
    parser.add_argument("--track-url", default="http://localhost:8302/track")
    parser.add_argument("--route-path", default="/bench/profile")
    parser.add_argument("--service-name", default="bench-profile")
    parser.add_argument("--namespace", default="k6")
    parser.add_argument("--http-method", default="POST")
    parser.add_argument("--vus", type=int, default=25)
    parser.add_argument("--total-requests", type=int, default=10000)
    parser.add_argument("--duration", default="")
    parser.add_argument("--skip-markdown", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    name = args.name or (
        f"{Path(args.script).stem}_{args.total_requests}req_{args.vus}vus"
        if args.total_requests is not None
        else f"{Path(args.script).stem}_{args.vus}vus"
    )
    summary_path = output_dir / f"{name}.json"
    state_path = output_dir / f"{name}.state.json"
    markdown_path = output_dir / f"{name}.md"

    command = _build_command(
        script=args.script,
        output_path=summary_path,
        track_url=args.track_url,
        route_path=args.route_path,
        service_name=args.service_name,
        namespace=args.namespace,
        http_method=args.http_method,
        vus=args.vus,
        total_requests=args.total_requests if args.duration == "" else None,
        duration=args.duration or None,
    )
    print("Running:", " ".join(command))
    completed = subprocess.run(command, check=False)
    if completed.returncode not in (0, 99):
        raise subprocess.CalledProcessError(completed.returncode, command)
    if not summary_path.exists():
        raise FileNotFoundError(f"k6 summary export was not created: {summary_path}")

    state = _load_state(
        dsn=os.getenv(
            "DATABASE_URL_SYNC",
            "postgresql://driftgate:dev@localhost:55433/driftgate_runtime",
        ),
        route_path=args.route_path,
        service_name=args.service_name,
        namespace=args.namespace,
        http_method=args.http_method,
    )
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if not args.skip_markdown:
        row = summarize_artifact(summary_path)
        row["state"] = state
        row["state_summary"] = ", ".join(f"{key}={value}" for key, value in state.items())
        markdown_path.write_text(render_markdown([row]) + "\n", encoding="utf-8")
        print(f"wrote {markdown_path}")

    print(f"wrote {summary_path}")
    print(f"wrote {state_path}")


if __name__ == "__main__":
    main()
