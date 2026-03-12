# -*- coding: utf-8 -*-
"""
Skills 倒排索引构建器
====================
读取 skills.json，按 "skill可用场景" 构建 topic → [完整skill信息] 的倒排索引，
保存为 skills_index.json（与 skills.json 同目录）。

用法:
    python shared/skills_topic_to_index.py
"""

import sys, json
from pathlib import Path

# ─── 项目路径设置 ───────────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
from config.config_loader import load_config


def build_index(skills_json_path: Path) -> Path:
    """
    读取 skills.json，构建倒排索引并保存到同目录下的 skills_index.json。

    Returns:
        输出文件路径
    """
    with open(skills_json_path, encoding="utf-8") as f:
        skills = json.loads(f.read())

    index: dict[str, list[dict]] = {}
    for skill in skills:
        for topic in skill.get("skill可用场景", []):
            index.setdefault(topic, []).append(skill)

    output_path = skills_json_path.parent / "skills_index.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    print(f"[OK] 倒排索引已保存: {output_path}")
    print(f"     共 {len(index)} 个 topic，覆盖 {len(skills)} 个 skill")
    return output_path


def main():
    cfg = load_config()
    search_cfg = cfg.get("topic_search_skills_config", {})
    skills_json_rel = search_cfg.get("skills_json_path", "Outputs/skills.json")
    skills_json_path = _PROJECT_ROOT / skills_json_rel

    if not skills_json_path.exists():
        print(f"[Error] skills.json 不存在: {skills_json_path}")
        return 1

    build_index(skills_json_path)
    return 0


if __name__ == "__main__":
    exit(main())
