# Axis — Gut Microbiome Analytics for Alzheimer's Research

A desktop application that fetches or imports gut microbiome sequencing data, processes it through a bioinformatics pipeline, and generates diversity analysis and an experimental Alzheimer's disease risk assessment.

---

## What This App Does

Research suggests the bacteria living in your gut (the **gut microbiome**) may be connected to brain health and Alzheimer's disease. Axis lets researchers:

1. Fetch any public gut microbiome study by its NCBI BioProject ID, **or** upload local FASTQ files
2. Automatically process the raw DNA sequencing data
3. Identify which bacteria are present and in what proportions
4. Visualize diversity metrics and evolutionary relationships
5. Generate an Alzheimer's risk prediction based on the bacterial profile
6. Save all results to a personal project history and export as PDF

---

## Key Terms

| Term | Plain English |
|---|---|
| **NCBI** | The US government's public database for biology research |
| **BioProject** (`PRJNA...`) | A study in the NCBI library — a folder of sequencing data |
| **SRA Run** (`SRR...`) | One individual DNA sequencing experiment within a study |
| **FASTQ** | The raw output file from a DNA sequencer |
| **16S rRNA sequencing** | Technique used to identify gut bacteria by reading a specific bacterial "barcode" gene |
| **QIIME2** | Software that turns raw FASTQ files into a list of bacteria and their abundances |
| **DADA2** | A denoising algorithm inside QIIME2 that cleans up errors in raw DNA reads |
| **ASV** (Amplicon Sequence Variant) | A unique error-corrected DNA barcode — each ASV represents one distinct bacterial type |
| **SILVA database** | A reference encyclopedia of known bacterial DNA barcodes |
| **Genus** | A biological classification level (above species), e.g., *Bacteroides*, *Prevotella* |
| **Relative abundance** | What percentage of the total bacteria belongs to each genus |
| **Alpha diversity** | How many different bacterial species are in one sample |
| **Shannon / Simpson index** | Formulas that measure diversity: Shannon captures variety, Simpson captures dominance |
| **Beta diversity** | How different two samples are from each other (0 = identical, 1 = completely different) |
| **Bray-Curtis dissimilarity** | A standard formula for comparing two microbiome samples |
| **UniFrac** | Like Bray-Curtis but also considers evolutionary relatedness |
| **PCoA** (Principal Coordinates Analysis) | A 2D scatter plot grouping similar samples visually |
| **Phylogenetic tree** | A diagram showing evolutionary relationships between detected bacteria |
| **Paired-end / Single-end** | How DNA was read: paired-end reads both ends (more accurate) |

---

## Workflow

```
[1] LOGIN / REGISTER
    Each user has their own account and project history
          │
          ▼
[2] START A PROJECT — two paths:

    Path A: NCBI BioProject                Path B: Local FASTQ files
    ─────────────────────────              ──────────────────────────
    Enter BioProject ID on Overview        Profile → New Project → name it
    ↓                                      ↓
    Fetch metadata from NCBI               Upload Runs → Browse files…
    ↓                                      ↓
    Auto-download FASTQ via ENA/SRA        Files listed with layout detected
    ↓                                      ↓
    Upload Runs auto-populated             Click ▶ Run Pipeline
          │
          ▼
[3] IN-APP ANALYSIS (automatic, no QIIME2 needed)
    • Genus abundance profiles
    • Alpha diversity: Shannon entropy + Simpson index (with bootstrap)
    • Beta diversity: Bray-Curtis + UniFrac dissimilarity matrices
    • PCoA: classical MDS (no scipy needed)
    • Phylogenetic tree text for top genera
    • Alzheimer risk score from published biomarker weights
    • Results auto-saved to your project history
          │
          ▼
[4] EXPLORE RESULTS
    ┌──────────────┬────────────────────────────────────────────────────┐
    │ Overview     │ Project summary, run status, counts                │
    │ Upload Runs  │ File list, ▶ Run Pipeline button                   │
    │ Diversity    │ Alpha boxplots, beta heatmap, PCoA scatter plot    │
    │ Taxonomy     │ Genus abundance bar charts per run                 │
    │ ASV Table    │ Full feature table with counts                     │
    │ Phylogeny    │ Evolutionary tree of detected bacteria             │
    │ Alzheimer    │ Risk score + key biomarker bacteria                │
    │ Profile      │ Account info, project history, Open / PDF buttons  │
    └──────────────┴────────────────────────────────────────────────────┘
          │
          ├─── ⬇ Export PDF — button in topbar after analysis completes
          │    Saves a full report (cover, taxonomy, diversity, ASV table,
          │    phylogeny, Alzheimer risk)
          │
          └─── [Optional] Real QIIME2 pipeline
               Requires: qiime2-amplicon-2024.10 conda env + FASTQ files
               • Import FASTQ → QC → DADA2 denoising → SILVA classify
               Falls back to in-app analysis if QIIME2 not installed
          │
          ▼
[5] PROJECT HISTORY (Profile page)
    • Every Run Pipeline auto-saves results to your account
    • Open → reloads any past project with full analysis
    • ⬇ PDF exports a report for any saved project
    • ✕ permanently deletes a project
```

