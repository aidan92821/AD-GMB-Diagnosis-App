# src/db/db_models.py

# ORM models for project
# Each class maps to a table in SQLite database
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, Text,
    CheckConstraint, ForeignKeyConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def utcnow():
    return datetime.now(timezone.utc)


# ==== USER ====
# password hashing and auth logic will be added in sec phase
class User(Base):
    __tablename__ = "user"

    user_id  = Column(Integer, primary_key=True)
    username = Column(String(64), nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    # One user owns many projects. Deleting a user deletes all their projects.
    projects = relationship("Project", back_populates="user", cascade="all, delete-orphan")


# ==== PROJECT ====
# A project groups one or more sequencing runs for one user
class Project(Base):
    __tablename__ = "project"

    project_id = Column(Integer, primary_key=True)
    user_id    = Column(Integer, ForeignKey("user.user_id"), nullable=False)
    name       = Column(String(128), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    user = relationship("User", back_populates="projects")
    # Deleting a project cascades to all its runs and everything under them.
    runs = relationship("Run", back_populates="project", cascade="all, delete-orphan")


# ==== RUN ====
# either uploaded from local files or pulled from NCBI
# source = "upload" || "ncbi"
class Run(Base):
    __tablename__ = "run"

    run_id             = Column(Integer, primary_key=True)
    project_id         = Column(Integer, ForeignKey("project.project_id"), nullable=False)
    srr_accession      = Column(String(64), unique=True, nullable=False)  # e.g. SRR35606904
    bio_proj_accession = Column(String(64))   # e.g. PRJNA123456
    library_layout     = Column(String(32))   # e.g. PAIRED, SINGLE
    source             = Column(String(16), nullable=False)  # "upload" or "ncbi"
    created_at         = Column(DateTime(timezone=True), default=utcnow)
    risk_score         = Column(Float)       # 0-100
    risk_label         = Column(String(32))  # "Low", "Moderate", "High"
    confidence         = Column(Float)       # 0-100

    project           = relationship("Project", back_populates="runs")
    genus_data        = relationship("Genus",         back_populates="run", cascade="all, delete-orphan")
    features          = relationship("Feature",       back_populates="run", cascade="all, delete-orphan")
    trees             = relationship("Tree",          back_populates="run", cascade="all, delete-orphan")
    alpha_diversities = relationship("AlphaDiversity", back_populates="run", cascade="all, delete-orphan")


# ==== GENUS ====
# Genus relative abundance
# Composite PK: (run_id, genus) — one row per genus per run
class Genus(Base):
    __tablename__ = "genus"

    run_id            = Column(Integer, ForeignKey("run.run_id"), primary_key=True, nullable=False)
    genus             = Column(String(128), primary_key=True, nullable=False)
    relative_abundance = Column(Float, nullable=False)

    run = relationship("Run", back_populates="genus_data")

    __table_args__ = (
        # Relative abundance must be between 0 and 1
        CheckConstraint(
            "relative_abundance >= 0 AND relative_abundance <= 1",
            name="ck_genus_abundance_range",
        ),
    )


# ==== FEATURE ====
# An ASV (Amplicon Sequence Variant)
# Populated from .fastq and .tsv files
# Composite PK: (run_id, feature_id) — feature IDs are ASV hashes (unique for each run)
class Feature(Base):
    __tablename__ = "feature"

    run_id     = Column(Integer, ForeignKey("run.run_id"), primary_key=True, nullable=False)
    feature_id = Column(String(64), primary_key=True, nullable=False)  # ASV hash ID
    sequence   = Column(Text)     # DNA sequence from .fastq
    taxonomy   = Column(Text)     # Taxonomic classification string from .tsv

    run    = relationship("Run", back_populates="features")
    counts = relationship("FeatureCount", back_populates="feature", cascade="all, delete-orphan")


# ==== FEATURE COUNT ====
# Raw abundance count for one ASV in one run
# Populated from .tsv (rows = ASVs, columns = run IDs, values = counts)
# Composite PK + composite FK back to Feature: (run_id, feature_id)
class FeatureCount(Base):
    __tablename__ = "feature_count"

    run_id     = Column(Integer, primary_key=True, nullable=False)
    feature_id = Column(String(64), primary_key=True, nullable=False)
    abundance  = Column(Integer, nullable=False)

    # Composite FK — both columns together point to the Feature row
    feature = relationship("Feature", back_populates="counts")

    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "feature_id"],
            ["feature.run_id", "feature.feature_id"],
        ),
    )


# ==== TREE ====
# Phylogenetic tree built from features for a run
# The actual tree is stored as a .nwk file on disk and we store the path here
class Tree(Base):
    __tablename__ = "tree"

    tree_id     = Column(Integer, primary_key=True)
    run_id      = Column(Integer, ForeignKey("run.run_id"), nullable=False)
    newick_path = Column(Text, nullable=False)  # path to .nwk file on disk
    created_at  = Column(DateTime(timezone=True), default=utcnow)

    run = relationship("Run", back_populates="trees")


# ==== ALPHA DIVERSITY ====
# A single diversity metric value for one run
# Composite PK: (run_id, metric) — one row per metric per run
class AlphaDiversity(Base):
    __tablename__ = "alpha_div"

    run_id = Column(Integer, ForeignKey("run.run_id"), primary_key=True, nullable=False)
    metric = Column(String(64), primary_key=True, nullable=False)
    value  = Column(Float, nullable=False)

    run = relationship("Run", back_populates="alpha_diversities")


# ==== BETA DIVERSITY ====
# A pairwise diversity distance between two runs
# Composite PK: (run_id_1, run_id_2, metric) — one row per pair per metric
class BetaDiversity(Base):
    __tablename__ = "beta_div"

    run_id_1 = Column(Integer, ForeignKey("run.run_id"), primary_key=True, nullable=False)
    run_id_2 = Column(Integer, ForeignKey("run.run_id"), primary_key=True, nullable=False)
    metric   = Column(String(64), primary_key=True, nullable=False)
    value    = Column(Float, nullable=False)

    __table_args__ = (
        # A run cannot be compared to itself
        CheckConstraint("run_id_1 != run_id_2", name="ck_beta_diff_runs"),
    )
