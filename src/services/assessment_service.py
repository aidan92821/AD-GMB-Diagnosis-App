# src/services/assessment_service.py
#
# The service layer sits between the UI and the database.
# It owns the session lifecycle (open -> commit/rollback -> close) so the UI
# never touches SQLAlchemy directly. Every function returns a plain Python dict.
from __future__ import annotations

import json
import math
from typing import Callable

# Import only what we need from the repository layer.
# The repository handles raw DB operations; the service calls them and wraps errors.
from src.db.repository import (
    get_project, create_microbiome_data, create_risk_assessment,
    create_simulation_run, get_subject, list_projects_for_subject,
    get_latest_microbiome, get_latest_cognitive,
    get_latest_mri, get_latest_risk_assessment, RepositoryError,
)
from src.db.database import SessionLocal


# RepositoryError (from repository.py) is a DB-level error.
# We catch it and re-raise as ServiceError so the UI only needs one error type.
class ServiceError(Exception):
    """Raised when a service operation fails (wraps RepositoryError)."""


# ── Private helpers ────────────────────────────────────────────────────────────

def _compute_shannon(taxa: dict[str, float]) -> float:
      """Compute Shannon diversity index: H = -sum(p * ln(p)) for all p > 0."""
      # Higher result = more diverse microbiome. Skips any taxa with proportion 0.
      return -sum(p * math.log(p) for p in taxa.values() if p > 0)


def _risk_label(probability: float) -> str:
      """Translate a risk percentage into a human-readable label."""
      if probability < 33.0:
           return "Low"
      if probability < 66.0:
           return "Moderate"
      return "High"


# ── Public service functions ───────────────────────────────────────────────────

def store_microbiome_upload(
      project_id: int,
      file_path: str | None,
      taxa: dict[str, float],
      alpha_diversity: float | None = None,
      shannon_index: float | None = None,
) -> dict:
      """
      Persist a parsed microbiome file upload to the database.

      Automatically computes shannon_index and alpha_diversity from the taxa
      dict if they are not provided by the caller.
      Raises ServiceError if the project does not exist.
      """
      # Open a new DB session for this request
      session = SessionLocal()
      try:
            # Verify the project exists — raises RepositoryError (caught below) if not
            project = get_project(session, project_id)

            # Auto-compute stats if the caller didn't provide them
            if shannon_index is None:
                  shannon_index = _compute_shannon(taxa)
            if alpha_diversity is None:
                  alpha_diversity = float(len(taxa))  # count of distinct taxa

            # Write the microbiome row to the DB (session.flush happens inside)
            mb = create_microbiome_data(
                  session,
                  project=project,
                  raw_file_path=file_path,
                  taxa=taxa,
                  alpha_diversity=alpha_diversity,
                  shannon_index=shannon_index,
            )
            # Finalize the write — without commit() nothing is saved to disk
            session.commit()

            # Return a plain dict (no SQLAlchemy objects) so the UI can use it freely
            return {
                  "microbiome_id": mb.microbiome_id,
                  "project_id": mb.project_id,
                  "raw_file_path": mb.raw_file_path,
                  "taxa": taxa,
                  "alpha_diversity": mb.alpha_diversity,
                  "shannon_index": mb.shannon_index,
                  "created_at": mb.created_at.isoformat(),  # convert datetime to string
            }
      except RepositoryError as e:
            session.rollback()  # undo any partial writes on error
            raise ServiceError(str(e)) from e
      finally:
            session.close()  # always close, whether success or error


