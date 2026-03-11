# -*- coding: utf-8 -*-
"""
uquery_generate.py — 为 data/ 目录结构生成 user_queries.json
=============================================================
从 profile 文件夹中读取 user_profile.json 和 MAP_Linux.json，
调用 LLM 按指定任务列表生成用户 query，写入 user_queries.json。

目录结构（输入/输出）：
  data/
  └── profile_1/
      ├── user_profile.json      ← 用户画像（必需，或 profile_analyzed.json）
      ├── computer_profile/      ← 文件系统目录
      ├── MAP_Linux.json         ← Linux 路径映射（优先使用）
      ├── MAP_Windows.json       ← Windows 路径映射（备选）
      └── user_queries.json      ← 输出

使用方式：
  # 默认：生活类10条 + 学习类10条，8并发
  python uquery_generate.py --data-dir Outputs/environments

  # 多倾向各自指定数量
  python uquery_generate.py --data-dir data --tendency 生活类 学习类 工作类 --count 10 10 5

  # 跳过已生成的
  python uquery_generate.py --data-dir data --skip-existing
"""

import os, sys, json, argparse, random, re, threading
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

# ─── 路径设置 ────────────────────────────────────────────────────────────────
_CONTROL_CENTER = Path(__file__).resolve().parent
_PROJECT_ROOT   = _CONTROL_CENTER.parent

sys.path.insert(0, str(_PROJECT_ROOT))

from config.config_loader import load_config
from shared.llm_caller import chat_with_retry

_cfg     = load_config()
_api_cfg = _cfg.get("api_config", {})
_gen_cfg = _cfg.get("uquery_generate_config", {})

LLM_MODEL = os.getenv("LLM_MODEL", _api_cfg.get("LLM_MODEL", "gpt-4o"))

# ─── 倾向分类说明 ─────────────────────────────────────────────────────────────
TENDENCY_DESCRIPTIONS = {
    "生活类": """个人生活助手场景（非工作/非学习），覆盖：
    - 娱乐兴趣与资讯推荐（影音、游戏、书籍、订阅等）
    - 出行与订购（机票、酒店、外卖、快递等）
    - 日常事务与日程提醒（账单、预约、备忘等）
    - 健康与习惯养成、个人理财、家居管理等""",

    "学习类": """学习与知识管理场景，覆盖：
    - 知识搜索与研究（查资料、了解概念、行业调研等）
    - 学习资料管理（整理笔记、归档文档、制作摘要等）
    - 学习计划与课程管理（制定计划、跟踪进度等）
    - 习题练习与错题复盘等""",

    "工作类": """工作与职业场景，覆盖：
    - 文件与项目管理（整理、归档、批量处理等）
    - 数据处理与分析（清洗、可视化、报表等）
    - 文档与内容创作（撰写、PPT、格式转换等）
    - 工作流自动化、跨软件协作等""",
}

def _load_default_tasks():
    tasks_cfg = _gen_cfg.get("tasks")
    if tasks_cfg:
        return [(t["tendency"], int(t["count"])) for t in tasks_cfg]
    return [(_gen_cfg.get("tendency", "生活类"), int(_gen_cfg.get("count", 10))),
            ("学习类", 10)]

DEFAULT_TASKS        = _load_default_tasks()
DEFAULT_CONCURRENCY  = int(_gen_cfg.get("max_concurrency", 8))

