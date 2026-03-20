# -*- coding: utf-8 -*-
"""
批量转换 environment 的 MAP 文件（Windows <-> Linux）。

用法:
  python convert_env_maps.py --envs-dir Outputs/environments
  python convert_env_maps.py --envs-dir Outputs/environments --convert-to-linux false
"""

import argparse
import json
import sys
from pathlib import Path

# 路径设置（与 batch_generate.py 风格一致）
_CONTROL_CENTER = Path(__file__).resolve().parent.parent
_PROJECT_ROOT = _CONTROL_CENTER.parent  # user_simulator_agent/
DEFAULT_ENVS_DIR = _PROJECT_ROOT / "Outputs" / "environments"

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config.config_loader import load_config

_cfg = load_config()
# 按用户要求使用 convert_env_maps_confg；同时兼容 convert_env_maps_config
_convert_cfg = _cfg.get("convert_env_maps_confg", _cfg.get("convert_env_maps_config", {}))


def str2bool(value: str | bool) -> bool:
    """解析命令行布尔参数。"""
    if isinstance(value, bool):
        return value
    val = value.strip().lower()
    if val in {"1", "true", "t", "yes", "y"}:
        return True
    if val in {"0", "false", "f", "no", "n"}:
        return False
    raise argparse.ArgumentTypeError(f"Invalid boolean value: {value}")


def _resolve(val: str | None, default: Path) -> str:
    """将 yaml 中路径解析为绝对路径（相对路径以 _PROJECT_ROOT 为基准）。"""
    if not val:
        return str(default)
    p = Path(val)
    return str(p if p.is_absolute() else _PROJECT_ROOT / p)


def _resolve_profile_dir(env_dir: Path) -> Path:
    """
    解析实际文件系统根目录。
    batch_generate.py 的标准结构是: env_dir / env_dir.name / C|D|E...
    """
    standard = env_dir / env_dir.name
    return standard if standard.exists() else env_dir


def _collect_file_paths(profile_dir: Path) -> list[str]:
    """
    收集相对路径（相对 profile_dir），仅保留 X/...（X 为单字母盘符）开头的文件。
    """
    file_paths: list[str] = []
    for file_path in profile_dir.rglob("*"):
        if not file_path.is_file():
            continue
        rel_path = file_path.relative_to(profile_dir)
        parts = rel_path.parts
        if len(parts) >= 2 and len(parts[0]) == 1 and parts[0].isalpha():
            file_paths.append(str(rel_path).replace("\\", "/"))
    file_paths.sort()
    return file_paths


def _build_windows_mapping(file_paths: list[str]) -> dict[str, str]:
    """生成 Windows 映射: X/... -> X:\\..."""
    mapping: dict[str, str] = {}
    for path in file_paths:
        parts = path.split("/", 1)
        drive = parts[0]
        rest = parts[1] if len(parts) > 1 else ""
        if len(drive) == 1 and drive.isalpha():
            src = drive + ":\\" + rest.replace("/", "\\")
        else:
            src = path.replace("/", "\\")
        mapping[path] = src
    return mapping


def _build_linux_mapping(file_paths: list[str]) -> dict[str, str]:
    """生成 Linux 映射: C/... -> ~/..., X/... -> ~/X/..."""
    mapping: dict[str, str] = {}
    for path in file_paths:
        parts = path.split("/", 1)
        drive = parts[0]
        rest = parts[1] if len(parts) > 1 else ""
        if drive == "C":
            src = "~/" + rest
        elif len(drive) == 1 and drive.isalpha():
            src = f"~/{drive}/" + rest
        else:
            src = path
        mapping[path] = src
    return mapping


def _convert_single_env(env_dir: Path, convert_to_linux: bool) -> tuple[bool, str]:
    """转换单个环境目录，返回 (是否成功处理, 说明)。"""
    profile_dir = _resolve_profile_dir(env_dir)
    if not profile_dir.exists():
        return False, f"{env_dir.name}: skip (profile dir not found)"

    file_paths = _collect_file_paths(profile_dir)
    if not file_paths:
        return False, f"{env_dir.name}: skip (no disk files under drive folders)"

    windows_map_path = env_dir / "MAP_Windows.json"
    linux_map_path = env_dir / "MAP_Linux.json"

    if convert_to_linux:
        target_path = linux_map_path
        delete_path = windows_map_path
        mapping = _build_linux_mapping(file_paths)
        target_name = "MAP_Linux.json"
        delete_name = "MAP_Windows.json"
    else:
        target_path = windows_map_path
        delete_path = linux_map_path
        mapping = _build_windows_mapping(file_paths)
        target_name = "MAP_Windows.json"
        delete_name = "MAP_Linux.json"

    target_path.write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if delete_path.exists():
        delete_path.unlink()
        return True, f"{env_dir.name}: wrote {target_name} ({len(mapping)}), deleted {delete_name}"
    return True, f"{env_dir.name}: wrote {target_name} ({len(mapping)})"


def convert_env_maps(envs_dir: Path, convert_to_linux: bool = True) -> int:
    """批量转换 envs_dir 下所有环境目录的 map。"""
    if not envs_dir.exists() or not envs_dir.is_dir():
        print(f"[Error] envs_dir not found: {envs_dir}")
        return 1

    env_dirs = sorted([p for p in envs_dir.iterdir() if p.is_dir()])
    if not env_dirs:
        print(f"[Info] no environment directories in: {envs_dir}")
        return 0

    print(f"[Start] envs_dir={envs_dir}")
    print(f"[Mode] convert_to_linux={convert_to_linux}")

    ok_count = 0
    skip_count = 0
    for env_dir in env_dirs:
        ok, msg = _convert_single_env(env_dir, convert_to_linux)
        print(f"  - {msg}")
        if ok:
            ok_count += 1
        else:
            skip_count += 1

    print(f"[Done] processed={len(env_dirs)}, converted={ok_count}, skipped={skip_count}")
    return 0


def parse_args() -> argparse.Namespace:
    """
    参数优先级：
    1) baseline_using.yaml 的 convert_env_maps_confg（若存在该字段）
    2) shell 传参
    3) 内置默认值
    """
    parser = argparse.ArgumentParser(description="Convert MAP_Windows.json and MAP_Linux.json in environments.")
    parser.add_argument(
        "--envs-dir",
        type=str,
        default=str(DEFAULT_ENVS_DIR),
        help="环境目录（其下每个子目录视为一个 environment）",
    )
    parser.add_argument(
        "--convert-to-linux",
        default=True,
        type=str2bool,
        help="True: 生成 MAP_Linux.json 并删除 MAP_Windows.json；False 反向转换（默认 True）",
    )
    args = parser.parse_args()

    cfg_envs_dir = _convert_cfg.get("envs_dir", None)
    cfg_convert_to_linux = _convert_cfg.get("convert_to_linux", None)

    # yaml 优先：只要 yaml 有值，就覆盖 shell 传参
    if cfg_envs_dir:
        args.envs_dir = _resolve(str(cfg_envs_dir), DEFAULT_ENVS_DIR)
    else:
        args.envs_dir = _resolve(args.envs_dir, DEFAULT_ENVS_DIR)

    if cfg_convert_to_linux is not None:
        args.convert_to_linux = str2bool(cfg_convert_to_linux)

    return args


def main() -> int:
    args = parse_args()
    return convert_env_maps(Path(args.envs_dir), bool(args.convert_to_linux))


if __name__ == "__main__":
    raise SystemExit(main())
