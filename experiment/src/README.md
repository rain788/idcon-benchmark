# experiment/src: module map

Several module names come from earlier, unrelated prototypes of the authors (engineering
model checking with forces, boundary conditions and materials) and were kept because the
frozen stage-1 and stage-2 records and design records pin these files by SHA-256. What they do for IdCon:

| module | role in IdCon |
|---|---|
| `hard_benchmark.py` | generator of the synthetic suites (IdCon-Hard, -Hard-X, -Hard-H), method dispatch, timed driver (`infer`), reference builder (`reference`) |
| `external_hprd.py`, `external_hprd_x.py` | importers of IdCon-HPRD, -HPRD-X, -HPRD-H |
| `external_cite.py` | importer of IdCon-Cite (stage 3) |
| `lad_baseline.py`, `glasgow_baseline.py` | two-query adapters for LAD2025 and the Glasgow Subgraph Solver (also used by the reference builder) |
| `comparison_baselines.py`, `full_benchmark_methods.py`, `semantic_projection.py`, `projection_engine.py` | CP-SAT and Trad-CP adapters and the shared graph front end (`projection_engine.graph_data`); `projection_engine.vectors` and the force/boundary/material code are unused legacy |
| `revision_baselines.py` | Enum-Glasgow, Enum-VF2, ASP-cautious (stage 2) |
| `sat_baseline.py` | SAT baseline (stage 3), built on `../independent/cnf_encoding.py` |
| `coordination_confirmation_data.py` | `legal()`: the witness replay checker used by the reference builder and scoring (re-exported by `witness_check.py`); `state_query()`: CP-SAT exact-state queries |
| `final_confirmation_evidence.py` | `predicate_range()`: states excluded by the observation tables |
| `score_idcon.py`, `analysis_tables.py`, `r2_analyses.py`, `r2_tables.py`, `revision_analyses.py` | scoring and every table, macro and analysis of the paper |
| `revision_*.py`, `r2_*.py` | registration, orchestration, reruns, counts of stages 2 (`revision_*`) and 3 (`r2_*`) |
| `diagnostic_engine.py`, `complex_core.py`, `inference.py`, `final_confirmation_study.py`, `submission_data.py` | legacy prototypes; `submission_data.graph` and `bfs_nodes` generate IdCon hosts and patterns |

The independent reference check (`../independent/`) deliberately imports nothing from this folder.
