import json
import sys
import subprocess
from pathlib import Path

APP_DIR = Path(__file__).parent.parent.parent


def _find_ml_python() -> str:
    """
    Return the path to a Python interpreter that has xgboost installed.
    Searches common venv/conda-env names inside the project directory,
    then falls back to sys.executable (with a warning if xgboost is missing).
    """
    # Candidate relative paths — covers Unix and Windows layouts
    _VENV_NAMES = [
        "biomicro-venv", "venv", ".venv", "ml_env", "env", "mlenv", "risk_env",
    ]
    candidates: list[Path] = []
    for name in _VENV_NAMES:
        candidates.append(APP_DIR / name / "bin" / "python")        # Unix
        candidates.append(APP_DIR / name / "Scripts" / "python.exe") # Windows

    for candidate in candidates:
        if not candidate.exists():
            continue
        probe = subprocess.run(
            [str(candidate), "-c", "import xgboost"],
            capture_output=True,
        )
        if probe.returncode == 0:
            return str(candidate)

    # Last resort: current interpreter (may lack xgboost — caller gets stderr)
    return sys.executable


_ML_PYTHON = _find_ml_python()


def run_assess(model: str, genus_abundance: dict, apoe: dict = None, nifty_path: str = None):
    """
    model options: 'gmb', 'tab', or 'full'
    Runs risk-assessment.py in a subprocess using whichever Python has xgboost.
    Returns the assessment dict, or {'stderr': '...'} on failure.
    """
    result = subprocess.run(
        [_ML_PYTHON, "risk-assessment.py"],
        input=json.dumps({
            "model": model,
            "microbiome": genus_abundance,
            "genetic": apoe,
            "mri": nifty_path,
        }),
        capture_output=True,
        text=True,
        cwd=str(APP_DIR / "src/risk"),
    )

    if result.returncode != 0:
        return {"stderr": result.stderr}

    return json.loads(result.stdout)
