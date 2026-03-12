# -*- coding: utf-8 -*-
import os, sys, ssl, httpx
from pathlib import Path
from openai import OpenAI
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.config_loader import load_config
_api_cfg = load_config().get("api_config", {})

LLM_API_KEY  = os.getenv("LLM_API_KEY",  _api_cfg.get("LLM_API_KEY",  ""))
LLM_BASE_URL = os.getenv("LLM_BASE_URL", _api_cfg.get("LLM_BASE_URL", "https://api.openai.com/v1"))
LLM_MODEL    = os.getenv("LLM_MODEL",    _api_cfg.get("LLM_MODEL",       "gpt-4o"))

ssl._create_default_https_context = ssl._create_unverified_context
client = OpenAI(
    api_key=LLM_API_KEY,
    base_url=LLM_BASE_URL,
    http_client=httpx.Client(verify=False, timeout=30),
)

resp = client.chat.completions.create(
    model=LLM_MODEL,
    messages=[{"role": "user", "content": "hello"}],
    max_tokens=50,
)

msg = resp.choices[0].message
print("=== raw message fields ===")
print(f"content          : {msg.content!r}")
print(f"role             : {msg.role!r}")
print(f"model_fields     : {list(msg.model_fields_set)}")
# Some reasoning models put output in extra fields
print(f"model_extra      : {msg.model_extra}")
print(f"finish_reason    : {resp.choices[0].finish_reason!r}")
