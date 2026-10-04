# Cluster experiment workflow

The top-level `../reproduce.py` is the recommended interface. This directory
contains the underlying experiment matrix, job generation, semantic validation,
and one launcher per experiment class.

The hosted profile is `ae_cluster_config.yaml`. It requires the evaluator key
provided separately. Credentials are read from the ignored
`../credentials/ae_cluster_key`. `../setup_ae.sh` uploads the checkout, checks
the remote environment, and builds the simulator without replacing existing
traces or results.

Two native execution profiles are also provided:

- `generic_slurm_config.yaml` runs directly from a checkout on any Slurm
  cluster. Site-specific partition, account, QoS, constraint, time, extra
  `sbatch` arguments, and job preamble settings are optional.
- `local_config.yaml` runs the same jobs serially on one Linux machine and
  limits compiler parallelism to two jobs by default.

Neither native profile requires the hosted-cluster key or access.

Copy the selected template to the ignored `execution_config.yaml` before
customizing it. The top-level README contains complete setup and launch
examples. Native execution writes directly to `../results/`; no SSH upload or
result-fetch step is involved.

For the complete 55-trace matrix on a generic Slurm cluster, run `slurm plan`,
`slurm resume`, and `slurm progress` without `--classes` or `--traces`, always
passing the customized profile. Once complete, run `reproduce.py figures`;
native results are already local, so no fetch command is needed.

The complete local path follows the same sequence with the `local` target:
run `local plan`, `local resume`, and `local progress` without `--classes` or
`--traces`, then run `reproduce.py figures`. Local execution is serial and can
therefore take a very long time.

Available classes:

- `main`: baseline, Priority, MORDOR, and insecure PRT-125 runs.
- `multi-prt`: PRT 250, 500, and 1000 runs.
- `latency`: the five high-PRO, single-core, 100M-instruction runs used by Figure 8.
- `bank-count`: 8-bank and 32-bank sensitivity.
- `blast-radius`: BRC=2 blast radii 2 and 4; radius 1 reuses `main`.
- `drfm-address-setup`: NRH 122 MORDOR with 47.5 ns additional DRFM latency.
Every class evaluates ABACuS alongside Hydra, PARA, CoMeT, DAPPER, and
Graphene. The aggregate classes use the single 55-trace definition in
`common.py`.

Figure 6 alone requires the `main` class. After it finishes, run
`.venv/bin/python reproduce.py figures -- --figures 6` from the repository
root to build the reduced input bundle and emit only the Figure 6 PNG.

Final outputs use semantic directories such as `main/priority/PARA`,
`main/mordor/PARA`, and `main/insecure/PARA`; filenames are simply
`<trace>_output.yaml`. Other classes follow the same policy-first convention
under `prt_sweep`, `latency`, `bank_count`, `blast_radius`, and
`drfm_address_setup`. Every generated job also has a sibling `_manifest.yaml`
recording the nominal/effective NRH, BRC, blast radius, core/instruction count,
scheduler, and whether DRFM address-setup latency is enabled.

For direct operation inside a prepared cluster checkout:

```bash
python artifact_evaluation/run_artifact.py build
python artifact_evaluation/run_experiments.py \
  --repo-root ramulator \
  --trace-dir /path/to/cputraces \
  --workspace-root artifact_workspace \
  --ramulator ramulator/build/ramulator2 \
  --classes main
python artifact_evaluation/run_experiments.py \
  --repo-root ramulator \
  --trace-dir /path/to/cputraces \
  --workspace-root artifact_workspace \
  --ramulator ramulator/build/ramulator2 \
  --classes main --status
python artifact_evaluation/run_experiments.py \
  --repo-root ramulator \
  --trace-dir /path/to/cputraces \
  --workspace-root artifact_workspace \
  --ramulator ramulator/build/ramulator2 \
  --classes main --resume
```

Job generation never submits by default. `--submit` performs a new submission;
`--resume` submits or locally executes only runs without a semantically valid
final result. Local jobs use `--backend local --run-local`; the top-level
`../reproduce.py local run` command supplies those flags.
