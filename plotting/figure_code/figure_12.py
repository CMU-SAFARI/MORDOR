from pathlib import Path
import math
import re
import statistics

import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.ticker import MaxNLocator
import numpy as np
import pandas as pd
import seaborn as sns


def find_repo_root():
    # Locate the consolidated result root from any nested working directory.
    start = Path.cwd().resolve()
    for candidate in [start, *start.parents]:
        if (candidate / "bank_count").is_dir() and (candidate / "baseline" / "no_mitigation").is_dir():
            return candidate
    raise FileNotFoundError("Could not locate the MORDOR repository root")


REPO_ROOT = find_repo_root()
MECHANISMS = ["Hydra", "PARA", "comet", "DAPPER", "graphene", "abacus"]
MECHANISM_LABELS = {
    "Hydra": "Hydra", "PARA": "Para", "comet": "Comet",
    "DAPPER": "Dapper", "graphene": "Graphene", "abacus": "Abacus",
}
SCHEDULERS = ["priority", "mordor"]
SCHEDULER_LABELS = {"priority": "Priority", "mordor": "MORDOR"}
DATASETS = {
  16: {"results": REPO_ROOT / "main", "baseline": REPO_ROOT / "baseline" / "no_mitigation"},
  8: {"results": REPO_ROOT / "bank_count" / "banks_8", "baseline": REPO_ROOT / "bank_count" / "banks_8" / "baseline"},
  32: {"results": REPO_ROOT / "bank_count" / "banks_32", "baseline": REPO_ROOT / "bank_count" / "banks_32" / "baseline"},
}


BANK_ORDER = [8, 16, 32]
# Greyscale with orange reserved for MORDOR; bank-count hatches carry the third dimension.
COLORS = {"priority": "#858585", "mordor": "#f28e3b"}
BANK_HATCHES = {16: "", 8: "///", 32: "xxx"}
BACKGROUND = "#f7f7f7"
GRID = "#c9c9c9"
PLOT_FONT_SIZE = 14

sns.set_theme(style="whitegrid", context="paper")
plt.rcParams.update({
    "figure.dpi": 120,
    "font.size": PLOT_FONT_SIZE,
    "font.weight": "normal",
    "axes.labelsize": PLOT_FONT_SIZE,
    "axes.labelweight": "normal",
    "axes.titlesize": PLOT_FONT_SIZE,
    "axes.titleweight": "normal",
    "xtick.labelsize": PLOT_FONT_SIZE,
    "ytick.labelsize": PLOT_FONT_SIZE,
    "legend.fontsize": PLOT_FONT_SIZE,
    "legend.title_fontsize": PLOT_FONT_SIZE,
    "axes.facecolor": BACKGROUND,
    "axes.spines.top": False,
    "axes.spines.right": False,
})

print(f"Repository root: {REPO_ROOT}")

CORE_PATTERNS = [
    re.compile(rf"^\s+cycles_recorded_core_{core}:\s+([^\s#]+)", re.MULTILINE)
    for core in range(8)
]
ENERGY_PATTERN = re.compile(r"^\s+total_energy:\s+([^\s#]+)", re.MULTILINE)
RESULT_FILE_PATTERN = re.compile(r"^(?P<trace>.+)_output\.yaml$")


def finite_float(text):
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def read_metrics(path):
    text = path.read_text(errors="replace")
    cycles = []
    for pattern in CORE_PATTERNS:
        match = pattern.search(text)
        value = finite_float(match.group(1)) if match else None
        if value is None:
            return None
        cycles.append(value)
    energy_match = ENERGY_PATTERN.search(text)
    energy = finite_float(energy_match.group(1)) if energy_match else None
    if energy is None:
        return None
    return {"cycles": statistics.fmean(cycles), "energy": energy}


