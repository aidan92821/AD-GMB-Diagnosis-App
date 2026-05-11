"""
Axis – MainWindow.

Start-up flow:
  1. App shows AuthPage (login / register)
  2. On login_success → main content revealed, user stored in self._current_user
  3. NCBI fetch → _FetchWorker → builds AppState; project saved to DB under user
  4. _DownloadWorker runs fasterq-dump to download FASTQ → data/<proj>/fastq/<layout>/
     (skipped gracefully if fasterq-dump is not installed)
  5. _AnalysisWorker fills diversity, taxonomy, risk data
  6. All pages updated via page.load(state)
"""

from __future__ import annotations
import os

from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QFrame, QLabel, QHBoxLayout, QVBoxLayout,
    QStackedWidget, QScrollArea, QPushButton, QSizePolicy,
)
from PyQt6.QtCore import Qt, QThread, QObject, pyqtSignal

import numpy as np

from src.services.assessment_service import ServiceError

from resources.styles import (
    APP_QSS, SB_BG, SB_SECTION, WHITE, BG_PAGE, BG_CARD, BORDER, TEXT_H, TEXT_M,
    ACCENT,
)
from models.app_state import AppState, RunState
from ui.pages import (
    OverviewPage, UploadRunsPage, DiversityPage,
    TaxonomyPage, AsvTablePage, PhylogenyPage, AlzheimerPage, SimulationPage,
)
from ui.export_page import ExportPage
from ui.auth_page import AuthPage
from ui.profile_page import ProfilePage

from src.pipeline.qiime2_runner import QiimeRunner
from src.pipeline.qiime_preproc import download_classifier, qiime_preprocess, infer_phylogeny
from src.pipeline.fetch_data import (fetch_runs, download_runs, 
                                     write_manifest, cleanup)
from src.pipeline.db_import import (parse_feat_tax_seqs, parse_feature_counts,
                                    parse_genus_table)

from src.risk.run_assess import run_assess

from src.simulation.simulate_gmb import simulate, plot_sim_results, get_abundance_shift_stats

from src.services.assessment_service import (save_ncbi_project, get_genus_dict, 
                                             create_run,ingest_run_data, 
                                             get_run_id_by_srr, get_feature_counts,
                                             get_tree, store_alpha_diversities,
                                             store_beta_diversity, ServiceError,
                                             get_beta_diversity_matrix, store_pcoa,
                                             create_tree_instance, get_run_feature_ids,
                                             create_simulation, ingest_simulation_genus)

# ── Sidebar nav ───────────────────────────────────────────────────────────────

NAV = [
    ("ANALYSIS", [
        ("Overview",       "⊞"),
        ("Upload Runs",    "↑"),
        ("Diversity",      "≋"),
        ("Taxonomy",       "⊙"),
        ("ASV Table",      "⋮"),
        ("Phylogeny",      "∿"),
    ]),
    ("INSIGHTS", [
        ("Alzheimer Risk", "♥"),
        ("Simulation",     "⚗"),
    ]),
    ("EXPORT", [
        ("Export PDF",     "⬇"),
    ]),
    ("ACCOUNT", [
        ("Profile",        "◉"),
    ]),
]


class _FetchWorkerReal(QObject):
    finished = pyqtSignal(object, object, object)   # emits list of single runs, list of paired runs, and project dictionary
    errored  = pyqtSignal(str)
    progress = pyqtSignal(str)
    canceled = pyqtSignal()

    def __init__(self, bioproject: str, email: str, runner: QiimeRunner, srr: str=None, n_runs=1) -> None:
        super().__init__()
        self._bioproject = bioproject
        self._email = email
        self._srr = srr
        self._n_runs = n_runs
        self._runner = runner
    
    def run(self):

        def cb(line: str):
            if line:
                self.progress.emit(line)

        try:
            self.progress.emit("[fetch] Fetching runs...")
            single_runs, paired_runs, project = fetch_runs(email=self._email, runner=self._runner, 
                                                           bioproject=self._bioproject, srr=self._srr, 
                                                           n_runs=self._n_runs, callback=cb)
            # unsupported sequencing platform
            if not (single_runs or paired_runs) or not project:
                # cancel the fetch + download sequence
                self.canceled.emit()
            else:
                self.finished.emit(single_runs, paired_runs, project)
        except Exception as exc:
            self.errored.emit(str(exc))


class _DownloadWorkerReal(QObject):
    finished = pyqtSignal(object)   # emits updated AppState
    errored  = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, state: AppState, runner: QiimeRunner) -> None:
        super().__init__()
        self._state = state
        self._runner = runner
    
    def run(self):
        try:
            from pathlib import Path as _Path
            APP_DIR = _Path(__file__).parent.parent / "pipeline"
            total = len(self._state.single_runs) + len(self._state.paired_runs)
            ok, skipped, failed_srrs = 0, 0, []

            if self._state.single_runs:
                fastq_dir = APP_DIR / f"data/{self._state.bioproject_id}/fastq/single"
                for srr in self._state.single_runs:
                    if (fastq_dir / f"{srr}.fastq").exists():
                        self.progress.emit(f"✓ {srr} — already on disk, skipping")
                        skipped += 1
                    else:
                        self.progress.emit(f"Downloading {srr} (single-end)… [{ok+skipped+1}/{total}]")
                download_runs(runner=self._runner, bioproject=self._state.bioproject_id,
                              lib_layout='single', runs=self._state.single_runs, state=self._state)
                write_manifest(self._state.bioproject_id, lib_layout='single', state=self._state)
                for srr in self._state.single_runs:
                    if self._state.runs.get(srr, {}).get('uploaded'):
                        ok += 1
                    elif not (fastq_dir / f"{srr}.fastq").exists():
                        failed_srrs.append(srr)

            if self._state.paired_runs:
                fastq_dir = APP_DIR / f"data/{self._state.bioproject_id}/fastq/paired"
                for srr in self._state.paired_runs:
                    if (fastq_dir / f"{srr}_1.fastq").exists():
                        self.progress.emit(f"✓ {srr} — already on disk, skipping")
                        skipped += 1
                    else:
                        self.progress.emit(f"Downloading {srr} (paired-end)… [{ok+skipped+1}/{total}]")
                download_runs(runner=self._runner, bioproject=self._state.bioproject_id,
                              lib_layout='paired', runs=self._state.paired_runs, state=self._state)
                write_manifest(self._state.bioproject_id, lib_layout='paired', state=self._state)
                for srr in self._state.paired_runs:
                    if self._state.runs.get(srr, {}).get('uploaded'):
                        ok += 1
                    elif not (fastq_dir / f"{srr}_1.fastq").exists():
                        failed_srrs.append(srr)

            # Emit a summary for the topbar badge only (not status panel)
            ready = ok + skipped
            if failed_srrs:
                self.progress.emit(f"⚠  {ready} of {total} run(s) ready — {len(failed_srrs)} could not be downloaded")
            else:
                self.progress.emit(f"✓ All {ready} run(s) downloaded and ready")

            self.finished.emit(self._state)
        except Exception as exc:
            self.errored.emit(str(exc))
            print(exc)


class _CheckEnvWorker(QObject):
    '''
    this worker checks to make sure the qiime env is up and running
    '''
    finished = pyqtSignal(bool, object, object)   # emits if the env available and the subprocess result
    errored  = pyqtSignal(str)

    def __init__(self, runner: QiimeRunner) -> None:
        super().__init__()
        self._runner = runner

    def run(self):

        import subprocess as _sp
        proc = None
        try:
            proc = _sp.Popen(
                [str(self._runner.base_cmd[0]), "run", "-p",
                str(self._runner.base_cmd[3]), "qiime", "--version"],
                stdout=_sp.PIPE,
                stderr=_sp.PIPE,
                text=True
            )
            stdout, stderr = proc.communicate(timeout=20)
            qiime2_available = (proc.returncode == 0)
            self.finished.emit(qiime2_available, stdout, stderr)
        except _sp.TimeoutExpired as e:
            proc.kill()
            self.errored.emit(str(e))
        except Exception as exc:
            self.errored.emit(str(exc))


