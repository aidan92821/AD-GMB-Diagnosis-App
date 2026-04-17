<<<<<<< HEAD
# src/services/__init__.py
#
# Re-export the functions that pipeline/pipeline.py imports via:
#   from services import create_project, create_run, ingest_run_data, ...
#
# pipeline.py uses bare `from services import ...` which resolves to this
# package when src/ is on sys.path.

from services.assessment_service import (
    get_or_create_user,
    create_project,
    create_run,
    ingest_run_data,
    get_project_overview,
)

__all__ = [
    "get_or_create_user",
    "create_project",
    "create_run",
    "ingest_run_data",
    "get_project_overview",
]
=======
from .assessment_service import *
>>>>>>> feature/ui-pipeline
