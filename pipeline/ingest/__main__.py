"""Phase 1 ingestion: clone a GitHub repo and write GraphRAG-ready .txt files.

Usage:
    python -m pipeline.ingest <github-url> [options]
"""
import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from .clone import clone_repo
from .select import build_manifest, select_files
from .convert import convert_files


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest a GitHub repo into graphrag/input/"
    )
    parser.add_argument("url", help="GitHub repository URL")
    parser.add_argument(
        "--workspace", default="graphrag",
        help="GraphRAG workspace root (default: graphrag). Input files go to <workspace>/input/",
    )
    parser.add_argument(
        "--clone-dir", default=None,
        help="Parent dir to clone into (default: system temp)",
    )
    parser.add_argument(
        "--size-cap", type=int, default=500_000,
        help="Skip files larger than N bytes (default: 500000)",
    )
    parser.add_argument(
        "--model", default="gpt-4o-mini",
        help="OpenAI model for file selection (default: gpt-4o-mini)",
    )
    parser.add_argument(
        "--clone-depth", type=int, default=1, metavar="N",
        help="Git clone depth (default: 1 shallow). Use 0 for full history.",
    )
    args = parser.parse_args()

    load_dotenv(Path(args.workspace) / ".env")
    api_key = os.environ.get("GRAPHRAG_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        sys.exit("Error: GRAPHRAG_API_KEY not set. Add to <workspace>/.env or export it.")

    output_dir = Path(args.workspace) / "input"
    clone_root = Path(args.clone_dir) if args.clone_dir else None

    print("=== Phase 1: Ingestion ===")

    print("\n[1/4] Cloning repo...")
    depth = args.clone_depth if args.clone_depth > 0 else None
    repo_path = clone_repo(args.url, clone_root=clone_root, depth=depth)

    print("\n[2/4] Building file manifest...")
    entries = build_manifest(repo_path, size_cap=args.size_cap)
    print(f"  {len(entries)} candidate files after pre-filtering")
    if not entries:
        sys.exit("Error: No candidate files found after filtering.")

    print(f"\n[3/4] Selecting files with {args.model}...")
    result = select_files(entries, api_key=api_key, model=args.model)
    print(f"  Language : {result.detected_language}")
    print(f"  Framework: {result.detected_framework}")
    print(f"  Selected : {len(result.included)} files")
    print(f"  Excluded : {len(result.excluded)} files")
    print(f"  Summary  : {result.summary}")

    print(f"\n[4/4] Writing .txt files to {output_dir} ...")
    written = convert_files(repo_path, result.included, output_dir)
    print(f"  Wrote {len(written)} files")

    report = {
        "url": args.url,
        "detected_language": result.detected_language,
        "detected_framework": result.detected_framework,
        "summary": result.summary,
        "included": result.included,
        "excluded": result.excluded,
    }
    report_path = output_dir / "selection_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nSelection report: {report_path}")
    print(f"\nNext: python -m pipeline.config --workspace {args.workspace}")


if __name__ == "__main__":
    main()
