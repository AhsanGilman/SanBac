import shutil
import subprocess
from pathlib import Path
from .base import BaseTool, get_cmd_version, find_executable, run_subprocess
from ..config import config

class ProkkaTool(BaseTool):
    @property
    def name(self) -> str:
        return "prokka"

    @property
    def description(self) -> str:
        return "Prokka (rapid prokaryotic genome annotation) for protein annotation and gene prediction"

    def _resolve_cmd(self) -> str:
        """Resolves the prokka executable path."""
        configured = config.get_executable("prokka")
        return find_executable(configured)

    def is_installed(self) -> bool:
        return self._resolve_cmd() is not None

    def update_db(self) -> bool:
        prokka_cmd = self._resolve_cmd()
        if not self.is_installed():
            print("Error: 'prokka' command not found. Please install Prokka first.")
            return False
        
        print("Setting up Prokka databases (if writable)...")
        try:
            result = run_subprocess(
                [prokka_cmd, "--setupdb"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                print("Prokka databases configured successfully.")
            else:
                print("Notice: Prokka --setupdb failed (this is normal if system databases are read-only and already configured).")
            return True
        except Exception as e:
            print(f"Notice: Prokka database setup skipped: {e}")
            return True

    def run(self, input_file: Path, output_dir: Path, threads: int) -> Path:
        prokka_cmd = self._resolve_cmd()
        if not prokka_cmd:
            raise FileNotFoundError("Prokka is not installed or not in PATH.")

        # Save each sample's Prokka files to its own subfolder in the output_dir
        sample_outdir = output_dir / input_file.stem
        
        cmd = [
            prokka_cmd,
            "--outdir", str(sample_outdir),
            "--prefix", input_file.stem,
            "--cpus", str(threads),
            "--force",
            str(input_file)
        ]
        
        print(f"[{self.name.upper()}] Running Prokka annotation on {input_file.name}...")
        try:
            run_subprocess(cmd, capture_output=True, text=True, errors="replace", check=True)
            return sample_outdir
        except subprocess.CalledProcessError as e:
            print(f"[{self.name.upper()}] Error running Prokka on {input_file.name}:")
            print(e.stderr or e.stdout)
            raise e

    def get_version(self) -> str:
        cmd_path = self._resolve_cmd()
        if not cmd_path:
            return "Not Installed"
        return get_cmd_version([cmd_path], "--version")
