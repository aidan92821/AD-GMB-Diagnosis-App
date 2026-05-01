import os
import stat
import urllib.request
from pathlib import Path
import subprocess
import platform

APP_DIR = Path(__file__).parent # gets the current directory
ENV_DIR = APP_DIR / "qiime_env"
SRA_BIN = APP_DIR / "bin" / "sratoolkit" / "bin"
MAMBA_BIN = APP_DIR / "bin" / "micromamba"

_YML_FILES = {
    "linux-64":  APP_DIR / "qiime2-linux.yml",
    "osx-64":    APP_DIR / "qiime2.yml",
    "osx-arm64": APP_DIR / "qiime2.yml",
}

# MICROMAMBA_VERSION = "2.0.8"

# # Download URLs per platform — from micromamba's official GitHub releases
# _MICROMAMBA_URLS = {
#     "linux-64":   f"https://github.com/mamba-org/mamba/releases/download/micromamba-{MICROMAMBA_VERSION}/micromamba-linux-64",
#     "osx-64":     f"https://github.com/mamba-org/mamba/releases/download/micromamba-{MICROMAMBA_VERSION}/micromamba-osx-64",
#     "osx-arm64":  f"https://github.com/mamba-org/mamba/releases/download/micromamba-{MICROMAMBA_VERSION}/micromamba-osx-arm64",
# }


def get_platform() -> str:
    system = platform.system()
    machine = platform.machine()

    if system == "Darwin":
        return "osx-arm64" if machine == "arm64" else "osx-64"
    if system == "Linux":
        return "linux-64"
    raise RuntimeError(
        f"Unsupported platform: {system} ({machine}). "
        "QIIME2 requires macOS or Linux. Windows users should run under WSL2."
    )


# def download_micromamba(callback=None) -> bool:
#     if MAMBA_BIN.exists():
#         return True

#     conda_platform = get_platform()
#     url = _MICROMAMBA_URLS[conda_platform]

#     if callback:
#         callback(f"downloading micromamba for {conda_platform}...\n")

#     try:
#         MAMBA_BIN.parent.mkdir(parents=True, exist_ok=True)
#         urllib.request.urlretrieve(url, MAMBA_BIN)
#         MAMBA_BIN.chmod(MAMBA_BIN.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
#         if callback:
#             callback("micromamba downloaded successfully\n")
#         return True
#     except Exception as e:
#         if callback:
#             callback(f"failed to download micromamba: {e}\n")
#         return False


def env_exists():
    return (ENV_DIR / "bin" / "qiime").exists() \
       and (SRA_BIN / "fasterq-dump").exists() \
       and (ENV_DIR / "bin" / "efetch").exists() \
       and (ENV_DIR / "bin" / "esearch").exists()


# callback(line: str) -> None is a function used for streaming logs to the ui
def create_env(callback=None):
    conda_platform = get_platform()
    yml_file = _YML_FILES[conda_platform]

    env = os.environ.copy()
    env.update({
        "CONDA_SUBDIR": conda_platform,
        "CONDA_CHANNEL_PRIORITY": "strict",
        "CONDA_SOLVER": "classic",
    })

    cmd = [
        str(MAMBA_BIN),
        "create",
        "-y",
        "-p", str(ENV_DIR),

        "--channel-priority", "flexible",
        "--platform", conda_platform,

        "-f", str(yml_file)
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
    # if not download_micromamba(callback):     # Comment out if we change our mind
    #     return False
    if not env_exists():
        callback("setting up environment\n")
        return create_env(callback)
    callback("environment requirements satisfied\n")
    return True


# TODO placeholder callback function for testing
def callback(line: str):
    print(line)
