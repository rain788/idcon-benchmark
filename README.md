# IdCon: Identity-Consensus Diagnosis Benchmark

IdCon measures whether a system answers a simple-sounding question correctly:
*does a requirement pattern hold for **every** admissible embedding of it in an observed graph?*
A first-match pipeline finds one embedding and reads the observations there; when several
embeddings are admissible and disagree, its answer depends on search order. IdCon fixes the
task, the inputs, the reference labels and the scoring, and ships exact baselines.

Companion paper: *IdCon: A Benchmark for Identity-Consensus Diagnosis over Ambiguous Graph
Embeddings* (KDD 2027 Datasets and Benchmarks track, under review). Source in `paper/`;
`tools/verify.py` recomputes every table and number of the paper from the frozen records.

## How the study was run

The study ran in three stages, each fixed by a design record written before that stage's runs.
The records, their amendments and the run logs are released; their times are the authors' own.
Two result folders keep their working names because the frozen records refer to them by path:

| stage | design record | adds |
|---|---|---|
| 1 | `experiment/results/{idcon_hard,idcon_hprd}/` (local hash-stamped records), Amendments 1-3 | IdCon-Hard, IdCon-HPRD; LAD, Glasgow, CP-SAT, Trad-CP, first-match; two solvers of the authors (EG-ICAF, LAD-SV) |
| 2 | `experiment/results/revision_r1/design.json`, Amendment 4 | IdCon-HPRD-X, IdCon-HPRD-H; Enum-Glasgow, Enum-VF2, ASP-cautious; 10 s reruns; re-check of reference negatives; the authors' solvers dropped from the benchmark |
| 3 | `experiment/results/revision_r2/design.json`, Amendments 5-7 | IdCon-Hard-X, IdCon-Hard-H, IdCon-Cite; SAT (CaDiCaL); independent reference check (`experiment/independent/`); 60 s reruns; sensitivity analyses |

The authors' solvers are not ranked; their stage-1 results are reported in the paper's appendix.
Deviations are listed in the paper's appendix and in each stage's `orchestrate.log`.

## Task

Input: a pattern graph of roles, a host graph of entities with coordinates, optional anchors,
metric edges and unary role domains, checked roles with `S/U/V` observation tables.
An admissible identity is an injective, anchor- and metric-respecting, edge-preserving map from
roles to entities. Outcome:

| outcome | meaning |
|---|---|
| `SATISFIES` | every admissible identity has state S |
| `VIOLATES` | every admissible identity has state V |
| `UNKNOWN` | some identity has state U, or states disagree |
| `EMPTY` | no admissible identity exists |

A method may also return no answer (budget). Scoring: correct iff the outcome equals the reference;
PAR-2 with a 2 s budget (4 s penalty), averaged per ancestor, then across ancestors. A method that
returns a certified outcome contradicting a reference is unsound and is not ranked by runtime.

## Suites

| suite | ancestors | tasks | source |
|---|---:|---:|---|
| IdCon-Hard | 72 | 504 | synthetic, 2,048-8,192 entities, 48-96 roles, metric edges, empty-space probes |
| IdCon-HPRD | 100 | 200 | HPRD graph + Sun & Luo dense-16 queries 1-100 |
| IdCon-HPRD-X | 96 | 192 | HPRD graph + CEMR artifact queries of 8, 16, 24, 32 vertices, dense and sparse |
| IdCon-Hard-X | 12 | 72 | synthetic, 16,384 entities, 128 roles |
| IdCon-Cite | 96 | 192 | Cora and PubMed citation graphs + random-walk queries of 8, 16, 24 vertices, dense and sparse |
| IdCon-HPRD-H (held out) | 100 | 200 | HPRD graph + Sun & Luo dense-16 queries 101-200; labels not public |
| IdCon-Hard-H (held out) | 12 | 72 | synthetic, as Hard-X with another seed; inputs and labels not distributed (65 assessed); its seed is in the stage-3 design record |

The held-out references are kept out of this repository; the SHA-256 of the reference file is in
`experiment/data/processed/idcon_hprd_h/reference_commitment.json` and
`experiment/data/processed/idcon_hard_h/commitment.json`. Send predictions (or, for IdCon-Hard-H, a method that we
can run) to the corresponding author for scoring.

## Main results (2 s end-to-end budget, two repeats; correct runs / PAR-2 ms)

| method | Hard (1,008 runs) | HPRD (400) | HPRD-X (384) | Cite (384) |
|---|---:|---:|---:|---:|
| LAD (LAD2025, two-query) | 725 / **1,635** | 389 / 1,036 | 199 / 2,513 | 192 / 2,086 |
| Glasgow | 562 / 2,113 | 0 / 4,000 | 1 / 3,995 | 92 / 3,256 |
| Glasgow `--staged` (post hoc on Hard/HPRD) | 651 / 1,740 | 304 / 1,361 | 265 / 1,734 | 126 / 2,904 |
| CP-SAT | 321 / 2,998 | 384 / 455 | 360 / 830 | 124 / 2,911 |
| Traditional CP | 214 / 3,347 | 279 / 1,858 | 191 / 2,603 | 190 / 2,188 |
| Enum-Glasgow (stage 2) | 88 / 3,688 | 235 / 2,638 | 65 / 3,568 | 104 / 3,118 |
| Enum-VF2, NetworkX (stage 2) | 14 / 3,951 | 127 / 2,937 | 74 / 3,354 | 77 / 3,300 |
| ASP-cautious, clingo (stage 2) | 15 / 3,968 | 400 / 748 | 365 / 1,230 | 223 / 1,964 |
| SAT, CaDiCaL (stage 3) | 240 / 3,378 | 400 / **374** | 384 / **380** | 265 / **1,598** |
| First-match (not exact; wrong runs) | 626 (315 wrong) | 230 (170 wrong) | 224 (160 wrong) | 114 (80 wrong) |

