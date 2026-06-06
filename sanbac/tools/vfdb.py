import gzip
import shutil
import subprocess
import requests
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
        
        fasta_gz = vfdb_dir / "VFDB_setB_pro.fas.gz"
        fasta_file = vfdb_dir / "VFDB_setB_pro.fas"
        db_prefix = vfdb_dir / "vfdb"

        urls_to_try = [
            ("https://www.mgc.ac.cn/VFs/Down/VFDB_setB_pro.fas.gz", True),
            ("http://www.mgc.ac.cn/VFs/Down/VFDB_setB_pro.fas.gz", True),
            ("https://www.mgc.ac.cn/VFs/Down/VFDB_setB_pro.fas", False),
            ("http://www.mgc.ac.cn/VFs/Down/VFDB_setB_pro.fas", False),
        ]
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
        }

        success = False
        for url, is_gzip in urls_to_try:
            target_path = fasta_gz if is_gzip else fasta_file
            print(f"Downloading VFDB database from {url}...")
            try:
                response = requests.get(url, headers=headers, stream=True, timeout=15)
                if response.status_code == 200:
                    total_size = int(response.headers.get('content-length', 0))
                    downloaded = 0
                    chunk_size = 1024 * 64
                    with open(target_path, "wb") as f:
                        for chunk in response.iter_content(chunk_size=chunk_size):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                if total_size > 0:
                                    percent = (downloaded / total_size) * 100
                                    if (downloaded // chunk_size) % 10 == 0:
                                        print(f"  Downloaded: {downloaded / (1024 * 1024):.2f} MB / {total_size / (1024 * 1024):.2f} MB ({percent:.1f}%)", flush=True)
                                else:
                                    if (downloaded // chunk_size) % 10 == 0:
                                        print(f"  Downloaded: {downloaded / (1024 * 1024):.2f} MB", flush=True)
                    print("Download completed successfully.")
                    success = True
                    break
                else:
                    print(f"  HTTP status code: {response.status_code}. Trying next URL...")
            except Exception as e:
                print(f"  Error or timeout downloading from {url}: {e}. Trying next URL...")

        if not success:
            print("Error: All download attempts for VFDB database failed.")
            return False

        # Extract if gzipped
        if fasta_gz.exists():
            print("Extracting VFDB_setB_pro.fas.gz...")
            try:
                with gzip.open(fasta_gz, 'rb') as f_in:
                    with open(fasta_file, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                fasta_gz.unlink()
            except Exception as e:
                print(f"Error extracting database file: {e}")
                return False

        print("Building DIAMOND database for VFDB...")
        diamond_cmd = self._resolve_diamond()
        cmd = [
            diamond_cmd,
            "makedb",
            "--in", str(fasta_file),
            "-d", str(db_prefix)
        ]
        try:
            run_subprocess(cmd, capture_output=True, text=True, errors="replace", check=True)
            print("VFDB DIAMOND database built successfully.")
            return True
        except subprocess.CalledProcessError as e:
            print(f"Error running diamond makedb: {e.stderr or e.stdout}")
            return False

    def run(self, input_file: Path, output_dir: Path, threads: int) -> Path:
        diamond_cmd = self._resolve_diamond()
        if not diamond_cmd:
            raise FileNotFoundError("DIAMOND is not installed or not in PATH.")

        output_dir.mkdir(parents=True, exist_ok=True)
        vfdb_dir = config.db_dir / "vfdb"
        db_prefix = vfdb_dir / "vfdb"
        
        # Check if database file exists
        if not db_prefix.with_suffix(".dmnd").exists():
            print(f"VFDB database not found at {db_prefix}. Attempting download/build...")
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

        raw_output_file = output_dir / f"{input_file.stem}_results_virulence_detailed_raw.tmp"
        
        # Run DIAMOND blastp with requested parameters
        cmd = [
            diamond_cmd,
            "blastp",
            "-q", str(prokka_faa_path),
            "-d", str(db_prefix),
            "-o", str(raw_output_file),
            "--outfmt", "6", "qseqid", "sseqid", "salltitles", "pident", "qcovhsp", "evalue", "bitscore",
            "--id", "80",
            "--query-cover", "80",
            "--subject-cover", "80",
            "--max-target-seqs", "1",
            "--threads", str(threads)
        ]

        print(f"[{self.name.upper()}] Running DIAMOND blastp against VFDB database for {input_file.name}...")
        try:
            run_subprocess(cmd, capture_output=True, text=True, errors="replace", check=True)
            
            detailed_output_file = output_dir / f"{input_file.stem}_results.tsv"
            headers = "Query_Gene\tVFDB_ID\tVFDB_Description\tIdentity\tQuery_Coverage\tEvalue\tBitscore\n"
            
            with open(detailed_output_file, "w", encoding="utf-8") as outfile:
                outfile.write(headers)
                if raw_output_file.exists():
                    with open(raw_output_file, "r", encoding="utf-8", errors="replace") as infile:
                        shutil.copyfileobj(infile, outfile)
            
            # Clean up raw output file
            if raw_output_file.exists():
                raw_output_file.unlink()
                
            print(f"[{self.name.upper()}] Virulence hits saved at: {detailed_output_file}")
            return detailed_output_file
            
        except subprocess.CalledProcessError as e:
            if raw_output_file.exists():
                try:
                    raw_output_file.unlink()
                except Exception:
                    pass
            print(f"[{self.name.upper()}] Error running DIAMOND blastp on {input_file.name}:")
            print(e.stderr or e.stdout)
            raise e

    def get_version(self) -> str:
        cmd_path = self._resolve_diamond()
        if not cmd_path:
            return "Not Installed"
        return get_cmd_version([cmd_path], "version")
