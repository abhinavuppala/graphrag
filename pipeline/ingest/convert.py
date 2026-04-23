import re
from pathlib import Path


def _safe_filename(rel_path: str) -> str:
    """Convert a relative path to a flat .txt filename. server/main.go → server__main.txt"""
    without_ext = re.sub(r"\.[^./\\]+$", "", rel_path)
    safe = without_ext.replace("/", "__").replace("\\", "__")
    safe = re.sub(r"[^\w\-.]", "_", safe)
    return safe + ".txt"


def convert_files(
    repo_path: Path,
    selected: list[dict],  # [{"path": str, "reason": str}]
    output_dir: Path,
) -> list[Path]:
    """Write selected source files as .txt with a path header into output_dir."""
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    name_counts: dict[str, int] = {}

    for item in selected:
        rel_path = item["path"]
        src = repo_path / rel_path
        if not src.exists():
            print(f"  [warn] Not found, skipping: {rel_path}")
            continue

        name = _safe_filename(rel_path)
        if name in name_counts:
            name_counts[name] += 1
            stem = name[:-4]
            name = f"{stem}_{name_counts[name]}.txt"
        else:
            name_counts[name] = 0

        dest = output_dir / name
        try:
            content = src.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            print(f"  [warn] Could not read {rel_path}: {e}")
            continue

        dest.write_text(f"=== FILE: {rel_path} ===\n\n{content}", encoding="utf-8")
        written.append(dest)

    return written
