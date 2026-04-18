# src/services/assessment_service.py
#
# Service layer — bridges the GUI and the database.
# Owns the session lifecycle (open -> commit/rollback -> close).
# All functions return plain Python dicts, no SQLAlchemy objects leave this module.
from __future__ import annotations

from typing import Callable

from src.db.database import SessionLocal
from src.db.repository import (
    get_user,
    get_user_by_username,
    create_user as repo_create_user,
    create_project as repo_create_project,
    create_run as repo_create_run,
    get_project,
    get_run,
    get_run_by_srr,
    list_projects_for_user,
    list_runs_for_project,
    create_genus_bulk,
    get_genus_for_run,
    get_run_exists_genus_table,
    create_feature,
    list_features_for_run,
    create_feature_count_bulk,
    get_feature_counts_for_run,
    get_run_exists_feature_table,
    get_run_exists_feature_count_table,
    create_tree,
    get_tree_for_run,
    create_alpha_diversity,
    get_alpha_diversity_for_run,
    create_beta_diversity as repo_create_beta_diversity,
    get_beta_diversity,
    update_run_risk,
    RepositoryError,
    NotFoundError,
    hash_password,
    verify_password,
    username_exists,
)


class ServiceError(Exception):
    """Raised when a service operation fails (wraps RepositoryError)."""


# ==== User ====
def get_or_create_user(username: str) -> dict:
    """
    Return existing user by username, or create one and return if not found.
    Intended for pipeline/testing use while the GUI auth is not yet built.
    """
    session = SessionLocal()
    try:
        user = get_user_by_username(session, username)
        if user is None:
            user = repo_create_user(session, username=username)
            session.commit()
        return {"user_id": user.user_id, "username": user.username}
    except RepositoryError as e:
        session.rollback()
        raise ServiceError(str(e)) from e
    finally:
        session.close()

def register_user(username: str, password: str) -> dict:
    session = SessionLocal()
    try:
        if username_exists(session, username):
            raise ServiceError(f"Username {username!r} is already taken")
        hashed = hash_password(password)
        user = repo_create_user(session, username=username, password_hash=hashed)
        session.commit()
        return {"user_id": user.user_id, "username": user.username}
    except RepositoryError as e:
        session.rollback()
        raise ServiceError(str(e)) from e
    finally:
        session.close()

def login_user(username: str, password: str) -> dict:
    session = SessionLocal()
    try:
        user = get_user_by_username(session, username)
        if not verify_password(password, user.password_hash):
            raise ServiceError("Incorrect password")
        return {"user_id": user.user_id, "username": user.username}
    except RepositoryError as e:
        raise ServiceError(str(e)) from e
    finally:
        session.close()

# ==== Project & Run setup ====
def create_project(user_id: int, name: str) -> dict:
    """
    Create a new project for a user and return it as a dict.
    Raises ServiceError if the user does not exist.
    """
    session = SessionLocal()
    try:
        user = get_user(session, user_id)       # verify user exists first
        project = repo_create_project(session, user=user, name=name)
        session.commit()
        return {
            "project_id": project.project_id,
            "user_id": project.user_id,
            "name": project.name,
            "created_at": project.created_at.isoformat(),
        }
    except RepositoryError as e:
        session.rollback()
        raise ServiceError(str(e)) from e
    finally:
        session.close()


def create_run(
        project_id: int,
        source: str,                            # "upload" || "ncbi"
        srr_accession: str | None = None,       # e.g. SRR35606904
        bio_proj_accession: str | None = None,  # e.g. PRJNA123456
        library_layout: str | None = None,      # "PAIRED" || "SINGLE"
) -> dict:
    """
    Create a new run under a project and return it as a dict.
    Raises ServiceError if the project does not exist.
    """
    session = SessionLocal()
    try:
        project = get_project(session, project_id)
        run = repo_create_run(
            session,
            project=project,
            source=source,
            srr_accession=srr_accession,
            bio_proj_accession=bio_proj_accession,
            library_layout=library_layout,
        )
        session.commit()
        return {
            "run_id": run.run_id,
            "project_id": run.project_id,
            "source": run.source,
            "srr_accession": run.srr_accession,
            "bio_proj_accession": run.bio_proj_accession,
            "library_layout": run.library_layout,
            "created_at": run.created_at.isoformat(),
        }
    except RepositoryError as e:
        session.rollback()
        raise ServiceError(str(e)) from e
    finally:
        session.close()


