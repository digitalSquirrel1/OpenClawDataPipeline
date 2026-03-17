# -*- coding: utf-8 -*-
"""
standard_format.py — 将 queries_with_skills 目录下的 JSON 文件标准化打包
==========================================================================
流程：
  对每个原 JSON 文件中的每组 results（topic + queries + skills），生成一个独立的打包文件夹，

  **无 env_rel_path 时**（纯 skills 模式）：
    输出到 output_dir 下：
      {profile_rel_path_stem}_{topic}/
      ├── {原始profile文件名}.json
      └── user_queries.json

  **有 env_rel_path 时**（env + skills 模式）：
    输出到 envs_dir/{env_rel_path}/ 下：
      ├── {原始profile文件名}.json   # 覆盖已有
      └── user_queries.json          # list[dict]，包含所有 topic 的结果

使用方式：
  python ControlCenter/standard_format.py

  # 纯 skills 模式
  python ControlCenter/standard_format.py \
      --info-dir Outputs/queries_with_skills \
      --output-dir Outputs/standard_output

  # env + skills 模式（JSON 中含 env_rel_path）
  python ControlCenter/standard_format.py \
      --info-dir Outputs/queries_with_skills \
      --envs-dir Outputs/environments
"""

import os, sys, json, argparse, shutil, zipfile
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
    profiles_dir: Path,
    skills_dir: Path,
    output_dir: Path | None,
    envs_dir: Path | None,
) -> list[str]:
    """处理单个原 JSON 文件，返回生成的打包文件夹路径列表。"""

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    profile_rel_path = data["profile_rel_path"]
    results = data["results"]
    env_rel_path = data.get("env_rel_path")

    # profile_rel_path 的 stem（去掉 .json 后缀）
    profile_stem = Path(profile_rel_path).stem

    # ── env_rel_path 存在时的前置校验 ──
    if env_rel_path is not None:
        assert envs_dir is not None, (
            f"JSON 文件 {json_path.name} 包含 env_rel_path={env_rel_path}，"
            f"但未提供 --envs-dir 参数"
        )
        assert output_dir is None, (
            f"JSON 文件 {json_path.name} 包含 env_rel_path={env_rel_path}，"
            f"此时不应指定 --output-dir 参数"
        )

    created_folders = []

    # ── env + skills 模式：收集所有 topic 结果，一次性写入 ──
    if env_rel_path is not None:
        pack_dir = envs_dir / env_rel_path
        if not pack_dir.exists():
            raise FileNotFoundError(
                f"env 目录不存在: {pack_dir}\n"
                f"  env_rel_path={env_rel_path}, envs_dir={envs_dir}"
            )

        # 复制 profile
        src_profile = profiles_dir / profile_rel_path
        if not src_profile.exists():
            raise FileNotFoundError(
                f"profile 文件不存在: {src_profile}\n"
                f"  profile_rel_path={profile_rel_path}, profiles_dir={profiles_dir}"
            )
        shutil.copy2(src_profile, pack_dir / Path(profile_rel_path).name)

        # 遍历 results，收集为 list
        all_queries = []
        for result_item in results:
            topic = result_item["topic"]
            skills = result_item["skills"]
            queries = result_item["queries"]
            system_type = result_item.get("system_type")

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

            all_queries.append({
                "topic": topic,
                "system_type": system_type,
                "queries": queries,
                "skills": skill_rel_paths,
            })

        with open(pack_dir / "user_queries.json", "w", encoding="utf-8") as f:
            json.dump(all_queries, f, ensure_ascii=False, indent=2)

        # 删除该 env 目录下的 zip 文件（内容已变更，旧 zip 失效）
        for zip_file in pack_dir.glob("*.zip"):
            zip_file.unlink()
            print(f"    [删除旧 zip] {zip_file.name}")

        created_folders.append(str(pack_dir))

    else:
        # ── 纯 skills 模式：每个 topic 一个独立文件夹，各写一个 dict ──
        for result_item in results:
            topic = result_item["topic"]
            skills = result_item["skills"]
            queries = result_item["queries"]
            system_type = result_item.get("system_type")

            folder_name = _sanitize_folder_name(f"{profile_stem}_{topic}")
            pack_dir = output_dir / folder_name
            pack_dir.mkdir(parents=True, exist_ok=True)

            src_profile = profiles_dir / profile_rel_path
            if not src_profile.exists():
                raise FileNotFoundError(
                    f"profile 文件不存在: {src_profile}\n"
                    f"  profile_rel_path={profile_rel_path}, profiles_dir={profiles_dir}"
                )
            shutil.copy2(src_profile, pack_dir / Path(profile_rel_path).name)

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

            user_queries = [{
                "topic": topic,
                "system_type": system_type,
                "queries": queries,
                "skills": skill_rel_paths,
            }]
            with open(pack_dir / "user_queries.json", "w", encoding="utf-8") as f:
                json.dump(user_queries, f, ensure_ascii=False, indent=2)

            created_folders.append(str(pack_dir))

    return created_folders


