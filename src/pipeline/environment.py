from pathlib import Path
import subprocess


def get_conda_env_path(env_name):
    result = subprocess.run(
        ["conda", "env", "list"],
        capture_output=True,
        text=True,
        check=True
    )

    for line in result.stdout.splitlines():
        if line.startswith(env_name + " "):
            return Path(line.split()[-1])

    raise RuntimeError(f"Environment {env_name} not found")