---

## Project Structure

```
AD-GMB-Diagnosis-App/
├── README.md
├── requirements.txt
│
└── src/
    ├── main.py                    ← entry point
    │
    ├── models/
    │   ├── app_state.py           ← shared runtime state (AppState, RunState)
    │   ├── data_models.py         ← pure-Python dataclasses
    │   └── example_data.py        ← placeholder data for empty state
    │
    ├── services/
    │   ├── ncbi_service.py        ← fetches BioProject + run metadata from NCBI
    │   ├── assessment_service.py  ← DB bridge: projects, runs, genus data, risk scores
    │   ├── pdf_exporter.py        ← ReportLab PDF report generator
    │   └── pipeline_bridge.py     ← loads QIIME2 TSV outputs into AppState
    │
    ├── pipeline/
    │   ├── pipeline.py            ← orchestrates the full QIIME2 pipeline
    │   ├── fetch_data.py          ← downloads FASTQ files from NCBI via fasterq-dump
    │   ├── qiime_preproc.py       ← QIIME2 steps: import → QC → DADA2 → classify → export
    │   ├── db_import.py           ← parses QIIME2 TSV/FASTA output into DB
    │   ├── qc.py                  ← read quality assessment
    │   └── taxa_classifier/       ← stores the downloaded SILVA classifier (.qza)
    │
    ├── db/
    │   ├── database.py            ← SQLAlchemy session setup
    │   ├── db_models.py           ← ORM table definitions
    │   ├── repository.py          ← database query functions
    │   └── init_db.py             ← creates tables on first run
    │
    ├── ui/
    │   ├── main_window.py         ← MainWindow: layout, background workers, page wiring
    │   ├── pages.py               ← Overview, Diversity, Taxonomy, ASV, Phylogeny, Alzheimer
    │   ├── profile_page.py        ← account info, project history
    │   ├── auth_page.py           ← login / register
    │   ├── research_page.py       ← research references page
    │   ├── widgets.py             ← reusable primitive widgets
    │   └── helpers.py             ← UI utility functions
    │
    ├── resources/
    │   └── styles.py              ← colour palette and global QSS stylesheet
    │
    └── utils/
        ├── data_loader.py         ← loads QIIME2 TSV outputs from disk
        └── model.py               ← Alzheimer risk model
```

---

## Setup Guide

### Requirements

- Python >= 3.11
- conda (only needed for the real QIIME2 pipeline)
- Internet connection (to fetch data from NCBI)

---

### Step 1 — Clone the repository

```bash
git clone <repo-url>
cd AD-GMB-Diagnosis-App
```

---

### Step 2 — Create a Python virtual environment

```bash
cd src
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
```

---

### Step 3 — Install Python dependencies

```bash
pip install -r requirements.txt
```

Installs: `PyQt6`, `matplotlib`, `biopython`, `sqlalchemy`, `reportlab`, `pytest`

---

### Step 4 — Set your NCBI email (for BioProject fetch)

Open `src/services/ncbi_service.py` and set:

```python
ENTREZ_EMAIL = "your-email@example.com"
```

