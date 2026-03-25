# -*- coding: utf-8 -*-
"""
Cross-platform pipeline runner with validation, logging, and resume support.
python user_simulator_agent/ControlCenter/pipeline_runner.py --config baseline_using.yaml --skip-preflight
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import sys
import traceback
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

_CONTROL_CENTER = Path(__file__).resolve().parent
_PROJECT_ROOT = _CONTROL_CENTER.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
_CONFIG_DIR = _PROJECT_ROOT / "config"
_OUTPUTS_DIR = _PROJECT_ROOT / "Outputs"
_STATE_FILE = "run_state.json"
_VALIDATION_JSON = "validation_report.json"
_VALIDATION_MD = "validation_report.md"
_LOGS_DIR = "logs"
_ARTIFACTS_DIR = "artifacts"
_CONFIG_ENV_VAR = "USER_SIMULATOR_CONFIG_PATH"

STAGES = [
    "validate_config",
    "generate_user_profile",
    "batch_generate",
    "query_gen_with_topic_skill_profile",
    "standard_format",
]

SCRIPT_PATHS = {
    "generate_user_profile": _CONTROL_CENTER / "generate_user_profile.py",
    "batch_generate": _CONTROL_CENTER / "batch_generate.py",
    "query_gen_with_topic_skill_profile": _CONTROL_CENTER / "query_gen_with_topic_skill_profile.py",
    "standard_format": _CONTROL_CENTER / "standard_format.py",
}

STAGE_OUTPUT_KEYS = {
    "generate_user_profile": ["profiles_dir"],
    "batch_generate": ["envs_dir"],
    "query_gen_with_topic_skill_profile": ["output_dir"],
    "standard_format": ["output_dir", "envs_dir"],
}


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def print_banner(title: str) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def mask_sensitive(obj: Any) -> Any:
    if isinstance(obj, dict):
        masked = {}
        for key, value in obj.items():
            if any(token in key.upper() for token in ("KEY", "TOKEN", "SECRET", "PASSWORD")):
                if isinstance(value, str) and value:
                    masked[key] = f"{value[:4]}***{value[-2:]}" if len(value) > 6 else "***"
                else:
                    masked[key] = "***" if value else value
            else:
                masked[key] = mask_sensitive(value)
        return masked
    if isinstance(obj, list):
        return [mask_sensitive(item) for item in obj]
    return obj


def resolve_config_path(config_arg: str | None) -> Path:
    if not config_arg:
        return (_CONFIG_DIR / "baseline_using.yaml").resolve()
    candidate = Path(config_arg)
    if candidate.is_absolute():
        return candidate.resolve()
    if candidate.parent == Path("."):
        return (_CONFIG_DIR / candidate).resolve()
    return (_PROJECT_ROOT / candidate).resolve()


def load_yaml(config_path: Path) -> dict:
    with open(config_path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def resolve_project_path(value: str | None) -> Path | None:
    if value is None:
        return None
    path = Path(value)
    return path if path.is_absolute() else (_PROJECT_ROOT / path).resolve()


def ensure_workspace(workspace_arg: str | None) -> Path:
    if workspace_arg:
        workspace = Path(workspace_arg)
        if not workspace.is_absolute():
            workspace = (_PROJECT_ROOT / workspace).resolve()
    else:
        workspace = (_OUTPUTS_DIR / datetime.now().strftime("%Y%m%d_%H%M%S")).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / _LOGS_DIR).mkdir(exist_ok=True)
    (workspace / _ARTIFACTS_DIR).mkdir(exist_ok=True)
    return workspace


def state_path(workspace: Path) -> Path:
    return workspace / _STATE_FILE


def validation_json_path(workspace: Path) -> Path:
    return workspace / _VALIDATION_JSON


def validation_md_path(workspace: Path) -> Path:
    return workspace / _VALIDATION_MD


def init_stage_state(workspace: Path) -> dict:
    logs_dir = workspace / _LOGS_DIR
    stages = {}
    for stage in STAGES:
        stages[stage] = {
            "status": "pending",
            "started_at": None,
            "ended_at": None,
            "duration_seconds": None,
            "command": None,
            "exit_code": None,
            "log_path": str((logs_dir / f"{stage}.log").resolve()),
            "outputs": [],
            "error_type": None,
            "error_message": None,
            "traceback": None,
        }
    return stages


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_state(workspace: Path) -> dict:
    path = state_path(workspace)
    if not path.exists():
        raise FileNotFoundError(f"workspace state file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(workspace: Path, state: dict) -> None:
    state["updated_at"] = now_iso()
    write_json(state_path(workspace), state)


def summarize_value(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def prompt_paths_from_config(cfg: dict) -> list[Path]:
    prompt_paths: list[Path] = []
    for value in cfg.values():
        if not isinstance(value, dict):
            continue
        for key, item in value.items():
            if key.startswith("PROMPT") and item:
                prompt_paths.append(resolve_project_path(item))
    return prompt_paths


def count_topics(topics_path: Path) -> int:
    topics = []
    for line in topics_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        if line and line[0].isdigit():
            dot_idx = line.find(".")
            if dot_idx != -1 and dot_idx < 5:
                line = line[dot_idx + 1 :].strip()
        if "：" in line:
            line = line.split("：", 1)[0].strip()
        elif ":" in line:
            line = line.split(":", 1)[0].strip()
        if line:
            topics.append(line)
    return len(topics)


def parent_creatable(path: Path) -> bool:
    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    return probe.exists()


def validation_report_to_markdown(report: dict) -> str:
    lines = [
        "# Validation Report",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Config path: `{report['config_path']}`",
        f"- Validation passed: `{report['validation_passed']}`",
        f"- Need environments: `{report['need_envs']}`",
        f"- Need skills: `{report['need_skills']}`",
        "",
        "## Key Metrics",
        "",
        f"- User profile count: `{report['metrics']['profile_count']}`",
        f"- Topic count: `{report['metrics']['topic_count']}`",
        f"- Num user per topic: `{report['metrics']['num_user_per_topic']}`",
        f"- Estimated query total: `{report['metrics']['estimated_query_total']}`",
        f"- detailed_query_ratio: `{report['metrics']['detailed_query_ratio']}` (详细型 query 概率)",
        f"- simple_query_ratio: `{report['metrics']['simple_query_ratio']}` (简洁型 query 概率)",
        f"- WINDOWS_MAP_RATIO: `{report['metrics']['windows_map_ratio']}` (Windows 映射生成概率)",
        "",
        "## Checks",
        "",
    ]
    for item in report["checks"]:
        lines.append(f"- [{item['status'].upper()}] {item['message']}")
    lines += ["", "## Service Checks", ""]
    for name, result in report["service_checks"].items():
        lines.append(
            f"- {name}: `{result['status']}` | http={summarize_value(result['http_status'])} | {result['summary']}"
        )
    return "\n".join(lines) + "\n"


def add_check(report: dict, ok: bool, message: str) -> None:
    report["checks"].append({"status": "ok" if ok else "fail", "message": message})
    print(f"[{'OK' if ok else 'FAIL'}] {message}")


def validate_config(config_path: Path, cfg: dict, workspace: Path, skip_preflight: bool) -> dict:
    report = {
        "generated_at": now_iso(),
        "config_path": str(config_path),
        "validation_passed": False,
        "need_envs": False,
        "need_skills": False,
        "metrics": {},
        "checks": [],
        "service_checks": {},
        "resolved_paths": {},
    }

    gen_cfg = cfg.get("generate_user_profile_config", {})
    batch_cfg = cfg.get("batch_generate_config", {})
    query_cfg = cfg.get("query_gen_with_topic_skill_profile_config", {})
    fmt_cfg = cfg.get("standard_format_config", {})
    skills_cfg = cfg.get("topic_search_skills_config", {})

    profiles_paths = {
        "generate_user_profile_config.profiles_dir": resolve_project_path(gen_cfg.get("profiles_dir")),
        "batch_generate_config.profiles_dir": resolve_project_path(batch_cfg.get("profiles_dir")),
        "query_gen_with_topic_skill_profile_config.profiles_dir": resolve_project_path(query_cfg.get("profiles_dir")),
        "standard_format_config.profiles_dir": resolve_project_path(fmt_cfg.get("profiles_dir")),
    }
    non_null_profiles = {k: v for k, v in profiles_paths.items() if v is not None}
    if not non_null_profiles:
        add_check(report, False, "No profiles_dir configured in pipeline config sections")
    else:
        unique_profiles = {str(v) for v in non_null_profiles.values()}
        add_check(
            report,
            len(unique_profiles) == 1,
            "All configured profiles_dir values resolve to the same path",
        )

    env_paths = {
        "batch_generate_config.envs_dir": resolve_project_path(batch_cfg.get("envs_dir")),
        "query_gen_with_topic_skill_profile_config.envs_dir": resolve_project_path(query_cfg.get("envs_dir")),
        "standard_format_config.envs_dir": resolve_project_path(fmt_cfg.get("envs_dir")),
    }
    non_null_envs = {k: v for k, v in env_paths.items() if v is not None}
    add_check(
        report,
        len({str(v) for v in non_null_envs.values()}) <= 1,
        "All non-null envs_dir values resolve to the same path",
    )

    topics_path = resolve_project_path(query_cfg.get("topics_txt_path"))
    if topics_path is None or not topics_path.exists():
        add_check(report, False, f"topics_txt_path exists: {topics_path}")
        topic_count = 0
    else:
        add_check(report, True, f"topics_txt_path exists: {topics_path}")
        topic_count = count_topics(topics_path)

    profile_count = int(gen_cfg.get("count") or 0)
    num_user_per_topic = query_cfg.get("num_user_per_topic")
    if num_user_per_topic is None:
        num_user_per_topic = profile_count
    else:
        num_user_per_topic = int(num_user_per_topic)

    detailed_query_ratio = query_cfg.get("detailed_query_ratio")
    simple_query_ratio = query_cfg.get("simple_query_ratio")
    windows_map_ratio = batch_cfg.get("WINDOWS_MAP_RATIO")
    estimated_query_total = profile_count * topic_count * num_user_per_topic

    report["metrics"] = {
        "profile_count": profile_count,
        "topic_count": topic_count,
        "num_user_per_topic": num_user_per_topic,
        "estimated_query_total": estimated_query_total,
        "detailed_query_ratio": detailed_query_ratio,
        "simple_query_ratio": simple_query_ratio,
        "windows_map_ratio": windows_map_ratio,
    }

    print_banner("Generation Metrics")
    print(f"user_profile count: {profile_count}")
    print(f"topic count: {topic_count}")
    print(f"num_user_per_topic: {num_user_per_topic}")
    print(f"estimated query total: {estimated_query_total}")
    print(f"detailed_query_ratio: {detailed_query_ratio} (详细型 query 概率)")
    print(f"simple_query_ratio: {simple_query_ratio} (简洁型 query 概率)")
    print(f"WINDOWS_MAP_RATIO: {windows_map_ratio} (Windows 环境映射生成概率)")

    need_envs = query_cfg.get("envs_dir") is not None
    need_skills = bool(query_cfg.get("use_match_skills", True))
    report["need_envs"] = need_envs
    report["need_skills"] = need_skills

    print_banner("Pipeline Modes")
    print(f"need environments: {need_envs}")
    print(f"need skills: {need_skills}")

    fmt_output_dir = fmt_cfg.get("output_dir")
    fmt_envs_dir = fmt_cfg.get("envs_dir")
    if not need_envs:
        add_check(report, fmt_envs_dir is None, "No-env mode requires standard_format_config.envs_dir to be null")
        add_check(report, fmt_output_dir is not None, "No-env mode requires standard_format_config.output_dir to be non-null")
    else:
        add_check(report, fmt_envs_dir is not None, "Env mode requires standard_format_config.envs_dir to be non-null")
        add_check(report, fmt_output_dir is None, "Env mode requires standard_format_config.output_dir to be null")

    add_check(report, query_cfg.get("envs_dir") is None or batch_cfg.get("envs_dir") is not None, "Env mode requires batch_generate_config.envs_dir to be configured")

    skills_json_path = resolve_project_path(skills_cfg.get("skills_json_path"))
    skills_dir = resolve_project_path(skills_cfg.get("skills_dir"))
    topic_to_skills_map = resolve_project_path(skills_cfg.get("topic_to_skills_map")) if skills_cfg.get("topic_to_skills_map") else None

    if need_skills:
        add_check(report, skills_json_path is not None and skills_json_path.exists(), f"skills_json_path exists: {skills_json_path}")
    else:
        add_check(report, True, "use_match_skills is false; skills_json_path check skipped")
    add_check(report, skills_dir is not None and skills_dir.exists(), f"skills_dir exists: {skills_dir}")
    if topic_to_skills_map is not None:
        add_check(report, topic_to_skills_map.exists(), f"topic_to_skills_map exists: {topic_to_skills_map}")
    else:
        add_check(report, True, "topic_to_skills_map is null; skills index may be auto-built")

    for prompt_path in prompt_paths_from_config(cfg):
        add_check(report, prompt_path.exists(), f"prompt exists: {prompt_path}")

    for label, path in {
        "profiles_dir parent creatable": next(iter(non_null_profiles.values())).parent if non_null_profiles else None,
        "envs_dir parent creatable": next(iter(non_null_envs.values())).parent if non_null_envs else None,
        "query output_dir parent creatable": resolve_project_path(query_cfg.get("output_dir")).parent if query_cfg.get("output_dir") else None,
        "standard_format output_dir parent creatable": resolve_project_path(fmt_cfg.get("output_dir")).parent if fmt_cfg.get("output_dir") else None,
    }.items():
        if path is None:
            continue
        add_check(report, parent_creatable(path), f"{label}: {path}")

    report["resolved_paths"] = {
        "profiles_dir": str(next(iter(non_null_profiles.values())).resolve()) if non_null_profiles else None,
        "envs_dir": str(next(iter(non_null_envs.values())).resolve()) if non_null_envs else None,
        "topics_txt_path": str(topics_path.resolve()) if topics_path and topics_path.exists() else str(topics_path) if topics_path else None,
        "query_output_dir": str(resolve_project_path(query_cfg.get("output_dir"))) if query_cfg.get("output_dir") else None,
        "standard_format_output_dir": str(resolve_project_path(fmt_cfg.get("output_dir"))) if fmt_cfg.get("output_dir") else None,
        "skills_json_path": str(skills_json_path) if skills_json_path else None,
        "skills_dir": str(skills_dir) if skills_dir else None,
    }

    if not skip_preflight:
        from tests.test_jina_connection import check_jina_connection
        from tests.test_llm_connection import check_llm_connection
        from tests.test_serper_connection import check_serper_connection

        print_banner("Service Checks")
        report["service_checks"]["serper"] = check_serper_connection()
        print(f"serper: {report['service_checks']['serper']['status']} | {report['service_checks']['serper']['summary']}")
        report["service_checks"]["jina"] = check_jina_connection()
        print(f"jina: {report['service_checks']['jina']['status']} | {report['service_checks']['jina']['summary']}")
        report["service_checks"]["llm"] = check_llm_connection()
        print(f"llm: {report['service_checks']['llm']['status']} | {report['service_checks']['llm']['summary']}")
    else:
        report["service_checks"] = {
            "serper": {"status": "skipped", "http_status": None, "summary": "Skipped by --skip-preflight", "raw_excerpt": ""},
            "jina": {"status": "skipped", "http_status": None, "summary": "Skipped by --skip-preflight", "raw_excerpt": ""},
            "llm": {"status": "skipped", "http_status": None, "summary": "Skipped by --skip-preflight", "raw_excerpt": ""},
        }

    write_json(workspace / _ARTIFACTS_DIR / "service_checks.json", report["service_checks"])

    all_checks_ok = all(item["status"] == "ok" for item in report["checks"])
    services_ok = all(result["status"] in {"ok", "skipped"} for result in report["service_checks"].values())
    report["validation_passed"] = all_checks_ok and services_ok
    write_json(validation_json_path(workspace), report)
    validation_md_path(workspace).write_text(validation_report_to_markdown(report), encoding="utf-8")
    return report


def build_initial_state(workspace: Path, mode: str, config_path: Path, cfg: dict) -> dict:
    return {
        "workspace_dir": str(workspace.resolve()),
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "mode": mode,
        "config_path": str(config_path.resolve()),
        "config_snapshot": mask_sensitive(copy.deepcopy(cfg)),
        "resolved_paths": {},
        "validation_passed": None,
        "need_envs": None,
        "need_skills": None,
        "stage_order": STAGES,
        "stages": init_stage_state(workspace),
        "last_successful_stage": None,
    }


@contextmanager
def configured_environment(config_path: Path):
    old_value = os.environ.get(_CONFIG_ENV_VAR)
    os.environ[_CONFIG_ENV_VAR] = str(config_path.resolve())
    try:
        from config.config_loader import reset_config_cache

        reset_config_cache()
        yield
    finally:
        if old_value is None:
            os.environ.pop(_CONFIG_ENV_VAR, None)
        else:
            os.environ[_CONFIG_ENV_VAR] = old_value
        from config.config_loader import reset_config_cache

        reset_config_cache()


def stage_outputs_for(stage: str, cfg: dict) -> list[str]:
    section_map = {
        "generate_user_profile": "generate_user_profile_config",
        "batch_generate": "batch_generate_config",
        "query_gen_with_topic_skill_profile": "query_gen_with_topic_skill_profile_config",
        "standard_format": "standard_format_config",
    }
    section_name = section_map.get(stage)
    if not section_name:
        return []
    section = cfg.get(section_name, {})
    outputs = []
    for key in STAGE_OUTPUT_KEYS.get(stage, []):
        value = section.get(key)
        path = resolve_project_path(value)
        if path is not None:
            outputs.append(str(path))
    return outputs


def run_script_stage(stage: str, config_path: Path, workspace: Path, state: dict) -> None:
    stage_state = state["stages"][stage]
    script_path = SCRIPT_PATHS[stage]
    command = [sys.executable, str(script_path)]
    log_path = Path(stage_state["log_path"])
    env = os.environ.copy()
    env[_CONFIG_ENV_VAR] = str(config_path.resolve())
    env["PYTHONIOENCODING"] = "utf-8"
    env["USER_SIMULATOR_WORKSPACE"] = str(workspace.resolve())

    stage_state["status"] = "running"
    stage_state["started_at"] = now_iso()
    stage_state["ended_at"] = None
    stage_state["duration_seconds"] = None
    stage_state["command"] = command
    stage_state["exit_code"] = None
    stage_state["error_type"] = None
    stage_state["error_message"] = None
    stage_state["traceback"] = None
    save_state(workspace, state)

    start = datetime.now()
    completed = subprocess.run(
        command,
        cwd=str(_PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    log_content = []
    log_content.append(f"stage={stage}")
    log_content.append(f"started_at={stage_state['started_at']}")
    log_content.append(f"command={json.dumps(command, ensure_ascii=False)}")
    log_content.append(f"config_path={config_path}")
    log_content.append("")
    log_content.append("=== STDOUT ===")
    log_content.append(completed.stdout or "")
    log_content.append("")
    log_content.append("=== STDERR ===")
    log_content.append(completed.stderr or "")
    log_path.write_text("\n".join(log_content), encoding="utf-8")

    end = datetime.now()
    stage_state["ended_at"] = now_iso()
    stage_state["duration_seconds"] = round((end - start).total_seconds(), 3)
    stage_state["exit_code"] = completed.returncode
    stage_state["outputs"] = stage_outputs_for(stage, load_yaml(config_path))
    if completed.returncode == 0:
        stage_state["status"] = "success"
        state["last_successful_stage"] = stage
    else:
        stage_state["status"] = "failed"
        stage_state["error_type"] = "SubprocessError"
        stage_state["error_message"] = f"{stage} exited with code {completed.returncode}"
        stage_state["traceback"] = completed.stderr[-4000:] if completed.stderr else None
    save_state(workspace, state)
    if completed.returncode != 0:
        raise RuntimeError(stage_state["error_message"])


def mark_stage_skipped(workspace: Path, state: dict, stage: str, reason: str) -> None:
    stage_state = state["stages"][stage]
    stage_state["status"] = "skipped"
    stage_state["started_at"] = now_iso()
    stage_state["ended_at"] = now_iso()
    stage_state["duration_seconds"] = 0.0
    stage_state["command"] = None
    stage_state["exit_code"] = 0
    stage_state["outputs"] = []
    stage_state["error_type"] = None
    stage_state["error_message"] = reason
    stage_state["traceback"] = None
    Path(stage_state["log_path"]).write_text(reason + "\n", encoding="utf-8")
    save_state(workspace, state)


def stages_to_run(state: dict, force_stage: str | None) -> set[str]:
    if not force_stage:
        return {
            stage
            for stage in STAGES
            if state["stages"][stage]["status"] in {"pending", "failed", "running"}
        }
    start_index = STAGES.index(force_stage)
    return set(STAGES[start_index:])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cross-platform pipeline runner")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--config", default="baseline_using.yaml", help="Config YAML name or path")
    group.add_argument("--resume", help="Resume from an existing workspace directory")
    parser.add_argument("--workspace", help="Workspace directory; default is Outputs/<timestamp>")
    parser.add_argument("--force-stage", choices=STAGES[1:], help="Force rerun this stage and all following stages when used with --resume")
    parser.add_argument("--skip-preflight", action="store_true", help="Skip external connectivity tests")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.resume:
        workspace = Path(args.resume)
        if not workspace.is_absolute():
            workspace = (_PROJECT_ROOT / workspace).resolve()
        (workspace / _LOGS_DIR).mkdir(parents=True, exist_ok=True)
        (workspace / _ARTIFACTS_DIR).mkdir(parents=True, exist_ok=True)
        state = load_state(workspace)
        config_path = Path(state["config_path"]).resolve()
        cfg = load_yaml(config_path)
        state["mode"] = "resume"
        save_state(workspace, state)
    else:
        config_path = resolve_config_path(args.config)
        cfg = load_yaml(config_path)
        workspace = ensure_workspace(args.workspace)
        state = build_initial_state(workspace, "config", config_path, cfg)
        save_state(workspace, state)

    print_banner("Pipeline Runner")
    print(f"workspace: {workspace}")
    print(f"config: {config_path}")

    if not args.resume or state["stages"]["validate_config"]["status"] in {"pending", "failed", "running"} or args.force_stage == "validate_config":
        try:
            with configured_environment(config_path):
                report = validate_config(config_path, cfg, workspace, args.skip_preflight)
        except Exception as exc:
            state["stages"]["validate_config"]["status"] = "failed"
            state["stages"]["validate_config"]["started_at"] = state["stages"]["validate_config"]["started_at"] or now_iso()
            state["stages"]["validate_config"]["ended_at"] = now_iso()
            state["stages"]["validate_config"]["error_type"] = type(exc).__name__
            state["stages"]["validate_config"]["error_message"] = str(exc)
            state["stages"]["validate_config"]["traceback"] = traceback.format_exc()
            save_state(workspace, state)
            raise
        state["resolved_paths"] = report["resolved_paths"]
        state["validation_passed"] = report["validation_passed"]
        state["need_envs"] = report["need_envs"]
        state["need_skills"] = report["need_skills"]
        validate_stage = state["stages"]["validate_config"]
        validate_stage["status"] = "success" if report["validation_passed"] else "failed"
        validate_stage["started_at"] = validate_stage["started_at"] or now_iso()
        validate_stage["ended_at"] = now_iso()
        validate_stage["duration_seconds"] = 0.0
        validate_stage["exit_code"] = 0 if report["validation_passed"] else 1
        validate_stage["outputs"] = [
            str(validation_json_path(workspace)),
            str(validation_md_path(workspace)),
            str((workspace / _ARTIFACTS_DIR / "service_checks.json").resolve()),
        ]
        validate_stage["error_type"] = None if report["validation_passed"] else "ValidationError"
        validate_stage["error_message"] = None if report["validation_passed"] else "Preflight validation failed"
        validate_stage["traceback"] = None
        save_state(workspace, state)
        if report["validation_passed"]:
            state["last_successful_stage"] = "validate_config"
            save_state(workspace, state)
        else:
            print("Validation failed. See workspace report files for details.")
            return 1
    elif state.get("validation_passed") is not True:
        print("Cannot resume execution because previous validation did not pass.")
        return 1

    run_set = stages_to_run(state, args.force_stage)
    for stage in STAGES[1:]:
        if stage not in run_set:
            continue
        if stage == "batch_generate" and not state["need_envs"]:
            mark_stage_skipped(workspace, state, stage, "Skipped because env generation is not required")
            continue
        print_banner(f"Running stage: {stage}")
        try:
            with configured_environment(config_path):
                run_script_stage(stage, config_path, workspace, state)
        except Exception as exc:
            stage_state = state["stages"][stage]
            if stage_state["status"] != "failed":
                stage_state["status"] = "failed"
                stage_state["ended_at"] = now_iso()
                stage_state["error_type"] = type(exc).__name__
                stage_state["error_message"] = str(exc)
                stage_state["traceback"] = traceback.format_exc()
                save_state(workspace, state)
            print(f"Stage failed: {stage}. See {stage_state['log_path']}")
            return 1

    print_banner("Pipeline Completed")
    print(f"workspace: {workspace}")
    print(f"last successful stage: {state.get('last_successful_stage')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
