# -*- coding: utf-8 -*-
"""
Config Loader
=============
Loads baseline.yaml and resolves prompt file paths relative to the
user_simulator_agent project root.

Usage (from any file in the project):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # adjust depth
    from config.config_loader import load_config, get_prompt
"""

import os
from pathlib import Path
import yaml

# user_simulator_agent/ (project root)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_CONFIG_FILE = _PROJECT_ROOT / "config" / "baseline_using.yaml"
_CONFIG_ENV_VAR = "USER_SIMULATOR_CONFIG_PATH"

_config_cache: dict[Path, dict] = {}


def get_config_path() -> Path:
    """Resolve the active config file path."""
    cfg_path = os.getenv(_CONFIG_ENV_VAR)
    if not cfg_path:
        return _DEFAULT_CONFIG_FILE
    path = Path(cfg_path)
    return path if path.is_absolute() else (_PROJECT_ROOT / path).resolve()


def reset_config_cache(config_path: str | Path | None = None) -> None:
    """Clear config cache for one file or all files."""
    global _config_cache
    if config_path is None:
        _config_cache = {}
        return
    path = Path(config_path)
    if not path.is_absolute():
        path = (_PROJECT_ROOT / path).resolve()
    _config_cache.pop(path, None)


def load_config() -> dict:
    """Load and cache baseline.yaml. Returns empty dict on error."""
    config_path = get_config_path()
    if config_path not in _config_cache:
        try:
            with open(config_path, encoding="utf-8") as f:
                _config_cache[config_path] = yaml.safe_load(f) or {}
        except FileNotFoundError:
            print(f"[config_loader] Warning: config file not found: {config_path}")
            _config_cache[config_path] = {}
    return _config_cache[config_path]


def get_prompt(prompt_rel_path: str) -> str:
    """
    Read a prompt file at path relative to the project root.
    E.g. get_prompt("prompts/profile_generation_prompt.md")
    """
    prompt_path = _PROJECT_ROOT / prompt_rel_path
    return prompt_path.read_text(encoding="utf-8")
