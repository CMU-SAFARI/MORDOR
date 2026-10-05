# Validating MORDOR Table 1

This directory reproduces the area, static power, dynamic power, and access
latency values reported in Table 1 of the MORDOR paper.

PROQ denotes the Preventive Refresh Operation Queue, which stores outstanding
Preventive Refresh Operations (PROs) issued by read disturbance mitigation
techniques.

## 1. Check the host

Use an x86-64 Linux machine with:

- Docker and internet access for the initial image build
- at least 8 GB of available RAM
- approximately 10 GB of free disk space
- preferably multiple CPU cores

No local OpenROAD, Yosys, PDK, CACTI, or GPU installation is required.

Verify the basic requirements:

```bash
uname -m                 # expected: x86_64
docker --version
free -h
df -h .
```

If Docker reports a permission error, use `sudo docker` in the commands below
or obtain Docker access from the system administrator.

## 2. Build the pinned environment

Run the complete evaluation from the `openroad/` directory:

```bash
./reproduce_table1.sh
```

This wrapper builds the image, ensures that `out/` exists, runs the full
experiment, and writes the console output to `out/run.log`. Use
`./reproduce_table1.sh --sudo` if Docker requires elevated privileges.

The equivalent manual build command is:

```bash
docker build -t mordor-hw .
```

The first build normally takes 10–20 minutes, primarily to download the pinned
OpenROAD-flow-scripts image.

## 3. Run the paper experiment

```bash
mkdir -p out

docker run --rm \
  -v "$PWD/out:/out" \
  mordor-hw |& tee out/run.log
```

The full run performs five synthesis and place-and-route flows—one baseline and
four CAM-on-path designs—and normally takes 2–2.5 hours.

For a shorter functional check using only PROQ size 32:

```bash
docker run --rm \
  -v "$PWD/out:/out" \
  -e PROQS=32 \
  mordor-hw |& tee out/run-p32.log
```

## 4. Inspect the report

The generated report is:

```text
out/mordor_table1_output.txt
```

It contains three views:

1. raw NanGate45 results;
2. DeepScaleTool-scaled 14 nm results;
3. 14 nm results for six memory channels.

The camera-ready Table 1 uses the **14 nm × 6 channels** view. Its expected
values are:

| PROQ entries | Area (mm²) | Static (mW) | Dynamic (mW) | Access latency (ns) |
|---:|---:|---:|---:|---:|
| 32 | 0.058 | 13.60 | 145.14 | 0.51 |
| 48 | 0.089 | 22.63 | 191.65 | 0.50 |
| 64 | 0.118 | 28.71 | 255.88 | 0.54 |
| 78 | 0.144 | 46.18 | 311.26 | 0.67 |

Compare the numerical results with the values reported in Table 1.

## 5. Compare with the reference results

The normal run contains the paper implementation but omits the supplementary
blocked-bit section. Compare the paper portion with:

```bash
diff -u \
  <(sed '/SUPPLEMENTARY/,$d' expected_output.txt) \
  out/mordor_table1_output.txt
```

No difference indicates a successful paper-result reproduction.

For a byte-for-byte comparison of the complete reference report, including the
non-paper blocked-bit experiment, run:

```bash
docker run --rm \
  -v "$PWD/out:/out" \
  mordor-hw --blocked-bit |& tee out/run-blocked-bit.log

diff out/mordor_table1_output.txt expected_output.txt
```

An empty `diff` indicates an exact match. The blocked-bit section is
supplementary and is not the implementation reported in the paper.

## 6. Check for partial failures

Confirm that the report contains all four numerical CAM-on-path rows:

```bash
grep '^CAM-on-path' out/mordor_table1_output.txt
```

Also inspect `out/run.log` for `[FAIL]`. Raw OpenROAD reports and logs are
available under:

```text
out/openroad_raw/reports/
out/openroad_raw/logs/
out/raw_workdir/
```
