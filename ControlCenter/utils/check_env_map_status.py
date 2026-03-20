# -*- coding: utf-8 -*-
"""
统计 envs_dir 下各环境目录的 MAP 文件状态。

用法:
  python check_env_map_status.py --envs-dir Outputs/environments
"""

import argparse
from pathlib import Path


def check_env_map_status(envs_dir: Path, verbose: bool = False) -> int:
    if not envs_dir.exists() or not envs_dir.is_dir():
        print(f"[Error] envs_dir not found: {envs_dir}")
        return 1

    env_dirs = sorted([p for p in envs_dir.iterdir() if p.is_dir()])
    if not env_dirs:
        print(f"[Info] no environment directories in: {envs_dir}")
        return 0

    only_windows: list[str] = []
    only_linux: list[str] = []
    neither: list[str] = []
    both: list[str] = []

    for env_dir in env_dirs:
        has_windows = (env_dir / "MAP_Windows.json").exists()
        has_linux = (env_dir / "MAP_Linux.json").exists()

        if has_windows and has_linux:
            both.append(env_dir.name)
        elif has_windows:
            only_windows.append(env_dir.name)
        elif has_linux:
            only_linux.append(env_dir.name)
        else:
            neither.append(env_dir.name)

    print(f"[envs_dir] {envs_dir}")
    print(f"[total] {len(env_dirs)}")
    print(f"[only MAP_Windows.json] {len(only_windows)}")
    print(f"[only MAP_Linux.json] {len(only_linux)}")
    print(f"[neither exists] {len(neither)}")
    print(f"[both exist] {len(both)}")

    if verbose:
        def _print_names(title: str, names: list[str]) -> None:
            print(f"\n{title} ({len(names)}):")
            if not names:
                print("  - (none)")
                return
            for n in names:
                print(f"  - {n}")

        _print_names("Only MAP_Windows.json", only_windows)
        _print_names("Only MAP_Linux.json", only_linux)
        _print_names("Neither exists", neither)
        _print_names("Both exist", both)

    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check MAP file status under env directories.")
    parser.add_argument(
        "--envs-dir",
        required=True,
        type=str,
        help="环境根目录（其下每个子目录视为一个 environment）",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="输出每一类对应的目录名列表",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return check_env_map_status(Path(args.envs_dir), verbose=args.verbose)


if __name__ == "__main__":
    raise SystemExit(main())
