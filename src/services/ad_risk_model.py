"""
Alzheimer's Disease Risk Model
================================

Architecture (Emma Gomez, CPSC 491 Senior Capstone 2026)
---------------------------------------------------------
    Branch 1  – Gut microbiome genus abundance  →  XGBoost (TabularModel)
    Branch 2  – APOE genotype                   →  XGBoost (TabularModel)
    Branch 3  – MRI structural scan (optional)  →  3D CNN  (ImagingModel)
    Meta-layer – Logistic Regression stacking all branch probabilities

Trained model files (place in  data/models/ ):
    risk_assess-tab.pkl    ← tabular-only ensemble (microbiome + genetic)
    risk_assess-full.pkl   ← full ensemble including MRI branch

When no model file is found the heuristic fallback is used automatically.

Microbiome preprocessing (must match training):
    1. Extract TOP_20 genera from genus abundance dict (fill 0 if absent)
    2. Add 1e-6 pseudo-count, renormalize to sum 1
    3. CLR transform: log(x / geometric_mean(x))
    → shape (1, 20), columns in TOP_20 order

Genetic preprocessing:
    User inputs ε2, ε3, ε4 copy counts →
    DataFrame columns: e4_count, e3_count, e2_count  (note: e4 first)

Imaging preprocessing:
    preprocess_mri() in mri_preprocessing.py returns (128, 128, 128) float32
    → reshaped to (1, 128, 128, 128) before passing to ImagingModel
"""
from __future__ import annotations

import os
import pickle
import math
import numpy as np
from typing import Optional

# ── Project paths ─────────────────────────────────────────────────────────────
_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
_MODEL_DIR = os.path.join(_PROJECT_ROOT, "data", "models")

# ── TOP_20 genera used by the trained microbiome model ────────────────────────
TOP_20: list[str] = [
    "Bacteroides", "Bifidobacterium", "Enterococcus", "Prevotella",
    "Akkermansia", "Veillonella", "Clostridium", "Eubacterium",
    "Anaerostipes", "Lachnospiraceae", "Lachnoclostridium", "Blautia",
    "Roseburia", "Dorea", "Odoribacter", "UCG-002", "UCG-005",
    "Faecalibacterium", "Alistipes", "Marvinbryantia",
]

# ═════════════════════════════════════════════════════════════════════════════
#  Emma's class definitions — must live here so pickle.load can resolve them
# ═════════════════════════════════════════════════════════════════════════════

try:
    import xgboost as xgb
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import train_test_split, GridSearchCV
    _SKLEARN_XGB_OK = True
except ImportError:
    _SKLEARN_XGB_OK = False

try:
    import torch
    import torch.nn as nn
    _TORCH_OK = True
except ImportError:
    _TORCH_OK = False


class TabularModel:
    """XGBoost classifier with optional GridSearchCV. Used for both microbiome and genetic branches."""

    def __init__(self, name: str, use_gs: bool = True):
        self.name = name
        self.use_gridsearch = use_gs
        self.model = None
        if _SKLEARN_XGB_OK:
            self.base_model = xgb.XGBClassifier(
                use_label_encoder=False,
                eval_metric="logloss",
                random_state=42,
            )

    def fit(self, X, y):
        if not _SKLEARN_XGB_OK:
            raise RuntimeError("xgboost and scikit-learn are required to train TabularModel")
        if self.use_gridsearch:
            param_grid = {
                "n_estimators": [100, 200],
                "max_depth": [3, 4, 6],
                "learning_rate": [0.01, 0.05, 0.1],
                "subsample": [0.8],
                "colsample_bytree": [0.8],
            }
            grid = GridSearchCV(
                estimator=self.base_model,
                param_grid=param_grid,
                scoring="roc_auc",
                cv=3,
                verbose=1,
                n_jobs=1,
            )
            grid.fit(X, y)
            self.model = grid.best_estimator_
            self.best_params_ = grid.best_params_
            self.best_score_ = grid.best_score_
        else:
            self.model = self.base_model
            self.model.fit(X, y)

    def predict_proba(self, X) -> np.ndarray:
        return self.model.predict_proba(X)[:, 1]


