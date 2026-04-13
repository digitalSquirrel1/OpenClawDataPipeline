# -*- coding: utf-8 -*-
"""
browser_query_generator.py — 根据 topics + user_profile 生成浏览器交互 query
=============================================================================
流程:
  1. 读取 topics.txt + profiles 目录
  2. 构建 (topic, profile) 组合为任务列表
  3. ThreadPoolExecutor 并发处理每个任务
  4. 每个任务经过 3 步:
     Step 1: LLM 生成子主题
     Step 2: Agent 搜索+浏览+分析网站（带 search/visit 工具）
     Step 3: LLM 生成浏览器交互 query

使用方式:
  cd user_simulator_agent
  python ControlCenter/browser_query_generator.py

  # 自定义参数
  python ControlCenter/browser_query_generator.py \
      --topics-txt Examples/topics.txt \
      --profiles-dir Outputs/260408/profiles \
      --output-dir Outputs/260408/browser_dep_queries \
      --queries-per-combination 10
"""

import os
import sys
import json
import re
import argparse
import threading
import traceback
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# ─── Windows 中文编码 ────────────────────────────────────────────────────────
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ─── 路径设置 ─────────────────────────────────────────────────────────────────
_CONTROL_CENTER = Path(__file__).resolve().parent           # ControlCenter/
_PROJECT_ROOT   = _CONTROL_CENTER.parent                    # user_simulator_agent/
_WORKING_SPACE  = _PROJECT_ROOT / "WorkingSpace"

for _p in (_PROJECT_ROOT, _WORKING_SPACE, _CONTROL_CENTER):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from config.config_loader import load_config
from utils.llm_client import LLMClient
from utils.web_tools import WebTools

from browser_dep.steps import (
    step1_generate_subtopics,
    step2_browse_and_analyze,
    step3_generate_queries,
)


# ─── 复用自 query_gen_with_topic_skill_profile.py 的工具函数 ──────────────────
# 直接定义而非 import，避免触发该模块的重量级传递依赖

def load_topics(topics_txt_path: Path) -> list[str]:
    """读取 topics.txt，提取每行中文冒号前的关键词。"""
    if not topics_txt_path.exists():
        raise FileNotFoundError(f"topics 文件不存在: {topics_txt_path}")
    topics = []
    for line in topics_txt_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        if line and line[0].isdigit():
            dot_idx = line.find(".")
            if dot_idx != -1 and dot_idx < 5:
                line = line[dot_idx + 1 :].strip()
        if "：" in line:
            keyword = line.split("：", 1)[0].strip()
        elif ":" in line:
            keyword = line.split(":", 1)[0].strip()
        else:
            keyword = line.strip()
        if keyword:
            topics.append(keyword)
    return topics


def load_profiles(profile_dir: Path) -> list[tuple[str, dict]]:
    """加载 profile_dir 下所有 JSON profile 文件。

    Returns: [(relative_path, profile_dict), ...]
    """
    if not profile_dir.exists():
        raise FileNotFoundError(f"profile 目录不存在: {profile_dir}")
    profiles = []
    for json_path in sorted(profile_dir.glob("*.json")):
        try:
            profile = json.loads(json_path.read_text(encoding="utf-8"))
            rel_path = json_path.relative_to(profile_dir).as_posix()
            profiles.append((rel_path, profile))
        except Exception as e:
            print(f"  [Warning] 无法解析 profile: {json_path.name} — {e}")
    return profiles


# ─── 辅助 ────────────────────────────────────────────────────────────────────

def _banner(msg: str) -> None:
    print("\n" + "═" * 60)
    print(f"  {msg}")
    print("═" * 60)


def _sanitize_topic(topic: str) -> str:
    """将 topic 转为安全的目录名。"""
    # 替换 Windows 不允许的字符
    sanitized = re.sub(r'[\\/:*?"<>|]', "_", topic)
    return sanitized.strip()[:64]


def _init_llm() -> LLMClient:
    """从配置初始化 LLMClient。"""
    cfg = load_config()
    api_cfg = cfg.get("api_config", {})
    return LLMClient(
        os.getenv("LLM_API_KEY", api_cfg.get("LLM_API_KEY", "")),
        os.getenv("LLM_BASE_URL", api_cfg.get("LLM_BASE_URL", "")),
        os.getenv("LLM_MODEL", api_cfg.get("LLM_MODEL", "gpt-4o")),
        backend=os.getenv("LLM_BACKEND", api_cfg.get("LLM_BACKEND", "openai")),
    )


