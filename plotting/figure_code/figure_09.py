"""Figure 9: ready reads and writes delayed by a PRO."""

REQUEST_KINDS = ("read", "write")
STATISTICS = ("average", "maximum")
FIELDS = {
    ("read", "average"): "read_avg_delayed",
    ("read", "maximum"): "read_max_delayed",
    ("write", "average"): "write_avg_delayed",
    ("write", "maximum"): "write_max_delayed",
}

required = {}
for mechanism in MECHANISMS:
    for scheduler in SCHEDULER_COMPARISON_SCHEDULERS:
        values = scheduler_comparison_metrics[(mechanism, scheduler)]
        required[
            f"{MECHANISM_LABELS[mechanism]} "
            f"{SCHEDULER_COMPARISON_SCHEDULER_LABELS[scheduler]}"
        ] = {
            trace for trace, metrics in values.items()
            if all(metrics[FIELDS[key]] is not None
                   for key in FIELDS)
        }
figure9_traces = require_paper_trace_cohort("Figure 9", required)

fig, axes_grid = plt.subplots(2, 2, figsize=(9.2, 6.7))
fig.subplots_adjust(left=0.11, right=0.99, bottom=0.11, top=0.89,
                    hspace=0.62, wspace=0.12)
fig.text(0.55, 0.945, "(a) Read requests", ha="center", va="center",
         fontsize=14, fontweight="bold")
fig.text(0.55, 0.485, "(b) Write requests", ha="center", va="center",
         fontsize=14, fontweight="bold")
positions = list(range(len(MECHANISMS)))
offsets = {"mordor": -0.18, "priority": 0.18}
colors = {"mordor": "#f4b183", "priority": "#b8b8b8"}

for axes, request_kind in zip(axes_grid, REQUEST_KINDS):
    axes[0].set_ylabel(
        f"{request_kind.capitalize()} requests\ndelayed by a PRO"
    )
    for ax, statistic_name in zip(axes, STATISTICS):
        field = FIELDS[(request_kind, statistic_name)]
        for scheduler in ("mordor", "priority"):
            datasets = [
                [scheduler_comparison_metrics[(mechanism, scheduler)][trace][field]
                 for trace in figure9_traces]
                for mechanism in MECHANISMS
            ]
            boxes = ax.boxplot(
                datasets,
                positions=[position + offsets[scheduler] for position in positions],
                widths=0.30, patch_artist=True, manage_ticks=False,
                showfliers=True,
                medianprops={"color": "#ffffff", "linewidth": 1.3},
                whiskerprops={"color": "#333333", "linewidth": 0.8},
                capprops={"color": "#333333", "linewidth": 0.8},
                flierprops={"marker": "o", "markersize": 2.5,
                            "markerfacecolor": "none",
                            "markeredgecolor": "#777777",
                            "markeredgewidth": 0.5},
            )
            for box in boxes["boxes"]:
                box.set_facecolor(colors[scheduler])
                box.set_edgecolor("#111111")
                box.set_linewidth(0.5)
        ax.set_title("Average" if statistic_name == "average" else "Maximum")
        ax.set_xticks(positions, [MECHANISM_LABELS[m] for m in MECHANISMS],
                      rotation=25, ha="right")
        ax.set_facecolor("white")
        ax.grid(axis="y", color="#d6d6d6", linewidth=0.65, alpha=0.75)
        ax.set_axisbelow(True)
        for spine in ax.spines.values():
            spine.set_visible(True)
            spine.set_color("#111111")
            spine.set_linewidth(0.9)

handles = [Patch(facecolor=colors[scheduler], edgecolor="#111111",
                 label=SCHEDULER_COMPARISON_SCHEDULER_LABELS[scheduler])
           for scheduler in ("priority", "mordor")]
legend = axes_grid[0, 0].legend(handles=handles, frameon=True)
legend.get_frame().set_facecolor("white")
legend.get_frame().set_edgecolor("#111111")
plt.show()
