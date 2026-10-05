# Reproducing MORDOR results

We provide two execution backends to reproduce MORDOR's simulation results:
serial execution on a local Linux machine and parallel execution on Slurm.
This guide describes both backends, paper-figure generation, and hardware
evaluation.
The same experiment definitions and semantic validation apply to both
simulation backends. Results are written directly into your workspace.

The experiments evaluate six read disturbance mitigation techniques: PARA,
Hydra, CoMeT, DAPPER, Graphene, and ABACuS. MORDOR schedules their Preventive
Refresh Operations (PROs) while preserving their data integrity guarantees.

## Setup

Clone the repository and create the Python environment:

```bash
git clone https://github.com/CMU-SAFARI/MORDOR.git
cd MORDOR
```

Install the dependencies for simulation orchestration and plotting:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install \
  -r reproduction/requirements.txt \
  -r plotting/requirements.txt
```

## Generic Slurm cluster

Clone the repository on a shared filesystem visible from the Slurm compute
nodes. Copy and edit the generic profile:

```bash
cp reproduction/generic_slurm_config.yaml \
   reproduction/execution_config.yaml
```

Set any site-required `partition`, `account`, `qos`, `constraint`, `time`,
`exclude`, extra `sbatch` arguments, or module commands in
`reproduction/execution_config.yaml`. Empty scheduler fields are omitted
so that the site's defaults apply.

Download and verify the 55 traces, check for Slurm/build dependencies, and
build Ramulator:

```bash
.venv/bin/python reproduce.py slurm setup \
  --profile reproduction/execution_config.yaml
```

Plan a small cohort before submitting it:

```bash
.venv/bin/python reproduce.py slurm plan \
  --profile reproduction/execution_config.yaml \
  --classes main --traces 429.mcf
.venv/bin/python reproduce.py slurm submit \
  --profile reproduction/execution_config.yaml \
  --classes main --traces 429.mcf
```

Use the same class/trace selection when checking or resuming that cohort:

```bash
.venv/bin/python reproduce.py slurm progress \
  --profile reproduction/execution_config.yaml \
  --classes main --traces 429.mcf
.venv/bin/python reproduce.py slurm resume \
  --profile reproduction/execution_config.yaml \
  --classes main --traces 429.mcf
```

To run the complete paper matrix across all 55 traces on this Slurm cluster,
omit both `--classes` and `--traces`:

```bash
.venv/bin/python reproduce.py slurm plan \
  --profile reproduction/execution_config.yaml
.venv/bin/python reproduce.py slurm resume \
  --profile reproduction/execution_config.yaml
.venv/bin/python reproduce.py slurm progress \
  --profile reproduction/execution_config.yaml
```

The `resume` command submits only jobs with missing or invalid results and
skips jobs that are already active or have validated outputs. It can be used
for both the initial submission and subsequent restarts. The `submit`
command performs an unconditional submission.

The results are already local in `results/`, so this path has no fetch step.
After `progress` reports the complete matrix as valid, generate Figures 2 and
5–14:

```bash
.venv/bin/python reproduce.py figures
```

To plot only selected traces, pass their exact names to the figure generator:

```bash
.venv/bin/python reproduce.py figures --traces 429.mcf 470.lbm -- --figures 2
```

This rebuilds `paper_results/` with only the selected traces and uses that same
cohort consistently for Figure 2. Figure 6 ranks the 25 workloads with the
highest PRO intensity and requires at least 25 complete traces. Omit
`--traces` to retain the 55-workload paper cohort for complete reproduction.

## Long-running local execution

The local backend executes simulations serially and does not require Slurm.
Copy its profile:

```bash
cp reproduction/local_config.yaml \
   reproduction/execution_config.yaml
```

The local profile limits the build to two concurrent compiler jobs to reduce
peak memory use. Set `local.build_jobs` to `1` for the lowest-memory build, or
raise it if the host has sufficient RAM.

Prepare the traces and simulator, then plan and run a small cohort:

```bash
.venv/bin/python reproduce.py local setup \
  --profile reproduction/execution_config.yaml
.venv/bin/python reproduce.py local plan \
  --profile reproduction/execution_config.yaml \
  --classes main --traces 429.mcf
.venv/bin/python reproduce.py local run \
  --profile reproduction/execution_config.yaml \
  --classes main --traces 429.mcf
```

To run the complete paper matrix across all 55 traces locally, omit both
`--classes` and `--traces`. First review the complete plan:

```bash
.venv/bin/python reproduce.py local plan \
  --profile reproduction/execution_config.yaml
```

The `resume` command executes simulations with missing or invalid outputs
and retains validated results. For execution in the background:

```bash
nohup .venv/bin/python -u reproduce.py local resume \
  --profile reproduction/execution_config.yaml \
  > local-run.log 2>&1 &
```

Monitor it from another terminal:

```bash
.venv/bin/python reproduce.py local progress \
  --profile reproduction/execution_config.yaml
