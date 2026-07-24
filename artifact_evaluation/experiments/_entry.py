"""Shared entry point for one experiment-class launcher."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def run(experiment_class: str) -> None:
    driver = Path(__file__).resolve().parent.parent / "run_experiments.py"
    subprocess.run(
        [sys.executable, str(driver), "--classes", experiment_class, *sys.argv[1:]],
        check=True,
    )
