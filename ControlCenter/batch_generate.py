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

import os, sys, json, argparse, io, threading, contextvars, random
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

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
        # 保留 encoding 属性以兼容 reconfigure 等检测
        self.encoding = getattr(streams[0], "encoding", "utf-8")

    def write(self, data):
        if not data:
            return 0
        tag = _task_tag.get("")
        if tag:
            # 给每一行加上 tag 前缀（保留末尾换行）
            lines = data.split("\n")
            # 最后一个空元素说明 data 以 \n 结尾，不需要加 tag
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

    # 让 reconfigure 等调用不报错
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
_PROJECT_ROOT   = _CONTROL_CENTER.parent              # user_simulator_agent/
_WORKING_SPACE  = _PROJECT_ROOT / "WorkingSpace"

# 默认路径配置
DEFAULT_PROFILES_DIR = _PROJECT_ROOT / "Outputs" / "profiles"
DEFAULT_ENVS_DIR     = _PROJECT_ROOT / "Outputs" / "environments"
DEFAULT_LOG_DIR      = _PROJECT_ROOT / "Log"

# ─── 加载配置 & 导入 pipeline ─────────────────────────────────────────────────
# 把 project root 和 WorkingSpace 都加到 sys.path
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
if str(_WORKING_SPACE) not in sys.path:
    sys.path.insert(0, str(_WORKING_SPACE))
if str(_CONTROL_CENTER) not in sys.path:
    sys.path.insert(0, str(_CONTROL_CENTER))

