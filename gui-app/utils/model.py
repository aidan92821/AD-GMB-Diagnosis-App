"""
utils/model.py
──────────────
Stub for the AD risk prediction model.
Replace the body of `predict_risk` with your actual ML pipeline.
"""
from __future__ import annotations
import random


def predict_risk(microbiome_data: dict, intervention: dict | None = None) -> float:
    """
    Predict Alzheimer's disease risk percentage.

    Parameters
    ----------
    microbiome_data : dict
        Parsed microbiome sample data.
    intervention : dict, optional
        Keys: probiotic, antibiotics, fiber, processed_foods (each -10..+10)

    Returns
    -------
    float
        Risk percentage (0–100).
    """
    # ── Placeholder: random walk from 50 % ──────────────────
    base = 50.0

    if intervention:
        base -= intervention.get("probiotic", 0) * 1.5
        base += intervention.get("antibiotics", 0) * 1.2
        base -= intervention.get("fiber", 0) * 1.0
        base += intervention.get("processed_foods", 0) * 1.3

    return max(1.0, min(99.0, round(base + random.gauss(0, 3), 1)))