# ─── Prompt 模板 ─────────────────────────────────────────────────────────────
_PROMPT_TEMPLATE = """根据以下用户画像和用户电脑中的文件结构，生成 {count} 个用户日常可能在电脑上执行的自然语言 query。

--- 用户画像 ---
{profile_summary}
--- end ---

--- 用户电脑文件结构（部分采样，Linux 路径） ---
{file_samples}
--- end ---

【Query 倾向】：{tendency}
{tendency_desc}

已知电脑可实现的操作包括但不限于：
• 文件管理：查找、整理、重命名、删除、批量处理
• 数据处理：数据清洗、分析、可视化
• 文档编辑：撰写、修改、格式转换
• 网络/本地信息操作：网络搜索、数据库操作、调研推荐
• 通信与日程：邮件、闹钟、提醒、任务管理
• 内容整合：图表生成、摘要、合规校验
• 形式化展示：网页、PPT、海报制作
• 浏览器操作：社区互动、资料爬取、GitHub 管理
• 系统操作管理、常用 App/软件操作
• 生活技能：出行订改、购物选品、地图查询、健康管理、理财
• 多模态处理：语音/图像/视频的编辑、识别、生成、分析

生成规则：
1. Query 必须完全具体、可直接执行，无模糊信息，无歧义
2. 严禁宽泛性 query（如"对图片进行处理"——不知道如何处理）
3. 涉及文件时必须使用文件结构中真实存在的路径
4. Query 种类尽量多样，不要全部集中于同一操作类型
5. Query 要符合该用户的性格、职业背景和实际使用习惯
6. 禁止生成需要账号登录、注册或付费才能完成的 query（如"登录微信""注册账号"等）
7. 每条 query 直接描述任务本身，不加任何序号前缀

输出严格的 JSON 格式（只有 queries 数组）：
{{
  "queries": [
    "...",
    "...",
    ...
  ]
}}"""


# ─── 工具函数 ─────────────────────────────────────────────────────────────────
def _build_profile_summary(profile: dict) -> str:
    """支持 user_profile.json（基本信息键）和 profile_analyzed.json（英文键）两种格式"""
    lines = []

    if "基本信息" in profile:
        basic = profile["基本信息"]
        lines.append(f"姓名：{basic.get('姓名', '未知')}，性别：{basic.get('性别', '')}，年龄：{basic.get('年龄', '')}岁")
        lines.append(f"职业：{basic.get('职业', '')}")
        if basic.get("性格"):
            lines.append(f"性格：{basic['性格']}")
        if basic.get("家庭情况"):
            lines.append(f"家庭情况：{basic['家庭情况']}")
        if basic.get("身体情况"):
            lines.append(f"身体情况：{basic['身体情况']}")
        life_prefs = profile.get("生活喜好", [])
        if life_prefs:
            lines.append("\n生活喜好：")
            for p in life_prefs[:6]:
                lines.append(f"  - {p}")
        work_prefs = profile.get("学习工作喜好", [])
        if work_prefs:
            lines.append("\n学习/工作喜好：")
            for p in work_prefs[:4]:
                lines.append(f"  - {p}")
        tools = profile.get("常用电脑工具", [])
        if tools:
            lines.append(f"\n常用工具：{'、'.join(tools[:8]) if isinstance(tools, list) else tools}")
        websites = profile.get("常用网站", [])
        if websites:
            lines.append(f"常用网站：{'、'.join(websites[:6]) if isinstance(websites, list) else websites}")
    else:
        lines.append(f"姓名：{profile.get('name', '未知')}，性别：{profile.get('gender', '')}，年龄：{profile.get('age', '')}岁")
        lines.append(f"职业：{profile.get('role', '')}，行业：{profile.get('industry', '')}")
        lines.append(f"公司/部门：{profile.get('company', '')} / {profile.get('department', '')}")
        personality = profile.get("personality", [])
        if personality:
            lines.append(f"性格：{'、'.join(personality)}")
        work_focus = profile.get("work_focus", [])
        if work_focus:
            lines.append("\n工作重心：")
            for w in work_focus[:4]:
                lines.append(f"  - {w}")
        tools = profile.get("core_tools", [])
        if tools:
            lines.append(f"\n常用工具：{'、'.join(tools[:8])}")
        file_types = profile.get("file_types", [])
        if file_types:
            lines.append(f"常用文件类型：{'、'.join(file_types[:8])}")
        style = profile.get("file_organization_style", "")
        if style:
            lines.append(f"文件习惯：{style}")

    return "\n".join(lines)