class _PipelineWorkerReal(QObject):
    '''
    this worker will run the full qiime2 preprocessing and create the tables ready for parsing
    '''
    finished = pyqtSignal(object)   # emits updated AppState
    errored  = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, runner: QiimeRunner, bioproject: str, state: AppState) -> None:
        super().__init__()
        self._state = state
        self._bioproject = bioproject
        self._runner = runner
        self.APP_DIR = Path(__file__).parent.parent
        self.QIIME_DIR = self.APP_DIR / f"pipeline/data/{self._bioproject}/qiime/"
        CLF_DIR = self.APP_DIR / f"pipeline/taxa_classifier"
        CLASSIFIER = 'silva-138-99-nb-classifier.qza'
        SOURCE = 'https://data.qiime2.org/classifiers/sklearn-1.4.2/silva'
        
        # get the classifier for annotating taxa
        if CLASSIFIER not in os.listdir(str(CLF_DIR)):
            download_classifier(classifier_url=f"{SOURCE}/{CLASSIFIER}")
    
    def run(self):
        import re as _re

        def _format(line: str) -> str | None:
            s = line.strip()
            if not s:
                return None
            # Warnings
            if '** WARNING:' in s:
                warning_text = s.replace('** WARNING:', '').strip()
                return f'⚠️  {warning_text}'
            # Phase headers: [single] Importing samples…
            if s.startswith('['):
                return s
            # "Saved FeatureTable[Frequency] to: /long/path/table.qza"
            if s.startswith('Saved '):
                artifact = s.split(' to:')[0]          # "Saved FeatureTable[Frequency]"
                return f'✓  {artifact}'
            # "Imported /path/manifest.tsv as SingleEndFastqManifestPhred33V2 to /path"
            if s.startswith('Imported '):
                m = _re.search(r'\bas\s+(\S+)', s)
                return f'✓  Imported as {m.group(1)}' if m else '✓  Imported'
            # "Exported /path/rep-seqs.qza as DNASequencesDirectoryFormat to directory /path"
            if s.startswith('Exported '):
                m = _re.search(r'\bas\s+(\S+)', s)
                return f'✓  Exported as {m.group(1)}' if m else '✓  Exported'
            if s.startswith('Getting '):
                return s
            # Errors
            if 'error' in s.lower():
                return f'✗  {s}'
            return None

        def cb(line: str):
            msg = _format(line)
            if msg:
                self.progress.emit(msg)

        try:
            # preprocess the paired end fastq files
            if self._state.paired_runs:
                qiime_preprocess(runner=self._runner, bioproject=self._bioproject,
                                    lib_layout='paired', callback=cb)

            # preprocess the single end fastq files
            if self._state.single_runs:
                qiime_preprocess(runner=self._runner, bioproject=self._bioproject,
                                    lib_layout='single', callback=cb)

            # Infer phylogenetic tree (one per project — prefer single layout)
            self.progress.emit("[phylogeny] Building phylogenetic tree…")
            nwk = ""
            if self._state.single_runs:
                nwk = infer_phylogeny(runner=self._runner, bioproject=self._bioproject,
                                      lib_layout='single', callback=cb)
            elif self._state.paired_runs:
                nwk = infer_phylogeny(runner=self._runner, bioproject=self._bioproject,
                                      lib_layout='paired', callback=cb)
            self._state._nwk_string = nwk

            self.finished.emit(self._state)
        except Exception as exc:
            self.errored.emit(str(exc))


class _ParseWorkerReal(QObject):

    finished = pyqtSignal(object) # emits updated AppState
    errored  = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, bioproject: str, state: AppState, user):
        super().__init__()
        self._data_dir = str((Path(__file__).parent.parent / f"pipeline/data/{bioproject}").resolve())
        self._state = state
        self._user = user

    def run(self):
        try:
            all_feature_seqs: list = []
            all_genera: set = set()

            # parse the paired end tables
            if self._state.paired_runs:
                abundances     = parse_genus_table(genus=f"{self._data_dir}/qiime/paired/genus-table.tsv")
                feature_seqs   = parse_feat_tax_seqs(tax=f"{self._data_dir}/qiime/paired/taxonomy.tsv",
                                                   seqs=f"{self._data_dir}/reps-tree/paired/dna-sequences.fasta")
                feature_counts = parse_feature_counts(feat=f"{self._data_dir}/qiime/paired/feature-table.tsv")
                all_feature_seqs.extend(feature_seqs)
                for row in abundances.values():
                    all_genera.update(g for g, _ in row)

                for run, row in abundances.items():
                    try:
                        run_id = get_run_id_by_srr(run)
                        label = self._state.runs[run]['label']
                        self._state.lbs[label] = run_id
                    except ServiceError:
                        db_run = create_run(project_id=self._state.db_project_id, source='ncbi', srr_accession=run,
                                            bio_proj_accession=self._state.bioproject_id, library_layout='paired')
                        run_id = db_run['run_id']
                        label = self._state.runs[run]['label']
                        self._state.lbs[label] = run_id
                    ingest_run_data(run_id=run_id, genus_rows=row, features=feature_seqs,
                                    feature_counts=feature_counts.get(run, {}))

            # parse the single end tables
            if self._state.single_runs:
                abundances     = parse_genus_table(genus=f"{self._data_dir}/qiime/single/genus-table.tsv")
                feature_seqs   = parse_feat_tax_seqs(tax=f"{self._data_dir}/qiime/single/taxonomy.tsv",
                                                   seqs=f"{self._data_dir}/reps-tree/single/dna-sequences.fasta")
                feature_counts = parse_feature_counts(feat=f"{self._data_dir}/qiime/single/feature-table.tsv")
                all_feature_seqs.extend(feature_seqs)
                for row in abundances.values():
                    all_genera.update(g for g, _ in row)

                for run, row in abundances.items():
                    try:
                        run_id = get_run_id_by_srr(run)
                        label = self._state.runs[run]['label']
                        self._state.lbs[label] = run_id
                    except ServiceError:
                        db_run = create_run(project_id=self._state.db_project_id, source='ncbi', srr_accession=run,
                                            bio_proj_accession=self._state.bioproject_id, library_layout='single')
                        run_id = db_run['run_id']
                        label = self._state.runs[run]['label']
                        self._state.lbs[label] = run_id
                    ingest_run_data(run_id=run_id, genus_rows=row, features=feature_seqs,
                                    feature_counts=feature_counts.get(run, {}))

            self._state.asv_count   = len(all_feature_seqs)
            self._state.genus_count = len(all_genera)
            
            # Save Newick string to DB before cleanup removes intermediate files
            nwk = getattr(self._state, '_nwk_string', '') or ''
            if not nwk:
                # fallback: read from disk if pipeline was re-run without phylogeny step
                for layout in ('single', 'paired'):
                    nwk_path = Path(self._data_dir) / f"reps-tree/{layout}/tree.nwk"
                    if nwk_path.exists():
                        nwk = nwk_path.read_text().strip()
                        break
            if nwk and self._state.db_project_id:
                try:
                    tree_info = create_tree_instance(
                        project_id=self._state.db_project_id, newick_string=nwk
                    )
                    if tree_info:
                        self._state.tree_id = tree_info.get('tree_id')
                except Exception:
                    pass

            # remove all the intermediate files
            cleanup(self._state.bioproject_id)

            self.finished.emit(self._state)
        except Exception as exc:
            self.errored.emit(str(exc))


