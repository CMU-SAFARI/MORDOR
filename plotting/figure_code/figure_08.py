fig, ax = plt.subplots(figsize=(7.1, 3.15), constrained_layout=True)
x = list(range(len(PLOTTED_MECHANISMS)))
bar_width = 0.22
for variant_index, variant in enumerate(VARIANTS):
    means, errors = [], []
    for mechanism in PLOTTED_MECHANISMS:
        values = overheads[(mechanism, variant)]
        means.append(statistics.fmean(values) if values else float("nan"))
        errors.append(statistics.stdev(values) / len(values) ** 0.5 if len(values) > 1 else 0.0)
    offset = (variant_index - (len(VARIANTS) - 1) / 2) * bar_width
    ax.bar([position + offset for position in x], means, width=bar_width, yerr=errors, capsize=3,
           color=VARIANT_COLORS[variant],
           edgecolor="#111111", linewidth=0.5, label=VARIANT_LABELS[variant])
ax.set_xticks(x, [MECHANISM_LABELS[mechanism] for mechanism in PLOTTED_MECHANISMS], rotation=25, ha="right")
ax.set_ylabel("Cycle Count Overhead [%]")
ax.yaxis.set_major_locator(MaxNLocator(nbins=5))
ax.set_facecolor(PLOT_BACKGROUND_COLOR)
ax.grid(axis="y", color=GRID_COLOR, linewidth=0.7, alpha=0.6)
ax.set_axisbelow(True)
ax.spines[["top", "right"]].set_visible(False)
variant_handles = [Patch(facecolor=VARIANT_COLORS[variant], edgecolor="#111111",
                         label=VARIANT_LABELS[variant])
                   for variant in VARIANTS]
legend = ax.legend(handles=variant_handles, title="Scheduler", frameon=True,
                   fontsize=PLOT_FONT_SIZE, title_fontsize=PLOT_FONT_SIZE)
legend.get_frame().set_facecolor("#f4f4f4")
legend.get_frame().set_edgecolor(GRID_COLOR)
plt.show()
