"""
Compute alpha and beta diversity metrics from DB data and persist results.

Alpha:  Shannon entropy + Simpson index  (per-run, from feature counts)
Beta:   Bray-Curtis dissimilarity matrix  (pairwise, from genus abundances)
PCoA:   First two principal coordinates   (per-run, from beta matrix)
"""
from __future__ import annotations

import math
import numpy as np

from src.services.assessment_service import (
    get_feature_counts,
    get_genus_data,
    store_alpha_diversities,
    store_beta_diversity,
    store_pcoa,
    ServiceError,
)


# ── Alpha ─────────────────────────────────────────────────────────────────────

def _alpha_from_counts(feature_counts: list[dict]) -> dict[str, float]:
    counts = [fc["abundance"] for fc in feature_counts if fc["abundance"] > 0]
    if not counts:
        return {}
    total = sum(counts)
    props = [c / total for c in counts]

    shannon = -sum(p * math.log2(p) for p in props)
    simpson = 1.0 - sum(p * p for p in props)

    return {
        "shannon":           round(shannon, 4),
        "simpson":           round(simpson, 4),
        "observed_features": float(len(counts)),
    }


def compute_and_store_alpha(run_id: int) -> dict[str, float]:
    """Compute + persist alpha diversity for one run. Returns metrics dict."""
    fcs = get_feature_counts(run_id)
    metrics = _alpha_from_counts(fcs)
    if metrics:
        store_alpha_diversities(run_id, metrics)
    return metrics


# ── Beta (Bray-Curtis) ────────────────────────────────────────────────────────

def _bray_curtis(u: dict[str, float], v: dict[str, float]) -> float:
    genera = set(u) | set(v)
    num = sum(abs(u.get(g, 0.0) - v.get(g, 0.0)) for g in genera)
    den = sum(u.get(g, 0.0) + v.get(g, 0.0) for g in genera)
    return num / den if den > 0 else 0.0


def _pcoa_2d(dist_matrix: np.ndarray) -> np.ndarray:
    """Classical MDS on a symmetric distance matrix → (n, 2) coordinate array."""
    n = dist_matrix.shape[0]
    D2 = dist_matrix ** 2
    H = np.eye(n) - np.ones((n, n)) / n
    B = -0.5 * H @ D2 @ H
    # Symmetrise to suppress floating-point noise before eig
    B = (B + B.T) / 2
    vals, vecs = np.linalg.eigh(B)
    # Sort descending
    idx = np.argsort(vals)[::-1]
    vals, vecs = vals[idx], vecs[:, idx]
    # Keep first two positive eigenvectors
    coords = np.zeros((n, 2))
    for k in range(min(2, n - 1)):
        if vals[k] > 0:
            coords[:, k] = vecs[:, k] * math.sqrt(vals[k])
    return coords


def compute_and_store_beta(run_ids: list[int]) -> None:
    """
    Compute pairwise Bray-Curtis dissimilarity and PCoA for a list of run IDs.
    Safe to call with a single run (no-op for beta/PCoA).
    """
    if len(run_ids) < 2:
        return

    # Load genus profiles
    profiles: dict[int, dict[str, float]] = {}
    for rid in run_ids:
        rows = get_genus_data(rid)
        if rows:
            profiles[rid] = {r["genus"]: r["relative_abundance"] for r in rows}

    valid = [rid for rid in run_ids if rid in profiles]
    if len(valid) < 2:
        return

    n = len(valid)
    dist = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            bc = _bray_curtis(profiles[valid[i]], profiles[valid[j]])
            dist[i, j] = bc
            dist[j, i] = bc
            try:
                store_beta_diversity(valid[i], valid[j], "bray_curtis", bc)
            except ServiceError:
                pass

    coords = _pcoa_2d(dist)
    for i, rid in enumerate(valid):
        try:
            store_pcoa(rid, "bray_curtis", float(coords[i, 0]), float(coords[i, 1]))
        except ServiceError:
            pass


# ── Convenience entry point ───────────────────────────────────────────────────

def compute_and_store_all(run_ids: list[int]) -> None:
    """Compute alpha for each run + beta/PCoA across all runs."""
    for rid in run_ids:
        try:
            compute_and_store_alpha(rid)
        except ServiceError:
            pass
    compute_and_store_beta(run_ids)