if _TORCH_OK:
    class ImagingCNN(nn.Module):
        """3D CNN: (batch, 1, 128, 128, 128) → scalar risk probability per sample."""

        def __init__(self):
            super().__init__()
            self.encoder = nn.Sequential(
                nn.Conv3d(1, 16, kernel_size=3, padding=1), nn.ReLU(), nn.MaxPool3d(2),
                nn.Conv3d(16, 32, kernel_size=3, padding=1), nn.ReLU(), nn.MaxPool3d(2),
                nn.Conv3d(32, 64, kernel_size=3, padding=1), nn.ReLU(), nn.AdaptiveAvgPool3d(4),
            )
            self.classifier = nn.Sequential(
                nn.Flatten(),
                nn.Linear(64 * 4 * 4 * 4, 256), nn.ReLU(), nn.Dropout(0.4),
                nn.Linear(256, 64),              nn.ReLU(), nn.Dropout(0.3),
                nn.Linear(64, 1),                nn.Sigmoid(),
            )

        def forward(self, x):
            return self.classifier(self.encoder(x)).squeeze(1)

    class ImagingModel:
        """Training + inference wrapper for ImagingCNN."""

        def __init__(self, epochs: int = 20, lr: float = 1e-3, device=None):
            self.device = device or torch.device("cpu")
            self.epochs = epochs
            self.lr = lr
            self.net = ImagingCNN().to(self.device)

        def fit(self, X: np.ndarray, y: np.ndarray):
            dataset = torch.utils.data.TensorDataset(
                torch.tensor(X[:, None], dtype=torch.float32),
                torch.tensor(y, dtype=torch.float32),
            )
            loader = torch.utils.data.DataLoader(dataset, batch_size=8, shuffle=True)
            opt = torch.optim.Adam(self.net.parameters(), lr=self.lr)
            loss_fn = nn.BCELoss()
            self.net.train()
            for _ in range(self.epochs):
                for xb, yb in loader:
                    xb, yb = xb.to(self.device), yb.to(self.device)
                    opt.zero_grad()
                    loss_fn(self.net(xb), yb).backward()
                    opt.step()

        def predict_proba(self, X: np.ndarray) -> np.ndarray:
            self.net.eval()
            with torch.no_grad():
                t = torch.tensor(X[:, None], dtype=torch.float32).to(self.device)
                return self.net(t).cpu().numpy()

else:
    class ImagingCNN:  # stub when torch not installed
        pass

    class ImagingModel:  # stub when torch not installed
        def predict_proba(self, X):
            raise RuntimeError("torch is required for MRI inference")


class AlzheimerRiskEnsemble:
    """
    Meta-learner ensemble (LogisticRegression) stacking XGBoost microbiome,
    XGBoost genetic, and 3D-CNN imaging branch probabilities.
    """

    def __init__(self, device=None, use_imaging: bool = False):
        self.use_imaging = use_imaging
        self.microbiome_model = TabularModel("microbiome")
        self.genetic_model    = TabularModel("genetic")
        self.imaging_model    = ImagingModel(epochs=10, device=device) if use_imaging else None
        if _SKLEARN_XGB_OK:
            self.meta_learner = LogisticRegression(C=1.0, max_iter=1000)
            self.meta_scaler  = StandardScaler()
        self._fitted = False

    def _base_predict(self, microbiome, genetic, imaging=None) -> np.ndarray:
        cols = [
            self.microbiome_model.predict_proba(microbiome),
            self.genetic_model.predict_proba(genetic),
        ]
        if self.use_imaging and imaging is not None:
            cols.append(self.imaging_model.predict_proba(imaging))
        return np.column_stack(cols)

    def fit(self, microbiome, genetic, y, imaging=None):
        self.microbiome_model.fit(microbiome, y)
        self.genetic_model.fit(genetic, y)
        if self.use_imaging and imaging is not None:
            self.imaging_model.fit(imaging, y)

        img_val = None
        if self.use_imaging and imaging is not None:
            (mb_tr, mb_val, ge_tr, ge_val, img_tr, img_val,
             y_tr, y_val) = train_test_split(
                microbiome, genetic, imaging, y,
                test_size=0.2, stratify=y, random_state=42,
            )
            self.microbiome_model.fit(mb_tr, y_tr)
            self.genetic_model.fit(ge_tr, y_tr)
            self.imaging_model.fit(img_tr, y_tr)
        else:
            (mb_tr, mb_val, ge_tr, ge_val,
             y_tr, y_val) = train_test_split(
                microbiome, genetic, y,
                test_size=0.2, stratify=y, random_state=42,
            )
            self.microbiome_model.fit(mb_tr, y_tr)
            self.genetic_model.fit(ge_tr, y_tr)

        meta_X = self._base_predict(mb_val, ge_val, img_val)
        meta_X = self.meta_scaler.fit_transform(meta_X)
        self.meta_learner.fit(meta_X, y_val)
        self._fitted = True

    def predict_proba(self, microbiome, genetic, imaging=None) -> np.ndarray:
        assert self._fitted, "Call fit() before predict_proba()"
        meta_X = self._base_predict(microbiome, genetic, imaging)
        meta_X = self.meta_scaler.transform(meta_X)
        return self.meta_learner.predict_proba(meta_X)[:, 1]

    def predict_risk(self, microbiome, genetic, imaging=None) -> dict:
        prob = float(self.predict_proba(microbiome, genetic, imaging)[0])
        return {
            "risk_probability": round(prob * 100, 1),
            "risk_level":       "high" if prob > 0.66 else "moderate" if prob > 0.33 else "low",
            "confidence":       round(abs(prob - 0.5) * 200, 1),
            "modality_scores": {
                "microbiome": round(float(self.microbiome_model.predict_proba(microbiome)[0]) * 100, 1),
                "genetic":    round(float(self.genetic_model.predict_proba(genetic)[0]) * 100, 1),
            },
        }


