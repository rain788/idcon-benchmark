# Data licences

**IdCon's own data: CC BY 4.0.** The synthetic IdCon-Hard and IdCon-Hard-X inputs, all manifests,
observation rules, construction maps, reference records, predictions, scores and
design records in `experiment/data/` and `experiment/results/` are licensed under
the Creative Commons Attribution 4.0 International licence
(https://creativecommons.org/licenses/by/4.0/).

Suggested attribution: "Yulin Liu, Zhiyu Liu and Ru Wang. IdCon: Identity-Consensus
Diagnosis Benchmark, 2026, CC BY 4.0."

**Third-party data are not covered by this grant and are not redistributed.**

| Source | Used by | Terms | How to obtain |
|---|---|---|---|
| HPRD protein interaction network as distributed in the SubgraphMatching repository of Sun & Luo (SIGMOD 2020) | IdCon-HPRD, IdCon-HPRD-X, IdCon-HPRD-H | HPRD is free for academic, non-commercial use; commercial use needs a licence from the HPRD maintainers. The repository's MIT licence covers its code, not HPRD's terms. | `tools/fetch_sunluo_hprd.sh` (pinned commit, SHA-256 checked) |
| Sun & Luo dense-16 query graphs | IdCon-HPRD (1-100), IdCon-HPRD-H (101-200) | as above (derived from HPRD) | `tools/fetch_sunluo_hprd.sh` |
| CEMR query graphs (Yang et al., PVLDB 19(7), 2026; github.com/pkumod/CEMR) | IdCon-HPRD-X | no licence file in the source repository | `tools/fetch_cemr_queries.sh` (pinned commit, SHA-256 checked) |
| Cora and PubMed citation graphs as distributed in the Planetoid repository (Yang, Cohen & Salakhutdinov, ICML 2016; github.com/kimiyoung/planetoid); the graphs originate from Sen et al. (AI Magazine 2008) and Namata et al. (MLG 2012) | IdCon-Cite | the Planetoid repository is MIT-licensed; the citation graphs carry no separate licence there and are widely redistributed for research; we do not redistribute them | `tools/fetch_planetoid.sh` (pinned commit; SHA-256 of every file in `experiment/data/processed/idcon_cite/source_hashes.json`) |

Task files of the HPRD suites (`experiment/data/processed/idcon_hprd*/identities`,
`tables`) are generated locally from these files by `experiment/src/external_hprd*.py`
and inherit HPRD's terms. The task files of IdCon-Cite are likewise generated locally by
`experiment/src/external_cite.py`.

The held-out references of IdCon-HPRD-H and both the inputs and the references of the
held-out synthetic split IdCon-Hard-H are not distributed; only their SHA-256 commitments are.
(IdCon-Hard-H can be regenerated from the seed in the stage-3 design record.)

The patched LAD2025 sources and binaries are under the CeCILL-B licence
(`CECILL-B-LICENSE.txt`).
