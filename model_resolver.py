"""Model resolver — resolves which LLM model to use for a given role.

Cascade: per-character → per-story → site role default → DEFAULT_MODEL
"""

import json
import os

MODEL_SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "model_settings.json")
VALID_ROLES = {"creative", "dialogue", "classification", "summarization", "tools"}


def _load_settings() -> dict:
    if os.path.exists(MODEL_SETTINGS_PATH):
        try:
            with open(MODEL_SETTINGS_PATH) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


# Thread-local session override for A/B testing
_session_override: dict[str, str] = {}


def set_session_model_override(model: str):
    """Set a temporary model override for all roles (used by A/B testing)."""
    _session_override["model"] = model


def clear_session_model_override():
    """Clear the temporary override."""
    _session_override.pop("model", None)


def get_model_for_role(role: str, story_override: str = "", character_override: str = "") -> str:
    """Resolve a model for a given role using the cascade.

    Priority: session_override → character_override → story_override → site role default → DEFAULT_MODEL
    """
    from config import DEFAULT_MODEL

    # Session override (A/B testing)
    session_model = _session_override.get("model", "")
    if session_model:
        return session_model

    # Per-character override
    if character_override and character_override != "default":
        return character_override

    # Per-story override
    if story_override and story_override != "default":
        return story_override

    # Site role default
    settings = _load_settings()
    roles = settings.get("roles", {})
    role_model = roles.get(role, "")
    if role_model and role_model != "default":
        return role_model

    # Fall back to DEFAULT_MODEL
    return DEFAULT_MODEL


def save_role_settings(roles: dict):
    """Save role → model mapping."""
    settings = _load_settings()
    cleaned = {k: v for k, v in roles.items() if k in VALID_ROLES and isinstance(v, str)}
    settings["roles"] = cleaned
    with open(MODEL_SETTINGS_PATH, "w") as f:
        json.dump(settings, f, indent=2)


def load_role_settings() -> dict:
    """Load saved role → model mapping."""
    return _load_settings()