def _init_web_tools() -> WebTools:
    """从配置初始化 WebTools。"""
    cfg = load_config()
    web_cfg = cfg.get("web_tools_config", {})
    return WebTools(
        serper_key=os.getenv("SERPER_KEY", web_cfg.get("SERPER_KEY", "")),
        jina_key=os.getenv("JINA_KEY", web_cfg.get("JINA_KEY", "")),
    )


def _resolve_path(val, default: Path) -> Path:
    """解析路径：为空用默认值，相对路径基于 _PROJECT_ROOT。"""
    if not val:
        return default
    p = Path(val)
    return p if p.is_absolute() else (_PROJECT_ROOT / p).resolve()


# ─── 任务执行 ─────────────────────────────────────────────────────────────────

def run_task(
    topic: str,
    profile_rel: str,
    profile: dict,
    task_dir: Path,
    llm: LLMClient,
    web_tools: WebTools,
    search_semaphore: threading.Semaphore,
    visit_semaphore: threading.Semaphore,
    max_agent_turns: int,
    subtopics_per_batch: int,
    n_queries: int,
) -> dict:
    """执行一个 (topic, profile) 组合的完整 3 步管线。"""
    task_dir.mkdir(parents=True, exist_ok=True)

    try:
        # ── Step 1: 子主题生成 ──
        subtopics = step1_generate_subtopics(
            topic=topic,
            profile=profile,
            llm=llm,
            task_dir=task_dir,
        )

        # ── Step 2: 搜索+浏览+分析 ──
        website_analyses = step2_browse_and_analyze(
            subtopics=subtopics,
            topic=topic,
            profile=profile,
            llm=llm,
            web_tools=web_tools,
            search_semaphore=search_semaphore,
            visit_semaphore=visit_semaphore,
            task_dir=task_dir,
            max_turns=max_agent_turns,
            subtopics_per_batch=subtopics_per_batch,
        )

        # ── Step 3: 生成 query ──
        queries = step3_generate_queries(
            topic=topic,
            profile=profile,
            website_analyses=website_analyses,
            llm=llm,
            task_dir=task_dir,
            n_queries=n_queries,
        )

        print(f"  [OK] {profile_rel} × {topic} → {len(queries)} 条 query")
        return {
            "topic": topic,
            "profile_rel": profile_rel,
            "status": "ok",
            "count": len(queries),
        }

    except Exception as e:
        print(f"  [FAIL] {profile_rel} × {topic} → {e}")
        traceback.print_exc()
        return {
            "topic": topic,
            "profile_rel": profile_rel,
            "status": "fail",
            "error": str(e),
        }


# ─── 任务组装 ─────────────────────────────────────────────────────────────────

def _assemble_tasks(
    topics: list[str],
    profiles: list[tuple[str, dict]],
    output_dir: Path,
    skip_existing: bool,
) -> list[dict]:
    """构建 (topic, profile) 任务列表，跳过已完成的。"""
    tasks = []
    skipped = 0
    for topic in topics:
        sanitized_topic = _sanitize_topic(topic)
        for profile_rel, profile in profiles:
            profile_stem = Path(profile_rel).stem
            task_dir = output_dir / profile_stem / sanitized_topic

            # skip: step3_queries.json 存在 = 任务完全完成
            if skip_existing and (task_dir / "step3_queries.json").exists():
                skipped += 1
                continue

            tasks.append({
                "topic": topic,
                "profile_rel": profile_rel,
                "profile": profile,
                "task_dir": task_dir,
            })

    if skipped:
        print(f"  [skip_existing] 跳过 {skipped} 个已完成的 (topic, profile) 组合")
    return tasks


