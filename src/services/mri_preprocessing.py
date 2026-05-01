"""
MRI preprocessing for Alzheimer's disease risk assessment.

Steps applied to every .nii / .nii.gz volume:
    1. Load with nibabel
    2. Resample to 1 mm isotropic voxels (if needed)
    3. Clip intensity to [1st, 99th] percentile of non-zero voxels
    4. Z-score normalise using brain-mask (non-zero) statistics
    5. Return float32 array with non-brain voxels zeroed

Endpoint for the risk model
---------------------------
After preprocessing call your model as shown below, then render results:

    from src.services.mri_preprocessing import preprocess_mri

    mri_array = preprocess_mri(nii_path)          # float32 ndarray (X, Y, Z)
    apoe      = {"e2": 0, "e3": 1, "e4": 1}       # allele copy counts

    risk_result = your_model.predict(mri_array, apoe)
    # risk_result expected keys: predicted_pct, confidence_pct, risk_level,
    #   biomarkers (list of dicts with: name, value, unit, status, normal, role)
"""
from __future__ import annotations

import numpy as np


def preprocess_mri(nii_path: str) -> np.ndarray:
    """
    Parameters
    ----------
    nii_path : str
        Absolute path to a .nii or .nii.gz file.

    Returns
    -------
    np.ndarray, shape (X, Y, Z), dtype float32
        Preprocessed 3-D volume. Non-brain voxels are zeroed.
    """

    return np.zeros((1, 1, 1), dtype=np.float32)  # placeholder
