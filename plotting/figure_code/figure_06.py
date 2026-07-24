# Aggregate cycle and energy overheads across all PRT thresholds.
MULTI_PRTS = [125, 250, 500, 1000]

def multi_prt_directory(prt, variant, mechanism):
    if prt == 125:
        return Path("main") / variant / mechanism
    return Path("prt_sweep") / f"prt_{prt}" / variant / mechanism

MULTI_PRT_FILE_RE = re.compile(r"^(?P<trace>.+)_output\.yaml$")
multi_prt_metrics = {}
for prt in MULTI_PRTS:
    for mechanism in MECHANISMS:
        for scheduler in SCHEDULER_COMPARISON_SCHEDULERS:
            by_trace = {}
            directory = multi_prt_directory(prt, scheduler, mechanism)
            for path in sorted(directory.glob("*_output.yaml")):
                match = MULTI_PRT_FILE_RE.match(path.name)
                metrics = read_scheduler_comparison_metrics(path, mechanism) if match else None
                if metrics is not None:
                    by_trace[match.group("trace")] = metrics
            multi_prt_metrics[(prt, mechanism, scheduler)] = by_trace

multi_prt_complete_traces = {}
for prt in MULTI_PRTS:
    required = {"No-mitigation baseline": scheduler_comparison_baselines}
    required.update({
        f"{MECHANISM_LABELS[mechanism]} {SCHEDULER_COMPARISON_SCHEDULER_LABELS[scheduler]}":
            multi_prt_metrics[(prt, mechanism, scheduler)]
        for mechanism in MECHANISMS for scheduler in SCHEDULER_COMPARISON_SCHEDULERS
    })
    multi_prt_complete_traces[prt] = require_paper_trace_cohort(
        f"Figure 6 / PRT {prt}", required
    )

def multi_prt_grouped_stats(prt, metric):
    grouped = {}
    for mechanism in MECHANISMS:
        for scheduler in SCHEDULER_COMPARISON_SCHEDULERS:
            overheads = [
                100.0 * (multi_prt_metrics[(prt, mechanism, scheduler)][trace][metric]
                         / scheduler_comparison_baselines[trace][metric] - 1.0)
                for trace in multi_prt_complete_traces[prt]
            ]
            sem = (statistics.stdev(overheads) / len(overheads) ** 0.5
                   if len(overheads) > 1 else 0.0)
            grouped[(mechanism, scheduler)] = (statistics.fmean(overheads), sem)
    return grouped

fig, axes = plt.subplots(2, len(MULTI_PRTS), figsize=(12.2, 4.8),
                         constrained_layout=True, sharex="col")
multi_prt_specs = [("cycles", "Cycle Count\nOverhead [%]"),
                   ("energy", "DRAM Energy\nOverhead [%]")]
x = list(range(len(MECHANISMS)))
bar_width = 0.34
for column, prt in enumerate(MULTI_PRTS):
    for row_index, (metric, ylabel) in enumerate(multi_prt_specs):
        ax = axes[row_index, column]
        grouped = multi_prt_grouped_stats(prt, metric)
        for scheduler_index, scheduler in enumerate(SCHEDULER_COMPARISON_SCHEDULERS):
            means = [grouped[(mechanism, scheduler)][0] for mechanism in MECHANISMS]
            errors = [grouped[(mechanism, scheduler)][1] for mechanism in MECHANISMS]
            positions = [position + (scheduler_index - 0.5) * bar_width for position in x]
            ax.bar(positions, means, bar_width, yerr=errors, capsize=2.5,
                   color=SCHEDULER_COMPARISON_SCHEDULER_COLORS[scheduler],
                   edgecolor="#111111", linewidth=0.6,
                   error_kw={"elinewidth": 0.7})
        if row_index == 0:
            ax.set_title(f"PRT = {prt}")
        if column == 0:
            ax.set_ylabel(ylabel)
        if row_index == 1:
            ax.set_xticks(x, [MECHANISM_LABELS[m] for m in MECHANISMS],
                          rotation=30, ha="right")
        else:
            ax.tick_params(axis="x", labelbottom=False)
        ax.yaxis.set_major_locator(MaxNLocator(nbins=4))
        ax.axhline(0, color="#111111", linewidth=0.6)
        ax.set_facecolor(PLOT_BACKGROUND_COLOR)
        ax.grid(axis="y", color=GRID_COLOR, linewidth=0.7, alpha=0.6)
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)

multi_prt_handles = [
    Patch(facecolor=SCHEDULER_COMPARISON_SCHEDULER_COLORS[scheduler], edgecolor="#111111",
          label=SCHEDULER_COMPARISON_SCHEDULER_LABELS[scheduler])
    for scheduler in SCHEDULER_COMPARISON_SCHEDULERS
]
multi_prt_legend = axes[1, -1].legend(handles=multi_prt_handles, title="Scheduler",
                                           frameon=True, fontsize=PLOT_FONT_SIZE,
                                           title_fontsize=PLOT_FONT_SIZE,
                                           loc="upper right")
multi_prt_legend.get_frame().set_facecolor("#f4f4f4")
multi_prt_legend.get_frame().set_edgecolor(GRID_COLOR)
plt.show()

print("Complete traces used per PRT: " + ", ".join(
    f"{prt}: {len(multi_prt_complete_traces[prt])}" for prt in MULTI_PRTS
))
