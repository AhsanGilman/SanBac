import shutil
import subprocess
from pathlib import Path
from .base import BaseTool, get_cmd_version, find_executable, run_subprocess
from ..config import config

class VfdbTool(BaseTool):
    @property
    def name(self) -> str:
        return "vfdb"

    @property
    def description(self) -> str:
        return "VFDB (Virulence Factor Database) DIAMOND blastp alignment for identifying virulence factor genes"

    def _resolve_diamond(self) -> str:
        configured = config.get_executable("diamond")
        return find_executable(configured)

    def is_installed(self) -> bool:
        return self._resolve_diamond() is not None

    def update_db(self) -> bool:
        if not self.is_installed():
            print("Error: DIAMOND tool ('diamond') not found. Please install DIAMOND first.")
            return False

        vfdb_dir = config.db_dir / "vfdb"
        vfdb_dir.mkdir(parents=True, exist_ok=True)

        try:
            # 1. Download VFDB protein database
            run_subprocess(
                ["wget", "https://www.mgc.ac.cn/VFs/Down/VFDB_setB_pro.fas.gz"],
                cwd=str(vfdb_dir),
                check=True
            )

            run_subprocess(
                ["gunzip", "VFDB_setB_pro.fas.gz"],
                cwd=str(vfdb_dir),
                check=True
            )

            # 3. Create DIAMOND database
            db_sub_dir = vfdb_dir / "databases" / "vfdb"
            db_sub_dir.mkdir(parents=True, exist_ok=True)

            shutil.copy(vfdb_dir / "VFDB_setB_pro.fas", db_sub_dir / "VFDB_setB_pro.fas")

            diamond_cmd = self._resolve_diamond()
            makedb_cmd = [
                diamond_cmd,
                "makedb",
                "--in", "databases/vfdb/VFDB_setB_pro.fas",
                "-d", "databases/vfdb/vfdb"
            ]
            run_subprocess(makedb_cmd, cwd=str(vfdb_dir), check=True)
            print("VFDB DIAMOND database built successfully.")
            return True
        except Exception as e:
            print(f"Error updating VFDB database: {e}")
            return False

    def run(self, input_file: Path, output_dir: Path, threads: int) -> Path:
        diamond_cmd = self._resolve_diamond()
        if not diamond_cmd:
            raise FileNotFoundError("DIAMOND is not installed or not in PATH.")

        output_dir.mkdir(parents=True, exist_ok=True)
        vfdb_dir = config.db_dir / "vfdb"
        
        # Check if database file exists
        db_file = vfdb_dir / "databases" / "vfdb" / "vfdb.dmnd"
        if not db_file.exists():
            print(f"VFDB database not found. Attempting download/build...")
            if not self.update_db():
                raise RuntimeError("Could not find or build VFDB database.")

        # Ensure Prokka protein sequence (.faa) output is present
        prokka_faa_path = output_dir.parent / "prokka" / input_file.stem / f"{input_file.stem}.faa"
        if not prokka_faa_path.exists():
            print(f"[{self.name.upper()}] Prokka output not found at {prokka_faa_path}. Running Prokka first...")
            from .prokka import ProkkaTool
            prokka_tool = ProkkaTool()
            if not prokka_tool.is_installed():
                raise FileNotFoundError("Prokka is not installed but is required to generate proteins for VFDB.")
            
            prokka_outdir = output_dir.parent / "prokka"
            prokka_tool.run(input_file, prokka_outdir, threads)
            
            if not prokka_faa_path.exists():
                raise FileNotFoundError(f"Prokka ran but did not produce expected protein file at {prokka_faa_path}")

        detailed_output_file = output_dir / f"{input_file.stem}_results.tsv"
        
        # Setup temp folder to match path format: prokka_out/sample.faa
        prokka_out_dir = vfdb_dir / "prokka_out"
        prokka_out_dir.mkdir(parents=True, exist_ok=True)
        
        temp_faa = prokka_out_dir / f"{input_file.stem}.faa"
        shutil.copy(prokka_faa_path, temp_faa)
        
        # 5. Run DIAMOND and export gene descriptions directly
        cmd = [
            diamond_cmd,
            "blastp",
            "-q", f"prokka_out/{input_file.stem}.faa",
            "-d", "databases/vfdb/vfdb",
            "-o", f"{input_file.stem}_results.tsv",
            "--outfmt", "6", "qseqid", "sseqid", "salltitles", "pident", "qcovhsp", "evalue", "bitscore",
            "--id", "80",
            "--query-cover", "80",
            "--subject-cover", "80",
            "--max-target-seqs", "1",
            "--threads", str(threads)
        ]

        print(f"[{self.name.upper()}] Running DIAMOND blastp against VFDB database for {input_file.name}...")
        try:
            run_subprocess(cmd, cwd=str(vfdb_dir), check=True)
            
            # 6. Add a readable header
            sed_cmd = [
                "sed", "-i",
                "1iQuery_Gene\tVFDB_ID\tVFDB_Description\tIdentity\tQuery_Coverage\tEvalue\tBitscore",
                f"{input_file.stem}_results.tsv"
            ]
            run_subprocess(sed_cmd, cwd=str(vfdb_dir), check=True)
            
            # Move the output file to the final destination
            shutil.move(vfdb_dir / f"{input_file.stem}_results.tsv", detailed_output_file)
            
            # Cleanup temp files
            if temp_faa.exists():
                temp_faa.unlink()
            if prokka_out_dir.exists():
                try:
                    shutil.rmtree(prokka_out_dir)
                except Exception:
                    pass
            
            print(f"[{self.name.upper()}] Virulence hits saved at: {detailed_output_file}")
            return detailed_output_file
            
        except subprocess.CalledProcessError as e:
            if temp_faa.exists():
                temp_faa.unlink()
            print(f"[{self.name.upper()}] Error running DIAMOND blastp on {input_file.name}:")
            print(e.stderr or e.stdout)
            raise e

    def get_version(self) -> str:
        cmd_path = self._resolve_diamond()
        if not cmd_path:
            return "Not Installed"
        return get_cmd_version([cmd_path], "version")
