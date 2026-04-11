"""
Axis – example data.

All sample values live here so every panel can import realistic data
without touching any network or file I/O.  Swap these out with real
API calls in services/ncbi_service.py when going to production.
"""

from __future__ import annotations

# ── Project ───────────────────────────────────────────────────────────────────
PROJECT = {
    "bioproject_id": "PRJNA123456",
    "project_id":    "GSE201234",          # <-- distinct from bioproject id
    "title":         "Human Gut Microbiome Study",
    "runs":          ["R1", "R2", "R3", "R4"],
    "run_accessions": {
        "R1": "SRR001001",
        "R2": "SRR001002",
        "R3": "SRR001003",
        "R4": "SRR001004",
    },
    "asv_count":     2841,
    "genus_count":   183,
    "library":       "Paired + Single",
    "uploaded":      {"R1": True, "R2": True, "R3": True, "R4": False},
    "qiime_errors": {
        "R2": "Phred score line length mismatch at record #482. QIIME2 halted."
    },
}

# ── Genus abundances per run ───────────────────────────────────────────────────
GENERA = [
    "Bacteroides", "Prevotella", "Ruminococcus",
    "Faecalibacterium", "Blautia", "Roseburia",
    "Lachnospiraceae", "Akkermansia", "Bifidobacterium", "Lactobacillus",
]

GENUS_ABUNDANCE: dict[str, list[float]] = {
    "R1": [18.3, 12.1, 10.9,  7.4,  5.2,  4.8,  3.6,  2.9,  2.1,  1.8],
    "R2": [22.1,  9.3, 14.2,  5.0,  6.1,  3.9,  2.8,  3.1,  1.9,  1.5],
    "R3": [10.4, 20.2,  8.1, 12.3,  4.5,  5.5,  3.2,  2.7,  2.4,  1.6],
    "R4": [15.0, 15.0, 10.0, 10.0,  5.5,  4.2,  3.8,  3.0,  2.5,  1.9],
}

# ── ASV feature table ─────────────────────────────────────────────────────────
ASV_FEATURES: dict[str, list[dict]] = {
    run: [
        {"id": "ASV_001", "genus": "Bacteroides",      "count": 4821, "pct": 18.3},
        {"id": "ASV_002", "genus": "Prevotella",       "count": 3204, "pct": 12.1},
        {"id": "ASV_003", "genus": "Ruminococcus",     "count": 2880, "pct": 10.9},
        {"id": "ASV_004", "genus": "Faecalibacterium", "count": 1940, "pct":  7.4},
        {"id": "ASV_005", "genus": "Blautia",          "count": 1374, "pct":  5.2},
        {"id": "ASV_006", "genus": "Roseburia",        "count": 1269, "pct":  4.8},
        {"id": "ASV_007", "genus": "Lachnospiraceae",  "count":  952, "pct":  3.6},
        {"id": "ASV_008", "genus": "Akkermansia",      "count":  769, "pct":  2.9},
    ]
    for run in ["R1", "R2", "R3", "R4"]
}

# ── Alpha diversity (box-plot whisker data: min,q1,med,q3,max) ────────────────
ALPHA_DIVERSITY: dict[str, dict] = {
    "R1": {"shannon": (2.8, 3.1, 3.42, 3.7, 4.1), "simpson": (0.78, 0.83, 0.87, 0.91, 0.95)},
    "R2": {"shannon": (3.1, 3.4, 3.71, 4.0, 4.4), "simpson": (0.84, 0.88, 0.91, 0.94, 0.97)},
    "R3": {"shannon": (2.5, 2.9, 3.18, 3.5, 3.8), "simpson": (0.72, 0.78, 0.82, 0.86, 0.90)},
    "R4": {"shannon": (2.9, 3.2, 3.55, 3.8, 4.2), "simpson": (0.81, 0.85, 0.89, 0.92, 0.96)},
}

# ── Beta diversity matrices ───────────────────────────────────────────────────
# Values: dissimilarity 0.0 (identical) → 1.0 (completely different)
BETA_BRAY_CURTIS = [
    [0.00, 0.18, 0.64, 0.71],
    [0.18, 0.00, 0.60, 0.67],
    [0.64, 0.60, 0.00, 0.22],
    [0.71, 0.67, 0.22, 0.00],
]

BETA_UNIFRAC = [
    [0.00, 0.12, 0.55, 0.63],
    [0.12, 0.00, 0.51, 0.58],
    [0.55, 0.51, 0.00, 0.17],
    [0.63, 0.58, 0.17, 0.00],
]

# PCoA coordinates (PC1, PC2) for each metric
PCOA_BRAY_CURTIS = {
    "R1": (-0.38,  0.22),
    "R2": (-0.29,  0.15),
    "R3": ( 0.31, -0.18),
    "R4": ( 0.36, -0.19),
}

PCOA_UNIFRAC = {
    "R1": (-0.30,  0.18),
    "R2": (-0.22,  0.12),
    "R3": ( 0.25, -0.14),
    "R4": ( 0.27, -0.16),
}

# ── Phylogenetic tree (Newick-style text for display) ─────────────────────────
PHYLO_TREE_TEXT = {
    run: (
        "  ┌─── Bacteroides fragilis\n"
        "──┤  └─── Bacteroides thetaiotaomicron\n"
        "  │\n"
        "  ├─── Prevotella copri\n"
        "  │    └─── Prevotella melaninogenica\n"
        "  │\n"
        "  ├─── Ruminococcus gnavus\n"
        "  │\n"
        "  └─── Faecalibacterium prausnitzii\n"
        "       └─── Roseburia intestinalis"
    )
    for run in ["R1", "R2", "R3", "R4"]
}

# ── Alzheimer risk biomarkers ─────────────────────────────────────────────────
ALZHEIMER_RISK = {
    "predicted_pct": 67.0,
    "confidence_pct": 81.0,
    "risk_level": "elevated",
    "biomarkers": [
        {
            "name":    "Faecalibacterium prausnitzii",
            "value":   2.1,   "unit": "%",
            "normal":  ">8%", "role": "Anti-inflammatory",
            "status":  "low",
        },
        {
            "name":    "Akkermansia muciniphila",
            "value":   0.3,   "unit": "%",
            "normal":  ">1%", "role": "Gut barrier integrity",
            "status":  "low",
        },
        {
            "name":    "Proteobacteria (phylum)",
            "value":   24.0,  "unit": "%",
            "normal":  "<5%", "role": "Pro-inflammatory",
            "status":  "high",
        },
        {
            "name":    "Butyrate producers",
            "value":   8.4,   "unit": "%",
            "normal":  ">20%","role": "Neuroprotective",
            "status":  "low",
        },
        {
            "name":    "Bacteroides / Firmicutes ratio",
            "value":   3.2,   "unit": "×",
            "normal":  "~1×", "role": "Dysbiosis marker",
            "status":  "high",
        },
        {
            "name":    "Lactobacillus spp.",
            "value":   4.8,   "unit": "%",
            "normal":  "2–6%","role": "Within range",
            "status":  "normal",
        },
    ],
}