import shutil
import subprocess
from pathlib import Path
from .base import BaseTool, get_cmd_version
from ..config import config

class MashtreeTool(BaseTool):
    @property
    def name(self) -> str:
        return "mashtree"

    @property
    def description(self) -> str:
        return "Mashtree phylogenetic tree generation using Mash distances"

    @property
    def run_per_file(self) -> bool:
        return False

    def is_installed(self) -> bool:
        mashtree_cmd = config.get_executable("mashtree")
        return shutil.which(mashtree_cmd) is not None

    def update_db(self) -> bool:
        # Mashtree does not use a database to download/update
        return True

    def run(self, input_file: Path, output_dir: Path, threads: int) -> Path:
        # Note: input_file is actually the input directory containing genomes
        mashtree_cmd = config.get_executable("mashtree")
        if not self.is_installed():
            raise FileNotFoundError("Mashtree is not installed or not in PATH.")

        from ..pipeline import discover_fasta_files
        fasta_files = discover_fasta_files(input_file)
        
        if not fasta_files:
            raise ValueError("No query genome files found to construct Mashtree.")

        # Ensure output directory exists
        output_dir.mkdir(parents=True, exist_ok=True)
        out_tree = output_dir / "mashtree.dnd"

        # Construct command
        cmd = [
            mashtree_cmd,
            "--numcpus", str(threads),
            "--outtree", str(out_tree)
        ]
        for f in fasta_files:
            cmd.append(str(f))

        print(f"[{self.name.upper()}] Running Mashtree alignment and tree generation...")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
            if result.returncode != 0:
                print(f"[{self.name.upper()}] Error running Mashtree:")
                print(result.stderr or result.stdout)
                raise subprocess.CalledProcessError(result.returncode, cmd, output=result.stdout, stderr=result.stderr)
            
            if out_tree.exists():
                print(f"[{self.name.upper()}] Phylogenetic tree saved at: {out_tree}")
                return out_tree
            else:
                raise FileNotFoundError(f"Expected Mashtree output tree not found at {out_tree}")
        except Exception as e:
            print(f"[{self.name.upper()}] Exception while running Mashtree: {e}")
            raise e

    def get_version(self) -> str:
        mashtree_cmd = config.get_executable("mashtree")
        return get_cmd_version([mashtree_cmd], "--version")
