# src/db/db_models.py
from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, Text,
    UniqueConstraint, CheckConstraint
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

def utcnow():
    return datetime.now(timezone.utc)

class Subject(Base):
    __tablename__ = "subject"

    subject_id = Column(Integer, primary_key=True)
    age = Column(Integer)
    sex = Column(String(16))
    apoe_genotype = Column(String(16))
    polygenic_risk_score = Column(Float)

    projects = relationship("Project", back_populates="subject", cascade="all, delete-orphan")


class Project(Base):
    __tablename__ = "project"

    project_id = Column(Integer, primary_key=True)
    subject_id = Column(Integer, ForeignKey("subject.subject_id"), nullable=False)

    name = Column(String(128), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow)
    notes = Column(Text)

    subject = relationship("Subject", back_populates="projects")

    microbiome_data = relationship("MicrobiomeData", back_populates="project", cascade="all, delete-orphan")
    cognitive_data  = relationship("CognitiveData", back_populates="project", cascade="all, delete-orphan")
    mri_data        = relationship("MRIData", back_populates="project", cascade="all, delete-orphan")


class CognitiveData(Base):
    __tablename__ = "cognitive_data"

    cognitive_id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("project.project_id"), nullable=False)

    mmse_score = Column(Float)
    memory_score = Column(Float)
    processing_speed = Column(Float)
    executive_function = Column(Float)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    project = relationship("Project", back_populates="cognitive_data")


class MRIData(Base):
    __tablename__ = "mri_data"

    mri_id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("project.project_id"), nullable=False)

    image_path = Column(Text)
    extracted_features_json = Column(Text)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    project = relationship("Project", back_populates="mri_data")


class MicrobiomeData(Base):
    __tablename__ = "microbiome_data"

    microbiome_id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("project.project_id"), nullable=False)

    raw_file_path = Column(Text)
    taxa_json = Column(Text, nullable=False)
    alpha_diversity = Column(Float)
    shannon_index = Column(Float)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    project = relationship("Project", back_populates="microbiome_data")


class RiskAssessment(Base):
    __tablename__ = "risk_assessment"

    risk_id = Column(Integer, primary_key=True)

    project_id = Column(Integer, ForeignKey("project.project_id"), nullable=False)
    microbiome_id = Column(Integer, ForeignKey("microbiome_data.microbiome_id"), nullable=False)
    cognitive_id = Column(Integer, ForeignKey("cognitive_data.cognitive_id"))
    mri_id = Column(Integer, ForeignKey("mri_data.mri_id"))

    risk_probability = Column(Float, nullable=False)
    risk_label = Column(String(32))
    model_version = Column(String(64))
    feature_importance_json = Column(Text)
    created_at = Column(DateTime(timezone=True), default=utcnow)


class SimulationRun(Base):
    __tablename__ = "simulation_run"

    simulation_id = Column(Integer, primary_key=True)

    base_microbiome_id = Column(Integer, ForeignKey("microbiome_data.microbiome_id"), nullable=False)
    resulting_microbiome_id = Column(Integer, ForeignKey("microbiome_data.microbiome_id"), nullable=False)
    resulting_risk_id = Column(Integer, ForeignKey("risk_assessment.risk_id"))

    diet_parameters_json = Column(Text, nullable=False)
    updated_taxa_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        CheckConstraint("base_microbiome_id != resulting_microbiome_id", name="ck_sim_diff_microbiomes"),
    )


class BetaDistance(Base):
    __tablename__ = "beta_distance"

    distance_id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("project.project_id"), nullable=False)

    microbiome_id_a = Column(Integer, ForeignKey("microbiome_data.microbiome_id"), nullable=False)
    microbiome_id_b = Column(Integer, ForeignKey("microbiome_data.microbiome_id"), nullable=False)

    metric = Column(String(32), nullable=False)
    distance_value = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        CheckConstraint("microbiome_id_a != microbiome_id_b", name="ck_beta_diff_samples"),
        UniqueConstraint("project_id", "metric", "microbiome_id_a", "microbiome_id_b",
                         name="uq_beta_pair_metric"),
    )