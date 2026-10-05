#!/usr/bin/env python3
"""Render the paper's hardware-overhead table from raw 45 nm measurements."""

import os
import sys


POWER_SCALE = float(os.environ.get("SC_POW", "2.438"))
AREA_SCALE = float(os.environ.get("SC_AREA", "12.5"))
DELAY_SCALE = float(os.environ.get("SC_DLY", "1.35"))
CHANNELS = int(os.environ.get("NCHAN", "6"))
CPU_AREA_MM2 = float(os.environ.get("CPU_AREA_MM2", "698"))
CAM_KB = {32: 0.72, 48: 1.08, 64: 1.44, 78: 1.74}


def read_rows(source):
    rows = []
    for line in source:
        fields = line.split()
        if len(fields) != 6 or not fields[1].isdigit():
            continue
        entries = int(fields[1])
        try:
            static_mw, dynamic_mw, area_um2, latency_ns = map(float, fields[2:])
        except ValueError:
            continue
        rows.append((entries, static_mw, dynamic_mw, area_um2, latency_ns))
    return rows


def main():
    source = open(sys.argv[1]) if len(sys.argv) > 1 else sys.stdin
    rows = read_rows(source)
    if not rows:
        raise SystemExit("render_table1: no valid rows")

    print("PROQ entries  PROQ CAM KB  Area mm2  % CPU   Static mW  Dyn. mW  Access lat. ns")
    for entries, static_mw, dynamic_mw, area_um2, latency_ns in rows:
        if entries not in CAM_KB:
            raise SystemExit(f"render_table1: unsupported PROQ size {entries}")
        area_mm2 = area_um2 / AREA_SCALE * CHANNELS / 1_000_000
        cpu_percent = area_mm2 / CPU_AREA_MM2 * 100
        static_scaled = static_mw / POWER_SCALE * CHANNELS
        dynamic_scaled = dynamic_mw / POWER_SCALE * CHANNELS
        latency_scaled = latency_ns / DELAY_SCALE
        print(
            f"{entries:<13} {CAM_KB[entries]:<12.2f} {area_mm2:<9.3f} "
            f"{cpu_percent:<7.3f} {static_scaled:<10.2f} "
            f"{dynamic_scaled:<8.2f} {latency_scaled:.2f}"
        )


if __name__ == "__main__":
    main()
