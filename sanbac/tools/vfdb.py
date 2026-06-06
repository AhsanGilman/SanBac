import gzip
import shutil
import subprocess
import requests
from pathlib import Path
from .base import BaseTool, get_cmd_version
from ..config import config

class VfdbTool(BaseTool):
    @property
    def name(self) -> str:
        return "vfdb"

    @property
    def description(self) -> str:
        return "VFDB (Virulence Factor Database) blastn alignment for identifying virulence factor genes"

    def is_installed(self) -> bool:
        blastn_cmd = config.get_executable("blastn")
        makeblastdb_cmd = config.get_executable("makeblastdb")
        return shutil.which(blastn_cmd) is not None and shutil.which(makeblastdb_cmd) is not None

    def update_db(self) -> bool:
        if not self.is_installed():
            print("Error: BLAST tools ('blastn' or 'makeblastdb') not found. Please install NCBI BLAST+.")
            return False

        vfdb_dir = config.db_dir / "vfdb"
        vfdb_dir.mkdir(parents=True, exist_ok=True)
        
        fasta_gz = vfdb_dir / "VFDB_setB_nt.fas.gz"
        fasta_file = vfdb_dir / "VFDB_setB_nt.fas"
        db_prefix = vfdb_dir / "vfdb_db"

        # Download the full (core + predicted) VFDB dataset
        url = "https://www.mgc.ac.cn/VFs/Down/VFDB_setB_nt.fas.gz"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
        }
        print(f"Downloading full VFDB database from {url}...")
        try:
            response = requests.get(url, headers=headers, stream=True, timeout=60)
            if response.status_code == 200:
                with open(fasta_gz, "wb") as f:
                    shutil.copyfileobj(response.raw, f)
            else:
                fallback_url = "https://www.mgc.ac.cn/VFs/Down/VFDB_setB_nt.fas"
                print(f"Gzip file not found (HTTP {response.status_code}). Trying fallback URL: {fallback_url}...")
                res_fb = requests.get(fallback_url, headers=headers, timeout=60)
                res_fb.raise_for_status()
                with open(fasta_file, "wb") as f:
                    f.write(res_fb.content)
        except Exception as e:
            print(f"Error downloading VFDB: {e}")
            return False

        # Extract if gzipped
        if fasta_gz.exists():
            print("Extracting VFDB_setB_nt.fas.gz...")
            try:
                with gzip.open(fasta_gz, 'rb') as f_in:
                    with open(fasta_file, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                fasta_gz.unlink()
            except Exception as e:
                print(f"Error extracting database file: {e}")
                return False

        print("Building BLAST database for VFDB...")
        makeblastdb_cmd = config.get_executable("makeblastdb")
        cmd = [
            makeblastdb_cmd,
            "-in", str(fasta_file),
            "-dbtype", "nucl",
            "-out", str(db_prefix)
        ]
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            print("VFDB BLAST database built successfully.")
            return True
        except subprocess.CalledProcessError as e:
            print(f"Error running makeblastdb: {e.stderr or e.stdout}")
            return False

    def run(self, input_file: Path, output_dir: Path, threads: int) -> Path:
        if not self.is_installed():
            raise FileNotFoundError("BLAST+ tools ('blastn' / 'makeblastdb') are not installed or not in PATH.")

        output_dir.mkdir(parents=True, exist_ok=True)
        vfdb_dir = config.db_dir / "vfdb"
        db_prefix = vfdb_dir / "vfdb_db"
        
        # Check if database files exist
        if not (db_prefix.with_suffix(".nhr").exists() or db_prefix.with_suffix(".nin").exists() or db_prefix.with_suffix(".nsq").exists()):
            print(f"VFDB database not found at {db_prefix}. Attempting download/build...")
            if not self.update_db():
                raise RuntimeError("Could not find or build VFDB database.")

        raw_output_file = output_dir / f"{input_file.stem}_results_virulence_detailed_raw.tmp"
        blastn_cmd = config.get_executable("blastn")
        
        # Run BLASTn with custom 15-column format
        cmd = [
            blastn_cmd,
            "-query", str(input_file),
            "-db", str(db_prefix),
            "-out", str(raw_output_file),
            "-outfmt", "6 qseqid sseqid pident length mismatch gapopen qstart qend sstart send evalue bitscore qlen slen stitle",
            "-num_threads", str(threads)
        ]

        print(f"[{self.name.upper()}] Running blastn against VFDB database for {input_file.name}...")
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            # Parse, filter, calculate coverage, and format output
            print(f"[{self.name.upper()}] Filtering significant hits for {input_file.name}...")
            filtered_lines = []
            
            # Write header
            filtered_lines.append("qseqid\tsseqid\tpident\tlength\tmismatch\tgapopen\tqstart\tqend\tsstart\tsend\tevalue\tbitscore\tqlen\tslen\tscov(%)\tproduct")
            
            if raw_output_file.exists():
                with open(raw_output_file, "r") as infile:
                    for line in infile:
                        parts = line.strip().split("\t")
                        if len(parts) < 15:
                            continue
                        
                        try:
                            pident = float(parts[2])
                            length = int(parts[3])
                            evalue = float(parts[10])
                            bitscore = float(parts[11])
                            qlen = int(parts[12])
                            slen = int(parts[13])
                            
                            # Re-join all fields from the 15th column onwards as product
                            product = " ".join(parts[14:])
                            
                            # Coverage calculation: (alignment_length / query_length) * 100
                            qcov = (length / qlen) * 100
                            
                            # Apply strict filter rules
                            if pident >= 80.0 and qcov >= 80.0 and evalue <= 1e-5:
                                formatted = f"{parts[0]}\t{parts[1]}\t{pident:.3f}\t{length}\t{parts[4]}\t{parts[5]}\t{parts[6]}\t{parts[7]}\t{parts[8]}\t{parts[9]}\t{evalue:.2e}\t{bitscore:.1f}\t{qlen}\t{slen}\t{qcov:.2f}\t{product}"
                                filtered_lines.append(formatted)
                        except ValueError:
                            continue
                
                # Delete temporary raw file
                raw_output_file.unlink()
            
            # Create the gene summary (cut -f2 | sort | uniq -c | sort -nr)
            summary_output_file = output_dir / f"{input_file.stem}.txt"
            from collections import Counter
            sseqid_counts = Counter()
            
            # Skip header (index 0)
            for line in filtered_lines[1:]:
                parts = line.split("\t")
                if len(parts) > 1:
                    sseqid = parts[1]
                    sseqid_counts[sseqid] += 1
            
            # Sort by count (descending), then by sseqid (ascending)
            sorted_counts = sorted(sseqid_counts.items(), key=lambda x: (-x[1], x[0]))
            
            # Write summary file matching the 'uniq -c' formatting
            with open(summary_output_file, "w") as sum_file:
                for sseqid, count in sorted_counts:
                    sum_file.write(f"{count:>7} {sseqid}\n")
                    
            print(f"[{self.name.upper()}] Virulence summary saved at: {summary_output_file}")
            return summary_output_file
            
        except subprocess.CalledProcessError as e:
            if raw_output_file.exists():
                try:
                    raw_output_file.unlink()
                except Exception:
                    pass
            print(f"[{self.name.upper()}] Error running blastn on {input_file.name}:")
            print(e.stderr or e.stdout)
            raise e

    def get_version(self) -> str:
        blastn_cmd = config.get_executable("blastn")
        return get_cmd_version([blastn_cmd], "-version")
