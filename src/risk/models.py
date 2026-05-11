import numpy as np
import torch.nn as nn
import torch
import xgboost as xgb
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import StratifiedKFold
from sklearn.model_selection import GridSearchCV


class TabularModel:
    # base class for the 2 models that use tabular data (gmb and apoe)
    def __init__(self, name: str, use_gs: bool=True):
        self.name = name
        self.use_gridsearch = use_gs
        self.model = None
        self.base_model = xgb.XGBClassifier(
            use_label_encoder=False,
            eval_metric="logloss",
            random_state=42,
        )

    def fit(self, X, y):
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
            self.best_score_  = grid.best_score_ # mean cross-val ROC-AUC (avg over 3 val folds for best hyperparams)
            print(f"[{self.name}] Best params:", grid.best_params_)

        else:
            self.model = self.base_model
            self.model.fit(X, y)

    def predict_proba(self, X) -> np.ndarray:
        # return prob of AD
        return self.model.predict_proba(X)[:, 1]
    
    def prediction_certainty(self, X) -> dict:
        prob = float(self.model.predict_proba(X)[:, 1])
        return round(abs(prob - 0.5) * 200, 1)


class ImagingCNN(nn.Module):
    # uses MRI volumes from NIfTI format (.nii) -> dimensions are: x, y, z, t (time), ...[other dimensions we won't use]
    # in: (batch, 1, x, y, z)
    # out: risk prob per sample

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
    # wrapper for cnn

    def __init__(self, epochs=20, lr=1e-3, device="cpu"):
        self.device = device or torch.device("cpu")
        self.epochs = epochs
        self.lr = lr
        self.net = ImagingCNN().to(self.device)

    def fit(self, X: np.ndarray, y: np.ndarray):
        # X shape: (N, x, y, z)
        dataset = torch.utils.data.TensorDataset(
            torch.tensor(X[:, None], dtype=torch.float32),
            torch.tensor(y, dtype=torch.float32),
        )
        loader = torch.utils.data.DataLoader(dataset, batch_size=8, shuffle=True)
        opt = torch.optim.Adam(self.net.parameters(), lr=self.lr)
        loss_fn = nn.BCELoss()

        self.net.train()
        for epoch in range(self.epochs):
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


class ImagingCNN(nn.Module):
    # uses MRI volumes from NIfTI format (.nii) -> dimensions are: x, y, z, t (time), ...[other dimensions we won't use]
    # in: (batch, 1, x, y, z)
    # out: risk prob per sample

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
    

class AlzheimerRiskEnsemble:
    '''
    the shapes of the data
    microbiome (N, n_genera) from the genus abundance table
    genetic (N, n_alleles) APOE alleles (2, 3, and 4), ea row sum = 4
    imaging (N, x, y, z) MRI volumes (use .nii files)
    '''

    def __init__(self, device = None, use_imaging: bool = False):
        self.use_imaging = use_imaging

        self.microbiome_model = TabularModel("microbiome")
        self.genetic_model    = TabularModel("genetic")
        self.imaging_model    = ImagingModel(epochs=10, device=device) if use_imaging else None
        self.device           = device

        # use base model probabilities as features for meta learn
        self.meta_learner  = LogisticRegression(C=1.0, max_iter=1000)
        self.meta_scaler   = StandardScaler()
        self._fitted       = False

    def _base_predict(self,
                      microbiome, genetic,
                      imaging=None) -> np.ndarray:
        # stack base model outputs into meta feature matrix
        cols = [
            self.microbiome_model.predict_proba(microbiome),
            self.genetic_model.predict_proba(genetic),
        ]
        if self.use_imaging and imaging is not None:
            cols.append(self.imaging_model.predict_proba(imaging))
        return np.column_stack(cols)

    def fit(self, microbiome, genetic, y, imaging=None):
      kf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

      n = len(y)
      n_modalities = 2 + (1 if self.use_imaging else 0)

      meta_X = np.zeros((n, n_modalities))

      for train_idx, val_idx in kf.split(microbiome, y):
          mb_tr, mb_val = microbiome.iloc[train_idx], microbiome.iloc[val_idx]
          ge_tr, ge_val = genetic.iloc[train_idx], genetic.iloc[val_idx]
          y_tr, y_val   = y.iloc[train_idx], y.iloc[val_idx]

          # fresh models each fold
          mb_model = TabularModel("microbiome")
          ge_model = TabularModel("genetic")

          mb_model.fit(mb_tr, y_tr)
          ge_model.fit(ge_tr, y_tr)

          cols = [
              mb_model.predict_proba(mb_val),
              ge_model.predict_proba(ge_val),
          ]

          if self.use_imaging and imaging is not None:
              img_tr, img_val = imaging[train_idx], imaging[val_idx]
              img_model = ImagingModel(device=self.device)
              img_model.fit(img_tr, y_tr)
              cols.append(img_model.predict_proba(img_val))

          meta_X[val_idx] = np.column_stack(cols)

      # train meta learner on full OOF predictions
      self.meta_scaler.fit(meta_X)
      meta_X_scaled = self.meta_scaler.transform(meta_X)
      self.meta_learner.fit(meta_X_scaled, y)

      # finally train base models on FULL data (for inference)
      self.microbiome_model.fit(microbiome, y)
      self.genetic_model.fit(genetic, y)

      if self.use_imaging and imaging is not None:
          self.imaging_model.fit(imaging, y)

      self._fitted = True

    def predict_proba(self, microbiome, genetic,
                      imaging=None) -> np.ndarray:
        assert self._fitted, "Call fit() before predict_proba()"
        meta_X = self._base_predict(microbiome, genetic, imaging)
        meta_X = self.meta_scaler.transform(meta_X)
        return self.meta_learner.predict_proba(meta_X)[:, 1]

    def prediction_certainty(self, microbiome, genetic,
                     imaging=None) -> dict:
        prob = float(self.predict_proba(microbiome, genetic, imaging)[0])
        return round(abs(prob - 0.5) * 200, 1)