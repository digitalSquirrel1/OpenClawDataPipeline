# -*- coding: utf-8 -*-
"""
Step 1 — Profile Analyzer
Parses free-text user_profile.txt into a structured JSON dict.
"""
import sys
from pathlib import Path
from utils.llm_client import LLMClient

# ─── 加载配置 ──────────────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # user_simulator_agent/
sys.path.insert(0, str(_PROJECT_ROOT))
from config.config_loader import load_config, get_prompt

_cfg = load_config()
_analyzer_cfg = _cfg.get("profile_analyzer_config", {})

_prompt_path = _analyzer_cfg.get("PROMPT_TMPL")
PROMPT_TMPL = get_prompt(_prompt_path) if _prompt_path else ""

SYSTEM = "你是一名精通用户研究的专家，擅长将自然语言用户画像转化为结构化数据。只输出合法JSON。"


class ProfileAnalyzer:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    def analyze(self, profile_text: str) -> dict:
        print("[Step 1] 分析用户画像...")
        prompt = PROMPT_TMPL.format(profile_text=profile_text.strip())
        result = self.llm.generate_json(prompt, system=SYSTEM)
        print(f"  → 生成角色：{result.get('name')}，{result.get('role')}")
        return result
