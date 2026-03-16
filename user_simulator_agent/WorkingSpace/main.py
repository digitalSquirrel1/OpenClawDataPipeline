# -*- coding: utf-8 -*-
"""
user_simulator_agent — main entry point
========================================
配置 API 密钥后，读取 user_profile.txt，自动完成：
  1. 解析用户画像
  2. 设计电脑环境规格（目录结构 + 文件列表 + env_config）
  3. 生成 / 下载所有文件
  4. 输出 env_config.json
  5. 生成用户查询queries
  6. 打包为 computer_profile.zip

输出目录：./output/
  ├── computer_profile/     ← 模拟电脑文件系统
  │   ├── env_config.json
  │   └── D/研究资料/...
  ├── user_queries.json     ← 用户日常查询
  └── computer_profile.zip  ← 打包版
"""

import os, sys, json, zipfile, time, argparse
from pathlib import Path
from datetime import datetime

# Windows GBK 控制台兼容：强制 stdout/stderr 使用 UTF-8
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ─── ① 在此配置 API 密钥（也可通过环境变量覆盖） ──────────────────────────────
# OpenAI-compatible 后端（默认）
LLM_API_KEY  = os.getenv("LLM_API_KEY",  "sk-U2BkWhBzdLcJn01ovsXXESVO2nboXEjKqjj8WxECS6Dom5UZ")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.gptplus5.com/v1")
LLM_MODEL    = os.getenv("LLM_MODEL",    "gpt-4o")
LLM_PROXY    = os.getenv("LLM_PROXY",    "http://10.90.91.193:3127")
# Anthropic 后端（若 OpenAI 接口不可用，设置 LLM_BACKEND=anthropic
#   并在环境变量中设置 ANTHROPIC_API_KEY 即可切换）
LLM_BACKEND  = os.getenv("LLM_BACKEND",  "openai")   # "openai" | "anthropic"

SERPER_KEY   = os.getenv("SERPER_KEY",   "c18083640ab538baeab47710fe7a93d7f987b754")
JINA_KEY     = os.getenv("JINA_KEY",     "jina_8c9997a799d3462c883b72ac03d53330B2HEHAGXvdyZDKuetE2i0PWOCJeV")

# ─── 并发控制（线程数）──────────────────────────────────────────────────────────
# MAX_WORKERS: 并行下载/生成文件的线程数（I/O密集型，8线程合适）
MAX_WORKERS  = int(os.getenv("MAX_WORKERS", "8"))

# ─── 路径修正（保证从项目根目录运行） ─────────────────────────────────────────
_ROOT = Path(__file__).parent
_PROJECT_ROOT = _ROOT.parent  # 项目根目录（user_simulator_agent）
sys.path.insert(0, str(_ROOT))


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="User Simulator Agent - 根据用户画像生成模拟电脑环境"
    )
    parser.add_argument(
        "--user-profile",
        type=str,
        default="user_profile.txt",
        help="用户画像文件路径（相对于 WorkingSpace 目录）"
    )
    parser.add_argument(
        "--output",
        type=str,
        required=True,
        help="输出目录名称（将保存在项目根目录的 Outputs 下）"
    )
    return parser.parse_args()


def _banner(msg: str) -> None:
    print("\n" + "═" * 60)
    print(f"  {msg}")
    print("═" * 60)


