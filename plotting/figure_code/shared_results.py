from pathlib import Path
import math
import re
import statistics

import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.ticker import MaxNLocator
import yaml

PRIORITY_RESULTS_DIR = Path("main/priority")
MORDOR_RESULTS_DIR = Path("main/mordor")
INSECURE_RESULTS_DIR = Path("main/insecure")
NO_MITIGATION_RESULTS_DIR = Path("baseline/no_mitigation")

MECHANISMS = ["Hydra", "PARA", "comet", "DAPPER", "graphene", "abacus"]
MECHANISM_LABELS = {"Hydra": "Hydra", "PARA": "PARA", "comet": "CoMeT",
                    "DAPPER": "DAPPER", "graphene": "Graphene", "abacus": "ABACuS"}
# Neutral mechanism palette; orange is reserved for data explicitly labeled MORDOR.
MECHANISM_COLORS = {"abacus": "#404040", "comet": "#666666", "DAPPER": "#858585",
                    "graphene": "#a3a3a3", "Hydra": "#c2c2c2", "PARA": "#dedede"}
VARIANTS = ["priority", "mordor", "insecure"]
VARIANT_LABELS = {"priority": "Priority", "mordor": "MORDOR", "insecure": "Insecure"}
# Greyscale comparisons with orange reserved exclusively for MORDOR.
VARIANT_COLORS = {"priority": "#858585", "mordor": "#f28e3b", "insecure": "#c9c9c9"}
PLOT_BACKGROUND_COLOR = "#f7f7f7"
GRID_COLOR = "#c9c9c9"
PLOT_FONT_SIZE = 14
CORE_CYCLE_KEYS = [f"cycles_recorded_core_{core}" for core in range(8)]
RESULT_FILE_RE = re.compile(r"^(?P<trace>.+)_output\.yaml$")

def read_eight_core_cycles(path):
    lines = path.read_text(errors="replace").splitlines()
    start = next((index for index, line in enumerate(lines) if line.strip() == "Frontend:"), None)
    if start is None:
        return None
    try:
        data = yaml.safe_load("\n".join(lines[start:]) + "\n")
        cycles = [float(data["Frontend"][key]) for key in CORE_CYCLE_KEYS]
    except (KeyError, TypeError, ValueError, yaml.YAMLError):
        return None
    if len(cycles) != 8 or not all(math.isfinite(value) for value in cycles):
        return None
    return statistics.fmean(cycles)

def collect_variant(directory):
    values = {}
    for path in sorted(directory.glob("*_output.yaml")):
        match = RESULT_FILE_RE.match(path.name)
        if match is None:
            continue
        cycles = read_eight_core_cycles(path)
        if cycles is not None:
            values[match.group("trace")] = cycles
    return values

cycle_values = {}
for mechanism in MECHANISMS:
    variant_directories = {
        "priority": PRIORITY_RESULTS_DIR / mechanism,
        "mordor": MORDOR_RESULTS_DIR / mechanism,
        "insecure": INSECURE_RESULTS_DIR / mechanism,
    }
    for variant, directory in variant_directories.items():
        cycle_values[(mechanism, variant)] = collect_variant(directory)

baseline_values = {}
for path in sorted(NO_MITIGATION_RESULTS_DIR.glob("*_output.yaml")):
    cycles = read_eight_core_cycles(path)
    if cycles is not None:
        baseline_values[path.name.removesuffix("_output.yaml")] = cycles

required_cycle_traces = {"No-mitigation baseline": baseline_values}
required_cycle_traces.update({
    f"{MECHANISM_LABELS[mechanism]} / {VARIANT_LABELS[variant]}":
        cycle_values[(mechanism, variant)]
    for mechanism in MECHANISMS for variant in VARIANTS
})
shared_cycle_traces = require_paper_trace_cohort(
    "Shared multicore results", required_cycle_traces
)
traces_by_mechanism = {mechanism: shared_cycle_traces for mechanism in MECHANISMS}
PLOTTED_MECHANISMS = list(MECHANISMS)

overheads = {}
for mechanism in PLOTTED_MECHANISMS:
    for variant in VARIANTS:
        overheads[(mechanism, variant)] = [
            100.0 * (cycle_values[(mechanism, variant)][trace] / baseline_values[trace] - 1.0)
            for trace in traces_by_mechanism[mechanism]
        ]

