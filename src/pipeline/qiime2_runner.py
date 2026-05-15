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
    def run(self, args: list[str], callback=None, env=None, cwd=None):

        cmd = self.base_cmd + args

        process = subprocess.Popen(
            cmd,
            cwd=cwd,
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

        return_code = process.wait()
        self._current_process = None
        if return_code != 0:
            raise subprocess.CalledProcessError(returncode=return_code, cmd=cmd)


    # for esearch
    def es_run(self, args: list[str], env=None):

        cmd = self.base_cmd + args

        process = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
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

    def mv(self, file: str, dir: str):
        cmd = [
            'mv',
            file,
            f"{dir}/"
        ]

        process = subprocess.Popen(
            cmd
        )

        process.wait()

    def rm(self, files: list[str]):

        cmd = ['rm']
        cmd.extend(files)

        process = subprocess.Popen(
            cmd
        )

        process.wait()

    def get_agora_models(self, genus: str, zip_path: str):
        print(f"[get_agora_models] function entry")
        # get the first file in the .zip that matches a genus
        cmd_list = ['unzip', '-l', zip_path]
        process_1 = subprocess.Popen(
            cmd_list,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        cmd_grep = ['grep', genus]
        process_2 = subprocess.Popen(
            cmd_grep,
            stdin=process_1.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        cmd_head = ['head', '-1']
        process_3 = subprocess.Popen(
            cmd_head,
            stdin=process_2.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        process_1.stdout.close()
        process_2.stdout.close()
        line = process_3.stdout.readline()
        process_1.wait()
        process_2.wait()
        process_3.wait()
        if not line.strip():
            return None
        return line.strip().split()[-1] # just get the filename
    
    def unzip_agora(self, zip_path: str, model_file: str, dest_dir_path: str):
        print(f"[unzip_agora] function entry")
        
        cmd = ['unzip', '-n', zip_path, model_file, '-d', dest_dir_path]
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        process.wait()