# ─── Argparse ─────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    cfg = load_config()
    bd_cfg = cfg.get("browser_dep_config", {})

    parser = argparse.ArgumentParser(
        description="根据 topics + user_profile 生成浏览器交互 query"
    )
    parser.add_argument(
        "--topics-txt",
        type=str,
        default=bd_cfg.get("topics_txt_path", "Examples/topics.txt"),
        help="topics.txt 路径（相对于项目根目录）",
    )
    parser.add_argument(
        "--profiles-dir",
        type=str,
        default=bd_cfg.get("profiles_dir", "Outputs/profiles"),
        help="用户 profile 所在文件夹（相对于项目根目录）",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=bd_cfg.get("output_dir", "Outputs/browser_dep_queries"),
        help="输出目录（相对于项目根目录）",
    )
    parser.add_argument(
        "--queries-per-combination",
        type=int,
        default=bd_cfg.get("queries_per_combination", 10),
        help="每组 (topic, profile) 生成的 query 数量",
    )
    parser.add_argument(
        "--max-agent-turns",
        type=int,
        default=bd_cfg.get("max_agent_turns", 8),
        help="Step 2 Agent 每批最大轮次数",
    )
    parser.add_argument(
        "--subtopics-per-batch",
        type=int,
        default=bd_cfg.get("subtopics_per_batch", 2),
        help="Step 2 每批处理的子主题数量",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        default=bd_cfg.get("skip_existing", True),
        help="跳过已完成的 (topic, profile) 组合",
    )
    return parser.parse_args()


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    args = parse_args()

    _banner("browser_dep — 生成浏览器交互 query")

    # ── 解析路径 ──
    topics_path = _resolve_path(args.topics_txt, _PROJECT_ROOT / "Examples" / "topics.txt")
    profiles_dir = _resolve_path(args.profiles_dir, _PROJECT_ROOT / "Outputs" / "profiles")
    output_dir = _resolve_path(args.output_dir, _PROJECT_ROOT / "Outputs" / "browser_dep_queries")
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── 加载 topics & profiles ──
    topics = load_topics(topics_path)
    print(f"  topics 文件: {topics_path}")
    print(f"  提取到 {len(topics)} 个 topic: {topics}")

    profiles = load_profiles(profiles_dir)
    print(f"  profiles 目录: {profiles_dir}")
    print(f"  找到 {len(profiles)} 个 profile")

    if not topics:
        print("[Error] 无 topic，退出")
        return 1
    if not profiles:
        print("[Error] 无 profile 文件，退出")
        return 1

    # ── 组装任务 ──
    tasks = _assemble_tasks(topics, profiles, output_dir, args.skip_existing)
    total_combinations = len(topics) * len(profiles)
    print(f"  共 {total_combinations} 个 (topic, profile) 组合，待执行 {len(tasks)} 个任务")

    if not tasks:
        print("[Info] 全部已完成，无需执行")
        return 0

    # ── 初始化 LLM & WebTools ──
    llm = _init_llm()
    web_tools = _init_web_tools()

    # ── 并发参数 ──
    cfg = load_config()
    pipeline_cfg = cfg.get("pipeline_config", {})
    bd_cfg = cfg.get("browser_dep_config", {})
    max_workers = int(os.getenv("MAX_LLM_CALLS", pipeline_cfg.get("MAX_LLM_CALLS", 4)))
    max_search = int(bd_cfg.get("max_search_concurrency", 5))
    max_visit = int(bd_cfg.get("max_visit_concurrency", 3))
    search_semaphore = threading.Semaphore(max_search)
    visit_semaphore = threading.Semaphore(max_visit)

    print(f"  并发度 (MAX_LLM_CALLS): {max_workers}")
    print(f"  搜索并发限制: {max_search}")
    print(f"  访问并发限制: {max_visit}")
    print(f"  每组生成 query 数: {args.queries_per_combination}")
    print(f"  Agent 最大轮次: {args.max_agent_turns}")
    print(f"  每批子主题数: {args.subtopics_per_batch}")
    print(f"  输出目录: {output_dir}\n")

    # ── 线程池并发执行 ──
    total_ok = total_fail = 0

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(
                run_task,
                topic=t["topic"],
                profile_rel=t["profile_rel"],
                profile=t["profile"],
                task_dir=t["task_dir"],
                llm=llm,
                web_tools=web_tools,
                search_semaphore=search_semaphore,
                visit_semaphore=visit_semaphore,
                max_agent_turns=args.max_agent_turns,
                subtopics_per_batch=args.subtopics_per_batch,
                n_queries=args.queries_per_combination,
            ): t
            for t in tasks
        }
        for future in as_completed(futures):
            result = future.result()
            if result["status"] == "ok":
                total_ok += 1
            else:
                total_fail += 1

    # ── 汇总 ──
    _banner(f"完成: 成功 {total_ok}  失败 {total_fail}  共 {len(tasks)} 个任务")
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
