# MORDOR — Hardware / Power / Area / Latency Overhead (MICRO 2026 Artifact)

For a short reviewer-oriented procedure, see
[`VALIDATE_TABLE1.md`](VALIDATE_TABLE1.md).

This artifact regenerates MORDOR's **hardware-overhead** numbers — the OpenROAD synthesis +
place-and-route results behind the paper's **Table 1** (whose power numbers also feed the
Fig. 5 hardware-energy component). It is fully self-contained via Docker: you do **not**
clone or build OpenROAD-flow-scripts (ORFS) yourself. A *pinned prebuilt ORFS image*
supplies yosys + the NanGate45 PDK, this artifact overlays the MORDOR design files, and it
drops in the authors' exact `openroad` binary so the numbers reproduce **exactly**.
The host wrapper verifies that binary against the repository checksum before
building the Docker image.
(CACTI is **not used by the paper** — it only models the optional `--blocked-bit` extra, below.)

## The three scripts

Everything is driven by three small scripts in `overlay/flow/designs/` (the container
entrypoint just calls the third):

| script | what it does |
|--------|--------------|
| `mordor_table1_analyze.sh [--blocked-bit]` | runs the OpenROAD synth+P&R for the Table-1 design points (baseline + impl1 CAM at PROQ ∈ {32,48,64,78}); incremental — already-built variants are skipped |
| `mordor_table1_report.sh [--blocked-bit] [-o FILE]` | renders the existing analysis results into a new file (default `mordor_table1_report.txt`) + stdout; seconds, no builds |
| `mordor_table1.sh [--blocked-bit] [-o FILE]` | analysis, then report |

`--blocked-bit` (accepted by all three, default **off**) additionally analyzes/reports the
**optional impl2 blocked-bit** alternative — a lower-cost design (one broadcast "blocked" bit
per MC entry + a FIFO/RAM PROQ with a 1-port install CAM) that is **NOT in the paper**. It is
the only part that uses CACTI.

## What it produces

The run writes the report to **`out/mordor_ae_output.txt`**: the paper's **Table 1** — impl1
CAM-on-path overhead vs the baseline MC (area, static/dynamic power, and the synthesized
`reg → ready_o` scheduling-path latency) — in three views:

- **45 nm raw** — what the flow actually produces.
- **14 nm** — 45 nm ÷ the authors' DeepScaleTool factors (power 2.438, area 12.5, energy 3.316,
  delay 1.35). *These are the printed Table 1 values.*
- **14 nm × 6 channels** — one MORDOR instance per memory channel (see "Per-channel" below);
  area + power scale ×6, latency and per-lookup energy are per-instance.

With `--blocked-bit`, a clearly-marked `SUPPLEMENTARY` section with the same views for the
impl2 alternative follows below the Table-1 block.

## Requirements
- **Docker Engine and CLI** with a running daemon, an **x86-64 Linux** host,
  internet for the first build, **~10 GB free disk**, **≥ 8 GB RAM**, ideally
  multi-core.
- **Docker Buildx** is recommended. The Dockerfile currently works with the
  deprecated legacy builder, but Docker is removing that fallback.
- No GPU, no PDK download, no toolchain build.

## Quick start

The simplest option is the host-side wrapper, which builds the image, ensures
that `out/` exists, runs the experiment, and records the console log:

```bash
./reproduce_table1.sh
```

Use `./reproduce_table1.sh --quick` for the PROQ=32 smoke test,
`./reproduce_table1.sh --skip-build` to reuse an existing image, or
`./reproduce_table1.sh --sudo` on systems where Docker requires `sudo`.

The equivalent manual commands are:

```bash
docker build -t mordor-hw-ae .                                    # ~10-20 min, mostly the base-image pull
mkdir -p out
docker run --rm -v "$PWD/out:/out" mordor-hw-ae                   # paper Table 1, ~2-2.5 h
docker run --rm -v "$PWD/out:/out" mordor-hw-ae --blocked-bit     # + optional impl2 table
```
Then compare against the shipped reference — `expected_output.txt` is byte-identical to the
report of a `--blocked-bit` run on the pinned image:
```bash
diff out/mordor_ae_output.txt expected_output.txt   # empty for a --blocked-bit run
```
A default (no-flag) run reproduces everything above the `SUPPLEMENTARY` banner; `diff` then
shows only the absent impl2 block as trailing additions.

The `TABLE 1` section prints to stdout and to `out/mordor_ae_output.txt`; raw OpenROAD reports
and CACTI outputs land in `out/openroad_raw/` and `out/cacti_raw/`.

### Runtime
| step | time | notes |
|------|------|-------|
| build | ~10–20 min | one-time; dominated by the ~6.5 GB base-image pull |
| run (default) | ~2–2.5 h | 5 full-flow builds: base (~3 min) + the four impl1 Table-1 cams (P=32 ~13 min, P=48 ~19 min, P=64 ~34 min, P=78 ~54 min, big die) |
| run (`--blocked-bit`) | + ~5 min | adds the impl2 blk variant (~3 min) + CACTI (seconds) |

> **Kick-the-tires shortcut (~20 min).** Restrict the sweep to P = 32:
> `docker run --rm -v "$PWD/out:/out" -e PROQS=32 mordor-hw-ae`. This builds only base +
> cam@P=32 and emits a one-row Table 1 — eyeball it against the P=32 row of
> `expected_output.txt` (the other rows are simply absent in this shortcut).

> **Docker permissions.** If `docker` gives "permission denied … docker.sock", either add
> yourself to the `docker` group (`sudo usermod -aG docker $USER`, then re-login) or prefix
> the commands with `sudo`. If the socket does not exist, start Docker Engine
> first (typically `sudo systemctl enable --now docker` on a systemd host).