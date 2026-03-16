# -*- coding: utf-8 -*-
"""
批量环境生成器
===============
遍历 Outputs/profiles 目录中的用户画像 JSON 文件，批量调用 WorkingSpace/main.py 生成环境。

使用方式：
  python batch_generate.py
  python batch_generate.py --profiles-dir Outputs/profiles
"""

import os, sys, json, argparse, subprocess
from pathlib import Path
from datetime import datetime

# 支持中文字符显示
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ─── 项目路径设置 ───────────────────────────────────────────────────────────────
_CONTROL_CENTER = Path(__file__).parent
_PROJECT_ROOT = _CONTROL_CENTER.parent
_WORKING_SPACE = _PROJECT_ROOT / "WorkingSpace"
_MAIN_SCRIPT = _WORKING_SPACE / "main.py"

# 默认路径配置
# profiles 和 environments 都放在项目根目录的 Outputs 下
DEFAULT_PROFILES_DIR = _PROJECT_ROOT / "Outputs" / "profiles"
DEFAULT_ENVS_DIR = _PROJECT_ROOT / "Outputs" / "environments"


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="批量根据用户画像生成环境"
    )
    parser.add_argument(
        "--profiles-dir",
        type=str,
        default=str(DEFAULT_PROFILES_DIR),
        help=f"用户画像目录（默认: {DEFAULT_PROFILES_DIR}）"
    )
    parser.add_argument(
        "--envs-dir",
        type=str,
        default=str(DEFAULT_ENVS_DIR),
        help=f"环境输出目录（默认: {DEFAULT_ENVS_DIR}）"
    )
    parser.add_argument(
        "--pattern",
        type=str,
        default="*.json",
        help="匹配文件名模式（默认: *.json）"
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="跳过已生成的环境"
    )
    return parser.parse_args()


def get_profile_info(profile_path: Path) -> dict:
    """从用户画像文件中提取基本信息，用于生成输出目录名"""
    try:
        with open(profile_path, "r", encoding="utf-8") as f:
            profile = json.load(f)

        basic = profile.get("基本信息", {})
        name = basic.get("姓名", "unknown")
        role = basic.get("职业", "unknown")

        # 清理角色名称（移除特殊字符）
        role_clean = (
            role.replace(" ", "_")
                .replace("/", "_")
                .replace("\\", "_")
                .replace(":", "_")
                .replace("*", "_")
                .replace("?", "_")
                .replace('"', "_")
                .replace("<", "_")
                .replace(">", "_")
                .replace("|", "_")
        )

        return {"name": name, "role": role_clean, "profile": profile}
    except Exception as e:
        print(f"    [Error] 读取失败: {e}")
        return None


def generate_env_for_profile(
    profile_path: Path,
    output_dir: Path,
    main_script: Path,
    skip_existing: bool = False
) -> bool:
    """为单个用户画像生成环境"""
    # 提取画像信息
    info = get_profile_info(profile_path)
    if not info:
        return False

    # 生成输出子目录名
    env_name = f"{info['name']}_{info['role']}"
    env_path = output_dir / env_name

    # 检查是否已存在
    if skip_existing and env_path.exists():
        print(f"  [SKIP] {env_name} (已存在)")
        return True

    print(f"  [处理] {env_name}")
    print(f"    输出: {env_path}")

    # 构建 main.py 的调用命令
    # --user-profile 参数：如果相对于 WorkingSpace 则用相对路径，否则用绝对路径
    # --output 参数：相对于 WorkingSpace 的路径，例如 "../Outputs/environments/用户名_职业"
    output_full_path = output_dir / env_name

    # 转换为相对于 WorkingSpace 目录的路径
    try:
        profile_arg = profile_path.relative_to(_WORKING_SPACE)
    except ValueError:
        profile_arg = profile_path

    try:
        output_arg = output_full_path.relative_to(_WORKING_SPACE)
    except ValueError:
        output_arg = output_full_path

    cmd = [
        sys.executable,
        str(main_script),
        "--user-profile", str(profile_arg),
        "--output", str(output_arg)
    ]

    # 执行命令
    try:
        result = subprocess.run(
            cmd,
            cwd=str(_WORKING_SPACE),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )

        if result.returncode == 0:
            print(f"  [OK] {env_name} 生成成功")
            # 生成文件映射表
            generate_file_mappings(env_path, info['profile'])
            return True
        else:
            print(f"  [FAIL] {env_name} 生成失败")
            print(f"    stderr: {result.stderr[-500:]}")
            return False
    except Exception as e:
        print(f"  [Error] 执行失败: {e}")
        return False


