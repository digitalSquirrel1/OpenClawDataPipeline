# -*- coding: utf-8 -*-
"""
steps.py — 三步管线实现 + checkpoint 读写
==========================================
Step 1: 子主题生成（1次 LLM call）
Step 2: 搜索+浏览+分析（多轮 Agent，分批执行）
Step 3: 生成浏览器交互 query（1次 LLM call）
"""

import asyncio
import json
import re
import threading
from datetime import datetime
from pathlib import Path

from config.config_loader import load_config, get_prompt
from .agent_loop import make_search_tool, make_visit_tool, run_agent_loop


# ─── 辅助函数 ─────────────────────────────────────────────────────────────────

def _load_checkpoint(path: Path) -> dict | None:
    """加载 checkpoint 文件，不存在返回 None。"""
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _save_checkpoint(path: Path, data: dict) -> None:
    """原子写入 checkpoint。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ─── Step 1: 子主题生成 ──────────────────────────────────────────────────────

def step1_generate_subtopics(
    topic: str,
    profile: dict,
    llm,
    task_dir: Path,
) -> list[str]:
    """生成 3-5 个子主题。单次 LLM 调用，无工具。

    Checkpoint: task_dir/step1_subtopics.json
    """
    checkpoint_path = task_dir / "step1_subtopics.json"

    # ── Resume ──
    existing = _load_checkpoint(checkpoint_path)
    if existing is not None:
        return existing["subtopics"]

    # ── 加载 prompt ──
    cfg = load_config()
    bd_cfg = cfg.get("browser_dep_config", {})
    prompt_rel = bd_cfg.get("STEP1_PROMPT", "prompts/browser_dep/step1_subtopic_gen.md")
    prompt_tmpl = get_prompt(prompt_rel)

    prompt = prompt_tmpl.format(
        topic=topic,
        profile_json=json.dumps(profile, ensure_ascii=False, indent=2),
        current_date=datetime.now().strftime("%Y年%m月%d日"),
    )

    # ── LLM 调用 ──
    result = llm.generate_json(prompt)
    if isinstance(result, list):
        subtopics = result
    else:
        subtopics = result.get("subtopics", [])

    if not isinstance(subtopics, list) or len(subtopics) == 0:
        raise ValueError(f"Step 1 返回无效的 subtopics: {result}")

    # ── 存盘 ──
    _save_checkpoint(checkpoint_path, {
        "topic": topic,
        "subtopics": subtopics,
    })
    print(f"    [Step1] 生成 {len(subtopics)} 个子主题: {subtopics}")
    return subtopics


# ─── Step 2: 搜索 + 浏览 + 分析 ─────────────────────────────────────────────

def step2_browse_and_analyze(
    subtopics: list[str],
    topic: str,
    profile: dict,
    llm,
    web_tools,
    search_semaphore: threading.Semaphore,
    visit_semaphore: threading.Semaphore,
    task_dir: Path,
    max_turns: int = 8,
    subtopics_per_batch: int = 2,
) -> list[dict]:
    """搜索、浏览、分析网站。按子主题分批执行 Agent。

    Checkpoint: task_dir/step2_websites.json（含 batches 数组）
    Resume: 比对已完成批次，只跑缺失的。
    """
    checkpoint_path = task_dir / "step2_websites.json"

    # ── 加载已有结果 ──
    existing = _load_checkpoint(checkpoint_path)
    if existing is None:
        existing = {"topic": topic, "batches": []}

    completed_batches = existing.get("batches", [])
    completed_subtopic_sets = [
        frozenset(b["subtopics"]) for b in completed_batches
    ]

    # ── 分批 ──
    batches = []
    for i in range(0, len(subtopics), subtopics_per_batch):
        batches.append(subtopics[i : i + subtopics_per_batch])

    # 检查是否全部完成
    all_done = all(
        frozenset(batch) in completed_subtopic_sets for batch in batches
    )
    if all_done and completed_batches:
        print(f"    [Step2] 所有 {len(batches)} 批次已完成，跳过")
        return completed_batches

    # ── 构建工具 ──
    tools = [
        make_search_tool(web_tools, search_semaphore),
        make_visit_tool(web_tools, visit_semaphore),
    ]

    # ── 加载 prompt ──
    cfg = load_config()
    bd_cfg = cfg.get("browser_dep_config", {})
    system_prompt_rel = bd_cfg.get(
        "STEP2_SYSTEM_PROMPT", "prompts/browser_dep/step2_system.md"
    )
    user_prompt_rel = bd_cfg.get(
        "STEP2_USER_PROMPT", "prompts/browser_dep/step2_user.md"
    )
    system_prompt = get_prompt(system_prompt_rel)
    user_prompt_tmpl = get_prompt(user_prompt_rel)

    # ── 逐批执行 ──
    for batch_idx, batch in enumerate(batches):
        if frozenset(batch) in completed_subtopic_sets:
            continue

        print(f"    [Step2] 批次 {batch_idx + 1}/{len(batches)}: {batch}")

        user_prompt = user_prompt_tmpl.format(
            topic=topic,
            subtopics=json.dumps(batch, ensure_ascii=False),
            profile_json=json.dumps(profile, ensure_ascii=False, indent=2),
            current_date=datetime.now().strftime("%Y年%m月%d日"),
        )

        final_response, _history = asyncio.run(run_agent_loop(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            tools=tools,
            llm=llm,
            max_turns=max_turns,
        ))

        # ── 解析 Agent 输出 ──
        batch_result = _parse_step2_analysis(final_response, batch)
        completed_batches.append(batch_result)

        # ── 存盘（每批完成后立即保存）──
        existing["batches"] = completed_batches
        _save_checkpoint(checkpoint_path, existing)
        print(
            f"    [Step2] 批次 {batch_idx + 1} 完成，"
            f"分析了 {len(batch_result.get('websites', []))} 个网站"
        )

    return completed_batches


def _parse_step2_analysis(response: str, subtopics: list[str]) -> dict:
    """解析 Agent 最终回复中的 <analysis>...</analysis> 结构化结果。

    解析失败时保留 raw_analysis，Step 3 仍可使用。
    """
    result = {
        "subtopics": subtopics,
        "websites": [],
        "raw_analysis": response,
    }

    # 提取 <analysis>...</analysis>
    match = re.search(r"<analysis>(.*?)</analysis>", response, re.DOTALL)
    if match:
        raw_json = match.group(1).strip()
        try:
            parsed = json.loads(raw_json)
            if isinstance(parsed, list):
                result["websites"] = parsed
            elif isinstance(parsed, dict) and "websites" in parsed:
                result["websites"] = parsed["websites"]
        except json.JSONDecodeError:
            # JSON 解析失败，尝试清洗
            try:
                cleaned = _clean_analysis_json(raw_json)
                parsed = json.loads(cleaned)
                if isinstance(parsed, list):
                    result["websites"] = parsed
            except (json.JSONDecodeError, ValueError):
                pass

    return result


def _clean_analysis_json(raw: str) -> str:
    """清洗 analysis JSON：移除注释、尾逗号。"""
    # 移除单行注释
    raw = re.sub(r"//.*?$", "", raw, flags=re.MULTILINE)
    # 移除尾逗号
    raw = re.sub(r",\s*([}\]])", r"\1", raw)
    return raw


# ─── Step 3: 生成 query ──────────────────────────────────────────────────────

def step3_generate_queries(
    topic: str,
    profile: dict,
    website_analyses: list[dict],
    llm,
    task_dir: Path,
    n_queries: int = 10,
) -> list[dict]:
    """生成浏览器交互 query。单次 LLM 调用，无工具。

    Checkpoint: task_dir/step3_queries.json
    """
    checkpoint_path = task_dir / "step3_queries.json"

    # ── Resume ──
    existing = _load_checkpoint(checkpoint_path)
    if existing is not None:
        return existing["queries"]

    # ── 格式化网站分析结果 ──
    analyses_text = _format_website_analyses(website_analyses)

    # ── 加载 prompt ──
    cfg = load_config()
    bd_cfg = cfg.get("browser_dep_config", {})
    prompt_rel = bd_cfg.get("STEP3_PROMPT", "prompts/browser_dep/step3_query_gen.md")
    prompt_tmpl = get_prompt(prompt_rel)

    ratio_mention = bd_cfg.get("ratio_mention_specific_website", 0.2)
    pct_mention = int(ratio_mention * 100)
    pct_no_mention = 100 - pct_mention

    prompt = prompt_tmpl.format(
        topic=topic,
        profile_json=json.dumps(profile, ensure_ascii=False, indent=2),
        website_analyses=analyses_text,
        n=n_queries,
        current_date=datetime.now().strftime("%Y年%m月%d日"),
        pct_mention=pct_mention,
        pct_no_mention=pct_no_mention,
    )

    # ── LLM 调用 ──
    raw_response = llm.generate(prompt)

    # ── 解析 <queries>...</queries> ──
    queries = _parse_queries_response(raw_response)

    if not queries:
        raise ValueError(f"Step 3 未能解析出有效的 queries。原始回复前500字符: {raw_response[:500]}")

    # ── 验证并标准化 ──
    validated = _validate_queries(queries)

    # ── 存盘 ──
    output_data = {
        "topic": topic,
        "generated_at": datetime.now().isoformat(),
        "queries": validated,
    }
    _save_checkpoint(checkpoint_path, output_data)
    print(f"    [Step3] 生成 {len(validated)} 条浏览器交互 query")
    return validated


def _parse_queries_response(response: str) -> list:
    """从 LLM 回复中解析 query 列表。

    尝试顺序:
      1. <queries>...</queries> 标签内的 JSON
      2. 整体 JSON 解析
      3. 正则提取最外层 [...] 数组
    """
    # 1. 尝试 <queries> 标签
    match = re.search(r"<queries>(.*?)</queries>", response, re.DOTALL)
    if match:
        raw = match.group(1).strip()
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            # 尝试清洗后解析
            cleaned = re.sub(r",\s*([}\]])", r"\1", raw)
            try:
                parsed = json.loads(cleaned)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass

    # 2. 尝试整体 JSON
    # 去除 markdown 代码围栏
    text = response.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # 找到开始和结束的 ```
        start = 1
        end = len(lines)
        for i in range(1, len(lines)):
            if lines[i].strip().startswith("```"):
                end = i
                break
        text = "\n".join(lines[start:end])

    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict) and "queries" in parsed:
            return parsed["queries"]
    except json.JSONDecodeError:
        pass

    # 3. 正则提取 [...]
    array_match = re.search(r"\[.*\]", response, re.DOTALL)
    if array_match:
        try:
            return json.loads(array_match.group(0))
        except json.JSONDecodeError:
            pass

    return []


def _validate_queries(raw_queries: list) -> list[dict]:
    """标准化 query 列表，确保每条都有 queries 和 ref_websites 字段。"""
    validated = []
    for item in raw_queries:
        if isinstance(item, str):
            validated.append({"queries": item, "ref_websites": []})
        elif isinstance(item, dict):
            validated.append({
                "queries": item.get("queries", item.get("query", "")),
                "ref_websites": item.get("ref_websites", item.get("ref_website", [])),
            })
    return validated


def _format_website_analyses(analyses: list[dict]) -> str:
    """将所有批次的网站分析结果格式化为可读文本，供 Step 3 prompt 使用。"""
    parts = []
    for i, batch in enumerate(analyses, 1):
        subtopics_str = ", ".join(batch.get("subtopics", []))
        parts.append(f"### 批次 {i}: {subtopics_str}")

        websites = batch.get("websites", [])
        if websites:
            for w in websites:
                parts.append(f"**网站**: {w.get('url', '?')}")
                parts.append(f"  标题: {w.get('title', '?')}")
                if w.get("subtopic"):
                    parts.append(f"  所属子主题: {w['subtopic']}")
                parts.append(f"  内容摘要: {w.get('content_summary', w.get('summary', '?'))}")
                parts.append(f"  可交互元素: {w.get('interactive_elements', '无')}")
                if w.get("query_directions"):
                    directions = w["query_directions"]
                    if isinstance(directions, list):
                        directions = "; ".join(directions)
                    parts.append(f"  可设计的query方向: {directions}")
                if w.get("quality"):
                    parts.append(f"  质量评估: {w['quality']}")
                parts.append("")
        else:
            # 回退到 raw_analysis
            raw = batch.get("raw_analysis", "无分析结果")
            if len(raw) > 4000:
                raw = raw[:4000] + "\n[...内容过长，已截断...]"
            parts.append(raw)

        parts.append("")

    return "\n".join(parts)
