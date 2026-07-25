#!/usr/bin/env python3
"""Validate and prepare a Slurm or local MORDOR execution environment."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from common import TRACES


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def require_command(name: str) -> None:
    if shutil.which(name) is None:
        raise SystemExit(f"environment setup failed: required command not found: {name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--workspace-root", type=Path, required=True)
    parser.add_argument("--trace-dir", type=Path, required=True)
    parser.add_argument("--ramulator", type=Path, required=True)
    parser.add_argument("--backend", choices=("slurm", "local"), default="slurm")
    parser.add_argument("--build", action="store_true")
    parser.add_argument(
        "--build-jobs",
        type=positive_int,
        help="maximum number of concurrent compiler jobs",
    )
    args = parser.parse_args()

    if sys.version_info < (3, 9):
        raise SystemExit("environment setup failed: Python 3.9 or newer is required")
    try:
        import yaml  # noqa: F401
    except ImportError as error:
        raise SystemExit(
            "environment setup failed: Python package PyYAML is missing"
        ) from error

    commands = ["cmake", "c++"]
    if args.backend == "slurm":
        commands.extend(("sbatch", "squeue"))
    for command in commands:
        require_command(command)

    required_repo_files = (
        args.repo_root / "CMakeLists.txt",
        args.repo_root / "ramulator_configs",
        args.repo_root.parent / "artifact_evaluation" / "run_experiments.py",
    )
    missing_repo = [path for path in required_repo_files if not path.exists()]
    if missing_repo:
        raise SystemExit(
            "environment setup failed: incomplete checkout:\n  "
            + "\n  ".join(map(str, missing_repo))
        )

    missing_traces = [name for name in TRACES if not (args.trace_dir / name).is_file()]
    if missing_traces:
        raise SystemExit(
            f"environment setup failed: {len(missing_traces)} of 55 traces are "
            f"missing from "
            f"{args.trace_dir}; first missing trace: {missing_traces[0]}"
        )

    args.workspace_root.mkdir(parents=True, exist_ok=True)
    probe = args.workspace_root / ".mordor_ae_write_test"
    probe.write_text("ok\n")
    probe.unlink()

    if args.build:
        build_dir = args.repo_root / "build"
        subprocess.run(
            ["cmake", "-S", str(args.repo_root), "-B", str(build_dir)],
            check=True,
        )
        build_command = ["cmake", "--build", str(build_dir), "-j"]
        if args.build_jobs is not None:
            build_command.append(str(args.build_jobs))
        subprocess.run(build_command, check=True)

    if not args.ramulator.is_file():
        raise SystemExit(
            f"environment setup failed: Ramulator binary was not built: {args.ramulator}"
        )

    probe_run = subprocess.run(
        [str(args.ramulator)],
        capture_output=True,
        text=True,
    )
    help_text = probe_run.stdout + probe_run.stderr
    if "Ramulator" not in help_text:
        raise SystemExit(
            "environment setup failed: Ramulator executable sanity check failed"
        )

    print(f"{args.backend.capitalize()} setup complete")
    print(f"  repository: {args.repo_root.parent}")
    print(f"  workspace:  {args.workspace_root}")
    print(f"  traces:     55/55 in {args.trace_dir}")
    print(f"  simulator:  {args.ramulator}")


if __name__ == "__main__":
    main()
