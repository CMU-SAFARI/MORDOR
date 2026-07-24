delay_fields = {"average": "avg_delayed", "maximum": "max_delayed"}
scheduler_comparison_delay_traces = {}
for mechanism in MECHANISMS:
    scheduler_comparison_delay_traces[mechanism] = sorted(
        trace for trace in (set(scheduler_comparison_metrics[(mechanism, "priority")])
                            & set(scheduler_comparison_metrics[(mechanism, "mordor")]))
        if trace in PAPER_TRACE_SET
        and all(scheduler_comparison_metrics[(mechanism, scheduler)][trace][field] is not None
                for scheduler in SCHEDULER_COMPARISON_SCHEDULERS for field in delay_fields.values())
    )
scheduler_comparison_delay_mechanisms = [mechanism for mechanism in MECHANISMS
                         if scheduler_comparison_delay_traces[mechanism]]
shared_delay_traces = require_paper_trace_cohort(
    "Figure 13",
    {MECHANISM_LABELS[mechanism]: scheduler_comparison_delay_traces[mechanism]
     for mechanism in MECHANISMS},
)
scheduler_comparison_delay_traces = {mechanism: shared_delay_traces for mechanism in MECHANISMS}
for mechanism in scheduler_comparison_delay_mechanisms:
    print(f"{MECHANISM_LABELS[mechanism]}: {len(scheduler_comparison_delay_traces[mechanism])} paired traces")

fig, axes = plt.subplots(1, 2, figsize=(9.2, 3.2), constrained_layout=True)
delay_specs = [("average", "Avg. Num. Requests Delayed by a PRO"),
               ("maximum", "Max. Num. Requests Delayed by a PRO")]
base_positions = list(range(len(scheduler_comparison_delay_mechanisms)))
box_width = 0.30
offsets = {"mordor": -0.18, "priority": 0.18}
for ax, (metric, xlabel) in zip(axes, delay_specs):
    for scheduler in ["mordor", "priority"]:
        datasets = [
            [scheduler_comparison_metrics[(mechanism, scheduler)][trace][delay_fields[metric]]
             for trace in scheduler_comparison_delay_traces[mechanism]]
            for mechanism in scheduler_comparison_delay_mechanisms
        ]
        positions = [position + offsets[scheduler] for position in base_positions]
        boxes = ax.boxplot(
            datasets, positions=positions, widths=box_width, patch_artist=True,
            manage_ticks=False, showfliers=True,
            medianprops={"color": "#ffffff", "linewidth": 1.3},
            whiskerprops={"color": "#333333", "linewidth": 0.8},
            capprops={"color": "#333333", "linewidth": 0.8},
            flierprops={"marker": "o", "markersize": 2.5,
                        "markerfacecolor": "none", "markeredgecolor": "#777777",
                        "markeredgewidth": 0.5})
        for box in boxes["boxes"]:
            box.set_facecolor(SCHEDULER_COMPARISON_SCHEDULER_COLORS[scheduler])
            box.set_edgecolor("#111111")
            box.set_linewidth(0.5)
            box.set_hatch("")
    ax.set_xticks(base_positions, [MECHANISM_LABELS[m] for m in scheduler_comparison_delay_mechanisms],
                  rotation=25, ha="right")
    ax.set_xlabel(xlabel, labelpad=8, fontsize=PLOT_FONT_SIZE + 2)
    ax.set_facecolor(PLOT_BACKGROUND_COLOR)
    ax.grid(axis="y", color=GRID_COLOR, linewidth=0.7, alpha=0.6)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)
delay_handles = [Patch(facecolor=SCHEDULER_COMPARISON_SCHEDULER_COLORS[scheduler],
                       edgecolor="#111111",
                       label=SCHEDULER_COMPARISON_SCHEDULER_LABELS[scheduler])
                 for scheduler in ["mordor", "priority"]]
delay_legend = axes[0].legend(handles=delay_handles, title="Scheduler", frameon=True,
                              fontsize=PLOT_FONT_SIZE, title_fontsize=PLOT_FONT_SIZE)
delay_legend.get_frame().set_facecolor("#f4f4f4")
delay_legend.get_frame().set_edgecolor(GRID_COLOR)
plt.show()
