PLOT_FONT_SIZE = 14

from collections import Counter
from pathlib import Path
import math
import re

import matplotlib.pyplot as plt
import numpy as np

# Canonical latency results use semantic scheduler and mechanism directories.
RESULTS_ROOT = Path("latency")

# Exact trace names to include. Use [] to include every discovered trace.
SELECTED_TRACES = ["429.mcf"]
assert set(SELECTED_TRACES) <= PAPER_TRACE_SET
PERCENTILE_POINTS = 1001

MECHANISMS = ["Hydra", "PARA", "graphene", "DAPPER", "comet", "abacus"]
MECHANISM_LABELS = {"Hydra": "Hydra", "PARA": "Para", "graphene": "Graphene",
                    "DAPPER": "DAPPER", "comet": "CoMeT", "abacus": "ABACuS"}
SCHEDULERS = ["mordor", "priority"]
CURVE_ORDER = [("mordor", "RD"), ("mordor", "PRO"),
               ("priority", "RD"), ("priority", "PRO")]
CURVE_LABELS = {("mordor", "RD"): "MORDOR RD",
                ("mordor", "PRO"): "MORDOR PRO",
                ("priority", "RD"): "Priority RD",
                ("priority", "PRO"): "Priority PRO"}
CURVE_STYLES = {("mordor", "RD"): dict(color="#f28e3b", linestyle="-", linewidth=1.9),
                ("mordor", "PRO"): dict(color="#f28e3b", linestyle="--", linewidth=1.9),
                ("priority", "RD"): dict(color="#666666", linestyle="-", linewidth=1.9),
                ("priority", "PRO"): dict(color="#666666", linestyle="--", linewidth=1.9)}
# Neutral context for the body, with orange reserved for the latency tail.
PERCENTILE_REGIONS = [
    (0, 50, "#eeeeee"),
    (50, 90, "#bdbdbd"),
    (90, 100, "#f28e3b"),
]
PLOT_BACKGROUND = "#f7f7f7"
GRID_COLOR = "#c9c9c9"

LINE_RE = re.compile(r"^\[Lat ?\((?P<kind>RD|PRO)\):\s*(?P<latency>\d+)\]$")
CANONICAL_MECHANISMS = {name.lower(): name for name in MECHANISMS}

discovered_files = []
unexpected_files = []
for path in sorted(RESULTS_ROOT.glob("*/*/*_latency.txt")):
    scheduler = path.parent.parent.name
    mechanism = CANONICAL_MECHANISMS.get(path.parent.name.lower())
    trace = path.name.removesuffix("_latency.txt")
    if scheduler not in SCHEDULERS or mechanism is None:
        unexpected_files.append(path)
        continue
    if trace not in PAPER_TRACE_SET or (SELECTED_TRACES and trace not in SELECTED_TRACES):
        continue
    discovered_files.append({"path": path, "mechanism": mechanism,
                             "queue": scheduler, "trace": trace})

histograms = {}
file_counts = {}
invalid_lines = []
for item in discovered_files:
    per_file_counts = Counter()
    with item["path"].open(errors="replace") as stream:
        for line_number, line in enumerate(stream, 1):
            match = LINE_RE.fullmatch(line.rstrip("\n"))
            if not match:
                if line.strip():
                    invalid_lines.append((item["path"], line_number, line.rstrip()))
                continue
            kind, latency = match.group("kind"), int(match.group("latency"))
            key = (item["mechanism"], item["queue"], kind)
            histograms.setdefault(key, Counter())[latency] += 1
            per_file_counts[kind] += 1
    file_counts[str(item["path"])] = dict(per_file_counts)

print(f"Loaded {len(discovered_files)} latency files from {RESULTS_ROOT}.")
print("Selected traces:", ", ".join(SELECTED_TRACES) if SELECTED_TRACES else "all discovered traces")
if unexpected_files:
    print(f"Ignored {len(unexpected_files)} files with unexpected names.")
if invalid_lines:
    print(f"Ignored {len(invalid_lines)} non-latency lines; first five:")
    for path, line_number, line in invalid_lines[:5]:
        print(f"  {path}:{line_number}: {line}")

print("\nSample counts by mechanism and curve:")
for mechanism in MECHANISMS:
    counts = []
    for queue, kind in CURVE_ORDER:
        counts.append(f"{CURVE_LABELS[(queue, kind)]}={sum(histograms.get((mechanism, queue, kind), {}).values()):,}")
    print(f"{MECHANISM_LABELS[mechanism]:<10} " + ", ".join(counts))


def percentile_curve(histogram, percentile_points=PERCENTILE_POINTS):
    if not histogram:
        return np.array([]), np.array([])
    latencies = np.array(sorted(histogram), dtype=np.int64)
    counts = np.array([histogram[value] for value in latencies], dtype=np.int64)
    cumulative = np.cumsum(counts)
    total = int(cumulative[-1])
    percentiles = np.linspace(0.0, 100.0, percentile_points)
    ranks = np.maximum(1, np.ceil(percentiles * total / 100.0).astype(np.int64))
    values = latencies[np.searchsorted(cumulative, ranks, side="left")]
    return percentiles, values

plt.rcParams.update({"font.weight": "normal", "axes.labelweight": "normal",
                     "axes.titleweight": "normal", "legend.frameon": True})
LATENCY_FONT_SIZE = PLOT_FONT_SIZE + 1
fig, axes = plt.subplots(2, 3, figsize=(9.0, 5.2), constrained_layout=True)
legend_handles = {}

for ax, mechanism in zip(axes.ravel(), MECHANISMS):
    plotted = 0
    for queue, kind in CURVE_ORDER:
        histogram = histograms.get((mechanism, queue, kind), Counter())
        percentiles, values = percentile_curve(histogram)
        if not len(values):
            continue
        line, = ax.plot(percentiles, values, label=CURVE_LABELS[(queue, kind)],
                        **CURVE_STYLES[(queue, kind)])
        legend_handles[(queue, kind)] = line
        plotted += 1
    ax.set_title(MECHANISM_LABELS[mechanism], fontsize=LATENCY_FONT_SIZE)
    ax.set_xlim(-1, 101)
    ax.set_xticks([0, 50, 100])
    ax.tick_params(axis="both", labelsize=LATENCY_FONT_SIZE)
    for region_start, region_end, region_color in PERCENTILE_REGIONS:
        ax.axvspan(region_start, region_end, color=region_color, alpha=0.12,
                   linewidth=0, zorder=0)
    ax.set_facecolor(PLOT_BACKGROUND)
    ax.grid(axis="both", color=GRID_COLOR, linewidth=0.65, alpha=0.6)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)
    if not plotted:
        ax.text(0.5, 0.5, "No completed data", ha="center", va="center",
                transform=ax.transAxes, color="#666666", fontsize=10)

for ax in axes[:, 0]:
    ax.set_ylabel("Latency (cycles)", fontsize=LATENCY_FONT_SIZE)
for ax in axes[-1, :]:
    ax.set_xlabel("Percentile (%)", fontsize=LATENCY_FONT_SIZE)

handles = [legend_handles[key] for key in CURVE_ORDER if key in legend_handles]
labels = [CURVE_LABELS[key] for key in CURVE_ORDER if key in legend_handles]
if handles:
    legend = axes[0, 0].legend(handles, labels, loc="upper left", fontsize=8,
                               frameon=True, borderpad=0.35, handlelength=2.2)
    legend.get_frame().set_facecolor("#f4f4f4")
    legend.get_frame().set_edgecolor(GRID_COLOR)

plt.show()
