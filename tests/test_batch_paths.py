import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent  # user_simulator_agent/
sys.path.insert(0, str(_ROOT))

from config.config_loader import load_config

_PROJECT_ROOT = _ROOT
_batch_cfg = load_config().get("batch_generate_config", {})

def _resolve(val, default):
    if not val:
        return str(default)
    p = Path(val)
    return str(p if p.is_absolute() else _PROJECT_ROOT / p)

DEFAULT_ENVS_DIR     = _PROJECT_ROOT / "Outputs" / "environments"
DEFAULT_PROFILES_DIR = _PROJECT_ROOT / "Outputs" / "profiles"

envs   = _resolve(_batch_cfg.get("envs_dir"),     DEFAULT_ENVS_DIR)
profs  = _resolve(_batch_cfg.get("profiles_dir"), DEFAULT_PROFILES_DIR)

print(f"envs_dir   : {envs}")
print(f"profiles_dir: {profs}")

assert envs.replace("\\", "/").endswith("user_simulator_agent/Outputs/environments"), f"Wrong path: {envs}"
print("OK")
