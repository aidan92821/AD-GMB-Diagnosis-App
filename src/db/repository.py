# src/db/repository.py
from __future__ import annotations

import json

from sqlalchemy.orm import Session
from sqlalchemy import select, desc

# Import ORM models
from src.db.db_models import Subject, Project, CognitiveData, MRIData, MicrobiomeData, RiskAssessment, SimulationRun, BetaDistance

# ---- Custom repo errors ----
class RepositoryError(Exception):
    """Base class for repository-layer errors."""

class NotFoundError(RepositoryError):
    """Raised when a requested row does not exist."""

class IntegrityError(RepositoryError):
    """Raised when the required operation would violate app-level integrity rules."""

# ==== SUBJECT ====
def create_subject(         # REceiving session transaction. hint strings for data types
        session: Session,
        *,                                              # Means everything must be passed as a keyword arg to prevent accidental parameter ordering mistakes
        age: int | None = None,
        sex: str | None = None,
        apoe_genotype: str | None = None,
        polygenic_risk_score: float | None = None,
) -> Subject:                                           # returns subect object
    subject = Subject(                                  # Creates Python object in memory, not sent to db yet
        age = age,
        sex = sex,
        apoe_genotype = apoe_genotype,
        polygenic_risk_score = polygenic_risk_score,
    )

    session.add(subject)    # Pending insert to db
    session.flush()         # generates subject_id. Flush, not commit, because we want id immediately

    return subject

# ==== PROJECT ====
def create_project(
        session: Session,
        *,
        subject: Subject,
        name: str,
        notes: str | None = None,
) -> Project:
    project = Project(
        subject = subject,  # ORM relationship assignment
        name = name,
        notes = notes,
    )

    session.add(project)
    session.flush()         # ensures project.project_id is available now

    return project

# ==== MICROBIOME ====
def create_microbiome_data(
        session: Session,
        *,
        project: Project,
        raw_file_path: str | None = None,
        taxa: dict[str, float],
        alpha_diversity: float | None = None,
        shannon_index: float | None = None,
) -> MicrobiomeData:
    microbiome_data = MicrobiomeData(
        project = project,
        raw_file_path = raw_file_path,
        taxa_json = json.dumps(taxa),
        alpha_diversity =  alpha_diversity,
        shannon_index = shannon_index,
    )

    session.add(microbiome_data)
    session.flush()

    return microbiome_data

# ==== COGNITIVE DATA ====
def create_cognitive_data(
        session: Session,
        *,
        project: Project,
        mmse_score: float | None = None,
        memory_score: float | None = None,
        processing_speed: float | None = None,
        executive_function: float | None = None,
) -> CognitiveData:
    cognitive_data = CognitiveData(
        project=project,
        mmse_score=mmse_score,
        memory_score=memory_score,
        processing_speed=processing_speed,
        executive_function=executive_function,
    )

    session.add(cognitive_data)
    session.flush()

    return cognitive_data

# ==== MRI DATA ====
def create_mri_data(
        session: Session,
        *,
        project: Project,
        image_path: str | None = None,
        extracted_features: dict | None = None,
) -> MRIData:

    mri_data = MRIData(
        project=project,
        image_path=image_path,
        extracted_features_json=json.dumps(extracted_features) if extracted_features else None,
    )

    session.add(mri_data)
    session.flush()

    return mri_data

# ==== RISK ASSESSMENT ====
def create_risk_assessment(
        session: Session,
        *,
        project: Project,
        microbiome: MicrobiomeData,
        cognitive: CognitiveData | None = None,
        mri: MRIData | None = None,
        risk_probability: float,
        risk_label: str | None = None,
        model_version: str | None = None,
        feature_importance: dict | None = None,
) -> RiskAssessment:

    # Integrity checks for mismatch
    if microbiome.project_id != project.project_id:
        raise IntegrityError("Microbiome does not belong to the given project.")

    if cognitive and cognitive.project_id != project.project_id:
        raise IntegrityError("Cognitive Data does not belong to the given project.")

    if mri and mri.project_id != project.project_id:
        raise IntegrityError("MRI Data does not belong to the given project.")

    risk_assessment = RiskAssessment(
        project_id=project.project_id,
        microbiome_id=microbiome.microbiome_id,
        cognitive_id=cognitive.cognitive_id if cognitive else None,
        mri_id=mri.mri_id if mri else None,
        risk_probability=risk_probability,
        risk_label=risk_label,
        model_version=model_version,
        feature_importance_json=json.dumps(feature_importance) if feature_importance else None,
    )

    session.add(risk_assessment)
    session.flush()

    return risk_assessment

# ==== SIMULATION RUN ====
def create_simulation_run(
        session: Session,
        *,
        base_microbiome: MicrobiomeData,
        resulting_microbiome: MicrobiomeData,
        diet_parameters: dict,
        updated_taxa: dict,
        resulting_risk: RiskAssessment | None = None,
) -> SimulationRun:

    # Check if biomes are the same
    if base_microbiome.microbiome_id == resulting_microbiome.microbiome_id:
        raise IntegrityError("Base and resulting microbiomes must differ.")

    simulation_run = SimulationRun(
        base_microbiome_id=base_microbiome.microbiome_id,
        resulting_microbiome_id=resulting_microbiome.microbiome_id,
        resulting_risk_id=resulting_risk.risk_id if resulting_risk else None,
        diet_parameters_json=json.dumps(diet_parameters),
        updated_taxa_json=json.dumps(updated_taxa),
    )

    session.add(simulation_run)
    session.flush()

    return simulation_run

