# scripts/db_smoketest.py
import os
import json

from sqlalchemy import select

from src.db.database import engine, SessionLocal
from src.db.db_models import Base, Subject, Project, MicrobiomeData

def main():
    os.makedirs("data", exist_ok=True)

    # Fresh recreate for smoke test
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    with SessionLocal() as session:
        # Insert Subject
        subject = Subject(
            age=70,
            sex="F",
            apoe_genotype="e3/e4",
            polygenic_risk_score=1.23
        )
        session.add(subject)
        session.flush()  # assigns subject_id

        # Insert Project linked to subject
        project = Project(
            subject_id=subject.subject_id,
            name="Smoke Test Project",
            notes="DB pipeline smoke test"
        )
        session.add(project)
        session.flush()  # assigns project_id

        # Insert Microbiome sample linked to project
        taxa = {"Bacteroides": 0.22, "Firmicutes": 0.48, "Akkermansia": 0.03}
        mb = MicrobiomeData(
            project_id=project.project_id,
            raw_file_path="data/example_microbiome.tsv",
            taxa_json=json.dumps(taxa),
            alpha_diversity=2.5,
            shannon_index=1.9
        )
        session.add(mb)
        session.commit()

        # Query back with joins
        stmt = (
            select(MicrobiomeData, Project, Subject)
            .join(Project, MicrobiomeData.project_id == Project.project_id)
            .join(Subject, Project.subject_id == Subject.subject_id)
        )
        row = session.execute(stmt).first()
        assert row is not None, "No row returned from join query!"

        microbiome, proj, subj = row
        print("Smoke test passed!")
        print(f"Subject ID: {subj.subject_id}, Project ID: {proj.project_id}, Microbiome ID: {microbiome.microbiome_id}")
        print(f"Taxa JSON: {microbiome.taxa_json}")

if __name__ == "__main__":
    main()