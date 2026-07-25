# Top 25 PRO-intensive traces that are complete for every mechanism under all three configurations.
# Execution-time reduction [%] = (Cycles_priority / Cycles_MORDOR - 1) * 100.
TOP_PRO_TRACE_COUNT = min(25, len(PAPER_TRACES))
SPEEDUP_MECHANISMS = ["abacus", "comet", "DAPPER", "graphene", "Hydra", "PARA"]
# Reuse the shared greyscale mechanism palette. Hatches remain useful here
# because six mechanisms are repeated within every trace group.
SPEEDUP_COLORS = {mechanism: MECHANISM_COLORS[mechanism] for mechanism in SPEEDUP_MECHANISMS}
SPEEDUP_HATCHES = {"abacus": "", "comet": "//", "DAPPER": "",
                    "graphene": "xx", "Hydra": "..", "PARA": "++"}

common_complete_traces = set.intersection(
    *(set(traces_by_mechanism[mechanism]) for mechanism in SPEEDUP_MECHANISMS)
) & PAPER_TRACE_SET

# Rank using logical MORDOR PROQ insertions summed across mechanisms.
# ABACuS contributes 32 blacklist entries per logical all-bank PRO.
pro_intensity = {}
for mechanism in SPEEDUP_MECHANISMS:
    directory = MORDOR_RESULTS_DIR / mechanism
    for path in sorted(directory.glob("*_output.yaml")):
        match = RESULT_FILE_RE.match(path.name)
        if match is None or match.group("trace") not in common_complete_traces:
            continue
        text = path.read_text(errors="replace")
        values = [float(value) for value in
                  re.findall(r"^\s+num_PROQ_adds:\s+([^\s#]+)", text, re.MULTILINE)]
        values = [value for value in values if math.isfinite(value)]
        if values:
            pro_intensity[(mechanism, match.group("trace"))] = (
                sum(values) / PROQ_LENGTH_DIVISORS[mechanism]
            )

fully_available_traces = [
    trace for trace in common_complete_traces
    if all((mechanism, trace) in pro_intensity for mechanism in SPEEDUP_MECHANISMS)
]
aggregate_pro_intensity = {
    trace: sum(pro_intensity[(mechanism, trace)] for mechanism in SPEEDUP_MECHANISMS)
    for trace in fully_available_traces
}
top_pro_traces = [trace for trace, _ in
                  sorted(aggregate_pro_intensity.items(), key=lambda item: (-item[1], item[0]))
                  [:TOP_PRO_TRACE_COUNT]]
if len(top_pro_traces) < TOP_PRO_TRACE_COUNT:
    raise ValueError(
        f"Only {len(top_pro_traces)} fully complete traces are available; "
        f"cannot plot the requested top {TOP_PRO_TRACE_COUNT}"
    )

execution_time_reduction = {
    (mechanism, trace):
        100.0 * (cycle_values[(mechanism, "priority")][trace]
                 / cycle_values[(mechanism, "mordor")][trace] - 1.0)
    for mechanism in SPEEDUP_MECHANISMS for trace in top_pro_traces
}

print(f"Top {TOP_PRO_TRACE_COUNT} traces by aggregate logical MORDOR PRO intensity")
print("Execution-time reduction [%] = (Cycles_priority / Cycles_MORDOR - 1) * 100")
for rank, trace in enumerate(top_pro_traces, 1):
    print(f"{rank:>2}. {trace:<24} aggregate PRO intensity: {aggregate_pro_intensity[trace]:.0f}")

plt.rcParams.update({"font.weight": "normal", "axes.labelweight": "normal",
                     "axes.titleweight": "normal"})
fig, ax = plt.subplots(figsize=(12.5, 3.8), constrained_layout=True)
x = list(range(len(top_pro_traces)))
group_width = 0.82
single_bar_width = group_width / len(SPEEDUP_MECHANISMS)
for mechanism_index, mechanism in enumerate(SPEEDUP_MECHANISMS):
    offset = (mechanism_index - (len(SPEEDUP_MECHANISMS) - 1) / 2) * single_bar_width
    values = [execution_time_reduction[(mechanism, trace)] for trace in top_pro_traces]
    ax.bar([position + offset for position in x], values, width=single_bar_width,
           color=SPEEDUP_COLORS[mechanism], hatch=SPEEDUP_HATCHES[mechanism],
           edgecolor="#111111", linewidth=0.45, label=MECHANISM_LABELS[mechanism])
ax.axhline(0, color="#111111", linewidth=0.7)
ax.set_ylabel("Execution-Time\nReduction [%]")
ax.set_xticks(x, top_pro_traces, rotation=65, ha="right", fontsize=PLOT_FONT_SIZE)
ax.set_facecolor(PLOT_BACKGROUND_COLOR)
ax.grid(axis="y", color=GRID_COLOR, linewidth=0.7, alpha=0.6)
ax.set_axisbelow(True)
ax.spines[["top", "right"]].set_visible(False)
legend = ax.legend(title="Mechanism", ncols=3, frameon=True,
                   fontsize=PLOT_FONT_SIZE, title_fontsize=PLOT_FONT_SIZE, loc="upper right")
legend.get_frame().set_facecolor("#f4f4f4")
legend.get_frame().set_edgecolor(GRID_COLOR)
plt.show()
