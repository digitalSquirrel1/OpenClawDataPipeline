# -*- coding: utf-8 -*-
"""
Step 2 — Computer Spec Designer
设计完整的 Windows 电脑环境：深层目录结构 + 丰富文件列表（目标 55-70 个文件）。

文件类型说明：
  type = "downloadable"  → 网络上可公开获取
    sub_type: "pdf"      → 直接下载 .pdf 二进制
               "html"    → 下载并保存为 .html 页面
               "excel"   → 搜索并下载 .xlsx/.xls
               "csv"     → 搜索并下载 .csv
  type = "generated"    → 由 LLM 生成内容
    format: csv / xlsx / docx / txt / md / pptx / py / json

设计策略：多次分类调用，每次仅生成一个类别的文件列表，避免单次输出被截断。
"""
import json
import sys
import threading
import concurrent.futures
from pathlib import Path
from utils.llm_client import LLMClient

# ─── 加载配置 ──────────────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # user_simulator_agent/
sys.path.insert(0, str(_PROJECT_ROOT))
from config.config_loader import load_config, get_prompt

_cfg = load_config()
_spec_cfg = _cfg.get("computer_spec_designer_config", {})


def _load_prompt(key: str) -> str:
    path = _spec_cfg.get(key)
    return get_prompt(path) if path else ""


SYSTEM = "你是一名专业的IT环境模拟专家。你的任务是设计一个高度真实的Windows用户电脑环境。只输出合法JSON，不要有任何注释或多余文字。"

PROMPT_DIRS        = _load_prompt("PROMPT_DIRS")
PROMPT_PDF         = _load_prompt("PROMPT_PDF")
PROMPT_HTML        = _load_prompt("PROMPT_HTML")
PROMPT_EXCEL_CSV   = _load_prompt("PROMPT_EXCEL_CSV")
PROMPT_DOCX        = _load_prompt("PROMPT_DOCX")
PROMPT_XLSX        = _load_prompt("PROMPT_XLSX")
PROMPT_MD          = _load_prompt("PROMPT_MD")
PROMPT_IMAGE       = _load_prompt("PROMPT_IMAGE")
PROMPT_VIDEO       = _load_prompt("PROMPT_VIDEO")
PROMPT_AUDIO       = _load_prompt("PROMPT_AUDIO")
PROMPT_FILE_COUNTS = _load_prompt("PROMPT_FILE_COUNTS")
PROMPT_ENVCONFIG   = _load_prompt("PROMPT_ENVCONFIG")


class ComputerSpecDesigner:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    def design(self, profile: dict) -> dict:
        profile_json = json.dumps(profile, ensure_ascii=False, indent=2)
        username = profile.get("username", "user")

        # ── Step 1: directories ──────────────────────────────────────────────
        print("[Step 1] 设计目录结构...")
        dirs_spec = self.llm.generate_json(
            PROMPT_DIRS.format(profile_json=profile_json, username=username),
            # max_tokens=3000
        )
        directories = dirs_spec.get("directories", [])
        print(f"  -> {len(directories)} 个目录")
        dirs_json = json.dumps(directories, ensure_ascii=False)

        # ── Step 2: file counts ─────────────────────────────────────────────
        print("[Step 2] 确定各类文件数量...")
        counts_spec = self.llm.generate_json(
            PROMPT_FILE_COUNTS.format(profile_json=profile_json),
            # max_tokens=2000
        )
        file_counts = counts_spec.get("file_counts", {})
        print(f"  -> 文件数量配置: {file_counts}")

        # ── Step 3: files per category（并行调用，3个worker避免API限速）────────
        all_files: list[dict] = []
        results_lock = threading.Lock()
        cat_results: dict[str, list] = {}

        categories = [
            ("PDF文件(可下载)",     PROMPT_PDF,       3000, file_counts.get("PDF文件(可下载)", 15)),
            ("HTML网页(可下载)",    PROMPT_HTML,      2500, file_counts.get("HTML网页(可下载)", 10)),
            ("Excel/CSV(可下载)",   PROMPT_EXCEL_CSV, 2000, file_counts.get("Excel/CSV(可下载)", 6)),
            ("图片文件(可下载)",     PROMPT_IMAGE,     2500, file_counts.get("图片文件(可下载)", 12)),
            ("视频文件(可下载)",     PROMPT_VIDEO,     2500, file_counts.get("视频文件(可下载)", 6)),
            ("音频文件(可下载)",     PROMPT_AUDIO,     2500, file_counts.get("音频文件(可下载)", 5)),
            ("Word/文本(生成)",     PROMPT_DOCX,      3000, file_counts.get("Word/文本(生成)", 20)),
            ("Excel/CSV(生成)",     PROMPT_XLSX,      2500, file_counts.get("Excel/CSV(生成)", 15)),
            ("Markdown报告(生成)",  PROMPT_MD,        2500, file_counts.get("Markdown报告(生成)", 8)),
        ]

        print(f"[Step 3] 并行设计 {len(categories)} 个文件类别...")

        def design_category(cat_name, tmpl, max_tok, file_count):
            try:
                prompt = tmpl.format(
                    profile_json=profile_json,
                    dirs_json=dirs_json,
                    username=username,
                    file_count=file_count,
                )
                result = self.llm.generate_json(
                    prompt, 
                    # max_tokens=max_tok
                )
                files = result.get("files", [])
                print(f"  -> [{cat_name}] +{len(files)} 个文件")
                return cat_name, files
            except Exception as e:
                print(f"  [!] {cat_name} 设计失败: {repr(e)}")
                return cat_name, []

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(design_category, cat_name, tmpl, max_tok, file_count): cat_name
                for cat_name, tmpl, max_tok, file_count in categories
            }
            # 按类别顺序合并（保证路径去重稳定）
            ordered_results = {}
            for future in concurrent.futures.as_completed(futures):
                cat_name, files = future.result()
                ordered_results[cat_name] = files

        # 按原始顺序合并，去重
        seen_paths: set[str] = set()
        for cat_name, _, _, _ in categories:
            for f in ordered_results.get(cat_name, []):
                path = f.get("path", "")
                if path and path not in seen_paths:
                    seen_paths.add(path)
                    all_files.append(f)

        print(f"[Step 4] 文件规划完成，共 {len(all_files)} 个文件，{len(directories)} 个目录")

        # ── Step 4: env_config ───────────────────────────────────────────────
        print("[Step 5] 设计电脑环境配置（env_config）...")
        prompt_env = PROMPT_ENVCONFIG.format(
            name=profile.get("name", "用户"),
            role=profile.get("role", ""),
            company=profile.get("company", ""),
            username=username,
            hostname=profile.get("hostname", "PC"),
            tools=", ".join(profile.get("core_tools", [])),
        )
        try:
            env_config = self.llm.generate_json(
                prompt_env, 
                # max_tokens=4096
            )
        except Exception as e:
            print(f"  [!] env_config 生成失败: {e}")
            env_config = {}

        return {
            "directories": directories,
            "files": all_files,
            "env_config": env_config,
        }
