"""Figure 14: sensitivity to targeted-DRFM address-setup latency."""

import numpy as np

DRFM_SETUP_ROOT = Path("drfm_address_setup/mordor")
figure14_metrics = {}
for mechanism in MECHANISMS:
    values = {}
    directory = DRFM_SETUP_ROOT / mechanism
    for path in sorted(directory.glob("*_output.yaml")):
        trace = path.name.removesuffix("_output.yaml")
        metrics = read_scheduler_comparison_metrics(path, mechanism)
        if metrics is not None:
            values[trace] = metrics
    figure14_metrics[mechanism] = values

required = {"No mitigation": scheduler_comparison_baselines}
for mechanism in MECHANISMS:
    required[f"{MECHANISM_LABELS[mechanism]} Priority"] = scheduler_comparison_metrics[(mechanism, "priority")]
    required[f"{MECHANISM_LABELS[mechanism]} MORDOR"] = scheduler_comparison_metrics[(mechanism, "mordor")]
    required[f"{MECHANISM_LABELS[mechanism]} MORDOR + setup"] = figure14_metrics[mechanism]
traces = require_paper_trace_cohort("Figure 14", required)

variants = ("priority", "mordor", "setup")
labels = {"priority": "Priority", "mordor": "MORDOR",
          "setup": "MORDOR\n+47.5 ns"}
colors = {"priority": "#858585", "mordor": "#f28e3b", "setup": "#d64b3c"}
grouped = {}
for mechanism in MECHANISMS:
    sources = {
        "priority": scheduler_comparison_metrics[(mechanism, "priority")],
        "mordor": scheduler_comparison_metrics[(mechanism, "mordor")],
        "setup": figure14_metrics[mechanism],
    }
    for variant in variants:
        for metric in ("cycles", "energy"):
            values = [100.0 * (sources[variant][trace][metric]
                               / scheduler_comparison_baselines[trace][metric] - 1.0)
                      for trace in traces]
            grouped[(mechanism, variant, metric)] = (
                statistics.fmean(values),
                statistics.stdev(values) / len(values) ** 0.5,
            )

fig, axes = plt.subplots(1, 2, figsize=(9.0, 3.45), constrained_layout=True)
x = np.arange(len(MECHANISMS))
width = 0.25
for ax, (metric, ylabel) in zip(axes, (
    ("cycles", "Performance Overhead [%]\nover no RowHammer Mitigation"),
    ("energy", "DRAM Energy Overhead [%]\nover no RowHammer Mitigation"),
)):
    for index, variant in enumerate(variants):
        means = [grouped[(m, variant, metric)][0] for m in MECHANISMS]
        errors = [grouped[(m, variant, metric)][1] for m in MECHANISMS]
        ax.bar(x + (index - 1) * width, means, width, yerr=errors, capsize=2.2,
               color=colors[variant], edgecolor="#111111", linewidth=0.6,
               error_kw={"elinewidth": 0.7})
    ax.set_ylabel(ylabel)
    ax.set_xticks(x, [MECHANISM_LABELS[m] for m in MECHANISMS],
                  rotation=28, ha="right")
    ax.axhline(0, color="#111111", linewidth=0.7)
    ax.grid(axis="y", color=GRID_COLOR, linewidth=0.65, alpha=0.7)
    ax.set_axisbelow(True)
handles = [Patch(facecolor=colors[v], edgecolor="#111111", label=labels[v])
           for v in variants]
fig.legend(handles=handles, ncols=3, loc="upper center",
           bbox_to_anchor=(0.5, 1.10), frameon=True)
plt.show()
