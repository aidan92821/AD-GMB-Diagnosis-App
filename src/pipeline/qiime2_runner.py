from io import StringIO
from pathlib import Path
import subprocess
import os

APP_DIR = Path(__file__).parent
ENV_DIR = APP_DIR / "qiime_env"
MAMBA_BIN = APP_DIR / "bin" / "micromamba"


class QiimeRunner:
    def __init__(self):
        self.base_cmd = [
            str(MAMBA_BIN),
            "run",
            "-p",
            str(ENV_DIR),
        ]

        self.env = os.environ.copy()
        self.env.update({
            "VDB_CONFIG": str(APP_DIR / "vdb-config"),
            "NCBI_SETTINGS": str(APP_DIR / "vdb-config/user-settings.mkfg")
        })

        self._current_process = None

    def cancel(self) -> None:
        """Kill the currently running subprocess, if any."""
        if self._current_process and self._current_process.poll() is None:
            self._current_process.kill()
            self._current_process = None

    # args is the command with arguments separated into a list
    def run(self, args: list[str], callback=None, env=None):

        cmd = self.base_cmd + args

        process = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        self._current_process = process

        for line in process.stdout:
            print(line, end='', flush=True)  # always stream to VS Code terminal
            if callback:
                callback(line)

        process.wait()
        self._current_process = None


    # for esearch
    def es_run(self, args: list[str], env=None):
        
        cmd = self.base_cmd + args

        process = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        return process

    # for efetch
    def ef_run(self, args: list[str], es_process, callback=None, env=None):
        
        cmd = self.base_cmd + args

        process = subprocess.Popen(
            cmd,
            env=env,
            stdin=es_process.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )

        es_process.stdout.close()

        output = []
        for line in process.stdout:
            output.append(line)
            if callback:
                callback(line)

        es_process.wait()
        process.wait()

        return StringIO("".join(output))
    
    def fq_run(self, args: list[str], env=None):

        process = subprocess.Popen(
            args,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        process.wait()