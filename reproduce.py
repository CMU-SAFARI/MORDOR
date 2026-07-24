#!/usr/bin/env python3
"""Convenience entry point for the standalone MORDOR reproduction artifact."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parent / "artifact_evaluation" / "reproduce.py"
sys.path.insert(0, str(SCRIPT.parent))
runpy.run_path(str(SCRIPT), run_name="__main__")
