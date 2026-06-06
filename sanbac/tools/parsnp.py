import shutil
import subprocess
from pathlib import Path
from .base import BaseTool, get_cmd_version, find_executable, run_subprocess
from ..config import config

class ParsnpTool(BaseTool):
    def __init__(self):
        self.reference_parsnp = None

    @property
    def name(self) -> str:
        return "parsnp"

    @property
    def description(self) -> str:
        return "Parsnp core genome alignment and phylogenetic tree generation"

    @property
    def run_per_file(self) -> bool:
        return False

    def _resolve_cmd(self) -> str:
        """Resolves the parsnp executable path."""
        configured = config.get_executable("parsnp")
        return find_executable(configured)

    def is_installed(self) -> bool:
        return self._resolve_cmd() is not None

    def update_db(self) -> bool:
        # Parsnp doesn't use a database to download/update
        return True

    def run(self, input_file: Path, output_dir: Path, threads: int) -> Path:
        # Note: input_file is actually the input directory containing genomes
        parsnp_cmd = self._resolve_cmd()
        if not parsnp_cmd:
            raise FileNotFoundError("Parsnp is not installed or not in PATH.")

        if not self.reference_parsnp:
            raise ValueError("Reference genome file path is required for Parsnp.")

        ref_path = Path(self.reference_parsnp).resolve()
        
        # Create a temporary directory for query genomes under output_dir.parent
        # to ensure that the reference file is excluded (if it is in the input dir)
        # and that we only run on valid fasta/fna files.
        temp_query_dir = output_dir.parent / "temp_parsnp_query_genomes"
        if temp_query_dir.exists():
            try:
                shutil.rmtree(temp_query_dir)
            except Exception:
                pass
        temp_query_dir.mkdir(parents=True, exist_ok=True)
        
        from ..pipeline import discover_fasta_files
        fasta_files = discover_fasta_files(input_file)
        
        copied_any = False
        for f in fasta_files:
            if f.resolve() == ref_path:
                continue
            shutil.copy(f, temp_query_dir)
            copied_any = True

        if not copied_any:
            # Clean up empty temp_query_dir
            try:
                temp_query_dir.rmdir()
            except Exception:
                pass
            raise ValueError("No query genome files found to align (or only the reference genome was found in the input directory).")

        # Ensure output_dir does not exist so parsnp can create it and doesn't complain
        if output_dir.exists():
            try:
                shutil.rmtree(output_dir)
            except Exception as e:
                print(f"Warning: Failed to remove existing output directory {output_dir}: {e}")

        # Run parsnp with -c (curated directory) flag to ignore MUMi distance filtering
        # and ensure a tree is generated even for slightly divergent draft genomes.
        cmd = [
            parsnp_cmd,
            "-c",
            "-r", str(ref_path),
            "-d", str(temp_query_dir),
            "-o", str(output_dir),
            "-p", str(threads)
        ]

        print(f"[{self.name.upper()}] Running Parsnp core genome alignment...")
        try:
            # Run the command
            result = run_subprocess(cmd, capture_output=True, text=True, errors="replace")
            if result.returncode != 0:
                print(f"[{self.name.upper()}] Error running Parsnp:")
                print(result.stderr or result.stdout)
                raise subprocess.CalledProcessError(result.returncode, cmd, output=result.stdout, stderr=result.stderr)
            
            # Find the tree file recursively in the output directory
            found_tree_path = None
            for p in output_dir.rglob("*.tree"):
                found_tree_path = p
                break

            # If not found under *.tree, check standard name
            if not found_tree_path:
                standard_tree = output_dir / "parsnp.tree"
                if standard_tree.exists():
                    found_tree_path = standard_tree

            if found_tree_path and found_tree_path.exists():
                # Move tree file to a temporary location outside output_dir
                temp_tree = output_dir.parent / "temp_parsnp_tree.tree"
                shutil.move(found_tree_path, temp_tree)

                # Clean up the entire output directory
                try:
                    shutil.rmtree(output_dir)
                except Exception:
                    pass

                # Recreate the output directory and move the tree file back
                output_dir.mkdir(parents=True, exist_ok=True)
                dest_tree = output_dir / "presnp_treee.tree"
                shutil.move(temp_tree, dest_tree)
                
                print(f"[{self.name.upper()}] Phylogenetic tree saved at: {dest_tree}")
                return dest_tree
            else:
                raise FileNotFoundError(f"Expected Parsnp output tree file not found in {output_dir}")
                
        finally:
            # Clean up temp_query_dir
            try:
                shutil.rmtree(temp_query_dir)
            except Exception as e:
                print(f"Warning: Failed to clean up temporary directory {temp_query_dir}: {e}")

    def get_version(self) -> str:
        cmd_path = self._resolve_cmd()
        if not cmd_path:
            return "Not Installed"
        v = get_cmd_version([cmd_path], "--version")
        if v in ("Unknown", ""):
            v = get_cmd_version([cmd_path], "-h")
            if v and v != "Not Installed" and v != "Unknown":
                v = v.replace("|--", "").replace("--|", "").strip()
        return v
