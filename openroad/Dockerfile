# MORDOR hardware-overhead reproducer (Paper Result Reproduction)
#
# Self-contained image that regenerates the OpenROAD numbers behind the paper's Table 1
# (CACTI is included only for the optional --blocked-bit table, which is not in the paper).
# It reproduces the authors' reference numbers EXACTLY by pinning three pieces:
#   * the ORFS prebuilt image at the authors' exact commit (flow, yosys, NanGate45 PDK),
#   * the authors' exact `openroad` binary + their flow-script patches (the overlay), and
#   * a pinned CACTI (for the optional table only).
#
#   docker build -t mordor-hw .
#   docker run --rm -v "$PWD/out:/out" mordor-hw                 # paper Table 1 (impl1)
#   docker run --rm -v "$PWD/out:/out" mordor-hw --blocked-bit   # + optional impl2 table
#
# BASE IMAGE = the authors' exact ORFS commit: `git describe b14dd6d76` = v3.0-4018-gb14dd6d76
# (ORFS b14dd6d76, 2025-10-16). This provides yosys + the NanGate45 platform. It also ships a
# NEWER `openroad` than the authors used, which we overwrite in step 2 -- that newer resizer
# leaves the CAM at min-size (X1) cells on the relaxed 100MHz clock, giving ~2x lower power and
# ~15-20% higher latency for the identical design. To pin harder, use the image digest.
FROM openroad/orfs:v3.0-4018-gb14dd6d76

ARG ORFS=/OpenROAD-flow-scripts

# 1) MORDOR overlay: the three Table-1 scripts (mordor_table1{,_analyze,_report}.sh +
#    render_table1.py), the MORDOR RTL, NanGate45 design configs, AND the authors' 10 patched
#    flow scripts (flow/scripts/*.tcl) -- the authors' exact working tree. Those patches are
#    what make the run match the paper: they (a) comment out
#    `set ::env(SETUP_MOVE_SEQUENCE ...)` so repair_timing does not pass `-sequence` (a flag the
#    authors' older openroad lacks -> STA-0562), (b) replace the finish-stage `report_metrics 6`
#    with `report_power` / `report_design_area` / `report_worst_slack` (the parseable lines
#    mordor_table1_report.sh greps from 6_report.log), and (c) drop the other per-stage
#    report_metrics.
COPY overlay/flow/ ${ORFS}/flow/

# 2) The authors' EXACT openroad binary (Debian pkg `openroad 2.0-17598-ga008522d8`, built
#    2024-12-11 -- the build their reference numbers came from). We overwrite the image's newer
#    openroad. Its older, more aggressive resizer upsizes the CAM to X8/X16/X32 cells, which is
#    what reproduces the paper's power (cam_64: leak 5.86mW, dyn 61.8mW) and latency (0.69ns) --
#    verified byte-for-byte against the authors' local logs. The .deb is no longer downloadable,
#    so the binary is shipped in the build context (BSD-3 licensed, same as OpenROAD). The
#    `-version` below is a build-time smoke test that the binary runs against the image's libs.
COPY openroad-v2.0-17598-ga008522d8 ${ORFS}/tools/install/OpenROAD/bin/openroad
RUN chmod +x ${ORFS}/tools/install/OpenROAD/bin/openroad \
 && ${ORFS}/tools/install/OpenROAD/bin/openroad -version

# 2b) Defensive: force `report_metrics` to a no-op. The overlay scripts already drop the
#     authors' report_metrics calls, but this guards any non-overlaid stage (the older openroad
#     lacks some metric commands). Harmless -- the eval never consumes report_metrics output.
RUN sed -i '/^proc report_metrics /a\  return' ${ORFS}/flow/scripts/report_metrics.tcl; \
    grep -A1 '^proc report_metrics ' ${ORFS}/flow/scripts/report_metrics.tcl \
      || echo "WARN: proc report_metrics not found in this image"
ENV SKIP_REPORT_METRICS=1

# 2c) Defensive (a no-op on this pinned image, which predates the feature): if a newer base
#     image is ever substituted, disable ORFS's post-repair Logical Equivalence Check -- its
#     `kepler-formal` binary needs AVX-512 and SIGILLs ("child killed: illegal instruction")
#     on CPUs without it (e.g. i9-12900K/KF), which killed CTS on the newer image.
RUN if [ -f ${ORFS}/flow/scripts/lec_check.tcl ]; then \
      sed -i '/^proc lec_check_enabled /a\  return 0' ${ORFS}/flow/scripts/lec_check.tcl && \
      grep -A1 '^proc lec_check_enabled ' ${ORFS}/flow/scripts/lec_check.tcl; \
    else echo "no lec_check.tcl in this image (older ORFS predates kepler-formal LEC) -- nothing to disable"; fi

# 3) The report's latency step shells out to a standalone `sta` (OpenSTA). The image ships
#    `openroad` (same OpenSTA engine/commands) but no `sta`, so provide a shim.
RUN printf '#!/usr/bin/env bash\nexec openroad "$@"\n' > /usr/local/bin/sta \
 && chmod +x /usr/local/bin/sta

# 4) CACTI (pinned) -- used ONLY by the optional --blocked-bit table (impl2's install CAM);
#    the paper's Table 1 needs no CACTI.
RUN git clone https://github.com/HewlettPackard/cacti /opt/cacti \
 && git -C /opt/cacti checkout 1ffd8dfb10303d306ecd8d215320aea07651e878 \
 && make -C /opt/cacti -j"$(nproc)"
ENV CACTI_DIR=/opt/cacti

COPY run.sh /opt/run.sh
RUN chmod +x /opt/run.sh

WORKDIR ${ORFS}/flow
ENTRYPOINT ["/opt/run.sh"]
