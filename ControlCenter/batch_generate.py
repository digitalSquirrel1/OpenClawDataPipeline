# -*- coding: utf-8 -*-
"""
批量环境生成器
===============
遍历 Outputs/profiles 目录中的用户画像 JSON 文件，
批量调用 WorkingSpace/main.py 生成环境。

使用方式：
  python batch_generate.py
  python batch_generate.py --profiles-dir Outputs/profiles
"""

import os, sys, json, argparse, threading, traceback
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess
import contextvars

# 每个并发 task 的日志前缀，主线程为空
_task_tag: contextvars.ContextVar[str] = contextvars.ContextVar("_task_tag", default="")

# 支持中文字符显示
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# ─── Tee：同时输出到 terminal 和 log 文件 ────────────────────────────────────
class _TeeWriter:
    """将 write/flush 同时转发到多个流。"""

    def __init__(self, *streams):
        self._streams = streams
        self.encoding = getattr(streams[0], "encoding", "utf-8")

    def write(self, data):
        if not data:
            return 0
        tag = _task_tag.get("")
        if tag:
            lines = data.split("\n")
            tagged_parts = []
            for i, line in enumerate(lines):
                if i == len(lines) - 1 and line == "":
                    tagged_parts.append("")
                else:
                    tagged_parts.append(f"{tag} {line}" if line else "")
            data = "\n".join(tagged_parts)
        for s in self._streams:
            try:
                s.write(data)
                s.flush()
            except Exception:
                pass
        return len(data) if isinstance(data, str) else 0

    def flush(self):
        for s in self._streams:
            try:
                s.flush()
            except Exception:
                pass

    def __getattr__(self, name):
        return getattr(self._streams[0], name)


def _setup_tee_logging(log_dir: Path) -> Path:
    """创建日志文件并将 stdout/stderr 同时 tee 到该文件。"""
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%H%M%S")
    log_path = log_dir / f"{timestamp}.log"
    log_file = open(log_path, "w", encoding="utf-8")

    sys.stdout = _TeeWriter(sys.__stdout__, log_file)
    sys.stderr = _TeeWriter(sys.__stderr__, log_file)
    return log_path


# ─── 项目路径设置 ───────────────────────────────────────────────────────────────
_CONTROL_CENTER = Path(__file__).resolve().parent
_PROJECT_ROOT   = _CONTROL_CENTER.parent
_WORKING_SPACE  = _PROJECT_ROOT / "WorkingSpace"
_MAIN_SCRIPT    = _WORKING_SPACE / "main.py"

# 默认路径配置
DEFAULT_PROFILES_DIR = _PROJECT_ROOT / "Outputs" / "profiles"
DEFAULT_ENVS_DIR     = _PROJECT_ROOT / "Outputs" / "environments"
DEFAULT_LOG_DIR      = _PROJECT_ROOT / "Log"

# ─── 加载配置 ─────────────────────────────────────────────────────────────────
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
if str(_WORKING_SPACE) not in sys.path:
    sys.path.insert(0, str(_WORKING_SPACE))

from config.config_loader import load_config

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
    profiles_dir_default    = _resolve(_batch_cfg.get("profiles_dir"), DEFAULT_PROFILES_DIR)
    envs_dir_default        = _resolve(_batch_cfg.get("envs_dir"),     DEFAULT_ENVS_DIR)
    pattern_default         = _batch_cfg.get("pattern")      or "*.json"
    skip_existing_default   = bool(_batch_cfg.get("skip_existing", False))
    max_concurrency_default = int(_batch_cfg.get("max_concurrency", 3))

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
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=max_concurrency_default,
        help=f"最大并发数（默认: {max_concurrency_default}）"
    )
    return parser.parse_args()


def get_profile_info(profile_path: Path) -> dict | None:
    """从用户画像文件中提取基本信息，用于生成输出目录名"""
    try:
        with open(profile_path, "r", encoding="utf-8") as f:
            profile = json.load(f)

        basic = profile.get("基本信息", {})
        name = basic.get("姓名", "unknown")
        role = basic.get("职业", "unknown")

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
    info = get_profile_info(profile_path)
    if not info:
        return False

    env_name = f"{info['name']}_{info['role']}"
    env_path = output_dir / env_name

    if skip_existing and env_path.exists():
        print(f"  [SKIP] {env_name} (已存在)")
        return True

    print(f"  [处理] {env_name}")
    print(f"    输出: {env_path}")

    output_full_path = output_dir / env_name

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
            generate_file_mappings(env_path, info['profile'])
            return True
        else:
            print(f"  [FAIL] {env_name} 生成失败")
            print(f"    stderr: {result.stderr[-500:]}")
            return False
    except Exception as e:
        print(f"  [FAIL] {env_name} 生成失败: {e}")
        traceback.print_exc()
        return False