```

An interrupt terminates the active local job while preserving completed
outputs. The complete configuration contains 6,165 simulations and can take a
substantial time on a single machine. Use `--classes` and `--traces` to
evaluate a subset of the experiment matrix.

The results are already local in `results/`, so this path has no fetch step.
After `progress` reports the complete matrix as valid, generate Figures 2 and
5–14:

```bash
.venv/bin/python reproduce.py figures
```

## Full matrix for one trace

To exercise every read disturbance mitigation technique and experiment class
for one trace without running the complete 55-trace evaluation:

```bash
.venv/bin/python reproduce.py local plan --traces 401.bzip2
.venv/bin/python reproduce.py local resume --traces 401.bzip2
.venv/bin/python reproduce.py local progress --traces 401.bzip2
```

This produces 123 jobs: one for each configuration-level case. `resume` skips
valid results and active jobs on Slurm. Use the same `--traces` selection when
checking progress. Use `slurm` instead of `local` and pass your `--profile` to
run this cohort on a Slurm installation.

Omitting `--traces` always restores the canonical paper cohorts: 55 traces for
aggregate studies and five high-PRO workloads for latency.

## Inspecting or running selected experiments

Generate the complete job plan without submitting it:

```bash
.venv/bin/python reproduce.py local plan
```

Individual experiment types can be selected with `--classes`, for example:

```bash
.venv/bin/python reproduce.py local plan --classes main latency blast-radius
```

Each experiment type also has a standalone launcher under
`reproduction/experiments/`.

Every job writes a `.partial` output first. The output is renamed to its final
name only after Ramulator exits successfully and the required cycle, energy, or
latency fields pass semantic validation. `status` returns success only when the
selected cohort is complete; `resume` runs or submits only missing or invalid jobs.

Results use semantic policy names:

```text
results/
├── baseline/no_mitigation/<trace>_output.yaml
├── main/{priority,mordor,insecure}/<technique>/<trace>_output.yaml
├── prt_sweep/prt_<n>/{priority,mordor}/<technique>/<trace>_output.yaml
├── latency/{priority,mordor}/<technique>/<trace>_latency.txt
├── bank_count/banks_<n>/{baseline,priority/<technique>,mordor/<technique>}/
├── blast_radius/brc_2/radius_<n>/{priority,mordor}/<technique>/
└── drfm_address_setup/mordor/<technique>/
```

Here `priority` denotes Priority Scheduling of PROs, `mordor` denotes MORDOR
scheduling of PROs with aggressor-row blacklisting, and `insecure` denotes
the Insecure configuration, which schedules PROs in the read queue without
aggressor-row blacklisting.
The directory hierarchy records the configuration, so result filenames contain
only the trace name.

The aggregate studies use the 55 paper workloads. The latency study uses
`429.mcf`, `470.lbm`, `random_10.trace`, `stream_10.trace`, and
`549.fotonik3d`, each with one core and 100 million instructions.
The blast-radius study uses BRC 2 and radii 2 and 4; radius 1 uses the
main-study results.

Plotting rebuilds the compact `paper_results/` tree from `results/`
and writes labelled PNGs for data-derived Figures 2 and 5–14 to `figures/`.
Conceptual Figures 1, 3, and 4 are not generated by this workflow.

## Reproduce area and power locally

Run the OpenROAD experiment on the local x86-64 Linux machine:

```bash
./reproduce.py openroad -- --sudo
```

Omit `--sudo` where the current user already has Docker access. OpenROAD
reports are written beneath `openroad/out/`.

## Requirements

Simulation requires an x86-64 Linux host, CMake 3.14 or newer, a C++20
compiler, Python 3.9 or newer, PyYAML, outbound HTTPS access to Zenodo, and
approximately 10 GB free space while the traces are downloaded and extracted
(approximately 7.5 GB remains afterward). The simulator's C++ dependencies
are vendored. Each Slurm simulation requests one CPU and 6 GB memory by
default and requires no GPU. Local execution runs one simulation at a time.

Slurm execution additionally requires `sbatch` and `squeue`, and a checkout
and workspace accessible to the compute nodes. Customize the profile to
match your installation's scheduling and module requirements.

Local plotting is lightweight. Hardware evaluation requires Docker Engine
with a running daemon, Docker socket access (directly or through `--sudo`),
x86-64 Linux, at least 8 GB RAM, and approximately 10 GB free disk space.
Docker Buildx is recommended.

## Plotting and hardware paths

The default output and tool paths are specified in
[`reproduction/reproduction_config.yaml`](reproduction/reproduction_config.yaml).
To customize them, copy the file to the ignored
`reproduction/reproduction_override.yaml` and pass it before the target:

```bash
cp reproduction/reproduction_config.yaml \
   reproduction/reproduction_override.yaml
# Edit reproduction_override.yaml before running:
.venv/bin/python reproduce.py \
  --config reproduction/reproduction_override.yaml figures
```

Paths are resolved relative to the repository root; absolute paths are also
accepted. If your execution profile changes `paths.workspace_root`, set
`paths.results_root` in the reproduction configuration to that workspace's
`results/` directory. The same configuration selects the OpenROAD directory.

## Reduced Figure 6 reproduction

Figure 6 requires the `main` class. After local setup, run:

```bash
.venv/bin/python reproduce.py local resume --classes main
.venv/bin/python reproduce.py local progress --classes main
.venv/bin/python reproduce.py figures -- --figures 6
```

For Slurm, replace `local` with `slurm` and pass your `--profile`.
Run plotting after all selected simulations are valid. This builds only
Figure 6's inputs in `paper_results/` and writes
`figures/Figure_06_top25_per_trace_speedup.png`.