def get_run_id_by_srr(srr_accession: str) -> int:
    """
    Look up the integer run_id for an SRR accession string.
    ML pipeline uses SRR strings, the DB uses integer IDs.
    Raises ServiceError if the accession is not registered.
    """
    session = SessionLocal()
    try:
        run = get_run_by_srr(session, srr_accession)
        return run.run_id
    except RepositoryError as e:
        raise ServiceError(str(e)) from e
    finally:
        session.close()


# ==== Project overview ====
def get_project_overview(project_id: int) -> dict:
    """
    Return a summary of a project for the dashboard header.

    Counts total runs, unique ASVs across all runs, unique genere across all
    runs, and how many runs have data uploaded vs still pending.
    """
    session = SessionLocal()
    try:
        project = get_project(session, project_id)
        runs = list_runs_for_project(session, project_id)

        uploaded_count = 0
        total_asvs = 0
        all_genera: set[str] = set()

        for run in runs:
            features = list_features_for_run(session, run.run_id)
            genera = get_genus_for_run(session, run.run_id)

            # A run is "uploaded" if it has any data associated with it
            if features or genera:
                uploaded_count += 1

            total_asvs += len(features)
            all_genera.update(g.genus for g in genera)

        return {
            "project_id": project.project_id,
            "name": project.name,
            # Use the first run's accession as the project-level accession (ncbi projects)
            "bio_proj_accession": runs[0].bio_proj_accession if runs else None,
            "total_runs": len(runs),
            "uploaded_runs": uploaded_count,
            "pending_runs": len(runs) - uploaded_count,
            "total_asvs": total_asvs,
            "total_genera": len(all_genera),
            "run_ids": [r.run_id for r in runs],
        }
    except RepositoryError as e:
        raise ServiceError(str(e)) from e
    finally:
        session.close()


# ==== Run data ingestion ====
def ingest_run_data(
        run_id: int,                         # integer DB ID returned by create_run(), NOT the SRR accession string
        genus_rows: list[tuple[str, float]], # [(genus_name, relative_abundance), ...] parsed from genus-table.tsv
        features: list[dict],                # [{"feature_id": ..., "sequence": ..., "taxonomy": ...}]
        feature_counts: dict[str, int],      # {feature_id: raw_count}
        newick_path: str | None = None,      # path to .nwk file on disk, if available
) -> dict:
    """
    Bulk-insert all QIIME2 output for a run in a single transaction.

    Stores genus abundances, ASV features, feature counts, and optionally a
    phylogenetic tree. If anything fails, everything rolls back.
    """
    session = SessionLocal()
    try:
        run = get_run(session, run_id)

        # Convert list of tuples to dict for the repository layer
        genus_abundances = dict(genus_rows)

        # Insert genus-level relative abundances
        if not get_run_exists_genus_table(session, run_id):
            create_genus_bulk(session, run=run, genus_abundances=genus_abundances)

        # Insert each ASV feature (sequence + taxonomy)
        if not get_run_exists_feature_table(session, run_id):
            for f in features:
                create_feature(
                    session,
                    run=run,
                    feature_id=f["feature_id"],
                    sequence=f.get("sequence"),
                    taxonomy=f.get("taxonomy"),
                )

        # Flush features to DB before inserting counts — feature_count has a FK to feature
        session.flush()
        if not get_run_exists_feature_count_table(session, run_id):
            create_feature_count_bulk(session, run_id=run_id, counts=feature_counts)

        # Tree is optional — only store if a path was provided
        tree = None
        if newick_path:
            tree = create_tree(session, run=run, newick_path=newick_path)

        session.commit()
        return {
            "run_id": run_id,
            "genera_inserted": len(genus_abundances),
            "features_inserted": len(features),
            "feature_counts_inserted": len(feature_counts),
            "tree_path": tree.newick_path if tree else None,
        }
    except RepositoryError as e:
        session.rollback()
        raise ServiceError(str(e)) from e
    finally:
        session.close()


# ==== Genus data ====
def get_genus_data(run_id: int) -> list[dict]:
    """
    Return all genus relative abundances for a run, sorted alphabetically.
    """
    session = SessionLocal()
    try:
        genera = get_genus_for_run(session, run_id)
        return [
            {"genus": g.genus, "relative_abundance": g.relative_abundance}
            for g in genera
        ]
    except RepositoryError as e:
        raise ServiceError(str(e)) from e
    finally:
        session.close()


def get_is_run_in_genus(run_id: int) -> bool:
    """
    check if there is already a run_id in genus table
    """
    session = SessionLocal()
    try:
        in_table = get_run_exists_genus_table(session=session, run_id=run_id)
        return in_table
    except RepositoryError as e:
        raise ServiceError(str(e)) from e
    finally:
        session.close()