# ═════════════════════════════════════════════════════════════════════════════
#  Preprocessing helpers
# ═════════════════════════════════════════════════════════════════════════════

def clr_transform(genus_dict: dict[str, float]):
    """
    Build a (1, 20) CLR-transformed DataFrame from a genus abundance dict.
    Matches the preprocessing applied during model training exactly.

    Parameters
    ----------
    genus_dict : dict[str, float]
        Genus name → relative abundance (any scale; will be renormalized).

    Returns
    -------
    pd.DataFrame, shape (1, 20), columns = TOP_20
    """
    import pandas as pd

    row = {g: genus_dict.get(g, 0.0) for g in TOP_20}
    df  = pd.DataFrame([row], columns=TOP_20)

    # Drop Chloroplast if accidentally included
    for col in list(df.columns):
        if col == "Chloroplast":
            df.drop(columns=[col], inplace=True)

    # Add pseudo-count and renormalize
    df = df + 1e-6
    df = df.div(df.sum(axis=1), axis=0)

    # CLR transform
    log_df = np.log(df)
    gm     = log_df.mean(axis=1)
    df     = log_df.sub(gm, axis=0)

    return df[TOP_20]


def format_apoe(e2: int, e3: int, e4: int):
    """
    Build the genetic feature DataFrame expected by the trained genetic XGBoost.

    Parameters
    ----------
    e2, e3, e4 : int
        APOE allele copy counts (each 0–2, sum == 2).

    Returns
    -------
    pd.DataFrame, shape (1, 3), columns = [e4_count, e3_count, e2_count]
    """
    import pandas as pd
    return pd.DataFrame(
        {"e4_count": [e4], "e3_count": [e3], "e2_count": [e2]},
        dtype=float,
    )


# ═════════════════════════════════════════════════════════════════════════════
#  Model loading
# ═════════════════════════════════════════════════════════════════════════════

def _load_trained_model(use_imaging: bool = False) -> "AlzheimerRiskEnsemble | None":
    """
    Load a trained AlzheimerRiskEnsemble from data/models/.

    Tries:
        risk_assess-full.pkl  (use_imaging=True)
        risk_assess-tab.pkl   (tabular only)

    Returns None if no file exists or loading fails.
    """
    fname  = "risk_assess-full.pkl" if use_imaging else "risk_assess-tab.pkl"
    fpath  = os.path.join(_MODEL_DIR, fname)
    # Also try the non-imaging model as fallback for full
    fpath2 = os.path.join(_MODEL_DIR, "risk_assess-tab.pkl")

    for path in ([fpath, fpath2] if use_imaging else [fpath]):
        if os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    model = pickle.load(f)
                if hasattr(model, "_fitted") and model._fitted:
                    return model
            except Exception:
                pass
    return None


# ═════════════════════════════════════════════════════════════════════════════
#  Main inference entry point
# ═════════════════════════════════════════════════════════════════════════════