class _AnalysisWorkerReal(QObject):

    finished = pyqtSignal(object)   # emits updated AppState
    errored  = pyqtSignal(str)
    progress = pyqtSignal(str)      # status message

    def __init__(self, state: AppState) -> None:
        super().__init__()
        self._state = state

    def run(self):
        try:
            self.progress.emit("Computing alpha diversity")
            self._fill_alpha(self._state.lbs)

            if self._state.run_count > 1:    
                self.progress.emit("Computing Bray-Curtis beta diversity")
                self._fill_bray_curtis(self._state, self._state.lbs)
                
                self.progress.emit("Computing PCoA…")
                self._fill_pcoa(self._state, self._state.lbs, "bray_curtis")
            
            self.finished.emit(self._state)
        except Exception as exc:
            self.errored.emit(str(exc))

    @staticmethod
    def _shannon(counts: np.ndarray) -> float:
        total = counts.sum()
        if total == 0:
            return 0.0
        p = counts[counts > 0] / total
        return float(-np.sum(p * np.log2(p)))

    @staticmethod
    def _simpson(counts: np.ndarray) -> float:
        total = counts.sum()
        if total == 0:
            return 0.0
        p = counts / total
        return float(1.0 - np.sum(p ** 2))

    @staticmethod
    def _fill_alpha(labels: dict) -> None:
        for run_id in labels.values():
            try:
                rows = get_feature_counts(run_id)
            except ServiceError:
                continue

            if not rows:
                continue

            counts = np.array([r["abundance"] for r in rows], dtype=int)

            sh = _AnalysisWorkerReal._shannon(counts)
            si = _AnalysisWorkerReal._simpson(counts)

            try:
                store_alpha_diversities(run_id, {"shannon": sh, "simpson": si})
            except ServiceError:
                continue

    @staticmethod
    def _fill_bray_curtis(state: AppState, labels: dict) -> None:
        # Bray-Curtis: BC(u,v) = sum|u-v| / sum(u+v); 0/0 → 0
        def _braycurtis(mat: np.ndarray) -> np.ndarray:
            n = mat.shape[0]
            bc = np.zeros((n, n))
            for _i in range(n):
                for _j in range(_i + 1, n):
                    num = np.abs(mat[_i] - mat[_j]).sum()
                    den = (mat[_i] + mat[_j]).sum()
                    v   = num / den if den > 0 else 0.0
                    bc[_i, _j] = bc[_j, _i] = v
            return bc

        run_ids = list(labels.values())
        run_labels = list(labels.keys())

        # ASV counts of all feature ids per run
        counts_per_run: dict[int, dict[str, int]] = {}

        try:
            first_run_id = list(labels.values())[0]
            feature_ids = get_run_feature_ids(first_run_id)
        except (ServiceError, IndexError, Exception):
            return

        if not feature_ids:
            return

        for run_id in run_ids:
            try:
                rows = get_feature_counts(run_id)
                counts_per_run[run_id] = {r['feature_id']: int(r['abundance']) for r in rows}
            except ServiceError:
                counts_per_run[run_id] = {}

        # rows = samples (runs), columns = OTUs (features)
        # missing features for a run get count 0
        count_matrix = np.array(
            [
                [counts_per_run[run_id].get(fid, 0) for fid in feature_ids]
                for run_id in run_ids
            ],
            dtype=float,
        )

        bc_matrix = _braycurtis(count_matrix)

        for i, label_a in enumerate(run_labels):
            for j, label_b in enumerate(run_labels):
                if j <= i:
                    continue
                value = float(bc_matrix[i, j])
                id_a  = labels[label_a]
                id_b  = labels[label_b]
                id_lo, id_hi = sorted([id_a, id_b])
                try:
                    store_beta_diversity(id_lo, id_hi, "bray_curtis", value)
                except ServiceError:
                    continue
        
        state.count_matrix = count_matrix # will be used later for unifrac

    @staticmethod
    def _build_dissimilarity_matrix(
        labels: list[str],
        flat: list[dict],
        run_id_map: dict[str, int],
    ) -> np.ndarray:
        """
        Reconstruct a symmetric nxn dissimilarity matrix from the flat
        upper-triangle rows returned by get_beta_diversity_matrix().
    
        flat rows: {"run_id_1": int, "run_id_2": int, "metric": str, "value": float}
        Diagonal is 0.0 (a sample is identical to itself).
        """
        n         = len(labels)
        mat       = np.zeros((n, n), dtype=float)
        id_to_idx = {
            run_id_map[lbl]: i
            for i, lbl in enumerate(labels)
            if lbl in run_id_map
        }
        for row in flat:
            i = id_to_idx.get(row["run_id_1"])
            j = id_to_idx.get(row["run_id_2"])
            if i is not None and j is not None:
                val       = float(row["value"])
                mat[i, j] = val
                mat[j, i] = val
        return mat
    
    @staticmethod
    def _pcoa_from_matrix(
        labels: list[str],
        matrix: np.ndarray,
    ) -> dict[str, tuple[float, float]]:
        """
        Classical MDS via numpy.linalg.eigh on a symmetric dissimilarity matrix.
        Returns {label: (pc1, pc2)}.
    
        eigh solves the full eigenproblem exactly for symmetric matrices and
        returns eigenvalues in ascending order — we reverse to get descending.
        Negative eigenvalues (numerical artefacts from non-Euclidean distances)
        are clamped to zero before taking the square root.
        """
        from numpy.linalg import eigh

        n = len(labels)
        if n < 2:
            return {lbl: (0.0, 0.0) for lbl in labels}
    
        # Double-centre: B = -0.5 * H D² H,  H = I - (1/n) 11ᵀ
        d2  = matrix ** 2
        H   = np.eye(n) - np.ones((n, n)) / n
        B   = -0.5 * H @ d2 @ H
    
        eigenvalues, eigenvectors = eigh(B)
        eigenvalues  = eigenvalues[::-1]      # descending
        eigenvectors = eigenvectors[:, ::-1]
    
        pc1 = eigenvectors[:, 0] * np.sqrt(max(eigenvalues[0], 0.0))
        pc2 = eigenvectors[:, 1] * np.sqrt(max(eigenvalues[1], 0.0))
    
        return {
            labels[i]: (round(float(pc1[i]), 4), round(float(pc2[i]), 4))
            for i in range(n)
        }
    
    @staticmethod
    def _fill_pcoa(state: AppState, labels: dict[str, int], metric: str) -> None:
        """
        Derive and store PCoA coordinates from the already-computed beta matrix.
        """
        try:
            flat = get_beta_diversity_matrix(state.db_project_id, metric)
        except ServiceError:
            return

        if flat:
            run_labels = state.run_labels
            matrix     = _AnalysisWorkerReal._build_dissimilarity_matrix(run_labels, flat, labels)
            coords     = _AnalysisWorkerReal._pcoa_from_matrix(run_labels, matrix)

            for label, (pc1, pc2) in coords.items():
                run_id = labels[label]
                try:
                    store_pcoa(run_id, metric, pc1, pc2)
                except ServiceError:
                    continue


class _PhylogenyWorker(QObject):
    '''
    this worker will run the full qiime2 preprocessing and create the tables ready for parsing
    '''
    finished = pyqtSignal(object)   # emits updated AppState
    errored  = pyqtSignal(str)

    def __init__(self, runner: QiimeRunner, state: AppState) -> None:
        super().__init__()
        self._runner = runner
        self._state = state
        self._bioproject = self._state.bioproject_id

    def run(self):
        try:
            # first check to make sure it doesn't exist yet
            try:
                tree_info = get_tree(self._state.db_project_id)
                self._state.tree_id = tree_info['tree_id']
                self.finished.emit(self._state)
            except ServiceError:
                # only need to get one tree per bioproject
                nwk = ""    
                if self._state.single_runs:
                    nwk = infer_phylogeny(runner=self._runner, bioproject=self._bioproject, lib_layout='single', callback=print)
                elif self._state.paired_runs:
                    nwk = infer_phylogeny(runner=self._runner, bioproject=self._bioproject, lib_layout='paired', callback=print)
                # store newick string in db
                tree_info = create_tree_instance(project_id=self._state.db_project_id, newick_string=nwk)
                self._state.tree_id = tree_info['tree_id']
                self.finished.emit(self._state)
        except Exception as exc:
            self.errored.emit(str(exc))


class _UnifracWorker(QObject):
    """
    Computes weighted UniFrac distances + PCoA using the project tree.
    Pure-Python implementation — no skbio dependency.
    """
    finished = pyqtSignal(object)   # emits updated AppState
    errored  = pyqtSignal(str)

    def __init__(self, state: AppState) -> None:
        super().__init__()
        self._state    = state
        self._project_id = self._state.db_project_id

    def run(self):
        try:
            if self._state.run_count > 1:
                self._fill_unifrac(
                    state=self._state,
                    project_id=self._project_id,
                    labels=self._state.lbs,
                )
            self.finished.emit(self._state)
        except Exception as exc:
            self.errored.emit(str(exc))

    @staticmethod
    def _fill_unifrac(state: AppState, project_id: int, labels: dict) -> None:
        """
        Weighted UniFrac using _TreeNode (no skbio).

        Algorithm:
          1. Load Newick from DB; prune to sample tips.
          2. Iterative postorder: accumulate per-sample subtree proportions.
          3. WUniFrac(A,B) = Σ(l·|pA−pB|) / Σ(l·(pA+pB))  over all branches.
          4. Store pairwise distances and derive PCoA coordinates.
        """
        import io as _io
        from ui.pages import _TreeNode

        # ── Load tree ─────────────────────────────────────────────────────
        try:
            tree_info = get_tree(project_id=project_id)
        except ServiceError:
            print("UniFrac: no tree in DB — skipping")
            return
        nwk = tree_info.get("newick_string", "")
        if not nwk:
            print("UniFrac: empty newick string — skipping")
            return

        # ── Feature counts per run ────────────────────────────────────────
        run_ids = list(labels.values())
        try:
            feature_ids = get_run_feature_ids(run_ids[0])
        except Exception:
            return
        if not feature_ids:
            return

        counts_per_run: dict[int, dict[str, int]] = {}
        for run_id in run_ids:
            try:
                rows = get_feature_counts(run_id)
                counts_per_run[run_id] = {
                    r["feature_id"]: int(r["abundance"]) for r in rows
                }
            except ServiceError:
                counts_per_run[run_id] = {}

        # Tips present in any sample with count > 0
        all_sample_tips: set[str] = set()
        for cnt in counts_per_run.values():
            all_sample_tips.update(k for k, v in cnt.items() if v > 0)
        if not all_sample_tips:
            return

        # ── Parse & prune tree to sample tips ─────────────────────────────
        try:
            tree = _TreeNode.read(_io.StringIO(nwk))
            tree.shear(all_sample_tips)
        except Exception as exc:
            print(f"UniFrac: tree parse/prune error: {exc}")
            return

        # Build postorder list once; reused for every pair
        postorder_nodes = list(tree.postorder())

        def _wunifrac(counts_a: dict, counts_b: dict) -> float:
            total_a = sum(counts_a.values())
            total_b = sum(counts_b.values())
            if total_a == 0 and total_b == 0:
                return 0.0
            prop_a = ({k: v / total_a for k, v in counts_a.items()}
                      if total_a else {})
            prop_b = ({k: v / total_b for k, v in counts_b.items()}
                      if total_b else {})

            # Iterative postorder: accumulate subtree proportion sums
            sub_a: dict[int, float] = {}
            sub_b: dict[int, float] = {}
            for node in postorder_nodes:
                nid = id(node)
                if not node.children:          # leaf
                    sub_a[nid] = prop_a.get(node.name or "", 0.0)
                    sub_b[nid] = prop_b.get(node.name or "", 0.0)
                else:
                    sub_a[nid] = sum(sub_a[id(c)] for c in node.children)
                    sub_b[nid] = sum(sub_b[id(c)] for c in node.children)

            numerator = denominator = 0.0
            for node in postorder_nodes:
                if node.parent is None:        # root — no branch above
                    continue
                bl = node.length or 0.0
                if bl == 0.0:
                    continue
                nid = id(node)
                sa, sb = sub_a[nid], sub_b[nid]
                numerator   += bl * abs(sa - sb)
                denominator += bl * (sa + sb)

            return numerator / denominator if denominator > 0 else 0.0

        # ── Pairwise weighted UniFrac ──────────────────────────────────────
        run_labels = list(labels.keys())
        for i, label_a in enumerate(run_labels):
            for j, label_b in enumerate(run_labels):
                if j <= i:
                    continue
                id_a = labels[label_a]
                id_b = labels[label_b]
                u_val = _wunifrac(
                    counts_per_run.get(id_a, {}),
                    counts_per_run.get(id_b, {}),
                )
                id_lo, id_hi = sorted([id_a, id_b])
                try:
                    store_beta_diversity(id_lo, id_hi, "unifrac", u_val)
                except ServiceError:
                    continue

        # ── UniFrac PCoA ──────────────────────────────────────────────────
        _AnalysisWorkerReal._fill_pcoa(
            state=state, labels=labels, metric="unifrac"
        )
    

