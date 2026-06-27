import os
import shutil
import subprocess
from pathlib import Path
from .base import BaseTool, run_subprocess, get_cmd_version
from ..updater import get_tools_env_prefix

class PhigaroTool(BaseTool):
    @property
    def name(self) -> str:
        return "phigaro"

    @property
    def description(self) -> str:
        return "Phigaro: A scalable command-line tool for predicting phages and prophages."

    def _get_phigaro_bin(self) -> Path:
        env_dir = get_tools_env_prefix() / "phigaro"
        return env_dir / "bin" / "phigaro"

    def is_installed(self) -> bool:
        phigaro_bin = self._get_phigaro_bin()
        return phigaro_bin.exists() and os.access(phigaro_bin, os.X_OK)

    def update_db(self) -> bool:
        env_dir = get_tools_env_prefix() / "phigaro"
        conda_path = os.environ.get("CONDA_EXE") or shutil.which("conda")
        
        if not conda_path:
            print("Error: conda executable not found. Cannot create isolated environment for Phigaro.")
            return False

        print(f"Creating isolated conda environment for Phigaro at {env_dir}...")
        try:
            # Clean up if existing corrupted environment
            if env_dir.exists():
                shutil.rmtree(str(env_dir), ignore_errors=True)

            # 1. Create conda env with prodigal and hmmer
            run_subprocess([
                conda_path, "create", "-y", "-p", str(env_dir), 
                "-c", "conda-forge", "-c", "bioconda", 
                "prodigal", "hmmer", "python=3.9"
            ], check=True)
            
            # 2. Install phigaro via pip inside the env
            pip_bin = env_dir / "bin" / "pip"
            if not pip_bin.exists():
                print("Error: pip not found in the new conda environment.")
                return False
            
            print("Installing Phigaro via pip...")
            run_subprocess([str(pip_bin), "install", "phigaro"], check=True)
            
            # 3. Run phigaro-setup
            setup_bin = env_dir / "bin" / "phigaro-setup"
            if not setup_bin.exists():
                print("Error: phigaro-setup not found after pip install.")
                return False
                
            print("Running phigaro-setup (downloading databases)...")
            run_subprocess([str(setup_bin), "--no-updated"], check=True)
            
            print("Phigaro installed successfully.")
            return True
        except subprocess.CalledProcessError as e:
            print(f"Error installing Phigaro: {e.stderr or e.stdout}")
            return False
        except Exception as e:
            print(f"Error installing Phigaro: {e}")
            return False

    def run(self, input_file: Path, output_dir: Path, threads: int) -> Path:
        phigaro_bin = self._get_phigaro_bin()
        
        if not phigaro_bin.exists():
            print("Phigaro not installed. Attempting installation...")
            if not self.update_db():
                raise RuntimeError("Could not install Phigaro.")
                
        output_dir.mkdir(parents=True, exist_ok=True)
        # We output to a prefix. E.g. output_dir/MBBL_5_phigaro
        # Phigaro automatically appends extensions to this output prefix.
        out_prefix = output_dir / f"{input_file.stem}_phigaro"
        
        cmd = [
            str(phigaro_bin),
            "-f", str(input_file.resolve()),
            "-o", str(out_prefix.resolve()),
            "-t", str(threads)
        ]
        
        print(f"[{self.name.upper()}] Running Phigaro on {input_file.name}...")
        try:
            # Note: If -t is not supported by phigaro, you can remove it or handle it in a wrapper. 
            # We assume -t threads works based on common bioconda CLI practices.
            # If it throws an error, the CalledProcessError will catch it.
            # Pass input="Y\n" to automatically bypass interactive prompts (e.g. dropping sequences)
            run_subprocess(cmd, check=True, input="Y\n", text=True)
            print(f"[{self.name.upper()}] Results saved with prefix: {out_prefix}")
            return output_dir
        except subprocess.CalledProcessError as e:
            # Some tools return non-zero if no hits are found, others crash.
            # Let's see if we can catch an argument error.
            if "unrecognized arguments: -t" in (e.stderr or ""):
                print(f"[{self.name.upper()}] Warning: threads argument not supported by Phigaro. Running without -t...")
                cmd.remove("-t")
                cmd.remove(str(threads))
                run_subprocess(cmd, check=True, input="Y\n", text=True)
                print(f"[{self.name.upper()}] Results saved with prefix: {out_prefix}")
                return output_dir
            else:
                print(f"[{self.name.upper()}] Error running Phigaro on {input_file.name}:")
                print(e.stderr or e.stdout)
                raise e

    def get_version(self) -> str:
        if not self.is_installed():
            return "Not Installed"
        # Try --version, if fails try -v
        try:
            return get_cmd_version([str(self._get_phigaro_bin()), "--version"])
        except Exception:
            return "Installed"
