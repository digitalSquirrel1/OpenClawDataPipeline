# -*- coding: utf-8 -*-
"""
user_simulator_agent — main entry point
========================================
配置 API 密钥后，读取 user_profile.txt，自动完成：
  1. 解析用户画像
  2. 设计电脑环境规格（目录结构 + 文件列表 + env_config）
  3. 生成 / 下载所有文件
  4. 输出 env_config.json
  5. 生成 user_agent.py
  6. 打包为 computer_profile.zip

输出目录：./output/
  ├── computer_profile/     ← 模拟电脑文件系统
  │   ├── env_config.json
  │   └── D/研究资料/...
  ├── computer_profile.zip  ← 打包版
  └── user_agent.py         ← 用户代理脚本
"""

import os, sys, json, zipfile, time
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
# Anthropic 后端（若 OpenAI 接口不可用，设置 LLM_BACKEND=anthropic
#   并在环境变量中设置 ANTHROPIC_API_KEY 即可切换）
LLM_BACKEND  = os.getenv("LLM_BACKEND",  "openai")   # "openai" | "anthropic"

SERPER_KEY   = os.getenv("SERPER_KEY",   "c18083640ab538baeab47710fe7a93d7f987b754")
JINA_KEY     = os.getenv("JINA_KEY",     "jina_8c9997a799d3462c883b72ac03d53330B2HEHAGXvdyZDKuetE2i0PWOCJeV")

# ─── 并发控制（线程数）──────────────────────────────────────────────────────────
# MAX_WORKERS: 并行下载/生成文件的线程数（I/O密集型，8线程合适）
MAX_WORKERS  = int(os.getenv("MAX_WORKERS", "8"))

# ─── ② 输入 / 输出路径 ────────────────────────────────────────────────────────
USER_PROFILE_PATH = "user_profile.txt"
OUTPUT_DIR        = "output"

# ─── 路径修正（保证从项目根目录运行） ─────────────────────────────────────────
_ROOT = Path(__file__).parent
sys.path.insert(0, str(_ROOT))
os.chdir(_ROOT)


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


def main() -> None:
    t0 = time.time()
    _banner("user_simulator_agent 启动")

    # ── 导入子模块 ──────────────────────────────────────────────────────────
    from utils.llm_client          import LLMClient
    from utils.web_tools           import WebTools
    from agents.profile_analyzer   import ProfileAnalyzer
    from agents.computer_spec_designer import ComputerSpecDesigner
    from agents.file_processor     import FileProcessor
    from agents.user_agent_builder import UserAgentBuilder

    # ── 初始化工具 ──────────────────────────────────────────────────────────
    llm = LLMClient(LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, backend=LLM_BACKEND)
    web = WebTools(SERPER_KEY, JINA_KEY)

    # ── 读取用户画像 ────────────────────────────────────────────────────────
    profile_path = Path(USER_PROFILE_PATH)
    if not profile_path.exists():
        sys.exit(f"[Error] 找不到 {USER_PROFILE_PATH}，请先创建该文件。")
    profile_text = profile_path.read_text(encoding="utf-8")
    print(f"\n[读取] {USER_PROFILE_PATH} ({len(profile_text)} chars)")

    # ── Step 1：分析用户画像 ────────────────────────────────────────────────
    _banner("Step 1 / 4  分析用户画像")
    analyzer = ProfileAnalyzer(llm)
    profile  = analyzer.analyze(profile_text)

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

    # ── Step 4：生成 user_agent.py ───────────────────────────────────────────
    _banner("Step 4 / 4  生成 user_agent.py")
    builder    = UserAgentBuilder(llm, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL)
    agent_code = builder.build(profile, spec)
    agent_path = out_dir / "user_agent.py"
    builder.save(agent_code, str(agent_path))

    # ── 打包 computer_profile.zip ────────────────────────────────────────────
    zip_path = out_dir / "computer_profile.zip"
    _zip_dir(profile_dir, zip_path)

    # ── 完成汇总 ─────────────────────────────────────────────────────────────
    elapsed = time.time() - t0
    _banner("完成 [OK]")
    print(f"\n  模拟角色    : {profile.get('name')}（{profile.get('role')}）")
    print(f"  创建文件数  : {len(created)}")
    print(f"  耗时        : {elapsed:.1f} 秒\n")
    print(f"  📁 computer_profile.zip : {zip_path}")
    print(f"  🤖 user_agent.py        : {agent_path}")
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
    lines += [
        "",
        "## 任务",
        "",
        profile.get("task_description", ""),
        "",
        "---",
        "*Generated by user_simulator_agent*",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
