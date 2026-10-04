"""Figure 8: mean latency-percentile curves for five high-PRO workloads."""

from collections import Counter
import numpy as np

LATENCY_TRACES = ("429.mcf", "470.lbm", "random_10.trace",
                  "stream_10.trace", "549.fotonik3d")
LATENCY_MECHANISMS = ["Hydra", "PARA", "graphene", "DAPPER", "comet", "abacus"]
LATENCY_RE = re.compile(r"^\[Lat ?\((RD|PRO)\):\s*(\d+)\]$")


def latency_percentiles(path):
    histograms = {"RD": Counter(), "PRO": Counter()}
    for line in path.read_text(errors="replace").splitlines():
        match = LATENCY_RE.fullmatch(line)
        if match:
            histograms[match.group(1)][int(match.group(2))] += 1
    if not histograms["RD"]:
        raise ValueError(f"No demand-read samples in {path}")
    result = {}
    percentiles = np.linspace(0.0, 100.0, 1001)
    for kind, histogram in histograms.items():
        if not histogram:
            continue
        values = np.array(sorted(histogram), dtype=np.int64)
        counts = np.array([histogram[value] for value in values], dtype=np.int64)
        cumulative = np.cumsum(counts)
        ranks = np.maximum(1, np.ceil(percentiles * cumulative[-1] / 100.0).astype(int))
        result[kind] = values[np.searchsorted(cumulative, ranks, side="left")]
    return percentiles, result


styles = {
    ("mordor", "RD"): ("#f28e3b", "-", "MORDOR Read"),
    ("mordor", "PRO"): ("#f28e3b", "--", "MORDOR PRO"),
    ("priority", "RD"): ("#666666", "-", "Priority Read"),
    ("priority", "PRO"): ("#666666", "--", "Priority PRO"),
}
fig, axes = plt.subplots(2, 3, figsize=(9.0, 5.2), constrained_layout=True)
for ax, mechanism in zip(axes.ravel(), LATENCY_MECHANISMS):
    for scheduler in ("mordor", "priority"):
        curves = {"RD": [], "PRO": []}
        for trace in LATENCY_TRACES:
            path = Path("latency") / scheduler / mechanism / f"{trace}_latency.txt"
            if not path.is_file():
                raise FileNotFoundError(path)
            percentiles, values = latency_percentiles(path)
            for kind in curves:
                if kind in values:
                    curves[kind].append(values[kind])
        if len(curves["RD"]) != len(LATENCY_TRACES):
            raise ValueError(f"Incomplete Figure 8 demand-read cohort: {mechanism}/{scheduler}")
        for kind, per_trace in curves.items():
            if not per_trace:
                continue
            color, linestyle, label = styles[(scheduler, kind)]
            ax.plot(percentiles, np.mean(np.stack(per_trace), axis=0),
                    color=color, linestyle=linestyle, linewidth=1.65, label=label)
    ax.set_title(MECHANISM_LABELS[mechanism])
    ax.set_xlim(-1, 101)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.axvspan(90, 100, color="#f28e3b", alpha=0.08, linewidth=0)
    ax.grid(color=GRID_COLOR, linewidth=0.5, alpha=0.6)
    ax.set_axisbelow(True)
for ax in axes[:, 0]:
    ax.set_ylabel("Mean Latency (cycles)")
for ax in axes[-1, :]:
    ax.set_xlabel("Percentile (%)")
axes[0, 0].legend(loc="upper left", fontsize=8, frameon=True)
plt.show()
