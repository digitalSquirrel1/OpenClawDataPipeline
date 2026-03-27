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
                api_key=api_key or os.getenv("ANTHROPIC_API_KEY", ""),
                timeout=60.0,
            )
        else:
            self._ant = None

    # ── low-level ─────────────────────────────────────────────────────────────
    def chat(self, messages: list, temperature: float = 0.7,
             json_mode: bool = False, max_tokens: int = 16384) -> str:
        if self.backend == "anthropic":
            return self._ant_chat(messages, temperature, max_tokens)
        else:
            return self._oai_chat(messages, temperature, json_mode, max_tokens)

    def _oai_chat(self, messages, temperature, json_mode, max_tokens):
        kwargs: dict = dict(temperature=temperature, max_tokens=max_tokens)
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        return chat_with_retry(messages, model=self.model, **kwargs)

    def _ant_chat(self, messages, temperature, max_tokens,
                  max_retries: int = 5, retry_delay: float = 3.0):
        sys_msg   = next((m["content"] for m in messages if m["role"] == "system"), "")
        user_msgs = [m for m in messages if m["role"] != "system"]
        kwargs    = dict(model=self.model, max_tokens=max_tokens,
                         messages=user_msgs, temperature=temperature)
        if sys_msg:
            kwargs["system"] = sys_msg
        last_exc: Exception = None
        for attempt in range(1, max_retries + 1):
            try:
                resp = self._ant.messages.create(**kwargs)
                return resp.content[0].text
            except Exception as exc:
                last_exc = exc
                if attempt < max_retries:
                    print(f"  [Anthropic retry {attempt}/{max_retries}] {type(exc).__name__}: {exc}")
                    time.sleep(retry_delay)
                else:
                    print(f"  [Anthropic] 已重试 {max_retries} 次，全部失败")
        raise last_exc

    # ── convenience ───────────────────────────────────────────────────────────
    def generate(self, prompt: str,
                 system: str = "你是一个专业、严谨的AI助手。",
                 temperature: float = 0.7,
                 json_mode: bool = False,
                 max_tokens: int = 16384) -> str:
        return self.chat(
            [{"role": "system", "content": system},
             {"role": "user",   "content": prompt}],
            temperature=temperature, json_mode=json_mode, max_tokens=max_tokens
        )

    def generate_json(self, prompt: str,
                      system: str = "你是一个专业的AI助手，按照用户的格式要求输出合法JSON。并输出高质量的JSON内容。",
                      max_retry = 3
                      ) -> dict:
        """Generate and parse JSON, with fallback extraction.
        删除max_token=4096防止解码为空或截断"""
        for i_try in range(max_retry):
            raw = self.generate(prompt, 
                                system=system,
                                json_mode=True,
                                )
            try:
                if not isinstance(raw, str):
                    raise TypeError(f'llm_client.py generate do not return a stiring: type={type(raw)}, {raw=}')
                # 如果 LLM 受 prompt 模板 {{}} 转义影响，输出了双花括号，先剥掉外层
                stripped = self._strip_json_fence(raw.strip())
                if stripped.startswith('{{') and stripped.endswith('}}'):
                    print(f'double braces found: {stripped[:50]}...{stripped[-50:]}')
                    stripped = stripped[1:-1]  # 剥掉最外层的一对花括号
                return json.loads(stripped)
            except json.JSONDecodeError:
                # 找到了tags(target_json_str存在)
                # 但是json无法正常解析（target_json_str无法解析），才会进来这个分支
                # 这里重点解决json无法解析的问题
                cleaned = self._clean_json(raw)
                try:
                    return json.loads(cleaned)
                except json.JSONDecodeError:
                    pass
                # 正则提取最外层 {...}
                m = re.search(r"(\{[\s\S]+\}|\[[\s\S]+\])", cleaned)
                if m:
                    try:
                        return json.loads(m.group())
                    except json.JSONDecodeError:
                        pass
                print(f"Cannot parse JSON, retry {i_try}/{max_retry-1}:\n{raw=}")
                with open(r'D:\PythonProject\OpenClawDataPipeline\user_simulator_agent\Outputs\260312\environments\error.json', 'a+', encoding='utf-8') as f:
                    f.write(raw)
            except Exception as e:
                print(f'error parsing, {repr(e)}, {raw=}')
        raise ValueError(f"Cannot parse JSON, failed {max_retry} times:\n{raw=}")

    @staticmethod
    def _strip_json_fence(raw: str) -> str:
        """Strip a surrounding markdown code fence if JSON is wrapped in ```json ... ```."""
        s = raw.strip()
        if not s.startswith("```"):
            return s

        lines = s.splitlines()
        if not lines:
            return s

        if not lines[0].strip().startswith("```"):
            return s

        if len(lines) >= 2 and lines[-1].strip() == "```":
            return "\n".join(lines[1:-1]).strip()
        return s

    @staticmethod
    def _clean_json(raw: str) -> str:
        """尝试修复 LLM 输出的常见 JSON 格式错误。"""
        s = LLMClient._strip_json_fence(raw)
        # 去除 // 行注释
        s = re.sub(r'//[^\n]*', '', s)
        # 去除 /* ... */ 块注释
        s = re.sub(r'/\*[\s\S]*?\*/', '', s)
        # 移除尾逗号（}, ] 或 }, } 之前的多余逗号）
        s = re.sub(r',\s*([}\]])', r'\1', s)
        # 尝试补全未闭合的括号
        opens = s.count('{') - s.count('}')
        if opens > 0:
            s = s.rstrip()
            # 如果末尾是逗号或普通值，先加上必要的闭合
            s += '}' * opens
        opens = s.count('[') - s.count(']')
        if opens > 0:
            s = s.rstrip().rstrip(',')
            s += ']' * opens
            # 补完数组后可能还需要补对象闭合
            opens2 = s.count('{') - s.count('}')
            if opens2 > 0:
                s += '}' * opens2
        return s
