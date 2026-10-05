# MORDOR code guide

This guide describes the simulator components, configuration parameters,
and experiment workflows used to implement and evaluate MORDOR.
For environment setup and complete paper reproduction, see
[REPRODUCING.md](REPRODUCING.md).

## Implementation entry points

| Component | Source | Role |
| --- | --- | --- |
| Simulator entry point | [main.cpp](ramulator/src/main.cpp) | Loads YAML, constructs components, advances simulation, and prints statistics. |
| Memory controller | [blacklisting_dram_controller.cpp](ramulator/src/dram_controller/impl/blacklisting_dram_controller.cpp) | Implements the `Blacklisting` controller, request queues, and aggressor-row blacklist. |
| Scheduler | [blacklisting_scheduler.cpp](ramulator/src/dram_controller/impl/scheduler/blacklisting_scheduler.cpp) | Implements `FRFCFS_blacklisting`, which considers readiness and blacklist eligibility. |
| DRAM model | [DDR5.cpp](ramulator/src/dram/impl/DDR5.cpp) | Models DDR5 commands and timing. |
| Read disturbance mitigation techniques | [plugin/](ramulator/src/dram_controller/impl/plugin/) | Implements read disturbance mitigation techniques as controller plugins. |
| Hardware design | [mordor_v9.v](openroad/overlay/flow/designs/src/mordor_v9/mordor_v9.v) | Verilog design used in hardware evaluation. |

The DDR5 implementations of the evaluated read disturbance mitigation techniques are
`abacus_ddr5.cpp`, `hydraDDR5.cpp`, `paraDDR5.cpp`, `comet_ddr5.cpp`,
`dapper_ddr5.cpp`, and `graphene_ddr5.cpp` in the plugin directory.

## Configuration and scheduling policies

The [PARA PRT-125 MORDOR configuration](ramulator/ramulator_configs/example_ddr5_config_PARA_125_read.yaml)
and corresponding [Priority Scheduling configuration](ramulator/ramulator_configs/example_ddr5_config_PARA_125_priority.yaml)
illustrate the scheduling policies evaluated in the paper.
Both use the `Blacklisting` controller and `FRFCFS_blacklisting` scheduler.
The read disturbance mitigation technique's plugin selects the queue for
Preventive Refresh Operations (PROs):

| Policy | Plugin settings | Meaning |
| --- | --- | --- |
| Priority Scheduling | `queue_type: priority`, `insecure_read_queue: false` | PROs are prioritized over demand memory requests. |
| MORDOR | `queue_type: read`, `insecure_read_queue: false` | PROs use the read queue with aggressor-row blacklisting. |
| Insecure | `queue_type: read`, `insecure_read_queue: true` | PROs use the read queue without aggressor-row blacklisting; this configuration does not guarantee data integrity. |

In supplied filenames, `_read` identifies MORDOR; generated results use the
policy name `mordor`. Inspect plugin settings as well as filenames when
modifying configurations.

The YAML also selects the frontend, traces, address translation, DDR5
organization and timing, row policy, and read disturbance mitigation technique's
plugin. Plugin thresholds are technique-specific; consult the corresponding
source before changing them.

## Running a custom configuration

Build the simulator using the commands in the [README](README.md#installation).
Copy a supplied configuration and replace `Frontend.traces` with paths to
the workload traces to be evaluated. The supplied `example_inst.trace` is a placeholder.
Use absolute trace paths to make trace location independent of the working
directory.

For a configuration saved as `/path/to/custom.yaml`, run from the repository
root:

```bash
mkdir -p results/custom
ramulator/build/ramulator2 -f /path/to/custom.yaml \
  > results/custom/run_output.yaml
```

The simulator accepts repeated `-p KEY=VALUE` overrides; see
`ramulator/build/ramulator2 --help` and
[config.cpp](ramulator/src/base/config.cpp) for configuration handling.
Direct runs do not automatically apply the experiment workflow's semantic
validation or partial-output promotion. For paper comparisons, use
`reproduce.py` to retain consistent cohort definitions and result checks.

## Extending the reproduction workflow

The public interface is [reproduce.py](reproduce.py), which delegates to
[reproduction/reproduce.py](reproduction/reproduce.py).
[common.py](reproduction/common.py) defines read disturbance mitigation
techniques, experiment classes, and canonical traces.
[run_experiments.py](reproduction/run_experiments.py)
generates jobs and supports local and Slurm execution.
[experiments/](reproduction/experiments/) contains standalone launchers.

An exploratory experiment can be defined by copying a configuration and
modifying the relevant parameters. To include the experiment in a
reproducible study, update the experiment generator and output naming, then
inspect the generated jobs with `plan` before execution.
When adding output statistics, review
[validate_result.py](reproduction/validate_result.py) and the consumers
in [plotting/](plotting/) so they validate and interpret those fields
consistently.

The paper-figure pipeline assumes the canonical study and trace cohorts.
Keep exploratory results in a separate output location when changing those
assumptions. The [reproduction guide](REPRODUCING.md#inspecting-or-running-selected-experiments)
documents the standard result hierarchy and experiment selections.
