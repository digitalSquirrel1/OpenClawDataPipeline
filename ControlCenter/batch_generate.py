# -*- coding: utf-8 -*-
"""
批量环境生成器
===============
遍历 Outputs/profiles 目录中的用户画像 JSON 文件，
直接调用 WorkingSpace/main.py 的 run_pipeline() 生成环境。

使用方式：
  python batch_generate.py
  python batch_generate.py --profiles-dir Outputs/profiles
"""

import os, sys, json, argparse
from pathlib import Path

# 支持中文字符显示
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ─── 项目路径设置 ───────────────────────────────────────────────────────────────
_CONTROL_CENTER = Path(__file__).resolve().parent
_PROJECT_ROOT   = _CONTROL_CENTER.parent              # user_simulator_agent/
_WORKING_SPACE  = _PROJECT_ROOT / "WorkingSpace"

# 默认路径配置
DEFAULT_PROFILES_DIR = _PROJECT_ROOT / "Outputs" / "profiles"
DEFAULT_ENVS_DIR     = _PROJECT_ROOT / "Outputs" / "environments"

# ─── 加载配置 & 导入 pipeline ─────────────────────────────────────────────────
# 把 project root 和 WorkingSpace 都加到 sys.path
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
if str(_WORKING_SPACE) not in sys.path:
    sys.path.insert(0, str(_WORKING_SPACE))

from config.config_loader import load_config
from main import run_pipeline          # ← 直接 import，不再用 subprocess

_cfg = load_config()
_batch_cfg = _cfg.get("batch_generate_config", {})


# ─── 工具函数 ─────────────────────────────────────────────────────────────────
def _resolve(val: str | None, default: Path) -> str:
    """将 yaml 中的路径解析为绝对路径（相对路径以 _PROJECT_ROOT 为基准）。"""
    if not val:
        return str(default)
    p = Path(val)
    return str(p if p.is_absolute() else _PROJECT_ROOT / p)


def parse_args():
    """解析命令行参数（默认值从 config/baseline.yaml 读取）"""
    profiles_dir_default  = _resolve(_batch_cfg.get("profiles_dir"), DEFAULT_PROFILES_DIR)
    envs_dir_default      = _resolve(_batch_cfg.get("envs_dir"),     DEFAULT_ENVS_DIR)
    pattern_default       = _batch_cfg.get("pattern")      or "*.json"
    skip_existing_default = bool(_batch_cfg.get("skip_existing", False))

    parser = argparse.ArgumentParser(
        description="批量根据用户画像生成环境"
    )
    parser.add_argument(
        "--profiles-dir",
        type=str,
        default=profiles_dir_default,
        help=f"用户画像目录（默认: {profiles_dir_default}）"
    )
    parser.add_argument(
        "--envs-dir",
        type=str,
        default=envs_dir_default,
        help=f"环境输出目录（默认: {envs_dir_default}）"
    )
    parser.add_argument(
        "--pattern",
        type=str,
        default=pattern_default,
        help=f"匹配文件名模式（默认: {pattern_default}）"
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        default=skip_existing_default,
        help="跳过已生成的环境"
    )
    return parser.parse_args()


def _sanitize_name(name: str) -> str:
    """移除 Windows 目录名中不允许的字符。"""
    for ch in r'\/:*?"<>|':
        name = name.replace(ch, "_")
    return name.strip()


def get_profile_info(profile_path: Path) -> dict | None:
    """从用户画像 JSON 文件中提取基本信息。"""
    try:
        with open(profile_path, "r", encoding="utf-8") as f:
            profile = json.load(f)

        basic = profile.get("基本信息", {})
        name  = basic.get("姓名", "unknown")
        role  = basic.get("职业", "unknown")
        role_clean = _sanitize_name(role)

        return {"name": name, "role": role_clean, "profile": profile}
    except Exception as e:
        print(f"    [Error] 读取失败: {e}")
        return None


def generate_env_for_profile(
    profile_path: Path,
    envs_dir: Path,
    skip_existing: bool = False,
) -> bool:
    """为单个用户画像生成环境（直接调用 run_pipeline）。"""
    info = get_profile_info(profile_path)
    if not info:
        return False

    env_name = f"{info['name']}_{info['role']}"
    env_path = envs_dir / env_name

    # 检查是否已存在
    if skip_existing and env_path.exists():
        print(f"  [SKIP] {env_name} (已存在)")
        return True

    print(f"  [处理] {env_name}")
    print(f"    画像: {profile_path}")
    print(f"    输出: {env_path}")

    try:
        run_pipeline(
            user_profile_path=profile_path,
            output_dir=env_path,
            profile_dir_name=env_name,
        )
        print(f"  [OK] {env_name} 生成成功")
        return True
    except Exception as e:
        print(f"  [FAIL] {env_name} 生成失败: {e}")
        return False


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
            skip_existing=args.skip_existing,
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
