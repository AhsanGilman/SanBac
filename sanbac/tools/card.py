import shutil
import subprocess
import requests
import tarfile
from pathlib import Path
from .base import BaseTool, get_cmd_version, find_executable, run_subprocess
from ..config import config

class CardTool(BaseTool):
    @property
    def name(self) -> str:
        return "card"

    @property
    def description(self) -> str:
        return "CARD (Comprehensive Antibiotic Resistance Database) via RGI (Resistance Gene Identifier) for Antibiotic Resistance Genes (ARGs)"

    def _resolve_cmd(self) -> str:
        """Resolves the rgi executable path."""
        configured = config.get_executable("rgi")
        return find_executable(configured)

    def is_installed(self) -> bool:
        return self._resolve_cmd() is not None

    def update_db(self) -> bool:
        if not self.is_installed():
            print("Error: 'rgi' command not found. Please install RGI first.")
            return False

        card_dir = config.db_dir / "card"
        card_dir.mkdir(parents=True, exist_ok=True)
        
        tar_path = card_dir / "card_data.tar.gz"
        local_db_dir = card_dir / "localDB"

        url = "https://card.mcmaster.ca/latest/data"
        print(f"Downloading CARD database from {url}...")
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
        }
        try:
            response = requests.get(url, headers=headers, stream=True, timeout=60)
            response.raise_for_status()
            with open(tar_path, "wb") as f:
                shutil.copyfileobj(response.raw, f)
            print("Download complete.")
        except Exception as e:
            print(f"Error downloading CARD database: {e}")
            return False

        # Extract the tarball
        print("Extracting CARD database...")
        if local_db_dir.exists():
            try:
                shutil.rmtree(local_db_dir)
            except Exception:
                pass
        local_db_dir.mkdir(parents=True, exist_ok=True)

        try:
            with tarfile.open(tar_path, "r:*") as tar:
                tar.extractall(path=local_db_dir)
            print("Extraction complete.")
            if tar_path.exists():
                tar_path.unlink()
        except Exception as e:
            print(f"Error extracting CARD database: {e}")
            return False

        # Find card.json inside localDB
        card_json = local_db_dir / "card.json"
        if not card_json.exists():
            for p in local_db_dir.rglob("card.json"):
                card_json = p
                break
        
        if card_json.exists():
            print(f"Found card.json at {card_json}. Loading local database into RGI...")
            rgi_cmd = self._resolve_cmd() or config.get_executable("rgi")
            try:
                # Run rgi load --card_json ... --local inside local_db_dir
                run_subprocess(
                    [rgi_cmd, "load", "--card_json", str(card_json), "--local"],
                    cwd=str(local_db_dir),
                    capture_output=True,
                    text=True,
                    errors="replace",
                    check=True
                )
                print("RGI local database loaded successfully.")
                return True
            except subprocess.CalledProcessError as e:
                print(f"Error running rgi load: {e.stderr or e.stdout}")
                return False
        else:
            print("Error: card.json not found in the extracted files.")
            return False

    def before_run(self, output_dir: Path):
        db_source = config.db_dir / "card" / "localDB"

        # Check if database exists
        if not db_source.exists() or not any(db_source.iterdir()):
            print("CARD local database not found. Attempting download/build...")
            if not self.update_db():
                raise RuntimeError("Could not download or configure CARD database.")

        # Ensure localDB is in the current execution directory
        # as required by RGI --local flag
        cwd = Path.cwd()
        local_link = cwd / "localDB"
        
        if local_link.exists() or local_link.is_symlink():
            try:
                if local_link.is_symlink():
                    local_link.unlink()
                else:
                    shutil.rmtree(local_link)
            except Exception:
                pass

        try:
            # Try symlinking (fast, native on Linux)
            local_link.symlink_to(db_source, target_is_directory=True)
        except Exception:
            # Fallback to copy if symlinking fails
            try:
                shutil.copytree(db_source, local_link)
            except Exception as e:
                print(f"Warning: Failed to copy localDB to current folder: {e}")

    def after_run(self, output_dir: Path):
        cwd = Path.cwd()
        local_link = cwd / "localDB"
        if local_link.exists() or local_link.is_symlink():
            try:
                if local_link.is_symlink():
                    local_link.unlink()
                else:
                    shutil.rmtree(local_link)
            except Exception:
                pass

    def run(self, input_file: Path, output_dir: Path, threads: int) -> Path:
        rgi_cmd = self._resolve_cmd()
        if not rgi_cmd:
            raise FileNotFoundError("RGI is not installed or not in PATH.")

        output_dir.mkdir(parents=True, exist_ok=True)
        output_prefix = output_dir / input_file.stem
        
        cmd = [
            rgi_cmd,
            "main",
            "--input_sequence", str(input_file.resolve()),
            "--output_file", str(output_prefix.resolve()),
            "--local",
            "--clean",
            "-n", str(threads)
        ]
        
        print(f"[{self.name.upper()}] Analyzing {input_file.name} with {threads} thread(s)...")
        try:
            run_subprocess(cmd, capture_output=True, text=True, errors="replace", check=True)

            txt_output = Path(f"{output_prefix}.txt")
            json_output = Path(f"{output_prefix}.json")
            csv_output = Path(f"{output_prefix}.csv")

            if txt_output.exists():
                # Convert TXT (TSV) to CSV using python's built-in csv module
                try:
                    import csv
                    with open(txt_output, "r", encoding="utf-8", errors="replace") as f_in:
                        reader = csv.reader(f_in, delimiter="\t")
                        rows = list(reader)
                    with open(csv_output, "w", newline="", encoding="utf-8") as f_out:
                        writer = csv.writer(f_out)
                        writer.writerows(rows)
                    print(f"[{self.name.upper()}] CSV file saved at: {csv_output}")
                    
                    # Delete txt output only if CSV conversion succeeded
                    try:
                        txt_output.unlink()
                    except Exception:
                        pass
                except Exception as e:
                    print(f"[{self.name.upper()}] Error converting TXT to CSV: {e}")
                    # Keep the txt output as fallback if conversion failed

            if json_output.exists():
                # Delete json output
                try:
                    json_output.unlink()
                except Exception:
                    pass

            return csv_output
        except subprocess.CalledProcessError as e:
            print(f"[{self.name.upper()}] Error running CARD/RGI on {input_file.name}:")
            print(e.stderr or e.stdout)
            raise e

    def get_version(self) -> str:
        # Try importlib.metadata first since RGI is a Python package
        try:
            import importlib.metadata
            return importlib.metadata.version("rgi")
        except Exception:
            pass
        try:
            import rgi
            return rgi.__version__
        except Exception:
            pass

        cmd_path = self._resolve_cmd()
        if not cmd_path:
            return "Not Installed"

        # Since RGI is in an isolated conda env, run python in that env to query its version
        from pathlib import Path
        python_exe = Path(cmd_path).parent / "python"
        if python_exe.exists():
            try:
                res = run_subprocess(
                    [str(python_exe), "-c", "import rgi; print(rgi.__version__)"],
                    capture_output=True, text=True, errors="replace", timeout=5
                )
                if res.returncode == 0 and res.stdout.strip():
                    return res.stdout.strip()
            except Exception:
                pass
            try:
                res = run_subprocess(
                    [str(python_exe), "-c", "import importlib.metadata; print(importlib.metadata.version('rgi'))"],
                    capture_output=True, text=True, errors="replace", timeout=5
                )
                if res.returncode == 0 and res.stdout.strip():
                    return res.stdout.strip()
            except Exception:
                pass
        
        version_str = get_cmd_version([cmd_path], "--version")
        if "usage:" in version_str:
            help_str = get_cmd_version([cmd_path], "--help")
            for line in help_str.splitlines():
                if "version" in line.lower() or "rgi" in line.lower():
                    parts = line.strip().split()
                    for p in parts:
                        cleaned = p.strip("(),:;[]")
                        if cleaned and cleaned[0].isdigit() and cleaned.replace('.', '').isdigit():
                            return cleaned
            return "Unknown"
        return version_str