# ==== Feature counts ====
def get_feature_counts(run_id: int) -> list[dict]:
    """
    Return ASV feature counts for a run, each with its taxonomy string.
    """
    session = SessionLocal()
    try:
        counts = get_feature_counts_for_run(session, run_id)
        return [
            {
                "feature_id": fc.feature_id,
                "abundance": fc.abundance,
                # fc.feature is the related Feature row — access taxonomy via relationship
                "taxonomy": fc.feature.taxonomy if fc.feature else None,
            }
            for fc in counts
        ]
    except RepositoryError as e:
        raise ServiceError(str(e)) from e
    finally:
        session.close()

    
def get_run_feature_ids(run_id: int) -> list:
    """
    Return feature ids that are associated with a run
    """
    session = SessionLocal()
    try:
        feats = list_features_for_run(session=session, run_id=run_id)
        feat_ids = [feat['feature_id'] for feat in feats]
        return feat_ids
    except RepositoryError as e:
        raise ServiceError(str(e)) from e
    finally:
        session.close()

def get_is_run_in_feature(run_id: int) -> bool:
    """
    check if there is already a run_id in feature table
    """
    session = SessionLocal()
    try:
        in_table = get_run_exists_feature_table(session=session, run_id=run_id)
        return in_table
    except RepositoryError as e:
        raise ServiceError(str(e)) from e
    finally:
        session.close()

def get_is_run_in_feature_count(run_id: int) -> bool:
    """
    check if there is already a run_id in feature count table
    """
    session = SessionLocal()
    try:
        in_table = get_run_exists_feature_count_table(session=session, run_id=run_id)
        return in_table
    except RepositoryError as e:
        raise ServiceError(str(e)) from e
    finally:
        session.close()

# ==== Tree ====
def get_tree(run_id: int) -> dict | None:
    """
    Return the phylogenetic tree path for a run, or None if not yet uploaded.
    """
    session = SessionLocal()
    try:
        tree = get_tree_for_run(session, run_id)
        if tree is None:
            return None
        return {
            "tree_id": tree.tree_id,
            "run_id": tree.run_id,
            "newick_path": tree.newick_path,
            "created_at": tree.created_at.isoformat(),
        }
    except RepositoryError as e:
        raise ServiceError(str(e)) from e
    finally:
        session.close()


# ==== Alpha diversity ====
def store_alpha_diversities(run_id: int, metrics: dict[str, float]) -> list[dict]:
    """
    Store one or more alpha diversity metrics for a run.
    metrics: {"shannon": 2.45, "simpson": 0.88, ...}
    """
    session = SessionLocal()
    try:
        run = get_run(session, run_id)
        rows = []
        for metric, value in metrics.items():
            alpha = create_alpha_diversity(session, run=run, metric=metric, value=value)
            rows.append({"run_id": run_id, "metric": alpha.metric, "value": alpha.value})
        session.commit()
        return rows
    except RepositoryError as e:
        session.rollback()
        raise ServiceError(str(e)) from e
    finally:
        session.close()


def get_alpha_diversities(run_id: int) -> list[dict]:
    """
    Return all stored alpha diversity metrics for a run.
    """
    session = SessionLocal()
    try:
        alphas = get_alpha_diversity_for_run(session, run_id)
        return [{"metric": a.metric, "value": a.value} for a in alphas]
    except RepositoryError as e:
        raise ServiceError(str(e)) from e
    finally:
        session.close()


# ==== Beta diversity ====
def store_beta_diversity(
        run_id_1: int,
        run_id_2: int,
        metric: str,
        value: float,
) -> dict:
    """
    Store a single pairwise beta diversity result between two runs.
    Raises ServiceError if either run does not exist or run_id_1 == run_id_2.
    """
    session = SessionLocal()
    try:
        r1 = get_run(session, run_id_1)
        r2 = get_run(session, run_id_2)
        beta = repo_create_beta_diversity(session, run_1=r1, run_2=r2, metric=metric, value=value)
        session.commit()
        return {
            "run_id_1": beta.run_id_1,
            "run_id_2": beta.run_id_2,
            "metric": beta.metric,
            "value": beta.value,
        }
    except RepositoryError as e:
        session.rollback()
        raise ServiceError(str(e)) from e
    finally:
        session.close()


