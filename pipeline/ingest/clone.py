import subprocess
import tempfile
from pathlib import Path


def clone_repo(url: str, clone_root: Path | None = None, depth: int | None = 1) -> Path:
    """Clone a GitHub repo. depth=1 for shallow (default), None for full history."""
    repo_name = url.rstrip("/").split("/")[-1].removesuffix(".git")
    if clone_root is None:
        clone_root = Path(tempfile.gettempdir()) / "graphrag_ingest"
    clone_root = Path(clone_root)
    clone_root.mkdir(parents=True, exist_ok=True)
    dest = clone_root / repo_name
    if (dest / ".git").exists():
        print(f"  Already cloned: {dest}")
        return dest
    depth_str = f"depth={depth}" if depth is not None else "full"
    print(f"  Cloning {url} ({depth_str}) ...")
    cmd = ["git", "clone"]
    if depth is not None:
        cmd.append(f"--depth={depth}")
    cmd += [url, str(dest)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"git clone failed:\n{result.stderr}")
    print(f"  Done: {dest}")
    return dest
