import os
import re
import yaml
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import matplotlib.ticker as ticker


N_CORES = 8

def parse_yaml_file(file_path):
    try:
        with open(file_path, 'r') as file:
            all_lines = file.readlines()
            lines = [line for line in all_lines if not line.startswith("[")]
            lines = [line for line in lines if not line.startswith("num")]
            lines = [line for line in lines if not line.startswith("m_addr")]
            data = yaml.safe_load("\n".join(lines))
            return data if data is not None else {}
    except Exception as e:
        print(f"Error parsing {file_path}: {e}")
        return {}

def process_directory(directory):
    """
    Reads all *_output.yaml files in a directory and returns a DataFrame with:
      - trace_name
      - Total Mem. Cycles   (sum over cores 0..N_CORES-1)
    """
    agg = {}
    if not os.path.isdir(directory):
        print(f"Warning: directory missing: {directory}")
        return pd.DataFrame(columns=["trace_name", "Total Mem. Cycles"])

    for filename in os.listdir(directory):
        if filename.endswith("_output.yaml") and not filename.endswith("_error.yaml"):
            file_path = os.path.join(directory, filename)
            data = parse_yaml_file(file_path)
            trace_stem = filename[:-len("_output.yaml")]
            trace_name = trace_stem
            if trace_name not in PAPER_TRACE_SET:
                continue

            frontend = data.get('Frontend', {})
            total_cycles = 0
            for c in range(N_CORES):
                key = f'cycles_recorded_core_{c}'
                total_cycles += int(frontend.get(key, 0) or 0)

            if total_cycles == 0:
                print(f"Warning: total cycles is zero for {trace_name} in {directory}")

            agg[trace_name] = {'Total Mem. Cycles': total_cycles}

    df = pd.DataFrame(agg).T
    df.index.name = 'trace_name'
    df.reset_index(inplace=True)
    return df

def compute_frfcfs_overhead_only(mech, trh, scheduler_label, df_frfcfs, df_baseline):
    """
    Per-trace FRFCFS overhead (%) vs baseline.
    """
    merged = df_frfcfs.merge(df_baseline, on='trace_name', suffixes=('_frfcfs', '_baseline'))

    merged = merged[
        (merged['Total Mem. Cycles_frfcfs'] != 0) &
        (merged['Total Mem. Cycles_baseline'] != 0)
    ].copy()

    merged['Overhead (%)'] = (merged['Total Mem. Cycles_frfcfs'] / merged['Total Mem. Cycles_baseline'] - 1.0) * 100.0
    merged['Mechanism'] = mech.capitalize()
    merged['tRH'] = trh
    merged['Scheduling'] = scheduler_label
    return merged[['trace_name', 'Mechanism', 'tRH', 'Scheduling', 'Overhead (%)']]

trh_values = [125]
mechanisms = ['Hydra', 'PARA', 'comet', 'DAPPER', 'graphene', 'abacus']

directory_baseline = "./baseline/no_mitigation"

SCHEDULER_RESULT_DIRS = {
    "MORDOR": "./main/mordor",
    "Priority Scheduling": "./main/priority",
}

MORDOR_AREA = 2 * 0.009773 #mm^2 (for 2 channels)

AREA = {
    ('Hydra', 'MORDOR'): 0.0700 + MORDOR_AREA,
    ('Hydra', 'Priority Scheduling'): 0.0700,

    ('Para', 'MORDOR'): 0.00000001 + MORDOR_AREA,
    ('Para', 'Priority Scheduling'): 0.00000001,

    ('Comet', 'MORDOR'): 0.07 + MORDOR_AREA,
    ('Comet', 'Priority Scheduling'): 0.07,

    ('Dapper', 'MORDOR'): 0.038 + MORDOR_AREA,
    ('Dapper', 'Priority Scheduling'): 0.038,

    ('Graphene', 'MORDOR'): 5.68 + MORDOR_AREA,
    ('Graphene', 'Priority Scheduling'): 5.68,

    ('Abacus', 'MORDOR'): 0.48 + MORDOR_AREA,
    ('Abacus', 'Priority Scheduling'): 0.48,
}

dfs = {trh: [] for trh in trh_values}

for trh in trh_values:
    df_baseline = process_directory(directory_baseline)

    for mech in mechanisms:
        for scheduler_label, result_root in SCHEDULER_RESULT_DIRS.items():
            dir_frfcfs = os.path.join(result_root, mech)

            df_frfcfs = process_directory(dir_frfcfs)
            require_paper_trace_cohort(
                f"Figure 14 / PRT {trh} / {mech} / {scheduler_label}",
                {
                    "No-mitigation baseline": set(df_baseline['trace_name']),
                    scheduler_label: set(df_frfcfs['trace_name']),
                },
            )
            df_over = compute_frfcfs_overhead_only(mech, trh, scheduler_label, df_frfcfs, df_baseline)

            dfs[trh].append(df_over)

df_frfcfs_all = pd.concat([pd.concat(dfs[trh]) for trh in trh_values], ignore_index=True)