from config.config_loader import load_config
from main import run_pipeline   # ← 直接 import，不再用 subprocess
from check_env import fix_readme, collect_disk_files

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
        "--overwrite-existing",
        action="store_true",
        help="覆盖已生成的环境（默认跳过）"
    )
    parser.add_argument(
        "--queries-dir",
        type=str,
        default=_batch_cfg.get("queries_dir", None),
        help="queries JSON 目录路径，为每个 profile 随机选一条 query 注入环境生成（默认：None，LLM 自由发挥）",
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


def generate_file_mappings(env_path: Path, profile_dir: Path):
    """
    根据生成的环境目录结构，创建 Windows 和 Linux 的文件映射表。

    目录结构：profile_dir 下直接存放 C/, D/, E/, Z/ 等盘符目录。

    映射规则（Windows）：X/ → X:\
    映射规则（Linux）：C/ → ~/, 其余盘符 X/ → ~/X/

    Args:
        env_path:    MAP JSON 文件的存放目录（env_name 外层）
        profile_dir: 实际文件系统根目录（包含 C/, D/, E/ 等盘符子目录）
    """
    if not profile_dir.exists():
        print(f"    [Skip] 未找到文件系统目录，跳过映射表生成")
        return

    # 收集所有文件路径（相对于 profile_dir，只收集盘符子目录下的文件）
    file_paths = []
    for file_path in profile_dir.rglob("*"):
        if file_path.is_file():
            rel_path = file_path.relative_to(profile_dir)
            parts = rel_path.parts
            # 只收录以单字母盘符目录开头的路径（C/, D/, E/, Z/ 等）
            if len(parts) >= 2 and len(parts[0]) == 1 and parts[0].isalpha():
                file_paths.append(str(rel_path).replace("\\", "/"))

    if not file_paths:
        print(f"    [Skip] 文件系统目录为空，跳过映射表生成")
        return

    # 生成 Windows 映射：X/ → X:\...
    windows_mapping = {}
    for path in file_paths:
        parts = path.split("/", 1)
        drive = parts[0]  # e.g. "C", "D", "E", "Z"
        rest = parts[1] if len(parts) > 1 else ""
        if len(drive) == 1 and drive.isalpha():
            win_src = drive + ":\\" + rest.replace("/", "\\")
        else:
            win_src = path.replace("/", "\\")
        windows_mapping[path] = win_src

    # 生成 Linux 映射：C/ → ~/, 其余 X/ → ~/X/
    linux_mapping = {}
    for path in file_paths:
        parts = path.split("/", 1)
        drive = parts[0]
        rest = parts[1] if len(parts) > 1 else ""
        if drive == "C":
            linux_src = "~/" + rest
        elif len(drive) == 1 and drive.isalpha():
            linux_src = f"~/{drive}/" + rest
        else:
            linux_src = path
        linux_mapping[path] = linux_src

    # 根据 WINDOWS_MAP_RATIO 概率只输出一个映射文件
    win_ratio = float(_batch_cfg.get("WINDOWS_MAP_RATIO", 0.7))
    if random.random() < win_ratio:
        map_path = env_path / "MAP_Windows.json"
        with open(map_path, "w", encoding="utf-8") as f:
            json.dump(windows_mapping, f, ensure_ascii=False, indent=2)
        print(f"    → MAP_Windows.json 已生成 ({len(windows_mapping)} 条)")
    else:
        map_path = env_path / "MAP_Linux.json"
        with open(map_path, "w", encoding="utf-8") as f:
            json.dump(linux_mapping, f, ensure_ascii=False, indent=2)
        print(f"    → MAP_Linux.json 已生成 ({len(linux_mapping)} 条)")


def _pick_query_for_profile(queries_dir: Path, profile_stem: str) -> str | None:
    """从 queries_dir 中找到该 profile 对应的 JSON，随机选一条 query 返回。"""
    query_file = queries_dir / f"{profile_stem}_queries.json"
    if not query_file.exists():
        return None
    try:
        data = json.loads(query_file.read_text(encoding="utf-8"))
        all_queries = [q for r in data.get("results", []) for q in r.get("queries", [])]
        return random.choice(all_queries) if all_queries else None
    except Exception as e:
        print(f"  [Warning] 读取 query 文件失败: {query_file.name} — {e}")
        return None


def generate_env_for_profile(
    profile_path: Path,
    envs_dir: Path,
    overwrite_existing: bool = False,
    query: str | None = None,
) -> bool:
    """为单个用户画像生成环境（直接调用 run_pipeline）。

    overwrite_existing=False（默认）时的逻辑：
      1. 环境目录已存在 → 视为完整生成，完全跳过
      2. 不存在          → 完整 3 步 pipeline
    """
    info = get_profile_info(profile_path)
    if not info:
        return False

    env_name    = profile_path.stem
    env_path    = envs_dir / env_name
    profile_dir = env_path / env_name   # Steps 1-3 生成的文件系统目录
    done_flag   = env_path / "task_done.txt"
    zip_path    = env_path / f"{env_name}.zip"

    if not overwrite_existing and (done_flag.exists() or zip_path.exists()):
        print(f"  [SKIP] {env_name} (已完成)")
        return True

    # 从头完整生成
    print(f"  [处理] {env_name}")
    print(f"    画像: {profile_path}")
    print(f"    输出: {env_path}")

    try:
        run_pipeline(
            user_profile_path=profile_path,
            output_dir=env_path,
            profile_dir_name=env_name,
            query=query,
        )
        print(f"  [OK] {env_name} 生成成功")
        fix_readme(profile_dir, collect_disk_files(profile_dir))
        generate_file_mappings(env_path, profile_dir)
        return True
    except Exception as e:
        import traceback
        print(f"  [FAIL] {env_name} 生成失败: {e}")
        traceback.print_exc()
        return False


def main():
    """主函数"""
    # ── 设置 tee 日志 ──────────────────────────────────────────────────
    log_path = _setup_tee_logging(DEFAULT_LOG_DIR)

    print("\n" + "=" * 60)
    print("  批量环境生成器")
    print("=" * 60)
    print(f"  日志文件: {log_path}")

    # 解析参数
    args = parse_args()
    profiles_dir = Path(args.profiles_dir)
    envs_dir = Path(args.envs_dir)
    queries_dir = Path(_resolve(args.queries_dir, Path(""))) if args.queries_dir else None
    max_concurrency = int(_cfg.get("pipeline_config", {}).get("MAX_LLM_CALLS", 4))

    # 检查路径
    if not profiles_dir.exists():
        print(f"\n[Error] 用户画像目录不存在: {profiles_dir}")
        return 1

    # 创建输出目录
    envs_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n  用户画像目录: {profiles_dir}")
    print(f"  环境输出目录: {envs_dir}")
    print(f"  最大并发数: {max_concurrency}")
    if queries_dir:
        print(f"  Query 驱动模式: {queries_dir}")

    # 查找所有用户画像文件
    profile_files = sorted(profiles_dir.glob("*.json"))

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
        query = None
        if queries_dir:
            query = _pick_query_for_profile(queries_dir, profile_file.stem)
            if query:
                print(f"  [Query] {profile_file.stem}: {query[:60]}...")
        success = generate_env_for_profile(
            profile_file,
            envs_dir,
            overwrite_existing=args.overwrite_existing,
            query=query,
        )
        return profile_file, success

    with ThreadPoolExecutor(max_workers=max_concurrency) as executor:
        futures = {
            executor.submit(_task, pf): pf for pf in profile_files
        }
        for future in as_completed(futures):
            pf = futures[future]
            try:
                _, success = future.result()
            except Exception as e:
                import traceback
                print(f"  [FAIL] {pf.name} 未捕获异常: {e}")
                traceback.print_exc()
                success = False

            with lock:
                if success:
                    results["success"] += 1
                else:
                    results["fail"] += 1

    # 汇总
    print("=" * 60)
    print("  生成完成")
    print("=" * 60)
    print(f"\n  总计: {len(profile_files)}")
    print(f"  成功: {results['success']}")
    print(f"  失败: {results['fail']}")
    print(f"  跳过: {results['skip']}")
    print(f"\n  日志文件: {log_path}")
    print()

    return 0 if results["fail"] == 0 else 1


if __name__ == "__main__":
    exit(main())