def _long_path(p: Path) -> str:
    """Windows 长路径前缀，解决 >260 字符路径的 OSError。"""
    s = str(p)
    if sys.platform == "win32" and not s.startswith("\\\\?\\"):
        s = "\\\\?\\" + os.path.abspath(s)
    return s


def run(
    info_dir: Path,
    profiles_dir: Path,
    skills_dir: Path,
    output_dir: Path | None,
    envs_dir: Path | None,
):
    """遍历 info_dir 下所有 JSON 文件并标准化打包。"""

    if not info_dir.exists():
        raise FileNotFoundError(f"输入目录不存在: {info_dir}")

    json_files = sorted(info_dir.glob("*.json"))
    if not json_files:
        print(f"[Warning] 输入目录下没有 JSON 文件: {info_dir}")
        return

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)

    total_folders = 0
    for json_path in json_files:
        print(f"  处理: {json_path.name}")
        folders = process_single_json(json_path, profiles_dir, skills_dir, output_dir, envs_dir)
        total_folders += len(folders)
        for f in folders:
            print(f"    -> {Path(f).name}")

    print(f"\n完成: 共处理 {len(json_files)} 个文件, 生成 {total_folders} 个打包文件夹")

    # ── 最终打包为 zip ──
    if envs_dir is not None:
        # env + skills 模式：将 envs_dir 下所有包含 user_queries.json 的子目录打入 zip
        zip_path = envs_dir / "standard_output.zip"
        dirs_to_pack = sorted(
            p.parent for p in envs_dir.rglob("user_queries.json")
        )
        if dirs_to_pack:
            # 先收集所有待打包文件
            all_files = []
            for dir_path in dirs_to_pack:
                for file in sorted(dir_path.rglob("*")):
                    if file.is_file():
                        all_files.append((file, file.relative_to(envs_dir).as_posix()))
            total = len(all_files)
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for i, (file, arcname) in enumerate(all_files, 1):
                    with open(_long_path(file), "rb") as fh:
                        zf.writestr(arcname, fh.read())
                    if i % 50 == 0 or i == total:
                        print(f"\r  打包进度: {i}/{total} ({i*100//total}%)", end="", flush=True)
            print(f"\n已打包 zip: {zip_path}  ({len(dirs_to_pack)} 个环境目录, {total} 个文件)")
        else:
            print("[Warning] envs_dir 下未找到包含 user_queries.json 的目录，跳过打包")
    else:
        assert output_dir is not None, "envs_dir 和 output_dir 均为 None，无法打包"
        # 纯 skills 模式：将整个 output_dir 打包
        zip_path = output_dir.parent / f"{output_dir.name}.zip"
        all_files = [
            (f, f.relative_to(output_dir.parent).as_posix())
            for f in sorted(output_dir.rglob("*")) if f.is_file()
        ]
        total = len(all_files)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for i, (file, arcname) in enumerate(all_files, 1):
                with open(_long_path(file), "rb") as fh:
                    zf.writestr(arcname, fh.read())
                if i % 50 == 0 or i == total:
                    print(f"\r  打包进度: {i}/{total} ({i*100//total}%)", end="", flush=True)
        print(f"\n已打包 zip: {zip_path}  ({total} 个文件)")


