# Axis — Gut Microbiome Analytics for Alzheimer's Research

A desktop application that fetches real gut microbiome sequencing data from public research databases, processes it through a bioinformatics pipeline, and generates diversity analysis and an experimental Alzheimer's disease risk assessment.

---

## What This App Does

Research suggests the bacteria living in your gut (the **gut microbiome**) may be connected to brain health and Alzheimer's disease.  lets researchers:

1. Look up any public gut microbiome study by its database ID
2. Automatically download and process the raw DNA sequencing data
3. Identify which bacteria are present and in what proportions
4. Visualize diversity metrics and evolutionary relationships
5. Generate an Alzheimer's risk prediction based on the bacterial profile

---

## Key Terms

| Term | Plain English |
|---|---|
| **NCBI** | The US government's public database for biology research — like a library for DNA data |
| **BioProject** (`PRJNA...`) | A study in the NCBI library — a folder containing all data from one research study |
| **SRA Run** (`SRR...`) | One individual DNA sequencing experiment within a study |
| **FASTQ** | The raw output file from a DNA sequencer — a text file with millions of DNA "reads" |
| **16S rRNA sequencing** | The technique used to identify gut bacteria by reading one specific gene that acts as a bacterial "barcode" |
| **QIIME2** | Software that turns raw FASTQ files into a list of which bacteria are present and how many |
| **DADA2** | A denoising algorithm inside QIIME2 that cleans up errors in the raw DNA reads (like spell-checking DNA) |
| **ASV** (Amplicon Sequence Variant) | A unique, error-corrected DNA barcode — each ASV represents one distinct bacterial type |
| **SILVA database** | A reference encyclopedia of known bacterial DNA barcodes, used to identify which bacterium each ASV belongs to |
| **Genus** | A biological classification level (above species), e.g., *Bacteroides*, *Prevotella* |
| **Relative abundance** | What percentage of the total bacteria in a sample belongs to each genus |
| **Alpha diversity** | How many different bacterial species are in one sample — higher = more diverse |
| **Shannon / Simpson index** | Formulas that measure diversity: Shannon captures variety, Simpson captures dominance |
| **Beta diversity** | How different two samples are from each other (0 = identical, 1 = completely different) |
| **Bray-Curtis dissimilarity** | A standard formula for comparing two microbiome samples |
| **UniFrac** | Like Bray-Curtis, but also considers the evolutionary relatedness of the bacteria |
| **PCoA** (Principal Coordinates Analysis) | A 2D scatter plot that groups similar samples visually — a "map" of how samples relate |
| **Phylogenetic tree** | A diagram showing the evolutionary relationships between detected bacteria |
| **Paired-end / Single-end** | How DNA was read: paired-end reads both ends of each fragment (more accurate), single-end reads only one |

---

## Workflow

```
[1] LOGIN / REGISTER
    Each user has their own account and project history
          │
          ▼
[2] ENTER BioProject ID (e.g. PRJNA1020741)
    Select max runs (1–20), optionally filter by SRR accession
          │
          ▼
[3] FETCH METADATA from NCBI
    • Call 1: Find all sequencing runs in the project
    • Call 2: Get per-run details (read count, library layout, organism)
    • Call 3: Get project title and description
    Project saved to your account history automatically
          │
          ▼
[4] AUTO-DOWNLOAD FASTQ files via fasterq-dump
    • Each run downloaded to  data/<BioProject>/fastq/<layout>/
    • QIIME2 manifest files written automatically
    • Upload Runs page shows ✓ Uploaded for each run
    (skipped gracefully if SRA Toolkit is not installed)
          │
          ▼
[5] IN-APP ANALYSIS (automatic, no QIIME2 needed)
    • Genus abundance profiles (based on literature microbiome values)
    • Alpha diversity: Shannon entropy + Simpson index (with bootstrap)
    • Beta diversity: Bray-Curtis + UniFrac dissimilarity matrices
    • PCoA: classical MDS from Bray-Curtis (no scipy needed)
    • Phylogenetic tree text for top genera
    • Alzheimer risk score from published biomarker weights
          │
          ├─── [6A] EXPLORE RESULTS
          │    ┌──────────────┬────────────────────────────────────────────┐
          │    │ Overview     │ Project summary, run status, counts        │
          │    │ Upload Runs  │ Download status, Run Pipeline button       │
          │    │ Diversity    │ Alpha boxplots, beta heatmap, PCoA plot    │
          │    │ Taxonomy     │ Genus abundance bar charts per run         │
          │    │ ASV Table    │ Full feature table                         │
          │    │ Phylogeny    │ Evolutionary tree of detected bacteria     │
          │    │ Alzheimer    │ Risk score + key biomarker bacteria        │
          │    │ Export PDF   │ Save full report                           │
          │    │ Profile      │ Account info, project history, past runs   │
          │    └──────────────┴────────────────────────────────────────────┘
          │
          └─── [6B] OPTIONAL: REAL QIIME2 PIPELINE
                    Click "Run Pipeline" on Upload Runs page
                    Requires: QIIME2 conda env + downloaded FASTQ files
                    • Import FASTQ → QC → DADA2 denoising → SILVA classify
                    • Real ASV counts replace simulated data on all pages
                    Falls back to in-app analysis if QIIME2 not installed
          │
          ▼
[7] ALZHEIMER RISK ASSESSMENT
    Literature-based model (Vogt 2017, Liu 2019, Shen 2021):
    • Protective genera weighted negatively (Faecalibacterium, Akkermansia…)
    • Risk genera weighted positively (Prevotella, Clostridium, Veillonella…)
    • Risk probability (0–100%), confidence score, Low/Moderate/High label
    • Key biomarker breakdown with reference ranges
```

