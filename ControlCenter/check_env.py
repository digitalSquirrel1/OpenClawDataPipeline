# -*- coding: utf-8 -*-
"""
环境一致性检查器 & README 修复器
==================================
校验单个 environment 目录中，实际文件系统与 README.md 文件清单是否一致；
并可以磁盘文件为准，自动修复 README.md 中的错误。

用法：
  python check_env.py <env_profile_dir>           # 仅检查
  python check_env.py <env_profile_dir> --fix     # 检查并修复 README.md

  env_profile_dir 是内层目录，即包含 README.md 和 C/ D/ E/ 等驱动器目录的那层。
  例如：
    python check_env.py "Outputs/environments/陈语汐_全职网约车司机/陈语汐_全职网约车司机"
    python check_env.py "Outputs/environments/陈语汐_全职网约车司机/陈语汐_全职网约车司机" --fix
"""

import sys
import re
from pathlib import Path

# ─── 单字母驱动器目录（C/ D/ E/ Z/ 等）──────────────────────────────────────
DRIVE_LETTERS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ")


def collect_disk_files(profile_dir: Path) -> set:
    """
    扫描 profile_dir 下所有单字母驱动器目录中的文件，
    返回相对路径集合（使用 / 分隔，如 D/foo/bar.pdf）。
    """
    files = set()
    for entry in profile_dir.iterdir():
        if entry.is_dir() and len(entry.name) == 1 and entry.name.upper() in DRIVE_LETTERS:
            for f in entry.rglob("*"):
                if f.is_file():
                    rel = f.relative_to(profile_dir)
                    files.add(str(rel).replace("\\", "/"))
    return files


def collect_readme_files(profile_dir: Path) -> set:
    """
    解析 README.md 中 ## 文件清单 部分，提取反引号内有扩展名的路径。
    """
    readme = profile_dir / "README.md"
    if not readme.exists():
        return set()

    content = readme.read_text(encoding="utf-8")
    section_match = re.search(r"^## 文件清单\s*\n(.*?)(?=^##|\Z)", content, re.MULTILINE | re.DOTALL)
    if not section_match:
        return set()

    paths = set(re.findall(r"`([^`]+)`", section_match.group(1)))
    return {p for p in paths if "." in Path(p).name}


def check_env(profile_dir: Path):
    """校验单个 environment profile 目录，返回 (disk_files, readme_files)。"""
    print(f"\n{'='*60}")
    print(f"  检查目录：{profile_dir.name}")
    print(f"{'='*60}")

    disk_files = collect_disk_files(profile_dir)
    readme_files = collect_readme_files(profile_dir)

    only_on_disk = disk_files - readme_files
    only_in_readme = readme_files - disk_files

    # stem 相同但扩展名不同
    disk_stems = {Path(f).stem: f for f in disk_files}
    readme_stems = {Path(f).stem: f for f in readme_files}
    type_mismatches = [
        (disk_stems[s], readme_stems[s])
        for s in disk_stems
        if s in readme_stems and Path(disk_stems[s]).suffix != Path(readme_stems[s]).suffix
    ]

    ok = True

    if only_on_disk:
        ok = False
        print(f"\n  [磁盘多余，README 未列出] ({len(only_on_disk)} 个):")
        for f in sorted(only_on_disk):
            print(f"    + {f}")

    if only_in_readme:
        ok = False
        print(f"\n  [README 列出，磁盘不存在] ({len(only_in_readme)} 个):")
        for f in sorted(only_in_readme):
            print(f"    - {f}")

    if type_mismatches:
        ok = False
        print(f"\n  [类型不一致，stem 相同但扩展名不同] ({len(type_mismatches)} 个):")
        for disk_p, readme_p in sorted(type_mismatches):
            print(f"    磁盘: {disk_p}")
            print(f"    README: {readme_p}")

    if ok:
        print(f"\n  [OK] 文件系统与 README 完全一致（共 {len(disk_files)} 个文件）")
    else:
        print(f"\n  磁盘文件数：{len(disk_files)}，README 列出文件数：{len(readme_files)}")

    return disk_files, readme_files


