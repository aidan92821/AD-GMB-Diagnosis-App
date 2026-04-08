# GutSeq — src/

This directory contains all application source code. See the [root README](../README.md) for the full project overview, workflow explanation, glossary, and setup guide.

---

## Quick start

```bash
# From this directory (src/)
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

---

## Module overview

| Directory | Responsibility |
|---|---|
| `models/` | Shared runtime state (`AppState`, `RunState`) and pure-Python dataclasses |
| `services/` | NCBI fetching, analysis computation, database bridge, pipeline output loader |
| `pipeline/` | QIIME2 pipeline steps: fetch → QC → DADA2 → classify → export |
| `db/` | SQLAlchemy ORM models, session setup, repository functions |
| `ui/` | All PyQt6 pages, widgets, sidebar, and `MainWindow` |
| `resources/` | Global QSS stylesheet and colour palette |
| `utils/` | QIIME2 TSV loaders and the Alzheimer risk ML model |
| `tests/` | pytest test suite |

---

## Entry point

```
main.py  →  ui/main_window.py  →  pages load via page.load(AppState)
```

`MainWindow` owns three background workers:
- `_FetchWorker` — calls NCBI and returns a `ProjectRecord`
- `_AnalysisWorker` — computes simulated diversity metrics and risk
- `_PipelineWorker` — runs the real QIIME2 pipeline when FASTQ files are uploaded
