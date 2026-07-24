# MORDOR hardware-overhead reproducer

Regenerates MORDOR's area / static-power / dynamic-power / access-latency / access-energy
numbers (OpenROAD + CACTI). Everything overlays onto a clone of OpenROAD-flow-scripts (ORFS).

Two models are included:
- **v9 (current, per-request)** — the faithful model: a baseline MC request-queue array plus
  the per-request "ready AND not-blacklisted" check done two ways (a compare-everything CAM
  vs a blocked-bit per entry), with the PROQ structure costed separately in CACTI. **Use this one.**
- **v7/v8 (earlier, per-bank stall)** — scheduler-logic + PROQ-CAM models that assumed a
  whole-bank stall on a blacklisted request. Kept for reference and the CAM cross-checks.

## v9 — per-request blacklist (recommended)

`flow/designs/mordor_v9_eval.sh` drives everything and prints 7 sections:

| # | what | tool |
|---|------|------|
| 1 | logic area overhead (blocked-bit, CAM) vs baseline MC array | OpenROAD synth |
| 2 | static power (leakage) | OpenROAD |
| 3 | dynamic power (internal+switching) | OpenROAD |
| 3b | access latency, reg→ready_o (on the per-cycle scheduling path) | OpenROAD STA |
| 4 | MC array as RAM vs searchable CAM (area / leak / search / energy) | CACTI |
| 5 | PROQ structure vs size P: FIFO vs 1-port install CAM vs M-port CAM | CACTI |
| 6 | consolidated impl2 overhead = OpenROAD logic delta + CACTI PROQ | both |
| 7 | install-lookup latency: synth flip-flop CAM vs CACTI dense CAM | both |

RTL: `flow/designs/src/mordor_v9/mordor_v9.v` — one parameterized module, selected by `MODE`:
- `0` baseline (MC array alone), `1` CAM (M×PROQ compare-everything), `2` blocked-bit
  (per-entry, set/cleared on PRO enqueue/dequeue), `3` install (admit-time PROQ search —
  drives `installed_blk_o`, used only for the OpenROAD-vs-CACTI latency cross-check).
- Params: `MC_ENTRIES`, `PROQ_ENTRIES`, `ADDR_W` (=24), `MODE`. Applied via ORFS
  `VERILOG_TOP_PARAMS` (yosys `chparam`).

Config: `flow/designs/nangate45/mordor_v9/` — `config.mk` + `constraint.sdc` (10 ns relaxed
clock, to isolate area/power without timing-driven gate bloat polluting the deltas).

### Run
```
cd flow
bash designs/mordor_v9_eval.sh            # build (if stale) + report, OpenROAD + CACTI
bash designs/mordor_v9_eval.sh cacti      # CACTI sections only (seconds)
BUILD=0 bash designs/mordor_v9_eval.sh    # NO rebuild -- report from existing artifacts
```
Knobs (env vars): `MCS` (MC sizes, default `"16 32 64"`), `PROQS` (PROQ sizes, default
`"16 32 64"`), `PROQ` (headline PROQ size, default `32`), `BUILD` (`1`=build if stale,
`0`=report-only), `CACTI_DIR` (default `~/cacti`).

### How to read it for a write-up (impl2 = blocked-bit)
Section 6 already assembles this, but the recipe is:
- **area** = OpenROAD `blk−base` logic delta (§1) **+** CACTI PROQ structure (§5).
- **static** = OpenROAD leakage delta (§2) **+** CACTI PROQ leakage (§5).
- **latency** = on-path `access` (§3b, must meet t_RRD) reported separately from off-path
  `install` (§5/§7) — not max'd together.
- **energy** = CACTI per-access search energy (§4/§5), e.g. 3.46 pJ/lookup at P=32.

The PROQ is a FIFO if the admit-time lookup is not modeled (variant B), or a 1-port CAM if it
is (variant A). Caveat: logic is NanGate45 std-cells, the PROQ is CACTI 45 nm `itrs-hp` — same
units, different cell model (the CACTI part is the conservative, leakier one).

## v7/v8 — earlier per-bank models

> **Not included in this AE package** — superseded by v9, and no paper number comes from
> them; they live in the main working repo. Described here only for methodology history.

`flow/designs/mordor_hw_eval.sh` (sections: latency, logic, cacti, xcheck):
- `flow/designs/src/mordor_v7/` — `mordor_v7_sched` (tree arbiter), `mordor_v7_noarb`,
  `per_bank_select`, `global_arbiter`.
- `flow/designs/src/mordor_v8/` — `mordor_v8_cam` (PROQ CAM alone), `mordor_v8_fused`
  (CAM search + scheduler).
- `flow/designs/nangate45/mordor_v{7,8}/` — `config.mk` + `constraint.sdc` (5 ns = t_RRD).
```
cd flow
bash designs/mordor_hw_eval.sh            # everything
bash designs/mordor_hw_eval.sh cacti      # CAM only (seconds)
bash designs/mordor_hw_eval.sh xcheck     # synth CAM vs CACTI cross-check
```
Knobs: `CACTI_DIR`, `CAM_BITS` (default `32` = 24b addr + pad), `SIZES` (default
`"16 32 48 64"`), `CLK` (default `5.0`).

## Shared
`flow/scripts/final_report.tcl` — **PATCHED**: emits `report_power` + `report_design_area`
+ `report_worst_slack` (vanilla ORFS calls `report_metrics`, which aborts on OpenROAD builds
lacking `report_fmax_metric`). All the scripts' result extractors depend on these lines — keep
this version.

## Setup
1. From the root of an ORFS clone, overlay the bundle (preserves `flow/...` paths):
   ```
   tar xzf mordor_hw_eval.tar.gz
   ```
2. CACTI: `git clone https://github.com/HewlettPackard/cacti ~/cacti` (or point `CACTI_DIR`
   at an existing clone — the scripts auto-build it if the binary is missing).
3. Build the ORFS Docker/local toolchain as usual, then run as above.

## Outputs
- OpenROAD per-build: `flow/{logs,reports,results}/nangate45/mordor_v{7,8,9}/<variant>/`
  (`6_report.log`, `reports/.../synth_stat.txt`, `results/.../6_final.{v,sdc}`).
- CACTI: `/tmp/mordor_v9_eval/c_*.out` (v9), `/tmp/mordor_hw_eval/*` (v7/8).
- Each script prints its consolidated tables.

Node: NanGate45 (45 nm) logic + CACTI 45 nm arrays (`itrs-hp` cells — fast/leaky, so a
conservative upper bound on leakage). v9 logic uses a 10 ns clock; v7/8 use 5 ns = t_RRD.
See each script's header for methodology notes.