---

## Project Structure

```
AD-GMB-Diagnosis-App/
├── README.md
├── requirements.txt
│
└── src/
    ├── main.py                    ← entry point (run this)
    ├── requirements.txt
    │
    ├── models/
    │   ├── app_state.py           ← shared runtime state (AppState, RunState)
    │   ├── data_models.py         ← pure-Python dataclasses
    │   └── example_data.py        ← placeholder data for empty state
    │
    ├── services/
    │   ├── ncbi_service.py        ← fetches BioProject + run metadata from NCBI
    │   ├── analysis_service.py    ← computes diversity metrics and taxonomy
    │   ├── assessment_service.py  ← DB bridge: stores/retrieves runs, genera, diversity
    │   └── pipeline_bridge.py     ← loads QIIME2 TSV outputs into AppState
    │
    ├── pipeline/
    │   ├── pipeline.py            ← orchestrates the full QIIME2 pipeline
    │   ├── fetch_data.py          ← downloads FASTQ files from NCBI via fasterq-dump
    │   ├── qiime_preproc.py       ← QIIME2 steps: import → QC → DADA2 → classify → export
    │   ├── qc.py                  ← read quality assessment and truncation point detection
    │   ├── environment.py         ← resolves the qiime2 conda environment path
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
    │   ├── pages.py               ← page classes (Overview, Diversity, Taxonomy, etc.)
    │   ├── upload_page.py         ← FASTQ upload UI and pipeline trigger
    │   ├── dashboard_page.py      ← dashboard layout helpers
    │   ├── intervention_page.py   ← Alzheimer risk + intervention suggestions
    │   ├── export_page.py         ← PDF export page
    │   ├── sidebar.py             ← left navigation panel
    │   ├── panels.py              ← reusable panel components
    │   ├── widgets.py             ← reusable primitive widgets
    │   └── helpers.py             ← UI utility functions
    │
    ├── resources/
    │   └── styles.py              ← colour palette and global QSS stylesheet
    │
    ├── utils/
    │   ├── data_loader.py         ← loads QIIME2 TSV outputs from disk
    │   └── model.py               ← Alzheimer risk ML model
    │
    └── tests/
        ├── test_ncbi_service.py
        └── test_data_loader_integration.py
```

---

## Setup Guide

### Requirements

- Python >= 3.11
- conda (for QIIME2 — only needed for the real pipeline)
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



### Step 3 — Set your NCBI email

NCBI requires a valid email address for API access. Open `src/services/ncbi_service.py` and set:

```python
ENTREZ_EMAIL = "your-email@example.com"
```

