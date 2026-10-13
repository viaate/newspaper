import os
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SECRET_NAMES = (
    "SCHOOLOGY_KEY",
    "SCHOOLOGY_SECRET",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_WORKSPACE_ID",
    "GEMINI_API_KEY",
    "GMAIL_ADDRESS",
    "GMAIL_APP_PASSWORD",
    "CALENDAR_URLS",
    "ARCHIVE_GITHUB_TOKEN",
)


def _read_dotenv(path):
    values = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load(path=None):
    """Settings from config.toml (or the example) plus secrets from .env / the environment."""
    path = Path(path) if path else ROOT / "config.toml"
    if not path.exists():
        path = ROOT / "config.example.toml"
    with open(path, "rb") as f:
        cfg = tomllib.load(f)

    dotenv = _read_dotenv(ROOT / ".env")
    cfg["secrets"] = {
        name: os.environ.get(name) or dotenv.get(name) or "" for name in SECRET_NAMES
    }
    cfg["data_dir"] = ROOT / "data"
    cfg["out_dir"] = ROOT / "out"
    return cfg
