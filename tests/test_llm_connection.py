# -*- coding: utf-8 -*-
"""
Test that LLM_API_KEY and LLM_BASE_URL from generate_user_profile.py work correctly.

Sends N one-shot requests and reports success rate (no exception + non-empty reply).
每次调用通过 shared/llm_caller.chat_with_retry() 进行（自带 5 次 retry）。

Run:
    conda activate datapipe
    python user_simulator_agent/tests/test_llm_connection.py
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent  # user_simulator_agent/
sys.path.insert(0, str(_ROOT))

from shared.llm_caller import chat_with_retry, LLM_BASE_URL, LLM_MODEL, LLM_API_KEY, LLM_PROXY

# ── Evaluation config ────────────────────────────────────────────────────────
EVAL_COUNT = 10   # number of requests to send

print(f"BASE_URL   : {LLM_BASE_URL}")
print(f"MODEL      : {LLM_MODEL}")
print(f"API_KEY    : {LLM_API_KEY[:8]}...{LLM_API_KEY[-4:]}")
print(f"PROXY      : {LLM_PROXY if LLM_PROXY else '(none)'}")
print(f"EVAL_COUNT : {EVAL_COUNT}")
print("=" * 60)

successes = 0

for i in range(1, EVAL_COUNT + 1):
    print(f"[{i:02d}/{EVAL_COUNT}] ", end="", flush=True)
    try:
        reply = chat_with_retry(
            messages=[{"role": "user", "content": "你叫什么名字"}],
            model=LLM_MODEL,
            max_retries=5,
        )
        if reply is None:
            reply = ""
        reply = reply.strip()

        if reply:
            successes += 1
            short = reply[:60].replace("\n", " ")
            print(f"PASS  {short!r}, {reply=}")
        else:
            print("FAIL  reply is empty string")
    except Exception as e:
        print(f"FAIL  {e}")

print("=" * 60)
print(f"Success: {successes}/{EVAL_COUNT}  ({successes/EVAL_COUNT*100:.1f}%)")
sys.exit(0 if successes > 0 else 1)
