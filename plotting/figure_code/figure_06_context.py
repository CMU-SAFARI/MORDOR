"""Minimal shared definitions required by the Figure 6 plotting source."""

from pathlib import Path
import math
import re
import statistics

import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.ticker import MaxNLocator
import yaml


NO_MITIGATION_RESULTS_DIR = Path("baseline/no_mitigation")
MECHANISMS = ["Hydra", "PARA", "comet", "DAPPER", "graphene", "abacus"]
MECHANISM_LABELS = {
    "Hydra": "Hydra",
    "PARA": "Para",
    "comet": "Comet",
    "DAPPER": "Dapper",
    "graphene": "Graphene",
    "abacus": "Abacus",
}
SCHEDULER_COMPARISON_SCHEDULERS = ["priority", "mordor"]
SCHEDULER_COMPARISON_SCHEDULER_LABELS = {
    "priority": "Priority",
    "mordor": "MORDOR",
}
SCHEDULER_COMPARISON_SCHEDULER_COLORS = {
    "priority": "#858585",
    "mordor": "#f28e3b",
}
PLOT_BACKGROUND_COLOR = "#f7f7f7"
GRID_COLOR = "#c9c9c9"
PLOT_FONT_SIZE = 14
CORE_CYCLE_KEYS = [f"cycles_recorded_core_{core}" for core in range(8)]


def read_scheduler_comparison_metrics(path, mechanism=None):
    lines = path.read_text(errors="replace").splitlines()
    start = next(
        (
            index
            for index, line in enumerate(lines)
            if line.strip() == "Frontend:"
        ),
        None,
    )
    if start is None:
        return None
    try:
        data = yaml.safe_load("\n".join(lines[start:]) + "\n")
        cycles = [float(data["Frontend"][key]) for key in CORE_CYCLE_KEYS]
        energy = float(data["MemorySystem"]["DRAM"]["total_energy"])
    except (KeyError, TypeError, ValueError, yaml.YAMLError):
        return None
    if not all(math.isfinite(value) for value in cycles + [energy]):
        return None
    return {"cycles": statistics.fmean(cycles), "energy": energy}


scheduler_comparison_baselines = {}
for path in sorted(NO_MITIGATION_RESULTS_DIR.glob("*_output.yaml")):
    metrics = read_scheduler_comparison_metrics(path)
    if metrics is not None:
        trace = path.name.removesuffix("_output.yaml")
        scheduler_comparison_baselines[trace] = metrics

plt.rcParams.update(
    {
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
        "figure.titlesize": PLOT_FONT_SIZE,
    }
)
