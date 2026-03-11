# -*- coding: utf-8 -*-
"""Verify the batch_generate → main.py refactoring works correctly."""
import sys
import inspect
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent          # user_simulator_agent/
_WS   = _ROOT / "WorkingSpace"
sys.path.insert(0, str(_WS))
sys.path.insert(0, str(_ROOT))

_PROJECT_ROOT = _ROOT

# Test 1: config loads correctly
print("[1] Testing config loader...")
from config.config_loader import load_config
cfg = load_config()
assert "api_config" in cfg
assert "batch_generate_config" in cfg
assert "pipeline_config" in cfg
assert cfg["api_config"]["LLM_BACKEND"] == "openai"
assert cfg["web_tools_config"]["SERPER_KEY"]
assert cfg["pipeline_config"]["MAX_WORKERS"] == 8
print("    OK: config loads with all sections")

# Test 2: run_pipeline is importable
print("[2] Testing run_pipeline import...")
from main import run_pipeline
assert callable(run_pipeline)
print("    OK: run_pipeline imported successfully")

# Test 3: batch_generate path resolution
print("[3] Testing batch_generate path resolution...")
batch_cfg = cfg.get("batch_generate_config", {})
DEFAULT_ENVS_DIR     = _PROJECT_ROOT / "Outputs" / "environments"
DEFAULT_PROFILES_DIR = _PROJECT_ROOT / "Outputs" / "profiles"

def _resolve(val, default):
    if not val:
        return str(default)
    p = Path(val)
    return str(p if p.is_absolute() else _PROJECT_ROOT / p)

envs  = _resolve(batch_cfg.get("envs_dir"),     DEFAULT_ENVS_DIR)
profs = _resolve(batch_cfg.get("profiles_dir"), DEFAULT_PROFILES_DIR)
print(f"    envs_dir   : {envs}")
print(f"    profiles_dir: {profs}")
assert envs.replace("\\", "/").endswith("user_simulator_agent/Outputs/environments"), f"Wrong envs path: {envs}"
assert profs.replace("\\", "/").endswith("user_simulator_agent/Outputs/profiles"), f"Wrong profs path: {profs}"
print("    OK: paths resolve correctly")

# Test 4: file_processor accepts profile_dir_name
print("[4] Testing file_processor signature...")
from agents.file_processor import FileProcessor
sig = inspect.signature(FileProcessor.process)
params = list(sig.parameters.keys())
assert "profile_dir_name" in params, f"Missing profile_dir_name in FileProcessor.process params: {params}"
print(f"    OK: FileProcessor.process params = {params}")

# Test 5: _sanitize_name in main.py
print("[5] Testing _sanitize_name...")
from main import _sanitize_name
assert _sanitize_name("张三_教师") == "张三_教师"
assert _sanitize_name('test:file*name') == 'test_file_name'
print("    OK: _sanitize_name works")

print("\nAll verification tests passed!")
