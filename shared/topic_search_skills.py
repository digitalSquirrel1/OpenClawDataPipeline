# -*- coding: utf-8 -*-
"""
Topic Search Skills
===================
Search skills by topic using an inverted index.
"""

import json
import random
import sys
from pathlib import Path

# Project root: user_simulator_agent/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config.config_loader import load_config

_cfg = load_config()
_search_cfg = _cfg.get("topic_search_skills_config", {})

_skills_json_rel = _search_cfg.get("skills_json_path", "Outputs/skills.json")
_skills_json_path = _PROJECT_ROOT / _skills_json_rel

# Index path: use config if provided, otherwise default beside skills.json
_map_path_cfg = _search_cfg.get("topic_to_skills_map")
if _map_path_cfg:
    _p = Path(_map_path_cfg)
    _INDEX_PATH = _p if _p.is_absolute() else (_PROJECT_ROOT / _p)
else:
    _INDEX_PATH = _skills_json_path.parent / "skills_index.json"

_skills_dir_rel = _search_cfg.get("skills_dir", "Outputs/skill_localize/skills_library")
_SKILLS_DIR = _PROJECT_ROOT / _skills_dir_rel
_MAX_SKILLS = int(_search_cfg.get("max_skills_per_topic", 5))

_INDEX_CACHE: dict | None = None


def _load_index_cached() -> dict:
    """Load skills index once and cache it in memory."""
    global _INDEX_CACHE
    if _INDEX_CACHE is not None:
        return _INDEX_CACHE

    if not _INDEX_PATH.exists():
        print(f"[Info] 倒排索引文件不存在: {_INDEX_PATH}，自动构建...")
        from shared.skills_topic_to_index import build_index
        build_index(_skills_json_path)

    try:
        with open(_INDEX_PATH, "r", encoding="utf-8") as f:
            _INDEX_CACHE = json.load(f)
    except json.JSONDecodeError as e:
        print(f"[Warning] 倒排索引 JSON 解析失败: {e}，自动重建: {_INDEX_PATH}")
        from shared.skills_topic_to_index import build_index
        build_index(_skills_json_path)
        with open(_INDEX_PATH, "r", encoding="utf-8") as f:
            _INDEX_CACHE = json.load(f)

    return _INDEX_CACHE


def search_skills_by_topic(
    topic: str,
    max_skills: int | None = None,
    filter_account_dependent_skills: bool = True,
) -> list[dict]:
    """
    Search skills for a topic.

    Args:
        topic: topic keyword.
        max_skills: max number of returned skills. If None, use config value.
        filter_account_dependent_skills: when True, remove skills whose
            "skill账号依赖" is non-empty.
    """
    if max_skills is None:
        max_skills = _MAX_SKILLS

    index = _load_index_cached()
    candidates = index.get(topic, [])
    if not candidates:
        return []

    if filter_account_dependent_skills:
        candidates = [s for s in candidates if s.get("skill账号依赖", "") == ""]

    if len(candidates) > max_skills:
        candidates = random.sample(candidates, max_skills)

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


def main() -> int:
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
    raise SystemExit(main())
