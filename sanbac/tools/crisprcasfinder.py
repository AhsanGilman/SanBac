import os
import glob
import shutil
import subprocess
import sys
from pathlib import Path
from .base import BaseTool, run_subprocess
from ..updater import get_tools_env_prefix
from ..config import config


class CrisprcasfinderTool(BaseTool):
    @property
    def name(self) -> str:
        return "crisprcasfinder"

    @property
    def description(self) -> str:
        return "CRISPRCasFinder: Identifies CRISPR arrays and Cas proteins."

    def _get_env_dir(self) -> Path:
        return get_tools_env_prefix() / "sanbac_crisprcasfinder"

    def _get_ccf_dir(self) -> Path:
        return config.db_dir / "crisprcasfinder"

    def _build_env(self) -> dict:
        """Build a subprocess environment dict that points to the conda env's
        perl, python, and all other binaries — completely bypassing the system."""
        env_dir = self._get_env_dir()
        env = os.environ.copy()

        # Force the conda env's bin/ to the front of PATH
        env["PATH"] = str(env_dir / "bin") + os.pathsep + env.get("PATH", "")

        # LD_LIBRARY_PATH for libgomp and other shared libs
        env_lib = str(env_dir / "lib")
        existing_ld = env.get("LD_LIBRARY_PATH", "")
        env["LD_LIBRARY_PATH"] = env_lib + (":" + existing_ld if existing_ld else "")

        return env

    def is_installed(self) -> bool:
        env_dir = self._get_env_dir()
        ccf_dir = self._get_ccf_dir()

        # Check that both the env and the CRISPRCasFinder repo exist
        if not env_dir.exists() or not ccf_dir.exists():
            return False

        # Check that the conda env's perl binary exists
        perl_bin = env_dir / "bin" / "perl"
        if not perl_bin.exists():
            return False

        # Check that BioPerl is loadable from the conda env's perl
        try:
            env = self._build_env()
            res = subprocess.run(
                [str(perl_bin), "-MBio::AlignIO", "-e", "print 'OK'"],
                capture_output=True, text=True, errors="replace",
                env=env, timeout=15
            )
            return res.returncode == 0
        except Exception:
            return False

    def update_db(self) -> bool:
        env_dir = self._get_env_dir()
        ccf_dir = self._get_ccf_dir()

        script_content = f"""#!/bin/bash
set -e
echo "==========================================="
echo " CRISPRCasFinder Automatic Installation"
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
conda create -y -p "$ENV_DIR" python=3.10 perl

conda config --add channels conda-forge || true
conda config --add channels bioconda || true
conda config --set channel_priority strict

echo "Installing dependencies into '$ENV_DIR'..."
conda install -y -p "$ENV_DIR" -c conda-forge -c bioconda \\
    perl perl-app-cpanminus perl-bioperl \\
    macsyfinder=2.1.2 vmatch emboss prodigal hmmer blast \\
    bedtools muscle mafft clustalw viennarna wget curl libgomp

echo "Activating environment for cpanm/macsydata..."
conda activate "$ENV_DIR"
cpanm Date::Calc File::Which XML::Simple Parallel::ForkManager || true
macsydata install -u CASFinder==3.1.0 || true

CCF_DIR="{ccf_dir}"
if [ ! -d "$CCF_DIR" ]; then
    mkdir -p "$(dirname "$CCF_DIR")"
    git clone https://github.com/dcouvin/CRISPRCasFinder.git "$CCF_DIR"
fi

cd "$ENV_DIR/lib"
if [ ! -e libgomp.so.1 ]; then
    ln -s libgomp.so.1.0.0 libgomp.so.1 || true
fi

echo "==========================================="
echo " Verifying BioPerl in conda env..."
echo "==========================================="
"$ENV_DIR/bin/perl" -MBio::AlignIO -e 'print "BioPerl OK\\n"'

echo ""
echo "==========================================="
echo " CRISPRCasFinder Installation Complete!"
echo "==========================================="
"""
        import tempfile
        script_file = Path(tempfile.gettempdir()) / "install_ccf.sh"
        script_file.write_text(script_content)

        try:
            print("Running CRISPRCasFinder installation script...")
            run_subprocess(["bash", str(script_file)], check=True)
            return True
        except subprocess.CalledProcessError as e:
            print(f"Error installing CRISPRCasFinder: {e}")
            return False
        finally:
            if script_file.exists():
                script_file.unlink()

    def run(self, input_file: Path, output_dir: Path, threads: int) -> Path:
        env_dir = self._get_env_dir()
        ccf_dir = self._get_ccf_dir()
        ccf_script = ccf_dir / "CRISPRCasFinder.pl"
        perl_bin = env_dir / "bin" / "perl"

        if not self.is_installed() or not ccf_script.exists():
            print("CRISPRCasFinder not found. Attempting download/build...")
            if not self.update_db():
                raise RuntimeError("Could not find or build CRISPRCasFinder.")

        output_dir.mkdir(parents=True, exist_ok=True)
        ccf_out_dir = output_dir / f"{input_file.stem}_crisprcasfinder"
        
        # CRISPRCasFinder will fail if the output directory already exists
        if ccf_out_dir.exists():
            import shutil
            shutil.rmtree(ccf_out_dir, ignore_errors=True)

        tmp_run_dir = output_dir / f".tmp_ccf_{input_file.stem}"
        if tmp_run_dir.exists():
            import shutil
            shutil.rmtree(tmp_run_dir, ignore_errors=True)
        tmp_run_dir.mkdir(parents=True)
        
        # Symlink all files from the installation directory into the sandbox
        # This satisfies CRISPRCasFinder's expectation to find its files (e.g. sel392v2.so, supplementary_files) in the current directory
        import os
        for item in ccf_dir.iterdir():
            if item.name == '.git':
                continue
            dest = tmp_run_dir / item.name
            if not dest.exists():
                try:
                    os.symlink(item, dest)
                except Exception:
                    pass
        
        # Copy input file to tmp_run_dir to avoid absolute path bugs in CRISPRCasFinder
        import shutil
        tmp_input_file = tmp_run_dir / input_file.name
        shutil.copy2(input_file, tmp_input_file)
        
        tmp_out_dir = tmp_run_dir / "result"

        # Build the command using the conda env's perl binary directly
        cmd = [
            str(perl_bin),
            str(ccf_script),
            "-in", tmp_input_file.name,
            "-cas",
            "-keep",
            "-out", tmp_out_dir.name,
            "-soFile", str(ccf_dir / "sel392v2.so"),
        ]

        # Build env with correct PATH, LD_LIBRARY_PATH
        env = self._build_env()

        print(f"[{self.name.upper()}] Running CRISPRCasFinder on {input_file.name}...")
        try:
            run_subprocess(cmd, check=True, cwd=str(tmp_run_dir), env=env)
            # Move result to final destination
            shutil.move(str(tmp_out_dir), str(ccf_out_dir))
            print(f"[{self.name.upper()}] Results saved at: {ccf_out_dir}")
            return ccf_out_dir
        except subprocess.CalledProcessError as e:
            print(f"[{self.name.upper()}] Error running CRISPRCasFinder on {input_file.name}:")
            raise e
        finally:
            if tmp_run_dir.exists():
                shutil.rmtree(tmp_run_dir, ignore_errors=True)

    def get_version(self) -> str:
        if not self.is_installed():
            return "Not Installed"

        env_dir = self._get_env_dir()
        ccf_dir = self._get_ccf_dir()
        perl_bin = env_dir / "bin" / "perl"
        ccf_script = ccf_dir / "CRISPRCasFinder.pl"

        if perl_bin.exists() and ccf_script.exists():
            try:
                env = self._build_env()
                res = subprocess.run(
                    [str(perl_bin), str(ccf_script), "-v"],
                    capture_output=True, text=True, errors="replace",
                    env=env, cwd=str(ccf_dir), timeout=15
                )
                output = ((res.stdout or "") + (res.stderr or "")).strip()
                if output:
                    for line in output.splitlines():
                        line = line.strip()
                        if line:
                            return line
            except Exception:
                pass

        return "Installed"
