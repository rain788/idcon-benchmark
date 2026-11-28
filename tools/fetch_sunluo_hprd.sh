#!/usr/bin/env bash
# Retrieve the HPRD data graph and the Sun & Luo dense-16 query graphs used by
# IdCon-HPRD (queries 1-100) and IdCon-HPRD-H (queries 101-200) from the
# public SubgraphMatching repository (Sun & Luo, SIGMOD 2020; MIT-licensed code).
# The graph is derived from HPRD, which is free for academic, non-commercial use;
# commercial use requires a licence from the HPRD maintainers. These files are
# therefore not redistributed by IdCon; their SHA-256 values are recorded in
# experiment/data/processed/idcon_hprd*/source_hashes.json.
set -euo pipefail
COMMIT=bcaa935c83709b0220e950634dbf5215ae2a526e
DEST="$(cd "$(dirname "$0")/.." && pwd)/experiment/data/raw/hprd_sun_luo"
TMP="$(mktemp -d)"
git clone -q --filter=blob:none --no-checkout https://github.com/RapidsAtHKUST/SubgraphMatching "$TMP/sl"
git -C "$TMP/sl" checkout -q "$COMMIT" -- test/data_graph/HPRD.graph test/query_graph LICENSE
mkdir -p "$DEST/query_graph"
cp "$TMP/sl/test/data_graph/HPRD.graph" "$TMP/sl/LICENSE" "$DEST/"
cp "$TMP"/sl/test/query_graph/query_dense_16_*.graph "$DEST/query_graph/"
rm -rf "$TMP"
echo "HPRD graph and $(ls "$DEST/query_graph" | wc -l) Sun-Luo queries at $DEST"