print("Result sources:")
print(f"  Priority: {PRIORITY_RESULTS_DIR}")
print(f"  MORDOR:   {MORDOR_RESULTS_DIR}")
print(f"  Insecure: {INSECURE_RESULTS_DIR}")
print(f"Complete traces: {len(shared_cycle_traces)}")

plt.rcParams.update({"font.size": PLOT_FONT_SIZE, "font.weight": "normal",
                     "axes.labelsize": PLOT_FONT_SIZE, "axes.labelweight": "normal",
                     "axes.titlesize": PLOT_FONT_SIZE, "axes.titleweight": "normal",
                     "xtick.labelsize": PLOT_FONT_SIZE,
                     "ytick.labelsize": PLOT_FONT_SIZE,
                     "legend.fontsize": PLOT_FONT_SIZE,
                     "legend.title_fontsize": PLOT_FONT_SIZE,
                     "figure.titlesize": PLOT_FONT_SIZE})

PROQ_LENGTH_DIVISORS = {mechanism: (32.0 if mechanism == "abacus" else 1.0)
                          for mechanism in MECHANISMS}


SCHEDULER_COMPARISON_SCHEDULERS = ["priority", "mordor"]
SCHEDULER_COMPARISON_SCHEDULER_LABELS = {"priority": "Priority", "mordor": "MORDOR"}
SCHEDULER_COMPARISON_SCHEDULER_COLORS = {"priority": VARIANT_COLORS["priority"],
                         "mordor": VARIANT_COLORS["mordor"]}
SCHEDULER_COMPARISON_RESULT_DIRS = {"priority": PRIORITY_RESULTS_DIR, "mordor": MORDOR_RESULTS_DIR}

def scheduler_comparison_repeated_values(text, key, nan_as_zero=False):
    values = []
    pattern = re.compile(rf"^\s+{re.escape(key)}:\s+([^\s#]+)", re.MULTILINE)
    for match in pattern.finditer(text):
        raw = match.group(1)
        if nan_as_zero and raw.lower() in {".nan", "nan", "+.nan", "-.nan"}:
            values.append(0.0)
            continue
        try:
            value = float(raw)
        except ValueError:
            continue
        if math.isnan(value) and nan_as_zero:
            values.append(0.0)
        elif math.isfinite(value):
            values.append(value)
    return values

def read_scheduler_comparison_metrics(path, mechanism):
    text = path.read_text(errors="replace")
    lines = text.splitlines()
    start = next((index for index, line in enumerate(lines) if line.strip() == "Frontend:"), None)
    if start is None:
        return None
    try:
        data = yaml.safe_load("\n".join(lines[start:]) + "\n")
        cycles = [float(data["Frontend"][key]) for key in CORE_CYCLE_KEYS]
        energy = float(data["MemorySystem"]["DRAM"]["total_energy"])
    except (KeyError, TypeError, ValueError, yaml.YAMLError):
        return None
    if not all(math.isfinite(value) for value in cycles + [energy]):
        return None
    divisor = PROQ_LENGTH_DIVISORS[mechanism]
    proq_adds = scheduler_comparison_repeated_values(text, "num_PROQ_adds")
    avg_proq = scheduler_comparison_repeated_values(text, "avg_PROQ_size")
    max_proq = scheduler_comparison_repeated_values(text, "max_PROQ_size")
    avg_delayed = scheduler_comparison_repeated_values(
        text, "avg_num_demand_delayed_by_PRO", nan_as_zero=True
    )
    max_delayed = scheduler_comparison_repeated_values(
        text, "max_num_demand_delayed_by_PRO"
    )
    avg_read_delayed = scheduler_comparison_repeated_values(
        text, "avg_num_read_demand_delayed_by_PRO", nan_as_zero=True
    )
    max_read_delayed = scheduler_comparison_repeated_values(
        text, "max_num_read_demand_delayed_by_PRO"
    )
    avg_write_delayed = scheduler_comparison_repeated_values(
        text, "avg_num_write_demand_delayed_by_PRO", nan_as_zero=True
    )
    max_write_delayed = scheduler_comparison_repeated_values(
        text, "max_num_write_demand_delayed_by_PRO"
    )
    counted_pros = scheduler_comparison_repeated_values(text, "num_counted_PROs")
    total_counted_pros = sum(counted_pros)

    def weighted_channel_average(values):
        if values and len(values) == len(counted_pros) and total_counted_pros > 0:
            return sum(value * count for value, count in zip(values, counted_pros)) / total_counted_pros
        if values and total_counted_pros == 0:
            return 0.0
        return None

    return {
        "cycles": statistics.fmean(cycles),
        "energy": energy,
        "num_proq_adds": sum(proq_adds) / divisor if proq_adds else None,
        "avg_proq_size": statistics.fmean(avg_proq) / divisor if avg_proq else None,
        "max_proq_size": max(max_proq) / divisor if max_proq else None,
        "avg_delayed": weighted_channel_average(avg_delayed),
        "max_delayed": max(max_delayed) if max_delayed else None,
        "read_avg_delayed": weighted_channel_average(avg_read_delayed),
        "read_max_delayed": max(max_read_delayed) if max_read_delayed else None,
        "write_avg_delayed": weighted_channel_average(avg_write_delayed),
        "write_max_delayed": max(max_write_delayed) if max_write_delayed else None,
    }

