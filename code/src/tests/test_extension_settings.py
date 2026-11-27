"""The extension's local search must use the server's numbers. It fetches them
from GET /search-settings, and falls back to extension/engine/settings.js: those
defaults must equal backend/config.py's."""
import re
from pathlib import Path

from backend import config
from backend.models import SearchSettingsResponse

SETTINGS_JS = Path(__file__).parent.parent / "extension" / "engine" / "settings.js"


def _js_defaults() -> dict:
    block = SETTINGS_JS.read_text(encoding="utf-8").split("DEFAULT_SETTINGS = Object.freeze({", 1)[1].split("});", 1)[0]
    values = {}
    for name, raw in re.findall(r"^\s*([A-Z_0-9]+):\s*(.+?),\s*$", block, re.MULTILINE):
        raw = raw.strip()
        if raw in ("true", "false"):
            values[name] = raw == "true"
        elif raw.startswith('"'):
            values[name] = raw.strip('"')
        else:
            values[name] = float(raw) if "." in raw else int(raw)
    return values


def test_extension_defaults_match_server_config():
    js = _js_defaults()
    names = list(SearchSettingsResponse.model_fields)
    assert sorted(js) == sorted(names)
    for name in names:
        assert js[name] == getattr(config, name), name
