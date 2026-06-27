import subprocess
import shutil
from pathlib import Path
from .base import BaseTool, get_cmd_version, find_executable, run_subprocess
from ..config import config

class ISEScanTool(BaseTool):
    @property
    def name(self) -> str:
        return "isescan"

    @property
    def description(self) -> str:
        return "ISEScan for identifying Insertion Sequences (IS) in genomes"

    def _resolve_cmd(self) -> str:
        """Resolves the isescan executable path."""
        configured = config.get_executable("isescan.py")
        if configured == "isescan.py":
            return find_executable("isescan.py")
        return find_executable(configured)

    def is_installed(self) -> bool:
        return self._resolve_cmd() is not None

    def update_db(self) -> bool:
        # ISEScan does not have a separate database update command
        return True

    def run(self, input_file: Path, output_dir: Path, threads: int) -> Path:
        cmd_path = self._resolve_cmd()
        if not cmd_path:
            raise FileNotFoundError("isescan.py is not installed or not in PATH.")

        sample_outdir = output_dir / input_file.stem
        
        cmd = [
            cmd_path,
            "--seqfile", str(input_file),
            "--output", str(sample_outdir),
            "--nthread", str(threads)
        ]
        
        print(f"[{self.name.upper()}] Running ISEScan on {input_file.name}...")
        try:
            run_subprocess(cmd, capture_output=True, text=True, errors="replace", check=True)
            
            # Extract the CSV file and move it to the main output_dir
            csv_files = list(sample_outdir.rglob("*.csv"))
            if csv_files:
                target_csv = output_dir / f"{input_file.name}.csv"
                shutil.move(str(csv_files[0]), str(target_csv))
                # Clean up the rest of the output directory
                shutil.rmtree(sample_outdir)
                return target_csv
            else:
                return sample_outdir
                
        except subprocess.CalledProcessError as e:
            print(f"[{self.name.upper()}] Error running ISEScan on {input_file.name}:")
            print(e.stderr or e.stdout)
            raise e

    def get_version(self) -> str:
        cmd_path = self._resolve_cmd()
        if not cmd_path:
            return "Not Installed"
        return get_cmd_version([cmd_path], "--version")
