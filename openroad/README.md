# MORDOR OpenROAD reproduction

This directory reproduces the hardware measurements reported by the paper for
PROQ sizes 32, 48, 64, and 78. The pinned Docker environment contains the
MORDOR RTL, OpenROAD flow, and reporting scripts.

Run the complete experiment on an x86-64 Linux host with Docker, internet
access for the initial image pull, at least 8 GB RAM, and about 10 GB free
disk space:

```bash
./reproduce_table1.sh
```

Use `--sudo` if Docker requires elevated privileges, `--quick` for the
PROQ-size-32 functional check, or `--skip-build` to reuse an existing image.
The full run normally takes 2–2.5 hours. Generated reports, logs, and
intermediate files are written under `out/` and ignored by Git.

The wrapper verifies the bundled OpenROAD executable against
`../CHECKSUMS.sha256` before building the image. Compare
`out/mordor_ae_output.txt` with the corresponding hardware-overhead table in
the paper.
