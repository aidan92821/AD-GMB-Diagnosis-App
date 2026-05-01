"""
MRI preprocessing for Alzheimer's disease risk assessment.

Matches the preprocessing applied during model training (Emma Gomez, CPSC 491):
    1. Load NIfTI volume with nibabel
    2. Resize to (128, 128, 128) using scipy.ndimage.zoom
    3. Z-score normalise within brain mask (non-zero voxels)
    4. Return float32 (128, 128, 128) array — non-brain voxels remain 0

The (128, 128, 128) output is passed directly to ImagingModel.predict_proba()
which internally reshapes it to (1, 1, 128, 128, 128) for the 3D CNN.
"""
from __future__ import annotations

import numpy as np

TARGET_SHAPE = (128, 128, 128)


def preprocess_mri(nii_path: str) -> np.ndarray:
    """
    Parameters
    ----------
    nii_path : str
        Absolute path to a .nii or .nii.gz file.

    Returns
    -------
    np.ndarray, shape (128, 128, 128), dtype float32
        Resized and z-score normalised brain volume.
        Non-brain voxels (original zeros) are zeroed out post-normalisation.

    Raises
    ------
    RuntimeError
        If nibabel or scipy are not installed.
    """
    try:
        import nibabel as nib
        from scipy.ndimage import zoom
    except ImportError as exc:
        raise RuntimeError(
            "nibabel and scipy are required for MRI preprocessing.\n"
            "Install them with:  pip install nibabel scipy"
        ) from exc

    img  = nib.load(nii_path)
    data = img.get_fdata(dtype=np.float32)

    # Resize to TARGET_SHAPE regardless of original voxel size
    factors = [t / s for t, s in zip(TARGET_SHAPE, data.shape[:3])]
    data    = zoom(data[..., 0] if data.ndim == 4 else data, factors, order=1).astype(np.float32)

    # Z-score normalise within brain mask
    mask = data > 0
    if mask.any():
        mu    = data[mask].mean()
        sigma = data[mask].std()
        if sigma > 0:
            data = (data - mu) / sigma
        data[~mask] = 0.0

    return data.astype(np.float32)
