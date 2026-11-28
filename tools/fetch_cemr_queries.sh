#!/usr/bin/env bash
# Retrieve the HPRD query graphs used by IdCon-HPRD-X from the public CEMR
# artifact (Yang et al., PVLDB 19(7), 2026). The files are not redistributed
# in this repository; their SHA-256 values are recorded in
# experiment/data/processed/idcon_hprd_x/source_hashes.json and checked by
# tools/verify.py --inputs.
set -euo pipefail
COMMIT=1eb4b0710fc6182fd6222f0e7e64dbed1be93642
DEST="$(cd "$(dirname "$0")/.." && pwd)/experiment/data/raw/cemr_hprd"
TMP="$(mktemp -d)"
git clone -q --filter=blob:none --no-checkout https://github.com/pkumod/CEMR "$TMP/CEMR"
git -C "$TMP/CEMR" checkout -q "$COMMIT" -- test/test_data/query_graph
mkdir -p "$DEST/query_graph"
cp "$TMP"/CEMR/test/test_data/query_graph/*.graph "$DEST/query_graph/"
rm -rf "$TMP"
echo "CEMR query graphs at $DEST/query_graph ($(ls "$DEST/query_graph" | wc -l) files)"
