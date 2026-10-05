# MORDOR hardware implementation

We model MORDOR's aggressor-row blacklist alongside a memory-controller
request queue to evaluate its area, power, and scheduling-path latency
overheads. The Verilog implementation is provided in
[src/mordor_v9/mordor_v9.v](src/mordor_v9/mordor_v9.v). The evaluation uses
OpenROAD synthesis and place-and-route with the NanGate45 library.

The Preventive Refresh Operation Queue (PROQ) stores outstanding Preventive
Refresh Operations (PROs) issued by read disturbance mitigation techniques.
MORDOR queries the PROQ before scheduling a demand memory request to
prevent an aggressor row from being reactivated while its PRO is pending.
The paper implementation performs this query using a content-addressable
memory (CAM).

## RTL configurations

The `MODE` parameter selects the hardware configuration:

| Mode | Configuration | Role |
| --- | --- | --- |
| `0` | Baseline memory-controller request-queue array | Provides the reference for incremental hardware overhead. |
| `1` | CAM lookup for each request-queue entry | Implements the blacklist query on the scheduling path; used for Table 1. |

The remaining parameters are `MC_ENTRIES` for request-queue capacity,
`PROQ_ENTRIES` for PROQ capacity, and `ADDR_W` for address width. Their default
values are 64, 32, and 24, respectively. The evaluation scripts apply these
parameters through the ORFS `VERILOG_TOP_PARAMS` setting.

The [design configuration](nangate45/mordor_v9/config.mk) and
[timing constraint](nangate45/mordor_v9/constraint.sdc) define the synthesis
and place-and-route environment. The 10 ns clock constraint is used to
measure area and power without imposing a tighter timing constraint.
The synthesized scheduling-path latency is measured separately.

## Table 1 evaluation

The bundled workflow consists of
[mordor_table1_analyze.sh](mordor_table1_analyze.sh),
[mordor_table1_report.sh](mordor_table1_report.sh), and
[mordor_table1.sh](mordor_table1.sh). The analysis script evaluates the baseline
and CAM configurations with PROQ capacities of 32, 48, 64, and 78 entries.
The report expresses MORDOR's hardware overhead relative to the baseline.

Use the Docker wrapper described in the
[hardware reproduction guide](../../../README.md). Inside the prepared
container, the equivalent command from the ORFS `flow/` directory is:

```bash
bash designs/mordor_table1.sh
```

The environment variables `MC`, `PROQS`, and `WORKDIR` select the
memory-controller request-queue capacity, PROQ capacities, and intermediate
result directory. Their defaults are 64, `32 48 64 78`, and
`/tmp/mordor_table1`, respectively. Changing them defines a different
hardware configuration from the default paper evaluation.

## Reports and intermediate results

Within the container, OpenROAD outputs are stored under
`flow/{reports,logs,results}/nangate45/mordor_v9/<variant>/`.
The analysis scripts write intermediate results to `WORKDIR`. The Docker
entry point copies the report, OpenROAD reports and logs, and intermediate
results into the mounted output directory.

The bundled [final-report script](../scripts/final_report.tcl) emits
`report_power`, `report_design_area`, and `report_worst_slack`. The result
extractors depend on these measurements.
