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
        if (candidate / 'blast_radius').is_dir() and (candidate / 'baseline' / 'no_mitigation').is_dir():
            return candidate
    raise FileNotFoundError('Could not locate the MORDOR repository root')


REPO_ROOT = find_repo_root()
RESULT_ROOT = REPO_ROOT / 'blast_radius' / 'brc_1'
RADII = [1, 2, 8]
MECHANISMS = ['Hydra', 'PARA', 'comet', 'DAPPER', 'graphene', 'abacus']
MECHANISM_LABELS = {
    'Hydra': 'Hydra', 'PARA': 'Para', 'comet': 'Comet',
    'DAPPER': 'Dapper', 'graphene': 'Graphene', 'abacus': 'Abacus',
}
SCHEDULERS = ['priority', 'mordor']
SCHEDULER_LABELS = {'priority': 'Priority', 'mordor': 'MORDOR'}
FONT_SIZE = 14
COLORS = {'priority': '#858585', 'mordor': '#f28e3b'}
HATCHES = {'priority': '///', 'mordor': ''}
BACKGROUND = '#f4f4f4'
GRID = '#c9c9c9'

plt.rcParams.update({
    'font.size': FONT_SIZE,
    'font.weight': 'normal',
    'axes.labelweight': 'normal',
    'axes.titleweight': 'normal',
    'axes.titlesize': FONT_SIZE,
    'xtick.labelsize': FONT_SIZE,
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


def collect_results(radius, mechanism, scheduler):
    directory = RESULT_ROOT / f'radius_{radius}' / scheduler / mechanism
    values = {}
    for path in sorted(directory.glob('*_output.yaml')) if directory.exists() else []:
        metrics = load_metrics(path)
        if metrics is not None:
            values[path.name.removesuffix('_output.yaml')] = metrics
    return values


result_values = {
    (radius, mechanism, scheduler): collect_results(radius, mechanism, scheduler)
    for radius in RADII for mechanism in MECHANISMS for scheduler in SCHEDULERS
}

def sem(values):
    return statistics.stdev(values) / len(values) ** 0.5 if len(values) > 1 else 0.0

CONFIGURATIONS = ['br1', 'br2', 'br8']
CONFIGURATION_LABELS = {
    'br1': 'BR 1',
    'br2': 'BR 2',
    'br8': 'BR 8',
}
CONFIGURATION_COLORS = {
    'br1': '#c9c9c9',
    'br2': '#858585',
    'br8': '#4d4d4d',
}
configuration_values = {}
for mechanism in MECHANISMS:
    configuration_values[('br1', mechanism, 'priority')] = result_values[
        (1, mechanism, 'priority')
    ]
    configuration_values[('br1', mechanism, 'mordor')] = result_values[
        (1, mechanism, 'mordor')
    ]
    configuration_values[('br2', mechanism, 'priority')] = result_values[
        (2, mechanism, 'priority')
    ]
    configuration_values[('br2', mechanism, 'mordor')] = result_values[
        (2, mechanism, 'mordor')
    ]
    configuration_values[('br8', mechanism, 'priority')] = result_values[
        (8, mechanism, 'priority')
    ]
    configuration_values[('br8', mechanism, 'mordor')] = result_values[
        (8, mechanism, 'mordor')
    ]

improvement_paired_traces = {}
improvement_rows = []
required_improvement_traces = {
    f"{CONFIGURATION_LABELS[configuration]} / {MECHANISM_LABELS[mechanism]} / "
    f"{SCHEDULER_LABELS[scheduler]}":
        configuration_values[(configuration, mechanism, scheduler)]
    for configuration in CONFIGURATIONS for mechanism in MECHANISMS
    for scheduler in SCHEDULERS
}
improvement_traces = available_paper_trace_cohort(
    "Figure 10 MORDOR-over-Priority results", required_improvement_traces
)
for configuration in CONFIGURATIONS:
    for mechanism in MECHANISMS:
        priority_values = configuration_values[(configuration, mechanism, 'priority')]
        mordor_values = configuration_values[(configuration, mechanism, 'mordor')]
        traces = improvement_traces
        improvement_paired_traces[(configuration, mechanism)] = traces
        for trace in traces:
            priority = priority_values[trace]
            mordor = mordor_values[trace]
            improvement_rows.append({
                'configuration': configuration,
                'mechanism': mechanism,
                'trace': trace,
                'cycle_reduction': 100 * (priority['cycles'] / mordor['cycles'] - 1),
                'energy_reduction': 100 * (priority['energy'] / mordor['energy'] - 1),
            })

improvements = pd.DataFrame(improvement_rows)
if improvements.empty:
    print('No paired Priority/MORDOR comparisons are available yet.')
else:
    improvement_summary_rows = []
    for configuration in CONFIGURATIONS:
        for mechanism in MECHANISMS:
            subset = improvements[(improvements.configuration == configuration)
                                  & (improvements.mechanism == mechanism)]
            if subset.empty:
                continue
            improvement_summary_rows.append({
                'configuration': configuration,
                'mechanism': mechanism,
                'traces': len(subset),
                'cycle_mean': statistics.fmean(subset.cycle_reduction),
                'cycle_sem': sem(subset.cycle_reduction.tolist()),
                'energy_mean': statistics.fmean(subset.energy_reduction),
                'energy_sem': sem(subset.energy_reduction.tolist()),
            })
    improvement_summary = pd.DataFrame(improvement_summary_rows)
    display(improvement_summary.round(3))

    improvement_mechanisms = [
        mechanism for mechanism in MECHANISMS
        if not improvement_summary[improvement_summary.mechanism == mechanism].empty
    ]
    improvement_panels = [
        ('cycle_mean', 'cycle_sem', 'Cycle Count Red. [%]'),
        ('energy_mean', 'energy_sem', 'DRAM Energy Red. [%]'),
    ]
    fig, axes = plt.subplots(1, 2, figsize=(7.1, 3.15))
    x = np.arange(len(improvement_mechanisms))
    width = min(0.78 / len(CONFIGURATIONS), 0.25)
    for ax, (mean_key, sem_key, ylabel) in zip(axes, improvement_panels):
        for configuration_index, configuration in enumerate(CONFIGURATIONS):
            configuration_rows = (improvement_summary[
                                  improvement_summary.configuration == configuration]
                           .set_index('mechanism').reindex(improvement_mechanisms))
            positions = x + (configuration_index - (len(CONFIGURATIONS) - 1) / 2) * width
            ax.bar(
                positions, configuration_rows[mean_key], width,
                yerr=configuration_rows[sem_key], capsize=2.5,
                color=CONFIGURATION_COLORS[configuration],
                edgecolor='#333333', linewidth=0.65,
                label=CONFIGURATION_LABELS[configuration],
                error_kw={'elinewidth': 0.75},
            )
        ax.set_xticks(
            x, [MECHANISM_LABELS[m] for m in improvement_mechanisms],
            rotation=28, ha='right', rotation_mode='anchor',
        )
        ax.set_ylabel(ylabel, fontsize=FONT_SIZE)
        ax.axhline(0, color='#333333', linewidth=0.7)
        ax.set_facecolor(BACKGROUND)
        ax.grid(axis='y', color=GRID, linewidth=0.6, alpha=0.7)
        ax.set_axisbelow(True)
        ax.spines[['top', 'right']].set_visible(False)
    axes[1].legend(title='Blast Radius', fontsize=9, title_fontsize=9, frameon=True)
    fig.subplots_adjust(left=0.17, right=0.98, bottom=0.25, top=0.92, wspace=0.62)
    plt.show()
