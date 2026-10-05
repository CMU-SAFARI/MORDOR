# Validating MORDOR hardware results

This directory reproduces the area, static power, dynamic power, and
scheduling-path latency measurements of the camera-ready MORDOR paper.
The Preventive Refresh Operation Queue (PROQ) stores outstanding Preventive
Refresh Operations (PROs) issued by read disturbance mitigation techniques.

## Host requirements

Use an x86-64 Linux host with Docker Engine, at least 8 GB RAM, and
approximately 10 GB free disk space. Internet access is required for the
initial image build. Verify the host environment:

```bash
uname -m
docker --version
free -h
df -h .
```

## Execute the evaluation

From the `openroad/` directory, run:

```bash
./reproduce_table1.sh
```

The wrapper verifies the bundled OpenROAD executable, builds the pinned
Docker environment, and runs the baseline and CAM configurations with PROQ
capacities of 32, 48, 64, and 78 entries. Use `--sudo` if Docker requires
elevated privileges, or `--quick` for the 32-entry PROQ configuration only.
The complete evaluation typically takes 2–2.5 hours.

The equivalent manual procedure is:

```bash
docker build -t mordor-hw .
mkdir -p out
docker run --rm -v "$PWD/out:/out" mordor-hw |& tee out/run.log
```

## Compare the measurements

The report is written to `out/mordor_table1_output.txt`. It includes PROQ
capacity, CAM storage, area, percentage of processor area, static power,
dynamic power, and scheduling-path latency. Area and power are scaled to
14 nm and six memory channels; latency is reported per instance.

Compare the numerical values with the hardware-overhead table in the
camera-ready paper. The report must contain one numerical row for each
selected PROQ capacity:

```bash
grep -E '^[[:space:]]*(32|48|64|78)[[:space:]]' out/mordor_table1_output.txt
```

A complete evaluation contains all four rows. A `--quick` evaluation
contains only the row for 32 entries. No precomputed reference report is
included in this version.

## Inspect execution logs

Inspect `out/run.log` (or `out/run-p32.log` for `--quick`) for `[FAIL]`,
rendering errors, and missing numerical values. Raw reports and logs are
available under:

```text
out/openroad_raw/reports/
out/openroad_raw/logs/
out/raw_workdir/
```

See [README.md](README.md) for the workflow and scaling factors.
