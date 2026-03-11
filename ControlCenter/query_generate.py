# -*- coding: utf-8 -*-
"""
query_generate.py — 为已生成的 env 文件夹生成 user_queries.json
=================================================================
从 env 文件夹中读取 pipeline_meta.json、profile_analyzed.json、spec.json，
调用 UserQueryGenerator 生成用户 query，写入 user_queries.json。

使用方式：
  # 处理单个 env 文件夹
  python query_generate.py --env-dir Outputs/environments/林辰_AI工程师

  # 批量处理 envs 根目录下所有子文件夹
  python query_generate.py --envs-dir Outputs/environments

  # 批量处理，跳过已生成的
  python query_generate.py --envs-dir Outputs/environments --skip-existing
"""

import os, sys, json, argparse
from pathlib import Path
from datetime import datetime

# 支持中文字符显示
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ─── 路径设置 ───────────────────────────────────────────────────────────────
_CONTROL_CENTER = Path(__file__).resolve().parent
_PROJECT_ROOT   = _CONTROL_CENTER.parent              # user_simulator_agent/
_WORKING_SPACE  = _PROJECT_ROOT / "WorkingSpace"

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
if str(_WORKING_SPACE) not in sys.path:
    sys.path.insert(0, str(_WORKING_SPACE))

from config.config_loader import load_config
from utils.llm_client import LLMClient
from agents.user_query_generate import UserQueryGenerator


def _banner(msg: str) -> None:
    print("\n" + "═" * 60)
    print(f"  {msg}")
    print("═" * 60)


def _init_llm() -> LLMClient:
    """从配置初始化 LLMClient。"""
    cfg     = load_config()
    api_cfg = cfg.get("api_config", {})
    return LLMClient(
        os.getenv("LLM_API_KEY",  api_cfg.get("LLM_API_KEY",  "")),
        os.getenv("LLM_BASE_URL", api_cfg.get("LLM_BASE_URL", "")),
        os.getenv("LLM_MODEL",    api_cfg.get("LLM_MODEL",    "gpt-4o")),
        backend=os.getenv("LLM_BACKEND", api_cfg.get("LLM_BACKEND", "openai")),
    )


def generate_queries_for_env(env_dir: Path, llm: LLMClient) -> None:
    """为单个 env 文件夹生成并写入 user_queries.json。

    Args:
        env_dir: env 文件夹绝对路径（内含 pipeline_meta.json / profile_analyzed.json / spec.json）
        llm:     已初始化的 LLMClient

    Raises:
        FileNotFoundError: 缺少必要的中间文件
        RuntimeError:      UserQueryGenerator 生成失败
    """
    meta_path    = env_dir / "pipeline_meta.json"
    profile_path = env_dir / "profile_analyzed.json"
    spec_path    = env_dir / "spec.json"

    for p in (meta_path, profile_path, spec_path):
        if not p.exists():
            raise FileNotFoundError(f"缺少必要文件: {p}")

    meta    = json.loads(meta_path.read_text(encoding="utf-8"))
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    spec    = json.loads(spec_path.read_text(encoding="utf-8"))

    source_profile_path = meta.get("source_profile_path", "")

    generator      = UserQueryGenerator(llm)
    queries_result = generator.generate(profile, spec)

    if queries_result.get("error"):
        raise RuntimeError(f"UserQueryGenerator 失败: {queries_result['error']}")

    # 附加溯源元信息
    queries_result["source_profile_path"] = source_profile_path
    queries_result["env_dir"]             = str(env_dir.resolve())

    out_path = env_dir / "user_queries.json"
    out_path.write_text(
        json.dumps(queries_result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  → user_queries.json 已写入 ({len(queries_result.get('queries', []))} 条 query)")
    print(f"    source_profile_path: {source_profile_path}")
    print(f"    env_dir: {env_dir.resolve()}")


def parse_args():
    parser = argparse.ArgumentParser(description="为 env 文件夹生成 user_queries.json")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--env-dir",
        type=str,
        help="单个 env 文件夹路径",
    )
    group.add_argument(
        "--envs-dir",
        type=str,
        help="env 根目录，批量处理所有子文件夹",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        default=True,
        help="跳过已存在 user_queries.json 的文件夹",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    _banner("query_generate — 生成 user_queries.json")

    llm = _init_llm()

    if args.env_dir:
        # 单个 env 文件夹模式
        env_dir = Path(args.env_dir)
        if not env_dir.is_absolute():
            env_dir = (_PROJECT_ROOT / env_dir).resolve()

        if not env_dir.exists():
            print(f"[Error] env 文件夹不存在: {env_dir}")
            return 1

        queries_path = env_dir / "user_queries.json"
        if args.skip_existing and queries_path.exists():
            print(f"[SKIP] user_queries.json 已存在: {queries_path}")
            return 0

        print(f"\n[处理] {env_dir.name}")
        generate_queries_for_env(env_dir, llm)
        print(f"\n[OK] 完成")
        return 0

    else:
        # 批量模式
        envs_dir = Path(args.envs_dir)
        if not envs_dir.is_absolute():
            envs_dir = (_PROJECT_ROOT / envs_dir).resolve()

        if not envs_dir.exists():
            print(f"[Error] envs 根目录不存在: {envs_dir}")
            return 1

        # 找出所有包含 pipeline_meta.json 的子文件夹（即合法 env 文件夹）
        env_dirs = sorted(
            p.parent for p in envs_dir.glob("*/pipeline_meta.json")
        )

        if not env_dirs:
            print(f"[Info] 未找到含 pipeline_meta.json 的子文件夹: {envs_dir}")
            return 0

        print(f"\n  找到 {len(env_dirs)} 个 env 文件夹")

        success = fail = skip = 0
        for env_dir in env_dirs:
            queries_path = env_dir / "user_queries.json"
            if args.skip_existing and queries_path.exists():
                print(f"  [SKIP] {env_dir.name} (user_queries.json 已存在)")
                skip += 1
                continue

            print(f"\n  [处理] {env_dir.name}")
            try:
                generate_queries_for_env(env_dir, llm)
                print(f"  [OK] {env_dir.name}")
                success += 1
            except Exception as e:
                import traceback
                print(f"  [FAIL] {env_dir.name}: {e}")
                traceback.print_exc()
                fail += 1

        print("\n" + "=" * 60)
        print(f"  总计: {len(env_dirs)}  成功: {success}  失败: {fail}  跳过: {skip}")
        print("=" * 60)
        return 0 if fail == 0 else 1


if __name__ == "__main__":
    exit(main())
