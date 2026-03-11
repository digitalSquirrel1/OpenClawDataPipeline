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

from pathlib import Path
import yaml

# user_simulator_agent/ (project root)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_FILE = _PROJECT_ROOT / "config" / "baseline_using.yaml"

_config = None  # type: dict


def load_config() -> dict:
    """Load and cache baseline.yaml. Returns empty dict on error."""
    global _config
    if _config is None:
        try:
            with open(_CONFIG_FILE, encoding="utf-8") as f:
                _config = yaml.safe_load(f) or {}
        except FileNotFoundError:
            print(f"[config_loader] Warning: config file not found: {_CONFIG_FILE}")
            _config = {}
    return _config


def get_prompt(prompt_rel_path: str) -> str:
    """
    Read a prompt file at path relative to the project root.
    E.g. get_prompt("prompts/profile_generation_prompt.md")
    """
    prompt_path = _PROJECT_ROOT / prompt_rel_path
    return prompt_path.read_text(encoding="utf-8")