def predict_ad_risk(
    genus_abundances: dict[str, float],
    apoe: dict[str, int],
    mri_array: Optional[np.ndarray] = None,
) -> dict:
    """
    Predict AD risk, trying the trained model first and falling back to heuristics.

    Parameters
    ----------
    genus_abundances : dict[str, float]
        Genus name → relative abundance (averaged across runs).
        Values can be raw counts or relative — will be renormalized.
    apoe : dict
        {"e2": int, "e3": int, "e4": int}  (each 0–2, sum == 2)
    mri_array : np.ndarray or None
        Float32 (128, 128, 128) array from mri_preprocessing.preprocess_mri().

    Returns
    -------
    dict compatible with AlzheimerPage._render():
        predicted_pct, confidence_pct, risk_level,
        apoe_score, micro_score, mri_score,
        biomarkers (list of dicts)
    """
    e2, e3, e4 = apoe.get("e2", 0), apoe.get("e3", 0), apoe.get("e4", 0)

    model = _load_trained_model(use_imaging=(mri_array is not None))

    if model is not None:
        return _trained_predict(model, genus_abundances, e2, e3, e4, mri_array)
    else:
        return _heuristic_predict(genus_abundances, e2, e3, e4, mri_array)


# ── Trained model path ────────────────────────────────────────────────────────

def _trained_predict(
    model: AlzheimerRiskEnsemble,
    genus_abundances: dict,
    e2: int, e3: int, e4: int,
    mri_array: Optional[np.ndarray],
) -> dict:
    X_micro = clr_transform(genus_abundances)
    X_gen   = format_apoe(e2, e3, e4)
    X_img   = None

    if mri_array is not None and model.use_imaging and model.imaging_model is not None:
        X_img = mri_array[np.newaxis]  # (1, 128, 128, 128)

    raw = model.predict_risk(X_micro, X_gen, X_img)

    micro_pct = raw["modality_scores"]["microbiome"]
    apoe_pct  = raw["modality_scores"]["genetic"]
    mri_pct   = None

    if X_img is not None and model.imaging_model is not None:
        try:
            mri_pct = round(float(model.imaging_model.predict_proba(X_img)[0]) * 100, 1)
        except Exception:
            pass

    biomarkers = _build_biomarkers_trained(
        model, X_micro, genus_abundances,
        micro_pct / 100, apoe_pct / 100,
        mri_pct / 100 if mri_pct is not None else None,
        e2, e3, e4,
    )

    return {
        "predicted_pct":  raw["risk_probability"],
        "confidence_pct": raw["confidence"],
        "risk_level":     raw["risk_level"],
        "apoe_score":     apoe_pct  / 100,
        "micro_score":    micro_pct / 100,
        "mri_score":      mri_pct / 100 if mri_pct is not None else None,
        "biomarkers":     biomarkers,
        "model_source":   "trained",
    }


def _build_biomarkers_trained(
    model, X_micro, genus_dict: dict,
    micro_score: float, apoe_score: float, mri_score,
    e2: int, e3: int, e4: int,
) -> list[dict]:
    bm: list[dict] = []

    # APOE card
    genotype_str = f"ε2×{e2} / ε3×{e3} / ε4×{e4}"
    apoe_status  = "high" if apoe_score > 0.65 else ("low" if apoe_score < 0.35 else "normal")
    bm.append({
        "name":   "APOE Genetic Risk (PRS)",
        "value":  round(apoe_score * 100, 1),
        "unit":   "% risk",
        "status": apoe_status,
        "normal": "< 50 %  (ε3ε3 baseline)",
        "role":   genotype_str,
    })

    # Microbiome dysbiosis card
    micro_status = "high" if micro_score > 0.65 else ("low" if micro_score < 0.35 else "normal")
    bm.append({
        "name":   "Gut Dysbiosis Score (XGBoost)",
        "value":  round(micro_score * 100, 1),
        "unit":   "% risk",
        "status": micro_status,
        "normal": "< 40 %",
        "role":   "CLR-transformed TOP-20 genus abundance",
    })

    # MRI card
    if mri_score is not None:
        mri_status = "high" if mri_score > 0.65 else ("low" if mri_score < 0.35 else "normal")
        bm.append({
            "name":   "MRI Structural Risk (CNN)",
            "value":  round(mri_score * 100, 1),
            "unit":   "% risk",
            "status": mri_status,
            "normal": "< 40 %",
            "role":   "3D CNN · (128³ volume)",
        })
    else:
        bm.append({
            "name":   "MRI Structural Risk (CNN)",
            "value":  0.0, "unit": "",
            "status": "normal",
            "normal": "Upload .nii scan to activate",
            "role":   "Not provided",
        })

    # SHAP genus contributions (via XGBoost pred_contribs)
    try:
        if _SKLEARN_XGB_OK:
            booster  = model.microbiome_model.model.get_booster()
            contribs = booster.predict(
                xgb.DMatrix(X_micro), pred_contribs=True
            )[0, :-1]  # drop bias term
            contributions = dict(zip(TOP_20, contribs))
            ranked = sorted(contributions.items(), key=lambda x: abs(x[1]), reverse=True)

            for genus, contrib in ranked[:5]:
                direction = "increases" if contrib > 0 else "decreases"
                status    = "high" if contrib > 0 else ("low" if contrib < 0 else "normal")
                abund     = genus_dict.get(genus, 0.0)
                bm.append({
                    "name":   genus,
                    "value":  round(abund * 100, 3),
                    "unit":   "% rel. abund.",
                    "status": status,
                    "normal": f"SHAP: {contrib:+.3f}",
                    "role":   f"High abundance {direction} AD risk",
                })
    except Exception:
        pass

    return bm


