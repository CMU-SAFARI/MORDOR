# MORDOR: Mitigating Overheads of Read Disturbance Preventive Operations via Elastic Refresh Scheduling

[![Artifacts Available](https://img.shields.io/badge/Artifacts-Available-brightgreen)](#reproduction)
[![Artifacts Evaluated — Functional](https://img.shields.io/badge/Artifacts_Evaluated-Functional-brightgreen)](#reproduction)
[![Results Reproduced](https://img.shields.io/badge/Results-Reproduced-brightgreen)](#reproduction)

MORDOR is a preventive refresh scheduling policy that improves the performance
and energy consumption of memory-controller-based read disturbance mitigation
techniques. It intelligently delays Preventive Refresh Operations (PROs) to
schedule them off the critical path of demand memory requests, while
maintaining the data integrity guarantees of the underlying read disturbance
mitigation technique.

MORDOR leverages the observation that a PRO targeting an aggressor DRAM row
must only be prioritized over a demand memory request if that request
activates the same aggressor row. MORDOR temporarily blacklists aggressor
rows with outstanding PROs, allowing other demand memory requests to
continue according to the memory controller's underlying scheduling
algorithm. We evaluate MORDOR alongside six
state-of-the-art read disturbance mitigation techniques: ABACuS, Hydra,
PARA, CoMeT, DAPPER, and Graphene.

This repository contains a MORDOR-specific implementation derived from
[Ramulator 2.0](https://github.com/CMU-SAFARI/ramulator2), experiment
configurations for six read disturbance mitigation techniques, figure-generation
scripts, and a Verilog hardware implementation with an OpenROAD reproduction
flow. We provide these implementations and workflows to enable reproduction
of the paper results and support further research.

## Documentation

- [Code guide](CODE_GUIDE.md): implementation entry points, configuration
  options, and custom experiments.
- [Reproduction guide](REPRODUCING.md): complete local and Slurm
  workflows, result validation, and plotting.
- [Experiment workflow](reproduction/README.md): experiment classes
  and underlying launchers.
- [Hardware reproduction](openroad/README.md): synthesis, area, power, and
  scheduling-path latency.

## Reproduction

The MORDOR reproduction package received the **Artifacts Available**,
**Artifacts Evaluated — Functional**, and **Results Reproduced** badges
in the MICRO 2026 artifact evaluation.
The [reproduction guide](REPRODUCING.md) provides the setup,
execution, validation, and plotting instructions for reproducing the paper
results.

## Repository structure

```text
.
├── ramulator/
│   ├── src/                      # Simulator and read disturbance mitigation techniques
│   ├── ext/                      # Vendored C++ dependencies
│   ├── ramulator_configs/        # Main study and threshold sweep
│   ├── bank_count_study/         # Bank-count sensitivity configurations
│   └── ...                      # Other experiment configurations
├── reproduction/                 # Job generation, execution, and validation
├── plotting/                     # Paper-figure generator and plotting sources
├── openroad/
│   ├── overlay/flow/designs/     # Verilog design and reproduction scripts
│   └── ...                      # Docker flow and reference hardware results
├── reproduce.py                 # Common command-line entry point
├── CODE_GUIDE.md                 # Implementation and configuration guide
└── REPRODUCING.md                # Detailed reproduction instructions
```

Traces are downloaded during setup. Downloaded traces, builds, simulation
results, and figures are excluded from version control.

## Installation

Native simulation requires an x86-64 Linux machine with Python 3.9 or newer,
CMake 3.14 or newer, a C++20 compiler, and Git. Allow approximately 10 GB of
free disk space during trace download and extraction. The simulator's C++
dependencies are included in the repository.

Clone the repository and install the Python dependencies:

```bash
git clone https://github.com/CMU-SAFARI/MORDOR.git
cd MORDOR
python3 -m venv .venv
.venv/bin/python -m pip install \
  -r reproduction/requirements.txt \
  -r plotting/requirements.txt
```

Prepare the simulator and canonical 55-trace set:

```bash
.venv/bin/python reproduce.py local setup
```

Setup verifies the archive's SHA-256 checksum and builds Ramulator. The local
profile uses two compiler jobs by default. See the
[reproduction guide](REPRODUCING.md#long-running-local-execution) to customize
that profile.

To build only the simulator without downloading traces:

```bash
cmake -S ramulator -B ramulator/build -DCMAKE_BUILD_TYPE=Release
cmake --build ramulator/build --parallel 2
```

## Example use

The following commands evaluate the main experiment class for one workload.
The `plan` command generates jobs without executing them. The `resume`
command executes jobs with missing or invalid results and retains validated
outputs:

```bash
.venv/bin/python reproduce.py local plan --classes main --traces 429.mcf
.venv/bin/python reproduce.py local resume --classes main --traces 429.mcf
.venv/bin/python reproduce.py local progress --classes main --traces 429.mcf
```

The `main` class compares the baseline without read disturbance mitigation,
Priority Scheduling of PROs, MORDOR, and the Insecure configuration, which
schedules PROs in the read queue without aggressor-row blacklisting, at a
nominal RowHammer threshold of 125. It evaluates six read
disturbance mitigation techniques: ABACuS, Hydra, PARA, CoMeT, DAPPER,
and Graphene.
A single-workload evaluation requires multiple simulations. Slurm supports
parallel execution for larger studies.

Results are written to `results/`. Jobs write partial outputs and promote
them to final results only after successful execution and semantic validation.
Use the same `--classes` and `--traces` selection for execution and progress.
See the [code guide](CODE_GUIDE.md) for custom simulator configurations.

## Reproducing paper results

The [reproduction guide](REPRODUCING.md) documents the complete matrix and
two execution paths: serial execution on a local Linux machine and parallel
execution on a Slurm installation. Both run directly from your checkout using
configurable paths and scheduler settings.

For example, Figure 6 requires the `main` class. After local
setup, run:

```bash
.venv/bin/python reproduce.py local resume --classes main
.venv/bin/python reproduce.py local progress --classes main
.venv/bin/python reproduce.py figures -- --figures 6
```

Run plotting after all selected simulations are valid. The figure generator
builds `paper_results/` from `results/` and writes PNGs into `figures/`.
The bundle includes `manifest.csv`, which
records the source files and their paper-figure consumers.
The complete matrix contains 6,165 simulations; data-derived Figures 2 and
5–14 are supported. Conceptual Figures 1, 3, and 4 are not generated.

## Hardware implementation and reproduction

The [Verilog implementation](openroad/overlay/flow/designs/src/mordor_v9/mordor_v9.v)
and pinned Docker/OpenROAD flow reproduce Table 1's area, power, and
scheduling-path latency results. The host needs Docker Engine with a running
daemon, x86-64 Linux, at least 8 GB RAM, and approximately 10 GB free disk space.

From the repository root:

```bash
python3 reproduce.py openroad
```

Use `python3 reproduce.py openroad -- --sudo` where Docker requires sudo.
Reports are written under `openroad/out/`. See the
[hardware guide](openroad/README.md) for a reduced run and reference outputs.

## Citation

Please cite the MORDOR paper when using this implementation in research.

Maria Makeenkova, Ataberk Olgun, F. Nisa Bostancı, İsmail Emir Yüksel,
Spiros Galanopoulos, and Onur Mutlu,
"MORDOR: Mitigating Overheads of Read Disturbance Preventive Operations via
Elastic Refresh Scheduling," MICRO 2026.

```bibtex
@inproceedings{makeenkova2026mordor,
  title = {{MORDOR: Mitigating Overheads of Read Disturbance Preventive Operations via Elastic Refresh Scheduling}},
  author = {Makeenkova, Maria and Olgun, Ataberk and Bostancı, F. Nisa and Yüksel, İsmail Emir and Galanopoulos, Spiros and Mutlu, Onur},
  booktitle = {MICRO},
  year = {2026}
}
```

## Contact

Maria Makeenkova (mmakeenkova [at] ethz [dot] ch)
