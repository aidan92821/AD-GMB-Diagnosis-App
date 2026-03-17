# src/db/repository.py
#
# Repository layer
# all raw database operations live here
# Functions receive a SQLAlchemy Session and return ORM objects
# The service layer own the session lifecycle (flush/commit/rollback/close)
from __future__ import annotations

from sqlalchemy.orm import Session
from sqlalchemy import select, desc

from src.db.db_models import (
    User, Project, Run, Genus, Feature, FeatureCount,
    Tree, AlphaDiversity, BetaDiversity,
)


# ==== Custom errors ====
class RepositoryError(Exception):
    """Base class for repository-layer errors."""

class NotFoundError(RepositoryError):
    """Raised when a requested row does not exist."""

class IntegrityError(RepositoryError):
    """Raised when an operation would violate app-level integrity rules."""


# ==== USER ====
def create_user(session: Session, *, username: str) -> User:
    user = User(username=username)  # build python object in memory
    session.add(user)               # stage it
    session.flush()                 # send SQL to DB without committing for immediate use (can be rolledback)
    return user                     # return the object


def get_user(session: Session, user_id: int) -> User:
    stmt = select(User).where(User.user_id == user_id)  # build SELECT query
    user = session.execute(stmt).scalar_one_or_none()   # run query and get one row or none (If multiple returned, shouldn't happen, error would raise)
    if user is None:
        raise NotFoundError(f"User not found: user_id={user_id}")   # if none send error
    return user


def get_user_by_username(session: Session, username: str) -> User:
    stmt = select(User).where(User.username == username)
    user = session.execute(stmt).scalar_one_or_none()
    if user is None:
        raise NotFoundError(f"User not found: username={username!r}")
    return user


# ==== PROJECT ====
def create_project(session: Session, *, user: User, name: str) -> Project:
    project = Project(user=user, name=name)
    session.add(project)
    session.flush()
    return project


def get_project(session: Session, project_id: int) -> Project:
    stmt = select(Project).where(Project.project_id == project_id)
    project = session.execute(stmt).scalar_one_or_none()
    if project is None:
        raise NotFoundError(f"Project not found: project_id={project_id}")
    return project


def list_projects_for_user(session: Session, user_id: int) -> list[Project]:
    """Return all projects for a user, newest first."""
    stmt = (
        select(Project)
        .where(Project.user_id == user_id)
        .order_by(desc(Project.created_at), desc(Project.project_id))   # if created_at tie, desc by id
    )
    return list(session.execute(stmt).scalars().all())  # Return all matching rows


# ==== RUN ====
def create_run(
        session: Session,
        *,
        project: Project,
        source: str,    # "upload" || "ncbi"
        bio_proj_accession: str | None = None,
        library_layout: str | None = None,
) -> Run:
    run = Run(
        project=project,
        source=source,
        bio_proj_accession=bio_proj_accession,
        library_layout=library_layout,
    )
    session.add(run)
    session.flush()
    return run


def get_run(session: Session, run_id: int) -> Run:
    stmt = select(Run).where(Run.run_id == run_id)
    run = session.execute(stmt).scalar_one_or_none()
    if run is None:
        raise NotFoundError(f"Run not found: run_id={run_id}")
    return run


def list_runs_for_project(session: Session, project_id: int) -> list[Run]:
    """Return all runs for a project, newest first."""
    stmt = (
        select(Run)
        .where(Run.project_id == project_id)
        .order_by(desc(Run.created_at), desc(Run.run_id))
    )
    return list(session.execute(stmt).scalars().all())


# ==== GENUS ====
def create_genus_bulk(
        session: Session,
        *,
        run: Run,
        genus_abundances: dict[str, float],   # {"Firmicutes": 0.35, ...}
) -> list[Genus]:
    """Insert all genus-level relative abundances for a run at once."""
    rows = []
    for genus_name, abundance in genus_abundances.items():
        row = Genus(run_id=run.run_id, genus=genus_name, relative_abundance=abundance)
        session.add(row)
        rows.append(row)
    session.flush()
    return rows


def get_genus_for_run(session: Session, run_id: int) -> list[Genus]:
    """Return all genus rows for a run, sorted alphabetically by genus name."""
    stmt = (
        select(Genus)
        .where(Genus.run_id == run_id)
        .order_by(Genus.genus)
    )
    return list(session.execute(stmt).scalars().all())