# Aggregate to one point per mechanism, threshold, and scheduler.
df_scatter = (
    df_frfcfs_all
    .groupby(['Mechanism', 'tRH', 'Scheduling'])['Overhead (%)']
    .mean()
    .reset_index()
    .rename(columns={'Overhead (%)': 'Mean Overhead (%)'})
)

def lookup_area(row):
    return AREA.get((row['Mechanism'], row['Scheduling']), np.nan)

df_scatter['Area'] = df_scatter.apply(lookup_area, axis=1)

missing_area = df_scatter['Area'].isna()
if missing_area.any():
    print("Warning: missing AREA entries for:")
    print(df_scatter.loc[missing_area, ['Mechanism', 'Scheduling']].drop_duplicates().to_string(index=False))

plt.rcParams.update({
    'font.size': 17,
    'axes.titlesize': 17,
    'axes.labelsize': 17,
    'xtick.labelsize': 17,
    'ytick.labelsize': 17,
    'legend.fontsize': 17,
    'legend.title_fontsize': 17,
    'figure.titlesize': 20
})

# Match the scheduler palette used by the other paper plots: orange is
# reserved for MORDOR, while Priority remains neutral gray. Mechanisms
# use marker shapes so both dimensions remain distinguishable.
SCHEDULER_COLORS = {
    "MORDOR": "#f28e3b",
    "Priority Scheduling": "#858585",
}
MECHANISM_MARKERS = {
    "Hydra": "o",
    "Para": "s",
    "Comet": "D",
    "Dapper": "^",
    "Graphene": "P",
    "Abacus": "X",
}
PLOT_BACKGROUND_COLOR = "#f7f7f7"
GRID_COLOR = "#c9c9c9"

fig, axes = plt.subplots(1, len(trh_values), figsize=(10, 6), sharey=True)
if len(trh_values) == 1:
    axes = [axes]



for i, trh in enumerate(trh_values):
    ax = axes[i]
    sub = df_scatter[df_scatter['tRH'] == trh].copy()

    # Offset paired points slightly on the logarithmic x-axis.
    OFFSET = {"Priority Scheduling": 0.98, "MORDOR": 1.08}
    sub["Area"] = sub["Area"].clip(lower=1e-12)
    sub["Area_plot"] = sub.apply(lambda r: r["Area"] * OFFSET.get(r["Scheduling"], 1.0), axis=1)

    sns.scatterplot(
        data=sub,
        x='Area_plot',
        y='Mean Overhead (%)',
        hue='Scheduling',
        style='Mechanism',
        s=260,
        ax=ax,
        palette=SCHEDULER_COLORS,
        markers=MECHANISM_MARKERS,
        edgecolor="#111111",
        linewidth=0.7
    )

    scheduler_handles = [
        Patch(facecolor=SCHEDULER_COLORS["MORDOR"], edgecolor="#111111",
              label="MORDOR"),
        Patch(facecolor=SCHEDULER_COLORS["Priority Scheduling"],
              edgecolor="#111111", label="Priority"),
    ]
    mechanism_handles = [
        Line2D([], [], linestyle="none", marker=MECHANISM_MARKERS[mechanism],
               markersize=10, markerfacecolor="#666666",
               markeredgecolor="#111111", label=mechanism)
        for mechanism in MECHANISM_MARKERS
    ]
    ax.legend(handles=scheduler_handles + mechanism_handles, title=None,
              ncols=2, loc="lower left", frameon=True,
              columnspacing=1.0, handletextpad=0.5)

    for mech in sub['Mechanism'].unique():
        mech_df = sub[sub['Mechanism'] == mech]
        if not set(mech_df['Scheduling']) >= {"Priority Scheduling", "MORDOR"}:
            continue

        without = mech_df[mech_df['Scheduling'] == 'Priority Scheduling'].iloc[0]
        with_   = mech_df[mech_df['Scheduling'] == 'MORDOR'].iloc[0]

        ax.annotate(
            "",
            xy=(with_['Area_plot'], with_['Mean Overhead (%)']),
            xytext=(without['Area_plot'], without['Mean Overhead (%)']),
            arrowprops=dict(
                arrowstyle="->",
                linewidth=1.5,
                color="#666666",
                alpha=0.8
            ),
            zorder=1
        )

    ax.set_xlabel('Area [mm²]')
    ax.axhline(0, color="#111111", linewidth=0.7)
    ax.set_xscale("log")
    ax.yaxis.set_major_locator(ticker.MultipleLocator(25))
    ax.yaxis.set_minor_locator(ticker.MultipleLocator(5))

    ax.set_facecolor(PLOT_BACKGROUND_COLOR)
    ax.grid(True, which='major', color=GRID_COLOR, linewidth=0.7, alpha=0.6)
    ax.grid(True, which='minor', color=GRID_COLOR, linewidth=0.5, alpha=0.3)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)

axes[0].set_ylabel('Execution Time Overhead vs Baseline [%]')
plt.tight_layout()
plt.show()
