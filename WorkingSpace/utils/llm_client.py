# -*- coding: utf-8 -*-
"""
LLM client wrapper — OpenAI-compatible / Anthropic SDK dual backend.
"""
import json, time, re, os


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
            self._client = None
        else:
            from openai import OpenAI
            self._client = OpenAI(api_key=api_key, base_url=base_url)
            self._ant = None

    # ── low-level ─────────────────────────────────────────────────────────────
    def chat(self, messages: list, temperature: float = 0.7,
             json_mode: bool = False, max_tokens: int = 4096) -> str:
        for attempt in range(3):
            try:
                if self.backend == "anthropic":
                    return self._ant_chat(messages, temperature, max_tokens)
                else:
                    return self._oai_chat(messages, temperature, json_mode, max_tokens)
            except Exception as exc:
                if attempt < 2:
                    print(f"  [LLM retry {attempt+1}] {exc}")
                    time.sleep(3)
                else:
                    raise

    def _oai_chat(self, messages, temperature, json_mode, max_tokens):
        kwargs: dict = dict(model=self.model, messages=messages,
                            temperature=temperature, max_tokens=max_tokens)
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = self._client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content

    def _ant_chat(self, messages, temperature, max_tokens):
        sys_msg   = next((m["content"] for m in messages if m["role"] == "system"), "")
        user_msgs = [m for m in messages if m["role"] != "system"]
        kwargs    = dict(model=self.model, max_tokens=max_tokens,
                         messages=user_msgs, temperature=temperature)
        if sys_msg:
            kwargs["system"] = sys_msg
        resp = self._ant.messages.create(**kwargs)
        return resp.content[0].text

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
                      max_tokens: int = 4096) -> dict:
        """Generate and parse JSON, with fallback extraction."""
        raw = self.generate(prompt, system=system, json_mode=True,
                            max_tokens=max_tokens)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            m = re.search(r"\{[\s\S]+\}", raw)
            if m:
                return json.loads(m.group())
            raise ValueError(f"Cannot parse JSON:\n{raw[:400]}")