# ==== FEATURE ====
def create_feature(
        session: Session,
        *,
        run: Run,
        feature_id: str,
        sequence: str | None = None,
        taxonomy: str | None = None,
) -> Feature:
    feature = Feature(
        run_id=run.run_id,
        feature_id=feature_id,
        sequence=sequence,
        taxonomy=taxonomy,
    )
    session.add(feature)
    session.flush()
    return feature


def get_feature(session: Session, run_id: int, feature_id: str) -> Feature:
    stmt = select(Feature).where(   # Composit key - pass two conditions to .where() is equivalent to WHERE run_id = ? AND feature_id = ?
        Feature.run_id == run_id,
        Feature.feature_id == feature_id,
    )
    feature = session.execute(stmt).scalar_one_or_none()
    if feature is None:
        raise NotFoundError(f"Feature not found: run_id={run_id}, feature_id={feature_id!r}")
    return feature


def list_features_for_run(session: Session, run_id: int) -> list[Feature]:
    stmt = select(Feature).where(Feature.run_id == run_id)
    return list(session.execute(stmt).scalars().all())


# ==== FEATURE COUNT ====
def create_feature_count_bulk(
        session: Session,
        *,
        run_id: int,
        counts: dict[str, int],   # {feature_id: abundance_count}
) -> list[FeatureCount]:
    """Insert all feature counts for a run at once (from feature-table.tsv)."""
    rows = []
    for feature_id, abundance in counts.items():
        row = FeatureCount(run_id=run_id, feature_id=feature_id, abundance=abundance)
        session.add(row)
        rows.append(row)
    session.flush()
    return rows


def get_feature_counts_for_run(session: Session, run_id: int) -> list[FeatureCount]:
    stmt = select(FeatureCount).where(FeatureCount.run_id == run_id)
    return list(session.execute(stmt).scalars().all())


# ==== TREE ====
def create_tree(session: Session, *, run: Run, newick_path: str) -> Tree:
    tree = Tree(run_id=run.run_id, newick_path=newick_path)
    session.add(tree)
    session.flush()
    return tree


def get_tree_for_run(session: Session, run_id: int) -> Tree | None:
    """Return the most recent tree for a run or None if none exists."""
    stmt = (
        select(Tree)
        .where(Tree.run_id == run_id)
        .order_by(desc(Tree.created_at), desc(Tree.tree_id))
        .limit(1)
    )
    return session.execute(stmt).scalar_one_or_none()


# ==== ALPHA DIVERSITY ====
def create_alpha_diversity(
        session: Session,
        *,
        run: Run,
        metric: str,
        value: float,
) -> AlphaDiversity:
    alpha = AlphaDiversity(run_id=run.run_id, metric=metric, value=value)
    session.add(alpha)
    session.flush()
    return alpha


def get_alpha_diversity_for_run(session: Session, run_id: int) -> list[AlphaDiversity]:
    """Return all alpha diversity metrics for a run."""
    stmt = select(AlphaDiversity).where(AlphaDiversity.run_id == run_id)
    return list(session.execute(stmt).scalars().all())


# ==== BETA DIVERSITY ====
def create_beta_diversity(
        session: Session,
        *,
        run_1: Run,
        run_2: Run,
        metric: str,
        value: float,
) -> BetaDiversity:
    if run_1.run_id == run_2.run_id:
        raise IntegrityError("Cannot compute beta diversity between a run and itself.")
    beta = BetaDiversity(
        run_id_1=run_1.run_id,
        run_id_2=run_2.run_id,
        metric=metric,
        value=value,
    )
    session.add(beta)
    session.flush()
    return beta


def get_beta_diversity(
        session: Session,
        run_id_1: int,
        run_id_2: int,
        metric: str | None = None,
) -> list[BetaDiversity]:
    """Return beta diversity rows for a pair of runs, optionally filtered by metric."""
    stmt = select(BetaDiversity).where(
        BetaDiversity.run_id_1 == run_id_1,
        BetaDiversity.run_id_2 == run_id_2,
    )
    if metric:
        stmt = stmt.where(BetaDiversity.metric == metric)
    return list(session.execute(stmt).scalars().all())
