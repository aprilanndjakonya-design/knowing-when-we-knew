# Knowing When We Knew — a bitemporal ontology for biomedical knowledge graphs

Phase 1 entry for the NIH "It's About Time: Temporal Reasoning in Biomedical Knowledge Graphs" Challenge (team Bitemporal KG).

Every biomedical fact has two times: when it is true in the world (valid time) and when it became knowable through a
source (availability time). The ontology makes "an as-of query may use only records available at T" a machine-checked
OWL 2 DL axiom: a safety check evaluated at T is typed `usedRecord only KnownAsOf_T`, so a check that uses a record
published after T makes the ontology inconsistent under a reasoner. The data module grounds this in public regulatory
data: every FDA Boxed Warning labeling change approved 2016–2026, the DailyMed version history of each label, RxNorm code
histories and prescriptions of synthetic (Synthea) patients.

## Layout

| Path | What |
|---|---|
| `ontology/its-about-time-bitemporal.ttl` / `.owl` | core ontology 0.1.1 (Turtle source; RDF/XML export) |
| `ontology/its-about-time-data-0.2.ttl` | full data module: 530 applications, 47,499 triples, 2.56 MB |
| `ontology/its-about-time-data-0.2-demo.ttl` | deterministic demonstration subgraph: 120 applications, 8 prescription checks + the 2 scenario checks |
| `ontology/its-about-time-submission-0.2-demo.owl` | **the submitted file**: core + demonstration module merged, RDF/XML, 1.34 MB |
| `ontology/validation_report.txt` | Phase 1 (N1) validation: HermiT, counter-examples A–F, as-of queries, rules R1–R10 |
| `*.py` (repository root) | the reproducible pipeline (see below); scripts find `evidence/`, `synthea/` and `ontology/` next to themselves |
| `evidence/` | every API response the module is built from (JSON), the FDA SrLC snapshots, lag reports, the access log |
| `synthea/` | synthetic patients used in the join (`patients.csv`, `medications.csv`; Synthea seed 4242) |

## Reproduce

Requirements: Python 3.13, `pip install -r requirements.txt` (rdflib 7.6, owlready2 0.51 — owlready2 bundles HermiT and
needs Java 17+), ROBOT 1.9.10 for the RDF/XML export and the OWL 2 DL profile check. No API keys; all sources are public.
Network steps throttle themselves (≤ 2 requests/s) and log every request to `evidence/access_log.json`.

```
python fetch_srlc_dailymed.py --list srlc_bw_list_dated.json --out srlc_dailymed_bw   # DailyMed history per application (~1,600 requests)
python verify_carriers.py --dir evidence/srlc_dailymed_bw --sample 40                  # SPL XML: Boxed Warning section check
python analyze_lags.py srlc_dailymed_bw && python analyze_lags_recent.py    # lag tables, long tail
python check_no_spl.py                                                                # applications without a label (Drugs@FDA)
python map_setids_rxcui.py && python rxnorm_status_table.py                  # RxNorm codes and their history status
python map_synthea_ingredients.py && python join_synthea_bw.py               # prescriptions vs availability windows
python build_abox.py                                                                  # full data module (Turtle)
python build_abox.py --apps 120 --max-cases 8 --out ontology/its-about-time-data-0.2-demo.ttl
python validate_abox.py --skip-hermit                                                 # closed-world rules on the full module (seconds)
python validate_abox.py --data ontology/its-about-time-data-0.2-demo.ttl              # HermiT on the demo (~200 s) + leak control
```

The FDA SrLC snapshots (`evidence/srlc_*`) were taken in a browser because the FDA site rate-limits scripted POSTs; the parsed
JSON is included so every later step runs from the repository alone.

## Validation status

| What | Reasoner / rules | Result |
|---|---|---|
| core ontology 0.1.1 | ROBOT 1.9.10 OWL 2 DL profile; HermiT | in profile; consistent, 0 unsatisfiable classes; counter-examples A–F behave as expected |
| submitted file (core + demo) | ROBOT `reason --reasoner hermit`, individuals realized | consistent, 6 minutes |
| demonstration module | HermiT (owlready2) + leak control | consistent in 197 s; an injected late record makes it inconsistent |
| full module, 530 applications | closed-world rules (`validate_abox.py --skip-hermit`) | 1,210 records, 0 violations, 0 of 62 checks leak; seconds |
| full module, all 62 checks | HermiT (owlready2), one run on a laptop | consistent, 0 unsatisfiable classes — after 84 hours |

## Data sources

DailyMed web services (NLM), FDA Safety-related Labeling Changes database, FDA Drug Safety Communications, Drugs@FDA via openFDA
(CC0), RxNav/RxNorm (NLM, no licence needed, ≤ 20 req/s), Synthea (MITRE, Apache-2.0; synthetic data, no PHI), ChEBI, MONDO,
BFO/IAO/RO, OWL-Time (W3C), Biolink Model 4.4.5, MeSH. Manufacturer label texts are **not** stored: only dates, identifiers and
section identifiers.

## Licence

Code: MIT. Ontology (`ontology/*.ttl`, `*.owl`): CC BY 4.0. Evidence files are facts retrieved from the public sources above under
their own terms.
