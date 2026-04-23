"""
Tests for pipeline/ingest — no network, no API calls.

Run: pytest tests/test_ingest.py -v
"""
import json
import subprocess
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pipeline.ingest.clone import clone_repo
from pipeline.ingest.convert import _safe_filename, convert_files
from pipeline.ingest.select import (
    FileEntry,
    SelectionResult,
    build_manifest,
    select_files,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def fake_repo(tmp_path: Path) -> Path:
    """Minimal fake repo with a mix of source, test, binary, and noise files."""
    files = {
        # Should be included
        "server/server.go":        "package main\nfunc main() {}",
        "server/client.go":        "package main",
        "config/config.go":        "package config",
        "api/handler.go":          "package api",
        "README.md":               "# Project\nArchitecture docs here.",
        # Should be excluded — test files
        "server/server_test.go":   "package main\nfunc TestX(t *testing.T) {}",
        "tests/test_client.py":    "def test_foo(): pass",
        # Should be excluded — skip dirs
        "vendor/lib/lib.go":       "package lib",
        "node_modules/pkg/x.js":   "module.exports = {}",
        "__pycache__/cache.pyc":   b"\x00\x01\x02",
        # Should be excluded — skip extensions
        "assets/logo.png":         b"\x89PNG",
        "dist/bundle.js.map":      "{}",
        "go.sum":                  "hash/1.0 h1:abc=",
        # Should be excluded — generated pattern
        "proto/types.pb.go":       "// Code generated",
        "gen/schema_gen.go":       "// generated",
    }

    for rel, content in files.items():
        dest = fake_repo_path = tmp_path / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            dest.write_bytes(content)
        else:
            dest.write_text(content, encoding="utf-8")

    return tmp_path


# ---------------------------------------------------------------------------
# build_manifest
# ---------------------------------------------------------------------------

class TestBuildManifest:
    def test_includes_source_files(self, fake_repo):
        entries = build_manifest(fake_repo)
        paths = {e.path for e in entries}
        assert "server/server.go" in paths
        assert "server/client.go" in paths
        assert "config/config.go" in paths
        assert "api/handler.go" in paths

    def test_includes_readme(self, fake_repo):
        entries = build_manifest(fake_repo)
        paths = {e.path for e in entries}
        assert "README.md" in paths

    def test_excludes_test_files(self, fake_repo):
        entries = build_manifest(fake_repo)
        paths = {e.path for e in entries}
        assert "server/server_test.go" not in paths
        assert "tests/test_client.py" not in paths

    def test_excludes_skip_dirs(self, fake_repo):
        entries = build_manifest(fake_repo)
        paths = {e.path for e in entries}
        assert not any(p.startswith("vendor/") for p in paths)
        assert not any(p.startswith("node_modules/") for p in paths)
        assert not any(p.startswith("__pycache__/") for p in paths)

    def test_excludes_skip_extensions(self, fake_repo):
        entries = build_manifest(fake_repo)
        paths = {e.path for e in entries}
        assert "assets/logo.png" not in paths
        assert "go.sum" not in paths

    def test_excludes_generated_patterns(self, fake_repo):
        entries = build_manifest(fake_repo)
        paths = {e.path for e in entries}
        assert "proto/types.pb.go" not in paths
        assert "gen/schema_gen.go" not in paths

    def test_size_cap(self, tmp_path):
        big = tmp_path / "big.go"
        big.write_bytes(b"x" * 600_000)
        small = tmp_path / "small.go"
        small.write_text("package main", encoding="utf-8")

        entries = build_manifest(tmp_path, size_cap=500_000)
        paths = {e.path for e in entries}
        assert "big.go" not in paths
        assert "small.go" in paths

    def test_entry_fields(self, fake_repo):
        entries = build_manifest(fake_repo)
        entry = next(e for e in entries if e.path == "server/server.go")
        assert entry.ext == ".go"
        assert entry.size > 0

    def test_paths_use_forward_slashes(self, fake_repo):
        entries = build_manifest(fake_repo)
        assert all("\\" not in e.path for e in entries)


# ---------------------------------------------------------------------------
# _safe_filename
# ---------------------------------------------------------------------------

class TestSafeFilename:
    def test_basic(self):
        assert _safe_filename("server/main.go") == "server__main.txt"

    def test_nested(self):
        assert _safe_filename("a/b/c/file.py") == "a__b__c__file.txt"

    def test_top_level(self):
        assert _safe_filename("README.md") == "README.txt"

    def test_no_extension(self):
        assert _safe_filename("Makefile") == "Makefile.txt"


# ---------------------------------------------------------------------------
# convert_files
# ---------------------------------------------------------------------------

class TestConvertFiles:
    def test_writes_file_with_header(self, fake_repo, tmp_path):
        selected = [{"path": "server/server.go", "reason": "core logic"}]
        written = convert_files(fake_repo, selected, tmp_path / "out")
        assert len(written) == 1
        content = written[0].read_text(encoding="utf-8")
        assert content.startswith("=== FILE: server/server.go ===")
        assert "package main" in content

    def test_output_extension_is_txt(self, fake_repo, tmp_path):
        selected = [{"path": "server/client.go", "reason": "x"}]
        written = convert_files(fake_repo, selected, tmp_path / "out")
        assert written[0].suffix == ".txt"

    def test_deduplicates_filenames(self, tmp_path):
        # Two files that flatten to the same name
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        (tmp_path / "a" / "main.go").write_text("package a", encoding="utf-8")
        (tmp_path / "b" / "main.go").write_text("package b", encoding="utf-8")
        selected = [
            {"path": "a/main.go", "reason": "x"},
            {"path": "b/main.go", "reason": "x"},
        ]
        out = tmp_path / "out"
        written = convert_files(tmp_path, selected, out)
        names = [f.name for f in written]
        assert len(set(names)) == 2, f"Duplicate filenames: {names}"

    def test_skips_missing_file(self, tmp_path):
        selected = [{"path": "does/not/exist.go", "reason": "x"}]
        written = convert_files(tmp_path, selected, tmp_path / "out")
        assert written == []

    def test_creates_output_dir(self, fake_repo, tmp_path):
        out = tmp_path / "deep" / "nested" / "out"
        assert not out.exists()
        convert_files(fake_repo, [{"path": "server/server.go", "reason": "x"}], out)
        assert out.exists()


# ---------------------------------------------------------------------------
# select_files (mocked OpenAI)
# ---------------------------------------------------------------------------

class TestSelectFiles:
    def _mock_response(self, data: dict) -> MagicMock:
        msg = MagicMock()
        msg.content = json.dumps(data)
        choice = MagicMock()
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]
        return resp

    def _entries(self, paths: list[str]) -> list[FileEntry]:
        return [FileEntry(path=p, size=100, ext=Path(p).suffix) for p in paths]

    @patch("pipeline.ingest.select.OpenAI")
    def test_returns_selection_result(self, mock_openai):
        entries = self._entries(["server/main.go", "server/client.go"])
        llm_data = {
            "detected_language": "Go",
            "detected_framework": "NATS",
            "summary": "Selected core server files.",
            "included": [
                {"path": "server/main.go", "reason": "entry point"},
            ],
        }
        mock_openai.return_value.chat.completions.create.return_value = (
            self._mock_response(llm_data)
        )
        result = select_files(entries, api_key="test-key")
        assert isinstance(result, SelectionResult)
        assert result.detected_language == "Go"
        assert result.detected_framework == "NATS"
        assert len(result.included) == 1
        assert result.included[0]["path"] == "server/main.go"
        assert "server/client.go" in result.excluded

    @patch("pipeline.ingest.select.OpenAI")
    def test_filters_hallucinated_paths(self, mock_openai):
        entries = self._entries(["real/file.go"])
        llm_data = {
            "detected_language": "Go",
            "detected_framework": "x",
            "summary": "x",
            "included": [
                {"path": "real/file.go", "reason": "real"},
                {"path": "hallucinated/fake.go", "reason": "does not exist"},
            ],
        }
        mock_openai.return_value.chat.completions.create.return_value = (
            self._mock_response(llm_data)
        )
        result = select_files(entries, api_key="test-key")
        included_paths = [i["path"] for i in result.included]
        assert "hallucinated/fake.go" not in included_paths
        assert "real/file.go" in included_paths

    @patch("pipeline.ingest.select.OpenAI")
    def test_excluded_is_manifest_minus_included(self, mock_openai):
        entries = self._entries(["a.go", "b.go", "c.go"])
        llm_data = {
            "detected_language": "Go", "detected_framework": "x", "summary": "x",
            "included": [{"path": "a.go", "reason": "x"}],
        }
        mock_openai.return_value.chat.completions.create.return_value = (
            self._mock_response(llm_data)
        )
        result = select_files(entries, api_key="test-key")
        assert set(result.excluded) == {"b.go", "c.go"}


