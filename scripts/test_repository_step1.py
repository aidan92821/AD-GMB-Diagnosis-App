from src.db.database import SessionLocal
from src.db.repository import create_subject, create_project, create_microbiome_data
import json

with SessionLocal() as session:
    subject = create_subject(session, age=70, sex="F")
    project = create_project(session, subject = subject, name = "Repo Step Test")
    
    mb = create_microbiome_data(
        session, project = project,
        raw_file_path = "Test",
        taxa = {"Firmicuttes": 0.2, "Bacteroids": 0.8},
        alpha_diversity = 0.2,
        shannon_index = 1.2,
        )

    print("Subject ID:", subject.subject_id, "| Subject Age:", subject.age, "| Subject Sex:", subject.sex)
    print("Project ID:", project.project_id, "| Project Name:", project.name, "| Project Notes:", project.notes)
    print("Microbiome ID:", mb.microbiome_id, "| File:", mb.raw_file_path)
    print("Taxa JSON (stored):", mb.taxa_json)
    print("Taxa dict (decoded):", json.loads(mb.taxa_json))
    
    session.rollback()      # Does not make insert permnanent 

# To run: "python3 -m scripts.test_repository_step1" from root folder