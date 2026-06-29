import os
import subprocess
from pathlib import Path
from .base import BaseTool, run_subprocess
from ..updater import get_tools_env_prefix
from ..config import config


class IntegronfinderTool(BaseTool):
    @property
    def name(self) -> str:
        return "integronfinder"

    @property
    def description(self) -> str:
        return "IntegronFinder: Identifies integrons in bacterial genomes."

    def _get_env_dir(self) -> Path:
        return get_tools_env_prefix() / "sanbac_integronfinder"

    def _get_src_dir(self) -> Path:
        return config.db_dir / "integronfinder"

    def _build_env(self) -> dict:
        """Build a subprocess environment dict that points to the conda env's binaries."""
        env_dir = self._get_env_dir()
        env = os.environ.copy()
        # Force the conda env's bin/ to the front of PATH
        env["PATH"] = str(env_dir / "bin") + os.pathsep + env.get("PATH", "")
        return env

    def is_installed(self) -> bool:
        env_dir = self._get_env_dir()
        src_dir = self._get_src_dir()

        # Check that both the env and the IntegronFinder repo exist
        if not env_dir.exists() or not src_dir.exists():
            return False

        # Check that the integron_finder binary exists
        integron_finder_bin = env_dir / "bin" / "integron_finder"
        if not integron_finder_bin.exists():
            return False

        try:
            env = self._build_env()
            res = subprocess.run(
                [str(integron_finder_bin), "--version"],
                capture_output=True, text=True, errors="replace", env=env, timeout=15
            )
            return res.returncode == 0
        except Exception:
            return False

    def update_db(self) -> bool:
        env_dir = self._get_env_dir()
        src_dir = self._get_src_dir()

        script_content = f"""#!/bin/bash
set -e
echo "==========================================="
echo " IntegronFinder Automatic Installation"
echo "==========================================="
if ! command -v conda >/dev/null 2>&1; then
    echo "ERROR: Conda is not installed."
    exit 1
fi
source "$(conda info --base)/etc/profile.d/conda.sh"

ENV_DIR="{env_dir}"
if [ -d "$ENV_DIR" ]; then
    echo "Removing existing environment at $ENV_DIR..."
    rm -rf "$ENV_DIR"
fi

echo "Creating Conda environment at '$ENV_DIR'..."
conda create -y -p "$ENV_DIR" python=3.10

conda config --add channels conda-forge || true
conda config --add channels bioconda || true
conda config --set channel_priority strict

echo "Installing dependencies into '$ENV_DIR'..."
conda install -y -p "$ENV_DIR" -c bioconda -c conda-forge pip hmmer infernal prodigal

echo "Activating environment..."
conda activate "$ENV_DIR"

SRC_DIR="{src_dir}"
if [ ! -d "$SRC_DIR" ]; then
    mkdir -p "$(dirname "$SRC_DIR")"
    git clone https://github.com/gem-pasteur/Integron_Finder.git "$SRC_DIR"
fi

cd "$SRC_DIR"
"$ENV_DIR/bin/python" -m pip install .

echo "==========================================="
echo " Verifying integron_finder in conda env..."
echo "==========================================="
if [ -f "$ENV_DIR/bin/integron_finder" ]; then
    "$ENV_DIR/bin/integron_finder" --version
else
    echo "integron_finder binary not found. Checking bin directory:"
    ls -la "$ENV_DIR/bin" | grep integron || true
    exit 1
fi

echo ""
echo "==========================================="
echo " IntegronFinder Installation Complete!"
echo "==========================================="
"""
        import tempfile
        script_file = Path(tempfile.gettempdir()) / "install_integronfinder.sh"
        script_file.write_text(script_content)

        try:
            print("Running IntegronFinder installation script...")
            run_subprocess(["bash", str(script_file)], check=True)
            return True
        except subprocess.CalledProcessError as e:
            print(f"Error installing IntegronFinder: {e}")
            return False
        finally:
            if script_file.exists():
                script_file.unlink()

    def run(self, input_file: Path, output_dir: Path, threads: int) -> Path:
        env_dir = self._get_env_dir()
        integron_finder_bin = env_dir / "bin" / "integron_finder"

        if not self.is_installed() or not integron_finder_bin.exists():
            print("IntegronFinder not found. Attempting download/build...")
            if not self.update_db():
                raise RuntimeError("Could not find or build IntegronFinder.")

        output_dir.mkdir(parents=True, exist_ok=True)
        out_dir = output_dir / f"{input_file.stem}_integronfinder"
        
        # IntegronFinder will fail if the output directory already exists or create nested dirs
        if out_dir.exists():
            import shutil
            shutil.rmtree(out_dir, ignore_errors=True)
        out_dir.mkdir(parents=True)

        # Build the command using the conda env's integron_finder binary directly
        cmd = [
            str(integron_finder_bin),
            "--local-max",
            "--func-annot",
            "--circ",
            "--cpu", str(threads),
            "--pdf",
            "--gbk",
            "--outdir", str(out_dir),
            str(input_file.resolve())
        ]

        # Build env with correct PATH
        env = self._build_env()

        print(f"[{self.name.upper()}] Running IntegronFinder on {input_file.name}...")
        try:
            run_subprocess(cmd, check=True, cwd=str(output_dir), env=env)
            print(f"[{self.name.upper()}] Results saved at: {out_dir}")
            return out_dir
        except subprocess.CalledProcessError as e:
            print(f"[{self.name.upper()}] Error running IntegronFinder on {input_file.name}:")
            raise e

    def get_version(self) -> str:
        if not self.is_installed():
            return "Not Installed"

        env_dir = self._get_env_dir()
        integron_finder_bin = env_dir / "bin" / "integron_finder"

        if integron_finder_bin.exists():
            try:
                env = self._build_env()
                res = subprocess.run(
                    [str(integron_finder_bin), "--version"],
                    capture_output=True, text=True, errors="replace", env=env, timeout=15
                )
                output = ((res.stdout or "") + (res.stderr or "")).strip()
                if output:
                    for line in output.splitlines():
                        line = line.strip()
                        if line and "version" in line.lower():
                            return line
            except Exception:
                pass

        return "Installed"
