#!/usr/bin/env bash
# R2 deviation (2026-11-27 12:2x UTC): make the kernel's OOM killer pick an external
# solver process (Glasgow, LAD, CaDiCaL, drat-trim) rather than the Python driver
# that records the runs. A solver killed this way fails with a non-zero exit code
# and its run is recorded as runtime_error (unanswered), as in R1.
while true; do
  for p in $(pgrep -f 'glasgow_subgraph_solver|lad2025|/cadical|drat-trim|/build/lad'); do
    echo 1000 > /proc/$p/oom_score_adj 2>/dev/null
  done
  sleep 0.1
done
