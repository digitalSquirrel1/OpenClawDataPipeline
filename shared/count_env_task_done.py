# -*- coding: utf-8 -*-
# 输入env目录，统计有多少已经生成了环境（有task_done.txt）。
import argparse
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Count subdirectories and how many contain task_done.txt."
    )
    parser.add_argument("target_dir", type=str, help="Directory to inspect")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target_dir = Path(args.target_dir).resolve()

    if not target_dir.exists():
        print(f"[error] directory not found: {target_dir}")
        return 1
    if not target_dir.is_dir():
        print(f"[error] not a directory: {target_dir}")
        return 1

    subdirs = sorted(path for path in target_dir.iterdir() if path.is_dir())
    done_count = sum(1 for subdir in subdirs if (subdir / "task_done.txt").exists())

    print(f"target_dir: {target_dir}")
    print(f"subdir_count: {len(subdirs)}")
    print(f"task_done_count: {done_count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
