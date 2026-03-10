# -*- coding: utf-8 -*-
"""
shared/llm_caller.py
====================
统一的 OpenAI-compatible 客户端初始化 + 带 retry 的 chat completions 调用。

其他模块统一通过 chat_with_retry() 调用，不直接使用 client.chat.completions.create。

用法：
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # 调整到 user_simulator_agent/
    from shared.llm_caller import chat_with_retry, LLM_MODEL
"""

import os
import ssl
import sys
import time
from pathlib import Path

import httpx
from openai import OpenAI

# ─── 项目根路径 & 配置加载 ────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent  # user_simulator_agent/
sys.path.insert(0, str(_PROJECT_ROOT))
from config.config_loader import load_config

_cfg = load_config()
_api = _cfg.get("api_config", {})

LLM_API_KEY  = os.getenv("LLM_API_KEY",  _api.get("LLM_API_KEY",  ""))
LLM_BASE_URL = os.getenv("LLM_BASE_URL", _api.get("LLM_BASE_URL", "https://api.openai.com/v1"))
LLM_MODEL    = os.getenv("LLM_MODEL",    _api.get("LLM_MODEL",    "gpt-4o"))
LLM_PROXY    = os.getenv("LLM_PROXY",    _api.get("LLM_PROXY",    None))

# ─── 全局 client（单例） ──────────────────────────────────────────────────────
ssl._create_default_https_context = ssl._create_unverified_context

_client = OpenAI(
    api_key=LLM_API_KEY,
    base_url=LLM_BASE_URL,
    http_client=httpx.Client(
        verify=False,
        proxy=LLM_PROXY or None,
        timeout=60,
    ),
)


def chat_with_retry(
    messages: list,
    model: str = None,
    max_retries: int = 5,
    retry_delay: float = 3.0,
    **kwargs,
) -> str:
    """
    调用 chat completions 接口，失败自动 retry，成功立即返回。

    Args:
        messages:     OpenAI messages 列表
        model:        模型名，为 None 时使用配置中的 LLM_MODEL
        max_retries:  最大重试次数（含第一次，默认 5）
        retry_delay:  每次 retry 前等待秒数（默认 3.0）
        **kwargs:     透传给 chat.completions.create 的其他参数
                      （如 temperature, max_tokens, response_format 等）

    Returns:
        模型回复文本（choices[0].message.content）

    Raises:
        最后一次失败的异常（所有重试均失败时）
    """
    _model = model or LLM_MODEL
    last_exc: Exception = None

    for attempt in range(1, max_retries + 1):
        try:
            resp = _client.chat.completions.create(
                model=_model,
                messages=messages,
                **kwargs,
            )
            return resp.choices[0].message.content
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries:
                print(f"  [LLM retry {attempt}/{max_retries}] {type(exc).__name__}: {exc}")
                time.sleep(retry_delay)
            else:
                print(f"  [LLM] 已重试 {max_retries} 次，全部失败")

    raise last_exc
