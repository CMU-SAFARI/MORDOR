import os
import re
import yaml
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
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

# Figure 10 uses the paper's two-channel, 22 nm normalized estimate. This is
# intentionally different from Table 4's six-channel, 14 nm value (0.058 mm2).
MORDOR_AREA = 2 * 0.009773

AREA = {
    # Hydra and CoMeT report 0.07 mm^2 per dual-rank channel at
    # N_RH=125.  The evaluated system has two channels.
    ('Hydra', 'MORDOR'): 0.1400 + MORDOR_AREA,
    ('Hydra', 'Priority Scheduling'): 0.1400,

    ('Para', 'MORDOR'): 0.00000001 + MORDOR_AREA,
    ('Para', 'Priority Scheduling'): 0.00000001,

    ('Comet', 'MORDOR'): 0.1400 + MORDOR_AREA,
    ('Comet', 'Priority Scheduling'): 0.1400,

    # DAPPER Table III reports 0.075 mm^2 for DAPPER-H.  The 0.038 mm^2
    # value in the same table belongs to ABACuS.
    ('Dapper', 'MORDOR'): 0.0750 + MORDOR_AREA,
    ('Dapper', 'Priority Scheduling'): 0.0750,

    # Two-channel DDR5-sized Graphene trackers.  Priority uses 10,377
    # entries/bank; the reduced MORDOR threshold uses 10,546 entries/bank.
    # Both are scaled from the ABACuS CACTI estimate of 5.68 mm^2/channel
    # for the previous 21,760-entry configuration.
    ('Graphene', 'MORDOR'): 5.525178352941176,
    ('Graphene', 'Priority Scheduling'): 5.417404411764706,

    # The evaluated implementation is ABACuS-Big, whose paper reports
    # 0.48 mm^2.  Keep that value rather than substituting standard ABACuS.
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
                f"Figure 10 / NRH {trh} / {mech} / {scheduler_label}",
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
    'font.size': 9,
    'axes.titlesize': 9,
    'axes.labelsize': 9,
    'xtick.labelsize': 9,
    'ytick.labelsize': 9,
    'legend.fontsize': 8,
    'legend.title_fontsize': 8,
    'figure.titlesize': 10,
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

fig, axes = plt.subplots(1, len(trh_values), figsize=(5.0, 3.2), sharey=True)
if len(trh_values) == 1:
    axes = [axes]



for i, trh in enumerate(trh_values):
    ax = axes[i]
    sub = df_scatter[df_scatter['tRH'] == trh].copy()

    sub["Area"] = sub["Area"].clip(lower=1e-12)
    sub["Area_plot"] = sub["Area"]

    sns.scatterplot(
        data=sub,
        x='Area_plot',
        y='Mean Overhead (%)',
        hue='Scheduling',
        style='Mechanism',
        s=75,
        ax=ax,
        palette=SCHEDULER_COLORS,
        markers=MECHANISM_MARKERS,
        edgecolor="#555555",
        linewidth=0.8,
        legend=False,
        zorder=3,
    )

    scheduler_handles = [
        Patch(facecolor=SCHEDULER_COLORS["Priority Scheduling"],
              edgecolor="#111111", label="Priority"),
        Patch(facecolor=SCHEDULER_COLORS["MORDOR"], edgecolor="#111111",
              label="MORDOR"),
    ]
    ax.legend(handles=scheduler_handles, title=None, loc="upper right",
              frameon=True, borderpad=0.25, labelspacing=0.25,
              handlelength=1.6, handletextpad=0.45, fontsize=11)

    for mech in sub['Mechanism'].unique():
        mech_df = sub[sub['Mechanism'] == mech]
        if not set(mech_df['Scheduling']) >= {"Priority Scheduling", "MORDOR"}:
            continue

        without = mech_df[mech_df['Scheduling'] == 'Priority Scheduling'].iloc[0]
        with_   = mech_df[mech_df['Scheduling'] == 'MORDOR'].iloc[0]

        ax.plot(
            [without['Area_plot'], with_['Area_plot']],
            [without['Mean Overhead (%)'], with_['Mean Overhead (%)']],
            color="#8a8a8a", linewidth=1.25, zorder=2,
        )

        # The paper identifies mechanisms next to their Priority point rather
        # than adding a second, bulky marker legend.
        label_offsets = {
            "Para": (5, -10),
            "Hydra": (5, 3),
            "Comet": (-7, -8),
            "Dapper": (-7, 2),
            "Graphene": (-7, 9),
            "Abacus": (-7, 6),
        }
        dx, dy = label_offsets[mech]
        ax.annotate(
            mech if mech != "Dapper" else "DAPPER",
            (without['Area_plot'], without['Mean Overhead (%)']),
            xytext=(dx, dy), textcoords="offset points",
            ha="left" if dx >= 0 else "right", va="center",
            fontsize=8,
        )

    ax.set_xlabel('Area [mm²]')
    ax.axhline(0, color="#111111", linewidth=0.7)
    ax.set_xscale("log")
    ax.set_xlim(4e-9, 20)
    ax.set_ylim(-8, 202)
    ax.yaxis.set_major_locator(ticker.MultipleLocator(25))
    ax.yaxis.set_minor_locator(ticker.MultipleLocator(5))

    ax.set_facecolor(PLOT_BACKGROUND_COLOR)
    ax.grid(True, which='major', color=GRID_COLOR, linewidth=0.7, alpha=0.6)
    ax.grid(True, which='minor', color=GRID_COLOR, linewidth=0.5, alpha=0.3)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)

axes[0].set_ylabel(
    'Performance Overhead [%]\nover no RowHammer Mitigation'
)
plt.tight_layout()
plt.show()