# ---------------------------------------------------------------------------
# clone_repo
# ---------------------------------------------------------------------------

class TestCloneRepo:
    @patch("pipeline.ingest.clone.subprocess.run")
    def test_shallow_clone_default(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0)
        clone_repo("https://github.com/org/repo.git", clone_root=tmp_path)
        cmd = mock_run.call_args[0][0]
        assert "--depth=1" in cmd

    @patch("pipeline.ingest.clone.subprocess.run")
    def test_full_clone_when_depth_none(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0)
        clone_repo("https://github.com/org/repo.git", clone_root=tmp_path, depth=None)
        cmd = mock_run.call_args[0][0]
        assert not any(a.startswith("--depth") for a in cmd)

    @patch("pipeline.ingest.clone.subprocess.run")
    def test_custom_depth(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0)
        clone_repo("https://github.com/org/repo.git", clone_root=tmp_path, depth=5)
        cmd = mock_run.call_args[0][0]
        assert "--depth=5" in cmd

    def test_skips_if_already_cloned(self, tmp_path):
        dest = tmp_path / "repo"
        (dest / ".git").mkdir(parents=True)
        # Should not call git at all
        with patch("pipeline.ingest.clone.subprocess.run") as mock_run:
            result = clone_repo("https://github.com/org/repo.git", clone_root=tmp_path)
            mock_run.assert_not_called()
        assert result == dest

    @patch("pipeline.ingest.clone.subprocess.run")
    def test_raises_on_clone_failure(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=1, stderr="fatal: repo not found")
        with pytest.raises(RuntimeError, match="git clone failed"):
            clone_repo("https://github.com/org/bad.git", clone_root=tmp_path)

    @patch("pipeline.ingest.clone.subprocess.run")
    def test_strips_git_suffix_from_repo_name(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0)
        result = clone_repo("https://github.com/org/myrepo.git", clone_root=tmp_path)
        assert result.name == "myrepo"
