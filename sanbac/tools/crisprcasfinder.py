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
        return get_tools_env_prefix() / "crisprcasfinder"

    def _get_ccf_dir(self) -> Path:
        return config.db_dir / "crisprcasfinder"

    def _build_env(self) -> dict:
        """Build a subprocess environment dict that points to the conda env's
        perl, python, and all other binaries — completely bypassing the system."""
        env_dir = self._get_env_dir()
        env = os.environ.copy()

        # Force the conda env's bin/ to the front of PATH
        env["PATH"] = str(env_dir / "bin") + os.pathsep + env.get("PATH", "")

        # Build PERL5LIB from every perl lib dir inside the conda env
        perl_lib_dirs = []
        for pattern in [
            str(env_dir / "lib" / "perl5" / "site_perl" / "*"),
            str(env_dir / "lib" / "perl5" / "site_perl"),
            str(env_dir / "lib" / "perl5" / "*"),
            str(env_dir / "lib" / "perl5"),
        ]:
            perl_lib_dirs.extend(glob.glob(pattern))

        # Also add any arch-specific dirs (e.g. x86_64-linux-thread-multi)
        for pattern in [
            str(env_dir / "lib" / "perl5" / "site_perl" / "*" / "*"),
            str(env_dir / "lib" / "perl5" / "*" / "*"),
        ]:
            for d in glob.glob(pattern):
                if Path(d).is_dir():
                    perl_lib_dirs.append(d)

        if perl_lib_dirs:
            env["PERL5LIB"] = os.pathsep.join(perl_lib_dirs)

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
        ccf_out_dir.mkdir(parents=True, exist_ok=True)

        # Build the command using the conda env's perl binary directly
        cmd = [
            str(perl_bin),
            str(ccf_script),
            "-in", str(input_file.resolve()),
            "-cas",
            "-keep",
            "-out", str(ccf_out_dir.resolve()),
        ]

        # Build env with correct PERL5LIB, PATH, LD_LIBRARY_PATH
        env = self._build_env()

        print(f"[{self.name.upper()}] Running CRISPRCasFinder on {input_file.name}...")
        try:
            run_subprocess(cmd, check=True, cwd=str(ccf_dir), env=env)
            print(f"[{self.name.upper()}] Results saved at: {ccf_out_dir}")
            return ccf_out_dir
        except subprocess.CalledProcessError as e:
            print(f"[{self.name.upper()}] Error running CRISPRCasFinder on {input_file.name}:")
            raise e

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
