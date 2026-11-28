# Patched LAD2025 used by IdCon (LAD adapter, First-match, reference builder)

`LAD2025_original_source.tgz` is the upstream archive (Christine Solnon,
https://perso.citi-lab.fr/csolnon/LAD2025.tgz; SHA-256 in
`../lad2025_provenance.json`), distributed under CeCILL-B (`../../../CECILL-B-LICENSE.txt`).

`main.c` and `domains.c` are the adapted sources (SHA-256 recorded in
`../lad2025_provenance.json` under `adapted_sources`): externally supplied unary
domains and metric-edge lists read from the file named by `EG_LAD_CONSTRAINTS`,
and the two domain-ignorant clique shortcuts disabled when domains are given.
Search, filtering, ordering and restarts are upstream. `build_lad.py` re-derives
the adapted files from the upstream archive; `make` builds
`../build/lad2025/lad2025`. The binary used for the recorded runs
(SHA-256 700597c1...) was built with GCC 11.4.0 on Ubuntu 22.04; a rebuild with
another compiler reproduces labels, not timings.
