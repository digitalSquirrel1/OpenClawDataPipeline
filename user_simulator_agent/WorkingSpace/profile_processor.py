# -*- coding: utf-8 -*-
"""
profile_processor — 用户画像处理核心模块
========================================
提供独立的用户画像处理功能，可被main.py和batch.py共享使用。
"""

import os, sys, json, zipfile, time
from pathlib import Path
from datetime import datetime
from typing import Dict

# Windows GBK 控制台兼容
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def process_profile(config: Dict) -> Dict:
    """
    处理单个用户画像

    Args:
        config: 配置字典，包含：
            - profile_path: 用户画像文件路径
            - output_dir: 输出目录路径
            - llm_api_key: LLM API密钥
            - llm_base_url: LLM API基础URL
            - llm_model: LLM模型名称
            - llm_backend: LLM后端类型 (openai/anthropic)
            - llm_proxy: 代理设置
            - max_workers: 并发线程数
            - serper_key: Serper搜索API密钥
            - jina_key: Jina阅读API密钥

    Returns:
        处理结果字典，包含状态、指标等信息
    """
    profile_path = Path(config["profile_path"])
    output_dir = Path(config["output_dir"])

    result = {
        "profile_path": str(profile_path),
        "output_dir": str(output_dir),
        "status": "processing",
        "error": None,
        "metrics": {}
    }

    try:
        print(f"  开始处理用户画像: {profile_path.name}")

        # ── 导入子模块（避免在模块初始化时导入）────
        _ROOT = Path(__file__).parent
        sys.path.insert(0, str(_ROOT))

        from utils.llm_client          import LLMClient
        from utils.web_tools           import WebTools
        from agents.profile_analyzer   import ProfileAnalyzer
        from agents.computer_spec_designer import ComputerSpecDesigner
        from agents.file_processor     import FileProcessor
        from agents.user_query_generate import UserQueryGenerator

        # ── 初始化工具 ──────────────────────────────────
        llm = LLMClient(
            config.get("llm_api_key"),
            config.get("llm_base_url"),
            config.get("llm_model"),
            backend=config.get("llm_backend", "openai"),
            proxy=config.get("llm_proxy")
        )

        web = WebTools(
            config.get("serper_key"),
            config.get("jina_key"),
            proxy=config.get("llm_proxy")
        )

        # ── 读取用户画像 ──────────────────────────────────
        if not profile_path.exists():
            raise FileNotFoundError(f"用户画像文件不存在: {profile_path}")

        profile_text = profile_path.read_text(encoding="utf-8")
        print(f"  读取用户画像: {len(profile_text)} 字符")

        # ── Step 1：分析用户画像 ───────────────────────────
        print(f"  Step 1/4: 分析用户画像...")
        analyzer = ProfileAnalyzer(llm)
        profile = analyzer.analyze(profile_text)

        # ── Step 2：设计电脑环境规格 ─────────────────────────
        print(f"  Step 2/4: 设计电脑环境...")
        designer = ComputerSpecDesigner(llm)
        spec = designer.design(profile)

        # ── 创建输出目录 ────────────────────────────────
        output_dir.mkdir(parents=True, exist_ok=True)
        profile_dir = output_dir / "computer_profile"
        profile_dir.mkdir(exist_ok=True)

        # ── Step 3：生成文件系统 ───────────────────────────
        print(f"  Step 3/4: 生成文件 & 目录...")
        processor = FileProcessor(llm, web, str(output_dir), max_workers=config.get("max_workers", 8))
        created = processor.process(spec, profile)

        # ── 写入 env_config.json ───────────────────────────
        env_cfg = spec.get("env_config", {})
        env_path = profile_dir / "env_config.json"
        env_path.write_text(
            json.dumps(env_cfg, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        print(f"  env_config.json 已写入")

        # ── 写入 README ───────────────────────────────────
        readme = _build_readme(profile, spec, created)
        (profile_dir / "README.md").write_text(readme, encoding="utf-8")

        # ── Step 4：生成用户日常查询 ─────────────────────────
        print(f"  Step 4/4: 生成用户查询...")
        query_gen = UserQueryGenerator(llm)
        query_result = query_gen.generate(profile, spec)

        # 保存queries结果
        queries_path = output_dir / "user_queries.json"
        queries_path.write_text(
            json.dumps(query_result, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        print(f"  user_queries.json 已写入")

        # ── 打包 computer_profile.zip ───────────────────────
        zip_path = output_dir / "computer_profile.zip"
        _zip_dir(profile_dir, zip_path)

        # ── 收集统计信息 ───────────────────────────────────
        queries_data = None
        if queries_path.exists():
            try:
                queries_data = json.loads(queries_path.read_text(encoding="utf-8"))
            except:
                pass

        file_count = len(list(profile_dir.rglob("*")))
        query_count = len(queries_data.get("queries", [])) if queries_data else 0

        result.update({
            "status": "success",
            "error": None,
            "metrics": {
                "file_count": file_count,
                "query_count": query_count,
                "profile": profile,
                "spec": spec
            },
            "created_files": list(created)
        })

        print(f"  ✓ 处理完成: 文件数={file_count}, 查询数={query_count}")

    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        result.update({
            "status": "failed",
            "error": error_msg,
            "metrics": {}
        })
        print(f"  ✗ 处理失败: {error_msg}")

    return result


def _zip_dir(src_dir: Path, zip_path: Path) -> None:
    """打包目录为zip文件"""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fp in src_dir.rglob("*"):
            if fp.is_file():
                zf.write(fp, fp.relative_to(src_dir.parent))
    size_kb = zip_path.stat().st_size / 1024 if zip_path.exists() else 0
    print(f"  computer_profile.zip 已打包: {size_kb:.2f} KB")


def _build_readme(profile: dict, spec: dict, created: list) -> str:
    """构建README文件内容"""
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


def get_default_config() -> Dict:
    """获取默认配置"""
    return {
        "llm_api_key": os.getenv("LLM_API_KEY", "sk-U2BkWhBzdLcJn01ovsXXESVO2nboXEjKqjj8WxECS6Dom5UZ"),
        "llm_base_url": os.getenv("LLM_BASE_URL", "https://api.gptplus5.com/v1"),
        "llm_model": os.getenv("LLM_MODEL", "gpt-4o"),
        "llm_backend": os.getenv("LLM_BACKEND", "openai"),
        "llm_proxy": os.getenv("LLM_PROXY", "http://10.90.91.193:3127"),
        "max_workers": int(os.getenv("MAX_WORKERS", "8")),
        "serper_key": os.getenv("SERPER_KEY", "c18083640ab538baeab47710fe7a93d7f987b754"),
        "jina_key": os.getenv("JINA_KEY", "jina_8c9997a799d3462c883b72ac03d53330B2HEHAGXvdyZDKuetE2i0PWOCJeV")
    }


# 兼容性函数：让batch.py可以调用
def create_user_simulation(profile_path: str, output_dir: str, config: Dict = None) -> Dict:
    """
    创建用户模拟环境的便捷函数

    Args:
        profile_path: 用户画像文件路径
        output_dir: 输出目录路径
        config: 可选配置（如果为None则使用默认配置）

    Returns:
        处理结果字典
    """
    if config is None:
        config = get_default_config()

    full_config = {
        **config,
        "profile_path": profile_path,
        "output_dir": output_dir
    }

    return process_profile(full_config)