def collect_scheduler_comparison_metrics(directory, mechanism):
    results = {}
    for path in sorted(directory.glob("*_output.yaml")):
        match = RESULT_FILE_RE.match(path.name)
        if match is None:
            continue
        metrics = read_scheduler_comparison_metrics(path, mechanism)
        if metrics is not None:
            results[match.group("trace")] = metrics
    return results

scheduler_comparison_metrics = {}
for mechanism in MECHANISMS:
    for scheduler in SCHEDULER_COMPARISON_SCHEDULERS:
        directory = SCHEDULER_COMPARISON_RESULT_DIRS[scheduler] / mechanism
        scheduler_comparison_metrics[(mechanism, scheduler)] = collect_scheduler_comparison_metrics(directory, mechanism)

def read_scheduler_comparison_baseline(path):
    text = path.read_text(errors="replace")
    lines = text.splitlines()
    start = next((index for index, line in enumerate(lines) if line.strip() == "Frontend:"), None)
    if start is None:
        return None
    try:
        data = yaml.safe_load("\n".join(lines[start:]) + "\n")
        cycles = [float(data["Frontend"][key]) for key in CORE_CYCLE_KEYS]
        energy = float(data["MemorySystem"]["DRAM"]["total_energy"])
    except (KeyError, TypeError, ValueError, yaml.YAMLError):
        return None
    if not all(math.isfinite(value) for value in cycles + [energy]):
        return None
    return {"cycles": statistics.fmean(cycles), "energy": energy}

scheduler_comparison_baselines = {}
for path in sorted(NO_MITIGATION_RESULTS_DIR.glob("*_output.yaml")):
    metrics = read_scheduler_comparison_baseline(path)
    if metrics is not None:
        scheduler_comparison_baselines[path.name.removesuffix("_output.yaml")] = metrics

required_scheduler_comparison_traces = {"No-mitigation baseline": scheduler_comparison_baselines}
required_scheduler_comparison_traces.update({
    f"{MECHANISM_LABELS[mechanism]} / {SCHEDULER_COMPARISON_SCHEDULER_LABELS[scheduler]}":
        scheduler_comparison_metrics[(mechanism, scheduler)]
    for mechanism in MECHANISMS for scheduler in SCHEDULER_COMPARISON_SCHEDULERS
})
shared_scheduler_comparison_traces = require_paper_trace_cohort(
    "Shared scheduler results", required_scheduler_comparison_traces
)

scheduler_comparison_traces_by_mechanism = {}
for mechanism in MECHANISMS:
    scheduler_comparison_traces_by_mechanism[mechanism] = shared_scheduler_comparison_traces
scheduler_comparison_plotted_mechanisms = [mechanism for mechanism in MECHANISMS
                           if scheduler_comparison_traces_by_mechanism[mechanism]]
if not scheduler_comparison_plotted_mechanisms:
    raise ValueError("No complete Priority/MORDOR/baseline comparisons found")

print("Scheduler result sources:")
print(f"  Priority: {SCHEDULER_COMPARISON_RESULT_DIRS['priority']}")
print(f"  MORDOR:   {SCHEDULER_COMPARISON_RESULT_DIRS['mordor']}")
for mechanism in scheduler_comparison_plotted_mechanisms:
    print(f"  {MECHANISM_LABELS[mechanism]}: {len(scheduler_comparison_traces_by_mechanism[mechanism])} paired traces")
