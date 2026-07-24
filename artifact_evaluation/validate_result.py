#!/usr/bin/env python3
"""Validate one completed Ramulator result before it becomes a final output."""

from __future__ import annotations

import argparse
import math
import re
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    parser.add_argument("--cores", type=int, default=8)
    parser.add_argument("--latency", action="store_true")
    args = parser.parse_args()

    if not args.result.is_file() or args.result.stat().st_size == 0:
        raise SystemExit(f"invalid result: empty or missing: {args.result}")
    text = args.result.read_text(errors="replace")
    if args.latency:
        values = [
            int(value)
            for value in re.findall(r"^\[Lat ?\((?:RD|PRO)\): ([0-9]+)\]$", text, re.MULTILINE)
        ]
        if not values:
            raise SystemExit(f"invalid latency result: no RD/PRO samples: {args.result}")
        return

    keys = [
        "memory_system_cycles",
        "total_energy",
        *(f"cycles_recorded_core_{core}" for core in range(args.cores)),
    ]
    missing = [
        key for key in keys
        if re.search(rf"^\s*{re.escape(key)}\s*:", text, re.MULTILINE) is None
    ]
    if missing:
        raise SystemExit(f"invalid result {args.result}: missing {', '.join(missing)}")
    energy = re.search(r"^\s*total_energy:\s*([-+0-9.eE]+)\s*$", text, re.MULTILINE)
    if energy is None or not math.isfinite(float(energy.group(1))):
        raise SystemExit(f"invalid result {args.result}: total_energy is not finite")


if __name__ == "__main__":
    main()
