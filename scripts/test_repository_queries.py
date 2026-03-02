from src.db.database import SessionLocal
from src.db.repository import (
    create_subject,
    create_project,
    create_microbiome_data,
    create_risk_assessment,
    get_project,
    list_microbiomes_for_project,
    get_latest_microbiome,
    get_latest_risk_assessment,
)

def run_test():
    with SessionLocal() as session:

        # ---- Setup data ----
        subject = create_subject(session, age=65, sex="M")
        project = create_project(session, subject=subject, name="Query Test")

        mb1 = create_microbiome_data(
            session,
            project=project,
            taxa={"A": 0.5},
        )

        mb2 = create_microbiome_data(
            session,
            project=project,
            taxa={"B": 0.7},
        )

        risk = create_risk_assessment(
            session,
            project=project,
            microbiome=mb2,
            risk_probability=0.82,
            risk_label="High",
            model_version="v1",
        )

        # ---- Test get_project ----
        fetched_project = get_project(session, project.project_id)
        assert fetched_project.project_id == project.project_id

        # ---- Test list ----
        microbiomes = list_microbiomes_for_project(session, project.project_id)
        assert len(microbiomes) == 2
        assert microbiomes[0].microbiome_id == mb2.microbiome_id  # newest first

        # ---- Test latest helpers ----
        latest_mb = get_latest_microbiome(session, project.project_id)
        assert latest_mb.microbiome_id == mb2.microbiome_id

        latest_risk = get_latest_risk_assessment(session, project.project_id)
        assert latest_risk.risk_id == risk.risk_id

        print("All repository query tests passed.")

        session.rollback()  # keep DB clean


if __name__ == "__main__":
    run_test()