def _zip_dir(src_dir: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fp in src_dir.rglob("*"):
            if fp.is_file():
                zf.write(fp, fp.relative_to(src_dir.parent))
    print(f"  → 打包完成：{zip_path}  ({zip_path.stat().st_size // 1024} KB)")


def _convert_json_profile_to_internal(json_profile: dict, llm: "LLMClient") -> dict:
    """
    将 generate_user_profile.py 生成的 JSON 格式转换为内部使用的格式。

    输入格式（generate_user_profile.py）:
    {
      "基本信息": {"姓名": "...", "性别": "...", "年龄": ..., "职业": "..."},
      "生活喜好": [...],
      "学习工作喜好": [...],
      "常用电脑工具": "...",
      "常用网站": "...",
      "生活类电脑操作Query": [...],
      "学习类电脑操作Query": [...]
    }

    输出格式（ProfileAnalyzer 生成的格式）:
    {
      "name": "...",
      "gender": "...",
      "age": ...,
      "role": "...",
      "industry": "...",
      "company": "...",
      "department": "...",
      "os": "...",
      "username": "...",
      "hostname": "...",
      "drive_layout": ["C", "D"],
      "core_tools": [...],
      "file_types": [...],
      "work_focus": [...],
      "file_organization_style": "...",
      "personality": [...],
      "domain_keywords": [...],
      "task_description": "...",
      "task_context": "..."
    }
    """
    basic = json_profile.get("基本信息", {})
    name = basic.get("姓名", "User")
    role = basic.get("职业", "Unknown")
    gender = basic.get("性别", "男")
    age = basic.get("年龄", 30)
    personality_str = basic.get("性格", "")

    # 生活喜好和学习工作喜好
    life_prefs = json_profile.get("生活喜好", [])
    work_prefs = json_profile.get("学习工作喜好", [])

    # 常用工具和网站
    tools_str = json_profile.get("常用电脑工具", "")
    sites_str = json_profile.get("常用网站", "")
    life_queries = json_profile.get("生活类电脑操作Query", [])
    work_queries = json_profile.get("学习类电脑操作Query", [])

    # 使用 LLM 将文本信息转换为结构化内部格式
    prompt = f"""根据以下用户信息，生成符合指定 JSON 格式的结构化数据。

用户基本信息：
- 姓名：{name}
- 性别：{gender}
- 年龄：{age}
- 职业：{role}
- 性格：{personality_str}

生活喜好：
{chr(10).join(f"  - {p}" for p in life_prefs)}

学习工作喜好：
{chr(10).join(f"  - {p}" for p in work_prefs)}

常用工具：{tools_str}
常用网站：{sites_str}

请只输出符合以下结构的 JSON，不要有任何额外说明：
{{
  "name": "{name}",
  "gender": "{gender}",
  "age": {age},
  "role": "{role}",
  "industry": "根据职业推断的行业",
  "company": "根据职业推断的单位名称",
  "department": "根据工作喜好推断的部门",
  "os": "Windows 11",
  "username": "基于姓名的拼音用户名（小写，如：{name.lower()}_user）",
  "hostname": "{name[:6].upper()}-PC",
  "drive_layout": ["C", "D"],
  "core_tools": 从常用工具中提取的软件列表数组,
  "file_types": 根据职业和工作喜好推断的文件类型数组（如：PDF, XLSX, PPTX, CSV, PY, MD）,
  "work_focus": 从学习工作喜好中提取的工作内容数组，
  "file_organization_style": "根据性格和偏好推断的文件组织习惯描述",
  "personality": [性格特征数组],
  "domain_keywords": 从职业和工作喜好中提取的关键词数组，
  "task_description": "{work_queries[0] if work_queries else '根据日常工作内容描述一个典型任务'}",
  "task_context": "用户当前的工作背景描述"
}}
"""

    system = "你是一名数据转换专家，擅长将用户信息转换为结构化JSON。只输出合法JSON，不要有任何额外说明。"

    print("  [Convert] 将 JSON 用户画像转换为内部格式...")
    result = llm.generate_json(prompt, system=system)
    print(f"  → 转换完成：{result.get('name')}，{result.get('role')}")
    return result


def main() -> None:
    # ── 解析命令行参数 ────────────────────────────────────────────────────────
    args = parse_args()
    USER_PROFILE_PATH = args.user_profile
    OUTPUT_SUBDIR = args.output

    # 输出目录：如果是相对路径，基于当前工作目录；如果是绝对路径直接使用
    OUTPUT_DIR = Path(OUTPUT_SUBDIR)
    if not OUTPUT_DIR.is_absolute():
        OUTPUT_DIR = _ROOT / OUTPUT_SUBDIR

    t0 = time.time()
    _banner("user_simulator_agent 启动")
    print(f"\n  用户画像: {USER_PROFILE_PATH}")
    print(f"  输出目录: {OUTPUT_DIR}")

    # ── 导入子模块 ──────────────────────────────────────────────────────────
    from utils.llm_client          import LLMClient
    from utils.web_tools           import WebTools
    from agents.computer_spec_designer import ComputerSpecDesigner
    from agents.file_processor     import FileProcessor
    from agents.user_query_generate import UserQueryGenerator

    # ── 初始化工具 ──────────────────────────────────────────────────────────
    llm = LLMClient(LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, backend=LLM_BACKEND, proxy=LLM_PROXY if LLM_PROXY else None)
    web = WebTools(SERPER_KEY, JINA_KEY, proxy=LLM_PROXY if LLM_PROXY else None)

    # ── 读取用户画像 ────────────────────────────────────────────────────────
    profile_path = Path(USER_PROFILE_PATH)
    # 如果是相对路径，基于项目根目录解析（支持从任何位置调用）
    if not profile_path.is_absolute():
        # 首先尝试基于 WorkingSpace 目录
        candidate = _ROOT / USER_PROFILE_PATH
        if candidate.exists():
            profile_path = candidate
        else:
            # 尝试基于项目根目录
            candidate = _PROJECT_ROOT / USER_PROFILE_PATH
            if candidate.exists():
                profile_path = candidate
            # 最后直接使用原路径（可能是相对于当前工作目录）

    if not profile_path.exists():
        sys.exit(f"[Error] 找不到 {profile_path}，请先创建该文件。")
    profile_text = profile_path.read_text(encoding="utf-8")
    print(f"\n[读取] {profile_path} ({len(profile_text)} chars)")

    # ── Step 1：分析用户画像 ────────────────────────────────────────────────
    _banner("Step 1 / 4  分析用户画像")

    # 检测是否为 JSON 格式（generate_user_profile.py 生成格式）
    is_json = profile_path.suffix.lower() == ".json"

    if is_json:
        try:
            json_profile = json.loads(profile_text)
            # 使用 LLM 转换 JSON 格式到内部格式
            profile = _convert_json_profile_to_internal(json_profile, llm)
        except json.JSONDecodeError:
            print("  [Warning] JSON 解析失败，降级使用文本解析")
            from agents.profile_analyzer import ProfileAnalyzer
            analyzer = ProfileAnalyzer(llm)
            profile = analyzer.analyze(profile_text)
    else:
        # 使用原有的 ProfileAnalyzer
        from agents.profile_analyzer import ProfileAnalyzer
        analyzer = ProfileAnalyzer(llm)
        profile = analyzer.analyze(profile_text)

    # ── Step 2：设计电脑环境规格 ────────────────────────────────────────────
    _banner("Step 2 / 4  设计电脑环境")
    designer = ComputerSpecDesigner(llm)
    spec     = designer.design(profile)

    # ── 创建输出目录 ────────────────────────────────────────────────────────
    out_dir = Path(OUTPUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    profile_dir = out_dir / "computer_profile"
    profile_dir.mkdir(exist_ok=True)

    # ── Step 3：生成文件系统 ─────────────────────────────────────────────────
    _banner("Step 3 / 4  生成文件 & 目录")
    processor = FileProcessor(llm, web, str(out_dir), max_workers=MAX_WORKERS)
    created   = processor.process(spec, profile)

    # ── 写入 env_config.json ─────────────────────────────────────────────────
    env_cfg = spec.get("env_config", {})
    env_path = profile_dir / "env_config.json"
    env_path.write_text(
        json.dumps(env_cfg, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n  → env_config.json 已写入")

    # ── 写入 README（说明文件） ──────────────────────────────────────────────
    readme = _build_readme(profile, spec, created)
    (profile_dir / "README.md").write_text(readme, encoding="utf-8")

    # ── Step 4：生成用户日常查询 ─────────────────────────────────────────────
    _banner("Step 4 / 4  生成用户查询")
    query_gen = UserQueryGenerator(llm)
    query_result = query_gen.generate(profile, spec)
    
    # 保存queries结果
    queries_path = out_dir / "user_queries.json"
    queries_path.write_text(
        json.dumps(query_result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  → user_queries.json 已写入")

    # ── 打包 computer_profile.zip ────────────────────────────────────────────
    zip_path = out_dir / "computer_profile.zip"
    _zip_dir(profile_dir, zip_path)

    # ── 完成汇总 ─────────────────────────────────────────────────────────────
    elapsed = time.time() - t0
    _banner("完成 [OK]")
    print(f"\n  模拟角色    : {profile.get('name')}（{profile.get('role')}）")
    print(f"  创建文件数  : {len(created)}")
    print(f"  生成查询数  : {len(query_result.get('queries', []))}")
    print(f"  耗时        : {elapsed:.1f} 秒\n")
    print(f"  📁 computer_profile.zip : {zip_path}")
    print(f"  📝 user_queries.json    : {queries_path}")
    print()


def _build_readme(profile: dict, spec: dict, created: list) -> str:
    lines = [
        f"# 模拟电脑环境 — {profile.get('name')}（{profile.get('role')}）",
        "",
        f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**操作系统**: {profile.get('os')}",
        f"**单位**: {profile.get('company')} · {profile.get('department')}",
        "",
        "## 目录结构",
        "```",
        *[f"  {d}" for d in spec.get("directories", [])],
        "```",
        "",
        "## 文件清单",
        "",
    ]
    for f in spec.get("files", []):
        tag = "🌐" if f.get("type") == "downloadable" else "📝"
        lines.append(f"- {tag} `{f['path']}` — {f.get('description','')}")

    return "\n".join(lines)


if __name__ == "__main__":
    main()
