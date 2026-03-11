# -*- coding: utf-8 -*-
import os, ssl, httpx
from openai import OpenAI

LLM_API_KEY  = os.getenv("LLM_API_KEY",  "sk-U2BkWhBzdLcJn01ovsXXESVO2nboXEjKqjj8WxECS6Dom5UZ")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.gptplus5.com/v1")
LLM_MODEL    = os.getenv("LLM_MODEL",    "gpt-5.2")

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
