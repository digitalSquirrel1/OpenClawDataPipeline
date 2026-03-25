# -*- coding: utf-8 -*-
import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


TIMESTAMP_RE = re.compile(r"^(?P<prefix>.+)_(?P<timestamp>\d{8}_\d{6})$")


@dataclass(frozen=True)
class RenamePair:
    old_stem: str
    new_stem: str
    timestamp: str


def short_code_from_timestamp(timestamp: str) -> str:
    """
    Convert YYYYMMDD_HHMMSS into the same 2-digit batch code used by the
    current profile generator: minute-of-day modulo 100.
    """
    dt = datetime.strptime(timestamp, "%Y%m%d_%H%M%S")
    minute_of_day = dt.hour * 60 + dt.minute
    return f"{minute_of_day % 100:02d}"


def convert_stem(stem: str) -> RenamePair | None:
    match = TIMESTAMP_RE.match(stem)
    if not match:
        return None
    prefix = match.group("prefix")
    timestamp = match.group("timestamp")
    return RenamePair(
        old_stem=stem,
        new_stem=f"{prefix}_{short_code_from_timestamp(timestamp)}",
        timestamp=timestamp,
    )


def ensure_unique_targets(rename_map: dict[str, str], label: str) -> None:
    reverse: dict[str, list[str]] = {}
    for old_name, new_name in rename_map.items():
        reverse.setdefault(new_name, []).append(old_name)

    conflicts = {new: olds for new, olds in reverse.items() if len(olds) > 1}
    if conflicts:
        lines = [f"{label} target name conflicts detected:"]
        for new_name, old_names in sorted(conflicts.items()):
            lines.append(f"  {new_name} <- {old_names}")
        raise ValueError("\n".join(lines))


def load_profile_rename_map(profiles_dir: Path) -> dict[str, str]:
    rename_map: dict[str, str] = {}
    for profile_path in sorted(profiles_dir.glob("*.json")):
        pair = convert_stem(profile_path.stem)
        if pair and pair.old_stem != pair.new_stem:
            rename_map[pair.old_stem] = pair.new_stem
    ensure_unique_targets(rename_map, "profile")
    return rename_map


def rename_path(old_path: Path, new_path: Path, dry_run: bool) -> None:
    if old_path == new_path:
        return
    if not old_path.exists():
        return
    if new_path.exists():
        raise FileExistsError(f"Target already exists: {new_path}")
    print(f"[rename] {old_path} -> {new_path}")
    if not dry_run:
        old_path.rename(new_path)


def rename_profiles(profiles_dir: Path, profile_map: dict[str, str], dry_run: bool) -> None:
    for old_stem, new_stem in sorted(profile_map.items()):
        rename_path(
            profiles_dir / f"{old_stem}.json",
            profiles_dir / f"{new_stem}.json",
            dry_run=dry_run,
        )


def load_env_rename_map(envs_dir: Path, profile_map: dict[str, str]) -> dict[str, str]:
    rename_map = dict(profile_map)
    for env_dir in sorted(envs_dir.iterdir()):
        if not env_dir.is_dir():
            continue
        if env_dir.name in rename_map:
            continue
        pair = convert_stem(env_dir.name)
        if pair and pair.old_stem != pair.new_stem:
            rename_map[pair.old_stem] = pair.new_stem
    ensure_unique_targets(rename_map, "environment")
    return rename_map


def update_pipeline_meta(meta_path: Path, old_stem: str, new_stem: str, dry_run: bool) -> bool:
    if not meta_path.exists():
        return False

    data = json.loads(meta_path.read_text(encoding="utf-8"))
    changed = False

    source_profile_path = data.get("source_profile_path")
    if isinstance(source_profile_path, str):
        src_path = Path(source_profile_path)
        if src_path.stem == old_stem:
            data["source_profile_path"] = str(src_path.with_name(f"{new_stem}{src_path.suffix}"))
            changed = True

    env_dir = data.get("env_dir")
    if isinstance(env_dir, str):
        env_path = Path(env_dir)
        if env_path.name == old_stem:
            data["env_dir"] = str(env_path.with_name(new_stem))
            changed = True

    if data.get("profile_dir_name") == old_stem:
        data["profile_dir_name"] = new_stem
        changed = True

    if changed:
        print(f"[update] {meta_path}")
        if not dry_run:
            meta_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    return changed


def rename_environment_children(env_root: Path, old_stem: str, new_stem: str, dry_run: bool) -> None:
    old_inner = env_root / old_stem
    new_inner = env_root / new_stem
    if old_inner.exists():
        rename_path(old_inner, new_inner, dry_run=dry_run)

    old_zip = env_root / f"{old_stem}.zip"
    new_zip = env_root / f"{new_stem}.zip"
    if old_zip.exists():
        rename_path(old_zip, new_zip, dry_run=dry_run)

    update_pipeline_meta(env_root / "pipeline_meta.json", old_stem, new_stem, dry_run=dry_run)


def rename_environments(envs_dir: Path, env_map: dict[str, str], dry_run: bool) -> None:
    for old_stem, new_stem in sorted(env_map.items()):
        env_root = envs_dir / old_stem
        if not env_root.exists():
            continue

        rename_environment_children(env_root, old_stem, new_stem, dry_run=dry_run)
        rename_path(env_root, envs_dir / new_stem, dry_run=dry_run)


def validate_root(root_dir: Path) -> tuple[Path, Path]:
    profiles_dir = root_dir / "profiles"
    envs_dir = root_dir / "environments"

    if not profiles_dir.exists():
        raise FileNotFoundError(f"profiles dir not found: {profiles_dir}")
    if not envs_dir.exists():
        raise FileNotFoundError(f"environments dir not found: {envs_dir}")

    return profiles_dir, envs_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rename profile/environment timestamp suffixes to 2-digit batch codes."
    )
    parser.add_argument("root_dir", type=str, help="Directory containing profiles/ and environments/")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview planned changes without renaming files.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root_dir = Path(args.root_dir).resolve()
    profiles_dir, envs_dir = validate_root(root_dir)

    profile_map = load_profile_rename_map(profiles_dir)
    env_map = load_env_rename_map(envs_dir, profile_map)

    print(f"[root] {root_dir}")
    print(f"[profiles] rename {len(profile_map)} files")
    print(f"[environments] rename {len(env_map)} directories")

    rename_profiles(profiles_dir, profile_map, dry_run=args.dry_run)
    rename_environments(envs_dir, env_map, dry_run=args.dry_run)

    if args.dry_run:
        print("[done] dry-run only, no changes written")
    else:
        print("[done] rename complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
