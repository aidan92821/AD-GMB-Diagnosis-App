# scripts/test_service_step1.py
# Smoke test for store_microbiome_upload
#
# Run with:  python3 -m scripts.test_service_step1

from src.db.database import SessionLocal, engine
from src.db.db_models import Base
from src.db.repository import create_subject, create_project
from src.services.assessment_service import store_microbiome_upload, get_subject_profile, compute_and_store_risk, run_and_store_simulation, ServiceError

# Create all tables if they don't exist yet
Base.metadata.create_all(engine)

# ── Setup: create a Subject and Project directly via the repository ──
session = SessionLocal()
subject = create_subject(session, age=72, sex="F")
project = create_project(session, subject=subject, name="Test Project")
session.commit()
project_id = project.project_id
subject_id = subject.subject_id
session.close()

# ── Test 1: basic call with auto-computed diversity stats ──
sample_taxa = {"Firmicutes": 0.35, "Bacteroides": 0.40, "Actinobacteria": 0.25}

result = store_microbiome_upload(
    project_id=project_id,
    file_path="data/raw/sample.csv",
    taxa=sample_taxa,
)

assert "microbiome_id" in result,   "FAIL: missing microbiome_id"
assert result["project_id"] == project_id, "FAIL: wrong project_id"
assert result["taxa"] == sample_taxa, "FAIL: taxa mismatch"
assert result["shannon_index"] is not None, "FAIL: shannon_index not computed"
assert result["alpha_diversity"] == 3.0, "FAIL: alpha_diversity should be 3 (3 taxa)"
assert "created_at" in result, "FAIL: missing created_at"
print(f"Test 1 PASS — microbiome_id={result['microbiome_id']}, shannon={result['shannon_index']:.4f}")

# ── Test 2: ServiceError raised for a non-existent project ──
try:
    store_microbiome_upload(project_id=99999, file_path=None, taxa=sample_taxa)
    print("Test 2 FAIL — should have raised ServiceError")
except ServiceError as e:
    print(f"Test 2 PASS — ServiceError caught: {e}")

# ── Test 3: get_subject_profile returns correct nested structure ──
# subject_id was saved during setup above.
# The project already has one microbiome record from Test 1.
profile = get_subject_profile(subject_id)

assert profile["subject_id"] == subject_id,           "FAIL: wrong subject_id"
assert profile["age"] == 72,                           "FAIL: wrong age"
assert profile["sex"] == "F",                          "FAIL: wrong sex"
assert isinstance(profile["projects"], list),          "FAIL: projects should be a list"
assert len(profile["projects"]) >= 1,                  "FAIL: should have at least one project"

first_project = profile["projects"][0]
assert "project_id" in first_project,                  "FAIL: missing project_id in project"
assert first_project["latest_microbiome"] is not None, "FAIL: should have a microbiome (we uploaded one)"
assert "shannon_index" in first_project["latest_microbiome"], "FAIL: missing shannon_index"
assert first_project["latest_cognitive"] is None,      "FAIL: no cognitive data uploaded yet, should be None"
assert first_project["latest_risk"] is None,           "FAIL: no risk computed yet, should be None"
print(f"Test 3 PASS — subject_id={profile['subject_id']}, projects={len(profile['projects'])}, "
      f"microbiome_id={first_project['latest_microbiome']['microbiome_id']}")

# ── Test 4: compute_and_store_risk returns correct risk assessment ──
# Use a dummy model that always returns 42.0 so the result is predictable.
dummy_model = lambda taxa: 42.0

risk = compute_and_store_risk(project_id=project_id, model_fn=dummy_model)

assert "risk_id"          in risk,              "FAIL: missing risk_id"
assert risk["project_id"] == project_id,        "FAIL: wrong project_id"
assert risk["risk_probability"] == 42.0,        "FAIL: wrong risk_probability"
assert risk["risk_label"]       == "Moderate",  "FAIL: 42% should be Moderate"
assert risk["microbiome_id"]    is not None,    "FAIL: missing microbiome_id"
assert risk["cognitive_id"]     is None,        "FAIL: no cognitive data, should be None"
assert risk["mri_id"]           is None,        "FAIL: no MRI data, should be None"
print(f"Test 4 PASS — risk_id={risk['risk_id']}, probability={risk['risk_probability']}%, label={risk['risk_label']}")

# ── Test 4b: ServiceError raised when project has no microbiome data ──
# Create a fresh project with no uploads to test the guard clause.
session = SessionLocal()
empty_subject = create_subject(session, age=65, sex="M")
empty_project = create_project(session, subject=empty_subject, name="Empty Project")
session.commit()
empty_project_id = empty_project.project_id
session.close()

try:
    compute_and_store_risk(project_id=empty_project_id, model_fn=dummy_model)
    print("Test 4b FAIL — should have raised ServiceError")
except ServiceError as e:
    print(f"Test 4b PASS — ServiceError caught: {e}")

# ── Test 5: run_and_store_simulation returns correct simulation result ──
# The sim model takes two args: (taxa, diet_parameters) -> float
sim_model = lambda _, __: 38.0

diet = {"probiotic": 5, "antibiotics": 0, "fiber": 3, "processed_foods": -2}

sim = run_and_store_simulation(
    project_id=project_id,
    diet_parameters=diet,
    model_fn=sim_model,
)

assert "simulation_id"             in sim,          "FAIL: missing simulation_id"
assert "base_microbiome_id"        in sim,          "FAIL: missing base_microbiome_id"
assert "resulting_microbiome_id"   in sim,          "FAIL: missing resulting_microbiome_id"
assert sim["base_microbiome_id"] != sim["resulting_microbiome_id"], "FAIL: base and resulting must differ"
assert sim["resulting_risk_probability"] == 38.0,   "FAIL: wrong risk probability"
assert sim["resulting_risk_label"]       == "Moderate", "FAIL: 38% should be Moderate"
assert sim["diet_parameters"] == diet,              "FAIL: diet_parameters mismatch"
assert "updated_taxa"          in sim,              "FAIL: missing updated_taxa"
assert "updated_shannon_index" in sim,              "FAIL: missing updated_shannon_index"
print(f"Test 5 PASS — simulation_id={sim['simulation_id']}, "
      f"base_mb={sim['base_microbiome_id']} -> resulting_mb={sim['resulting_microbiome_id']}, "
      f"risk={sim['resulting_risk_probability']}% ({sim['resulting_risk_label']})")
