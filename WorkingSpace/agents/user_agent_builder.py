# -*- coding: utf-8 -*-
"""
Step 4 — User Agent Builder
Generates a self-contained user_agent.py that simulates the user
doing a specific task while interacting with an external AI assistant.
"""
import json
import sys
from pathlib import Path
from utils.llm_client import LLMClient

# ─── 加载配置 ──────────────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # user_simulator_agent/
sys.path.insert(0, str(_PROJECT_ROOT))
from config.config_loader import load_config, get_prompt

_cfg = load_config()
_builder_cfg = _cfg.get("user_agent_builder_config", {})

_prompt_path = _builder_cfg.get("PROMPT_TMPL")
PROMPT_TMPL = get_prompt(_prompt_path) if _prompt_path else ""

SYSTEM = "你是一名资深AI应用开发工程师，擅长设计角色扮演型AI Agent。只输出纯Python代码。"


def _build_file_summary(spec: dict) -> str:
    lines = []
    for f in spec.get("files", [])[:20]:
        lines.append(f"  - {f['path']}  ({f.get('description','')})")
    return "\n".join(lines)


class UserAgentBuilder:
    def __init__(self, llm: LLMClient,
                 api_key: str, base_url: str, model: str):
        self.llm      = llm
        self.api_key  = api_key
        self.base_url = base_url
        self.model    = model

    def build(self, profile: dict, spec: dict) -> str:
        """Return the content of user_agent.py as a string."""
        print("[Step 4] 生成 user_agent.py ...")
        file_summary = _build_file_summary(spec)
        prompt = PROMPT_TMPL.format(
            profile_json     = json.dumps(profile, ensure_ascii=False, indent=2),
            file_summary     = file_summary,
            task_description = profile.get("task_description", ""),
            task_context     = profile.get("task_context", ""),
            api_key          = self.api_key,
            base_url         = self.base_url,
            model            = self.model,
        )
        code = self.llm.generate(prompt, system=SYSTEM, temperature=0.4)
        # strip markdown fences if present
        code = code.strip()
        if code.startswith("```"):
            lines = code.split("\n")
            code  = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
        print(f"  → 生成代码 {len(code)} chars")
        return code

    def save(self, code: str, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)
        print(f"  → 已保存：{path}")
