"""
utils/model.py
──────────────
Gut microbiome → Alzheimer's disease risk model.

Based on published literature:
  • Vogt et al. (2017) Sci Reports  — AD patients show reduced Firmicutes,
    elevated Bacteroidetes; depleted Bifidobacterium, Ruminococcaceae.
  • Liu et al. (2019) Frontiers     — Akkermansia, Faecalibacterium
    negatively correlated with AD cognitive scores.
  • Cattaneo et al. (2017) JAND     — Elevated Escherichia/Shigella and
    depleted E. rectale correlate with brain amyloid burden.
  • Shen et al. (2021) J Neuro.     — Prevotella, Clostridium, Veillonella
    elevated in MCI and AD cohorts.
"""
from __future__ import annotations
import math

# ── Biomarker weights ─────────────────────────────────────────────────────────
# Positive weight  → this genus being HIGH raises AD risk
# Negative weight  → this genus being HIGH lowers AD risk (protective)
# Weights are relative; total protective ≈ total risk to keep baseline ~50 %

BIOMARKER_WEIGHTS: dict[str, float] = {
    # PROTECTIVE (depleted in AD) — negative weights
    "Faecalibacterium":   -0.30,   # major anti-inflammatory SCFA producer
    "Akkermansia":        -0.25,   # gut barrier integrity, inversely correlated with AD
    "Bifidobacterium":    -0.20,   # reduces neuroinflammation; depleted in AD
    "Roseburia":          -0.18,   # butyrate producer; neuroprotective
    "Blautia":            -0.15,   # anti-inflammatory; depleted in AD
    "Eubacterium":        -0.12,   # butyrate; gut–brain axis protection
    "Lachnospiraceae":    -0.10,   # SCFA; inversely correlated with amyloid

    # RISK-ASSOCIATED (elevated in AD) — positive weights
    "Prevotella":         +0.22,   # pro-inflammatory in some gut contexts
    "Clostridium":        +0.20,   # some species produce neurotoxins / LPS
    "Veillonella":        +0.18,   # elevated in MCI and early AD
    "Enterococcus":       +0.16,   # neuroinflammation marker
    "Streptococcus":      +0.12,   # associated with increased gut permeability
    "Escherichia":        +0.14,   # LPS producer; amyloid burden correlate
}

# Reference normal ranges for biomarker card display (% relative abundance)
BIOMARKER_REFERENCE: dict[str, dict] = {
    "Faecalibacterium":  {"normal": ">8%",   "role": "Anti-inflammatory SCFA producer"},
    "Akkermansia":       {"normal": ">1%",   "role": "Gut barrier integrity"},
    "Bifidobacterium":   {"normal": ">2%",   "role": "Neuroinflammation reduction"},
    "Roseburia":         {"normal": ">3%",   "role": "Butyrate / neuroprotection"},
    "Blautia":           {"normal": ">4%",   "role": "Anti-inflammatory"},
    "Prevotella":        {"normal": "<10%",  "role": "Pro-inflammatory marker"},
    "Clostridium":       {"normal": "<4%",   "role": "Neurotoxin-associated species"},
    "Veillonella":       {"normal": "<3%",   "role": "Elevated in MCI/AD"},
    "Enterococcus":      {"normal": "<2%",   "role": "Neuroinflammation marker"},
}


