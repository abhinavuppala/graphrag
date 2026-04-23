"""Phase 2: Configure GraphRAG workspace from Phase 1 selection results.

Usage:
    python -m pipeline.config [options]
"""
import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from .detect import detect_domain
from .settings_gen import setup_workspace


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Configure GraphRAG workspace for indexing"
    )
    parser.add_argument(
        "--workspace", default="graphrag",
        help="GraphRAG workspace directory (default: graphrag)",
    )
    args = parser.parse_args()

    workspace = Path(args.workspace)
    load_dotenv(workspace / ".env")
    api_key = os.environ.get("GRAPHRAG_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        sys.exit("Error: GRAPHRAG_API_KEY not set. Add to <workspace>/.env or export it.")

    report_path = workspace / "input" / "selection_report.json"
    if not report_path.exists():
        sys.exit(f"Error: {report_path} not found — run Phase 1 first.")

    report = json.loads(report_path.read_text(encoding="utf-8"))
    detected_language = report.get("detected_language", "")
    detected_framework = report.get("detected_framework", "")

    print("=== Phase 2: Configuration ===")
    print(f"\n  Language : {detected_language}")
    print(f"  Framework: {detected_framework}")

    domain = detect_domain(detected_framework, detected_language)
    print(f"  Domain   : {domain.name} — {domain.description}")
    print(f"  Entities : {', '.join(domain.entity_types)}")

    print(f"\nSetting up workspace: {workspace}/")
    actions = setup_workspace(workspace, domain, api_key)
    for action in actions:
        prefix = "  [!]" if action.startswith("WARNING") else "   + "
        print(f"{prefix} {action}")

    if any("WARNING" in a for a in actions):
        print("\nWorkspace has issues — resolve warnings before indexing.")
        sys.exit(1)

    print(f"\nDone. Run: graphrag index --root ./{args.workspace}")


if __name__ == "__main__":
    main()
