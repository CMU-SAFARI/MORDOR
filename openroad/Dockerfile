# Pinned environment for the paper's OpenROAD hardware analysis.
FROM openroad/orfs:v3.0-4018-gb14dd6d76

ARG ORFS=/OpenROAD-flow-scripts

# Add the MORDOR design and flow scripts.
COPY overlay/flow/ ${ORFS}/flow/

# Use the checked OpenROAD version from the paper evaluation.
COPY openroad-v2.0-17598-ga008522d8 ${ORFS}/tools/install/OpenROAD/bin/openroad
RUN chmod +x ${ORFS}/tools/install/OpenROAD/bin/openroad \
 && ${ORFS}/tools/install/OpenROAD/bin/openroad -version

# Disable an unsupported metrics helper.
RUN sed -i '/^proc report_metrics /a\  return' ${ORFS}/flow/scripts/report_metrics.tcl; \
    grep -A1 '^proc report_metrics ' ${ORFS}/flow/scripts/report_metrics.tcl \
      || echo "WARN: proc report_metrics not found in this image"
ENV SKIP_REPORT_METRICS=1

# Keep the flow portable to hosts without AVX-512.
RUN if [ -f ${ORFS}/flow/scripts/lec_check.tcl ]; then \
      sed -i '/^proc lec_check_enabled /a\  return 0' ${ORFS}/flow/scripts/lec_check.tcl && \
      grep -A1 '^proc lec_check_enabled ' ${ORFS}/flow/scripts/lec_check.tcl; \
    else echo "no lec_check.tcl in this image (older ORFS predates kepler-formal LEC) -- nothing to disable"; fi

# Provide the standalone `sta` command used by the latency report.
RUN printf '#!/usr/bin/env bash\nexec openroad "$@"\n' > /usr/local/bin/sta \
 && chmod +x /usr/local/bin/sta

COPY run.sh /opt/run.sh
RUN chmod +x /opt/run.sh

WORKDIR ${ORFS}/flow
ENTRYPOINT ["/opt/run.sh"]