IdCon-Hard-X (68 assessed tasks, repeat 0; tasks answered correctly within 2 / 10 / 60 s, 60 s reruns for
LAD, Glasgow-staged and SAT): LAD 1 / 30 / 64, Glasgow-staged 15 / 33 / 46, SAT 2 / 2 / 40, CP-SAT 5 / 11 / --;
no method answers 3 tasks within 60 s. IdCon-Hard at 60 s: LAD answers 498 of 504 tasks on repeat 0, all methods
together all but 4.

No exact method returned a certified answer that contradicts a reference on any suite; every positive witness
returned by any method replays against the original constraints
(`experiment/results/revision_r2/witness_replay_r2.json`). Every wrong first-match run has an `UNKNOWN` reference.
The independent check (`experiment/results/revision_r2/idcheck.w*.jsonl`) agrees with every reference it decides.
Exact figures for every table are in `paper/tables/` and `paper/results_macros*.tex`, regenerated by `tools/verify.py`.

## Layout

```
experiment/src/                    generator, importers, method adapters, reference builder, scoring, analyses (module map: src/README.md)
experiment/data/processed/         manifests, input hashes (Hard inputs in inputs.tar.gz; HPRD inputs built locally)
experiment/data/protected/         construction maps and reference labels (read only for scoring)
experiment/data/raw/               not tracked: fetched by tools/fetch_*.sh (licences below)
experiment/results/idcon_*/        frozen predictions (stage 1 files; .r1. = stage 2, .r2. = stage 3; .b10./.b60. = 10/60 s reruns)
experiment/results/revision_r1/    stage-2 design record, Amendment 4, pilot validation, counts, overhead, analyses, logs
experiment/results/revision_r2/    stage-3 design record, Amendments 5-7, independent-check results, analyses, logs
experiment/independent/            independent reference check (CNF encoding + CaDiCaL + drat-trim); imports nothing from src/
experiment/third_party/            patched LAD2025 sources (lad2025_src/) and binary; provenance
paper/                             LaTeX source, tables and macros (generated), figures, build scripts
tools/verify.py                    read-only recomputation of every table and macro of the paper
```

## Quick start

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt            # Python 3.10
python tools/verify.py                     # hashes + recomputes every paper table from the frozen records
# inputs
tar xzf experiment/data/processed/idcon_hard/inputs.tar.gz -C experiment
tools/fetch_sunluo_hprd.sh && tools/fetch_cemr_queries.sh && tools/fetch_planetoid.sh
(cd experiment/src && IDCON_STUDY=idcon_hprd python -c "import external_hprd as e; e.generate()")
(cd experiment/src && IDCON_STUDY=idcon_hprd_x python external_hprd_x.py)   # regenerates; check hashes
tar xzf experiment/data/processed/idcon_hard_x/inputs.tar.gz -C experiment         # IdCon-Hard-X inputs
(cd experiment/src && IDCON_STUDY=idcon_cite python external_cite.py)                   # IdCon-Cite (needs tools/fetch_planetoid.sh)
# solvers
make -C experiment/third_party/lad2025_src                      # patched LAD2025
# Glasgow Subgraph Solver: build upstream commit 01ef6ca and place the binary at
# experiment/third_party/build/glasgow_subgraph_solver
# SAT baseline and independent check: CaDiCaL 2.1.3 and drat-trim at
# experiment/third_party/build/{cadical,drat-trim}
# a timed rerun (new output directory, new timings):
cd experiment/src && IDCON_STUDY=idcon_hard IDCON_PRED_TAG=myrun python hard_benchmark.py infer --methods lad_state
```

## Adding a method

Implement `diagnose_tables(identity, tables, base, timeout) -> dict(label, reason, certificate, mappings)`
and register it in `experiment/src/hard_benchmark.py:dispatch`. Return `certificate=True` only for answers your
method has established; return every positive witness in `mappings` so it can be replayed. Report correct,
wrong and unanswered runs, PAR-2, correct runs by reference label, and the number of certified answers that
contradict a reference. Learned or approximate methods leave `certificate=False` and should beat the
learned no-search prior reported in the paper.

## Licences

Project code: MIT (`LICENSE`). Our generated data, references and predictions: CC BY 4.0 (`DATA_LICENSE.md`).
LAD2025 sources: CeCILL-B (`CECILL-B-LICENSE.txt`). HPRD is free for academic, non-commercial use only and is
not redistributed; the CEMR query files carry no licence and are not redistributed; the Planetoid citation graphs
are fetched, not redistributed. See `DATA_LICENSE.md`. (The Zenodo record lists one licence, MIT, for the
archive; the per-component licences above govern.)

## Citation

See `CITATION.cff`.

Contact: Ru Wang (ru.wang13@bit.edu.cn), School of Mechanical Engineering, Beijing Institute of Technology.
