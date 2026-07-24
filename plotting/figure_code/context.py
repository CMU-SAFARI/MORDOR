from pathlib import Path
import os

# Canonical workload cohort used by every paper-result collector below.
# Figure 7 intentionally selects the top 25 from this cohort, and Figure 12
# shows its designated single-trace latency case (429.mcf).
PAPER_TRACES = [
    "random_10.trace", "stream_10.trace", "401.bzip2", "403.gcc",
    "429.mcf", "435.gromacs", "436.cactusADM", "437.leslie3d",
    "444.namd", "445.gobmk", "447.dealII", "450.soplex",
    "456.hmmer", "458.sjeng", "459.GemsFDTD", "462.libquantum",
    "464.h264ref", "470.lbm", "471.omnetpp", "473.astar",
    "481.wrf", "482.sphinx3", "483.xalancbmk", "500.perlbench",
    "502.gcc", "505.mcf", "507.cactuBSSN", "508.namd",
    "510.parest", "511.povray", "520.omnetpp", "523.xalancbmk",
    "525.x264", "526.blender", "531.deepsjeng", "538.imagick",
    "541.leela", "544.nab", "549.fotonik3d", "557.xz",
    "grep_map0", "h264_encode", "jp2_encode", "tpcc64",
    "tpch17", "tpch2", "tpch6", "wc_8443", "wc_map0",
    "ycsb_abgsave", "ycsb_aserver", "ycsb_bserver",
    "ycsb_cserver", "ycsb_dserver", "ycsb_eserver",
]
PAPER_TRACE_SET = frozenset(PAPER_TRACES)
assert len(PAPER_TRACES) == len(PAPER_TRACE_SET) == 55


def require_paper_trace_cohort(context, datasets):
    """Require every named result mapping/set to contain the canonical 55 traces."""
    missing = {}
    for label, values in datasets.items():
        available = set(values) & PAPER_TRACE_SET
        absent = [trace for trace in PAPER_TRACES if trace not in available]
        if absent:
            missing[label] = absent
    if missing:
        details = "\n".join(
            f"  {label} ({len(traces)} missing): {', '.join(traces)}"
            for label, traces in missing.items()
        )
        raise ValueError(
            f"{context} must use all {len(PAPER_TRACES)} PAPER_TRACES; "
            f"incomplete inputs:\n{details}"
        )
    return list(PAPER_TRACES)


def available_paper_trace_cohort(context, datasets):
    """Return one shared available cohort and report all incomplete inputs."""
    available_by_dataset = {
        label: set(values) & PAPER_TRACE_SET for label, values in datasets.items()
    }
    common = set.intersection(*available_by_dataset.values())
    included = [trace for trace in PAPER_TRACES if trace in common]
    excluded = [trace for trace in PAPER_TRACES if trace not in common]
    print(f"{context}: plotting {len(included)}/{len(PAPER_TRACES)} shared traces.")
    if excluded:
        print("  Excluded from every bar: " + ", ".join(excluded))
        print("  Incomplete inputs:")
        for label, available in available_by_dataset.items():
            missing = [trace for trace in PAPER_TRACES if trace not in available]
            if missing:
                print(f"    {label} ({len(missing)} missing): {', '.join(missing)}")
    if not included:
        raise ValueError(f"{context} has no shared PAPER_TRACES to plot")
    return included


def find_bundle_root():
    start = Path.cwd().resolve()
    for candidate in [start, *start.parents]:
        if (candidate / "main" / "priority").is_dir() and (candidate / "baseline" / "no_mitigation").is_dir():
            return candidate
    raise FileNotFoundError("Could not locate the MORDOR paper-results bundle")


BUNDLE_ROOT = find_bundle_root()
os.chdir(BUNDLE_ROOT)
print(f"Bundle root: {BUNDLE_ROOT}")
