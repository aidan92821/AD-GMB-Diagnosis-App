# GutSeq — Gut Microbiome Analytics for Alzheimer's Research

A desktop application that fetches real gut microbiome sequencing data from public research databases, processes it through a bioinformatics pipeline, and generates diversity analysis and an experimental Alzheimer's disease risk assessment.

---

## What This App Does

Research suggests the bacteria living in your gut (the **gut microbiome**) may be connected to brain health and Alzheimer's disease. GutSeq lets researchers:

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
[1] ENTER BioProject ID (e.g. PRJNA1020741)
          │
          ▼
[2] FETCH METADATA from NCBI
    • Call 1: Find all sequencing runs in the project
    • Call 2: Get per-run details (read count, library layout, organism)
    • Call 3: Get project title and description
          │
          ▼
[3] VIEW OVERVIEW
    Project info + table of runs (accessions, read counts, layout)
          │
          ├─── [4A] SIMULATED ANALYSIS (instant, no QIIME2 needed)
          │         Generates realistic results from run metadata:
          │         genus abundances, alpha/beta diversity, PCoA,
          │         phylogenetic tree, Alzheimer risk score
          │
          └─── [4B] REAL PIPELINE (requires QIIME2 + FASTQ files)
                    Upload FASTQ files → click "Run Pipeline"
                    Step 1: Download raw DNA files from NCBI
                    Step 2: Download SILVA classifier (~1.4 GB, one-time)
                    Step 3: QIIME2 pipeline:
                      • Import FASTQ into QIIME2 format
                      • QC: Assess read quality, find truncation points
                      • DADA2: Denoise reads → clean ASVs
                      • Classify: Match ASVs to SILVA → identify bacteria
                      • Export: TSV tables (ASV counts, genus abundances)
                    Results replace simulated data on all pages
          │
          ▼
[5] EXPLORE RESULTS ACROSS PAGES
    ┌──────────────┬──────────────────────────────────────────────────┐
    │ Overview     │ Project summary, run status, ASV/genus counts    │
    │ Upload Runs  │ FASTQ file upload and pipeline trigger           │
    │ Diversity    │ Alpha boxplots, beta heatmap, PCoA scatter plot  │
    │ Taxonomy     │ Bar charts of genus abundances per run           │
    │ ASV Table    │ Full table of detected bacterial sequences       │
    │ Phylogeny    │ Evolutionary tree of detected bacteria           │
    │ Alzheimer    │ Risk score + key bacteria driving the prediction │
    │ Export PDF   │ Save the full report                             │
    └──────────────┴──────────────────────────────────────────────────┘
          │
          ▼
[6] ALZHEIMER RISK ASSESSMENT
    ML model takes the genus abundance profile and outputs:
    • Risk probability (0–100%)
    • Risk label: Low / Moderate / High
    • Key biomarker bacteria driving the prediction
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

### Step 3 — Install Python dependencies

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

### Step 4 — Set your NCBI email

NCBI requires a valid email address for API access. Open `src/services/ncbi_service.py` and set:

```python
ENTREZ_EMAIL = "your-email@example.com"
```

Optionally, get a free API key at [ncbi.nlm.nih.gov/account](https://www.ncbi.nlm.nih.gov/account/) for faster requests (10 req/s instead of 3):

```python
ENTREZ_API_KEY = "your-api-key"
```

---

### Step 5 — Run the app

```bash
cd src
python main.py
```

The app opens immediately. You can enter any BioProject accession (e.g. `PRJNA1020741`) and explore simulated analysis results right away — no QIIME2 installation needed for this mode.

---

### Step 6 (Optional) — Install QIIME2 for the real pipeline

The real pipeline requires QIIME2 installed in a conda environment. This is only needed if you want to process actual FASTQ files.

**macOS / Linux:**

```bash
conda env create \
  -n qiime2-amplicon-2024.10 \
  --file https://data.qiime2.org/distro/amplicon/qiime2-amplicon-2024.10-py310-osx-conda.yml
```

**Windows:** Use WSL2 (Windows Subsystem for Linux) and follow the Linux instructions.

After installing QIIME2, also install SRA Toolkit (provides `fasterq-dump` for downloading FASTQ files from NCBI):

```bash
# macOS (via conda)
conda install -c bioconda sra-tools

# Or download from: https://github.com/ncbi/sra-tools/wiki/01.-Downloading-SRA-Toolkit
```

The SILVA classifier (~1.4 GB) is downloaded automatically on first pipeline run.

---

## Usage

### Simulated analysis (no QIIME2 needed)

1. Launch the app: `python main.py`
2. On the **Overview** page, enter a BioProject accession (e.g. `PRJNA1020741`)
3. Optionally enter a specific Run accession (`SRR...`) or set the max number of runs
4. Click **Fetch**
5. The app fetches real metadata from NCBI and populates all pages with analysis

### Real pipeline (requires QIIME2)

1. Complete the fetch step above
2. Go to the **Upload Runs** page
3. Select the FASTQ file for each run
4. Once all files are uploaded, click **Run Pipeline**
5. QIIME2 processes the data in the background — all pages update when done

### Example BioProject accessions to try

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

| Mode | How it works | When to use |
|---|---|---|
| **Simulated** | Derives realistic values from run metadata (read counts, library layout) using deterministic math | Quick exploration, demos, development without QIIME2 |
| **Real pipeline** | Downloads FASTQ → runs QIIME2 DADA2 → classifies against SILVA | Actual research analysis |

When real pipeline results are available they automatically replace the simulated data on all pages.
