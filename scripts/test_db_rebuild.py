# scripts/test_db_rebuild.py
# Smoke tests for the rebuilt database schema and repository layer.
# Run with: python3 -m scripts.test_db_rebuild

from src.db.database import SessionLocal, engine
from src.db.db_models import Base
from src.db.repository import (
    create_user, get_user, get_user_by_username,
    create_project, get_project, list_projects_for_user,
    create_run, get_run, list_runs_for_project,
    create_genus_bulk, get_genus_for_run,
    create_feature, create_feature_count_bulk, get_feature_counts_for_run,
    create_tree, get_tree_for_run,
    create_alpha_diversity, get_alpha_diversity_for_run,
    create_beta_diversity, get_beta_diversity,
    NotFoundError, IntegrityError,
)

# Delete and recreate the DB file so we start with a clean slate
import os
db_path = os.path.join("data", "axisad.db")
if os.path.exists(db_path):
    os.remove(db_path)
Base.metadata.create_all(engine)

# ── Shared setup ────────────────────────────────────────────────────────────────
session = SessionLocal()
user    = create_user(session, username="testuser")
project = create_project(session, user=user, name="Test Project")
run1    = create_run(session, project=project, source="upload", srr_accession="SRR99999999", library_layout="PAIRED")
run2    = create_run(session, project=project, source="ncbi",   srr_accession="SRR35606904", bio_proj_accession="PRJNA123456")
session.commit()
user_id    = user.user_id
project_id = project.project_id
run1_id    = run1.run_id
run2_id    = run2.run_id
session.close()

# ── Test 1: User lookup ─────────────────────────────────────────────────────────
session = SessionLocal()
u = get_user(session, user_id)
assert u.username == "testuser", f"Expected 'testuser', got {u.username!r}"
u2 = get_user_by_username(session, "testuser")
assert u2.user_id == user_id
session.close()
print("Test 1 PASS — user lookup by ID and username")

# ── Test 2: Project and run listing ─────────────────────────────────────────────
session = SessionLocal()
projects = list_projects_for_user(session, user_id)
assert len(projects) == 1
runs = list_runs_for_project(session, project_id)
assert len(runs) == 2
r = get_run(session, run1_id)
assert r.source == "upload"
session.close()
print("Test 2 PASS — project and run listing")

# ── Test 3: Genus bulk insert ────────────────────────────────────────────────────
session = SessionLocal()
run = get_run(session, run1_id)
create_genus_bulk(session, run=run, genus_abundances={
    "Firmicutes": 0.40,
    "Bacteroidetes": 0.35,
    "Actinobacteria": 0.25,
})
session.commit()
genera = get_genus_for_run(session, run1_id)
assert len(genera) == 3
assert all(0 <= g.relative_abundance <= 1 for g in genera)
session.close()
print("Test 3 PASS — genus bulk insert and retrieval")

# ── Test 4: Features and feature counts ─────────────────────────────────────────
session = SessionLocal()
run = get_run(session, run1_id)
create_feature(session, run=run, feature_id="asv001", sequence="ATCG", taxonomy="k__Bacteria;p__Firmicutes")
create_feature(session, run=run, feature_id="asv002", sequence="GCTA", taxonomy="k__Bacteria;p__Bacteroidetes")
session.flush()
create_feature_count_bulk(session, run_id=run1_id, counts={"asv001": 120, "asv002": 85})
session.commit()
counts = get_feature_counts_for_run(session, run1_id)
assert len(counts) == 2
assert sum(c.abundance for c in counts) == 205
session.close()
print("Test 4 PASS — features and feature counts")

# ── Test 5: Tree ─────────────────────────────────────────────────────────────────
session = SessionLocal()
run = get_run(session, run1_id)
create_tree(session, run=run, newick_path="data/trees/run1.nwk")
session.commit()
tree = get_tree_for_run(session, run1_id)
assert tree is not None
assert tree.newick_path == "data/trees/run1.nwk"
session.close()
print("Test 5 PASS — tree storage and retrieval")

# ── Test 6: Alpha diversity ──────────────────────────────────────────────────────
session = SessionLocal()
run = get_run(session, run1_id)
create_alpha_diversity(session, run=run, metric="shannon",            value=2.45)
create_alpha_diversity(session, run=run, metric="observed_features",  value=87.0)
session.commit()
alphas = get_alpha_diversity_for_run(session, run1_id)
assert len(alphas) == 2
metrics = {a.metric for a in alphas}
assert "shannon" in metrics
session.close()
print("Test 6 PASS — alpha diversity")

# ── Test 7: Beta diversity ───────────────────────────────────────────────────────
session = SessionLocal()
r1 = get_run(session, run1_id)
r2 = get_run(session, run2_id)
create_beta_diversity(session, run_1=r1, run_2=r2, metric="bray_curtis", value=0.32)
session.commit()
betas = get_beta_diversity(session, run1_id, run2_id, metric="bray_curtis")
assert len(betas) == 1
assert abs(betas[0].value - 0.32) < 1e-6
session.close()
print("Test 7 PASS — beta diversity")

# ── Test 8: NotFoundError on bad ID ─────────────────────────────────────────────
session = SessionLocal()
try:
    get_run(session, 9999)
    assert False, "Should have raised NotFoundError"
except NotFoundError:
    pass
finally:
    session.close()
print("Test 8 PASS — NotFoundError on missing run")

# ── Test 9: IntegrityError on same-run beta diversity ───────────────────────────
session = SessionLocal()
try:
    r1 = get_run(session, run1_id)
    create_beta_diversity(session, run_1=r1, run_2=r1, metric="bray_curtis", value=0.0)
    assert False, "Should have raised IntegrityError"
except IntegrityError:
    pass
finally:
    session.close()
print("Test 9 PASS — IntegrityError on same-run beta diversity")

print("\nAll tests passed.")