def collect_results(directory, mechanism, scheduler, bank_count):
    folder = directory / scheduler / mechanism
    rows, issues = [], []
    if not folder.is_dir():
        return rows, [(str(folder), "missing directory")]
    for path in sorted(folder.glob("*_output.yaml")):
        match = RESULT_FILE_PATTERN.match(path.name)
        if not match:
            issues.append((str(path), "unexpected filename"))
            continue
        trace = match.group("trace")
        if trace not in PAPER_TRACE_SET:
            continue
        metrics = read_metrics(path)
        if metrics is None:
            issues.append((str(path), "missing/invalid cycle or energy metric"))
            continue
        rows.append({
            "bank_count": bank_count,
            "mechanism": mechanism,
            "scheduler": scheduler,
            "trace": trace,
            **metrics,
        })
    return rows, issues


def collect_baselines(directory, bank_count):
    rows, issues = [], []
    if not directory.is_dir():
        return rows, [(str(directory), "missing baseline directory")]
    for path in sorted(directory.glob("*_output.yaml")):
        trace = path.name.removesuffix("_output.yaml")
        if trace not in PAPER_TRACE_SET:
            continue
        metrics = read_metrics(path)
        if metrics is None:
            issues.append((str(path), "missing/invalid cycle or energy metric"))
            continue
        rows.append({
            "bank_count": bank_count,
            "trace": trace,
            "baseline_cycles": metrics["cycles"],
            "baseline_energy": metrics["energy"],
        })
    return rows, issues


result_rows, baseline_rows, issues = [], [], []
for bank_count, dataset in DATASETS.items():
    baseline, baseline_issues = collect_baselines(dataset["baseline"], bank_count)
    baseline_rows.extend(baseline)
    issues.extend(baseline_issues)
    for mechanism in MECHANISMS:
        for scheduler in SCHEDULERS:
            rows, row_issues = collect_results(
                dataset["results"], mechanism, scheduler, bank_count
            )
            result_rows.extend(rows)
            issues.extend(row_issues)

raw_results = pd.DataFrame(result_rows)
baselines = pd.DataFrame(baseline_rows)

if raw_results.empty or baselines.empty:
    raise ValueError("No usable results or baselines were found; check DATASETS above")

# Require the same canonical cohort within every bank/mechanism/scheduler configuration.
required_bank_traces = {}
for bank_count in BANK_ORDER:
    required_bank_traces[f"{bank_count} banks / baseline"] = set(
        baselines.loc[baselines.bank_count == bank_count, "trace"]
    )
    for mechanism in MECHANISMS:
        for scheduler in SCHEDULERS:
            mask = (raw_results.bank_count == bank_count) & (raw_results.mechanism == mechanism) & (raw_results.scheduler == scheduler)
            required_bank_traces[
                f"{bank_count} banks / {MECHANISM_LABELS[mechanism]} / {SCHEDULER_LABELS[scheduler]}"
            ] = set(raw_results.loc[mask, "trace"])
complete_traces = require_paper_trace_cohort("Figure 9", required_bank_traces)

data = (
    raw_results[raw_results.trace.isin(complete_traces)]
    .merge(baselines, on=["bank_count", "trace"], validate="many_to_one")
    .copy()
)
for metric in ["cycles", "energy"]:
    data[f"{metric}_overhead"] = 100.0 * (data[metric] / data[f"baseline_{metric}"] - 1.0)

print(f"Complete paired traces used: {len(complete_traces)}")
print(f"Parsed result files: {len(raw_results):,}; baseline files: {len(baselines):,}")
print(f"Validation issues: {len(issues)}")
if issues:
    display(pd.DataFrame(issues, columns=["path", "issue"]).head(20))

pd.crosstab(
    [raw_results["bank_count"], raw_results["mechanism"]],
    raw_results["scheduler"],
).reindex(pd.MultiIndex.from_product([BANK_ORDER, MECHANISMS], names=["bank_count", "mechanism"]))

