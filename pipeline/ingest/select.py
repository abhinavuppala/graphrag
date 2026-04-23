import json
import re
from dataclasses import dataclass
from pathlib import Path

import tiktoken
from json_repair import repair_json
from openai import OpenAI


SIZE_CAP = 500_000  # 500 KB

SKIP_DIRS = {
    ".git", ".github", ".gitlab", ".svn",
    "node_modules", "vendor", "third_party",
    "__pycache__", ".venv", "venv", "env",
    "dist", "build", "target", ".gradle", ".cargo",
    "Pods", ".idea", ".vscode", ".claude"
}

SKIP_EXTENSIONS = {
    # Images / media
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".bmp", ".webp", ".svg",
    ".mp3", ".mp4", ".wav", ".avi", ".woff", ".woff2", ".ttf", ".eot",
    # Documents
    ".pdf", ".docx", ".xlsx", ".pptx",
    # Compiled / binary
    ".exe", ".dll", ".so", ".a", ".lib", ".dylib",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".whl", ".egg",
    ".pyc", ".pyo", ".class", ".o", ".obj",
    # Lockfiles
    ".lock", ".sum",
}

_GENERATED = re.compile(
    r"(\.pb\.go|_gen\.go|\.generated\.|_generated\.|"
    r"\.pb\.|\.min\.js|\.min\.css|\.snap$)"
)

_TEST_FILE = re.compile(
    r"(_test\.go|test_[^/\\]+\.py|[^/\\]+_test\.py|"
    r"\.(test|spec)\.(ts|js|tsx|jsx|mjs)$|_spec\.rb$)"
)

_MANIFEST_TOKEN_LIMIT = 40_000


@dataclass
class FileEntry:
    path: str
    size: int
    ext: str


@dataclass
class SelectionResult:
    included: list[dict]    # [{"path": str, "reason": str}]
    excluded: list[str]     # paths not selected
    detected_language: str
    detected_framework: str
    summary: str


def build_manifest(repo_path: Path, size_cap: int = SIZE_CAP) -> list[FileEntry]:
    """Walk repo tree and return candidate files after basic pre-filtering."""
    entries = []
    for file_path in sorted(repo_path.rglob("*")):
        if not file_path.is_file():
            continue
        rel = file_path.relative_to(repo_path)
        parts = rel.parts

        # Skip hidden dirs and known noise dirs
        if any(p in SKIP_DIRS or (p.startswith(".") and p not in {".env", ".envrc"}) for p in parts[:-1]):
            continue

        ext = file_path.suffix.lower()
        name = file_path.name

        if ext in SKIP_EXTENSIONS:
            continue
        if _GENERATED.search(name):
            continue
        if _TEST_FILE.search(name):
            continue

        try:
            size = file_path.stat().st_size
        except OSError:
            continue

        if size > size_cap:
            continue

        rel_str = str(rel).replace("\\", "/")
        entries.append(FileEntry(path=rel_str, size=size, ext=ext))

    return entries


def _format_manifest(entries: list[FileEntry]) -> str:
    lines = [f"{e.path} ({e.size / 1024:.1f}KB)" for e in entries]
    return "\n".join(lines)


def _truncate_to_tokens(text: str, limit: int) -> tuple[str, bool]:
    enc = tiktoken.get_encoding("cl100k_base")
    tokens = enc.encode(text)
    if len(tokens) <= limit:
        return text, False
    truncated = enc.decode(tokens[:limit])
    last_nl = truncated.rfind("\n")
    return truncated[:last_nl] + "\n[... truncated — token budget reached ...]", True


def select_files(
    entries: list[FileEntry],
    api_key: str,
    model: str = "gpt-4o-mini",
) -> SelectionResult:
    """Call LLM to select which files are relevant for GraphRAG indexing."""
    all_paths = {e.path for e in entries}
    manifest_text = _format_manifest(entries)
    manifest_text, was_truncated = _truncate_to_tokens(manifest_text, _MANIFEST_TOKEN_LIMIT)
    if was_truncated:
        print(f"  [warn] Manifest truncated to {_MANIFEST_TOKEN_LIMIT} tokens")

    prompt = f"""You are selecting source files from a GitHub repository to index with GraphRAG for building a knowledge graph.

SELECT files that explain HOW the system works:
- Core business logic and algorithms
- API / protocol / interface definitions
- Data structures and schemas
- Configuration structs and constants
- Important abstractions and entry points
- README if it contains substantive architecture docs

EXCLUDE:
- Test files (anything with _test., test_, .spec., .test.)
- Generated / protobuf files
- Lockfiles, changelogs, CI/CD configs, Makefiles
- Migration scripts, seed/fixture data
- Documentation-only .md files (except top-level README)

Repository file manifest (path, size):
{manifest_text}

Return JSON only (no markdown fences):
{{
  "detected_language": "...",
  "detected_framework": "...",
  "summary": "one sentence: what you selected and why",
  "included": [
    {{"path": "exact/path/from/manifest.go", "reason": "brief reason"}}
  ]
}}

Only list files in "included". Unlisted files are treated as excluded.
Paths must match exactly as shown in the manifest."""

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0,
    )

    raw = response.choices[0].message.content or "{}"
    data = json.loads(repair_json(raw))

    included = data.get("included", [])
    # Filter out any paths the LLM hallucinated that aren't in the manifest
    included = [item for item in included if item.get("path") in all_paths]
    included_paths = {item["path"] for item in included}
    excluded = sorted(all_paths - included_paths)

    return SelectionResult(
        included=included,
        excluded=excluded,
        detected_language=data.get("detected_language", "unknown"),
        detected_framework=data.get("detected_framework", "unknown"),
        summary=data.get("summary", ""),
    )
