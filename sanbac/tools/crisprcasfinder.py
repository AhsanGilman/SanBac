import os
import shutil
import subprocess
import sys
from pathlib import Path
from .base import BaseTool, run_subprocess

class CrisprcasfinderTool(BaseTool):
    @property
    def name(self) -> str:
        return "crisprcasfinder"

    @property
    def description(self) -> str:
        return "CRISPRCasFinder: Identifies CRISPR arrays and Cas proteins."

    def is_installed(self) -> bool:
        ccf_dir = Path.home() / "CRISPRCasFinder"
        if not ccf_dir.exists():
            return False
            
        try:
            conda_path = shutil.which("conda")
            if not conda_path:
                return False
            res = subprocess.run([conda_path, "env", "list"], capture_output=True, text=True, check=True)
            if "crisprcasfinder" not in res.stdout:
                return False
            return True
        except Exception:
            return False

    def update_db(self) -> bool:
        script_content = """#!/bin/bash
set -e
echo "==========================================="
echo " CRISPRCasFinder Automatic Installation"
echo "==========================================="
if ! command -v conda >/dev/null 2>&1; then
    echo "ERROR: Conda is not installed."
    exit 1
fi
source "$(conda info --base)/etc/profile.d/conda.sh"
ENV_NAME="crisprcasfinder"
if conda env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
    echo "Conda environment '$ENV_NAME' already exists."
else
    echo "Creating Conda environment '$ENV_NAME'..."
    conda create -y -n "$ENV_NAME" python=3.10 perl
fi
conda activate "$ENV_NAME"
conda config --add channels conda-forge || true
conda config --add channels bioconda || true
conda config --set channel_priority strict
conda install -y -c conda-forge -c bioconda perl perl-app-cpanminus perl-bioperl macsyfinder=2.1.2 vmatch emboss prodigal hmmer blast bedtools muscle mafft clustalw viennarna wget curl libgomp
cpanm Date::Calc File::Which XML::Simple Parallel::ForkManager || true
macsydata install -u CASFinder==3.1.0 || true
cd ~
if [ ! -d CRISPRCasFinder ]; then
    git clone https://github.com/dcouvin/CRISPRCasFinder.git
fi
cd CRISPRCasFinder
cd $CONDA_PREFIX/lib
if [ ! -e libgomp.so.1 ]; then
    ln -s libgomp.so.1.0.0 libgomp.so.1 || true
fi
mkdir -p $CONDA_PREFIX/etc/conda/activate.d
cat > $CONDA_PREFIX/etc/conda/activate.d/env_vars.sh << EOF
export LD_LIBRARY_PATH=\\$CONDA_PREFIX/lib:\\$LD_LIBRARY_PATH
EOF
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
        ccf_dir = Path.home() / "CRISPRCasFinder"
        ccf_script = ccf_dir / "CRISPRCasFinder.pl"
        
        if not self.is_installed() or not ccf_script.exists():
            print("CRISPRCasFinder not found. Attempting download/build...")
            if not self.update_db():
                raise RuntimeError("Could not find or build CRISPRCasFinder.")
                
        output_dir.mkdir(parents=True, exist_ok=True)
        ccf_out_dir = output_dir / f"{input_file.stem}_crisprcasfinder"
        ccf_out_dir.mkdir(parents=True, exist_ok=True)
        
        bash_cmd = f"""
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate crisprcasfinder
cd "{ccf_dir}"
perl CRISPRCasFinder.pl -in "{input_file.resolve()}" -cas -keep -out "{ccf_out_dir.resolve()}"
"""
        
        import tempfile
        run_file = Path(tempfile.gettempdir()) / "run_ccf.sh"
        run_file.write_text(bash_cmd)
        
        print(f"[{self.name.upper()}] Running CRISPRCasFinder on {input_file.name}...")
        try:
            run_subprocess(["bash", str(run_file)], check=True)
            print(f"[{self.name.upper()}] Results saved at: {ccf_out_dir}")
            return ccf_out_dir
        except subprocess.CalledProcessError as e:
            print(f"[{self.name.upper()}] Error running CRISPRCasFinder on {input_file.name}:")
            raise e
        finally:
            if run_file.exists():
                run_file.unlink()

    def get_version(self) -> str:
        if not self.is_installed():
            return "Not Installed"
        return "Installed"