def get_beta_diversity_matrix(project_id: int, metric: str) -> list[dict]:
    """
    Return all pairwise beta diversity values for a project as a flat list.

    Queries only the upper triangle of the matrix (run_id_1 < run_id_2)
    to avoid duplicate pairs.
    Returns: [{"run_id_1": 1, "run_id_2": 2, "metric": "bray_curtis", "value": 0.32}, ...]
    """
    session = SessionLocal()
    try:
        runs = list_runs_for_project(session, project_id)
        results = []
        for i, r1 in enumerate(runs):
            for r2 in runs[i + 1:]:  # upper triangle only — avoids (R1,R2) and (R2,R1) duplicates
                # Normalize order to match how the row was stored (lower ID first)
                id_a, id_b = sorted([r1.run_id, r2.run_id])
                betas = get_beta_diversity(session, id_a, id_b, metric=metric)
                for b in betas:
                    results.append({
                        "run_id_1": b.run_id_1,
                        "run_id_2": b.run_id_2,
                        "metric": b.metric,
                        "value": b.value,
                    })
        return results
    except RepositoryError as e:
        raise ServiceError(str(e)) from e
    finally:
        session.close()


# ==== AD Risk prediction ====
def compute_risk(
        run_id: int,
        model_fn: Callable[[dict], dict],
) -> dict:
    """
    Run the ML model against a run's genus data and return the risk assessment.

    model_fn receives {genus_name: relative_abundance} and must return a dict with:
      - risk_probability: float (0-100)
      - confidence:       float (0-100)
      - biomarkers:       dict[str, float]  key taxa driving the prediction (optional)

    Results are not persisted — add a RiskAssessment table later if needed.
    Raises ServiceError if the run has no genus data yet.
    """
    session = SessionLocal()
    try:
        run = get_run(session, run_id)
        genera = get_genus_for_run(session, run_id)
        if not genera:
            raise ServiceError(
                f"No genus data found for run_id={run_id}. "
                "Ingest run data before computing risk."
            )

        # Build the taxa dict the model expects: {genus_name: relative_abundance}
        taxa = {g.genus: g.relative_abundance for g in genera}

        result = model_fn(taxa)
        risk_probability = float(result["risk_probability"])
        risk_label = _risk_label(risk_probability)
        confidence = float(result.get("confidence", 0.0))

        update_run_risk(session, run=run, risk_score=risk_probability, risk_label=risk_label, confidence=confidence)
        session.commit()

        return {
            "run_id": run_id,
            "risk_probability": risk_probability,
            "risk_label": risk_label,
            "confidence": confidence,
            "biomarkers": result.get("biomarkers", {}),
        }
    except RepositoryError as e:
        session.rollback()
        raise ServiceError(str(e)) from e
    finally:
        session.close()


# ==== User project history ====
def list_user_projects(user_id: int) -> list[dict]:
    """
    Return all projects for a user with run summaries, newest first.
    Each project dict includes a 'runs' list with risk scores.
    """
    session = SessionLocal()
    try:
        projects = list_projects_for_user(session, user_id)
        result = []
        for p in projects:
            runs = list_runs_for_project(session, p.project_id)
            result.append({
                "project_id": p.project_id,
                "name": p.name,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "run_count": len(runs),
                "runs": [
                    {
                        "run_id":             r.run_id,
                        "srr_accession":      r.srr_accession,
                        "bio_proj_accession": r.bio_proj_accession,
                        "risk_label":         r.risk_label,
                        "risk_score":         r.risk_score,
                        "created_at":         r.created_at.isoformat() if r.created_at else None,
                    }
                    for r in runs
                ],
            })
        return result
    except RepositoryError as e:
        raise ServiceError(str(e)) from e
    finally:
        session.close()


def save_ncbi_project(
        user_id: int,
        bio_proj_accession: str,
        title: str,
        runs: list[dict],   # [{"accession": str, "layout": str}, ...]
) -> dict:
    """
    Persist an NCBI fetch result to the database.

    Creates a new project under the user and inserts run rows for each SRR
    accession, skipping any that are already in the database (unique constraint
    on srr_accession).  Safe to call multiple times for the same project.
    """
    session = SessionLocal()
    try:
        user = get_user(session, user_id)
        project = repo_create_project(session, user=user, name=title or bio_proj_accession)
        session.flush()

        for run in runs:
            srr = run.get("accession", "").strip()
            if not srr:
                continue
            # Skip runs already registered (unique constraint on srr_accession)
            try:
                get_run_by_srr(session, srr)
                continue          # already exists — skip
            except NotFoundError:
                pass              # not found — safe to insert

            repo_create_run(
                session,
                project=project,
                source="ncbi",
                srr_accession=srr,
                bio_proj_accession=bio_proj_accession,
                library_layout=run.get("layout"),
            )

        session.commit()
        return {
            "project_id": project.project_id,
            "user_id":    project.user_id,
            "name":       project.name,
            "created_at": project.created_at.isoformat() if project.created_at else None,
        }
    except RepositoryError as e:
        session.rollback()
        raise ServiceError(str(e)) from e
    finally:
        session.close()


