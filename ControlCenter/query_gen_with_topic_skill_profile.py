# -*- coding: utf-8 -*-
"""
query_gen_with_topic_skill_profile.py — 根据 topics + skills + user_profile 生成 query
=======================================================================================
流程：
  1. 读取 topics.txt，提取每行中文冒号前的关键词作为 topic
  2. 遍历 profile_dir 下的所有 profile JSON 文件
  3. 组装 (topic, profile) 排列组合为 task 列表，每个 task 独立查询 skills（利用随机性）
  4. 线程池并发调用 LLM 生成 query，每完成一个 task 立即追加保存到对应 profile 的输出文件
  5. 输出 JSON 含 queries、profile 相对路径、skills 相对路径、topic

使用方式：
  python ControlCenter/query_gen_with_topic_skill_profile.py

  # 指定 topics 文件和 profile 目录
  python ControlCenter/query_gen_with_topic_skill_profile.py \
      --topics-txt Outputs/topics.txt \
      --profile-dir Outputs/profiles \
      --output-dir Outputs/queries_with_skills

  # 跳过已生成的
  python ControlCenter/query_gen_with_topic_skill_profile.py --skip-existing
"""

import os, sys, json, argparse, random, threading
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# 支持中文字符显示
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ─── 路径设置 ───────────────────────────────────────────────────────────────
_CONTROL_CENTER = Path(__file__).resolve().parent
_PROJECT_ROOT   = _CONTROL_CENTER.parent              # user_simulator_agent/
_WORKING_SPACE  = _PROJECT_ROOT / "WorkingSpace"

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
if str(_WORKING_SPACE) not in sys.path:
    sys.path.insert(0, str(_WORKING_SPACE))

from config.config_loader import load_config, get_prompt
from utils.llm_client import LLMClient
from shared.topic_search_skills import search_skills_by_topic


def _banner(msg: str) -> None:
    print("\n" + "═" * 60)
    print(f"  {msg}")
    print("═" * 60)


def _init_llm() -> LLMClient:
    """从配置初始化 LLMClient。"""
    cfg     = load_config()
    api_cfg = cfg.get("api_config", {})
    return LLMClient(
        os.getenv("LLM_API_KEY",  api_cfg.get("LLM_API_KEY",  "")),
        os.getenv("LLM_BASE_URL", api_cfg.get("LLM_BASE_URL", "")),
        os.getenv("LLM_MODEL",    api_cfg.get("LLM_MODEL",    "gpt-4o")),
        backend=os.getenv("LLM_BACKEND", api_cfg.get("LLM_BACKEND", "openai")),
    )


