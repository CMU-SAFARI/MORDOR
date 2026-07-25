# MORDOR reproduction artifact

This repository is a standalone reproduction package. It contains the source,
configuration, orchestration, plotting, and OpenROAD files needed to reproduce
the MORDOR paper results.

CPU traces and generated results are intentionally not stored in the
repository. The setup workflows download and verify the canonical traces, and
validated outputs are written into the ignored local `results/` directory.

## Contents

- `ramulator/`: clean Ramulator/MORDOR source, dependencies, and experiment
  configurations.
- `artifact_evaluation/`: per-experiment Slurm launchers, semantic result
  validation, status/resume support, and SSH orchestration.
- `plotting/`: the self-contained paper-figure generator, canonical Python
  plotting sources, and plotting dependency list.
- `openroad/`: the self-contained area and power reproduction artifact.
- `reproduce.py`: the top-level local entry point.

The OpenROAD reproduction script automatically verifies the bundled executable
before building its Docker image. It can also be checked manually with:

```bash
sha256sum -c CHECKSUMS.sha256
```

## Choose an evaluation path

Three execution paths are supported:

1. **Hosted SAFARI infrastructure:** the shortest evaluator path, but it
   requires an SSH private key supplied separately through the
   artifact-evaluation channel. The key grants access to our evaluation account
   and is intentionally neither included in nor downloadable from this
   repository.
2. **Generic Slurm cluster:** for evaluators with access to another Slurm
   installation. This path does not require the SAFARI SSH key or access to our
   infrastructure.
3. **Local execution:** for running directly on an x86-64 Linux machine without
   Slurm. This path also requires no SAFARI credentials, but the complete
   experiment is extremely long.

All three paths use the same experiment definitions and semantic result
validation. The hosted path is described immediately below; the independent
Slurm and local alternatives follow it.

## Hosted evaluator quick start (SSH key required)

Clone the artifact from GitHub, enter the checkout, and save the private key
provided privately through the artifact-evaluation channel as:

```bash
git clone https://github.com/CMU-SAFARI/MORDOR.git
cd MORDOR

install -m 600 /path/to/provided-private-key credentials/ae_cluster_key
```

Prepare both the local plotting environment and the initially empty remote
`/mnt/galactica/aevaluator2/MORDOR` directory:

```bash
./setup_ae.sh
```

If the key file does not exist, the first invocation creates an empty,
permission-restricted slot and tells the evaluator to copy the key into it.
Evaluators who have not received this key should use one of the alternative
execution configurations below.

Setup synchronizes the local GitHub checkout to the cluster, excluding the SSH
key and every generated output. All hosted evaluator commands run from
`/mnt/galactica/aevaluator2/MORDOR`. Setup downloads the canonical trace archive
from Zenodo when `/mnt/galactica/aevaluator2/MORDOR/cputraces/` is absent,
verifies its SHA-256 checksum, and safely extracts exactly the 55 paper traces.
It then verifies SSH access, Slurm and build dependencies, workspace write
access, and the Ramulator build. Re-running setup updates the remote source to
match the local checkout while preserving the remote `artifact_workspace/` and
`cputraces/`. For a Git checkout, setup requires a clean working tree and
records the exact commit in
`/mnt/galactica/aevaluator2/MORDOR/.artifact_source_revision`.

Submit the complete experiment matrix:

```bash
./reproduce.py cluster submit
```

Check progress at any time and resume missing or invalid jobs:

```bash
./reproduce.py cluster progress
./reproduce.py cluster resume
```

Once progress reports that every selected result is valid, synchronize results
and generate the data-derived paper figures:

```bash
./reproduce.py cluster fetch
.venv/bin/python reproduce.py figures
```

`cluster fetch` is completion-gated. It refuses to present an incomplete
experiment as a final reproduction; `--allow-incomplete` is available for
diagnosis.

### Reduced Figure 6-only path

Figure 6 requires only the no-mitigation baseline, the PRT-125 Priority and
MORDOR results, and the PRT 250/500/1000 sweep. On the hosted infrastructure,
run only the corresponding `main` and `multi-prt` experiment classes:

```bash
./reproduce.py cluster resume --classes main multi-prt
./reproduce.py cluster progress --classes main multi-prt
./reproduce.py cluster fetch --classes main multi-prt
.venv/bin/python reproduce.py figures -- --figures 6
```

The last command rebuilds a compact `paper_results/` containing only Figure
6's inputs and writes only
`figures/Figure_06_overheads_across_prt.png`. The `main` class also evaluates
its standard insecure controls, but those results are neither required nor
copied into the Figure 6 bundle.

The same reduced selection works on the independent backends: substitute
`slurm` for `cluster` and omit the fetch step, or run
`local resume --classes main multi-prt` with the local profile. In every case,
use the same class selection for `progress` or `status`.

## Alternative execution configurations

