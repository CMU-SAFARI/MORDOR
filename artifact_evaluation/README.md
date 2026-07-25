# Cluster experiment workflow

The top-level `../reproduce.py` is the recommended interface. This directory
contains the underlying experiment matrix, job generation, semantic validation,
and one launcher per experiment class.

The evaluator-facing hosted connection profile is `ae_cluster_config.yaml`.
This path requires an SSH private key supplied separately through the
artifact-evaluation channel; it is only for evaluators authorized to use our
SAFARI infrastructure. Credentials are read from
`../credentials/ae_cluster_key`, which is deliberately excluded from version
control. `../setup_ae.sh` creates that slot when needed, uploads the local
GitHub checkout into the initially empty remote
`/mnt/galactica/aevaluator2/MORDOR`, checks the remote environment, and builds
the simulator. Hosted evaluator commands run from that directory. Re-running
setup updates source files but preserves
`/mnt/galactica/aevaluator2/MORDOR/artifact_workspace`.

Two native execution profiles are also provided:

- `generic_slurm_config.yaml` runs directly from a checkout on any Slurm
  cluster. Site-specific partition, account, QoS, constraint, time, extra
  `sbatch` arguments, and job preamble settings are optional.
- `local_config.yaml` runs the same jobs serially on one Linux machine.

Neither native profile requires the SAFARI SSH key or access to our
infrastructure.

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
- `latency`: the paper's `429.mcf` request-latency runs.
- `bank-count`: 8-bank and 32-bank sensitivity.
- `blast-radius`: BRC-1 blast radii 1, 2, and 8.
- `scheduling`: closed-row caps 4 and 16.

Every class evaluates ABACuS alongside Hydra, PARA, CoMeT, DAPPER, and
Graphene. The aggregate classes use the single 55-trace definition in
`common.py`.

Figure 6 alone requires the `main` and `multi-prt` classes. After those
classes finish, run
`.venv/bin/python reproduce.py figures -- --figures 6` from the repository
root to build the reduced input bundle and emit only the Figure 6 PNG.

Final outputs use semantic directories such as `main/priority/PARA`,
`main/mordor/PARA`, and `main/insecure/PARA`; filenames are simply
`<trace>_output.yaml`. Other classes follow the same policy-first convention
under `prt_sweep`, `latency`, `bank_count`, `blast_radius`, and `row_policy`.

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