def fix_readme(profile_dir: Path, disk_files: set):
    """
    以磁盘文件为准，修复 README.md：
    1. ## 文件清单：
       - 若文件不存在但有同 stem 不同后缀的磁盘文件，直接替换路径后缀
       - 若完全不存在，删除该条目行
    2. ## 目录结构：删除磁盘上不存在的目录路径行
    修复前备份原文件为 README.md.bak。
    """
    readme = profile_dir / "README.md"
    if not readme.exists():
        print("[错误] README.md 不存在，跳过修复")
        return

    content = readme.read_text(encoding="utf-8")

    # 备份
    bak = readme.with_suffix(".md.bak")
    bak.write_text(content, encoding="utf-8")
    print(f"\n  [备份] 原文件已备份至 {bak.name}")

    # 构建 stem → 磁盘路径 的映射，用于后缀修正
    disk_stem_map = {Path(f).stem: f for f in disk_files}

    # ─── 1. 修复 ## 文件清单 ──────────────────────────────────────────────────
    removed_files = []
    fixed_files = []

    def filter_file_section(match):
        section_text = match.group(0)
        lines = section_text.splitlines(keepends=True)
        kept = []
        for line in lines:
            path_match = re.search(r"`([^`]+)`", line)
            if path_match:
                path = path_match.group(1)
                if "." in Path(path).name and path not in disk_files:
                    stem = Path(path).stem
                    if stem in disk_stem_map:
                        # 同 stem 存在于磁盘，替换为磁盘实际路径
                        correct_path = disk_stem_map[stem]
                        fixed_files.append((path, correct_path))
                        line = line.replace(f"`{path}`", f"`{correct_path}`")
                    else:
                        removed_files.append(path)
                        continue  # 删除此行
            kept.append(line)
        return "".join(kept)

    content = re.sub(
        r"^## 文件清单\s*\n.*?(?=^##|\Z)",
        filter_file_section,
        content,
        flags=re.MULTILINE | re.DOTALL,
    )

    # ─── 2. 修复 ## 目录结构 代码块 ──────────────────────────────────────────
    # 收集磁盘上实际存在的所有目录（相对路径）
    disk_dirs = set()
    for f in disk_files:
        p = Path(f)
        # 收集从驱动器到父目录的所有层级
        for i in range(1, len(p.parts)):
            disk_dirs.add("/".join(p.parts[:i]))

    removed_dirs = []

    def filter_dir_codeblock(match):
        block = match.group(0)
        lines = block.splitlines(keepends=True)
        kept = []
        for line in lines:
            stripped = line.strip()
            # 只检查看起来像路径的行（以单字母/开头）
            if (
                len(stripped) >= 2
                and stripped[0].upper() in DRIVE_LETTERS
                and stripped[1] == "/"
            ):
                if stripped not in disk_dirs:
                    removed_dirs.append(stripped)
                    continue  # 删除此行
            kept.append(line)
        return "".join(kept)

    content = re.sub(
        r"```\n.*?```",
        filter_dir_codeblock,
        content,
        flags=re.DOTALL,
    )

    # ─── 写回 ────────────────────────────────────────────────────────────────
    readme.write_text(content, encoding="utf-8")

    print(f"  [修复] ## 文件清单：删除了 {len(removed_files)} 条不存在的文件记录")
    for f in sorted(removed_files):
        print(f"    - {f}")

    if fixed_files:
        print(f"  [修复] ## 文件清单：修正了 {len(fixed_files)} 条后缀名不一致的记录")
        for old, new in sorted(fixed_files):
            print(f"    {old}  →  {new}")

    print(f"  [修复] ## 目录结构：删除了 {len(removed_dirs)} 条不存在的目录路径")
    for d in sorted(removed_dirs):
        print(f"    - {d}")

    print(f"\n  [完成] README.md 已更新")


def main():
    fix_mode = "--fix" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    if not args:
        envs_root = Path(__file__).parent.parent / "Outputs" / "environments"
        candidates = []
        for env_outer in sorted(envs_root.iterdir()):
            if env_outer.is_dir():
                inner = env_outer / env_outer.name
                if inner.exists():
                    candidates.append(inner)
        if not candidates:
            print("用法: python check_env.py <env_profile_dir> [--fix]")
            return 1
        profile_dir = candidates[0]
        print(f"[自动选择] {profile_dir}")
    else:
        profile_dir = Path(args[0])

    if not profile_dir.exists():
        print(f"[错误] 目录不存在：{profile_dir}")
        return 1

    disk_files, readme_files = check_env(profile_dir)

    if fix_mode:
        fix_readme(profile_dir, disk_files)
    else:
        if disk_files != readme_files:
            print("\n  提示：运行 --fix 可自动修复 README.md")

    return 0


if __name__ == "__main__":
    sys.exit(main())