def _build_file_samples(profile_dir: Path, max_samples: int = 40) -> str:
    mapping = None
    for map_file in (profile_dir / "MAP_Linux.json", profile_dir / "MAP_Windows.json"):
        if map_file.exists():
            try:
                mapping = json.loads(map_file.read_text(encoding="utf-8"))
                break
            except Exception:
                pass

    if not mapping:
        computer_profile = profile_dir / "computer_profile"
        if not computer_profile.exists():
            return "  （未找到文件结构信息）"
        paths = []
        for fp in computer_profile.rglob("*"):
            if fp.is_file():
                parts = fp.relative_to(computer_profile).parts
                if len(parts) >= 2 and len(parts[0]) == 1 and parts[0].isalpha():
                    paths.append(str(fp.relative_to(computer_profile)).replace("\\", "/"))
        mapping = {p: p for p in paths}

    all_paths = list(mapping.values())
    sampled = random.sample(all_paths, max_samples) if len(all_paths) > max_samples else all_paths
    return "\n".join(f"  {p}" for p in sorted(sampled))


def _call_llm_for_tendency(tendency, count, profile_summary, file_samples):
    import time
    prompt = _PROMPT_TEMPLATE.format(
        count=count,
        profile_summary=profile_summary,
        file_samples=file_samples,
        tendency=tendency,
        tendency_desc=TENDENCY_DESCRIPTIONS.get(tendency, ""),
    )
    start = time.time()
    content = chat_with_retry(
        messages=[{"role": "user", "content": prompt}],
        model=LLM_MODEL,
    )
    elapsed = time.time() - start

    code_block = re.search(r'```(?:json)?\s*(.*?)```', content, re.DOTALL)
    if code_block:
        json_str = code_block.group(1).strip()
    else:
        first, last = content.find("{"), content.rfind("}")
        json_str = content[first:last + 1] if first != -1 and last > first else content

    try:
        queries = json.loads(json_str).get("queries", [])
    except json.JSONDecodeError as e:
        print(f"  [Error] JSON 解析失败: {e}\n  [Debug] {json_str[:300]}...")
        queries = []

    return queries, elapsed


def generate_queries_for_profile(profile_dir: Path, tasks):
    """为单个 profile 文件夹生成 queries，写入 user_queries.json。返回 groups dict。"""
    profile_path = profile_dir / "user_profile.json"
    if not profile_path.exists():
        profile_path = profile_dir / "profile_analyzed.json"
    if not profile_path.exists():
        raise FileNotFoundError(f"缺少 user_profile.json 或 profile_analyzed.json: {profile_dir}")

    profile         = json.loads(profile_path.read_text(encoding="utf-8"))
    profile_summary = _build_profile_summary(profile)
    file_samples    = _build_file_samples(profile_dir)

    groups = {}
    for tendency, count in tasks:
        queries, elapsed = _call_llm_for_tendency(tendency, count, profile_summary, file_samples)
        groups[tendency] = queries

    all_queries = [q for qs in groups.values() for q in qs]
    output = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tasks": [{"tendency": t, "count": c} for t, c in tasks],
        "total": len(all_queries),
        "groups": groups,
        "queries": all_queries,
    }
    out_path = profile_dir / "user_queries.json"
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return groups


# ─── CLI ─────────────────────────────────────────────────────────────────────
def _parse_tasks_from_args(tendencies, counts):
    if len(counts) == 1:
        return [(t, counts[0]) for t in tendencies]
    if len(counts) == len(tendencies):
        return list(zip(tendencies, counts))
    raise ValueError(f"--count 数量({len(counts)}) 必须为 1 或与 --tendency 数量({len(tendencies)}) 相同")


