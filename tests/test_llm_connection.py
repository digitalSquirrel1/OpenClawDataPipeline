# -*- coding: utf-8 -*-
"""
Simple LLM connectivity test and reusable health-check helper.
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent  # user_simulator_agent/
sys.path.insert(0, str(_ROOT))

from shared.llm_caller import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_PROXY, chat_with_retry

EVAL_COUNT = 10


def check_llm_connection(
    prompt: str = "请用一句话回复：连接测试成功。",
    max_retries: int = 2,
) -> dict:
    """Single-shot LLM connectivity check for runner reuse."""
    try:
        reply = chat_with_retry(
            messages=[{"role": "user", "content": prompt}],
            model=LLM_MODEL,
            max_retries=max_retries,
        )
    except Exception as exc:
        return {
            "status": "fail",
            "http_status": None,
            "summary": f"{type(exc).__name__}: {exc}",
            "raw_excerpt": "",
        }

    reply = (reply or "").strip()
    if not reply:
        return {
            "status": "fail",
            "http_status": None,
            "summary": "LLM returned empty response",
            "raw_excerpt": "",
        }

    lowered = reply.lower()
    if any(word in lowered for word in ("quota", "insufficient", "unauthorized", "invalid api key")):
        return {
            "status": "fail",
            "http_status": None,
            "summary": "LLM returned auth/quota related message",
            "raw_excerpt": reply[:500],
        }

    return {
        "status": "ok",
        "http_status": 200,
        "summary": "LLM returned non-empty response",
        "raw_excerpt": reply[:500],
    }


def main() -> int:
    print(f"BASE_URL   : {LLM_BASE_URL}")
    print(f"MODEL      : {LLM_MODEL}")
    masked_key = f"{LLM_API_KEY[:8]}...{LLM_API_KEY[-4:]}" if LLM_API_KEY else "(empty)"
    print(f"API_KEY    : {masked_key}")
    print(f"PROXY      : {LLM_PROXY if LLM_PROXY else '(none)'}")
    print(f"EVAL_COUNT : {EVAL_COUNT}")
    print("=" * 60)

    successes = 0
    for i in range(1, EVAL_COUNT + 1):
        print(f"[{i:02d}/{EVAL_COUNT}] ", end="", flush=True)
        result = check_llm_connection(prompt="你叫什么名字？", max_retries=5)
        if result["status"] == "ok":
            successes += 1
            short = result["raw_excerpt"][:60].replace("\n", " ")
            print(f"PASS  {short!r}")
        else:
            print(f"FAIL  {result['summary']}")

    print("=" * 60)
    print(f"Success: {successes}/{EVAL_COUNT}  ({successes / EVAL_COUNT * 100:.1f}%)")
    return 0 if successes > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
