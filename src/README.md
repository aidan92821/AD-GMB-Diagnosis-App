# GutSeq — Microbiome Analytics Dashboard

A PyQt6 desktop application for analysing human gut microbiome sequencing
data fetched from NCBI, processed through QIIME2, and visualised with
diversity metrics and an experimental Alzheimer's disease risk predictor.

---

## Project structure

```
gutseq/
├── main.py                   ← entry point
├── requirements.txt
│
├── models/
│   └── data_models.py        ← pure-Python dataclasses (no Qt)
│
├── services/
│   └── analysis_service.py   ← NCBI fetching, FASTQ validation,
│                               diversity & risk analysis
│
├── resources/
│   └── styles.py             ← colour palette + global QSS stylesheet
│
├── ui/
│   ├── main_window.py        ← MainWindow (shell + signal wiring)
│   ├── sidebar.py            ← left navigation panel
│   ├── panels.py             ← one class per dashboard section (Steps 1–6)
│   └── widgets.py            ← reusable primitive widgets
│
└── utils/
    └── __init__.py           ← (reserved for future helpers)
```

### Design principles

| Concern              | Location                  |
|----------------------|---------------------------|
| Data structures      | `models/`                 |
| Business / API logic | `services/`               |
| Visual layout        | `ui/panels.py`            |
| Reusable primitives  | `ui/widgets.py`           |
| App wiring           | `ui/main_window.py`       |
| Theming              | `resources/styles.py`     |

Keeping these layers separate means:
- Models and services can be unit-tested without starting Qt.
- Panels receive data through explicit setter methods; they never call
  services directly.
- Swapping in a dark theme only requires editing `styles.py`.

---

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Python ≥ 3.11 recommended.

---

## Usage

1. Enter a BioProject accession (e.g. `PRJNA123456`) and click **Fetch →**.
2. The dashboard populates all six sections automatically.
3. Optionally upload `.fastq` or `.fastq.gz` files for each run.
4. Use the **R1 / R2 / R3 / R4** pill buttons to switch between runs in
   the abundance, taxonomy, and diversity panels.

---

## Connecting to real data

All analysis methods in `services/analysis_service.py` are clearly marked
with `# TODO: real API call`.  To connect live data:

- **NCBI**: install `biopython` and use `Bio.Entrez.esearch` / `efetch`.
- **QIIME2**: install the `qiime2` Python package and call its artifact API.
- **Risk model**: train a classifier (scikit-learn / ONNX) on a cohort
  dataset and replace `_compute_risk_score` with model inference.

---

## Running tests

```bash
pip install pytest
pytest tests/          # (test directory not yet scaffolded — see below)
```

Suggested first tests:
- `test_validate_bioproject_accession` — regex edge cases
- `test_validate_fastq_file` — malformed FASTQ fixtures
- `test_compute_risk_score` — known biomarker inputs → expected score