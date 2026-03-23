# -*- coding: utf-8 -*-
"""
Topic Search Skills
===================
根据倒排索引按 topic 检索可用的 skills，返回完整 skill 信息列表。
会校验每个 skill 目录是否存在，不存在则剔除并打印警告。

用法:
    # 作为模块
    from shared.topic_search_skills import search_skills_by_topic
    results = search_skills_by_topic("购物")

    # 命令行测试
    python shared/topic_search_skills.py "购物"
"""

import sys, json, random, os
from pathlib import Path

# ─── 项目路径设置 ───────────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
from config.config_loader import load_config

# ─── 加载配置 ──────────────────────────────────────────────────────────────────
_cfg = load_config()
_search_cfg = _cfg.get("topic_search_skills_config", {})

_skills_json_rel = _search_cfg.get("skills_json_path", "Outputs/skills.json")
_skills_json_path = _PROJECT_ROOT / _skills_json_rel

# 倒排索引路径：优先用配置，否则默认 skills.json 同目录下的 skills_index.json
_map_path_cfg = _search_cfg.get("topic_to_skills_map")
if _map_path_cfg:
    _INDEX_PATH = Path(_map_path_cfg)
else:
    _INDEX_PATH = _skills_json_path.parent / "skills_index.json"

_skills_dir_rel = _search_cfg.get("skills_dir", "Outputs/skill_localize/skills_library")
_SKILLS_DIR = _PROJECT_ROOT / _skills_dir_rel
_MAX_SKILLS = _search_cfg.get("max_skills_per_topic", 5)


def search_skills_by_topic(
    topic: str,
    max_skills: int | None = None,
    filter_account_dependent_skills: bool = True,
) -> list[dict]:
    """
    根据 topic 检索 skills。

    Args:
        topic: 要检索的场景/话题
        max_skills: 最多返回数量，None 则使用配置的 max_skills_per_topic
        filter_account_dependent_skills: 为 True 时过滤掉 "skill账号依赖" 非空的 skill，
            只保留该字段为空字符串的；为 False 则不过滤。默认 True。

    Returns:
        skill 信息字典列表（字段与 skills.json 一致）
    """
    if max_skills is None:
        max_skills = _MAX_SKILLS

    if not _INDEX_PATH.exists():
        print(f"[Info] 倒排索引文件不存在: {_INDEX_PATH}，自动构建...")
        from shared.skills_topic_to_index import build_index
        build_index(_skills_json_path)

    with open(_INDEX_PATH, encoding="utf-8") as f:
        index = json.loads(f.read())

    candidates = index.get(topic, [])
    if not candidates:
        return []

    # 过滤掉需要账号依赖的 skill
    if filter_account_dependent_skills:
        candidates = [s for s in candidates if s.get("skill账号依赖", "") == ""]

    # 超过上限则随机抽样
    if len(candidates) > max_skills:
        candidates = random.sample(candidates, max_skills)

    # 校验 skill 目录是否存在
    valid = []
    for skill in candidates:
        skill_rel_dir = skill.get("skill目录", "").replace("\\", "/")
        skill_abs_dir = _SKILLS_DIR / skill_rel_dir
        if not skill_abs_dir.is_dir():
            print(f"[Warning] skill 目录不存在，已剔除: {skill_abs_dir}")
            continue
        # 统一路径分隔符为正斜杠，避免 Windows 反斜杠在其他平台引发路径错误
        normalized = {**skill, "skill目录": skill_rel_dir}
        valid.append(normalized)

    return valid


def main():
    if len(sys.argv) < 2:
        print("用法: python shared/topic_search_skills.py <topic>")
        print("示例: python shared/topic_search_skills.py 购物")
        return 1

    topic = sys.argv[1]
    print(f"检索 topic: {topic}")
    print(f"索引文件: {_INDEX_PATH}")
    print(f"skills 目录: {_SKILLS_DIR}")
    print(f"最大返回数: {_MAX_SKILLS}")
    print()

    results = search_skills_by_topic(topic)

    if not results:
        print(f"未找到与 \"{topic}\" 相关的 skills")
        return 0

    print(f"找到 {len(results)} 个 skills:\n")
    for i, skill in enumerate(results, 1):
        print(f"  {i}. {skill.get('skill名称', '?')}")
        print(f"     目录: {skill.get('skill目录', '?')}")
        print(f"     简介: {skill.get('skill简介', '?')[:80]}...")
        print()

    return 0


if __name__ == "__main__":
    exit(main())
