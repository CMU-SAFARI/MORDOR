# Experiment workflow

We provide a common interface, `../reproduce.py`, for the simulation
experiments. This directory contains the experiment definitions, job
generation and execution scripts, result validation, and a launcher for each
experiment class.

The experiments compare scheduling policies for Preventive Refresh Operations
(PROs) issued by read disturbance mitigation techniques.

Two execution profiles are provided:

- `generic_slurm_config.yaml` runs directly from a checkout on any Slurm
  cluster. Site-specific partition, account, QoS, constraint, time, extra
  `sbatch` arguments, and job preamble settings are optional.
- `local_config.yaml` runs the same jobs serially on one Linux machine and
  limits compiler parallelism to two jobs by default.

Copy the selected template to the ignored `execution_config.yaml` before
customizing it. The top-level [reproduction guide](../REPRODUCING.md) contains
complete setup and launch examples. Both backends write directly to the
workspace’s `results/` directory.

For the complete 55-trace matrix on a generic Slurm cluster, run `slurm plan`,
`slurm resume`, and `slurm progress` without `--classes` or `--traces`, always
passing the customized profile. Once complete, run `reproduce.py figures`;
results are already in the workspace.

The complete local path follows the same sequence with the `local` target:
run `local plan`, `local resume`, and `local progress` without `--classes` or
`--traces`, then run `reproduce.py figures`. Local execution is serial and can
therefore take a very long time.

Available classes:

- `main`: the baseline without read disturbance mitigation, Priority
  Scheduling, MORDOR, and Insecure configurations at nominal RowHammer threshold 125.
- `multi-prt`: nominal RowHammer thresholds of 250, 500, and 1000.
- `latency`: demand memory request and PRO latency measurements for five
  high-PRO workloads, each with one core and 100 million instructions.
- `bank-count`: 8-bank and 32-bank sensitivity.
- `blast-radius`: BRC 2 with blast radii 2 and 4; radius 1 uses `main`.
- `drfm-address-setup`: MORDOR with an effective threshold of 122 and
  47.5 ns additional DRFM latency at nominal RowHammer threshold 125.

Every class evaluates six read disturbance mitigation techniques: ABACuS,
Hydra, PARA, CoMeT, DAPPER, and Graphene. The aggregate classes use the single
55-trace definition in `common.py`.

Figure 6 alone requires the `main` class. After that
class finishes, run
`.venv/bin/python reproduce.py figures -- --figures 6` from the repository
root to build the reduced input bundle and emit only the Figure 6 PNG.

Final outputs use semantic directories such as `main/priority/PARA`,
`main/mordor/PARA`, and `main/insecure/PARA`; filenames are simply
`<trace>_output.yaml`. Other classes follow the same policy-first convention
under `prt_sweep`, `latency`, `bank_count`, `blast_radius`, and
`drfm_address_setup`. Each generated job has a sibling `_manifest.yaml`
recording the nominal and effective RowHammer thresholds, BRC, blast radius,
core and instruction counts, scheduler, and DRFM address-setup settings.

For direct operation inside a prepared cluster checkout:

```bash
python reproduction/run_reproduction.py build
python reproduction/run_experiments.py \
  --repo-root ramulator \
  --trace-dir /path/to/cputraces \
  --workspace-root reproduction_workspace \
  --ramulator ramulator/build/ramulator2 \
  --classes main
python reproduction/run_experiments.py \
  --repo-root ramulator \
  --trace-dir /path/to/cputraces \
  --workspace-root reproduction_workspace \
  --ramulator ramulator/build/ramulator2 \
  --classes main --status
python reproduction/run_experiments.py \
  --repo-root ramulator \
  --trace-dir /path/to/cputraces \
  --workspace-root reproduction_workspace \
  --ramulator ramulator/build/ramulator2 \
  --classes main --resume
```

Job generation never submits by default. `--submit` performs a new submission;
`--resume` submits or locally executes only runs without a semantically valid
final result. Local jobs use `--backend local --run-local`; the top-level
`../reproduce.py local run` command supplies those flags.