# ═════════════════════════════════════════════════════════════════════════════
#  Heuristic fallback (no trained model available)
# ═════════════════════════════════════════════════════════════════════════════

# APOE odds ratios — Farrer et al. 1997 JAMA meta-analysis
_APOE_OR: dict[tuple[int, int], float] = {
    (2, 0): 0.40,  # ε2ε2
    (1, 0): 0.62,  # ε2ε3
    (0, 0): 1.00,  # ε3ε3  baseline
    (1, 1): 0.88,  # ε2ε4
    (0, 1): 3.20,  # ε3ε4
    (0, 2): 8.10,  # ε4ε4
}

# Genus weights: + = protective (depleted in AD), - = risk-associated (enriched in AD)
# Sources: Vogt 2017, Cattaneo 2017, Liu 2019 meta-analysis
_GENUS_WEIGHTS: dict[str, float] = {
    "Faecalibacterium": +0.80, "Bifidobacterium": +0.70,
    "Eubacterium":      +0.65, "Lactobacillus":   +0.55,
    "Roseburia":        +0.60, "Akkermansia":      +0.50,
    "Anaerostipes":     +0.45, "Coprococcus":      +0.40,
    "Bacteroides":      -0.50, "Prevotella":       -0.40,
    "Clostridium":      -0.50, "Fusobacterium":    -0.60,
    "Escherichia":      -0.55, "Blautia":          -0.30,
    "Alistipes":        -0.45, "Enterococcus":     -0.35,
    "Veillonella":      -0.30, "Streptococcus":    -0.35,
}


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(max(-500.0, min(500.0, -x))))


def _heuristic_predict(
    genus_abundances: dict,
    e2: int, e3: int, e4: int,
    mri_array: Optional[np.ndarray],
) -> dict:
    # APOE branch
    or_val  = _APOE_OR.get((e2, e4), 1.0)
    p_apoe  = _sigmoid(math.log(max(or_val, 1e-9)) * 0.75)

    # Microbiome branch
    total = sum(genus_abundances.values())
    if total > 0 and genus_abundances:
        normed = {g: v / total for g, v in genus_abundances.items()}
        risk_sum = weight_sum = 0.0
        for genus, weight in _GENUS_WEIGHTS.items():
            ab = normed.get(genus, 0.0)
            if weight > 0:
                risk_sum += weight * (1.0 - min(ab / 0.15, 1.0))
            else:
                risk_sum += abs(weight) * min(ab / 0.20, 1.0)
            weight_sum += abs(weight)
        p_micro = float(np.clip(risk_sum / weight_sum, 0, 1)) if weight_sum else 0.5
    else:
        p_micro = 0.5

    # MRI branch
    p_mri = None
    if mri_array is not None:
        data  = np.asarray(mri_array, dtype=np.float32)
        brain = data != 0
        if brain.any():
            bv       = data[brain]
            vol_risk = float(np.clip(1.0 - brain.mean() / 0.40, 0, 1))
            var_risk = float(np.clip(1.0 - bv.var() / 1.2, 0, 1))
            neg_risk = float(np.clip((bv < -1.0).mean() / 0.25, 0, 1))
            mid      = data.shape[0] // 2
            lv = data[:mid][data[:mid] != 0]
            rv = data[mid:][data[mid:] != 0]
            asym_risk = float(np.clip(abs(lv.mean() - rv.mean()) / 0.4, 0, 1)) if lv.size and rv.size else 0.0
            p_mri = float(np.clip(vol_risk * 0.35 + var_risk * 0.25 + neg_risk * 0.25 + asym_risk * 0.15, 0, 1))

    # Meta-layer
    if p_mri is not None:
        raw = 0.40 * p_apoe + 0.35 * p_micro + 0.25 * p_mri
    else:
        raw = (0.40 / 0.75) * p_apoe + (0.35 / 0.75) * p_micro

    calibrated    = _sigmoid((raw - 0.50) * 4.0) * 0.85 + 0.10
    predicted_pct = float(np.clip(calibrated * 100, 5, 97))

    scores = [p_apoe, p_micro] + ([p_mri] if p_mri is not None else [])
    spread = float(np.std(scores)) if len(scores) > 1 else 0.0
    confidence_pct = float(np.clip((1.0 - spread * 2.5) * 100, 45, 94))

    risk_level = "low" if predicted_pct < 35 else ("moderate" if predicted_pct < 65 else "high")

    biomarkers = _build_biomarkers_heuristic(
        p_apoe, p_micro, p_mri, e2, e3, e4, genus_abundances
    )

    return {
        "predicted_pct":  predicted_pct,
        "confidence_pct": confidence_pct,
        "risk_level":     risk_level,
        "apoe_score":     p_apoe,
        "micro_score":    p_micro,
        "mri_score":      p_mri,
        "biomarkers":     biomarkers,
        "model_source":   "heuristic",
    }


