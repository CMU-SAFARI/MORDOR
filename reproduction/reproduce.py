#!/usr/bin/env python3
"""Coordinate local, Slurm, plotting, and OpenROAD reproduction workflows."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import yaml

from common import EXPERIMENT_CLASSES, resolve_path


SCRIPT_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = SCRIPT_DIR.parent
DEFAULT_SLURM_PROFILE = SCRIPT_DIR / "generic_slurm_config.yaml"
DEFAULT_LOCAL_PROFILE = SCRIPT_DIR / "local_config.yaml"


def load_config(path: Path) -> dict:
    with path.open() as stream:
        config = yaml.safe_load(stream) or {}
    if not isinstance(config, dict) or not isinstance(config.get("paths"), dict):
        raise ValueError(f"{path} must contain a paths mapping")
    return config


def load_execution_profile(path: Path, backend: str) -> dict:
    with path.open() as stream:
        profile = yaml.safe_load(stream) or {}
    configured_backend = profile.get("execution", {}).get("backend")
    if configured_backend != backend:
        raise SystemExit(
            f"{path} configures backend {configured_backend!r}, expected {backend!r}"
        )
    if "paths" not in profile or "traces" not in profile:
        raise SystemExit(f"{path} must contain paths and traces mappings")
    return profile


def profile_path(value: str | Path) -> Path:
    return resolve_path(value, PACKAGE_ROOT)


def native_paths(profile: dict) -> dict[str, Path]:
    paths = profile["paths"]
    return {
        "repo_root": profile_path(paths.get("repo_root", "ramulator")),
        "trace_dir": profile_path(paths.get("trace_dir", "cputraces")),
        "workspace_root": profile_path(paths.get("workspace_root", ".")),
        "ramulator": profile_path(
            paths.get("ramulator", "ramulator/build/ramulator2")
        ),
    }


def native_build_jobs(profile: dict, backend: str) -> int | None:
    value = profile.get(backend, {}).get("build_jobs")
    if value is None:
        return None
    if isinstance(value, bool):
        raise SystemExit(f"{backend}.build_jobs must be a positive integer")
    try:
        jobs = int(value)
    except (TypeError, ValueError):
        raise SystemExit(
            f"{backend}.build_jobs must be a positive integer"
        ) from None
    if jobs < 1:
        raise SystemExit(f"{backend}.build_jobs must be a positive integer")
    return jobs


def native_setup(profile: dict, backend: str) -> None:
    paths = native_paths(profile)
    traces = profile["traces"]
    url = traces.get("archive_url")
    sha256 = traces.get("archive_sha256")
    if not url or not sha256:
        raise SystemExit(
            "execution profile requires traces.archive_url and archive_sha256"
        )
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIR / "fetch_traces.py"),
            "--url", os.path.expandvars(str(url)),
            "--sha256", str(sha256),
            "--destination", str(paths["trace_dir"]),
        ],
        check=True,
    )
    command = [
        sys.executable,
        str(SCRIPT_DIR / "check_cluster.py"),
        "--backend", backend,
        "--repo-root", str(paths["repo_root"]),
        "--workspace-root", str(paths["workspace_root"]),
        "--trace-dir", str(paths["trace_dir"]),
        "--ramulator", str(paths["ramulator"]),
        "--build",
    ]
    build_jobs = native_build_jobs(profile, backend)
    if build_jobs is not None:
        command.extend(["--build-jobs", str(build_jobs)])
    subprocess.run(command, check=True)


def native_command(
    profile: dict,
    backend: str,
    action: str,
    classes: list[str],
    traces: list[str] | None,
) -> list[str]:
    paths = native_paths(profile)
    command = [
        sys.executable,
        str(SCRIPT_DIR / "run_experiments.py"),
        "--backend", backend,
        "--repo-root", str(paths["repo_root"]),
        "--workspace-root", str(paths["workspace_root"]),
        "--trace-dir", str(paths["trace_dir"]),
        "--ramulator", str(paths["ramulator"]),
        "--classes", *classes,
    ]
    if traces:
        command.extend(["--traces", *traces])
    if backend == "slurm":
        slurm = profile.get("slurm", {})
        for key, option in (
            ("partition", "--partition"),
            ("memory", "--memory"),
            ("exclude", "--exclude"),
            ("time", "--time"),
            ("account", "--account"),
            ("qos", "--qos"),
            ("constraint", "--constraint"),
        ):
            value = slurm.get(key)
            if value not in (None, ""):
                command.extend([option, str(value)])
        for value in slurm.get("extra_args") or []:
            command.append(f"--sbatch-arg={value}")
        for value in slurm.get("job_preamble") or []:
            command.append(f"--job-preamble={value}")
    else:
        local = profile.get("local", {})
        for value in local.get("job_preamble") or []:
            command.append(f"--job-preamble={value}")
    if action == "submit":
        command.append("--submit")
    elif action == "run":
        command.append("--run-local")
    elif action == "resume":
        command.append("--resume")
    elif action in ("status", "progress"):
        command.append("--status")
    return command


def add_native_parser(
    subparsers: argparse._SubParsersAction,
    backend: str,
    default_profile: Path,
) -> None:
    parser = subparsers.add_parser(backend)
    actions = (
        ("setup", "build", "plan", "submit", "status", "progress", "resume")
        if backend == "slurm"
        else ("setup", "build", "plan", "run", "status", "progress", "resume")
    )
    parser.add_argument("action", choices=actions)
    parser.add_argument("--profile", type=Path, default=default_profile)
    parser.add_argument(
        "--classes", nargs="+", choices=EXPERIMENT_CLASSES,
        default=EXPERIMENT_CLASSES,
    )
    parser.add_argument("--traces", nargs="+")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path,
        default=SCRIPT_DIR / "reproduction_config.yaml",
        help="paths for plotting and hardware reproduction",
    )
    subparsers = parser.add_subparsers(dest="target", required=True)

    openroad_parser = subparsers.add_parser("openroad")
    openroad_parser.add_argument("arguments", nargs=argparse.REMAINDER)

    figure_parser = subparsers.add_parser("figures")
    figure_parser.add_argument(
        "--traces",
        nargs="+",
        help="only plot these exact canonical trace names",
    )
    figure_parser.add_argument("arguments", nargs=argparse.REMAINDER)
    add_native_parser(subparsers, "slurm", DEFAULT_SLURM_PROFILE)
    add_native_parser(subparsers, "local", DEFAULT_LOCAL_PROFILE)

    args = parser.parse_args()
    repo = PACKAGE_ROOT

    if args.target in ("slurm", "local"):
        profile = load_execution_profile(profile_path(args.profile), args.target)
        if args.action == "setup":
            native_setup(profile, args.target)
            return
        if args.action == "build":
            command = [
                sys.executable,
                str(SCRIPT_DIR / "run_reproduction.py"),
            ]
            build_jobs = native_build_jobs(profile, args.target)
            if build_jobs is not None:
                command.extend(["--build-jobs", str(build_jobs)])
            command.append("build")
            subprocess.run(
                command,
                check=True,
            )
            return
        subprocess.run(
            native_command(
                profile, args.target, args.action, args.classes, args.traces
            ),
            check=True,
        )
        return
    config = load_config(profile_path(args.config))
    if args.target == "openroad":
        forwarded = args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
        openroad_dir = resolve_path(config["paths"]["openroad_dir"], repo)
        subprocess.run(
            [str(openroad_dir / "reproduce_table1.sh"), *forwarded],
            cwd=openroad_dir,
            check=True,
        )
        return

    output_paths = config["paths"]
    forwarded = args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
    plot_script = resolve_path(output_paths["plot_script"], repo)
    command = [
        sys.executable, str(plot_script),
        "--source-root", str(resolve_path(output_paths["results_root"], repo)),
        "--results-dir", str(resolve_path(output_paths["paper_results_dir"], repo)),
        "--figures-dir", str(resolve_path(output_paths["figure_dir"], repo)),
        "--rebuild-results",
    ]
    if args.traces:
        command.extend(["--traces", *args.traces])
    command.extend(forwarded)
    subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
