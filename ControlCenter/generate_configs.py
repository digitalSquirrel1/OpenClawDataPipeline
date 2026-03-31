"""
批量生成 AutomationConfig JSON 配置文件

用法示例：
  python generate_configs.py \
    --input  standard_output \
    --output configs/generated \
    --skill-dir /mnt/c/Users/Administrator/Downloads/dataset/skill_localize/skills_library \
    --agent-dir agents \
    --simulator-config configs/user_proxy_model.json \
    --workspace /home/nianzuzheng/.openclaw/workspace \
    --model claude-3-5-sonnet \
    --gateway-ws-url ws://127.0.0.1:18789/gateway \
    --timeout 3600
"""

import argparse
import json
import random
import sys
from pathlib import Path

# ─── 项目路径 & config 加载 ────────────────────────────────────────────────────
_CONTROL_CENTER = Path(__file__).resolve().parent
_PROJECT_ROOT   = _CONTROL_CENTER.parent

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config.config_loader import load_config

_cfg = load_config()
_gen_cfg = _cfg.get("generate_config", {})


def find_profile_file(folder: Path) -> str | None:
    """找到文件夹下 user_profile 开头的 JSON 文件，返回文件名"""
    for f in folder.iterdir():
        if f.name.startswith("user_profile") and f.suffix == ".json":
            return f.name
    return None


def find_map_file(folder: Path) -> str | None:
    """找到文件夹下 MAP_Linux.json 或 MAP_Windows.json，返回文件名（不含 .json 后缀）"""
    has_linux = (folder / "MAP_Linux.json").exists()
    has_windows = (folder / "MAP_Windows.json").exists()
    if has_linux and has_windows:
        raise FileExistsError(f"文件夹同时存在 MAP_Linux.json 和 MAP_Windows.json: {folder}")
    if has_linux:
        return "MAP_Linux"
    if has_windows:
        return "MAP_Windows"
    return None


def generate_single_config(
    folder: Path,
    input_base: Path,
    agent_index: int,
    query_index: int,
    query_text: str,
    path_discription_abs: str | None,
    skills: list,
    profile_file: str | None,
    map_file: str | None,
    skill_dir: str,
    agent_dir: str,
    simulator_config: str,
    workspace: str,
    model: str,
    gateway_ws_url: str,
    api_key: str | None,
    timeout: int,
    copy_map_not_workspace_ratio: float,
    hw_net_range: str,
) -> dict:
    """为单条 query 生成一份完整配置"""
    agent_name = f"assistant{agent_index}"
    relative_user_dir = Path(input_base.name) / folder.name

    # 根据 map_file 确定 platform
    if map_file == "MAP_Linux":
        platform = "linux"
    elif map_file == "MAP_Windows":
        platform = "windows"
    else:
        platform = None

    # 转换skills为路径字符串数组
    converted_skills = []
    for skill in skills:
        if isinstance(skill, dict) and "skill目录" in skill:
            converted_skills.append(Path(skill["skill目录"]).as_posix())
        else:
            converted_skills.append(skill)

    user_dir = {
        "path": relative_user_dir.as_posix(),
        "profile_file": profile_file,
    }
    if map_file is not None:
        if path_discription_abs == "abs":
            user_dir["map_file"] = map_file
        else:
            if random.random() < copy_map_not_workspace_ratio:
                user_dir["map_file"] = map_file

    return {
        "system": {
            "platform": [platform] if platform is not None else [],
            "hw_net_range": hw_net_range,
            "python": "3.12",
            "tools": []
        },
        "input_dir": {
            "skill_dir": Path(skill_dir).as_posix(),
            "agent_dir": agent_dir,
            "user_dir": user_dir
        },
        "agents": [
            {
                "name": agent_name,
                "config": [],
                "skills": converted_skills,
                "system_prompt": None,
                "model": model
            }
        ],
        "queries": [
            {
                "agent_name": agent_name,
                "text": query_text,
                "session_name": f"query{query_index}",
                "timeout": timeout
            }
        ],
        "gateway_ws_url": gateway_ws_url,
        "api_key": api_key,
        "workspace_base": workspace,
        "simulator_config": simulator_config
    }


def _resolve_path(val: str | None) -> str | None:
    """将相对路径解析为绝对路径（相对于 _PROJECT_ROOT）；绝对路径和 None 原样返回。"""
    if val is None:
        return None
    p = Path(val)
    if p.is_absolute():
        return str(p)
    return str((_PROJECT_ROOT / p).resolve())


def _get_param(name: str, cli_val, hardcoded_default, *, cast=None):
    """三级优先级：yaml generate_config > argparse CLI > hardcoded default。"""
    yaml_val = _gen_cfg.get(name)
    if yaml_val is not None:
        return cast(yaml_val) if cast else yaml_val
    if cli_val is not None:
        return cast(cli_val) if cast else cli_val
    return hardcoded_default


