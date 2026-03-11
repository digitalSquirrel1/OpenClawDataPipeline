# -*- coding: utf-8 -*-
"""
LLM client wrapper — OpenAI-compatible / Anthropic SDK dual backend.
"""
import json, time, re, os, sys
from pathlib import Path

# 加载共享 retry 调用函数
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # user_simulator_agent/
sys.path.insert(0, str(_PROJECT_ROOT))
from shared.llm_caller import chat_with_retry


class LLMClient:
    def __init__(self, api_key: str, base_url: str, model: str,
                 backend: str = "openai"):
        self.model   = model
        self.backend = backend
        if backend == "anthropic":
            import anthropic
            self._ant = anthropic.Anthropic(
                api_key=api_key or os.getenv("ANTHROPIC_API_KEY", "")
            )
        else:
            self._ant = None

    # ── low-level ─────────────────────────────────────────────────────────────
    def chat(self, messages: list, temperature: float = 0.7,
             json_mode: bool = False, max_tokens: int = 4096) -> str:
        if self.backend == "anthropic":
            return self._ant_chat(messages, temperature, max_tokens)
        else:
            return self._oai_chat(messages, temperature, json_mode, max_tokens)

    def _oai_chat(self, messages, temperature, json_mode, max_tokens):
        kwargs: dict = dict(temperature=temperature, max_tokens=max_tokens)
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        return chat_with_retry(messages, model=self.model, **kwargs)

    def _ant_chat(self, messages, temperature, max_tokens):
        sys_msg   = next((m["content"] for m in messages if m["role"] == "system"), "")
        user_msgs = [m for m in messages if m["role"] != "system"]
        kwargs    = dict(model=self.model, max_tokens=max_tokens,
                         messages=user_msgs, temperature=temperature)
        if sys_msg:
            kwargs["system"] = sys_msg
        last_exc: Exception = None
        for attempt in range(1, 6):
            try:
                resp = self._ant.messages.create(**kwargs)
                return resp.content[0].text
            except Exception as exc:
                last_exc = exc
                if attempt < 5:
                    print(f"  [Anthropic retry {attempt}/5] {type(exc).__name__}: {exc}")
                    time.sleep(3)
                else:
                    print("  [Anthropic] 已重试 5 次，全部失败")
        raise last_exc

    # ── convenience ───────────────────────────────────────────────────────────
    def generate(self, prompt: str,
                 system: str = "你是一个专业、严谨的AI助手。",
                 temperature: float = 0.7,
                 json_mode: bool = False,
                 max_tokens: int = 4096) -> str:
        return self.chat(
            [{"role": "system", "content": system},
             {"role": "user",   "content": prompt}],
            temperature=temperature, json_mode=json_mode, max_tokens=max_tokens
        )

    def generate_json(self, prompt: str,
                      system: str = "你是一个专业的AI助手，只输出合法JSON。",
                      ) -> dict:
        """Generate and parse JSON, with fallback extraction.
        删除max_token=4096防止解码为空"""
        raw = self.generate(prompt, system=system, 
                            json_mode=True,
                            )
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            m = re.search(r"\{[\s\S]+\}", raw)
            if m:
                return json.loads(m.group())
            raise ValueError(f"Cannot parse JSON:\n{raw[:400]}")
