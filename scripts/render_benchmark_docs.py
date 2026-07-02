from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.summarize_benchmarks import render_markdown, summarize_artifact


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render DriftGate benchmark docs from raw k6 JSON.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--title", default="DriftGate Benchmark Summary")
    parser.add_argument("--artifacts", nargs="+", required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    rows = [summarize_artifact(Path(path)) for path in args.artifacts]
    markdown = render_markdown(rows)
    if args.title:
        markdown = markdown.replace("# DriftGate Benchmark Summary", f"# {args.title}", 1)
    Path(args.output).write_text(markdown + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
