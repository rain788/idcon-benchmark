#!/usr/bin/env bash
# Retrieve the Cora and PubMed citation graphs used by IdCon-Cite (revision R2)
# from the Planetoid repository (Yang, Cohen & Salakhutdinov, ICML 2016;
# github.com/kimiyoung/planetoid, MIT licence) at a fixed commit. The graphs
# originate from Sen et al. (AI Magazine 2008) and Namata et al. (MLG 2012).
# They are not redistributed by IdCon; experiment/data/processed/idcon_cite/
# source_hashes.json records the SHA-256 of every file used.
set -euo pipefail
COMMIT=af6abf468a772cc055bec88c52e4d6f51b7c37e3
DEST="$(cd "$(dirname "$0")/.." && pwd)/experiment/data/raw/planetoid"
TMP="$(mktemp -d)"
git clone -q --filter=blob:none --no-checkout https://github.com/kimiyoung/planetoid "$TMP/p"
FILES=""
for d in cora pubmed; do for s in ally ty graph test.index; do FILES="$FILES data/ind.$d.$s"; done; done
git -C "$TMP/p" checkout -q "$COMMIT" -- $FILES LICENSE
mkdir -p "$DEST"
cp $(for f in $FILES; do echo "$TMP/p/$f"; done) "$TMP/p/LICENSE" "$DEST/"
rm -rf "$TMP"
echo "Planetoid files at $DEST"