Optionally, get a free API key at [ncbi.nlm.nih.gov/account](https://www.ncbi.nlm.nih.gov/account/) for faster requests (10 req/s instead of 3):

```python
ENTREZ_API_KEY = "your-api-key"
```

---



### Step 4  — Install QIIME2 for real ASV analysis

QIIME2 is only needed if you want real DADA2-based denoising and SILVA taxonomic classification. The app runs full in-app analysis (diversity, taxonomy, AD risk) without it.

> **Note for Apple Silicon Macs (M1/M2/M3):** The QIIME2 conda packages are built for x86_64 only. You must force Rosetta 2 emulation using `CONDA_SUBDIR=osx-64`. The steps below handle this automatically.

**Step 7a — Set channel priority to flexible** (required to avoid package conflicts):

```bash
conda config --set channel_priority flexible
```

**Step 7b — Download the environment file:**

```bash
curl -L -O https://data.qiime2.org/distro/amplicon/qiime2-amplicon-2024.10-py310-osx-conda.yml
```

**Step 7c — Remove incompatible packages** (`deblur` and `sortmerna` are not available on macOS):

```bash
sed -i '' '/deblur/d; /sortmerna/d' qiime2-amplicon-2024.10-py310-osx-conda.yml
```

**Step 7d — Create the environment** (uses Rosetta emulation on Apple Silicon):

```bash
CONDA_SUBDIR=osx-64 conda env create -n qiime2-amplicon-2024.10 --file qiime2-amplicon-2024.10-py310-osx-conda.yml
```

This step downloads ~3–5 GB and takes 10–20 minutes.

**Step 7e — Lock the environment to x86_64:**

```bash
conda activate qiime2-amplicon-2024.10
conda config --env --set subdir osx-64
```

**Step 7f — Verify:**

```bash
qiime --version
```

**Windows:** Use WSL2 and follow the Linux instructions (omit `CONDA_SUBDIR=osx-64`).

The SILVA classifier (~1.4 GB) is downloaded automatically on the first pipeline run.

> **Note:** `deblur` (removed above) is an alternative denoising method. The pipeline uses DADA2, so removing deblur has no effect on results.

---

### Step 5 — Install SRA Toolkit (for automatic FASTQ download)

The app automatically downloads FASTQ files from NCBI after fetching a project. This requires `fasterq-dump` from the SRA Toolkit.

```bash
conda install -c bioconda sra-tools
```

Verify the install:

```bash
fasterq-dump --version
```

### Step 6 — Install Python dependencies

```bash
pip install -r requirements.txt
```

This installs:
- `PyQt6` — the desktop UI framework
- `matplotlib` — charts and plots
- `biopython` — NCBI API access
- `sqlalchemy` — local database
- `reportlab` — PDF export
- `pytest` — for running tests

---

### Step 7 — Run the app

```bash
cd src
python main.py
```

The app opens immediately. You can enter any BioProject accession (e.g. `PRJNA1020741`) and explore simulated analysis results right away — no QIIME2 installation needed for this mode.

---

Once installed, FASTQ files are downloaded automatically to `data/<BioProject>/fastq/` after every fetch. No manual steps needed.

---

## Usage

### Standard workflow (SRA Toolkit required, QIIME2 optional)

```
Fetch NCBI metadata
      ↓
Auto-download FASTQ files via fasterq-dump  →  saved to data/<BioProject>/fastq/
      ↓
Upload Runs page auto-populates with downloaded files
      ↓
In-app analysis runs automatically
(diversity, taxonomy, PCoA, Alzheimer risk)
      ↓
[Optional] Click "Run Pipeline" for real QIIME2 DADA2 analysis
```

1. Launch the app: `python main.py`
2. Register or log in
3. On the **Overview** page, enter a BioProject accession (e.g. `PRJNA1020741`)
4. Select max runs from the dropdown (1–20) and click **Fetch**
5. The app fetches metadata from NCBI, then automatically downloads the FASTQ files
6. The **Upload Runs** page shows download status — all runs marked ✓ Uploaded automatically
7. In-app analysis completes and all pages (Diversity, Taxonomy, Phylogeny, Alzheimer Risk) populate
8. If QIIME2 is installed, click **Run Pipeline** on the Upload Runs page for real DADA2 results

### Without SRA Toolkit (metadata + simulated analysis only)

If `fasterq-dump` is not installed, the app still works — it fetches NCBI metadata and runs in-app analysis with biologically realistic simulated profiles. A warning appears on the Upload Runs page with install instructions.

### Without QIIME2

The **Run Pipeline** button checks for QIIME2 before starting. If not found, it falls back to in-app analysis automatically — no crash, no manual action needed.

### Example BioProject accessions to try

| Accession | Description |
|---|---|
| `PRJNA1020741` | Human gut microbiome study |
| `PRJNA31257` | Homo sapiens gut microbiome |
| `PRJNA743840` | Human gut 16S rRNA amplicon study |



Project : PRJNA1028813                        
Process : SRR26409620 

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
| Shared runtime data | `models/app_state.py` |
| NCBI API calls | `services/ncbi_service.py` |
| Analysis computation | `services/analysis_service.py` |
| Database persistence | `db/` + `services/assessment_service.py` |
| QIIME2 pipeline steps | `pipeline/` |
| UI pages and layout | `ui/` |
| Theming and styles | `resources/styles.py` |

The UI layers never call the pipeline or database directly — they receive data through explicit `page.load(state)` calls from `MainWindow`. This means all analysis logic can be tested without starting the Qt application.

---

## Two Analysis Modes

| Mode | Requires | How it works | When to use |
|---|---|---|---|
| **In-app analysis** | Nothing extra | Genus profiles interpolated from published AD microbiome literature; real Shannon/Simpson/Bray-Curtis math; classical MDS PCoA | Default — runs automatically after every fetch |
| **Real QIIME2 pipeline** | QIIME2 env + fasterq-dump | Downloads FASTQ → DADA2 denoising → SILVA classification → real ASV counts | Research-grade results with actual sequencing data |

When real pipeline results are available they automatically replace the in-app results on all pages. If QIIME2 is not installed, clicking "Run Pipeline" falls back to in-app analysis with an informational message.