def load_topics(topics_txt_path: Path) -> list[str]:
    """读取 topics.txt，提取每行中文冒号前的关键词。

    例如 "习题求解：针对各学科习题..." → "习题求解"
    """
    if not topics_txt_path.exists():
        raise FileNotFoundError(f"topics 文件不存在: {topics_txt_path}")

    topics = []
    for line in topics_txt_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        # 去掉行首可能的序号（如 "1. "）
        if line and line[0].isdigit():
            dot_idx = line.find(".")
            if dot_idx != -1 and dot_idx < 5:
                line = line[dot_idx + 1:].strip()
        # 提取中文冒号前的部分
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
    """加载 profile_dir 下的所有 JSON profile 文件。

    Returns:
        [(relative_path, profile_dict), ...]
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


def _format_skills_info(skills: list[dict]) -> str:
    """将 skills 列表格式化为可读文本，供 prompt 使用。"""
    if not skills:
        return "（无匹配的 skills）"
    parts = []
    for i, s in enumerate(skills, 1):
        name = s.get("skill名称", "?")
        desc = s.get("skill简介", "?")
        scenarios = s.get("skill可用场景", [])
        parts.append(
            f"{i}. {name}\n"
            f"   简介: {desc}\n"
            f"   可用场景: {', '.join(scenarios) if scenarios else '未指定'}"
        )
    return "\n".join(parts)


def generate_queries(
    topic: str,
    skills: list[dict],
    profile: dict,
    llm: LLMClient,
    prompt_tmpl: str,
    n: int = 5,
) -> list[str]:
    """调用 LLM 为一组 (topic, skills, profile) 生成 queries。

    Returns:
        query 字符串列表

    Raises:
        ValueError: LLM 返回无法解析的 JSON
    """
    skills_info = _format_skills_info(skills)
    profile_json = json.dumps(profile, ensure_ascii=False, indent=2)

    prompt = prompt_tmpl.format(
        topic=topic,
        skills_info=skills_info,
        profile_json=profile_json,
        n=n,
    )

    result = llm.generate_json(prompt)
    queries = result.get("queries", [])
    if not isinstance(queries, list):
        raise ValueError(f"LLM 返回的 queries 不是数组: {type(queries)}")
    return queries


def _append_record_to_file(
    out_path: Path,
    profile_rel: str,
    record: dict,
    lock: threading.Lock,
) -> None:
    """线程安全地将一条 record 追加到 profile 的输出 JSON 文件。

    文件格式:
        { "profile_rel_path": ..., "generated_at": ..., "results": [...] }

    若文件已存在，则读取并追加到 results 列表；否则新建。
    """
    with lock:
        if out_path.exists():
            data = json.loads(out_path.read_text(encoding="utf-8"))
        else:
            data = {
                "profile_rel_path": profile_rel,
                "generated_at": datetime.now().isoformat(),
                "results": [],
            }
        data["results"].append(record)
        out_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _run_task(
    topic: str,
    skills: list[dict],
    profile_rel: str,
    profile: dict,
    llm: LLMClient,
    prompt_tmpl: str,
    n_queries: int,
    out_path: Path,
    file_lock: threading.Lock,
) -> dict:
    """单个 task: 调用 LLM 生成 queries 并立即追加保存。

    Returns:
        {"topic": ..., "profile_rel": ..., "status": "ok"/"fail", "count": ..., "error": ...}
    """
    try:
        queries = generate_queries(
            topic=topic,
            skills=skills,
            profile=profile,
            llm=llm,
            prompt_tmpl=prompt_tmpl,
            n=n_queries,
        )
        record = {
            "topic": topic,
            "skills": [
                {
                    "skill名称": s.get("skill名称", ""),
                    "skill目录": s.get("skill目录", ""),
                }
                for s in skills
            ],
            "queries": queries,
        }
        _append_record_to_file(out_path, profile_rel, record, file_lock)
        print(f"  [OK] topic「{topic}」× profile「{profile_rel}」→ {len(queries)} 条 query")
        return {"topic": topic, "profile_rel": profile_rel, "status": "ok", "count": len(queries)}
    except Exception as e:
        import traceback
        print(f"  [FAIL] topic「{topic}」× profile「{profile_rel}」→ {e}")
        traceback.print_exc()
        return {"topic": topic, "profile_rel": profile_rel, "status": "fail", "error": str(e)}


def parse_args():
    cfg      = load_config()
    gen_cfg  = cfg.get("query_gen_with_topic_skill_profile_config", {})

    parser = argparse.ArgumentParser(
        description="根据 topics + skills + user_profile 生成 query"
    )
    parser.add_argument(
        "--topics-txt",
        type=str,
        default=gen_cfg.get("topics_txt_path", "Outputs/topics.txt"),
        help="topics.txt 路径（相对于项目根目录）",
    )
    parser.add_argument(
        "--profile-dir",
        type=str,
        default=gen_cfg.get("profile_dir", "Outputs/profiles"),
        help="用户 profile 所在文件夹（相对于项目根目录）",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=gen_cfg.get("output_dir", "Outputs/queries_with_skills"),
        help="输出目录（相对于项目根目录）",
    )
    parser.add_argument(
        "--num-user-per-topic",
        type=int,
        default=gen_cfg.get("num_user_per_topic"),
        help="每个 topic 最多使用多少个 profile，默认 None 表示全部使用",
    )
    parser.add_argument(
        "--queries-per-combination",
        type=int,
        default=gen_cfg.get("queries_per_combination", 5),
        help="每组 (topic, profile) 生成的 query 数量",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        default=gen_cfg.get("skip_existing", True),
        help="跳过已生成结果的 profile",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    _banner("query_gen_with_topic_skill_profile — 根据 topics + skills + profile 生成 query")

    # ── 解析路径 ────────────────────────────────────────────────────────────
    topics_path = Path(args.topics_txt)
    if not topics_path.is_absolute():
        topics_path = (_PROJECT_ROOT / topics_path).resolve()

    profile_dir = Path(args.profile_dir)
    if not profile_dir.is_absolute():
        profile_dir = (_PROJECT_ROOT / profile_dir).resolve()

    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = (_PROJECT_ROOT / output_dir).resolve()

    n_queries = args.queries_per_combination
    num_user_per_topic = args.num_user_per_topic

    # ── 加载 topics ─────────────────────────────────────────────────────────
    topics = load_topics(topics_path)
    print(f"\n  topics 文件: {topics_path}")
    print(f"  提取到 {len(topics)} 个 topic: {topics}")

    # ── 加载 profiles ───────────────────────────────────────────────────────
    all_profiles = load_profiles(profile_dir)
    print(f"\n  profile 目录: {profile_dir}")
    print(f"  找到 {len(all_profiles)} 个 profile")
    if num_user_per_topic is not None:
        print(f"  每个 topic 随机选取 {num_user_per_topic} 个 profile")
    print()

    if not all_profiles:
        print("[Info] 无 profile 文件，退出")
        return 0

    # ── 加载 prompt 模板 ────────────────────────────────────────────────────
    cfg     = load_config()
    gen_cfg = cfg.get("query_gen_with_topic_skill_profile_config", {})
    prompt_rel = gen_cfg.get("PROMPT_TMPL", "prompts/query_gen_with_topic_skill_profile_prompt.md")
    prompt_tmpl = get_prompt(prompt_rel)

    # ── 初始化 LLM ──────────────────────────────────────────────────────────
    llm = _init_llm()

    # ── 创建输出目录 ────────────────────────────────────────────────────────
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── 读取并发度 ──────────────────────────────────────────────────────────
    pipeline_cfg = cfg.get("pipeline_config", {})
    max_workers = int(os.getenv("MAX_LLM_CALLS", pipeline_cfg.get("MAX_LLM_CALLS", 4)))
    print(f"  并发度 (MAX_LLM_CALLS): {max_workers}")

    # ── 组装所有 (topic, profile) 排列组合为 task 列表 ───────────────────────
    # 每个 task 独立查询 skills（利用查询接口的随机性）
    # 每个 profile 的输出文件用一把锁保护并发写入
    file_locks: dict[str, threading.Lock] = {}   # out_path_str -> Lock
    tasks = []

    for topic in topics:
        # 为当前 topic 选取 profiles
        if num_user_per_topic is not None and num_user_per_topic < len(all_profiles):
            selected_profiles = random.sample(all_profiles, num_user_per_topic)
        else:
            selected_profiles = list(all_profiles)

        for profile_rel, profile in selected_profiles:
            profile_stem = Path(profile_rel).stem
            out_path = output_dir / f"{profile_stem}_queries.json"
            out_path_str = str(out_path)

            # skip-existing: 检查该 profile 的输出文件中是否已包含此 topic
            if args.skip_existing and out_path.exists():
                try:
                    existing = json.loads(out_path.read_text(encoding="utf-8"))
                    existing_topics = {r.get("topic") for r in existing.get("results", [])}
                    if topic in existing_topics:
                        continue
                except Exception:
                    pass

            # 为此 task 实时查询 skills（每次调用有随机性）
            skills = search_skills_by_topic(topic)
            if not skills:
                print(f"  [SKIP] topic「{topic}」无匹配 skills")
                continue

            if out_path_str not in file_locks:
                file_locks[out_path_str] = threading.Lock()

            tasks.append({
                "topic": topic,
                "skills": skills,
                "profile_rel": profile_rel,
                "profile": profile,
                "out_path": out_path,
                "file_lock": file_locks[out_path_str],
            })

    print(f"  共组装 {len(tasks)} 个 task（topic × profile 排列组合）\n")

    if not tasks:
        print("[Info] 无需执行的 task，退出")
        return 0

    # ── 线程池并发执行 ──────────────────────────────────────────────────────
    total_success = total_fail = 0

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(
                _run_task,
                topic=t["topic"],
                skills=t["skills"],
                profile_rel=t["profile_rel"],
                profile=t["profile"],
                llm=llm,
                prompt_tmpl=prompt_tmpl,
                n_queries=n_queries,
                out_path=t["out_path"],
                file_lock=t["file_lock"],
            ): t
            for t in tasks
        }
        for future in as_completed(futures):
            result = future.result()
            if result["status"] == "ok":
                total_success += 1
            else:
                total_fail += 1

    # ── 汇总 ────────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"  LLM 调用: 成功 {total_success}  失败 {total_fail}")
    print(f"  共 {len(tasks)} 个 task")
    print("=" * 60)
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    exit(main())
