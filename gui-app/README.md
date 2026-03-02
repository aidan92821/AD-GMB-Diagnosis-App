# Alzheimer's Risk Assessment Tool

A PyQt5 desktop application for assessing Alzheimer's disease risk from microbiome data,
simulating lifestyle interventions, and exporting reports.

---

## Project Structure

```
alzheimers_risk_app/
├── main.py                   # Entry point
├── requirements.txt
├── assets/
│   └── styles.qss            # Global QSS stylesheet
├── ui/
│   ├── __init__.py
│   ├── main_window.py        # Root window + sidebar navigation
│   ├── dashboard_page.py     # Figure 1 – Dashboard
│   ├── intervention_page.py  # Figure 2 – Intervention Simulation
│   └── export_page.py        # Figure 3 – Export / Report
└── utils/
    ├── model.py               # stub for your ML model
    └── data_loader.py         # CSV / TSV / JSON parser
---

## Create python env
```bash
python -m venv venv
source venv/bin/activate
```


## Installation

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---



### Dashboard (Figure 1)
| Panel | Description |
|---|---|
| **Risk of AD** | Large % badge showing computed risk |
| **Phylogeny of Microbiome Taxa** | Cladogram drawn with QPainter |
| **Uploaded Data** | Drag-and-drop or browse to load CSV/TSV/JSON |
| **Taxa Abundance** | Bar chart (matplotlib) |

### Intervention Simulation (Figure 2)
- Sliders: Probiotic, Antibiotics, Fiber, Processed Foods (range −10 to +10)
- Click **SIMULATE INTERVENTION** to run a simulation step
- Results plotted as a line chart: AD Risk (%) vs. Simulation number

### Export Page (Figure 3)
- Choose **Report Type**, **File Type** (PDF/HTML/DOCX/CSV), and sections to **Include**
- Preview shows live microbiome summary, phylogeny, perturbation trajectory, and taxa chart
- Click **GENERATE REPORT** to save (HTML export works out-of-the-box; add WeasyPrint/python-docx for other formats)

---

## Customisation

### Plug in your real ML model
Edit `utils/model.py` → replace `predict_risk()` with your actual inference pipeline.

### Plug in a real data parser
Edit `utils/data_loader.py` → extend `load_file()` for your specific microbiome file format (e.g. BIOM, QIIME2 artifacts).

### Wire the data loader into the UI
In `ui/dashboard_page.py`, `_load_file()` currently shows a basic summary.  
Call `data_loader.load_file(path)` there and pass the result to `model.predict_risk()`.

---

## Dependencies

| Package | Purpose |
|---|---|
| PyQt5 | GUI framework |
| matplotlib | Charts (bar, line) |
| numpy | Data manipulation |