def generate_file_mappings(env_path: Path, profile: dict):
    """
    根据生成的环境目录结构，创建 Windows 和 Linux 的文件映射表。

    映射规则：
    - Windows: C/ → C:\\, D/ → D:\\
    - Linux: C/ → ~/, D/ → ~/workspace/
    """
    computer_profile_dir = env_path / "computer_profile"

    if not computer_profile_dir.exists():
        print(f"    [Skip] 未找到 computer_profile 目录，跳过映射表生成")
        return

    file_paths = []
    for file_path in computer_profile_dir.rglob("*"):
        if file_path.is_file():
            rel_path = file_path.relative_to(computer_profile_dir)
            file_paths.append(str(rel_path).replace("\\", "/"))

    windows_mapping = {}
    for path in file_paths:
        if path.startswith("C/"):
            win_src = "C:\\" + path[2:].replace("/", "\\")
        elif path.startswith("D/"):
            win_src = "D:\\" + path[2:].replace("/", "\\")
        else:
            win_src = path.replace("/", "\\")
        windows_mapping[path] = win_src

    linux_mapping = {}
    for path in file_paths:
        if path.startswith("C/"):
            linux_src = "~/" + path[2:]
        elif path.startswith("D/"):
            linux_src = "~/workspace/" + path[2:]
        else:
            linux_src = path
        linux_mapping[path] = linux_src

    windows_map_path = env_path / "MAP_Windows.json"
    with open(windows_map_path, "w", encoding="utf-8") as f:
        json.dump(windows_mapping, f, ensure_ascii=False, indent=2)
    print(f"    → MAP_Windows.json 已生成")

    linux_map_path = env_path / "MAP_Linux.json"
    with open(linux_map_path, "w", encoding="utf-8") as f:
        json.dump(linux_mapping, f, ensure_ascii=False, indent=2)
    print(f"    → MAP_Linux.json 已生成")


def main():
    """主函数"""
    log_path = _setup_tee_logging(DEFAULT_LOG_DIR)

    print("\n" + "=" * 60)
    print("  批量环境生成器")
    print("=" * 60)
    print(f"  日志文件: {log_path}")

    args = parse_args()
    profiles_dir = Path(args.profiles_dir)
    envs_dir = Path(args.envs_dir)
    max_concurrency = args.max_concurrency

    if not profiles_dir.exists():
        print(f"\n[Error] 用户画像目录不存在: {profiles_dir}")
        return 1

    if not _MAIN_SCRIPT.exists():
        print(f"\n[Error] main.py 不存在: {_MAIN_SCRIPT}")
        return 1

    envs_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n  用户画像目录: {profiles_dir}")
    print(f"  环境输出目录: {envs_dir}")
    print(f"  匹配模式: {args.pattern}")
    print(f"  最大并发数: {max_concurrency}")

    profile_files = sorted(profiles_dir.glob(args.pattern))

    if not profile_files:
        print(f"\n[Info] 未找到匹配的用户画像文件")
        return 0

    print(f"\n  找到 {len(profile_files)} 个用户画像文件")

    # ── 并行处理 ──────────────────────────────────────────────────────
    print("\n[开始生成]")
    results = {"success": 0, "fail": 0, "skip": 0}
    lock = threading.Lock()

    def _task(profile_file: Path) -> tuple[Path, bool]:
        tag = f"[{profile_file.stem}]"
        _task_tag.set(tag)
        success = generate_env_for_profile(
            profile_file,
            envs_dir,
            _MAIN_SCRIPT,
            skip_existing=args.skip_existing
        )
        return profile_file, success

    with ThreadPoolExecutor(max_workers=max_concurrency) as executor:
        futures = {executor.submit(_task, pf): pf for pf in profile_files}
        for future in as_completed(futures):
            pf = futures[future]
            try:
                _, success = future.result()
            except Exception as e:
                print(f"  [FAIL] {pf.name} 未捕获异常: {e}")
                traceback.print_exc()
                success = False

            with lock:
                if success:
                    results["success"] += 1
                else:
                    results["fail"] += 1

    print()

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
