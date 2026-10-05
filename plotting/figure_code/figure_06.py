"""Figure 6: top-25 per-trace speedup at NRH=125."""

import numpy as np

TOP_COUNT = 25
FIGURE6_MECHANISMS = ["abacus", "comet", "DAPPER", "graphene", "Hydra", "PARA"]
FIGURE6_COLORS = {
    "Hydra": "#9ecae1", "PARA": "#f4b183", "comet": "#a9d8b8",
    "DAPPER": "#efaaa8", "graphene": "#bdbdbd", "abacus": "#c8b6e8",
}

complete = set(PAPER_TRACES)
for mechanism in FIGURE6_MECHANISMS:
    complete &= set(scheduler_comparison_metrics[(mechanism, "priority")])
    complete &= set(scheduler_comparison_metrics[(mechanism, "mordor")])

# Rank by logical MORDOR PROQ insertions summed across all six mechanisms.
# shared_results has already normalized ABACuS's 32 inserted entries per
# logical all-bank PRO.
intensity = {}
for trace in complete:
    values = []
    for mechanism in FIGURE6_MECHANISMS:
        value = scheduler_comparison_metrics[(mechanism, "mordor")][trace]["num_proq_adds"]
        if value is None:
            raise ValueError(f"Figure 6 lacks PROQ traffic for {mechanism}/{trace}")
        values.append(value)
    intensity[trace] = sum(values)
top_traces = [trace for trace, _ in sorted(
    intensity.items(), key=lambda item: (-item[1], item[0])
)[:TOP_COUNT]]
if len(top_traces) != TOP_COUNT:
    raise ValueError(f"Figure 6 requires {TOP_COUNT} complete traces")

fig, ax = plt.subplots(figsize=(12.5, 3.8), constrained_layout=True)
x = np.arange(len(top_traces) + 1, dtype=float)
width = 0.82 / len(FIGURE6_MECHANISMS)
upper_limit = 250.0
for index, mechanism in enumerate(FIGURE6_MECHANISMS):
    values = [
        100.0 * (
            scheduler_comparison_metrics[(mechanism, "priority")][trace]["cycles"]
            / scheduler_comparison_metrics[(mechanism, "mordor")][trace]["cycles"] - 1.0
        ) for trace in top_traces
    ]
    plotted = [*values, statistics.fmean(values)]
    offset = (index - (len(FIGURE6_MECHANISMS) - 1) / 2) * width
    positions = x + offset
    ax.bar(positions, plotted, width, color=FIGURE6_COLORS[mechanism],
           edgecolor="#111111", linewidth=0.65, zorder=3)
    for position, value in zip(positions, plotted):
        if value > upper_limit:
            ax.text(position, upper_limit - 1.5, f"{value:.1f}", ha="center",
                    va="bottom", fontsize=8.0, color="#111111", zorder=5)
ax.axhline(0, color="#111111", linewidth=0.8)
ax.axvline(len(top_traces) - 0.5, color="#666666", linewidth=1.0)
ax.set_ylabel("Speedup over Priority\nScheduling [%]")
ax.set_xticks(x, [*top_traces, "AVG"], rotation=65, ha="right")
ax.get_xticklabels()[-1].set_fontweight("bold")
ax.set_ylim(0, upper_limit)
ax.grid(axis="y", color="#d6d6d6", linewidth=0.65, alpha=0.75)
ax.set_axisbelow(True)
ax.set_facecolor("white")
handles = [Patch(facecolor=FIGURE6_COLORS[m], edgecolor="#111111",
                 label=MECHANISM_LABELS[m]) for m in FIGURE6_MECHANISMS]
ax.legend(handles=handles, ncols=3, loc="upper right", frameon=True)
plt.show()