def main():
    # ── argparse：所有 default=None，仅作为 CLI 传参载体 ──────────────────────
    parser = argparse.ArgumentParser(description="批量生成 AutomationConfig JSON 配置文件（每条 query 一个文件）")
    parser.add_argument("--input",  default=None, help="输入文件夹，包含各 profile 子目录（精确到 environments 层）")
    parser.add_argument("--output", default=None, help="输出配置文件夹")
    parser.add_argument("--skill-dir",        default=None, help="技能库根目录")
    parser.add_argument("--agent-dir",        default=None, help="Agent 源文件目录")
    parser.add_argument("--simulator-config", default=None, help="Simulator 配置 JSON 路径")
    parser.add_argument("--workspace",        default=None, help="工作空间基础目录")
    parser.add_argument("--model",            default=None, help="模型名称，如 claude-3-5-sonnet")
    parser.add_argument("--gateway-ws-url",   default=None, help="WebSocket 网关 URL")
    parser.add_argument("--api-key",          default=None, help="API Key（可选）")
    parser.add_argument("--timeout",          type=int, default=None, help="每条 query 超时时间（秒，默认 3600）")
    parser.add_argument("--copy-map-not-workspace-ratio", type=float, default=None,
                        help="当 path_discription_abs 不是 abs 时，输出 map_file 的概率，默认 0.5")
    parser.add_argument("--hw-net-range", default=None, choices=["green", "blue"],
                        help="hw_net_range，可选 green/blue，默认 green")
    args = parser.parse_args()

    # ── 三级合并：yaml > CLI > hardcoded default ─────────────────────────────
    input_path  = _resolve_path(_get_param("input",  args.input,  "Outputs/260327/env_configs/linux2/environments"))
    output_path = _resolve_path(_get_param("output", args.output, "Outputs/260327/env_configs/linux2/configs"))
    args.skill_dir        = _get_param("skill_dir",        args.skill_dir,        "skill_localize/skills_library")
    args.agent_dir        = _get_param("agent_dir",        args.agent_dir,        "agents")
    args.simulator_config = _get_param("simulator_config", args.simulator_config, "configs/user_proxy_model.json")
    args.workspace        = _get_param("workspace",        args.workspace,        "/home/ma-user/.openclaw/workspace")
    args.model            = _get_param("model",            args.model,            "claude-3-5-sonnet")
    args.gateway_ws_url   = _get_param("gateway_ws_url",   args.gateway_ws_url,   "ws://127.0.0.1:18789/gateway")
    args.api_key          = _get_param("api_key",          args.api_key,          None)
    args.timeout          = _get_param("timeout",          args.timeout,          3600, cast=int)
    args.copy_map_not_workspace_ratio = _get_param(
        "copy_map_not_workspace_ratio", args.copy_map_not_workspace_ratio, 0.5, cast=float
    )
    args.hw_net_range = _get_param("hw_net_range", args.hw_net_range, "green")

    if args.hw_net_range not in ("green", "blue"):
        raise ValueError(f"--hw-net-range 必须是 green 或 blue，当前值: {args.hw_net_range}")

    if not 0 <= args.copy_map_not_workspace_ratio <= 1:
        raise ValueError("--copy-map-not-workspace-ratio 必须在 0 到 1 之间")

    input_dir  = Path(input_path)
    output_dir = Path(output_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 按名称排序，保证编号稳定
    folders = sorted(
        [f for f in input_dir.iterdir() if f.is_dir() and (f / "user_queries.json").exists()]
    )

    if not folders:
        print(f"⚠ 未找到包含 user_queries.json 的子目录: {input_dir}")
        return

    print(f"📂 共发现 {len(folders)} 个有效文件夹，开始生成配置...")

    total = 0
    success = 0
    global_agent_idx = 0
    for folder_idx, folder in enumerate(folders, start=1):
        try:
            queries_data = json.loads((folder / "user_queries.json").read_text(encoding="utf-8"))
            profile_file = find_profile_file(folder)
            map_file = find_map_file(folder)

            # 新格式：user_queries.json 是数组，每个元素有 topic、queries、skills
            for topic_item in queries_data:
                topic = topic_item.get("topic", "unknown")
                queries_list: list = topic_item.get("queries", [])
                skills: list = topic_item.get("skills", [])
                path_discription_abs_list: list = topic_item.get("path_discription_abs", [])

                # topic 中特殊字符替换为下划线
                safe_topic = topic.replace("/", "_").replace(" ", "_").replace("（", "_").replace("）", "_")

                for q_idx, query_text in enumerate(queries_list, start=1):
                    if isinstance(path_discription_abs_list, list) and q_idx - 1 < len(path_discription_abs_list):
                        path_discription_abs = path_discription_abs_list[q_idx - 1]
                    else:
                        path_discription_abs = None

                    total += 1
                    global_agent_idx += 1
                    config = generate_single_config(
                        folder=folder,
                        input_base=input_dir,
                        agent_index=global_agent_idx,
                        query_index=q_idx,
                        query_text=query_text,
                        path_discription_abs=path_discription_abs,
                        skills=skills,
                        profile_file=profile_file,
                        map_file=map_file,
                        skill_dir=args.skill_dir,
                        agent_dir=args.agent_dir,
                        simulator_config=args.simulator_config,
                        workspace=args.workspace,
                        model=args.model,
                        gateway_ws_url=args.gateway_ws_url,
                        api_key=args.api_key,
                        timeout=args.timeout,
                        copy_map_not_workspace_ratio=args.copy_map_not_workspace_ratio,
                        hw_net_range=args.hw_net_range,
                    )
                    out_file = output_dir / f"{folder.name}_{safe_topic}_q{q_idx}.json"
                    out_file.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
                    print(f"  ✓ {out_file.name}")
                    success += 1

        except Exception as e:
            print(f"  ✗ [{folder_idx:03d}] {folder.name}: {e}")

    print(f"\n✅ 完成：{success}/{total} 个配置已写入 {output_dir}")


if __name__ == "__main__":
    main()
