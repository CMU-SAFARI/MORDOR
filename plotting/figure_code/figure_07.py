import re
from pathlib import Path


NUM_CORES = 8
CPU_FREQUENCY_HZ = 2.0e9
CPU_POWER_W = 500.0

# Section 7.2 evaluates six PROQs, one for each channel on the reference CPU.
DEFAULT_NUM_CHANNELS = 6
CAM_STATIC_POWER_PER_CHANNEL_MW = 2.267
CAM_DYNAMIC_POWER_PER_CHANNEL_MW = 24.190

MECHANISMS = ["Hydra", "PARA", "comet", "DAPPER", "graphene", "abacus"]
MECHANISM_LABELS = {
    "Hydra": "Hydra",
    "PARA": "PARA",
    "comet": "CoMeT",
    "DAPPER": "DAPPER",
    "graphene": "Graphene",
    "abacus": "ABACuS",
}

CORE_CYCLE_RE = re.compile(r"cycles_recorded_core_(\d+):\s*([0-9]+)")


def trace_name(path: Path) -> str:
    return path.name.removesuffix("_output.yaml")


def average_core_cycles(path: Path) -> float:
    cycles_by_core = {
        int(match.group(1)): int(match.group(2))
        for match in CORE_CYCLE_RE.finditer(path.read_text(errors="replace"))
    }
    missing = set(range(NUM_CORES)) - cycles_by_core.keys()
    if missing:
        raise ValueError(f"{path}: missing cycles for cores {sorted(missing)}")
    return sum(cycles_by_core[core] for core in range(NUM_CORES)) / NUM_CORES


def load_variant(
    base_dir: Path,
    mechanism: str,
) -> dict[str, float]:
    result_dir = base_dir / mechanism
    if not result_dir.is_dir():
        print(f"[warning] Missing directory: {result_dir}")
        return {}

    values = {}
    for path in sorted(result_dir.glob("*_output.yaml")):
        try:
            trace = trace_name(path)
            if trace in PAPER_TRACE_SET:
                values[trace] = average_core_cycles(path)
        except ValueError as error:
            print(f"[warning] {error}")
    return values


def build_summary(repo_root: Path, num_channels: int) -> list[dict[str, float | str]]:
    if num_channels < 1:
        raise ValueError("num_channels must be at least 1")

    cam_power_per_channel_w = (
        CAM_STATIC_POWER_PER_CHANNEL_MW + CAM_DYNAMIC_POWER_PER_CHANNEL_MW
    ) * 1e-3
    cam_hardware_power_w = num_channels * cam_power_per_channel_w

    rows = []
    for mechanism in MECHANISMS:
        priority = load_variant(
            repo_root / "main" / "priority", mechanism
        )
        mordor = load_variant(
            repo_root / "main" / "mordor", mechanism
        )
        common_traces = require_paper_trace_cohort(
            f"Figure 7 / {MECHANISM_LABELS[mechanism]}",
            {"Priority": priority, "MORDOR": mordor},
        )

        avg_priority_cycles = sum(priority[t] for t in common_traces) / len(
            common_traces
        )
        avg_mordor_cycles = sum(mordor[t] for t in common_traces) / len(
            common_traces
        )
        baseline_energy_j = (
            CPU_POWER_W * avg_priority_cycles / CPU_FREQUENCY_HZ
        )
        mordor_energy_j = (
            (CPU_POWER_W + cam_hardware_power_w)
            * avg_mordor_cycles
            / CPU_FREQUENCY_HZ
        )

        rows.append(
            {
                "Mechanism": mechanism,
                "NumPairedTraces": len(common_traces),
                "AvgCycles_Priority": avg_priority_cycles,
                "AvgCycles_MORDOR": avg_mordor_cycles,
                "NumChannels": num_channels,
                "CamPowerPerChannel_W": cam_power_per_channel_w,
                "CamHardwarePower_W": cam_hardware_power_w,
                "BaselineEnergy_J": baseline_energy_j,
                "CpuPlusCamEnergy_J": mordor_energy_j,
            }
        )
    return rows


energy_rows = build_summary(BUNDLE_ROOT, DEFAULT_NUM_CHANNELS)
x = list(range(len(energy_rows)))
width = 0.36
labels = [MECHANISM_LABELS[str(row["Mechanism"])] for row in energy_rows]
priority_energy = [float(row["BaselineEnergy_J"]) for row in energy_rows]
mordor_energy = [float(row["CpuPlusCamEnergy_J"]) for row in energy_rows]
fig, ax = plt.subplots(figsize=(3.4, 2.2), constrained_layout=True)
ax.set_facecolor("#f4f4f4")
ax.bar([value - width / 2 for value in x], priority_energy, width,
       label="Priority", color="#858585", edgecolor="black", linewidth=0.4)
ax.bar([value + width / 2 for value in x], mordor_energy, width,
       label="MORDOR", color="#f28e3b", edgecolor="black", linewidth=0.4)
ax.set_ylabel("Estimated Processor-Side\nEnergy [J]")
ax.set_xticks(x, labels, rotation=25, ha="right", rotation_mode="anchor")
ax.legend(frameon=False, ncol=2, loc="upper right",
          handlelength=1.2, columnspacing=0.8)
ax.grid(axis="y", color="#c9c9c9", linestyle="-", linewidth=0.3)
ax.set_axisbelow(True)
ax.spines[["top", "right"]].set_visible(False)
plt.show()