class _RiskPredictionWorker(QObject):
    finished = pyqtSignal(object)
    errored  = pyqtSignal(str)

    def __init__(self, state: AppState, apoe: dict=None, mri: str=None, run_lbl: str='R1') -> None:
        super().__init__()
        self._state = state
        self._apoe = apoe
        self._mri = mri
        self._run_lbl = run_lbl

    def run(self):
        try:
            abundance = get_genus_dict(self._state.lbs[self._run_lbl])
            if self._apoe and self._mri:
                if all(v == 0 for v in self._apoe.values()):
                    assessment = run_assess(model='gmb', genus_abundance=abundance, apoe=self._apoe, nifty_path=self._mri)
                else:
                    assessment = run_assess(model='full', genus_abundance=abundance, apoe=self._apoe, nifty_path=self._mri)
            elif self._apoe:
                if all(v == 0 for v in self._apoe.values()):
                    assessment = run_assess(model='gmb', genus_abundance=abundance, apoe=self._apoe, nifty_path=self._mri)
                else:
                    assessment = run_assess(model='tab', genus_abundance=abundance, apoe=self._apoe, nifty_path=self._mri)
            else:
                assessment = run_assess(model='gmb', genus_abundance=abundance, apoe=self._apoe, nifty_path=self._mri)
            if 'stderr' in assessment:
                self.errored.emit(assessment['stderr'])
            else:
                self._state.risk_result = assessment.pop('risk', None)
                self._state.risk_certainty = assessment.pop('certainty', None)
                self._state.contributions = assessment
                self.finished.emit(self._state)
        except Exception as exc:
            self.errored.emit(str(exc))


class _SimulationWorker(QObject):
    finished = pyqtSignal(object)
    errored  = pyqtSignal(str)

    def __init__(self, state: AppState, user_diet: dict, runner: QiimeRunner, run_label: str='R1') -> None:
        super().__init__()
        self._state = state
        self._run_id = state.lbs[run_label]
        self._user_diet = user_diet
        self._runner = runner
        self._run_label = run_label

    def run(self):
        try:
            abundance = get_genus_dict(self._run_id)
            results = simulate(run_id=self._run_id,
                               abundance=abundance,
                               user_diet=self._user_diet,
                               runner=self._runner)
            # save results to the AppState for pages to get
            plots = plot_sim_results(results, abundance)
            stats = get_abundance_shift_stats(abundance_old=abundance, abundance_new=results["new_abundance"])
            self._state.simu_plots[self._run_label] = plots
            self._state.simu_stats[self._run_label] = stats

            # save results to the database
            sim_id = create_simulation(self._run_id)['simulation_id']
            ingest_simulation_genus(run_id=self._run_id, simulation_id=sim_id, genus_rows=results["new_abundance"])
            self.finished.emit(self._state)
        except Exception as exc:
            self.errored.emit(str(exc))