def _build_biomarkers_heuristic(
    p_apoe, p_micro, p_mri, e2, e3, e4, genera: dict
) -> list[dict]:
    bm: list[dict] = []

    genotype_str = f"ε2×{e2} / ε3×{e3} / ε4×{e4}"
    apoe_status  = "high" if p_apoe > 0.65 else ("low" if p_apoe < 0.40 else "normal")
    bm.append({
        "name": "APOE Genetic Risk (PRS)", "value": round(p_apoe * 100, 1),
        "unit": "% risk", "status": apoe_status,
        "normal": "< 50 %  (ε3ε3 baseline)", "role": genotype_str,
    })

    micro_status = "high" if p_micro > 0.60 else ("low" if p_micro < 0.35 else "normal")
    bm.append({
        "name": "Gut Dysbiosis Index (heuristic)", "value": round(p_micro * 100, 1),
        "unit": "% dysbiosis", "status": micro_status,
        "normal": "< 40 %  (healthy profile)",
        "role": "Weighted genus deviation from healthy reference",
    })

    if p_mri is not None:
        mri_status = "high" if p_mri > 0.60 else ("low" if p_mri < 0.35 else "normal")
        bm.append({
            "name": "MRI Structural Risk (heuristic)", "value": round(p_mri * 100, 1),
            "unit": "% atrophy proxy", "status": mri_status,
            "normal": "< 40 %",
            "role": "Volume fraction · intensity variance · asymmetry",
        })
    else:
        bm.append({
            "name": "MRI Structural Risk", "value": 0.0, "unit": "",
            "status": "normal", "normal": "Upload .nii scan to activate",
            "role": "Not provided — upload MRI to activate",
        })

    total = sum(genera.values())
    normed = {g: v / total for g, v in genera.items()} if total > 0 else {}

    protective = sorted(
        [(g, normed.get(g, 0)) for g in _GENUS_WEIGHTS if _GENUS_WEIGHTS[g] > 0 and g in normed],
        key=lambda x: x[1]
    )[:2]
    for g, v in protective:
        bm.append({
            "name": f"{g}  (protective)", "value": round(v * 100, 3),
            "unit": "% rel. abund.",
            "status": "low" if v < 0.05 else "normal",
            "normal": "> 5 %  in healthy cohorts",
            "role": "Butyrate-producing / neuroprotective",
        })

    risk_gen = sorted(
        [(g, normed.get(g, 0)) for g in _GENUS_WEIGHTS if _GENUS_WEIGHTS[g] < 0 and g in normed],
        key=lambda x: -x[1]
    )[:2]
    for g, v in risk_gen:
        bm.append({
            "name": f"{g}  (risk-associated)", "value": round(v * 100, 3),
            "unit": "% rel. abund.",
            "status": "high" if v > 0.15 else "normal",
            "normal": "< 15 %  in healthy cohorts",
            "role": "Pro-inflammatory / LPS-producing",
        })

    return bm