def get_subject_profile(subject_id: int) -> dict:
      """
      Return a subject's full profile as a nested dict.

      Includes demographics and a list of all their projects, each with
      their latest microbiome, cognitive, MRI, and risk assessment records.
      Raises ServiceError if the subject does not exist.
      """
      session = SessionLocal()
      try:
            # Fetch the subject row. raises RepositoryError if subject_id doesn't exist
            subject = get_subject(session, subject_id)
            # Get all projects belonging to this subject (ordered newest first)
            projects_orm = list_projects_for_subject(session, subject_id)

            projects_out = []
            for proj in projects_orm:
                  # For each project, fetch the most recent record of each data type.
                  # These return None if no data has been uploaded yet for that type.
                  mb  = get_latest_microbiome(session, proj.project_id)
                  cog = get_latest_cognitive(session, proj.project_id)
                  mri = get_latest_mri(session, proj.project_id)
                  ra  = get_latest_risk_assessment(session, proj.project_id)

                  # "if mb else None" pattern: build a small summary dict only if the
                  # record exists, otherwise set the field to None
                  projects_out.append({
                        "project_id": proj.project_id,
                        "name": proj.name,
                        "created_at": proj.created_at.isoformat() if proj.created_at else None,
                        "notes": proj.notes,
                        "latest_microbiome": {"microbiome_id": mb.microbiome_id, "shannon_index": mb.shannon_index} if mb else None,
                        "latest_cognitive":  {"cognitive_id": cog.cognitive_id, "mmse_score": cog.mmse_score} if cog else None,
                        "latest_mri":        {"mri_id": mri.mri_id, "image_path": mri.image_path} if mri else None,
                        "latest_risk":       {"risk_id": ra.risk_id, "risk_probability": ra.risk_probability, "risk_label": ra.risk_label} if ra else None,
                  })

            return {
                  "subject_id": subject.subject_id,
                  "age": subject.age,
                  "sex": subject.sex,
                  "apoe_genotype": subject.apoe_genotype,
                  "polygenic_risk_score": subject.polygenic_risk_score,
                  "projects": projects_out,
            }
      except RepositoryError as e:
            # No rollback needed here since this function only reads, never writes
            raise ServiceError(str(e)) from e
      finally:
            session.close()


def compute_and_store_risk(
      project_id: int,
      model_fn: Callable[[dict], float],  # a function that takes taxa dict -> returns risk %
      model_version: str = "stub-v1",     # label stored with the result so we know which model ran
) -> dict:
      """
      Run model_fn against the project's latest microbiome data,
      persist the RiskAssessment, and return it as a dict.

      model_fn receives the taxa dict and must return a risk percentage (0-100).
      Cognitive and MRI data are included automatically if they exist.
      Raises ServiceError if the project has no microbiome data yet.
      """
      session = SessionLocal()
      try:
            project  = get_project(session, project_id)

            # Risk requires microbiome data. guard clause raises early if none uploaded yet
            microbiome = get_latest_microbiome(session, project_id)
            if microbiome is None:
                  raise ServiceError(
                  f"No microbiome data found for project_id={project_id}. "
                  "Upload microbiome data before computing risk."
            )

            # Cognitive and MRI are optional — pass them in if they exist, None otherwise
            cognitive = get_latest_cognitive(session, project_id)  # may be None
            mri       = get_latest_mri(session, project_id)        # may be None

            # taxa_json is stored as a raw text string in the DB — decode it back to a dict
            taxa = json.loads(microbiome.taxa_json)
            # Call the injected ML model. float() ensures we always get a float, not an int.
            risk_probability = float(model_fn(taxa))
            # Convert numeric probability to a human-readable label (Low / Moderate / High)
            label = _risk_label(risk_probability)

            # Persist the risk assessment row, linking it to microbiome (and optionally cog/mri)
            ra = create_risk_assessment(
                  session,
                  project=project,
                  microbiome=microbiome,
                  cognitive=cognitive,
                  mri=mri,
                  risk_probability=risk_probability,
                  risk_label=label,
                  model_version=model_version,
            )
            session.commit()

            return {
                  "risk_id": ra.risk_id,
                  "project_id": ra.project_id,
                  "risk_probability": ra.risk_probability,
                  "risk_label": ra.risk_label,
                  "model_version": ra.model_version,
                  "microbiome_id": ra.microbiome_id,
                  "cognitive_id": ra.cognitive_id,  # None if no cognitive data was available
                  "mri_id": ra.mri_id,              # None if no MRI data was available
                  "created_at": ra.created_at.isoformat(),
            }
      except RepositoryError as e:
            session.rollback()
            raise ServiceError(str(e)) from e
      finally:
            session.close()