def main():
    cfg = load_config()
    fmt_cfg = cfg.get("standard_format_config", {})

    # 从 query_gen 配置中获取 profiles_dir 和 skills_dir 的默认值
    gen_cfg = cfg.get("query_gen_with_topic_skill_profile_config", {})
    search_cfg = cfg.get("topic_search_skills_config", {})

    info_dir_default = _resolve(fmt_cfg.get("info_dir"), "Outputs/queries_with_skills")
    profiles_dir_default = _resolve(
        fmt_cfg.get("profiles_dir") or gen_cfg.get("profile_dir"),
        "Outputs/profiles",
    )
    skills_dir_default = _resolve(
        fmt_cfg.get("skills_dir") or search_cfg.get("skills_dir"),
        "Outputs/skill_localize/skills_library",
    )

    # 从 yaml 读取 output_dir / envs_dir 默认值（二者互斥，envs_dir 优先）
    _yaml_envs_dir = fmt_cfg.get("envs_dir")
    _yaml_output_dir = fmt_cfg.get("output_dir")

    envs_dir_default: str | None = None
    output_dir_default: str | None = None
    if _yaml_envs_dir:
        envs_dir_default = str(_resolve(_yaml_envs_dir, "Outputs/environments"))
    elif _yaml_output_dir:
        output_dir_default = str(_resolve(_yaml_output_dir, "Outputs/standard_output"))
    else:
        # yaml 两个都没配，给 output_dir 一个兜底默认
        output_dir_default = str(_resolve(None, "Outputs/standard_output"))

    parser = argparse.ArgumentParser(description="标准化打包 queries_with_skills")
    parser.add_argument("--info-dir", default=str(info_dir_default),
                        help=f"输入目录（默认: {info_dir_default}）")
    parser.add_argument("--output-dir", default=output_dir_default,
                        help=f"输出目录（纯 skills 模式，默认: {output_dir_default}）")
    parser.add_argument("--envs-dir", default=envs_dir_default,
                        help=f"环境目录（env+skills 模式，默认: {envs_dir_default}）")
    parser.add_argument("--profiles-dir", default=str(profiles_dir_default),
                        help=f"用户画像目录（默认: {profiles_dir_default}）")
    parser.add_argument("--skills-dir", default=str(skills_dir_default),
                        help=f"skills 目录（默认: {skills_dir_default}）")
    args = parser.parse_args()

    info_dir = Path(args.info_dir)
    output_dir = Path(args.output_dir) if args.output_dir else None
    envs_dir = Path(args.envs_dir) if args.envs_dir else None
    profiles_dir = Path(args.profiles_dir)
    skills_dir = Path(args.skills_dir)

    assert output_dir is not None or envs_dir is not None, (
        "必须至少指定 --output-dir 或 --envs-dir 之一（或在 yaml standard_format_config 中配置）"
    )

    print("=" * 60)
    print("  标准格式化打包")
    print("=" * 60)
    print(f"  输入目录:   {info_dir}")
    if output_dir is not None:
        print(f"  输出目录:   {output_dir}")
    if envs_dir is not None:
        print(f"  环境目录:   {envs_dir}")
    print(f"  画像目录:   {profiles_dir}")
    print(f"  Skills目录: {skills_dir}")
    print()

    run(info_dir, profiles_dir, skills_dir, output_dir, envs_dir)


if __name__ == "__main__":
    main()
