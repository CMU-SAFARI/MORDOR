"""Figure 5: MORDOR speedup and DRAM-energy reduction across NRH."""

import numpy as np

PRTS = (125, 250, 500, 1000)
FIGURE5_COLORS = {
    "Hydra": "#9ecae1", "PARA": "#f4b183", "comet": "#a9d8b8",
    "DAPPER": "#efaaa8", "graphene": "#bdbdbd", "abacus": "#c8b6e8",
}


def figure5_directory(prt, scheduler, mechanism):
    if prt == 125:
        return Path("main") / scheduler / mechanism
    return Path("prt_sweep") / f"prt_{prt}" / scheduler / mechanism


figure5_values = {}
for prt in PRTS:
    for mechanism in MECHANISMS:
        paired = {}
        for scheduler in ("priority", "mordor"):
            directory = figure5_directory(prt, scheduler, mechanism)
            paired[scheduler] = {
                path.name.removesuffix("_output.yaml"):
                    read_scheduler_comparison_metrics(path, mechanism)
                for path in sorted(directory.glob("*_output.yaml"))
            }
        traces = require_paper_trace_cohort(
            f"Figure 5 / NRH {prt} / {MECHANISM_LABELS[mechanism]}", paired
        )
        for metric in ("cycles", "energy"):
            figure5_values[(prt, mechanism, metric)] = [
                100.0 * (paired["priority"][trace][metric]
                         / paired["mordor"][trace][metric] - 1.0)
                for trace in traces
            ]

fig, axes = plt.subplots(1, 2, figsize=(9.2, 3.65), constrained_layout=True)
x = np.arange(len(PRTS), dtype=float)
group_width = 0.90
box_width = group_width / len(MECHANISMS)
upper_limit = 120.0
lower_limits = {"cycles": -2.0, "energy": -12.0}
for ax, (metric, ylabel) in zip(axes, (
    ("cycles", "Speedup over Priority\nScheduling [%]"),
    ("energy", "DRAM Energy\nReduction [%]"),
)):
    for index, mechanism in enumerate(MECHANISMS):
        groups = [figure5_values[(prt, mechanism, metric)] for prt in PRTS]
        offset = (index - (len(MECHANISMS) - 1) / 2) * box_width
        positions = x + offset
        boxes = ax.boxplot(
            groups, positions=positions, widths=box_width * 0.88,
            patch_artist=True, manage_ticks=False, showfliers=True,
            showmeans=True,
            medianprops={"color": "#111111", "linewidth": 0.8},
            meanprops={"marker": "D", "markerfacecolor": "white",
                       "markeredgecolor": "#111111", "markeredgewidth": 0.6,
                       "markersize": 3.0},
            whiskerprops={"color": "#111111", "linewidth": 0.65},
            capprops={"color": "#111111", "linewidth": 0.65},
            flierprops={"marker": "o", "markerfacecolor": "none",
                        "markeredgecolor": FIGURE5_COLORS[mechanism],
                        "markeredgewidth": 0.55, "markersize": 2.3,
                        "alpha": 0.8},
        )
        for box in boxes["boxes"]:
            box.set_facecolor(FIGURE5_COLORS[mechanism])
            box.set_edgecolor("#111111")
            box.set_linewidth(0.65)
        for position, group in zip(positions, groups):
            observed_max = max(group)
            if observed_max > upper_limit:
                ax.text(position, upper_limit - 1.5, f"{observed_max:.0f}",
                        ha="center", va="top", rotation=90, fontsize=8.0,
                        color="#111111", zorder=6,
                        bbox={"facecolor": "white", "edgecolor": "none",
                              "alpha": 0.82, "pad": 0.25})
    ax.axhline(0, color="#111111", linewidth=0.8)
    ax.set_ylabel(ylabel)
    ax.set_xticks(x, [str(prt) for prt in PRTS])
    ax.set_ylim(lower_limits[metric], upper_limit)
    ax.margins(x=0.035)
    ax.yaxis.set_major_locator(MaxNLocator(nbins=5))
    ax.grid(axis="y", color="#d6d6d6", linewidth=0.65, alpha=0.75)
    ax.set_axisbelow(True)
    ax.set_facecolor("white")
fig.supxlabel(r"RowHammer Threshold $N_{\mathrm{RH}}$")
handles = [Patch(facecolor=FIGURE5_COLORS[m], edgecolor="#111111",
                 label=MECHANISM_LABELS[m]) for m in MECHANISMS]
fig.legend(handles=handles, ncols=6, loc="upper center",
           bbox_to_anchor=(0.5, 1.10), frameon=True)
plt.show()