def run_and_store_simulation(
      project_id: int,
      diet_parameters: dict,                       # keys: probiotic, antibiotics, fiber, processed_foods
      model_fn: Callable[[dict, dict], float],     # takes (updated_taxa, diet_parameters) → risk %
      model_version: str = "stub-v1",
) -> dict:
      """
      Apply diet intervention parameters to the latest microbiome, compute a
      new risk score, and persist a SimulationRun linking base and result.
      Raises ServiceError if the project has no microbiome data yet.
      """
      session = SessionLocal()
      try:
            project = get_project(session, project_id)
            # The "before diet" microbiome required as the starting point
            base_microbiome = get_latest_microbiome(session, project_id)
            if base_microbiome is None:
                  raise ServiceError(
                  f"No microbiome data found for project_id={project_id}. "
                  "Upload microbiome data before running a simulation."
                  )

            # Decode taxa from JSON string back to a Python dict (stored as text in DB)
            base_taxa = json.loads(base_microbiome.taxa_json)

            # Compute a single multiplier for the net diet effect on microbiom diversity.
            # Coefficients are stubs — not clinically validated, replace with model-derived values later.
            # Positive terms increase diversity, negative terms decrease it.
            diversity_delta = (
                  diet_parameters.get("probiotic", 0)         * 0.02   # probiotics boost diversity
                  + diet_parameters.get("fiber", 0)           * 0.015  # fiber feeds beneficial bacteria
                  - diet_parameters.get("antibiotics", 0)     * 0.025  # antibiotics kill bacteria (strongest effect)
                  - diet_parameters.get("processed_foods", 0) * 0.01   # processed foods mildly reduce diversity
            )

            # Scale each taxon by the delta. max(0.001) prevents any taxon from reaching zero.
            scaled = {k: max(0.001, v * (1.0 + diversity_delta)) for k, v in base_taxa.items()}
            # Renormalize so all proportions still sum to 1.0
            total = sum(scaled.values())
            updated_taxa = {k: round(v / total, 6) for k, v in scaled.items()}
            # Recompute Shannon index for the updated microbiome
            new_shannon = _compute_shannon(updated_taxa)

            # Save the simulated "after diet" microbiome as a new DB row (not a real upload, so raw_file_path=None)
            resulting_microbiome = create_microbiome_data(
                  session,
                  project=project,
                  raw_file_path=None,
                  taxa=updated_taxa,
                  alpha_diversity=float(len(updated_taxa)),
                  shannon_index=new_shannon,
            )

            # Run the ML model on the post-diet taxa to get the new predicted risk
            new_risk_probability = float(model_fn(updated_taxa, diet_parameters))
            new_label            = _risk_label(new_risk_probability)

            # Store the predicted risk for the post-diet microbiome
            resulting_risk = create_risk_assessment(
                  session,
                  project=project,
                  microbiome=resulting_microbiome,
                  risk_probability=new_risk_probability,
                  risk_label=new_label,
                  model_version=model_version,
            )

            # Link the before/after microbiomes together in a SimulationRun record
            sim = create_simulation_run(
                  session,
                  base_microbiome=base_microbiome,
                  resulting_microbiome=resulting_microbiome,
                  diet_parameters=diet_parameters,
                  updated_taxa=updated_taxa,
                  resulting_risk=resulting_risk,
            )
            session.commit()

            return {
                  "simulation_id": sim.simulation_id,
                  "base_microbiome_id": sim.base_microbiome_id,           # the "before" microbiome
                  "resulting_microbiome_id": sim.resulting_microbiome_id, # the simulated "after" microbiome
                  "resulting_risk_probability": new_risk_probability,
                  "resulting_risk_label": new_label,
                  "diet_parameters": diet_parameters,
                  "updated_taxa": updated_taxa,
                  "updated_shannon_index": new_shannon,
                  "created_at": sim.created_at.isoformat(),
            }
      except RepositoryError as e:
            session.rollback()
            raise ServiceError(str(e)) from e
      finally:
            session.close()