def predict_ad_risk(genus_abundances: dict[str, float]) -> dict:
    """
    Predict Alzheimer's disease risk from genus-level relative abundances.

    Parameters
    ----------
    genus_abundances
        {genus_name: relative_abundance_percent} — values sum to ~100.

    Returns
    -------
    dict with keys:
        risk_probability  float  0–100
        confidence        float  0–100
        risk_label        str    "Low" | "Moderate" | "High"
        biomarkers        list   of biomarker detail dicts for the UI
    """
    total_pct   = sum(genus_abundances.values()) or 100.0
    normed      = {g: v / total_pct * 100 for g, v in genus_abundances.items()}

    # ── Weighted risk score ───────────────────────────────────────────────────
    # Accumulate weighted sum; scale so 0 = perfectly healthy, 100 = high risk
    raw_score = 0.0
    matched   = 0
    for genus, weight in BIOMARKER_WEIGHTS.items():
        abundance = normed.get(genus, 0.0)
        raw_score += weight * abundance
        if genus in normed:
            matched += 1

    # Normalise: raw_score range is roughly -30 to +30 → map to 0–100
    # Baseline is 50 (no information)
    risk = 50.0 + raw_score * 1.4
    risk = max(5.0, min(95.0, risk))

    # ── Confidence ───────────────────────────────────────────────────────────
    # Higher confidence when more key biomarkers are detected
    confidence = min(95.0, 50.0 + matched * 5.0)

    # ── Biomarker detail list for UI ─────────────────────────────────────────
    biomarkers = []
    for genus, ref in BIOMARKER_REFERENCE.items():
        val = normed.get(genus, 0.0)
        if val == 0.0 and genus not in normed:
            continue
        weight = BIOMARKER_WEIGHTS.get(genus, 0.0)
        # Determine status
        if weight < 0:   # protective
            threshold = _parse_threshold(ref["normal"])
            status = "low" if val < threshold else "normal"
        else:            # risk
            threshold = _parse_threshold(ref["normal"])
            status = "high" if val > threshold else "normal"

        biomarkers.append({
            "name":   genus,
            "value":  round(val, 2),
            "unit":   "%",
            "normal": ref["normal"],
            "role":   ref["role"],
            "status": status,
        })

    # Add Bacteroidetes/Firmicutes ratio if we have the data
    firmicutes_genera = ["Faecalibacterium", "Roseburia", "Blautia", "Lachnospiraceae",
                         "Ruminococcus", "Clostridium", "Eubacterium"]
    bacteroidetes_genera = ["Bacteroides", "Prevotella"]
    firm_sum = sum(normed.get(g, 0) for g in firmicutes_genera)
    bact_sum = sum(normed.get(g, 0) for g in bacteroidetes_genera)
    if firm_sum > 0:
        bf_ratio = round(bact_sum / firm_sum, 2)
        biomarkers.append({
            "name":   "Bacteroidetes/Firmicutes ratio",
            "value":  bf_ratio,
            "unit":   "×",
            "normal": "~1×",
            "role":   "Dysbiosis marker",
            "status": "high" if bf_ratio > 2.0 else ("low" if bf_ratio < 0.4 else "normal"),
        })

    return {
        "risk_probability": round(risk, 1),
        "confidence":       round(confidence, 1),
        "risk_label":       _risk_label(risk),
        "biomarkers":       biomarkers,
    }


def compute_shannon(abundances: list[float]) -> float:
    """Shannon entropy H = -Σ p_i · ln(p_i)."""
    total = sum(abundances) or 1.0
    h = 0.0
    for a in abundances:
        p = a / total
        if p > 0:
            h -= p * math.log(p)
    return h


def compute_simpson(abundances: list[float]) -> float:
    """Simpson diversity D = 1 - Σ p_i²."""
    total = sum(abundances) or 1.0
    return 1.0 - sum((a / total) ** 2 for a in abundances)


def bray_curtis(a: dict[str, float], b: dict[str, float]) -> float:
    """
    Bray-Curtis dissimilarity between two genus abundance profiles.
    BC = 1 - 2·Σ min(a_i, b_i) / (Σa + Σb)
    """
    genera = set(a) | set(b)
    shared = sum(min(a.get(g, 0), b.get(g, 0)) for g in genera)
    total  = sum(a.values()) + sum(b.values())
    if total == 0:
        return 0.0
    return round(1.0 - 2.0 * shared / total, 4)


# ── Private helpers ───────────────────────────────────────────────────────────

def _risk_label(probability: float) -> str:
    if probability < 33.0:  return "Low"
    if probability < 66.0:  return "Moderate"
    return "High"


def _parse_threshold(normal_str: str) -> float:
    """Extract numeric threshold from strings like '>8%', '<4%', '>1%'."""
    try:
        return float(normal_str.replace(">", "").replace("<", "").replace("%", "").replace("×", "").replace("~", "").strip())
    except ValueError:
        return 5.0
