# -*- coding: utf-8 -*-
"""
query_gen_with_topic_skill_profile.py — 根据 topics + skills + user_profile 生成 query
=======================================================================================
流程：
  1. 读取 topics.txt，提取每行中文冒号前的关键词作为 topic
  2. 遍历 profiles_dir 下的所有 profile JSON 文件
  3. 组装 (topic, profile) 排列组合为 task 列表，每个 task 独立查询 skills（利用随机性）
  4. 线程池并发调用 LLM 生成 query，每完成一个 task 立即追加保存到对应 profile 的输出文件
  5. 输出 JSON 含 queries、profile 相对路径、skills 相对路径、topic

两种模式：
  - envs_dir 为 null: 纯 topic + skills + profile 生成（原有逻辑）
  - envs_dir 存在:    额外读取用户电脑文件结构摘要，使用包含本地文件信息的 prompt

使用方式：
  python ControlCenter/query_gen_with_topic_skill_profile.py

  # 指定 topics 文件和 profiles 目录
  python ControlCenter/query_gen_with_topic_skill_profile.py \
      --topics-txt Outputs/topics.txt \
      --profiles-dir Outputs/profiles \
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


def _load_env_info(env_subdir: Path, env_rel_path: str) -> dict | None:
    """从环境子目录中加载文件结构摘要（通过 README.md）。

    Args:
        env_subdir: envs_dir 下某个环境的子目录，如 envs_dir/王爱琴_物业管理员
        env_rel_path: 相对于 envs_dir 的路径名

    目录结构: env_subdir / {同名子目录} / README.md

    Returns:
        {"dir_count": int, "file_types_summary": str, "file_samples": str, "env_rel_path": str}
        如果 README.md 不存在则返回 None。
    """
    env_name = env_subdir.name
    readme_path = env_subdir / env_name / "README.md"
    if not readme_path.exists():
        return None

    content = readme_path.read_text(encoding="utf-8")

    # ── 解析目录 ────────────────────────────────────────────────────────────
    dir_count = 0
    dirs_section = ""
    if "## 目录结构" in content:
        after_dirs = content.split("## 目录结构", 1)[1]
        # 提取 ``` 代码块内容
        if "```" in after_dirs:
            code_block = after_dirs.split("```", 2)
            if len(code_block) >= 2:
                dirs_section = code_block[1].strip()
                dir_count = len([l for l in dirs_section.splitlines() if l.strip()])

    # ── 解析文件清单 ────────────────────────────────────────────────────────
    file_types: dict[str, int] = {}
    file_samples_lines: list[str] = []
    if "## 文件清单" in content:
        after_files = content.split("## 文件清单", 1)[1]
        # 如果后面还有 ## 章节，截断
        next_section = after_files.find("\n## ")
        if next_section != -1:
            after_files = after_files[:next_section]

        for line in after_files.splitlines():
            line = line.strip()
            if not line.startswith("- "):
                continue
            # 格式: - 🌐 `path` — description  或  - 📝 `path` — description
            # 提取路径
            backtick_start = line.find("`")
            backtick_end = line.find("`", backtick_start + 1) if backtick_start != -1 else -1
            if backtick_start == -1 or backtick_end == -1:
                continue
            file_path = line[backtick_start + 1:backtick_end]

            # 提取描述（— 后面的部分）
            desc = ""
            dash_idx = line.find("—", backtick_end)
            if dash_idx != -1:
                desc = line[dash_idx + 1:].strip()

            # 统计文件类型（按后缀）
            suffix = Path(file_path).suffix.lower()
            if suffix:
                file_types[suffix] = file_types.get(suffix, 0) + 1

            # 收集样例
            file_samples_lines.append(f"  - {file_path}")
            if desc:
                file_samples_lines.append(f"    → {desc}")

    # 构建 file_types_summary
    type_summary_lines = []
    for ext, count in sorted(file_types.items(), key=lambda x: x[1], reverse=True):
        type_summary_lines.append(f"  - {ext}: {count}个文件")
    file_types_summary = "\n".join(type_summary_lines) if type_summary_lines else "  无文件类型统计"

    file_samples = "\n".join(file_samples_lines) if file_samples_lines else "  无文件样例"

    return {
        "dir_count": dir_count,
        "file_types_summary": file_types_summary,
        "file_samples": file_samples,
        "env_rel_path": env_rel_path,
    }


def load_profiles_from_envs(
    envs_dir: Path,
    profiles_dir: Path,
) -> list[tuple[str, dict, dict]]:
    """从 envs_dir 遍历子目录，通过 pipeline_meta.json 找到对应的 profile 并加载环境信息。

    流程:
      1. 遍历 envs_dir 下的每个子目录
      2. 读取子目录中的 pipeline_meta.json，提取 source_profile_path
      3. assert source_profile_path 以 profiles_dir 开头
      4. 加载 profile JSON
      5. 加载该环境的 README.md 摘要

    Returns:
        [(profile_rel_path, profile_dict, env_info_dict), ...]

    Raises:
        FileNotFoundError: envs_dir 不存在
        AssertionError: source_profile_path 不以 profiles_dir 开头
    """
    if not envs_dir.exists():
        raise FileNotFoundError(f"envs_dir 不存在: {envs_dir}")

    results = []
    profiles_dir_resolved = profiles_dir.resolve()

    for env_subdir in sorted(envs_dir.iterdir()):
        if not env_subdir.is_dir():
            continue

        meta_path = env_subdir / "pipeline_meta.json"
        if not meta_path.exists():
            print(f"  [Warning] 未找到 pipeline_meta.json: {meta_path}")
            continue

        # 读取 pipeline_meta.json
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        source_profile_path = meta.get("source_profile_path")
        if not source_profile_path:
            print(f"  [Warning] pipeline_meta.json 缺少 source_profile_path: {meta_path}")
            continue

        source_profile_path = Path(source_profile_path).resolve()

        # assert source_profile_path 以 profiles_dir 开头
        assert str(source_profile_path).startswith(str(profiles_dir_resolved)), (
            f"source_profile_path 不以 profiles_dir 开头!\n"
            f"  source_profile_path: {source_profile_path}\n"
            f"  profiles_dir:        {profiles_dir_resolved}"
        )

        if not source_profile_path.exists():
            print(f"  [Warning] profile 文件不存在: {source_profile_path}")
            continue

        # 加载 profile
        profile = json.loads(source_profile_path.read_text(encoding="utf-8"))
        profile_rel = source_profile_path.relative_to(profiles_dir_resolved).as_posix()

        # 加载环境信息
        env_rel_path = env_subdir.name
        env_info = _load_env_info(env_subdir, env_rel_path)
        if env_info is None:
            print(f"  [Warning] 未找到环境 README.md: {env_subdir / env_subdir.name / 'README.md'}")
            continue

        results.append((profile_rel, profile, env_info))

    return results


def generate_queries(
    topic: str,
    skills: list[dict],
    profile: dict,
    llm: LLMClient,
    prompt_tmpl: str,
    n: int = 5,
    env_info: dict | None = None,
) -> list[str]:
    """调用 LLM 为一组 (topic, skills, profile) 生成 queries。

    Args:
        env_info: 环境信息字典（含 dir_count, file_types_summary, file_samples），
                  为 None 时使用不含环境信息的 prompt。

    Returns:
        query 字符串列表

    Raises:
        ValueError: LLM 返回无法解析的 JSON
    """
    skills_info = _format_skills_info(skills)
    profile_json = json.dumps(profile, ensure_ascii=False, indent=2)

    fmt_kwargs = dict(
        topic=topic,
        skills_info=skills_info,
        profile_json=profile_json,
        n=n,
    )

    if env_info is not None:
        fmt_kwargs["dir_count"] = env_info["dir_count"]
        fmt_kwargs["file_types_summary"] = env_info["file_types_summary"]
        fmt_kwargs["file_samples"] = env_info["file_samples"]

    prompt = prompt_tmpl.format(**fmt_kwargs)

    result = llm.generate_json(prompt)
    if isinstance(result, list):
        queries = result
    else:
        queries = result.get("queries", [])
    if not isinstance(queries, list):
        raise ValueError(f"LLM 返回的 queries 不是数组: {type(queries)}")
    return queries


def _append_record_to_file(
    out_path: Path,
    profile_rel: str,
    record: dict,
    lock: threading.Lock,
    env_rel_path: str | None = None,
) -> None:
    """线程安全地将一条 record 追加到 profile 的输出 JSON 文件。

    文件格式:
        { "profile_rel_path": ..., "env_rel_path": ..., "generated_at": ..., "results": [...] }

    若文件已存在，则读取并追加到 results 列表；否则新建。
    env_rel_path 仅在新建文件时写入顶层。
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
            if env_rel_path is not None:
                data["env_rel_path"] = env_rel_path
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
    env_info: dict | None = None,
    system_type: str | None = None,
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
            env_info=env_info,
        )
        record = {
            "topic": topic,
            "system_type": system_type,
            "skills": [
                {
                    "skill名称": s.get("skill名称", ""),
                    "skill目录": s.get("skill目录", ""),
                }
                for s in skills
            ],
            "queries": queries,
        }
        _append_record_to_file(
            out_path, profile_rel, record, file_lock,
            env_rel_path=env_info["env_rel_path"] if env_info else None,
        )
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
        "--profiles-dir",
        type=str,
        default=gen_cfg.get("profiles_dir", "Outputs/profiles"),
        help="用户 profile 所在文件夹（相对于项目根目录）",
    )
    parser.add_argument(
        "--envs-dir",
        type=str,
        default=gen_cfg.get("envs_dir", None),
        help="用户环境目录（相对于项目根目录），为 null 时不读取环境信息",
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

    profiles_dir = Path(args.profiles_dir)
    if not profiles_dir.is_absolute():
        profiles_dir = (_PROJECT_ROOT / profiles_dir).resolve()

    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = (_PROJECT_ROOT / output_dir).resolve()

    # envs_dir: None 或有效路径
    envs_dir = None
    if args.envs_dir:
        envs_dir = Path(args.envs_dir)
        if not envs_dir.is_absolute():
            envs_dir = (_PROJECT_ROOT / envs_dir).resolve()

    n_queries = args.queries_per_combination
    num_user_per_topic = args.num_user_per_topic

    # ── 加载 topics ─────────────────────────────────────────────────────────
    topics = load_topics(topics_path)
    print(f"\n  topics 文件: {topics_path}")
    print(f"  提取到 {len(topics)} 个 topic: {topics}")

    # ── 加载 profiles（根据 envs_dir 是否存在走不同分支）────────────────
    # all_profiles: [(profile_rel, profile_dict), ...]
    # env_info_map:  {profile_rel: env_info_dict}   （仅 envs_dir 模式有值）
    env_info_map: dict[str, dict] = {}

    if envs_dir:
        # envs_dir 模式: 从环境目录的 pipeline_meta.json 反查 profile
        env_entries = load_profiles_from_envs(envs_dir, profiles_dir)
        # skip_existing: 过滤掉 env 子目录下已存在 user_queries.json 的 profile
        if args.skip_existing:
            before = len(env_entries)
            env_entries = [
                (rel, prof, einfo) for rel, prof, einfo in env_entries
                if not (envs_dir / einfo["env_rel_path"] / "user_queries.json").exists()
            ]
            skipped = before - len(env_entries)
            if skipped:
                print(f"  [skip_existing] 跳过 {skipped} 个已有 user_queries.json 的环境")
        all_profiles = [(rel, prof) for rel, prof, _ in env_entries]
        for rel, _, einfo in env_entries:
            env_info_map[rel] = einfo
        print(f"\n  envs_dir: {envs_dir}（从 pipeline_meta.json 加载 profile）")
        print(f"  profiles_dir: {profiles_dir}（用于校验 source_profile_path）")
        print(f"  找到 {len(all_profiles)} 个 profile（含环境信息）")
    else:
        # 纯模式: 直接从 profiles_dir 加载
        all_profiles = load_profiles(profiles_dir)
        print(f"\n  profiles 目录: {profiles_dir}")
        print(f"  找到 {len(all_profiles)} 个 profile")
        print(f"  envs_dir: 未配置（纯 topic+skills+profile 模式）")

    if num_user_per_topic is not None:
        print(f"  每个 topic 随机选取 {num_user_per_topic} 个 profile")
    print()

    if not all_profiles:
        print("[Info] 无 profile 文件，退出")
        return 0

    # ── 加载 prompt 模板 ────────────────────────────────────────────────────
    cfg     = load_config()
    gen_cfg = cfg.get("query_gen_with_topic_skill_profile_config", {})

    if envs_dir:
        # 加载 Windows 和 Linux 两个 env prompt，后续按 MAP 文件选择
        prompt_rel_win = gen_cfg.get(
            "PROMPT_TMPL_ENV",
            "prompts/query_gen_with_topic_skill_profile_env_prompt.md",
        )
        prompt_rel_linux = gen_cfg.get(
            "PROMPT_TMPL_ENV_LINUX",
            "prompts/query_gen_with_topic_skill_profile_env_linux_prompt.md",
        )
        prompt_tmpl_win = get_prompt(prompt_rel_win)
        prompt_tmpl_linux = get_prompt(prompt_rel_linux)
        # 读取 WINDOWS_MAP_RATIO（用于两个 MAP 都存在时的概率选择）
        batch_cfg = cfg.get("batch_generate_config", {})
        win_map_ratio = float(batch_cfg.get("WINDOWS_MAP_RATIO", 0.7))
        prompt_tmpl = None  # 不再统一使用，后面按 task 选择
    else:
        prompt_rel = gen_cfg.get(
            "PROMPT_TMPL",
            "prompts/query_gen_with_topic_skill_profile_prompt.md",
        )
        prompt_tmpl = get_prompt(prompt_rel)
        prompt_tmpl_win = None
        prompt_tmpl_linux = None
        win_map_ratio = 0.7

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

            # 获取 env_info（envs_dir 模式下 env_info_map 中一定有值）
            env_info = env_info_map.get(profile_rel)

            # 为此 task 选择 prompt 模板，并记录 system_type
            if envs_dir and env_info is not None:
                env_subdir = envs_dir / env_info["env_rel_path"]
                has_win_map = (env_subdir / "MAP_Windows.json").exists()
                has_linux_map = (env_subdir / "MAP_Linux.json").exists()
                if has_win_map and not has_linux_map:
                    task_prompt = prompt_tmpl_win
                    system_type = "windows"
                elif has_linux_map and not has_win_map:
                    task_prompt = prompt_tmpl_linux
                    system_type = "linux"
                elif has_win_map and has_linux_map:
                    if random.random() < win_map_ratio:
                        task_prompt = prompt_tmpl_win
                        system_type = "windows"
                    else:
                        task_prompt = prompt_tmpl_linux
                        system_type = "linux"
                else:
                    # 两个都不存在，回退到 Windows prompt
                    task_prompt = prompt_tmpl_win
                    system_type = "windows"
            else:
                task_prompt = prompt_tmpl
                system_type = None

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
                "env_info": env_info,
                "prompt_tmpl": task_prompt,
                "system_type": system_type,
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
                prompt_tmpl=t["prompt_tmpl"],
                n_queries=n_queries,
                out_path=t["out_path"],
                file_lock=t["file_lock"],
                env_info=t["env_info"],
                system_type=t["system_type"],
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
    if envs_dir:
        print(f"  模式: envs_dir（含用户电脑文件结构摘要）")
    else:
        print(f"  模式: 纯 topic+skills+profile")
    print("=" * 60)
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    exit(main())