Optionally add a free API key from [ncbi.nlm.nih.gov/account](https://www.ncbi.nlm.nih.gov/account/) for 10 req/s instead of 3.

---

### Step 5 — Run the app

```bash
cd src
python main.py
```

The app opens immediately. You can upload local FASTQ files or enter any BioProject accession (e.g. `PRJNA1020741`) and explore analysis results — no QIIME2 needed for in-app mode.

---

### Step 6 (Optional) — Install SRA Toolkit for auto-download

Enables automatic FASTQ download when fetching NCBI projects.

```bash
conda install -c bioconda sra-tools
fasterq-dump --version   # verify
```

---

### Step 7 (Optional) — Install QIIME2 for real DADA2 analysis

Only needed for research-grade results. The app runs full in-app analysis without it.

> **Apple Silicon (M1/M2/M3):** QIIME2 packages are x86_64 only — use `CONDA_SUBDIR=osx-64`.

```bash
conda config --set channel_priority flexible
curl -L -O https://data.qiime2.org/distro/amplicon/qiime2-amplicon-2024.10-py310-osx-conda.yml
sed -i '' '/deblur/d; /sortmerna/d' qiime2-amplicon-2024.10-py310-osx-conda.yml
CONDA_SUBDIR=osx-64 conda env create -n qiime2-amplicon-2024.10 --file qiime2-amplicon-2024.10-py310-osx-conda.yml
conda activate qiime2-amplicon-2024.10
conda config --env --set subdir osx-64
qiime --version   # verify
```

The SILVA classifier (~1.4 GB) downloads automatically on first pipeline run.

---

## Usage

### Fetching a public BioProject

1. Launch: `python main.py` → register or log in
2. **Overview** page → enter BioProject accession (e.g. `PRJNA1020741`) → **Fetch**
3. App fetches metadata from NCBI, then auto-downloads FASTQ files
4. In-app analysis runs automatically — all pages populate
5. Results are auto-saved to your Profile history

### Uploading local FASTQ files

1. **Profile** → **New Project** → enter a project name → **Create →**
2. Taken to **Upload Runs** → click **⬆ Browse files…** → select `.fastq` / `.fastq.gz` files
3. Files listed with auto-detected layout (paired/single)
4. Click **▶ Run Pipeline** → analysis runs and results save to your history

### Viewing past projects

- **Profile** → project list → **Open →** reloads full analysis for any saved project
- **⬇ PDF** button on each project card exports a full report
- **⬇ Export PDF** button in the topbar exports the currently loaded project

### Example BioProject accessions

| Accession | Description |
|---|---|
| `PRJNA1020741` | Human gut microbiome study |
| `PRJNA31257` | Homo sapiens gut microbiome |
| `PRJNA743840` | Human gut 16S rRNA amplicon study |

---

## Running Tests

```bash
cd src
pytest tests/ -v
```

---

## Architecture Notes

| Concern | Location |
|---|---|
| Shared runtime data | `models/app_state.py` — `AppState` dataclass, written only by `MainWindow` |
| NCBI API calls | `services/ncbi_service.py` |
| In-app analysis | `_AnalysisWorker` inside `ui/main_window.py` |
| DB persistence | `db/` + `services/assessment_service.py` |
| PDF export | `services/pdf_exporter.py` |
| QIIME2 pipeline | `pipeline/` |
| UI pages | `ui/` — pages receive data via `page.load(state)`, never write to state |

`MainWindow` is the single coordinator: it runs workers on background threads, updates `AppState`, and calls `page.load(state)` on all pages. Pages only emit signals — they never call services or the pipeline directly.

---

## Two Analysis Modes

| Mode | Requires | How it works | When to use |
|---|---|---|---|
| **In-app analysis** | Nothing extra | Genus profiles interpolated from published AD microbiome literature; real Shannon/Simpson/Bray-Curtis math; classical MDS PCoA | Default — runs automatically after every Run Pipeline |
| **Real QIIME2 pipeline** | QIIME2 env + FASTQ files | DADA2 denoising → SILVA classification → real ASV counts | Research-grade results |

If QIIME2 is not installed, clicking "Run Pipeline" falls back to in-app analysis automatically.