These alternatives are independent of the hosted SAFARI account and require no
SSH key for our infrastructure. The same experiment generator and semantic
result validation can run directly on another Slurm cluster or on one local
Linux host. All three configurations produce the same `results/` layout
consumed by the plotting command.

Create the Python environment once for either alternative:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install \
  -r artifact_evaluation/requirements.txt \
  -r plotting/requirements.txt
```

### Generic Slurm cluster

Clone the repository on a shared filesystem visible from the Slurm compute
nodes. Copy and edit the generic profile:

```bash
cp artifact_evaluation/generic_slurm_config.yaml \
   artifact_evaluation/execution_config.yaml
```

Set any site-required `partition`, `account`, `qos`, `constraint`, `time`,
`exclude`, extra `sbatch` arguments, or module commands in
`artifact_evaluation/execution_config.yaml`. Empty scheduler fields are omitted
so that the site's defaults apply.

Download and verify the 55 traces, check for Slurm/build dependencies, and
build Ramulator:

```bash
.venv/bin/python reproduce.py slurm setup \
  --profile artifact_evaluation/execution_config.yaml
```

Plan a small cohort before submitting it:

```bash
.venv/bin/python reproduce.py slurm plan \
  --profile artifact_evaluation/execution_config.yaml \
  --classes main --traces 429.mcf
.venv/bin/python reproduce.py slurm submit \
  --profile artifact_evaluation/execution_config.yaml \
  --classes main --traces 429.mcf
```

Use the same class/trace selection when checking or resuming that cohort:

```bash
.venv/bin/python reproduce.py slurm progress \
  --profile artifact_evaluation/execution_config.yaml \
  --classes main --traces 429.mcf
.venv/bin/python reproduce.py slurm resume \
  --profile artifact_evaluation/execution_config.yaml \
  --classes main --traces 429.mcf
```

To run the complete paper matrix across all 55 traces on this Slurm cluster,
omit both `--classes` and `--traces`:

```bash
.venv/bin/python reproduce.py slurm plan \
  --profile artifact_evaluation/execution_config.yaml
.venv/bin/python reproduce.py slurm resume \
  --profile artifact_evaluation/execution_config.yaml
.venv/bin/python reproduce.py slurm progress \
  --profile artifact_evaluation/execution_config.yaml
```

`resume` is safe for the initial launch and subsequent restarts: it submits
only missing or invalid jobs and skips valid or active ones. Use `slurm submit`
instead when an unconditional fresh submission is specifically desired.

The results are already local in `results/`, so this path has no fetch step.
After `progress` reports the complete matrix as valid, generate Figures 2 and
5–14:

```bash
.venv/bin/python reproduce.py figures
```

To plot only selected traces, pass their exact names to the figure generator:

```bash
.venv/bin/python reproduce.py figures --traces 429.mcf 470.lbm
```

This rebuilds `paper_results/` with only the selected traces and uses that same
cohort consistently across the generated figures. Omit `--traces` to retain
the canonical 55-trace paper cohort.

### Long-running local execution

The local backend needs no Slurm installation. It runs one simulation at a
time to keep the execution path predictable and resource usage conservative.
Copy its profile:

```bash
cp artifact_evaluation/local_config.yaml \
   artifact_evaluation/execution_config.yaml
```

The local profile limits the build to two concurrent compiler jobs to reduce
peak memory use. Set `local.build_jobs` to `1` for the lowest-memory build, or
raise it if the host has sufficient RAM.

Prepare the traces and simulator, then plan and run a small cohort:

```bash
.venv/bin/python reproduce.py local setup \
  --profile artifact_evaluation/execution_config.yaml
.venv/bin/python reproduce.py local plan \
  --profile artifact_evaluation/execution_config.yaml \
  --classes main --traces 429.mcf
.venv/bin/python reproduce.py local run \
  --profile artifact_evaluation/execution_config.yaml \
  --classes main --traces 429.mcf
```

To run the complete paper matrix across all 55 traces locally, omit both
`--classes` and `--traces`. First review the complete plan:

```bash
.venv/bin/python reproduce.py local plan \
  --profile artifact_evaluation/execution_config.yaml
```

Then start the serial run. `resume` is safe for both the initial launch and
every restart: it skips semantically valid outputs and reruns incomplete ones.
For an unattended run:

```bash
nohup .venv/bin/python -u reproduce.py local resume \
  --profile artifact_evaluation/execution_config.yaml \
  > local-run.log 2>&1 &
```

Monitor it from another terminal:

```bash
.venv/bin/python reproduce.py local progress \
  --profile artifact_evaluation/execution_config.yaml
