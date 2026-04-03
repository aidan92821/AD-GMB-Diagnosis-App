# Pipeline code review — findings and fixes
# Generated from systematic testing of all 5 files

FINDINGS = """
╔══════════════════════════════════════════════════════════════════════════════╗
║                    PIPELINE CODE REVIEW — FINDINGS                         ║
╚══════════════════════════════════════════════════════════════════════════════╝

┌──────────────────────────────────────────────────────────────────────────┐
│ FILE: qc.py  →  find_median_drop()                                       │
│ SEVERITY: 🔴 BUG — will crash at runtime                                 │
├──────────────────────────────────────────────────────────────────────────┤
│ Line 43:  trunc_len = pos.idmax()                                        │
│ PROBLEM:  pandas.Series has no method .idmax()                           │
│           The correct method is .idxmax()                                │
│ EFFECT:   AttributeError crash every time quality drops below threshold  │
│ FIX:      pos.idxmax()                                                   │
└──────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│ FILE: qc.py  →  get_min_run_len()                                        │
│ SEVERITY: 🟡 BUG — wrong result for multi-run projects                   │
├──────────────────────────────────────────────────────────────────────────┤
│ Line 23:  return min(lengths)                                            │
│ PROBLEM:  lengths is a list of STRINGS.                                  │
│           min(['251', '150', '100']) == '100' by lexicographic order     │
│           but min(['251', '75', '200']) == '200' — WRONG (should be 75) │
│ EFFECT:   Incorrect truncation length for datasets with short reads      │
│ FIX:      return min(int(x) for x in lengths)                           │
└──────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│ FILE: qiime_preproc.py  →  module-level env resolution                   │
│ SEVERITY: 🔴 CRASH — will crash the GUI on startup if QIIME2 missing    │
├──────────────────────────────────────────────────────────────────────────┤
│ Lines 9-16 run at IMPORT TIME:                                           │
│   env_path = get_conda_env_path(ENV_NAME)                                │
│ PROBLEM:  If the qiime2-amplicon-2024.10 conda env is not installed,    │
│           importing this module raises RuntimeError immediately.         │
│           This will crash the GUI on launch.                             │
│ FIX:      Move env resolution inside a lazy-loading function or use      │
│           try/except to degrade gracefully.                              │
└──────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│ FILE: qiime_preproc.py  →  dada2_denoise()                               │
│ SEVERITY: 🟡 SILENT FAILURE — no error when called incorrectly          │
├──────────────────────────────────────────────────────────────────────────┤
│ PROBLEM:  if trunc_f: / elif trunc_s: — both default to None            │
│           If neither is provided, the function silently does nothing.    │
│ FIX:      Add an explicit else: raise ValueError(...)                   │
└──────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│ FILE: pipeline.py  →  run_pipeline()                                     │
│ SEVERITY: 🟢 MINOR — unused parameter                                   │
├──────────────────────────────────────────────────────────────────────────┤
│ PROBLEM:  project_id parameter is accepted but never used                │
│ FIX:      Remove it, or use it (e.g. as a label in output paths)        │
└──────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│ DEPENDENCIES — all must be installed for the pipeline to run             │
├──────────────────────────────────────────────────────────────────────────┤
│  esearch / efetch    NCBI Entrez Direct CLI tools                        │
│    Install: https://www.ncbi.nlm.nih.gov/books/NBK179288/               │
│                                                                          │
│  fasterq-dump        SRA Toolkit                                         │
│    Install: https://github.com/ncbi/sra-tools/wiki/01.-Downloading-SRA  │
│                                                                          │
│  qiime2-amplicon-2024.10  QIIME2 conda environment                      │
│    Install: https://docs.qiime2.org/2024.10/install/native/             │
│                                                                          │
│  SILVA classifier (~1.4 GB download, auto-fetched by pipeline.py)       │
│    URL: https://data.qiime2.org/classifiers/sklearn-1.4.2/silva/        │
│         silva-138-99-nb-classifier.qza                                  │
└──────────────────────────────────────────────────────────────────────────┘

FUNCTIONS SAFE TO USE AS-IS (after fixes applied):
  ✓ environment.get_conda_env_path()    — logic correct, needs conda
  ✓ fetch_data.get_runs()              — logic correct, needs esearch/efetch
  ✓ fetch_data.fetch_runs()            — logic correct, needs fasterq-dump
  ✓ fetch_data.write_manifest()        — tested, works correctly
  ✓ fetch_data.cleanup()               — straightforward, correct
  ✓ fetch_data.fetch_ncbi_data()       — orchestrator, correct
  ✓ qiime_preproc.import_samples()     — correct after module-level fix
  ✓ qiime_preproc.qc()                 — correct after module-level fix
  ✓ qiime_preproc.dada2_denoise()      — correct after adding guard
  ✓ qiime_preproc.classify_taxa()      — correct after module-level fix
  ✓ qiime_preproc.create_tables()      — correct after module-level fix
  ✓ qiime_preproc.download_classifier() — correct
  ✓ pipeline.run_pipeline()            — correct after removing unused param
"""

print(FINDINGS)