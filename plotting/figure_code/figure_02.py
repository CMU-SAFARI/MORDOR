MOTIVATION_VARIANTS = ["priority", "insecure"]

def read_dram_energy(path):
    lines = path.read_text(errors="replace").splitlines()
    start = next((index for index, line in enumerate(lines)
                  if line.strip() == "Frontend:"), None)
    if start is None:
        return None
    try:
        data = yaml.safe_load("\n".join(lines[start:]) + "\n")
        energy = float(data["MemorySystem"]["DRAM"]["total_energy"])
    except (KeyError, TypeError, ValueError, yaml.YAMLError):
        return None
    return energy if math.isfinite(energy) else None

def collect_variant_energy(directory):
    values = {}
    for path in sorted(directory.glob("*_output.yaml")):
        match = RESULT_FILE_RE.match(path.name)
        if match is None:
            continue
        energy = read_dram_energy(path)
        if energy is not None:
            values[match.group("trace")] = energy
    return values

energy_values = {}
for mechanism in MECHANISMS:
    energy_directories = {
        "priority": PRIORITY_RESULTS_DIR / mechanism,
        "insecure": INSECURE_RESULTS_DIR / mechanism,
    }
    for variant, directory in energy_directories.items():
        energy_values[(mechanism, variant)] = collect_variant_energy(directory)

baseline_energy_values = {}
for path in sorted(NO_MITIGATION_RESULTS_DIR.glob("*_output.yaml")):
    energy = read_dram_energy(path)
    if energy is not None:
        baseline_energy_values[path.name.removesuffix("_output.yaml")] = energy

required_cycle_energy_traces = {
    "Cycle baseline": baseline_values,
    "Energy baseline": baseline_energy_values,
}
required_cycle_energy_traces.update({
    f"{MECHANISM_LABELS[mechanism]} / {VARIANT_LABELS[variant]} / cycles":
        cycle_values[(mechanism, variant)]
    for mechanism in MECHANISMS for variant in MOTIVATION_VARIANTS
})
required_cycle_energy_traces.update({
    f"{MECHANISM_LABELS[mechanism]} / {VARIANT_LABELS[variant]} / energy":
        energy_values[(mechanism, variant)]
    for mechanism in MECHANISMS for variant in MOTIVATION_VARIANTS
})
shared_cycle_energy_traces = require_paper_trace_cohort(
    "Figure 2", required_cycle_energy_traces
)
cycle_energy_traces = {
    mechanism: shared_cycle_energy_traces for mechanism in MECHANISMS
}
cycle_energy_mechanisms = [mechanism for mechanism in MECHANISMS
                           if cycle_energy_traces[mechanism]]
if not cycle_energy_mechanisms:
    raise ValueError("No traces are complete for cycle and energy across Priority and Insecure")

def three_config_overheads(mechanism, variant, metric):
    traces = cycle_energy_traces[mechanism]
    if metric == "cycles":
        values = cycle_values[(mechanism, variant)]
        baseline = baseline_values
    elif metric == "energy":
        values = energy_values[(mechanism, variant)]
        baseline = baseline_energy_values
    else:
        raise ValueError(f"Unknown metric: {metric}")
    return [100.0 * (values[trace] / baseline[trace] - 1.0) for trace in traces]

fig, axes = plt.subplots(1, 2, figsize=(7.1, 3.15), constrained_layout=True)
metric_specs = [("cycles", "Cycle Count\nOverhead [%]"),
                ("energy", "DRAM Energy\nOverhead [%]")]
x = list(range(len(cycle_energy_mechanisms)))
bar_width = 0.22
for ax, (metric, ylabel) in zip(axes, metric_specs):
    for variant_index, variant in enumerate(MOTIVATION_VARIANTS):
        means, errors = [], []
        for mechanism in cycle_energy_mechanisms:
            values = three_config_overheads(mechanism, variant, metric)
            means.append(statistics.fmean(values))
            errors.append(statistics.stdev(values) / len(values) ** 0.5
                          if len(values) > 1 else 0.0)
        offset = (variant_index - (len(MOTIVATION_VARIANTS) - 1) / 2) * bar_width
        ax.bar([position + offset for position in x], means, bar_width,
               yerr=errors, capsize=2.5, color=VARIANT_COLORS[variant],
               edgecolor="#111111", linewidth=0.5,
               label=VARIANT_LABELS[variant])
    ax.axhline(0, color="#111111", linewidth=0.6)
    ax.set_ylabel(ylabel)
    ax.set_xticks(x, [MECHANISM_LABELS[m] for m in cycle_energy_mechanisms],
                  rotation=25, ha="right")
    ax.yaxis.set_major_locator(MaxNLocator(nbins=5))
    ax.set_facecolor(PLOT_BACKGROUND_COLOR)
    ax.grid(axis="y", color=GRID_COLOR, linewidth=0.7, alpha=0.6)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)

configuration_handles = [
    Patch(facecolor=VARIANT_COLORS[variant], edgecolor="#111111",
          label=VARIANT_LABELS[variant])
    for variant in MOTIVATION_VARIANTS
]
configuration_legend = axes[1].legend(
    handles=configuration_handles, title="Configuration", loc="upper right",
    frameon=True, fontsize=12, title_fontsize=12,
)
configuration_legend.get_frame().set_facecolor("#f4f4f4")
configuration_legend.get_frame().set_edgecolor(GRID_COLOR)
plt.show()

print("Complete traces used for both cycle and energy metrics:")
for mechanism in cycle_energy_mechanisms:
    print(f"  {MECHANISM_LABELS[mechanism]}: {len(cycle_energy_traces[mechanism])}")
