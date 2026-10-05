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
| `mordor_table1_analyze.sh [--blocked-bit]` | Performs synthesis and place-and-route for the selected design points. Existing completed builds are retained. |
| `mordor_table1_report.sh [--blocked-bit] [-o FILE]` | Extracts measurements and produces the report from existing results. The default output is `mordor_table1_report.txt`. |
| `mordor_table1.sh [--blocked-bit] [-o FILE]` | Executes analysis followed by report generation. |

See the [hardware implementation guide](overlay/flow/designs/mordor_README.md)
for the RTL parameters and supplementary design.

## Hardware measurements and scaling

The report is written to `out/mordor_table1_output.txt`. It reports the
incremental overhead of MORDOR relative to the baseline memory-controller
request queue, including the synthesized register-to-`ready_o` path latency.
Three sets of results are provided:

- **45 nm:** measurements obtained with the NanGate45 library.
- **14 nm:** estimates obtained by dividing the 45 nm measurements by the
  DeepScaleTool factors used in the paper: 12.5 for area, 2.438 for power,
  3.316 for energy, and 1.35 for delay.
- **14 nm with six memory channels:** area and power estimates for one
  MORDOR instance per channel. Area and power scale with the number of
  channels; scheduling-path latency and energy per lookup remain per instance.

Table 1 uses the 14 nm results for six memory channels. Raw OpenROAD reports
and logs are stored under `out/openroad_raw/`, and intermediate results are
copied to `out/raw_workdir/`.

## Supplementary blocked-bit implementation

The `--blocked-bit` option additionally evaluates an alternative
implementation with one blocked bit per memory-controller request-queue
entry and a PROQ modeled as a FIFO/RAM with a single-port installation CAM.
This implementation is supplementary and is not used for the paper's
Table 1 results. CACTI is used only for this supplementary analysis.

```bash
./reproduce_table1.sh --blocked-bit
```

Its results appear after the `SUPPLEMENTARY` heading in the report.
For a comparison with the complete reference report, including this
supplementary implementation:

```bash
diff out/mordor_table1_output.txt expected_output.txt
```

For the default evaluation, compare the paper results without the
supplementary section as described in [VALIDATE_TABLE1.md](VALIDATE_TABLE1.md).
