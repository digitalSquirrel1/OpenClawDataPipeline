"""
将 environments 目录下的子文件夹按 MAP_linux / MAP_windows 分类，
搬运到 OUTPUT_PATH/linux 或 OUTPUT_PATH/windows 下。
不满足条件的保留原地。
"""

import os
import shutil
import concurrent.futures
from pathlib import Path
from tqdm import tqdm

# ── 并发参数 ──────────────────────────────────────────────
MAX_WORKERS = 8  # 32G Windows 安全值


def classify_subfolder(subfolder: Path) -> str | None:
    """返回 'linux' / 'windows' / None（保留原地）。"""
    children = {c.name for c in subfolder.iterdir()} if subfolder.is_dir() else set()
    has_user_queries = "user_queries.json" in children
    has_map_linux = "MAP_Linux.json" in children
    has_map_windows = "MAP_Windows.json" in children

    if has_map_linux and has_user_queries:
        return "linux"
    if has_map_windows and has_user_queries:
        return "windows"
    return None


def move_one(src: Path, dst: Path) -> str:
    """移动单个子文件夹，返回状态描述。"""
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return f"{src.name} -> {dst}"


def main():
    ENV_PATH = r"D:\PythonProject\OpenClawDataPipeline\user_simulator_agent\Outputs\260324\environments"
    OUTPUT_PATH = r"D:\PythonProject\OpenClawDataPipeline\user_simulator_agent\Outputs\260324\sorted_environments"

    env_path = Path(ENV_PATH)
    output_path = Path(OUTPUT_PATH)

    if not env_path.is_dir():
        raise FileNotFoundError(f"ENV_PATH 不存在: {env_path}")

    # ── 分类 ──────────────────────────────────────────────
    tasks: list[tuple[Path, Path]] = []  # (src, dst)
    counts = {"linux": 0, "windows": 0}
    skipped = 0

    for child in sorted(env_path.iterdir()):
        if not child.is_dir():
            continue
        os_type = classify_subfolder(child)
        if os_type is None:
            skipped += 1
            continue
        counts[os_type] += 1
        dst = output_path / os_type / "environments" / child.name
        tasks.append((child, dst))

    print(f"待搬运: {len(tasks)}  (linux: {counts['linux']}, windows: {counts['windows']})，保留原地: {skipped}")
    if not tasks:
        print("没有需要搬运的文件夹。")
        return

    # ── 并发搬运 ──────────────────────────────────────────
    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / "linux" / "environments").mkdir(parents=True, exist_ok=True)
    (output_path / "windows" / "environments").mkdir(parents=True, exist_ok=True)

    with tqdm(total=len(tasks), desc="搬运进度", unit="dir") as pbar:
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {pool.submit(move_one, src, dst): src.name for src, dst in tasks}
            for fut in concurrent.futures.as_completed(futures):
                try:
                    fut.result()
                except Exception as e:
                    print(f"\n[ERROR] {futures[fut]}: {e}")
                pbar.update(1)

    print("完成。")


if __name__ == "__main__":
    main()
