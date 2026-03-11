# -*- coding: utf-8 -*-
"""
Step 4 — User Query Generator
生成用户日常可能会询问的query，基于用户profile和电脑文件内容。

生成的query类型包括：
  • 生活相关：日程安排、娱乐、健康、个人理财等

  • 学习相关：知识问询、技能学习、数据分析、行业研究等

"""
import sys
import json
from pathlib import Path

# 确保 config 可以被 import（WorkingSpace/ 和 user_simulator_agent/ 都加入路径）
_WS = Path(__file__).resolve().parent.parent
_ROOT = _WS.parent
for _p in (str(_WS), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from config.config_loader import load_config, get_prompt
from utils.llm_client import LLMClient

_cfg = load_config().get("user_query_generator_config", {})
_PROMPT_TMPL_PATH = _cfg.get("PROMPT_TMPL", "prompts/user_query_generate_prompt.md")


class UserQueryGenerator:
    """根据用户profile和电脑环境生成用户query"""

    def __init__(self, llm: LLMClient):
        self.llm = llm

    def _build_file_types_summary(self, spec: dict) -> str:
        """构建文件类型摘要"""
        files = spec.get("files", [])
        
        # 按类型统计
        type_counts = {}
        for f in files:
            sub_type = f.get("sub_type", f.get("format", "unknown"))
            type_counts[sub_type] = type_counts.get(sub_type, 0) + 1
        
        # 格式化输出
        summary_lines = []
        for file_type, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
            summary_lines.append(f"  - {file_type}: {count}个文件")
        
        return "\n".join(summary_lines) if summary_lines else "  无文件类型统计"

    def _build_file_samples(self, spec: dict) -> str:
        """收集文件样例"""
        files = spec.get("files", [])
        
        # 取前20个文件作为样例
        samples = []
        for f in files:
            path = f.get("path", "")
            description = f.get("description", "").replace("\n", " ")
            samples.append(f"  - {path}")
            if description:
                samples.append(f"    → {description}")
        
        return "\n".join(samples) if samples else "  无文件样例"

    def generate(self, profile: dict, spec: dict) -> dict:
        """生成用户query"""
        profile_json = json.dumps(profile, ensure_ascii=False, indent=2)
        directories = spec.get("directories", [])
        files = spec.get("files", [])
        
        print("[Step 4] 生成用户日常查询...")
        
        # 构建prompt所需的信息
        file_types_summary = self._build_file_types_summary(spec)
        file_samples = self._build_file_samples(spec)
        
        prompt = get_prompt(_PROMPT_TMPL_PATH).format(
            profile_json=profile_json,
            dir_count=len(directories),
            file_types_summary=file_types_summary,
            file_samples=file_samples,
        )
        
        try:
            result = self.llm.generate_json(
                prompt,
                system="你是一名专业的用户行为分析专家。基于用户的工作特征和文件环境，生成真实、自然的用户查询。只输出合法JSON，不要有任何注释或多余文字。",
                max_tokens=2000
            )
            queries = result.get("queries", [])
            print(f"  → 生成 {len(queries)} 个user query")
            return {
                "queries": queries,
                "profile": profile,
                "spec_summary": {
                    "directories_count": len(directories),
                    "files_count": len(files),
                    "file_types": self._get_file_types(spec),
                }
            }
        except Exception as e:
            print(f"  [!] User query生成失败: {e}")
            return {
                "queries": [],
                "profile": profile,
                "error": str(e),
            }

    def _get_file_types(self, spec: dict) -> dict:
        """获取文件类型统计"""
        files = spec.get("files", [])
        type_counts = {}
        for f in files:
            sub_type = f.get("sub_type", f.get("format", "unknown"))
            type_counts[sub_type] = type_counts.get(sub_type, 0) + 1
        return type_counts