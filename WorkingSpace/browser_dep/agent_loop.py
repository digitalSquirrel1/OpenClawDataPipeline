# -*- coding: utf-8 -*-
"""
agent_loop.py — 多轮 Agent 循环 + 工具注册/解析/执行（异步版）
==============================================================
实现基于 <tool>...</tool> 标签的工具调用协议：
  - 模型在 system prompt 中了解可用工具及调用格式
  - 模型在 assistant 回复中使用 <tool>{"name":"xxx","arguments":{...}}</tool> 调用工具
  - 框架解析 <tool> 标签、**并发**执行工具、将结果以 user 角色 + <tool_response> 标签回传
  - 当模型回复中不含 <tool> 标签时，视为最终回答，循环结束

异步设计：
  - run_agent_loop 是 async 函数
  - LLM 调用和工具执行通过 asyncio.to_thread 包装（底层是同步 I/O）
  - 同一轮内的多个工具调用通过 asyncio.gather 并发执行
"""

import asyncio
import json
import re
import threading
from dataclasses import dataclass
from typing import Callable


# ─── Tool 定义 ───────────────────────────────────────────────────────────────

@dataclass
class ToolDef:
    """一个可供 Agent 调用的工具。"""
    name: str
    description: str                          # 注册到 system prompt 的文字说明
    execute: Callable[[dict], str]            # arguments dict -> 返回文本（同步）


# ─── <tool> 标签解析 ──────────────────────────────────────────────────────────

_TOOL_PATTERN = re.compile(
    r"<tool>\s*(\{.*?\})\s*</tool>",
    re.DOTALL,
)


def _fix_double_braces(s: str) -> str:
    """修复模型输出的双大括号 {{...}} → {...}。

    模型可能从 prompt 模板中的转义大括号学到 {{ }} 写法，
    导致输出 {{"name": ...}} 而非 {"name": ...}。
    """
    s = s.strip()
    if s.startswith("{{") and s.endswith("}}"):
        s = s[1:-1]
    return s


def parse_tool_calls(response_text: str) -> list[dict]:
    """从模型回复中提取所有 <tool>{...}</tool> 块。

    Returns:
        [{"name": str, "arguments": dict}, ...]
        无匹配时返回空列表。
    """
    results = []
    for match in _TOOL_PATTERN.finditer(response_text):
        raw = match.group(1)
        # 尝试直接解析
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            # 修复双大括号后重试
            fixed = _fix_double_braces(raw)
            try:
                parsed = json.loads(fixed)
            except json.JSONDecodeError:
                # 跳过此 tool call，继续解析其余的
                print(f"    [Agent] 跳过无法解析的 tool call: {raw[:200]}")
                continue
        if "name" not in parsed:
            print(f"    [Agent] 跳过缺少 name 字段的 tool call: {raw[:200]}")
            continue
        results.append({
            "name": parsed["name"],
            "arguments": parsed.get("arguments", {}),
        })
    return results


# ─── 工具工厂：search / visit ─────────────────────────────────────────────

def make_search_tool(web_tools, search_semaphore: threading.Semaphore) -> ToolDef:
    """创建 search 工具，包装 WebTools.search()。"""

    def execute(arguments: dict) -> str:
        queries = arguments.get("queries", [])
        if isinstance(queries, str):
            queries = [queries]
        num_results = int(arguments.get("num_results", 5))

        all_results = []
        for q in queries:
            with search_semaphore:
                results = web_tools.search(q, num=num_results)
            for r in results:
                all_results.append({
                    "title": r.get("title", ""),
                    "link": r.get("link", ""),
                    "snippet": r.get("snippet", ""),
                })
        return json.dumps(all_results, ensure_ascii=False, indent=2)

    return ToolDef(
        name="search",
        description=(
            "搜索工具。\n"
            "参数:\n"
            "  - queries (List[str]): 搜索关键词列表\n"
            "  - num_results (int, 默认5): 每个关键词返回的结果数量\n"
            "返回: JSON 列表，每条包含 title, link, snippet。"
        ),
        execute=execute,
    )


def make_visit_tool(web_tools, visit_semaphore: threading.Semaphore | None = None) -> ToolDef:
    """创建 visit 工具，包装 WebTools.read_url()，带重试和并发限制。"""
    MAX_CONTENT_LEN = 15000
    MAX_RETRIES = 1
    RETRY_DELAY = 1.0  # 秒

    def execute(arguments: dict) -> str:
        url = arguments.get("url", "")
        if not url:
            return "错误：缺少 url 参数"

        import time
        for attempt in range(1, MAX_RETRIES + 1):
            if visit_semaphore is not None:
                visit_semaphore.acquire()
            try:
                content = web_tools.read_url(url, timeout=30)
            except Exception as e:
                content = None
                print(f"    [visit] 异常 {url} (attempt {attempt}): {e}")
            finally:
                if visit_semaphore is not None:
                    visit_semaphore.release()

            if content is not None:
                break
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)

        if content is None:
            return f"无法访问该网页（重试 {MAX_RETRIES} 次后仍失败）: {url}"
        if len(content) > MAX_CONTENT_LEN:
            content = (
                content[:MAX_CONTENT_LEN]
                + f"\n\n[内容已截断，原文共 {len(content)} 字符]"
            )
        return content

    return ToolDef(
        name="visit",
        description=(
            "访问网页工具。\n"
            "参数:\n"
            "  - url (str): 要访问的网页URL\n"
            "返回: 网页内容的 Markdown 文本。如果无法访问则返回错误信息。"
        ),
        execute=execute,
    )


# ─── Agent 多轮循环（异步）────────────────────────────────────────────────────

async def run_agent_loop(
    system_prompt: str,
    user_prompt: str,
    tools: list[ToolDef],
    llm,
    max_turns: int = 8,
    temperature: float = 0.7,
    max_tokens: int = 16384,
) -> tuple[str, list[dict]]:
    """运行多轮 Agent 循环（异步版）。

    - LLM 调用通过 asyncio.to_thread 异步执行
    - 同一轮内的多个工具调用通过 asyncio.gather 并发执行
    """
    tool_map = {t.name: t for t in tools}
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    for turn in range(max_turns):
        # ── LLM 调用（异步）──
        response = await asyncio.to_thread(
            llm.chat, messages,
            temperature, False, max_tokens,
        )
        messages.append({"role": "assistant", "content": response})

        # ── 解析工具调用 ──
        tool_calls = parse_tool_calls(response)

        if not tool_calls:
            return response, messages

        # ── 并发执行所有工具 ──
        async def _exec_one(tc: dict) -> tuple[str, str]:
            name = tc["name"]
            args = tc["arguments"]
            if name not in tool_map:
                return name, f"未知工具: {name}"
            try:
                result = await asyncio.to_thread(tool_map[name].execute, args)
                return name, result
            except Exception as e:
                return name, f"工具执行错误 ({name}): {type(e).__name__}: {e}"

        exec_results = await asyncio.gather(
            *[_exec_one(tc) for tc in tool_calls]
        )

        # ── 将工具结果追加到 messages ──
        tool_result_parts = [
            f'<tool_response name="{name}">\n{result}\n</tool_response>'
            for name, result in exec_results
        ]
        messages.append({
            "role": "user",
            "content": "\n\n".join(tool_result_parts),
        })

    # 达到 max_turns，返回最后的 assistant 消息
    last_assistant = ""
    for m in reversed(messages):
        if m["role"] == "assistant":
            last_assistant = m["content"]
            break
    print(f"    [Agent] 已达最大轮次 ({max_turns})，返回当前结果")
    return last_assistant, messages