def parse_args():
    default_tendencies = [t for t, _ in DEFAULT_TASKS]
    default_counts     = [c for _, c in DEFAULT_TASKS]

    parser = argparse.ArgumentParser(description="为 data/ 目录结构生成 user_queries.json")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--profile-dir", type=str, help="单个 profile 文件夹路径")
    group.add_argument("--data-dir",    type=str, help="data 根目录，批量处理所有子文件夹")

    parser.add_argument("--tendency", nargs="+", default=default_tendencies,
                        choices=list(TENDENCY_DESCRIPTIONS.keys()), metavar="TENDENCY",
                        help=f"query 倾向，可多个（默认: {default_tendencies}）")
    parser.add_argument("--count", nargs="+", type=int, default=default_counts, metavar="N",
                        help=f"每组数量，单个值应用于所有倾向（默认: {default_counts}）")
    parser.add_argument("--max-concurrency", type=int, default=DEFAULT_CONCURRENCY,
                        help=f"并发数（默认: {DEFAULT_CONCURRENCY}）")
    parser.add_argument("--skip-existing", action="store_true",
                        default=bool(_gen_cfg.get("skip_existing", True)),
                        help="跳过已存在 user_queries.json 的文件夹")
    return parser.parse_args()


def main():
    args  = parse_args()
    tasks = _parse_tasks_from_args(args.tendency, args.count)

    print("\n" + "=" * 60)
    print("  uquery_generate — 生成 user_queries.json")
    print("=" * 60)
    for tendency, count in tasks:
        print(f"  [{tendency}] {count} 条")
    print(f"  并发数: {args.max_concurrency}")

    if args.profile_dir:
        profile_dir = Path(args.profile_dir)
        if not profile_dir.is_absolute():
            profile_dir = (_PROJECT_ROOT / profile_dir).resolve()
        if not profile_dir.exists():
            print(f"\n[Error] 文件夹不存在: {profile_dir}")
            return 1
        if args.skip_existing and (profile_dir / "user_queries.json").exists():
            print(f"\n[SKIP] user_queries.json 已存在")
            return 0
        print(f"\n[处理] {profile_dir.name}")
        try:
            groups = generate_queries_for_profile(profile_dir, tasks)
            total = sum(len(v) for v in groups.values())
            print(f"\n[OK] 完成，共 {total} 条")
        except Exception as e:
            import traceback
            print(f"\n[FAIL] {e}")
            traceback.print_exc()
            return 1
        return 0

    # 批量模式
    data_dir = Path(args.data_dir)
    if not data_dir.is_absolute():
        data_dir = (_PROJECT_ROOT / data_dir).resolve()
    if not data_dir.exists():
        print(f"\n[Error] data 目录不存在: {data_dir}")
        return 1

    profile_dirs = sorted({
        p.parent
        for pattern in ("*/user_profile.json", "*/profile_analyzed.json")
        for p in data_dir.glob(pattern)
    })
    if not profile_dirs:
        print(f"\n[Info] 未找到 profile 子文件夹: {data_dir}")
        return 0

    # 过滤已跳过的
    todo = []
    skip = 0
    for pd in profile_dirs:
        if args.skip_existing and (pd / "user_queries.json").exists():
            skip += 1
        else:
            todo.append(pd)

    total_dirs = len(profile_dirs)
    print(f"\n  找到 {total_dirs} 个 profile（跳过 {skip}，待处理 {len(todo)}）")

    if not todo:
        print("\n[Info] 全部已跳过")
        return 0

    # 并发执行
    success = fail = 0
    done    = 0
    lock    = threading.Lock()

    def _task(pd: Path):
        nonlocal done, success, fail
        name = pd.name
        try:
            groups = generate_queries_for_profile(pd, tasks)
            total  = sum(len(v) for v in groups.values())
            with lock:
                done += 1
                success += 1
                print(f"  [{done}/{len(todo)}] ✓ {name} — {total} 条")
        except Exception as e:
            import traceback
            with lock:
                done += 1
                fail += 1
                print(f"  [{done}/{len(todo)}] ✗ {name}: {e}")
                traceback.print_exc()

    print("\n[开始生成]")
    with ThreadPoolExecutor(max_workers=args.max_concurrency) as executor:
        futures = [executor.submit(_task, pd) for pd in todo]
        for f in as_completed(futures):
            f.result()  # 让异常在主线程可见（_task 内已捕获，此处不会抛出）

    print("\n" + "=" * 60)
    print(f"  总计: {total_dirs}  成功: {success}  失败: {fail}  跳过: {skip}")
    print("=" * 60)
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    exit(main())