def mean_sem(values):
    values = np.asarray(values, dtype=float)
    mean = values.mean()
    sem = values.std(ddof=1) / np.sqrt(len(values)) if len(values) > 1 else 0.0
    return pd.Series({"mean": mean, "sem": sem, "n": len(values)})


summary_parts = []
for metric in ["cycles", "energy"]:
    part = (
        data.groupby(["bank_count", "mechanism", "scheduler"], observed=True)[f"{metric}_overhead"]
        .apply(mean_sem)
        .unstack()
        .reset_index()
    )
    part["metric"] = metric
    summary_parts.append(part)
summary = pd.concat(summary_parts, ignore_index=True)
summary["mechanism"] = pd.Categorical(summary["mechanism"], MECHANISMS, ordered=True)
summary = summary.sort_values(["metric", "bank_count", "mechanism", "scheduler"]).reset_index(drop=True)

summary.assign(
    mechanism=summary.mechanism.map(MECHANISM_LABELS),
    scheduler=summary.scheduler.map(SCHEDULER_LABELS),
).round({"mean": 2, "sem": 2})

# Full two-column paper width, matching the other comparison figures.
cycle_fig, cycle_ax = plt.subplots(figsize=(7.1, 3.15))
cycle_rows = summary[summary.metric == "cycles"]
x = np.arange(len(MECHANISMS))
combinations = [(bank, scheduler) for bank in BANK_ORDER for scheduler in SCHEDULERS]
width = min(0.8 / len(combinations), 0.22)

for index, (bank_count, scheduler) in enumerate(combinations):
    rows = (
        cycle_rows[(cycle_rows.bank_count == bank_count) & (cycle_rows.scheduler == scheduler)]
        .set_index("mechanism")
        .reindex(MECHANISMS)
    )
    offset = (index - (len(combinations) - 1) / 2) * width
    cycle_ax.bar(
        x + offset, rows["mean"], width, yerr=rows["sem"], capsize=1.8,
        color=COLORS[scheduler], hatch=BANK_HATCHES[bank_count],
        edgecolor="#222222", linewidth=0.6, error_kw={"elinewidth": 0.7},
    )

cycle_ax.axhline(0, color="#333333", linewidth=0.7)
cycle_ax.set_ylabel(
    "Performance Overhead [%]\nover no RowHammer Mitigation",
    fontsize=PLOT_FONT_SIZE,
)
cycle_ax.set_xticks(x, [MECHANISM_LABELS[m] for m in MECHANISMS],
                    rotation=32, ha="right", rotation_mode="anchor")
cycle_ax.tick_params(axis="both", labelsize=PLOT_FONT_SIZE)
cycle_ax.grid(axis="y", color=GRID, linewidth=0.6)
cycle_ax.yaxis.set_major_locator(MaxNLocator(nbins=5))
scheduler_handles = [
    Patch(facecolor=COLORS[scheduler], edgecolor="#222222",
          label=SCHEDULER_LABELS[scheduler])
    for scheduler in SCHEDULERS
]
bank_handles = [
    Patch(facecolor="#bdbdbd", edgecolor="#222222",
          hatch=BANK_HATCHES[bank], label=str(bank))
    for bank in BANK_ORDER
]
cycle_fig.legend(handles=scheduler_handles, title="Scheduler", ncols=2,
                 loc="upper left", bbox_to_anchor=(0.14, 0.925), frameon=False,
                 fontsize=12, title_fontsize=12, handlelength=1.4,
                 columnspacing=0.7, handletextpad=0.35)
cycle_fig.legend(handles=bank_handles, title="Num. Banks", ncols=3,
                 loc="upper right", bbox_to_anchor=(0.99, 0.925), frameon=False,
                 fontsize=12, title_fontsize=12, handlelength=1.2,
                 columnspacing=0.55, handletextpad=0.3)
cycle_fig.subplots_adjust(left=0.18, right=0.98, bottom=0.20, top=0.73)
plt.show()