def generate_file_mappings(env_path: Path, profile: dict):
    """
    根据生成的环境目录结构，创建 Windows 和 Linux 的文件映射表。

    映射规则：
    - Windows: 保持原始路径，C/ → C:\, D/ → D:\
    - Linux: C/ → ~/, D/ → ~/workspace/
    """
    computer_profile_dir = env_path / "computer_profile"

    if not computer_profile_dir.exists():
        print(f"    [Skip] 未找到 computer_profile 目录，跳过映射表生成")
        return

    # 收集所有文件路径
    file_paths = []
    for file_path in computer_profile_dir.rglob("*"):
        if file_path.is_file():
            # 获取相对于 computer_profile 的路径
            rel_path = file_path.relative_to(computer_profile_dir)
            file_paths.append(str(rel_path).replace("\\", "/"))

    # 生成 Windows 映射
    windows_mapping = {}
    for path in file_paths:
        # 将 C/ 开头的路径转换为 Windows 格式 C:\
        # 将 D/ 开头的路径转换为 Windows 格式 D:\
        win_src = path
        if path.startswith("C/"):
            win_src = "C:\\" + path[2:].replace("/", "\\")
        elif path.startswith("D/"):
            win_src = "D:\\" + path[2:].replace("/", "\\")
        else:
            # 其他路径直接转 Windows 格式
            win_src = path.replace("/", "\\")

        windows_mapping[path] = win_src

    # 生成 Linux 映射
    linux_mapping = {}
    for path in file_paths:
        # C/ → ~/， D/ → ~/workspace/
        linux_src = path
        if path.startswith("C/"):
            linux_src = "~/" + path[2:]
        elif path.startswith("D/"):
            linux_src = "~/workspace/" + path[2:]
        else:
            # 其他路径保持不变
            linux_src = path

        linux_mapping[path] = linux_src


    # 保存 Windows 映射
    windows_map_path = env_path / "MAP_Windows.json"
    with open(windows_map_path, "w", encoding="utf-8") as f:
        json.dump(windows_mapping, f, ensure_ascii=False, indent=2)
    print(f"    → MAP_Windows.json 已生成")

    # 保存 Linux 映射
    linux_map_path = env_path / "MAP_Linux.json"
    with open(linux_map_path, "w", encoding="utf-8") as f:
        json.dump(linux_mapping, f, ensure_ascii=False, indent=2)
    print(f"    → MAP_Linux.json 已生成")


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("  批量环境生成器")
    print("=" * 60)

    # 解析参数
    args = parse_args()
    profiles_dir = Path(args.profiles_dir)
    envs_dir = Path(args.envs_dir)

    # 检查路径
    if not profiles_dir.exists():
        print(f"\n[Error] 用户画像目录不存在: {profiles_dir}")
        return 1

    if not _MAIN_SCRIPT.exists():
        print(f"\n[Error] main.py 不存在: {_MAIN_SCRIPT}")
        return 1

    # 创建输出目录
    envs_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n  用户画像目录: {profiles_dir}")
    print(f"  环境输出目录: {envs_dir}")
    print(f"  匹配模式: {args.pattern}")

    # 查找所有用户画像文件
    profile_files = sorted(profiles_dir.glob(args.pattern))

    if not profile_files:
        print(f"\n[Info] 未找到匹配的用户画像文件")
        return 0

    print(f"\n  找到 {len(profile_files)} 个用户画像文件")

    # 批量处理
    print("\n[开始生成]")
    results = {"success": 0, "fail": 0, "skip": 0}

    for profile_file in profile_files:
        success = generate_env_for_profile(
            profile_file,
            envs_dir,
            _MAIN_SCRIPT,
            skip_existing=args.skip_existing
        )

        if success:
            results["success"] += 1
        else:
            results["fail"] += 1

        print()

    # 汇总
    print("=" * 60)
    print("  生成完成")
    print("=" * 60)
    print(f"\n  总计: {len(profile_files)}")
    print(f"  成功: {results['success']}")
    print(f"  失败: {results['fail']}")
    print(f"  跳过: {results['skip']}")
    print()

    return 0 if results["fail"] == 0 else 1


if __name__ == "__main__":
    exit(main())