import shutil
from pathlib import Path

import yaml

from .detect import DomainConfig

_TEMPLATE = Path(__file__).parent / "templates" / "settings_base.yaml"

# Prompts source: committed graphrag/prompts/ at repo root
_PROMPTS_SOURCE = Path(__file__).parents[2] / "graphrag" / "prompts"


def render_settings(domain: DomainConfig) -> str:
    """Load base template and inject domain-specific entity_types."""
    data = yaml.safe_load(_TEMPLATE.read_text(encoding="utf-8"))
    data["extract_graph"]["entity_types"] = domain.entity_types
    return yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)


def setup_workspace(workspace_dir: Path, domain: DomainConfig, api_key: str) -> list[str]:
    """
    Ensure workspace has settings.yaml, .env, and prompts/.
    Returns human-readable list of actions taken.
    """
    workspace_dir.mkdir(parents=True, exist_ok=True)
    actions: list[str] = []

    settings_path = workspace_dir / "settings.yaml"
    if not settings_path.exists():
        settings_path.write_text(render_settings(domain), encoding="utf-8")
        actions.append(f"wrote settings.yaml (domain: {domain.name}, entities: {len(domain.entity_types)})")
    else:
        actions.append("settings.yaml exists — skipped")

    env_path = workspace_dir / ".env"
    if not env_path.exists():
        env_path.write_text(f"GRAPHRAG_API_KEY={api_key}\n", encoding="utf-8")
        actions.append("wrote .env with GRAPHRAG_API_KEY")
    else:
        actions.append(".env exists — skipped")

    prompts_dir = workspace_dir / "prompts"
    if not prompts_dir.exists():
        if _PROMPTS_SOURCE.is_dir():
            shutil.copytree(_PROMPTS_SOURCE, prompts_dir)
            actions.append(f"copied prompts/ from {_PROMPTS_SOURCE.relative_to(Path.cwd())}")
        else:
            actions.append(
                "WARNING: prompts/ not found — run `graphrag prompt-tune --root ./graphrag` first"
            )
    else:
        actions.append("prompts/ exists — skipped")

    (workspace_dir / "input").mkdir(exist_ok=True)

    return actions
