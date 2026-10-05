#!/usr/bin/env python3
"""Single entry point for building and running MORDOR reproduction experiments."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from common import repo_root_from_script


SCRIPT_DIR = Path(__file__).resolve().parent


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--build-jobs",
        type=positive_int,
        help="maximum number of concurrent compiler jobs",
    )
    parser.add_argument("action", choices=["build", "experiments", "all"])
    parser.add_argument("arguments", nargs=argparse.REMAINDER,
                        help="arguments forwarded to the selected stage")
    args = parser.parse_args()
    forwarded = args.arguments
    if forwarded and forwarded[0] == "--":
        forwarded = forwarded[1:]

    if args.action in ("build", "all"):
        repo = repo_root_from_script()
        subprocess.run(["cmake", "-S", str(repo), "-B", str(repo / "build")], check=True)
        build_command = ["cmake", "--build", str(repo / "build"), "-j"]
        if args.build_jobs is not None:
            build_command.append(str(args.build_jobs))
        subprocess.run(build_command, check=True)
    if args.action in ("experiments", "all"):
        subprocess.run([sys.executable, str(SCRIPT_DIR / "run_experiments.py"), *forwarded], check=True)


if __name__ == "__main__":
    main()
