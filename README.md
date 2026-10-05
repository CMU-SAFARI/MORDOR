# MORDOR reproduction artifact

This repository contains the simulator, experiment orchestration, OpenROAD
flow, and plotting code for the camera-ready MORDOR paper. CPU traces and
generated simulation results are deliberately not committed. Setup downloads
and verifies the 55 traces; completed outputs remain in the ignored `results/`
directory and are converted into an ignored, provenance-recorded
`paper_results/` bundle before plotting.

The simulator under `ramulator/` is derived from
[Ramulator 2.0](https://github.com/CMU-SAFARI/ramulator2) and contains the
MORDOR-specific controller, scheduling, and instrumentation changes used by
the paper.

## Camera-ready scope

The data-derived reproduction generates Figures 2 and 5–14:

| Figure | Generated result |
|---|---|
| 2 | Priority and insecure performance/DRAM-energy overhead |
| 5 | MORDOR speedup and DRAM-energy reduction over Priority at NRH 125/250/500/1000 |
| 6 | Per-trace speedup for the 25 most PRO-intensive workloads at NRH 125 |
| 7 | Processor-side energy using the paper's 500 W, 2 GHz, six-PROQ model |
| 8 | Equal-weight mean latency-percentile curves for five high-PRO workloads, one core, 100M instructions |
| 9 | Average/maximum ready reads and writes delayed by a PRO |
| 10 | Area versus performance overhead using two-channel, 22 nm-normalized area |
| 11 | Priority, MORDOR, and insecure performance overhead at NRH 125 |
| 12 | 8-, 16-, and 32-bank sensitivity |
| 13 | BRC=2 blast radii 1, 2, and 4 |
| 14 | Conservative DRFM address setup: NRH 122 and +47.5 ns |

Figures 1, 3, and 4 are conceptual diagrams and do not depend on simulation
output. The hardware-overhead table is reproduced independently through
OpenROAD.

The default paper matrix contains 6,165 simulations. Main experiments use 8
cores and 10M instructions across all 55 workloads. Figure 8 uses exactly
`429.mcf`, `470.lbm`, `random_10.trace`, `stream_10.trace`, and
`549.fotonik3d`, with one core and 100M instructions. Each generated job stores
a parameter manifest beside its YAML configuration.

## Hosted cluster workflow

The camera-ready appendix's cluster commands are retained. They require the
private evaluator key supplied separately; the key and generated outputs are
never uploaded to GitHub.

```bash
git clone https://github.com/CMU-SAFARI/MORDOR.git
cd MORDOR
install -m 600 /path/to/provided-private-key credentials/ae_cluster_key
./setup_ae.sh
./reproduce.py cluster submit
./reproduce.py cluster progress
./reproduce.py cluster fetch
.venv/bin/python reproduce.py figures
```

`setup_ae.sh` synchronizes source code, preserves remote traces/results,
downloads and verifies the trace archive when needed, checks Slurm, and builds
Ramulator. `cluster fetch` is completion-gated; use `--allow-incomplete` only
for diagnosis. Interrupted or failed matrices can be resumed safely:

```bash
./reproduce.py cluster resume
```

## Generic Slurm workflow

```bash
python3 -m venv .venv
.venv/bin/python -m pip install \
  -r artifact_evaluation/requirements.txt \
  -r plotting/requirements.txt
cp artifact_evaluation/generic_slurm_config.yaml \
   artifact_evaluation/execution_config.yaml
```

Edit the copied profile for the local Slurm installation, then run:

```bash
.venv/bin/python reproduce.py slurm setup \
  --profile artifact_evaluation/execution_config.yaml
.venv/bin/python reproduce.py slurm plan \
  --profile artifact_evaluation/execution_config.yaml
.venv/bin/python reproduce.py slurm resume \
  --profile artifact_evaluation/execution_config.yaml
.venv/bin/python reproduce.py slurm progress \
  --profile artifact_evaluation/execution_config.yaml
.venv/bin/python reproduce.py figures
```

## Local workflow

The local backend runs the same jobs serially and needs no Slurm installation:

```bash
cp artifact_evaluation/local_config.yaml \
   artifact_evaluation/execution_config.yaml
.venv/bin/python reproduce.py local setup \
  --profile artifact_evaluation/execution_config.yaml
.venv/bin/python reproduce.py local plan \
  --profile artifact_evaluation/execution_config.yaml
.venv/bin/python reproduce.py local resume \
  --profile artifact_evaluation/execution_config.yaml
.venv/bin/python reproduce.py local progress \
  --profile artifact_evaluation/execution_config.yaml
.venv/bin/python reproduce.py figures
```

Omitting `--classes` and `--traces` selects the full paper matrix on every
backend. For a small end-to-end check, append
`--classes main --traces 429.mcf` consistently to plan, resume, and progress.

## Selected experiments and figures

Paper experiment classes are `main`, `multi-prt`, `latency`, `bank-count`,
`blast-radius`, and `drfm-address-setup`.

Figure 6 needs only the `main` class:

```bash
./reproduce.py cluster resume --classes main
./reproduce.py cluster progress --classes main
./reproduce.py cluster fetch --classes main
.venv/bin/python reproduce.py figures -- --figures 6
```

The result hierarchy is:

```text
results/
├── baseline/no_mitigation/<trace>_output.yaml
├── main/{priority,mordor,insecure}/<mechanism>/<trace>_output.yaml
├── prt_sweep/prt_<n>/{priority,mordor}/<mechanism>/<trace>_output.yaml
├── latency/{priority,mordor}/<mechanism>/<trace>_latency.txt
├── bank_count/banks_<n>/{baseline,priority/<mechanism>,mordor/<mechanism>}/
├── blast_radius/brc_2/radius_<n>/{priority,mordor}/<mechanism>/
└── drfm_address_setup/mordor/<mechanism>/
```

The plotting command validates complete cohorts, rebuilds `paper_results/`,
writes `paper_results/manifest.csv`, and emits labelled PNGs under `figures/`.
It never downloads or relies on precomputed paper results.

## Hardware-overhead table (OpenROAD)

The appendix command works unchanged:

```bash
cd mordor_hw_ae
./reproduce_table1.sh
```

This compatibility entry point forwards to `openroad/reproduce_table1.sh`.
Use `--sudo` if Docker requires elevated privileges. Reports are written under
`openroad/out/`. The bundled OpenROAD executable can be checked independently:

```bash
sha256sum -c CHECKSUMS.sha256
```

## Requirements

Simulation requires x86-64 Linux, Python 3.9+, CMake 3.14+, a C++20 compiler,
and about 20 GiB for traces/results. Slurm runs request one CPU and 6 GB RAM.
Hosted orchestration additionally needs OpenSSH and `rsync`. The OpenROAD flow
requires Docker, Docker Buildx, and at least 8 GB RAM.

## Ramulator 2.0 citation

If you use this artifact, please also cite the original Ramulator 2.0 paper:

```bibtex
@article{luo2024ramulator2,
  author  = {Haocong Luo and Yahya Can Tu{\u{g}}rul and F. Nisa Bostanc{\i}
             and Ataberk Olgun and A. Giray Ya{\u{g}}l{\i}k{\c{c}}{\i}
             and Onur Mutlu},
  title   = {{Ramulator 2.0: A Modern, Modular, and Extensible DRAM Simulator}},
  journal = {IEEE Computer Architecture Letters},
  volume  = {23},
  number  = {1},
  pages   = {112--116},
  year    = {2024},
  doi     = {10.1109/LCA.2023.3333759}
}
```
