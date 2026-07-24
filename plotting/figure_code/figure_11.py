from pathlib import Path
import math
import re
import statistics

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml


def find_repo_root():
    start = Path.cwd().resolve()
    for candidate in [start, *start.parents]:
        if (candidate / 'row_policy').is_dir() and (candidate / 'main').is_dir():
            return candidate
    raise FileNotFoundError('Could not locate the MORDOR repository root')


REPO_ROOT = find_repo_root()
MECHANISMS = ['Hydra', 'PARA', 'comet', 'DAPPER', 'graphene', 'abacus']
MECHANISM_LABELS = {
    'Hydra': 'Hydra', 'PARA': 'Para', 'comet': 'Comet',
    'DAPPER': 'Dapper', 'graphene': 'Graphene', 'abacus': 'Abacus',
}
POLICIES = ['open', 'cap4', 'cap16']
POLICY_LABELS = {'open': 'Open Row', 'cap4': 'Cap 4', 'cap16': 'Cap 16'}
COLORS = {'open': '#c9c9c9', 'cap4': '#858585', 'cap16': '#4d4d4d'}
HATCHES = {'open': '', 'cap4': '', 'cap16': ''}
FONT_SIZE = 14
BACKGROUND = '#f4f4f4'
GRID = '#c9c9c9'

plt.rcParams.update({
    'font.size': FONT_SIZE, 'font.weight': 'normal',
    'axes.labelweight': 'normal', 'axes.titleweight': 'normal',
    'axes.titlesize': FONT_SIZE, 'xtick.labelsize': FONT_SIZE,
    'ytick.labelsize': FONT_SIZE,
})


def load_metrics(path):
    lines = path.read_text(errors='replace').splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip() == 'Frontend:'), None)
    if start is None:
        return None
    try:
        data = yaml.safe_load('\n'.join(lines[start:]) + '\n')
        cycles = [float(data['Frontend'][f'cycles_recorded_core_{core}']) for core in range(8)]
        energy = float(data['MemorySystem']['DRAM']['total_energy'])
    except (KeyError, TypeError, ValueError, yaml.YAMLError):
        return None
    if not all(math.isfinite(value) for value in [*cycles, energy]):
        return None
    return {'cycles': statistics.fmean(cycles), 'energy': energy}


def result_directory(policy, mechanism, scheduler):
    if policy == 'open':
        return REPO_ROOT / 'main' / scheduler / mechanism
    cap = int(policy.removeprefix('cap'))
    return REPO_ROOT / 'row_policy' / f'cap_{cap}' / scheduler / mechanism


def collect(policy, mechanism, scheduler):
    directory = result_directory(policy, mechanism, scheduler)
    values = {}
    for path in sorted(directory.glob('*_output.yaml')) if directory.exists() else []:
        metrics = load_metrics(path)
        if metrics is not None:
            values[path.name.removesuffix('_output.yaml')] = metrics
    return values


values = {
    (policy, mechanism, scheduler): collect(policy, mechanism, scheduler)
    for policy in POLICIES for mechanism in MECHANISMS
    for scheduler in ['priority', 'mordor']
}
required_policy_traces = {
    f"{POLICY_LABELS[policy]} / {MECHANISM_LABELS[mechanism]} / {scheduler}":
        values[(policy, mechanism, scheduler)]
    for policy in POLICIES for mechanism in MECHANISMS
    for scheduler in ['priority', 'mordor']
}
policy_traces = require_paper_trace_cohort("Figure 11", required_policy_traces)
paired_traces = {}
coverage = []
for policy in POLICIES:
    for mechanism in MECHANISMS:
        priority = set(values[(policy, mechanism, 'priority')]) & PAPER_TRACE_SET
        mordor = set(values[(policy, mechanism, 'mordor')]) & PAPER_TRACE_SET
        paired_traces[(policy, mechanism)] = policy_traces
        coverage.append({
            'policy': POLICY_LABELS[policy], 'mechanism': MECHANISM_LABELS[mechanism],
            'priority': len(priority), 'mordor': len(mordor),
            'paired': len(paired_traces[(policy, mechanism)]),
        })
display(pd.DataFrame(coverage))

rows = []
for policy in POLICIES:
    for mechanism in MECHANISMS:
        for trace in paired_traces[(policy, mechanism)]:
            priority = values[(policy, mechanism, 'priority')][trace]
            mordor = values[(policy, mechanism, 'mordor')][trace]
            rows.append({
                'policy': policy, 'mechanism': mechanism, 'trace': trace,
                'cycle_reduction': 100 * (priority['cycles'] / mordor['cycles'] - 1),
                'energy_reduction': 100 * (priority['energy'] / mordor['energy'] - 1),
            })
reductions = pd.DataFrame(rows)

def sem(values):
    return statistics.stdev(values) / len(values) ** 0.5 if len(values) > 1 else 0.0


if reductions.empty:
    print('No paired Priority/MORDOR comparisons are available yet.')
else:
    summary_rows = []
    for policy in POLICIES:
        for mechanism in MECHANISMS:
            subset = reductions[(reductions.policy == policy)
                                & (reductions.mechanism == mechanism)]
            if subset.empty:
                continue
            summary_rows.append({
                'policy': policy, 'mechanism': mechanism, 'traces': len(subset),
                'cycle_mean': statistics.fmean(subset.cycle_reduction),
                'cycle_sem': sem(subset.cycle_reduction.tolist()),
                'energy_mean': statistics.fmean(subset.energy_reduction),
                'energy_sem': sem(subset.energy_reduction.tolist()),
            })
    summary = pd.DataFrame(summary_rows)
    display(summary.round(3))

    mechanisms = [m for m in MECHANISMS if not summary[summary.mechanism == m].empty]
    fig, axes = plt.subplots(1, 2, figsize=(7.1, 3.15))
    panels = [
        ('cycle_mean', 'cycle_sem', 'Cycle Count Red. [%]'),
        ('energy_mean', 'energy_sem', 'DRAM Energy Red. [%]'),
    ]
    x = np.arange(len(mechanisms))
    width = min(0.78 / len(POLICIES), 0.25)
    for ax, (mean_key, sem_key, ylabel) in zip(axes, panels):
        for index, policy in enumerate(POLICIES):
            policy_rows = summary[summary.policy == policy].set_index('mechanism').reindex(mechanisms)
            positions = x + (index - (len(POLICIES) - 1) / 2) * width
            ax.bar(
                positions, policy_rows[mean_key], width, yerr=policy_rows[sem_key],
                capsize=2.5, color=COLORS[policy], hatch=HATCHES[policy],
                edgecolor='#333333', linewidth=0.65, label=POLICY_LABELS[policy],
                error_kw={'elinewidth': 0.75},
            )
        ax.set_xticks(x, [MECHANISM_LABELS[m] for m in mechanisms],
                      rotation=28, ha='right', rotation_mode='anchor')
        ax.set_ylabel(ylabel, fontsize=FONT_SIZE)
        ax.axhline(0, color='#333333', linewidth=0.7)
        ax.set_facecolor(BACKGROUND)
        ax.grid(axis='y', color=GRID, linewidth=0.6, alpha=0.7)
        ax.set_axisbelow(True)
        ax.spines[['top', 'right']].set_visible(False)
    axes[1].legend(title='Row Policy', fontsize=9, title_fontsize=9, frameon=True)
    fig.subplots_adjust(left=0.17, right=0.98, bottom=0.25, top=0.92, wspace=0.62)
    plt.show()
