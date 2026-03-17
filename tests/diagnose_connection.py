# -*- coding: utf-8 -*-
"""
Connectivity diagnosis: tests both direct and proxy connections.
Run: conda activate datapipe && python user_simulator_agent/tests/diagnose_connection.py
"""
import os, sys, ssl, httpx
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.config_loader import load_config
_api_cfg = load_config().get("api_config", {})

LLM_API_KEY  = os.getenv("LLM_API_KEY",  _api_cfg.get("LLM_API_KEY",  ""))
LLM_BASE_URL = os.getenv("LLM_BASE_URL", _api_cfg.get("LLM_BASE_URL", "https://api.openai.com/v1"))
LLM_PROXY    = os.getenv("LLM_PROXY",    _api_cfg.get("LLM_PROXY",       ""))

ssl._create_default_https_context = ssl._create_unverified_context
HEADERS = {"Authorization": f"Bearer {LLM_API_KEY}"}
URL = f"{LLM_BASE_URL}/models"

print(f"Target URL : {URL}")
print(f"Proxy      : {LLM_PROXY}")
print("-" * 50)

# 1. Direct connection (no proxy)
print("[1] Direct connection...")
try:
    r = httpx.get(URL, headers=HEADERS, verify=False, timeout=10)
    print(f"    Status: {r.status_code}  => {'OK' if r.status_code < 400 else 'FAIL'}")
    print(f"    Body: {r.text[:120]}")
except Exception as e:
    print(f"    FAIL: {e}")

# 2. Via proxy
print(f"[2] Proxy connection ({LLM_PROXY})...")
try:
    r = httpx.get(URL, headers=HEADERS, proxy=LLM_PROXY, verify=False, timeout=10)
    print(f"    Status: {r.status_code}  => {'OK' if r.status_code < 400 else 'FAIL'}")
    print(f"    Body: {r.text[:120]}")
except Exception as e:
    print(f"    FAIL: {e}")
