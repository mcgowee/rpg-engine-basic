"""Configuration — loads .env and exposes all settings."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent


def get_env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


# --- Flask ---
SECRET_KEY = get_env("SECRET_KEY", "dev-secret-change-me")
FLASK_HOST = get_env("FLASK_HOST", "0.0.0.0")
FLASK_PORT = int(get_env("FLASK_PORT", "5051"))
FLASK_DEBUG = get_env("FLASK_DEBUG", "").lower() in ("1", "true", "yes")

# --- LLM ---
LLM_PROVIDER = get_env("LLM_PROVIDER", "ollama")
DEFAULT_MODEL = get_env("DEFAULT_MODEL", "nchapman/mn-12b-mag-mell-r1:latest")
OLLAMA_HOST = get_env("OLLAMA_HOST", "http://localhost:11434")

# Azure
AZURE_ENDPOINT = get_env("AZURE_OPENAI_ENDPOINT", "")
AZURE_API_KEY = get_env("AZURE_OPENAI_API_KEY", "")
AZURE_API_VERSION = get_env("AZURE_API_VERSION", "2024-12-01-preview")
AZURE_DEPLOYMENT = get_env("AZURE_DEPLOYMENT", "gpt-4o-mini")

# --- Paths ---
GRAPHS_DIR = Path(get_env("GRAPHS_DIR", str(BASE_DIR / "graphs")))

# --- Game settings ---
SAVE_SLOTS = int(get_env("SAVE_SLOTS", "5"))


def ensure_dirs():
    GRAPHS_DIR.mkdir(parents=True, exist_ok=True)


ensure_dirs()
