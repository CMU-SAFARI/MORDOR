"""Shared definitions for the MORDOR reproduction workflow."""

from __future__ import annotations

import os
from pathlib import Path


MECHANISMS = ["Hydra", "PARA", "comet", "DAPPER", "graphene", "abacus"]
TRACES = [
    "random_10.trace", "stream_10.trace", "401.bzip2", "403.gcc",
    "429.mcf", "435.gromacs", "436.cactusADM",
    "437.leslie3d", "444.namd", "445.gobmk", "447.dealII",
    "450.soplex", "456.hmmer", "458.sjeng", "459.GemsFDTD",
    "462.libquantum", "464.h264ref", "470.lbm", "471.omnetpp",
    "473.astar", "481.wrf", "482.sphinx3", "483.xalancbmk",
    "500.perlbench", "502.gcc", "505.mcf", "507.cactuBSSN",
    "508.namd", "510.parest", "511.povray", "520.omnetpp",
    "523.xalancbmk", "525.x264", "526.blender", "531.deepsjeng",
    "538.imagick", "541.leela", "544.nab", "549.fotonik3d",
    "557.xz", "grep_map0", "h264_encode", "jp2_encode", "tpcc64",
    "tpch17", "tpch2", "tpch6", "wc_8443", "wc_map0",
    "ycsb_abgsave", "ycsb_aserver", "ycsb_bserver", "ycsb_cserver",
    "ycsb_dserver", "ycsb_eserver",
]

# The paper's latency figure uses only 429.mcf.  Keep this cohort separate from
# TRACES so the aggregate plots always use exactly the canonical 55 traces.
LATENCY_TRACES = ["429.mcf"]

# Blast radius is modeled directly at BRC=1 for comparison with prior work.
BLAST_BRC = 1
BLAST_RADII = [1, 2, 8]

if len(TRACES) != 55 or len(set(TRACES)) != 55:
    raise RuntimeError("TRACES must contain exactly 55 unique paper traces")

EXPERIMENT_CLASSES = [
    "main", "multi-prt", "latency", "bank-count", "blast-radius", "scheduling",
]


def resolve_path(value: str | Path, base: Path) -> Path:
    path = Path(os.path.expandvars(str(value))).expanduser()
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parent.parent / "ramulator"
