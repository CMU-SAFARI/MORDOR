#!/usr/bin/env python3
"""
Render the paper's Table 1 (hardware overhead) from raw 45nm overhead rows.

Reads whitespace-separated rows (from a file arg or stdin), one per design point:

    <design> <PROQ> <ORstat_mW> <ORdyn_mW> <OR+CACTI_area_um2> <energy_pJ> <leak_mW> <delay_ns> <Totstat_mW>

Use '-' for a cell that does not apply (e.g. the CAM-on-path row has no CACTI columns).
Emits three tables: 45nm raw, 14nm (45nm / factors), and 14nm x N channels.
45nm->14nm factors are DIVISORS (authors' DeepScaleTool values); overridable via env
SC_POW / SC_AREA / SC_EN / SC_DLY and NCHAN.  x-channels scales area+power only
(delay and per-lookup energy are per-instance and shown once).
"""
import os, sys

POW  = float(os.environ.get("SC_POW",  "2.438"))
AREA = float(os.environ.get("SC_AREA", "12.5"))
EN   = float(os.environ.get("SC_EN",   "3.316"))
DLY  = float(os.environ.get("SC_DLY",  "1.35"))
NCH  = int(float(os.environ.get("NCHAN", "6")))

COLS = ["design", "PROQ", "OR stat mW", "OR dyn mW", "OR+CACTI um2",
        "energy pJ", "leak mW", "delay ns", "Tot stat mW"]
W = [13, 6, 12, 12, 14, 11, 11, 10, 12]


def rows(src):
    out = []
    for ln in src:
        t = ln.split()
        if len(t) >= 9 and t[1].lstrip("-").isdigit() and t[0] != "design":
            out.append(t[:9])
    return out


def cell(v, div, mult, prec):
    if v == "-":
        return "-"
    return f"{float(v) / div * mult:.{prec}f}"


def emit(title, data, divs, mult, cols_keep):
    # divs indexes align to columns 2..8: ORstat,ORdyn,area,energy,leak,delay,totstat
    print(title)
    hdr = [COLS[i] for i in cols_keep]
    ww  = [W[i] for i in cols_keep]
    print("".join(h.ljust(w) for h, w in zip(hdr, ww)))
    # per-column (divisor, precision, scales_with_channels)
    spec = {  # col index -> (divisor, precision, extensive?)
        2: (divs[0], 4 if divs[0] != 1 else 3, True),   # OR stat
        3: (divs[1], 4 if divs[1] != 1 else 3, True),   # OR dyn
        4: (divs[2], 2 if divs[2] != 1 else 0, True),   # area
        5: (divs[3], 4 if divs[3] != 1 else 2, False),  # energy (per-instance)
        6: (divs[4], 4 if divs[4] != 1 else 3, True),   # leak
        7: (divs[5], 4 if divs[5] != 1 else 2, False),  # delay (per-instance)
        8: (divs[6], 4 if divs[6] != 1 else 3, True),   # Tot stat
    }
    for r in data:
        line = []
        for i in cols_keep:
            if i == 0:
                line.append(r[0].ljust(W[0]))
            elif i == 1:
                line.append(r[1].ljust(W[1]))
            else:
                div, prec, ext = spec[i]
                m = mult if (ext and mult != 1) else 1
                line.append(cell(r[i], div, m, prec).ljust(W[i]))
        print("".join(line))


def main():
    src = open(sys.argv[1]) if len(sys.argv) > 1 else sys.stdin
    data = rows(src)
    if not data:
        sys.stderr.write("render_table1: no valid rows\n"); sys.exit(2)

    one = [1, 1, 1, 1, 1, 1, 1]
    fac = [POW, POW, AREA, EN, POW, DLY, POW]
    allcols = list(range(9))
    x6cols  = [0, 1, 2, 3, 4, 6, 8]  # drop energy(5) & delay(7): per-instance

    emit("TABLE 1  -- 45nm raw (what the reproduction flow produces)", data, one, 1, allcols)
    print()
    emit(f"TABLE 1  -- 14nm (45nm / power {POW} area {AREA} energy {EN} delay {DLY})",
         data, fac, 1, allcols)
    print()
    emit(f"TABLE 1  -- 14nm x {NCH} channels (one MORDOR per MC/channel; area+power scale, delay/energy per-instance)",
         data, fac, NCH, x6cols)


if __name__ == "__main__":
    main()
