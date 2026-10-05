# MORDOR hardware result reproduction

We evaluate MORDOR's hardware overhead using Verilog, OpenROAD synthesis,
and place-and-route with the NanGate45 technology library. This directory
provides the implementation and workflow used to reproduce the area, static
power, dynamic power, and scheduling-path latency results in Table 1.
The power measurements also contribute to the hardware energy overhead
reported in Figure 5.

The Preventive Refresh Operation Queue (PROQ) stores outstanding Preventive
Refresh Operations (PROs) issued by read disturbance mitigation techniques
and serves as MORDOR's aggressor-row blacklist. We implement the PROQ as a
content-addressable memory (CAM) to determine whether a demand memory
request targets a blacklisted aggressor row.

The Docker environment uses a pinned OpenROAD-flow-scripts (ORFS) image,
the bundled MORDOR design files, and the OpenROAD executable used for the
paper evaluation. The host wrapper verifies the executable's checksum
before building the image. See [VALIDATE_TABLE1.md](VALIDATE_TABLE1.md) for
numerical reference results and validation instructions.

## Requirements

Hardware evaluation requires an x86-64 Linux host, Docker Engine with a
running daemon, at least 8 GB RAM, and approximately 10 GB free disk space.
Internet access is required for the initial image build. Docker Buildx is
recommended. The container supplies the synthesis tools and technology
library; a local OpenROAD or PDK installation is not required.

## Reproduction procedure

Run the following command from the `openroad/` directory:

```bash
./reproduce_table1.sh
```

The wrapper builds the image, executes the evaluation, and records the
console output in `out/run.log`. The default evaluation includes a baseline
memory-controller request queue and four CAM implementations with PROQ
capacities of 32, 48, 64, and 78 entries.

Use `--quick` to evaluate only the 32-entry PROQ, `--skip-build` to reuse an
existing image, or `--sudo` when Docker requires elevated privileges:

```bash
./reproduce_table1.sh --quick
./reproduce_table1.sh --skip-build
./reproduce_table1.sh --sudo
```

The equivalent manual procedure is:

```bash
docker build -t mordor-hw .
mkdir -p out
docker run --rm -v "$PWD/out:/out" mordor-hw
```

The initial image build typically takes 10–20 minutes. The complete hardware
evaluation typically takes 2–2.5 hours; the 32-entry PROQ evaluation takes
approximately 20 minutes. Execution time depends on the host system.

## Evaluation scripts

The scripts in `overlay/flow/designs/` separate analysis from reporting:

| Script | Function |
| --- | --- |
| `mordor_table1_analyze.sh` | Performs synthesis and place-and-route for the selected design points. Existing completed builds are retained. |
| `mordor_table1_report.sh [-o FILE]` | Extracts measurements and produces the report from existing results. The default output is `mordor_table1_report.txt`. |
| `mordor_table1.sh [-o FILE]` | Executes analysis followed by report generation. |

See the [hardware implementation guide](overlay/flow/designs/mordor_README.md)
for the RTL parameters.

## Hardware measurements and scaling

The report is written to `out/mordor_table1_output.txt`. It reports the
incremental overhead of MORDOR relative to the baseline memory-controller
request queue, including the synthesized register-to-`ready_o` path latency.
The report scales the raw 45 nm measurements to 14 nm using the paper's
DeepScaleTool factors: 12.5 for area, 2.438 for power, and 1.35 for delay.
Area and power are reported for six memory channels, with one MORDOR
instance per channel. Scheduling-path latency remains a per-instance value.
The report also includes PROQ CAM capacity and area as a fraction of the
698 mm² processor area used for normalization.

Compare the generated values with the hardware-overhead table in the
camera-ready paper. Raw OpenROAD reports and logs are stored under
`out/openroad_raw/`, and intermediate results are copied to
`out/raw_workdir/`. No precomputed reference report is included.
