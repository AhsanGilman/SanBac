import shutil
import subprocess
import sys
from pathlib import Path
from .base import BaseTool, run_subprocess, get_cmd_version, find_executable
from ..config import config

class PlasmidfinderTool(BaseTool):
    @property
    def name(self) -> str:
        return "plasmidfinder"

    @property
    def description(self) -> str:
        return "PlasmidFinder: Identifies plasmids in total or partial sequenced isolates of bacteria."

    def is_installed(self) -> bool:
        pf_dir = config.db_dir / "plasmidfinder"
        pf_py = pf_dir / "plasmidfinder.py"
        return pf_py.exists()

    def update_db(self) -> bool:
        pf_dir = config.db_dir / "plasmidfinder"
        db_dir = config.db_dir / "plasmidfinder_db"
        
        try:
            # 1. Clone or update plasmidfinder program
            if not pf_dir.exists():
                print("Cloning PlasmidFinder program...")
                run_subprocess(["git", "clone", "https://bitbucket.org/genomicepidemiology/plasmidfinder.git", str(pf_dir)], check=True)
            else:
                print("Updating PlasmidFinder program...")
                run_subprocess(["git", "pull"], cwd=str(pf_dir), check=True)
            
            # 2. Clone or update plasmidfinder database
            if not db_dir.exists():
                print("Cloning PlasmidFinder database...")
                run_subprocess(["git", "clone", "https://bitbucket.org/genomicepidemiology/plasmidfinder_db.git", str(db_dir)], check=True)
            else:
                print("Updating PlasmidFinder database...")
                run_subprocess(["git", "pull"], cwd=str(db_dir), check=True)
                
            # 3. Install database using kma_index
            print("Installing PlasmidFinder database...")
            # Using kma_index, relying on run_subprocess to find it in PATH or tool bin dirs
            run_subprocess([sys.executable, "INSTALL.py", "kma_index"], cwd=str(db_dir), check=True)
            
            print("PlasmidFinder database updated successfully.")
            return True
        except Exception as e:
            print(f"Error updating PlasmidFinder: {e}")
            return False

    def run(self, input_file: Path, output_dir: Path, threads: int) -> Path:
        if not self.is_installed():
            raise FileNotFoundError("PlasmidFinder program not found. Please run 'update-db' first.")
            
        pf_py = config.db_dir / "plasmidfinder" / "plasmidfinder.py"
        db_dir = config.db_dir / "plasmidfinder_db"
        
        if not db_dir.exists():
            print("PlasmidFinder database not found. Attempting download/build...")
            if not self.update_db():
                raise RuntimeError("Could not find or build PlasmidFinder database.")
                
        output_dir.mkdir(parents=True, exist_ok=True)
        pf_out_dir = output_dir / f"{input_file.stem}_results"
        pf_out_dir.mkdir(parents=True, exist_ok=True)
        
        cmd = [
            sys.executable, str(pf_py),
            "-i", str(input_file.resolve()),
            "-o", str(pf_out_dir.resolve()),
            "-p", str(db_dir.resolve()),
            "-x"
        ]
        
        print(f"[{self.name.upper()}] Running PlasmidFinder on {input_file.name}...")
        try:
            run_subprocess(cmd, check=True)
            print(f"[{self.name.upper()}] Results saved at: {pf_out_dir}")
            return pf_out_dir
        except subprocess.CalledProcessError as e:
            print(f"[{self.name.upper()}] Error running PlasmidFinder on {input_file.name}:")
            print(e.stderr or e.stdout)
            raise e

    def get_version(self) -> str:
        pf_dir = config.db_dir / "plasmidfinder"
        pf_py = pf_dir / "plasmidfinder.py"
        if not pf_py.exists():
            return "Not Installed"

        # 1. Try running plasmidfinder.py --version
        try:
            res = run_subprocess(
                [sys.executable, str(pf_py), "--version"],
                capture_output=True, text=True, errors="replace", timeout=10
            )
            output = ((res.stdout or "") + (res.stderr or "")).strip()
            if output and "error" not in output.lower():
                # Extract version number from output
                for line in output.splitlines():
                    line = line.strip()
                    if line:
                        return line
        except Exception:
            pass

        # 2. Try extracting version from the script source
        try:
            source = pf_py.read_text(errors="replace")
            import re
            match = re.search(r'(?:__version__|version)\s*=\s*["\']([^"\']+)["\']', source)
            if match:
                return match.group(1)
        except Exception:
            pass

        # 3. Fall back to git tag or commit date
        try:
            res = run_subprocess(
                ["git", "describe", "--tags", "--always"],
                cwd=str(pf_dir), capture_output=True, text=True, timeout=5
            )
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip()
        except Exception:
            pass

        try:
            res = run_subprocess(
                ["git", "log", "-1", "--format=%cd", "--date=short"],
                cwd=str(pf_dir), capture_output=True, text=True, timeout=5
            )
            if res.stdout.strip():
                return f"Git ({res.stdout.strip()})"
        except Exception:
            pass

        return "Unknown"
