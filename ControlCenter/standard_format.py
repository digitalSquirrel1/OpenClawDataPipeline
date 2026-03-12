# -*- coding: utf-8 -*-
"""
standard_format.py — 将 queries_with_skills 目录下的 JSON 文件标准化打包
==========================================================================
流程：
  对每个原 JSON 文件中的每组 results（topic + queries + skills），生成一个独立的打包文件夹，
  文件夹结构：
    {profile_rel_path_stem}_{topic}/
    ├── {原始profile文件名}.json        # 从 profile_dir 复制，保留原名
    └── user_queries.json               # { "topic": ..., "queries": [...], "skills": [...] }

使用方式：
  python ControlCenter/standard_format.py

  # 指定输入输出目录
  python ControlCenter/standard_format.py \
      --info-dir Outputs/queries_with_skills \
      --output-dir Outputs/standard_output
"""

import os, sys, json, argparse, shutil
from pathlib import Path

# ─── 项目路径设置 ───────────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
from config.config_loader import load_config


def _resolve(rel_or_none: str | None, default_rel: str) -> Path:
    """将相对路径解析为绝对路径（相对于 _PROJECT_ROOT）。"""
    rel = rel_or_none or default_rel
    p = Path(rel)
    return p if p.is_absolute() else (_PROJECT_ROOT / p).resolve()


def _sanitize_folder_name(name: str) -> str:
    """清理文件夹名中的非法字符。"""
    for ch in r'<>:"/\|?*':
        name = name.replace(ch, "_")
    return name.strip()


def process_single_json(
    json_path: Path,
    output_dir: Path,
    profile_dir: Path,
    skills_dir: Path,
) -> list[str]:
    """处理单个原 JSON 文件，返回生成的打包文件夹路径列表。"""

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    profile_rel_path = data["profile_rel_path"]
    results = data["results"]

    # profile_rel_path 的 stem（去掉 .json 后缀）
    profile_stem = Path(profile_rel_path).stem

    created_folders = []

    for result_item in results:
        topic = result_item["topic"]
        skills = result_item["skills"]
        queries = result_item["queries"]

        # 1. 打包文件夹名称 = profile_stem + "_" + topic
        folder_name = _sanitize_folder_name(f"{profile_stem}_{topic}")
        pack_dir = output_dir / folder_name
        pack_dir.mkdir(parents=True, exist_ok=True)

        # 2. 复制 profile 到文件夹下，保留原文件名
        src_profile = profile_dir / profile_rel_path
        if not src_profile.exists():
            raise FileNotFoundError(
                f"profile 文件不存在: {src_profile}\n"
                f"  profile_rel_path={profile_rel_path}, profile_dir={profile_dir}"
            )
        shutil.copy2(src_profile, pack_dir / Path(profile_rel_path).name)

        # 3. 收集 skills 相对路径列表，并验证存在性
        skill_rel_paths = []
        for skill_info in skills:
            skill_rel = skill_info["skill目录"]
            src_skill = skills_dir / skill_rel
            if not src_skill.exists():
                raise FileNotFoundError(
                    f"skill 目录不存在: {src_skill}\n"
                    f"  skill目录={skill_rel}, skills_dir={skills_dir}"
                )
            skill_rel_paths.append(skill_rel.replace("\\", "/"))

        # 4. 写 user_queries.json（含 skills 相对路径）
        user_queries = {
            "topic": topic,
            "queries": queries,
            "skills": skill_rel_paths,
        }
        with open(pack_dir / "user_queries.json", "w", encoding="utf-8") as f:
            json.dump(user_queries, f, ensure_ascii=False, indent=2)

        created_folders.append(str(pack_dir))

    return created_folders


def run(info_dir: Path, output_dir: Path, profile_dir: Path, skills_dir: Path):
    """遍历 info_dir 下所有 JSON 文件并标准化打包。"""

    if not info_dir.exists():
        raise FileNotFoundError(f"输入目录不存在: {info_dir}")

    json_files = sorted(info_dir.glob("*.json"))
    if not json_files:
        print(f"[Warning] 输入目录下没有 JSON 文件: {info_dir}")
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    total_folders = 0
    for json_path in json_files:
        print(f"  处理: {json_path.name}")
        folders = process_single_json(json_path, output_dir, profile_dir, skills_dir)
        total_folders += len(folders)
        for f in folders:
            print(f"    -> {Path(f).name}")

    print(f"\n完成: 共处理 {len(json_files)} 个文件, 生成 {total_folders} 个打包文件夹")
    print(f"输出目录: {output_dir}")


def main():
    cfg = load_config()
    fmt_cfg = cfg.get("standard_format_config", {})

    # 从 query_gen 配置中获取 profile_dir 和 skills_dir 的默认值
    gen_cfg = cfg.get("query_gen_with_topic_skill_profile_config", {})
    search_cfg = cfg.get("topic_search_skills_config", {})

    info_dir_default = _resolve(fmt_cfg.get("info_dir"), "Outputs/queries_with_skills")
    output_dir_default = _resolve(fmt_cfg.get("output_dir"), "Outputs/standard_output")
    profile_dir_default = _resolve(
        fmt_cfg.get("profile_dir") or gen_cfg.get("profile_dir"),
        "Outputs/profiles",
    )
    skills_dir_default = _resolve(
        fmt_cfg.get("skills_dir") or search_cfg.get("skills_dir"),
        "Outputs/skill_localize/skills_library",
    )

    parser = argparse.ArgumentParser(description="标准化打包 queries_with_skills")
    parser.add_argument("--info-dir", default=str(info_dir_default),
                        help=f"输入目录（默认: {info_dir_default}）")
    parser.add_argument("--output-dir", default=str(output_dir_default),
                        help=f"输出目录（默认: {output_dir_default}）")
    parser.add_argument("--profile-dir", default=str(profile_dir_default),
                        help=f"用户画像目录（默认: {profile_dir_default}）")
    parser.add_argument("--skills-dir", default=str(skills_dir_default),
                        help=f"skills 目录（默认: {skills_dir_default}）")
    args = parser.parse_args()

    info_dir = Path(args.info_dir)
    output_dir = Path(args.output_dir)
    profile_dir = Path(args.profile_dir)
    skills_dir = Path(args.skills_dir)

    print("=" * 60)
    print("  标准格式化打包")
    print("=" * 60)
    print(f"  输入目录:   {info_dir}")
    print(f"  输出目录:   {output_dir}")
    print(f"  画像目录:   {profile_dir}")
    print(f"  Skills目录: {skills_dir}")
    print()

    run(info_dir, output_dir, profile_dir, skills_dir)


if __name__ == "__main__":
    main()
