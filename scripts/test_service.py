# scripts/test_service.py
# Smoke tests for the service layer.
# Run with: python3 -m scripts.test_service

import os
from src.db.database import SessionLocal, engine
from src.db.db_models import Base
from src.db.repository import create_user
from src.services.assessment_service import (
    create_project,
    create_run,
    get_run_id_by_srr,
    get_project_overview,
    ingest_run_data,
    get_genus_data,
    get_feature_counts,
    get_tree,
    store_alpha_diversities,
    get_alpha_diversities,
    store_beta_diversity,
    get_beta_diversity_matrix,
    compute_risk,
    ServiceError,
)

# Fresh DB for every test run
db_path = os.path.join("data", "axisad.db")
if os.path.exists(db_path):
    os.remove(db_path)
Base.metadata.create_all(engine)

# ── Shared setup: create a user directly via repository ─────────────────────────
session = SessionLocal()
user = create_user(session, username="testuser")
session.commit()
user_id = user.user_id
session.close()

# ── Test 1: create_project ───────────────────────────────────────────────────────
proj = create_project(user_id, "Human Gut Study")
assert proj["name"] == "Human Gut Study"
assert "project_id" in proj
project_id = proj["project_id"]
print("Test 1 PASS — create_project")

# ── Test 2: create_run ───────────────────────────────────────────────────────────
run1 = create_run(project_id, source="ncbi", srr_accession="SRR35606904", bio_proj_accession="PRJNA123456", library_layout="PAIRED")
run2 = create_run(project_id, source="upload", srr_accession="SRR99999999", library_layout="SINGLE")
assert run1["srr_accession"] == "SRR35606904"
assert run1["bio_proj_accession"] == "PRJNA123456"
assert run2["source"] == "upload"
run1_id = run1["run_id"]
run2_id = run2["run_id"]
print("Test 2 PASS — create_run")

# ── Test 2b: get_run_id_by_srr ───────────────────────────────────────────────────
looked_up_id = get_run_id_by_srr("SRR35606904")
assert looked_up_id == run1_id
print("Test 2b PASS — get_run_id_by_srr")

# ── Test 3: ingest_run_data ──────────────────────────────────────────────────────
result = ingest_run_data(
    run_id=run1_id,
    genus_rows=[
        ("Bacteroides", 0.35),
        ("Firmicutes", 0.40),
        ("Prevotella", 0.25),
    ],
    features=[
        {"feature_id": "asv001", "sequence": "ATCG", "taxonomy": "k__Bacteria;p__Firmicutes"},
        {"feature_id": "asv002", "sequence": "GCTA", "taxonomy": "k__Bacteria;p__Bacteroidetes"},
    ],
    feature_counts={"asv001": 4821, "asv002": 3204},
    newick_path="data/trees/run1.nwk",
)
assert result["genera_inserted"] == 3
assert result["features_inserted"] == 2
assert result["tree_path"] == "data/trees/run1.nwk"
print("Test 3 PASS — ingest_run_data")

# ── Test 4: get_project_overview ─────────────────────────────────────────────────
overview = get_project_overview(project_id)
assert overview["total_runs"] == 2
assert overview["uploaded_runs"] == 1   # only run1 has data
assert overview["pending_runs"] == 1
assert overview["total_asvs"] == 2
assert overview["total_genera"] == 3
print("Test 4 PASS — get_project_overview")

# ── Test 5: get_genus_data ───────────────────────────────────────────────────────
genera = get_genus_data(run1_id)
assert len(genera) == 3
assert all("genus" in g and "relative_abundance" in g for g in genera)
print("Test 5 PASS — get_genus_data")

# ── Test 6: get_feature_counts ───────────────────────────────────────────────────
counts = get_feature_counts(run1_id)
assert len(counts) == 2
assert sum(c["abundance"] for c in counts) == 8025
assert any(c["taxonomy"] is not None for c in counts)
print("Test 6 PASS — get_feature_counts")

# ── Test 7: get_tree ─────────────────────────────────────────────────────────────
tree = get_tree(run1_id)
assert tree is not None
assert tree["newick_path"] == "data/trees/run1.nwk"
assert get_tree(run2_id) is None   # run2 has no tree
print("Test 7 PASS — get_tree")

# ── Test 8: store and get alpha diversities ──────────────────────────────────────
stored = store_alpha_diversities(run1_id, {"shannon": 2.45, "simpson": 0.88})
assert len(stored) == 2
alphas = get_alpha_diversities(run1_id)
metrics = {a["metric"] for a in alphas}
assert "shannon" in metrics and "simpson" in metrics
print("Test 8 PASS — alpha diversity store and retrieve")

# ── Test 9: store_beta_diversity and get_beta_diversity_matrix ───────────────────
stored_beta = store_beta_diversity(run1_id, run2_id, metric="bray_curtis", value=0.42)
assert abs(stored_beta["value"] - 0.42) < 1e-6

matrix = get_beta_diversity_matrix(project_id, metric="bray_curtis")
assert len(matrix) == 1
assert abs(matrix[0]["value"] - 0.42) < 1e-6
print("Test 9 PASS — store_beta_diversity and get_beta_diversity_matrix")

# ── Test 10: compute_risk ────────────────────────────────────────────────────────
def stub_model(taxa: dict) -> dict:
    return {"risk_probability": 67.0, "confidence": 81.0, "biomarkers": {"Firmicutes": 0.40}}

risk = compute_risk(run1_id, stub_model)
assert risk["risk_probability"] == 67.0
assert risk["risk_label"] == "High"
assert risk["confidence"] == 81.0
assert "Firmicutes" in risk["biomarkers"]
print("Test 10 PASS — compute_risk")

# ── Test 11: ServiceError on missing project ─────────────────────────────────────
try:
    create_project(9999, "Ghost Project")
    assert False, "Should have raised ServiceError"
except ServiceError:
    pass
print("Test 11 PASS — ServiceError on missing user")

# ── Test 12: ServiceError on compute_risk with no data ───────────────────────────
try:
    compute_risk(run2_id, stub_model)   # run2 has no genus data
    assert False, "Should have raised ServiceError"
except ServiceError:
    pass
print("Test 12 PASS — ServiceError on compute_risk with no genus data")

print("\nAll tests passed.")