# ── Main window ───────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Axis — Microbiome Analytics")
        self.resize(1280, 880)
        self.setMinimumSize(900, 600)
        self.setStyleSheet(APP_QSS)

        self._nav_buttons: list[QPushButton] = []
        self._active_idx  = 0
        self._state       = AppState()
        self._current_user: dict | None = None
        self._runner = QiimeRunner()
        self._downloaded = False

        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        """
        Top-level layout:
          index 0 → AuthPage  (login / register, no sidebar)
          index 1 → main app  (sidebar + topbar + content)
        """
        self._top_stack = QStackedWidget()
        self.setCentralWidget(self._top_stack)

        # Auth screen
        self._auth_page = AuthPage()
        self._auth_page.login_success.connect(self._on_login_success)
        self._top_stack.addWidget(self._auth_page)

        # Main app (built once, hidden until login)
        self._top_stack.addWidget(self._build_main_content())

        # Start on auth screen
        self._top_stack.setCurrentIndex(0)

    def _build_main_content(self) -> QWidget:
        root = QWidget()
        root.setStyleSheet(f"background: {BG_PAGE};")

        row = QHBoxLayout(root)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(self._build_sidebar())

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        right.addWidget(self._build_topbar())
        right.addWidget(self._build_content_area(), 1)
        row.addLayout(right, 1)

        return root

    def _build_sidebar(self) -> QFrame:
        sb = QFrame(); sb.setObjectName("sidebar"); sb.setFixedWidth(180)
        lay = QVBoxLayout(sb); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)

        logo_block = QWidget(); logo_block.setStyleSheet(f"background:{SB_BG};")
        lb = QVBoxLayout(logo_block); lb.setContentsMargins(20, 20, 20, 14); lb.setSpacing(2)
        lb.addWidget(_sb_label("Axis", "sb_logo"))
        lb.addWidget(_sb_label("microbiome analytics", "sb_sub"))
        lay.addWidget(logo_block)

        sep = QFrame(); sep.setStyleSheet("background:#2D3748; max-height:1px;")
        sep.setFixedHeight(1); lay.addWidget(sep)

        nav_w = QWidget(); nav_w.setStyleSheet(f"background:{SB_BG};")
        nav_l = QVBoxLayout(nav_w); nav_l.setContentsMargins(0, 8, 0, 0); nav_l.setSpacing(0)

        for section_name, items in NAV:
            sec = QLabel(section_name); sec.setObjectName("sb_section")
            nav_l.addWidget(sec)
            for display, icon in items:
                btn = QPushButton(f"  {icon}   {display}")
                btn.setObjectName("nav_btn")
                btn.setProperty("active", len(self._nav_buttons) == 0)
                idx = len(self._nav_buttons)
                btn.clicked.connect(lambda _, i=idx: self._switch_page(i))
                btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                btn.setFixedHeight(38)
                nav_l.addWidget(btn)
                self._nav_buttons.append(btn)

        nav_l.addStretch()
        lay.addWidget(nav_w, 1)

        footer = QLabel("QIIME2 pipeline · v2024.5")
        footer.setObjectName("sb_footer")
        footer.setStyleSheet(f"background:{SB_BG}; color:{SB_SECTION}; font-size:10px; padding:10px 20px;")
        lay.addWidget(footer)
        return sb

    def _build_topbar(self) -> QFrame:
        bar = QFrame(); bar.setObjectName("topbar"); bar.setFixedHeight(52)
        lay = QHBoxLayout(bar); lay.setContentsMargins(24, 0, 24, 0); lay.setSpacing(10)

        self._topbar_title = QLabel("Axis — Microbiome Analytics")
        self._topbar_title.setObjectName("topbar_title")
        lay.addWidget(self._topbar_title)
        lay.addStretch()

        self._status_badge = QLabel("No project loaded")
        self._status_badge.setObjectName("badge_yellow")
        lay.addWidget(self._status_badge)

        self._runs_badge = QLabel("")
        self._runs_badge.setObjectName("badge_green")
        self._runs_badge.hide()
        lay.addWidget(self._runs_badge)

        self._analysis_badge = QLabel("")
        self._analysis_badge.setObjectName("badge_green")
        self._analysis_badge.hide()
        lay.addWidget(self._analysis_badge)

        self._cancel_btn = QPushButton("✕  Cancel")
        self._cancel_btn.setFixedHeight(28)
        self._cancel_btn.setStyleSheet(
            "QPushButton { background:#FEE2E2; color:#991B1B; border:1px solid #FECACA;"
            "border-radius:6px; font-size:12px; font-weight:600; padding:0 12px; }"
            "QPushButton:hover { background:#FECACA; }"
        )
        self._cancel_btn.clicked.connect(self._on_cancel)
        self._cancel_btn.hide()
        lay.addWidget(self._cancel_btn)

        # Divider
        div = QFrame(); div.setObjectName("vdivider")
        div.setFixedWidth(1); div.setFixedHeight(24)
        lay.addWidget(div)

        # Signed-in user display
        self._user_lbl = QLabel("")
        self._user_lbl.setStyleSheet(
            f"font-size: 12px; font-weight: 600; color: {TEXT_H}; background: transparent;"
        )
        self._user_lbl.hide()
        lay.addWidget(self._user_lbl)

        self._signout_btn = QPushButton("Sign Out")
        self._signout_btn.setObjectName("btn_outline")
        self._signout_btn.setFixedHeight(28)
        self._signout_btn.clicked.connect(self._on_logout)
        self._signout_btn.hide()
        lay.addWidget(self._signout_btn)

        return bar

    def _build_content_area(self) -> QScrollArea:
        scroll = QScrollArea(); scroll.setObjectName("content_scroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        host = QWidget(); host.setObjectName("content_host")
        host.setStyleSheet(f"background:{BG_PAGE};")
        host_lay = QVBoxLayout(host); host_lay.setContentsMargins(0, 0, 0, 0)

        self._stack = QStackedWidget()
        self._stack.setStyleSheet(f"background:{BG_PAGE};")

        self._overview_page    = OverviewPage()
        self._upload_page      = UploadRunsPage()
        self._diversity_page   = DiversityPage()
        self._taxonomy_page    = TaxonomyPage()
        self._asv_page         = AsvTablePage()
        self._phylo_page       = PhylogenyPage()
        self._alzheimer_page   = AlzheimerPage()
        self._simulation_page  = SimulationPage()
        self._export_page      = ExportPage()
        self._profile_page     = ProfilePage()

        for page in [
            self._overview_page, self._upload_page,
            self._diversity_page, self._taxonomy_page,
            self._asv_page, self._phylo_page,
            self._alzheimer_page, self._simulation_page,
            self._export_page, self._profile_page,
        ]:
            self._stack.addWidget(page)

        # Wire signals
        self._overview_page.fetch_requested.connect(self._on_fetch_requested)
        self._overview_page.set_cancel_callback(self._on_cancel)
        self._upload_page.file_selected.connect(self._on_file_selected)
        self._upload_page.local_run_added.connect(self._on_local_run_added)
        self._profile_page.logout_requested.connect(self._on_logout)
        self._profile_page.load_project.connect(self._on_load_project)
        self._profile_page.delete_project.connect(self._on_delete_project)
        self._alzheimer_page.assessment_requested.connect(self._on_get_risk_assessment)
        self._simulation_page.simulation_requested.connect(self._on_run_simulation)

        host_lay.addWidget(self._stack)
        scroll.setWidget(host)
        return scroll

    # ── Auth flow ─────────────────────────────────────────────────────────────

    def _on_login_success(self, user: dict) -> None:
        self._current_user = user
        # Show user name in topbar
        self._user_lbl.setText(f"◉  {user['username']}")
        self._user_lbl.show()
        self._signout_btn.show()
        # Populate profile page
        self._profile_page.load(user)
        # Switch to main app
        self._top_stack.setCurrentIndex(1)

    def _on_logout(self) -> None:
        self._current_user = None
        self._state = AppState()
        # Reset topbar
        self._user_lbl.hide()
        self._signout_btn.hide()
        self._topbar_title.setText("Axis — Microbiome Analytics")
        self._status_badge.setText("No project loaded")
        self._status_badge.setObjectName("badge_yellow")
        self._status_badge.style().unpolish(self._status_badge)
        self._status_badge.style().polish(self._status_badge)
        self._runs_badge.hide()
        self._analysis_badge.hide()
        # Go back to auth screen
        self._top_stack.setCurrentIndex(0)

    # ── Fetch flow ────────────────────────────────────────────────────────────

    def _on_fetch_requested(self, bioproject: str, run_accession: str, max_runs: int, email: str, username: str) -> None:
        self._status_badge.setText("Fetching from NCBI…")
        self._status_badge.show()

        self._show_cancel(True)

        # emma changes
        self._fetch_real_thread = QThread(self)
        self._fetch_real_worker = _FetchWorkerReal(bioproject=bioproject,
                                                   email=email,
                                                   runner=self._runner,
                                                   srr=run_accession,
                                                   n_runs=max_runs)
        self._fetch_real_worker.moveToThread(self._fetch_real_thread)
        self._fetch_real_thread.started.connect(self._fetch_real_worker.run)
        self._fetch_real_worker.canceled.connect(self._on_cancel)
        self._fetch_real_worker.progress.connect(self._upload_page.append_terminal_output)
        self._fetch_real_worker.finished.connect(self._on_fetch_complete)
        self._fetch_real_worker.errored.connect(self._on_fetch_error)
        self._fetch_real_worker.finished.connect(self._fetch_real_thread.quit)
        self._fetch_real_worker.errored.connect(self._fetch_real_thread.quit)
        self._fetch_real_thread.start()
        # emma changes


        # self._fetch_thread = QThread(self)
        # self._fetch_worker = _FetchWorker(bioproject, run_accession, max_runs)
        # self._fetch_worker.moveToThread(self._fetch_thread)
        # self._fetch_thread.started.connect(self._fetch_worker.run)
        # self._fetch_worker.finished.connect(self._on_fetch_complete)
        # self._fetch_worker.errored.connect(self._on_fetch_error)
        # self._fetch_worker.finished.connect(self._fetch_thread.quit)
        # self._fetch_worker.errored.connect(self._fetch_thread.quit)
        # self._fetch_thread.start()

    def _on_fetch_complete(self, single_runs, paired_runs, project_dict: dict) -> None:
        """Build AppState from NCBI data, save to DB, then run analysis."""
        state = AppState(
            bioproject_id = project_dict["bioproject_id"],
            project_uid   = project_dict.get("project_uid", ""),
            title         = project_dict.get("title", ""),
            organism      = project_dict.get("organism", ""),
            single_runs   = single_runs,
            paired_runs   = paired_runs,
            run_count     = len(single_runs) + len(paired_runs)
        )

        for run in project_dict.get("runs", []):
            state.runs[run['run_accession']] = run
            # state.runs.append(RunState(
            #     label       = lbl,
            #     accession   = project_dict["run_accessions"].get(lbl, ""),
            #     read_count  = project_dict.get("read_counts", {}).get(lbl, 0),
            #     base_count  = project_dict.get("base_counts", {}).get(lbl, 0),
            #     layout      = project_dict.get("library_layouts", {}).get(lbl, "PAIRED"),
            #     instrument  = project_dict.get("instruments", {}).get(lbl, ""),
            #     uploaded    = False,
            # ))
        self._state = state

        # Persist project to DB so it appears on the profile page
        if self._current_user:
            try:
                project = save_ncbi_project(
                        user_id            = self._current_user["user_id"],
                        bio_proj_accession = self._state.bioproject_id,
                        title              = self._state.title or self._state.bioproject_id,
                        runs               = [
                            {"accession": accession, "layout": run_dict['library_layout']}
                            for accession, run_dict in self._state.runs.items()
                        ],
                )
                self._state.db_project_id = project["project_id"]
                self._profile_page.refresh()
            except Exception:
                pass   # DB failure must not interrupt analysis

        # Update topbar
        self._topbar_title.setText(f"{state.bioproject_id}")
        state.run_count = len(state.runs)
        self._runs_badge.setText(f"{state.run_count} run{'s' if state.run_count != 1 else ''} loaded")
        self._runs_badge.show()
        # self._status_badge.setText("Computing analysis…")

        self._overview_page.load(state)
        self._broadcast_state()
        # Navigate to Upload Runs page so user sees download progress
        self._switch_page(1)
        self._start_download()

    def _on_fetch_error(self, message: str) -> None:
        self._status_badge.setText("Fetch failed")
        self._overview_page.show_fetch_error(message)

    # ── Download flow (fasterq-dump) ──────────────────────────────────────────

    def _start_download(self) -> None:
        """Start fasterq-dump download."""
        self._show_cancel(True)
        self._status_badge.setText("Downloading FASTQ files…")
        self._status_badge.setObjectName("badge_yellow")
        self._status_badge.style().unpolish(self._status_badge)
        self._status_badge.style().polish(self._status_badge)
        self._upload_page.update_pipeline_status("Downloading FASTQ files from NCBI…", "info")
        self._upload_page.clear_terminal()

        # emma changes
        self._dl_thread_real = QThread(self)
        self._dl_worker_real = _DownloadWorkerReal(state=self._state, runner=self._runner)
        self._dl_worker_real.moveToThread(self._dl_thread_real)
        self._dl_thread_real.started.connect(self._dl_worker_real.run)
        self._dl_worker_real.progress.connect(self._on_analysis_progress)
        self._dl_worker_real.finished.connect(self._on_download_complete)
        self._dl_worker_real.errored.connect(self._on_download_error)
        self._dl_worker_real.finished.connect(self._dl_thread_real.quit)
        self._dl_worker_real.errored.connect(self._dl_thread_real.quit)
        self._dl_thread_real.start()
        # emma changes


        # self._dl_thread = QThread(self)
        # self._dl_worker = _DownloadWorker(self._state)
        # self._dl_worker.moveToThread(self._dl_thread)
        # self._dl_thread.started.connect(self._dl_worker.run)
        # self._dl_worker.progress.connect(self._on_analysis_progress)
        # self._dl_worker.finished.connect(self._on_download_complete)
        # self._dl_worker.errored.connect(self._on_download_error)
        # self._dl_worker.finished.connect(self._dl_thread.quit)
        # self._dl_worker.errored.connect(self._dl_thread.quit)
        # self._dl_thread.start()

    def _on_download_complete(self, state: "AppState") -> None:
        """All (or some) runs downloaded — auto-populate Upload page, then run pipeline."""
        self._show_cancel(False)
        self._state = state
        self._downloaded = True
        # get number of successfully downloaded runs as fastq files
        uploaded = self._state.uploaded_count

        self._runs_badge.setText(
            f"{state.run_count} run{'s' if state.run_count != 1 else ''} loaded  ·  "
            f"{uploaded} FASTQ downloaded"
        )
        self._status_badge.setText("Ready to run QIIME preprocessing")
        self._status_badge.setObjectName("badge_green")
        self._status_badge.style().unpolish(self._status_badge)
        self._status_badge.style().polish(self._status_badge)

        # Auto-populate Upload Runs page with the downloaded files
        self._upload_page.auto_mark_uploaded(state)

        # Count runs (not files) — uploaded_count counts 2 per paired run
        uploaded_runs = sum(1 for r in state.runs.values() if r['uploaded'])
        failed_runs   = state.run_count - uploaded_runs
        fastq_files   = uploaded  # uploaded_count property

        if failed_runs > 0:
            self._upload_page.update_pipeline_status(
                f"{uploaded_runs}/{state.run_count} run(s) downloaded "
                f"({fastq_files} FASTQ) — {failed_runs} failed. Browse to upload manually.",
                "warn",
            )
        else:
            self._upload_page.update_pipeline_status(
                f"All {uploaded_runs} run(s) downloaded ({fastq_files} FASTQ files) — ready",
                "ok",
            )

        # Enable button for any uploaded runs (partial data is fine)
        if uploaded_runs > 0:
            self._upload_page.show_run_pipeline_btn(
                ready=True,
                callback=self._on_check_env,
                cancel_callback=self._on_cancel,
            )

        # Refresh Overview so run statuses show ✓ Uploaded instead of ○ Pending
        self._overview_page.load(state)

    def _on_download_error(self, msg: str) -> None:
        self._show_cancel(False)
        self._status_badge.setText("Error downloading — try uploading from disk")
        # Show a non-blocking info notice on the Upload page
        if "not found" in msg.lower() or "sra-tools" in msg.lower():
            self._upload_page.update_pipeline_status(
                "fasterq-dump not found — browse to upload FASTQ files manually", "warn"
            )
            self._upload_page.append_terminal_output(
                "fasterq-dump not installed. Install SRA-tools to enable auto-download:\n"
                "  conda install -c bioconda sra-tools\n"
                "You can still browse and upload FASTQ files manually.\n"
            )
        else:
            self._upload_page.update_pipeline_status(f"Download error: {msg[:80]}", "err")
        self._broadcast_state()

    # ── Analysis flow ─────────────────────────────────────────────────────────

    def _run_analysis(self) -> None:
        # self._analysis_thread = QThread(self)
        # self._analysis_worker = _AnalysisWorker(self._state)
        # self._analysis_worker.moveToThread(self._analysis_thread)
        # self._analysis_thread.started.connect(self._analysis_worker.run)
        # self._analysis_worker.progress.connect(self._on_analysis_progress)
        # self._analysis_worker.finished.connect(self._on_analysis_complete)
        # self._analysis_worker.errored.connect(self._on_analysis_error)
        # self._analysis_worker.finished.connect(self._analysis_thread.quit)
        # self._analysis_worker.errored.connect(self._analysis_thread.quit)
        # self._analysis_thread.start()
        self._analysis_thread_real = QThread(self)
        self._analysis_worker_real = _AnalysisWorkerReal(self._state)
        self._analysis_worker_real.moveToThread(self._analysis_thread_real)
        self._analysis_thread_real.started.connect(self._analysis_worker_real.run)
        self._analysis_worker_real.progress.connect(self._on_analysis_progress)
        self._analysis_worker_real.finished.connect(self._on_analysis_complete)
        self._analysis_worker_real.errored.connect(self._on_analysis_error)
        self._analysis_worker_real.finished.connect(self._analysis_thread_real.quit)
        self._analysis_worker_real.errored.connect(self._analysis_thread_real.quit)
        self._analysis_thread_real.start()

    def _on_analysis_progress(self, msg: str) -> None:
        self._status_badge.setText(msg)

    def _on_analysis_complete(self, state: AppState) -> None:
        self._state = state
        self._state.pipeline_complete = True
        self._status_badge.setText("Analysis complete")
        self._status_badge.setObjectName("badge_green")
        self._status_badge.style().unpolish(self._status_badge)
        self._status_badge.style().polish(self._status_badge)

        self._analysis_badge.setText(
            f"{state.asv_count:,} ASVs  ·  {state.genus_count} genera"
        )
        self._analysis_badge.show()
        self._upload_page.update_pipeline_status(
            f"Analysis complete — {state.asv_count:,} ASVs · {state.genus_count} genera", "ok"
        )

        self._overview_page.load(state)
        self._broadcast_state()

        # If a phylogenetic tree is stored, compute UniFrac PCoA automatically
        if state.tree_id is not None and state.run_count > 1:
            self._on_unifrac_run()

    def _on_analysis_error(self, msg: str) -> None:
        self._status_badge.setText(f"Analysis error: {msg[:60]}")


    def _on_phylogeny_run(self) -> None:
        self._status_badge.setText("Inferring phylogeny...")
        self._status_badge.setObjectName("badge_yellow")
        self._status_badge.style().unpolish(self._status_badge)
        self._status_badge.style().polish(self._status_badge)
        self._phylo_thread = QThread(self)
        self._phylo_worker = _PhylogenyWorker(state=self._state, runner=self._runner)
        self._phylo_worker.moveToThread(self._phylo_thread)
        self._phylo_thread.started.connect(self._phylo_worker.run)
        self._phylo_worker.finished.connect(self._on_phylo_complete)
        self._phylo_worker.errored.connect(self._on_phylo_error)
        self._phylo_worker.finished.connect(self._phylo_thread.quit)
        self._phylo_worker.errored.connect(self._phylo_thread.quit)
        self._phylo_thread.start()

    def _on_phylo_complete(self, state: AppState) -> None:
        self._status_badge.setText("Phylogeny complete")
        self._status_badge.setObjectName("badge_green")
        self._status_badge.style().unpolish(self._status_badge)
        self._status_badge.style().polish(self._status_badge)
        self._state.phylo_tree = True # TODO: i don't know if this is needed but just in case (chung you can remove)

        # TODO: display the phylogenetic tree (chung)

        # TODO: TEMPORARY
        self._on_unifrac_run()
        # TODO: TEMPORARY

    def _on_phylo_error(self, msg: str) -> None:
        self._status_badge.setText("Error inferring phylogeny")
        self._status_badge.setObjectName("badge_red")
        self._status_badge.style().unpolish(self._status_badge)
        self._status_badge.style().polish(self._status_badge)


    def _on_unifrac_run(self) -> None:
        self._status_badge.setText("Computing UniFrac…")
        self._status_badge.setObjectName("badge_yellow")
        self._status_badge.style().unpolish(self._status_badge)
        self._status_badge.style().polish(self._status_badge)
        self._unifrac_thread = QThread(self)
        self._unifrac_worker = _UnifracWorker(state=self._state)
        self._unifrac_worker.moveToThread(self._unifrac_thread)
        self._unifrac_thread.started.connect(self._unifrac_worker.run)
        self._unifrac_worker.finished.connect(self._on_unifrac_complete)
        self._unifrac_worker.errored.connect(self._on_unifrac_error)
        self._unifrac_worker.finished.connect(self._unifrac_thread.quit)
        self._unifrac_worker.errored.connect(self._unifrac_thread.quit)
        self._unifrac_thread.start()

    def _on_unifrac_complete(self, state: AppState) -> None:
        self._state = state
        self._status_badge.setText("UniFrac complete")
        self._status_badge.setObjectName("badge_green")
        self._status_badge.style().unpolish(self._status_badge)
        self._status_badge.style().polish(self._status_badge)
        # Refresh diversity page so UniFrac PCoA appears
        self._broadcast_state()

    def _on_unifrac_error(self, msg: str) -> None:
        self._status_badge.setText(f"UniFrac skipped: {msg[:60]}")
        self._status_badge.setObjectName("badge_yellow")
        self._status_badge.style().unpolish(self._status_badge)
        self._status_badge.style().polish(self._status_badge)

    # ── Cancel ────────────────────────────────────────────────────────────────

    def _show_cancel(self, visible: bool) -> None:
        self._cancel_btn.setVisible(visible)

    def _on_cancel(self) -> None:
        self._cancel_btn.setEnabled(False)

        # Kill any running QIIME2 subprocess
        if self._runner:
            self._runner.cancel()

        # Terminate all active worker threads
        threads_to_kill = []
        for attr in (
            '_fetch_real_thread',
            '_dl_thread_real',
            '_pipeline_thread_real',
            '_parsing_thread_real',
            '_analysis_thread',
        ):
            thread = getattr(self, attr, None)
            if thread and thread.isRunning():
                thread.quit()
                # thread.terminate()
                # thread.wait(2000)
                threads_to_kill.append(thread)

        # # Delete intermediate files
        # if self._state and self._state.bioproject_id:
        #     try:
        #         from src.pipeline.fetch_data import cleanup
        #         cleanup(self._state.bioproject_id)
        #     except Exception as exc:
        #         print(f"Cleanup error on cancel: {exc}")

        # give threads a short time to quit gracefully
        # process UI events while waiting so the app doesn't freeze
        from PyQt6.QtCore import QCoreApplication
        import time
        deadline = time.time() + 2.0
        while any(t.isRunning() for t in threads_to_kill) and time.time() < deadline:
            QCoreApplication.processEvents()
            time.sleep(0.05)

        # force kill anything still running
        for thread in threads_to_kill:
            if thread.isRunning():
                thread.terminate()

        # run cleanup in background so it doesn't block UI
        def _do_cleanup():
            try:
                from src.pipeline.fetch_data import cleanup
                cleanup(self._state.bioproject_id)
            except Exception as exc:
                print(f"Cleanup error on cancel: {exc}")

        if self._state and self._state.bioproject_id:
            import threading
            threading.Thread(target=_do_cleanup, daemon=True).start()

        # Reset UI
        self._cancel_btn.hide()
        self._cancel_btn.setEnabled(True)
        self._overview_page._restore_fetch_btn()
        self._status_badge.setText("Canceled")
        self._status_badge.setObjectName("badge_yellow")
        self._status_badge.style().unpolish(self._status_badge)
        self._status_badge.style().polish(self._status_badge)
        self._upload_page.update_pipeline_status("Canceled", "warn")
        self._upload_page.append_terminal_output("\n[CANCELED] Operation canceled.\n")
        self._overview_page._status_lbl.hide()
        # Restore Run Pipeline button so the user can retry
        if self._state and any(r.get('uploaded') for r in self._state.runs.values()):
            self._upload_page.reset_pipeline_btn(
                callback=self._on_check_env, cancel_callback=self._on_cancel)

    def _broadcast_state(self) -> None:
        for page in [
            self._overview_page,
            self._upload_page,
            self._diversity_page,
            self._taxonomy_page,
            self._asv_page,
            self._phylo_page,
            self._alzheimer_page,
            self._simulation_page,
        ]:
            if hasattr(page, "load"):
                try:
                    page.load(self._state)
                except Exception:
                    pass

    # ── File upload + pipeline trigger ───────────────────────────────────────

    def _on_file_selected(self, run_label: str, slot: str, path: str) -> None:
        # Find run dict by label
        run_dict = next(
            (r for r in self._state.runs.values() if r['label'] == run_label), None)
        if not run_dict:
            return

        # Validate FASTQ header
        try:
            from src.pipeline.qc import _validate_fastq_header
            valid, error = _validate_fastq_header(path)
        except (ImportError, AttributeError):
            valid, error = True, ""

        if not valid:
            self._upload_page.update_run_status(run_label, False, error)
            return

        # Store path in run dict under the right slot
        layout = run_dict.get('library_layout', 'PAIRED').upper()
        if slot == 'forward':
            run_dict['fastq_forward'] = path
        elif slot == 'reverse':
            run_dict['fastq_reverse'] = path
        else:
            run_dict['fastq_path'] = path

        # Mark uploaded once all required files are present
        if layout == 'PAIRED':
            both = run_dict.get('fastq_forward') and run_dict.get('fastq_reverse')
            run_dict['uploaded'] = bool(both)
        else:
            run_dict['uploaded'] = bool(run_dict.get('fastq_path'))

        # Refresh both pages so file-path rows and status update
        self._upload_page.load(self._state)
        self._overview_page.load(self._state)

        uploaded_runs = sum(1 for r in self._state.runs.values() if r['uploaded'])
        if uploaded_runs > 0:
            self._upload_page.show_run_pipeline_btn(
                ready=True, callback=self._on_check_env, cancel_callback=self._on_cancel)
            self._upload_page.update_pipeline_status(
                f"{uploaded_runs} of {self._state.run_count} run(s) ready — click Run Pipeline to start",
                "ok"
            )

    def _on_local_run_added(self, layout: str, fwd_path: str, rev_path: str) -> None:
        """User added a local FASTQ file via the Add Local FASTQ card."""
        if self._state is None:
            return

        # Generate unique accession and label
        local_n = sum(1 for k in self._state.runs if k.startswith("LOCAL_")) + 1
        accession = f"LOCAL_{local_n}"
        all_labels = [r['label'] for r in self._state.runs.values()]
        label = f"L{local_n}"

        run = {
            'run_accession'    : accession,
            'label'            : label,
            'read_count'       : 0,
            'base_count'       : 0,
            'library_layout'   : layout,
            'library_strategy' : 'AMPLICON',
            'platform'         : 'LOCAL',
            'instrument'       : '',
            'sample_accession' : '',
            'organism'         : self._state.organism,
            'uploaded'         : True,
            'qiime_error'      : '',
        }

        if layout == 'PAIRED':
            run['fastq_forward'] = fwd_path
            run['fastq_reverse'] = rev_path
        else:
            run['fastq_path'] = fwd_path

        self._state.runs[accession] = run
        self._state.run_count = len(self._state.runs)
        if layout == 'PAIRED':
            self._state.paired_runs.append(accession)
        else:
            self._state.single_runs.append(accession)

        self._upload_page.load(self._state)
        self._overview_page.load(self._state)

        uploaded_runs = sum(1 for r in self._state.runs.values() if r['uploaded'])
        self._upload_page.show_run_pipeline_btn(
            ready=True, callback=self._on_check_env, cancel_callback=self._on_cancel)
        self._upload_page.update_pipeline_status(
            f"{label} added — {uploaded_runs} run(s) ready for pipeline", "ok")

    def _write_manifests_from_state(self) -> None:
        """Re-write QIIME2 manifest TSVs using paths stored in run dicts.

        Works for both NCBI-downloaded files (standard paths) and user-browsed
        files (arbitrary paths stored in fastq_forward / fastq_reverse / fastq_path).
        Called just before pipeline starts so manifests are always current.
        """
        import csv as _csv
        from pathlib import Path as _P

        APP_DIR = _P(__file__).parent.parent / "pipeline"
        bio = self._state.bioproject_id

        paired = [r for r in self._state.runs.values()
                  if r.get('library_layout', '').upper() == 'PAIRED' and r['uploaded']]
        single = [r for r in self._state.runs.values()
                  if r.get('library_layout', '').upper() == 'SINGLE' and r['uploaded']]

        if paired:
            out = APP_DIR / f"data/{bio}/qiime/paired"
            out.mkdir(parents=True, exist_ok=True)
            with open(out / "manifest.tsv", "w", newline="") as f:
                w = _csv.writer(f, delimiter='\t')
                w.writerow(['sample-id', 'forward-absolute-filepath',
                            'reverse-absolute-filepath'])
                for r in paired:
                    srr = r['run_accession']
                    fwd = r.get('fastq_forward') or str(
                        APP_DIR / f"data/{bio}/fastq/paired/{srr}_1.fastq")
                    rev = r.get('fastq_reverse') or str(
                        APP_DIR / f"data/{bio}/fastq/paired/{srr}_2.fastq")
                    w.writerow([srr, fwd, rev])

        if single:
            out = APP_DIR / f"data/{bio}/qiime/single"
            out.mkdir(parents=True, exist_ok=True)
            with open(out / "manifest.tsv", "w", newline="") as f:
                w = _csv.writer(f, delimiter='\t')
                w.writerow(['sample-id', 'absolute-filepath'])
                for r in single:
                    srr = r['run_accession']
                    path = r.get('fastq_path') or str(
                        APP_DIR / f"data/{bio}/fastq/single/{srr}.fastq")
                    w.writerow([srr, path])

    def _on_check_env(self) -> None:

        # Detect whether QIIME2 is available and report in the terminal
        self._upload_page.show_terminal(True)
        self._upload_page.clear_terminal()
        self._upload_page.update_pipeline_status("Checking QIIME2 environment…", "info")
        uploaded_srrs = [srr for srr, r in self._state.runs.items() if r['uploaded']]
        skipped_srrs  = [srr for srr, r in self._state.runs.items() if not r['uploaded']]
        self._upload_page.append_terminal_output("=== Axis Pipeline ===")
        self._upload_page.append_terminal_output(f"Project : {self._state.bioproject_id}")
        self._upload_page.append_terminal_output(
            f"Process : {', '.join(uploaded_srrs)}")
        if skipped_srrs:
            self._upload_page.append_terminal_output(
                f"Skipped : {', '.join(skipped_srrs)}  (not downloaded)")
        self._upload_page.append_terminal_output("")


        self._checkenv_thread = QThread(self)
        self._checkenv_worker = _CheckEnvWorker(runner=self._runner)
        self._checkenv_worker.moveToThread(self._checkenv_thread)
        self._checkenv_thread.started.connect(self._checkenv_worker.run)
        self._checkenv_worker.finished.connect(self._on_check_env_complete)
        self._checkenv_worker.errored.connect(self._on_check_env_error)
        self._checkenv_worker.finished.connect(self._checkenv_thread.quit)
        self._checkenv_worker.errored.connect(self._checkenv_thread.quit)
        self._checkenv_thread.start()


    def _on_check_env_complete(self, qiime2_available: bool, stdout) -> None:
        if qiime2_available:
            ver = stdout.strip().splitlines()[0] if stdout.strip() else "detected"
            self._upload_page.append_terminal_output(f"QIIME2 detected: {ver}")
            self._upload_page.append_terminal_output("")
            self._on_run_pipeline()
        else:
            self._upload_page.append_terminal_output(
                "QIIME2 not found in environment.\n"
                "Install QIIME2 (see README Setup Guide, Step 6) and try again."
            )
            self._upload_page.append_terminal_output("")
            self._upload_page.update_pipeline_status(
                "QIIME2 not found — install it to run the pipeline.", "err"
            )
            self._upload_page.show_pipeline_error(
                "QIIME2 is not installed. See the README Setup Guide (Step 6) for installation instructions."
            )
            self._upload_page.reset_pipeline_btn(callback=self._on_check_env,
                                                 cancel_callback=self._on_cancel)
            self._status_badge.setText("QIIME2 not found")
            self._status_badge.setObjectName("badge_red")
            self._status_badge.style().unpolish(self._status_badge)
            self._status_badge.style().polish(self._status_badge)


    def _on_check_env_error(self, exc: str) -> None:
        self._upload_page.append_terminal_output(
            f"QIIME2 environment check failed: {exc}"
        )
        self._upload_page.append_terminal_output("")
        self._upload_page.update_pipeline_status(
            "QIIME2 environment check failed.", "err"
        )
        self._upload_page.show_pipeline_error(
            f"Could not check QIIME2 environment: {exc}"
        )
        self._upload_page.reset_pipeline_btn(callback=self._on_check_env,
                                             cancel_callback=self._on_cancel)
        self._status_badge.setText("Environment check failed")
        self._status_badge.setObjectName("badge_red")
        self._status_badge.style().unpolish(self._status_badge)
        self._status_badge.style().polish(self._status_badge)


    def _on_run_pipeline(self) -> None:
        self._status_badge.setText("Running QIIME2 pipeline…")
        self._status_badge.setObjectName("badge_yellow")
        self._status_badge.style().unpolish(self._status_badge)
        self._status_badge.style().polish(self._status_badge)
        self._status_badge.show()
        self._upload_page.update_pipeline_status("QIIME2 pipeline running…\nThis may take a few minutes", "run")

        if self._downloaded == False:
            try:
                self._write_manifests_from_state()
                self._upload_page.append_terminal_output("Manifests written — starting QIIME2…\n")
            except Exception as e:
                self._upload_page.append_terminal_output(f"[WARN] Could not write manifests: {e}\n")

        # emma changes
        self._pipeline_thread_real = QThread(self)
        self._pipeline_worker_real = _PipelineWorkerReal(runner=self._runner,
                                                         bioproject=self._state.bioproject_id,
                                                         state=self._state)
        self._pipeline_worker_real.moveToThread(self._pipeline_thread_real)
        self._pipeline_thread_real.started.connect(self._pipeline_worker_real.run)
        self._pipeline_worker_real.progress.connect(self._on_analysis_progress)
        self._pipeline_worker_real.progress.connect(self._upload_page.append_terminal_output)
        self._pipeline_worker_real.finished.connect(self._on_pipeline_complete)
        self._pipeline_worker_real.errored.connect(self._on_pipeline_error)
        self._pipeline_worker_real.finished.connect(self._pipeline_thread_real.quit)
        self._pipeline_worker_real.errored.connect(self._pipeline_thread_real.quit)
        self._pipeline_thread_real.start()
        # emma changes

    def _on_pipeline_complete(self, state: AppState) -> None:
        self._upload_page.reset_pipeline_btn(callback=self._on_check_env,
                                             cancel_callback=self._on_cancel)
        self._state = state
        self._status_badge.setText("QIIME2 pipeline complete")
        self._status_badge.setObjectName("badge_green")
        self._status_badge.style().unpolish(self._status_badge)
        self._status_badge.style().polish(self._status_badge)
        self._upload_page.update_pipeline_status("QIIME2 pipeline complete — parsing results…", "ok")
        self._upload_page.append_terminal_output("\n=== Pipeline complete — saving results to database ===\n")

        self._overview_page.load(state)
        self._broadcast_state()

        self._run_parsing()

    def _on_pipeline_error(self, msg: str) -> None:
        self._upload_page.reset_pipeline_btn(callback=self._on_check_env,
                                             cancel_callback=self._on_cancel)
        if "db_import" in msg or "No module named" in msg:
            display = "QIIME2 pipeline module is incomplete (missing db_import)."
        else:
            display = msg
        self._upload_page.show_pipeline_error(display)
        self._upload_page.update_pipeline_status("Pipeline failed.", "err")
        self._upload_page.append_terminal_output(f"\n[ERROR] {msg}\n")
        self._status_badge.setText("Pipeline failed")
        self._status_badge.setObjectName("badge_red")
        self._status_badge.style().unpolish(self._status_badge)
        self._status_badge.style().polish(self._status_badge)

    def _run_parsing(self) -> None:
        self._status_badge.setText(
            "Parsing and saving to database..."
        )
        self._status_badge.setObjectName("badge_yellow")
        self._status_badge.style().unpolish(self._status_badge)
        self._status_badge.style().polish(self._status_badge)
        self._status_badge.show()

        self._parsing_thread_real = QThread(self)
        self._parsing_worker_real = _ParseWorkerReal(bioproject=self._state.bioproject_id, state=self._state, user=self._current_user)
        self._parsing_worker_real.moveToThread(self._parsing_thread_real)
        self._parsing_thread_real.started.connect(self._parsing_worker_real.run)
        self._parsing_worker_real.progress.connect(self._on_analysis_progress)
        self._parsing_worker_real.finished.connect(self._on_parsing_complete)
        self._parsing_worker_real.errored.connect(self._on_parsing_error)
        self._parsing_worker_real.finished.connect(self._parsing_thread_real.quit)
        self._parsing_worker_real.errored.connect(self._parsing_thread_real.quit)
        self._parsing_thread_real.start()

    def _on_parsing_complete(self, state: AppState):
        self._status_badge.setText("Parsing complete")
        self._status_badge.setObjectName("badge_green")
        self._status_badge.style().unpolish(self._status_badge)
        self._status_badge.style().polish(self._status_badge)
        self._upload_page.update_pipeline_status("Results saved — computing analysis…", "ok")
        self._upload_page.append_terminal_output("Results saved to database. Running analysis…\n")
        self._overview_page.load(state)
        self._broadcast_state()

        # hand it off to run analysis
        self._run_analysis()

    def _on_parsing_error(self, msg: str):
        self._upload_page.show_pipeline_error(msg)
        self._status_badge.setText("Parsing error")
        self._status_badge.setObjectName("badge_red")
        self._status_badge.style().unpolish(self._status_badge)
        self._status_badge.style().polish(self._status_badge)

    # ── Risk ──────────────────────────────────────────────────────────────────
    def _on_get_risk_assessment(self, apoe: dict=None, mri: str=None, run_lbl: str='R1') -> None:
        self._status_badge.setText(
            "Getting risk..."
        )
        self._status_badge.setObjectName("badge_yellow")
        self._status_badge.style().unpolish(self._status_badge)
        self._status_badge.style().polish(self._status_badge)
        self._status_badge.show()
        self._risk_assess_thread = QThread(self)
        self._risk_assess_worker = _RiskPredictionWorker(state=self._state, apoe=apoe, mri=mri, run_lbl=run_lbl)
        self._risk_assess_worker.moveToThread(self._risk_assess_thread)
        self._risk_assess_thread.started.connect(self._risk_assess_worker.run)
        self._risk_assess_worker.finished.connect(self._on_risk_assess_complete)
        self._risk_assess_worker.errored.connect(self._on_risk_assess_error)
        self._risk_assess_worker.finished.connect(self._risk_assess_thread.quit)
        self._risk_assess_worker.errored.connect(self._risk_assess_thread.quit)
        self._risk_assess_thread.start()
    
    def _on_risk_assess_complete(self, state: AppState):
        self._status_badge.setText("Assessment complete")
        self._status_badge.setObjectName("badge_green")
        self._status_badge.style().unpolish(self._status_badge)
        self._status_badge.style().polish(self._status_badge)
        self._alzheimer_page.load(state=state)
    
    def _on_risk_assess_error(self, msg: str):
        self._upload_page.show_pipeline_error(msg)
        print(msg)
        self._status_badge.setText("Assessment error")
        self._status_badge.setObjectName("badge_red")
        self._status_badge.style().unpolish(self._status_badge)
        self._status_badge.style().polish(self._status_badge)


    # ── Simulation ────────────────────────────────────────────────────────────

    def _on_run_simulation(self, user_diet: dict, run_label: str='R1'):
        self._status_badge.setText("Running simulation...")
        self._status_badge.setObjectName("badge_yellow")
        self._status_badge.style().unpolish(self._status_badge)
        self._status_badge.style().polish(self._status_badge)
        self._status_badge.show()

        self._simulation_thread = QThread(self)
        self._simulation_worker = _SimulationWorker(state=self._state, run_label=run_label, 
                                                    user_diet=user_diet, runner=self._runner)
        self._simulation_worker.moveToThread(self._simulation_thread)
        self._simulation_thread.started.connect(self._simulation_worker.run)
        self._simulation_worker.finished.connect(self._on_simulation_complete)
        self._simulation_worker.errored.connect(self._on_simulation_error)
        self._simulation_worker.finished.connect(self._simulation_thread.quit)
        self._simulation_worker.errored.connect(self._simulation_thread.quit)
        self._simulation_thread.start()
    
    def _on_simulation_complete(self, state: AppState):
        self._status_badge.setText("Simulation complete")
        self._status_badge.setObjectName("badge_green")
        self._status_badge.style().unpolish(self._status_badge)
        self._status_badge.style().polish(self._status_badge)
        self._simulation_page.load(state=state)
    
    def _on_simulation_error(self, msg: str):
        self._upload_page.show_pipeline_error(msg)
        self._status_badge.setText("Simulation error")
        self._status_badge.setObjectName("badge_red")
        self._status_badge.style().unpolish(self._status_badge)
        self._status_badge.style().polish(self._status_badge)


    # ── Profile page integration ──────────────────────────────────────────────

    def _on_load_project(self, bio_proj_accession: str) -> None:
        """Re-fetch a past project from NCBI and navigate to Overview."""
        self._switch_page(0)
        self._on_fetch_requested(bioproject=bio_proj_accession, run_accession="", max_runs=5, email='emmanicolego@gmail.com', username=self._current_user['user_id'])

    def _on_delete_project(self, project_id: int) -> None:
        """Delete a project from the DB and refresh the profile page."""
        try:
            from services.assessment_service import delete_project
            delete_project(project_id)
        except Exception as exc:
            print(f"Delete project error: {exc}")
        finally:
            self._profile_page.refresh()

    # ── Navigation ────────────────────────────────────────────────────────────

    def _switch_page(self, idx: int) -> None:
        if idx == self._active_idx:
            return
        old = self._nav_buttons[self._active_idx]
        old.setProperty("active", False)
        old.style().unpolish(old); old.style().polish(old)

        self._active_idx = idx
        new = self._nav_buttons[idx]
        new.setProperty("active", True)
        new.style().unpolish(new); new.style().polish(new)

        self._stack.setCurrentIndex(idx)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sb_label(text: str, obj_name: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName(obj_name)
    return lbl
