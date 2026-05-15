import os
# DO NOT REMOVE OR MOVE
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
# DO NOT REMOVE OR MOVE
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pickle
import xgboost as xgb
from models import AlzheimerRiskEnsemble, TabularModel, ImagingCNN, ImagingModel


# top 20 features
MODEL_GENUS = [
    'Bacteroides',
    'Bifidobacterium',
    'Enterococcus',
    'Prevotella',
    'Akkermansia',
    'Veillonella',
    'Clostridium',
    'Eubacterium',
    'Anaerostipes',
    'Lachnospiraceae',
    'Lachnoclostridium',
    'Blautia',
    'Roseburia',
    'Dorea',
    'Odoribacter',
    'UCG-002',
    'UCG-005',
    'Faecalibacterium',
    'Alistipes',
    'Marvinbryantia',
]


def preprocess_genera(genus_abundance: dict) -> pd.DataFrame:

    abundance = pd.DataFrame([genus_abundance])
    abundance.columns = abundance.columns.str.split("_").str[0]
    abundance = abundance.T.groupby(level=0).sum().T

    # CLR
    abundance += 1e-6
    gm = np.exp(np.log(abundance).mean(axis=1))
    abundance = np.log(abundance.div(gm, axis=0))

    return abundance


# get the subset of genus abundance that is in the top 20 feature list
def get_genus_subset(genus_abundance: pd.DataFrame) -> pd.DataFrame:

    for genus in MODEL_GENUS:
        if genus not in genus_abundance.columns:
            genus_abundance[genus] = 0.0
    
    subset = genus_abundance[MODEL_GENUS]
    return subset


# make a prediction using only microbiome data (use microbiome only model)
# returns a dictionary of size 9 with risk percentage & top 8 contributing genera
# and their effect on the risk prediction
# {'risk': risk_perc, genus: effect}
# if the effect is NEGATIVE -> made risk lower
# if the effect is POSITIVE -> made risk higher
def run_risk_assessment_gmb(genus_abundance_subset: pd.DataFrame) -> dict[str, float]:
    # load the correct model
    with open('risk-assess-gmb.pkl', 'rb') as f:
        model = pickle.load(f)

    # make prediction
    prob = model.predict_proba(genus_abundance_subset)

    # get the feature contributions from each genus
    assessment = get_shap(model.model, genus_abundance_subset)
    assessment['risk'] = float(prob[0])
    assessment['certainty'] = model.prediction_certainty(genus_abundance_subset)
    
    return assessment


# make a prediction using only tabular data (microbiome and genetic)
def run_risk_assessment_tab(genus_abundance_subset: pd.DataFrame, apoe: dict) -> dict[str, float]:
    # load the correct model
    with open('risk-assess-tab.pkl', 'rb') as f:
        model = pickle.load(f)

    # make prediction
    prob = model.predict_proba(genus_abundance_subset, pd.DataFrame([apoe]))

    # get the feature contributions from each genus
    assessment = get_shap(model.microbiome_model.model, genus_abundance_subset)
    assessment['risk'] = float(prob[0])
    assessment['certainty'] = model.prediction_certainty(microbiome=genus_abundance_subset,
                                                         genetic=pd.DataFrame([apoe]))
    
    return assessment


# make a prediction using all three modalities
def run_risk_assessment_full(genus_abundance_subset: pd.DataFrame, apoe: dict, mri: np.ndarray) -> dict[str, float]:
    import torch

    # load the correct model
    with open('risk-assess-full.pkl', 'rb') as f:
        model = pickle.load(f)

    # reattach the CNN weights
    model.imaging_model.net = ImagingCNN()  # must have class defined
    model.imaging_model.net.load_state_dict(
        torch.load("imaging_cnn_weights.pt", map_location="cpu", weights_only=True)
    )
    model.imaging_model.net.eval()
    
    # make prediction
    prob = model.predict_proba(microbiome=genus_abundance_subset,
                               genetic=pd.DataFrame([apoe]),
                               imaging=mri)
    
    # get the feature contributions from each genus
    assessment = get_shap(model.microbiome_model.model, genus_abundance_subset)
    assessment['risk'] = float(prob[0])
    assessment['certainty'] = model.prediction_certainty(microbiome=genus_abundance_subset,
                                                         genetic=pd.DataFrame([apoe]),
                                                         imaging=mri)
    
    return assessment


# use xgb native shap since actual shap causes dependency issues
# returns {'high_effect': val, 'low_effect': val}
def get_shap(model, genus_subset: pd.DataFrame) -> dict[str, float]:
    
    booster = model.get_booster()
    contribs = booster.predict(
        xgb.DMatrix(genus_subset),
        pred_contribs=True
    )

    contribs = contribs[0, :-1]
    contributions = dict(zip(MODEL_GENUS, contribs))
    ranked = sorted(contributions.items(), key=lambda x: abs(x[1]), reverse=True)
    ranked_dict = {contrib[0]: float(contrib[1]) for contrib in ranked}
    
    top_8 = {}
    i = 0
    for genus, contrib in ranked_dict.items():
        if i >= 8: break
        top_8[genus] = contrib
        i +=1

    return top_8


# mri is path to the NIfTY file (.nii)
def mri_preprocess(mri: str) -> np.ndarray:
    import nibabel as nib
    from scipy.ndimage import zoom

    img = nib.load(mri)
    data = img.get_fdata()

    def resize(img, correct_shape):
        factors = [t/s for t, s in zip(correct_shape, img.shape)]
        return zoom(img, factors, order=1)
    
    correct_shape = (128, 128, 128)
    data = resize(data, correct_shape)

    def normalize(x):
        mask = x > 0
        if np.sum(mask) > 0:
            x[mask] = (x[mask] - np.mean(x[mask])) / (np.std(x[mask]) + 1e-8)
        return x

    data = normalize(data)
    X_img = data[np.newaxis, :]

    return X_img


def risk_assess(model: str, genus_abundance: dict, apoe: dict = None, nifty_path: str = None) -> dict:
    pp_abundance = preprocess_genera(genus_abundance)
    subset = get_genus_subset(pp_abundance)

    if model == 'gmb':
        return run_risk_assessment_gmb(subset)

    elif model == 'tab' and apoe:
        return run_risk_assessment_tab(subset, apoe)

    elif model == 'full' and nifty_path:
        if not Path(nifty_path).exists():
            raise FileNotFoundError(f"NIfTI file not found: {nifty_path}")
        mri = mri_preprocess(mri=nifty_path)
        return run_risk_assessment_full(subset, apoe, mri)

    else:
        raise ValueError(
            f"Cannot run model='{model}': "
            f"apoe={'provided' if apoe else 'missing'}, "
            f"nifty_path={'provided' if nifty_path else 'missing'}"
        )


def main():
    data = json.loads(sys.stdin.read())
    try:
        assessment = risk_assess(
            data['model'], data['microbiome'], data['genetic'], data['mri']
        )
        print(json.dumps(assessment))
    except Exception as exc:
        import traceback
        print(json.dumps({"error": str(exc), "traceback": traceback.format_exc()}),
              file=sys.stderr)
        sys.exit(1)


main()