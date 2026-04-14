import os
from pathlib import Path
import subprocess

APP_DIR = Path(__file__).parent # gets the current directory 
ENV_DIR = APP_DIR / "qiime_env"
SRA_BIN = APP_DIR / "bin" / "sratoolkit" / "bin"
MAMBA_BIN = APP_DIR / "bin" / "micromamba"
YML_FILE = APP_DIR / "qiime2.yml"


def env_exists():
    return (ENV_DIR / "bin" / "qiime").exists() \
       and (SRA_BIN / "fasterq-dump").exists() \
       and (ENV_DIR / "bin" / "efetch").exists() \
       and (ENV_DIR / "bin" / "esearch").exists()


# callback(line: str) -> None is a function used for streaming logs to the ui
def create_env(callback=None):

    env = os.environ.copy()
    env.update({
        "CONDA_SUBDIR": "osx-64",
        "CONDA_CHANNEL_PRIORITY": "strict",
        "CONDA_SOLVER": "classic",
    })

    cmd = [
        str(MAMBA_BIN),
        "create",
        "-y",
        "-p", str(ENV_DIR),

        "--channel-priority", "flexible",
        "--platform", "osx-64",

        "-f", str(YML_FILE)
    ]

    process = subprocess.Popen( #popen() is non blocking
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    for line in process.stdout: # need to do this or else PIPE buffer will not be flushed
        if callback:
            callback(line) # this is for giving user information at the UI of what is happening in the subprocess

    process.wait()
    success = process.returncode == 0


    if success:
        (ENV_DIR / ".installed").touch()

    return success


def ensure_env(callback=None):
    if not env_exists():
        return create_env(callback)
    return True


# TODO placeholder callback function for testing
def callback(line: str):
    print(line)
