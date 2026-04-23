"""
Tests for pipeline/config — no network, no API calls.

Run: pytest tests/test_config.py -v
"""
import yaml
import pytest
from pathlib import Path

from pipeline.config.detect import detect_domain, DOMAINS
from pipeline.config.settings_gen import render_settings, setup_workspace


# ---------------------------------------------------------------------------
# detect_domain
# ---------------------------------------------------------------------------

class TestDetectDomain:
    def test_nats_is_pubsub(self):
        assert detect_domain("NATS pub-sub messaging", "Go").name == "pub-sub"

    def test_kafka_is_pubsub(self):
        assert detect_domain("Kafka event stream", "Java").name == "pub-sub"

    def test_jetstream_is_pubsub(self):
        assert detect_domain("JetStream", "Go").name == "pub-sub"

    def test_fastapi_is_webapi(self):
        assert detect_domain("FastAPI REST service", "Python").name == "web-api"

    def test_grpc_is_webapi(self):
        assert detect_domain("gRPC server", "Go").name == "web-api"

    def test_postgres_is_database(self):
        assert detect_domain("Postgres database engine", "C").name == "database"

    def test_unknown_defaults_to_pubsub(self):
        # All current clients are pub-sub; unknown framework falls back to it
        assert detect_domain("some unknown framework", "Rust").name == "pub-sub"

    def test_case_insensitive(self):
        assert detect_domain("KAFKA BROKER", "SCALA").name == "pub-sub"

    def test_returns_domain_config_with_entity_types(self):
        result = detect_domain("nats-server", "Go")
        assert isinstance(result.entity_types, list)
        assert len(result.entity_types) > 0

    def test_pubsub_entity_types_contain_topic(self):
        result = detect_domain("nats", "Go")
        assert "topic" in result.entity_types

    def test_webapi_entity_types_contain_endpoint(self):
        result = detect_domain("fastapi rest api", "Python")
        assert "endpoint" in result.entity_types


# ---------------------------------------------------------------------------
# render_settings
# ---------------------------------------------------------------------------

class TestRenderSettings:
    def test_produces_valid_yaml(self):
        domain = DOMAINS["pub-sub"]
        rendered = render_settings(domain)
        data = yaml.safe_load(rendered)
        assert isinstance(data, dict)

    def test_entity_types_injected(self):
        domain = DOMAINS["pub-sub"]
        rendered = render_settings(domain)
        data = yaml.safe_load(rendered)
        assert data["extract_graph"]["entity_types"] == domain.entity_types

    def test_webapi_entity_types_injected(self):
        domain = DOMAINS["web-api"]
        rendered = render_settings(domain)
        data = yaml.safe_load(rendered)
        assert "endpoint" in data["extract_graph"]["entity_types"]

    def test_correct_completion_model(self):
        rendered = render_settings(DOMAINS["pub-sub"])
        data = yaml.safe_load(rendered)
        model = data["completion_models"]["default_completion_model"]["model"]
        assert model == "gpt-4o-mini"

    def test_correct_embedding_model(self):
        rendered = render_settings(DOMAINS["pub-sub"])
        data = yaml.safe_load(rendered)
        model = data["embedding_models"]["default_embedding_model"]["model"]
        assert model == "text-embedding-3-small"

    def test_chunk_size(self):
        rendered = render_settings(DOMAINS["pub-sub"])
        data = yaml.safe_load(rendered)
        assert data["chunking"]["size"] == 1500
        assert data["chunking"]["overlap"] == 200

    def test_claim_extraction_disabled(self):
        rendered = render_settings(DOMAINS["pub-sub"])
        data = yaml.safe_load(rendered)
        assert data["extract_claims"]["enabled"] is False

    def test_api_key_uses_env_var(self):
        rendered = render_settings(DOMAINS["pub-sub"])
        assert "${GRAPHRAG_API_KEY}" in rendered

    def test_lancedb_path_uses_forward_slash(self):
        rendered = render_settings(DOMAINS["pub-sub"])
        data = yaml.safe_load(rendered)
        assert "\\" not in data["vector_store"]["db_uri"]


# ---------------------------------------------------------------------------
# setup_workspace
# ---------------------------------------------------------------------------

class TestSetupWorkspace:
    def test_creates_settings_yaml(self, tmp_path):
        setup_workspace(tmp_path, DOMAINS["pub-sub"], api_key="test-key")
        assert (tmp_path / "settings.yaml").exists()

    def test_settings_yaml_is_valid(self, tmp_path):
        setup_workspace(tmp_path, DOMAINS["pub-sub"], api_key="test-key")
        data = yaml.safe_load((tmp_path / "settings.yaml").read_text())
        assert "extract_graph" in data

    def test_creates_env_file(self, tmp_path):
        setup_workspace(tmp_path, DOMAINS["pub-sub"], api_key="sk-test-123")
        env = (tmp_path / ".env").read_text()
        assert "sk-test-123" in env

    def test_skips_existing_settings(self, tmp_path):
        (tmp_path / "settings.yaml").write_text("existing: true", encoding="utf-8")
        setup_workspace(tmp_path, DOMAINS["pub-sub"], api_key="test-key")
        data = yaml.safe_load((tmp_path / "settings.yaml").read_text())
        assert data == {"existing": True}

    def test_skips_existing_env(self, tmp_path):
        (tmp_path / ".env").write_text("GRAPHRAG_API_KEY=original\n", encoding="utf-8")
        setup_workspace(tmp_path, DOMAINS["pub-sub"], api_key="new-key")
        assert "original" in (tmp_path / ".env").read_text()

    def test_creates_input_dir(self, tmp_path):
        setup_workspace(tmp_path, DOMAINS["pub-sub"], api_key="test-key")
        assert (tmp_path / "input").is_dir()

    def test_creates_workspace_dir_if_missing(self, tmp_path):
        workspace = tmp_path / "new_workspace"
        assert not workspace.exists()
        setup_workspace(workspace, DOMAINS["pub-sub"], api_key="test-key")
        assert workspace.exists()

    def test_returns_action_list(self, tmp_path):
        actions = setup_workspace(tmp_path, DOMAINS["pub-sub"], api_key="test-key")
        assert isinstance(actions, list)
        assert len(actions) > 0