```

An interrupt terminates the active local job while preserving completed
outputs. The complete configuration contains 7,767 simulations and can take a
very long time on one machine; use `--classes` and `--traces` when a smaller
evaluation is sufficient.

The results are already local in `results/`, so this path has no fetch step.
After `progress` reports the complete matrix as valid, generate Figures 2 and
5–14:

```bash
.venv/bin/python reproduce.py figures
```

### Small Slurm smoke test

Before submitting the complete matrix, launch ten representative paper jobs:

```bash
./smoke_test_slurm.sh
```

The safe default is `resume`: it submits only missing PARA/`401.bzip2` jobs
from the main and blast-radius studies and skips completed or active jobs.
Inspect them with:

```bash
./smoke_test_slurm.sh queue
./smoke_test_slurm.sh status
```

After all ten jobs are valid, synchronize and verify the smoke outputs:

```bash
./fetch_smoke_results.sh
```

This permits the intentionally incomplete full cohort and verifies that the ten
expected outputs arrived. It does not run plotting.

After the complete experiment matrix finishes, use the completion-gated fetch:

```bash
./fetch_results.sh
```

It refuses to download an incomplete selected cohort. Additional cluster-fetch
arguments can be passed directly, such as
`./fetch_results.sh --classes main latency`.

Use `./smoke_test_slurm.sh plan` to generate the same ten jobs without
submitting them.

### Full matrix for one trace

To exercise every mechanism and experiment class for one trace without running
the complete 55-trace evaluation:

```bash
./reproduce.py cluster plan --traces 401.bzip2
./reproduce.py cluster resume --traces 401.bzip2
./reproduce.py cluster progress --traces 401.bzip2
```

This produces 153 jobs: one for each configuration-level case. `resume` is
recommended because it skips valid or currently active results. Use the same
`--traces` selection when checking progress or fetching:

```bash
./fetch_results.sh --traces 401.bzip2
```

Omitting `--traces` always restores the canonical paper cohorts: 55 traces for
aggregate studies and only `429.mcf` for latency.

## Inspecting or running selected experiments

Generate the complete job plan without submitting it:

```bash
./reproduce.py cluster plan
```

Individual experiment types can be selected with `--classes`, for example:

```bash
./reproduce.py cluster plan --classes main latency blast-radius
```

Each experiment type also has a standalone launcher under
`artifact_evaluation/experiments/`.

Every job writes a `.partial` output first. The output is renamed to its final
name only after Ramulator exits successfully and the required cycle, energy, or
latency fields pass semantic validation. `status` returns success only when the
selected cohort is complete; `resume` submits only missing or invalid runs.

Results use semantic policy names:

```text
results/
├── baseline/no_mitigation/<trace>_output.yaml
├── main/{priority,mordor,insecure}/<mechanism>/<trace>_output.yaml
├── prt_sweep/prt_<n>/{priority,mordor}/<mechanism>/<trace>_output.yaml
├── latency/{priority,mordor}/<mechanism>/<trace>_latency.txt
├── bank_count/banks_<n>/{baseline,priority/<mechanism>,mordor/<mechanism>}/
├── blast_radius/brc_1/radius_<n>/{priority,mordor}/<mechanism>/
└── row_policy/cap_<n>/{priority,mordor}/<mechanism>/
```

Here `priority` means priority scheduling, `mordor` means the secure MORDOR
policy, and `insecure` means the read-queue configuration without blacklisting.
The directory hierarchy records the configuration, so result filenames contain
only the trace name.

The aggregate studies use exactly the canonical 55 paper traces. The latency
study uses only `429.mcf`. The blast-radius study directly configures BRC 1 and
blast radii 1, 2, and 8.

Plotting rebuilds the compact `paper_results/` tree from synchronized `results/`
and writes labelled PNGs for data-derived Figures 2 and 5–14 to `figures/`.
Conceptual Figures 1, 3, and 4 and the unpublished paper PDF are intentionally
not included in the public artifact.

## Reproduce area and power locally

Run the OpenROAD experiment on the local x86-64 Linux machine:

```bash
./reproduce.py openroad -- --sudo
```

Omit `--sudo` where the current user already has Docker access. OpenROAD
reports are written beneath `openroad/out/`.

## Requirements

The hosted and generic cluster configurations require Slurm, CMake 3.14 or
newer, a C++20 compiler, Python 3.9 or newer, PyYAML, outbound HTTPS access to
Zenodo, and approximately 10 GB of free space while the trace archive is
downloaded and extracted (approximately 7.5 GB remains afterward). The
simulator's C++ dependencies are vendored, so the remote build does not
download them. Each Slurm simulation requests one CPU and 6 GB of memory and
requires no GPU.

The hosted-cluster orchestration machine additionally requires SSH and `rsync`.
Native local simulation requires the same compiler, CMake, Python, trace
storage, and simulator runtime resources as a compute node, but not Slurm.
Local plotting is lightweight. The local OpenROAD run requires Docker Engine
with a running daemon, Docker socket access (directly or through `--sudo`),
x86-64 Linux, at least 8 GB of RAM, and approximately 10 GB of free disk space.
Docker Buildx is recommended because Docker's legacy image builder is
deprecated.
