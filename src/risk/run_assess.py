import json
from pathlib import Path
import subprocess

APP_DIR = Path(__file__).parent.parent.parent
ENV_DIR = str(APP_DIR / "ml_env/bin/python")

# call in main_window _RiskPredictionWorker.run()
def run_assess(model: str, genus_abundance: dict, apoe: dict=None, nifty_path: str=None):
    '''
    model options: 'gmb', 'tab', or 'full'
    '''
    result = subprocess.run(
        [ENV_DIR, 
        "risk-assessment.py"],
        input=json.dumps({"model": model, "microbiome": genus_abundance, "genetic": apoe, "mri": nifty_path}),
        capture_output=True, text=True,
        cwd=str(APP_DIR / "src/risk")
    )

    if result.returncode != 0:
        return {'stderr': result.stderr}

    assessment = json.loads(result.stdout)
    return assessment