# ==== BETA DISTANCE ====
def create_beta_distance(
        session: Session,
        *,
        project: Project,
        microbiome_a: MicrobiomeData,
        microbiome_b: MicrobiomeData,
        metric: str,
        distance_value: float,
) -> BetaDistance:

    # Integrity checks for mismatch + biome match
    if microbiome_a.project_id != project.project_id:
        raise IntegrityError("Microbiome A does not belong to project.")

    if microbiome_b.project_id != project.project_id:
        raise IntegrityError("Microbiome B does not belong to project.")

    if microbiome_a.microbiome_id == microbiome_b.microbiome_id:
        raise IntegrityError("Cannot compute beta distance on same sample.")

    beta_distance = BetaDistance(
        project_id=project.project_id,
        microbiome_id_a=microbiome_a.microbiome_id,
        microbiome_id_b=microbiome_b.microbiome_id,
        metric=metric,
        distance_value=distance_value,
    )

    session.add(beta_distance)
    session.flush()

    return beta_distance

# ==== GET HELPERS ====
# Gets data tied to specific ID
def get_subject(session: Session, subject_id: int) -> Subject:
     # Build a SELECT query: SELECT * FROM subject WHERE subject_id = :subject_id
    stmt = select(Subject).where(Subject.subject_id == subject_id)
    subject = session.execute(stmt).scalara_one_or_non()
    # Convert "None" into a repository-level error that the UI/ service layer can use
    if subject is None:
        raise NotFoundError(f"Subject not found: subject_id={subject_id}")
    return subject

def get_project(session: Session, project_id: int) -> Project:
    stmt = select(Project).where(Project.project_id == project_id)
    project = session.execute(stmt).scalar_one_or_none()
    if project is None:
        raise NotFoundError(f"Project not found: project_id={project_id}")
    return project


def get_microbiome(session: Session, microbiome_id: int) -> MicrobiomeData:
    stmt = select(MicrobiomeData).where(MicrobiomeData.microbiome_id == microbiome_id)
    mb = session.execute(stmt).scalar_one_or_none()
    if mb is None:
        raise NotFoundError(f"Microbiome Data not found: microbiome_id={microbiome_id}")
    return mb


def get_cognitive_data(session: Session, cognitive_id: int) -> CognitiveData:
    stmt = select(CognitiveData).where(CognitiveData.cognitive_id == cognitive_id)
    cog = session.execute(stmt).scalar_one_or_none()
    if cog is None:
        raise NotFoundError(f"Cognitive Data not found: cognitive_id={cognitive_id}")
    return cog


def get_mri_data(session: Session, mri_id: int) -> MRIData:
    stmt = select(MRIData).where(MRIData.mri_id == mri_id)
    mri = session.execute(stmt).scalar_one_or_none()
    if mri is None:
        raise NotFoundError(f"MRI Data not found: mri_id={mri_id}")
    return mri


def get_risk_assessment(session: Session, risk_id: int) -> RiskAssessment:
    stmt = select(RiskAssessment).where(RiskAssessment.risk_id == risk_id)
    ra = session.execute(stmt).scalar_one_or_none()
    if ra is None:
        raise NotFoundError(f"Risk Assessment not found: risk_id={risk_id}")
    return ra

# ==== LIST HELPERS ====
# Returns list of data related to project
def list_projects_for_subject(session: Session, subject_id: int) -> list[Project]:
    stmt = (
        select(Project)
        .where(Project.subject_id == subject_id)
        .order_by(desc(Project.created_at), desc(Project.project_id))
    )
    return list(session.execute(stmt).scalars().all())

def list_microbiomes_for_project(session: Session, project_id: int) -> list[MicrobiomeData]:
    stmt = (
        select(MicrobiomeData)
        .where(MicrobiomeData.project_id == project_id)
        .order_by(desc(MicrobiomeData.created_at), desc(MicrobiomeData.microbiome_id))
    )
    return list(session.execute(stmt).scalars().all())


def list_cognitive_for_project(session: Session, project_id: int) -> list[CognitiveData]:
    stmt = (
        select(CognitiveData)
        .where(CognitiveData.project_id == project_id)
        .order_by(desc(CognitiveData.created_at), desc(CognitiveData.cognitive_id))
    )
    return list(session.execute(stmt).scalars().all())


def list_mris_for_project(session: Session, project_id: int) -> list[MRIData]:
    stmt = (
        select(MRIData)
        .where(MRIData.project_id == project_id)
        .order_by(desc(MRIData.created_at), desc(MRIData.mri_id))
    )
    return list(session.execute(stmt).scalars().all())


def list_risk_assessments_for_project(session: Session, project_id: int) -> list[RiskAssessment]:
    stmt = (
        select(RiskAssessment)
        .where(RiskAssessment.project_id == project_id)
        .order_by(desc(RiskAssessment.created_at), desc(RiskAssessment.risk_id))
    )
    return list(session.execute(stmt).scalars().all())


def list_simulation_runs(session: Session, project_id: int) -> list[SimulationRun]:
    # SimulationRun references microbiomes. we can list runs for a project by joining base microbiome
    stmt = (
        select(SimulationRun)
        .join(MicrobiomeData, SimulationRun.base_microbiome_id == MicrobiomeData.microbiome_id)
        .where(MicrobiomeData.project_id == project_id)
        .order_by(desc(SimulationRun.created_at), desc(SimulationRun.simulation_id))
    )
    return list(session.execute(stmt).scalars().all())


def list_beta_distances(session: Session, project_id: int, metric: str | None = None) -> list[BetaDistance]:
    stmt = select(BetaDistance).where(BetaDistance.project_id == project_id)
    if metric:
        stmt = stmt.where(BetaDistance.metric == metric)
    stmt = stmt.order_by(desc(BetaDistance.created_at), desc(BetaDistance.distance_id))
    return list(session.execute(stmt).scalars().all())