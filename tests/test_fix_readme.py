# -*- coding: utf-8 -*-
"""
测试 check_env.fix_readme 能否在 Outputs/260312/environments 目录上正常运行。

用法：
  cd user_simulator_agent
  python -m tests.test_fix_readme
"""

import sys
from pathlib import Path

# ─── 路径设置 ────────────────────────────────────────────────────────────────
_TESTS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _TESTS_DIR.parent                    # user_simulator_agent/
_CONTROL_CENTER = _PROJECT_ROOT / "ControlCenter"

if str(_CONTROL_CENTER) not in sys.path:
    sys.path.insert(0, str(_CONTROL_CENTER))

from check_env import collect_disk_files, collect_readme_files, fix_readme

ENVS_DIR = _PROJECT_ROOT / "Outputs" / "260312" / "environments"


def test_single_env(profile_dir: Path):
    """对单个 environment 的 profile_dir 执行 check + fix_readme 测试。"""
    env_name = profile_dir.name
    print(f"\n{'─'*60}")
    print(f"  测试: {env_name}")
    print(f"  路径: {profile_dir}")
    print(f"{'─'*60}")

    # 1. 检查 README.md 是否存在
    readme = profile_dir / "README.md"
    if not readme.exists():
        print(f"  [SKIP] README.md 不存在，跳过")
        return "skip"

    # 2. 收集磁盘文件
    disk_files = collect_disk_files(profile_dir)
    print(f"  磁盘文件数: {len(disk_files)}")
    if not disk_files:
        print(f"  [SKIP] 磁盘无文件，跳过")
        return "skip"

    # 3. 收集 README 中的文件清单
    readme_files = collect_readme_files(profile_dir)
    print(f"  README 文件数: {len(readme_files)}")

    # 4. 显示差异
    only_on_disk = disk_files - readme_files
    only_in_readme = readme_files - disk_files
    if only_on_disk:
        print(f"  [差异] 磁盘多余 {len(only_on_disk)} 个:")
        for f in sorted(only_on_disk)[:5]:
            print(f"    + {f}")
        if len(only_on_disk) > 5:
            print(f"    ... 还有 {len(only_on_disk) - 5} 个")
    if only_in_readme:
        print(f"  [差异] README 多余 {len(only_in_readme)} 个:")
        for f in sorted(only_in_readme)[:5]:
            print(f"    - {f}")
        if len(only_in_readme) > 5:
            print(f"    ... 还有 {len(only_in_readme) - 5} 个")

    # 5. 执行 fix_readme
    print(f"\n  >>> 执行 fix_readme ...")
    fix_readme(profile_dir, disk_files)

    # 6. 修复后再次校验
    readme_files_after = collect_readme_files(profile_dir)
    only_in_readme_after = readme_files_after - disk_files
    if only_in_readme_after:
        print(f"  [WARN] 修复后 README 仍有 {len(only_in_readme_after)} 个磁盘不存在的文件:")
        for f in sorted(only_in_readme_after)[:5]:
            print(f"    - {f}")
        return "warn"
    else:
        print(f"  [OK] 修复后 README 文件清单与磁盘一致 ({len(readme_files_after)} 个文件)")
        return "ok"


def main():
    if not ENVS_DIR.exists():
        print(f"[错误] 环境目录不存在: {ENVS_DIR}")
        return 1

    # 遍历所有 environment
    env_dirs = sorted(ENVS_DIR.iterdir())
    if not env_dirs:
        print(f"[错误] 环境目录为空: {ENVS_DIR}")
        return 1

    stats = {"ok": 0, "warn": 0, "skip": 0, "fail": 0}

    for env_outer in env_dirs:
        if not env_outer.is_dir():
            continue
        # 内层同名目录即 profile_dir
        profile_dir = env_outer / env_outer.name
        if not profile_dir.exists():
            print(f"\n  [SKIP] 内层目录不存在: {profile_dir}")
            stats["skip"] += 1
            continue

        try:
            result = test_single_env(profile_dir)
            stats[result] += 1
        except Exception as e:
            import traceback
            print(f"  [FAIL] 异常: {e}")
            traceback.print_exc()
            stats["fail"] += 1

    # 汇总
    print(f"\n{'='*60}")
    print(f"  测试汇总")
    print(f"{'='*60}")
    print(f"  总计: {sum(stats.values())}")
    print(f"  OK:   {stats['ok']}")
    print(f"  WARN: {stats['warn']}")
    print(f"  SKIP: {stats['skip']}")
    print(f"  FAIL: {stats['fail']}")

    return 1 if stats["fail"] > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
