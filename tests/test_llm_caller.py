# -*- coding: utf-8 -*-
"""验证 shared/llm_caller 和修改后的 llm_client / generate_user_profile 都能正常导入"""
import sys
import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent          # user_simulator_agent/
_WS   = _ROOT / "WorkingSpace"
sys.path.insert(0, str(_WS))
sys.path.insert(0, str(_ROOT))

# 1. shared/llm_caller
from shared.llm_caller import chat_with_retry, LLM_BASE_URL, LLM_MODEL, LLM_API_KEY
print(f"[1] shared.llm_caller OK  model={LLM_MODEL}  base_url={LLM_BASE_URL}")

# 2. llm_client uses chat_with_retry
from utils.llm_client import LLMClient, chat_with_retry as cwr2
assert chat_with_retry is cwr2, "llm_client should re-export the same chat_with_retry"
lc = LLMClient(api_key=LLM_API_KEY, base_url=LLM_BASE_URL, model=LLM_MODEL)
print(f"[2] llm_client.LLMClient OK  backend={lc.backend}")

# 3. generate_user_profile.ProfileGenerator
spec = importlib.util.spec_from_file_location(
    'gen',
    str(_ROOT / 'ControlCenter' / 'generate_user_profile.py')
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
pg = mod.ProfileGenerator(model='gpt-5.2')
assert pg.model == 'gpt-5.2'
assert not hasattr(pg, 'client'), "ProfileGenerator should no longer have self.client"
print(f"[3] generate_user_profile.ProfileGenerator OK  model={pg.model}")

print("\nAll OK")