def save_local_project(user_id: int, name: str) -> dict:
    """
    Create a local (non-NCBI) project for a user and return it as a dict.
    Used when a user creates a project from the Profile page.
    """
    session = SessionLocal()
    try:
        user = get_user(session, user_id)
        project = repo_create_project(session, user=user, name=name)
        session.commit()
        return {
            "project_id": project.project_id,
            "user_id":    project.user_id,
            "name":       project.name,
            "created_at": project.created_at.isoformat() if project.created_at else None,
        }
    except RepositoryError as e:
        session.rollback()
        raise ServiceError(str(e)) from e
    finally:
        session.close()


def save_analysis_to_project(db_project_id: int, state) -> None:
    """
    Persist analysis results from an AppState into the database.

    For each run in state.runs:
      - Finds or creates the matching DB run row (matched by accession string)
      - Saves genus abundances
      - Saves risk score

    Safe to call multiple times — genus rows are re-inserted each time
    (old rows are deleted first if they exist).
    """
    session = SessionLocal()
    try:
        project = get_project(session, db_project_id)
        existing_runs = list_runs_for_project(session, db_project_id)
        existing_by_acc = {(r.srr_accession or ""): r for r in existing_runs}

        risk_result   = state.risk_result or {}
        risk_score    = float(risk_result.get("predicted_pct", 0.0))
        risk_label    = (risk_result.get("risk_level") or "").capitalize() or _risk_label(risk_score)
        confidence    = float(risk_result.get("confidence_pct", 0.0))

        for run_state in state.runs:
            acc = run_state.accession or run_state.label

            if acc in existing_by_acc:
                run = existing_by_acc[acc]
            else:
                run = repo_create_run(
                    session,
                    project=project,
                    source="upload",
                    srr_accession=acc,
                    bio_proj_accession=(
                        state.bioproject_id
                        if state.bioproject_id and state.bioproject_id != "LOCAL"
                        else None
                    ),
                    library_layout=run_state.layout,
                )
                session.flush()

            # Delete old genus rows before re-inserting
            from src.db.db_models import Genus
            session.query(Genus).filter(Genus.run_id == run.run_id).delete()
            session.flush()

            genera = state.genus_abundances.get(run_state.label, [])
            if genera:
                create_genus_bulk(session, run=run, genus_abundances=dict(genera))

            if risk_result:
                update_run_risk(
                    session, run=run,
                    risk_score=risk_score,
                    risk_label=risk_label,
                    confidence=confidence,
                )

        session.commit()
    except RepositoryError as e:
        session.rollback()
        raise ServiceError(str(e)) from e
    finally:
        session.close()


def get_project_full_state(project_id: int) -> dict:
    """
    Return all saved analysis data for a project so the GUI can rebuild AppState.

    Returns a dict with:
      project_id, name, bioproject_id,
      runs: list of {run_id, accession, layout, risk_score, risk_label, genus_abundances}
    """
    session = SessionLocal()
    try:
        project = get_project(session, project_id)
        runs    = list_runs_for_project(session, project_id)

        bioproject_id = None
        run_data = []
        for run in runs:
            if run.bio_proj_accession and not bioproject_id:
                bioproject_id = run.bio_proj_accession
            genera = get_genus_for_run(session, run.run_id)
            run_data.append({
                "run_id":          run.run_id,
                "accession":       run.srr_accession or run.bio_proj_accession or f"R{run.run_id}",
                "layout":          run.library_layout or "PAIRED",
                "risk_score":      run.risk_score,
                "risk_label":      run.risk_label,
                "genus_abundances": [(g.genus, g.relative_abundance) for g in genera],
            })

        return {
            "project_id":   project.project_id,
            "name":         project.name,
            "bioproject_id": bioproject_id,
            "runs":         run_data,
        }
    except RepositoryError as e:
        raise ServiceError(str(e)) from e
    finally:
        session.close()


def delete_project(project_id: int) -> None:
    """
    Permanently delete a project and all its runs, genus data, features,
    trees, and diversity records (cascade delete via ORM).
    """
    from src.db.db_models import Project
    session = SessionLocal()
    try:
        proj = session.get(Project, project_id)
        if proj is None:
            return   # already gone — treat as success
        session.delete(proj)
        session.commit()
    except Exception as e:
        session.rollback()
        raise ServiceError(str(e)) from e
    finally:
        session.close()


# ==== Private helpers ====
def _risk_label(probability: float) -> str:
    """Translate a risk percentage into a human-readable label."""
    if probability < 33.0:
        return "Low"
    if probability < 66.0:
        return "Moderate"
    return "High"
