import shutil
import subprocess
import requests
import tarfile
from pathlib import Path
from .base import BaseTool, get_cmd_version
from ..config import config

class CardTool(BaseTool):
    @property
    def name(self) -> str:
        return "card"

    @property
    def description(self) -> str:
        return "CARD (Comprehensive Antibiotic Resistance Database) via RGI (Resistance Gene Identifier) for Antibiotic Resistance Genes (ARGs)"

    def is_installed(self) -> bool:
        rgi_cmd = config.get_executable("rgi")
        return shutil.which(rgi_cmd) is not None

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
            rgi_cmd = config.get_executable("rgi")
            try:
                # Run rgi load --card_json ... --local inside local_db_dir
                subprocess.run(
                    [rgi_cmd, "load", "--card_json", str(card_json), "--local"],
                    cwd=str(local_db_dir),
                    capture_output=True,
                    text=True,
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

    def run(self, input_file: Path, output_dir: Path, threads: int) -> Path:
        rgi_cmd = config.get_executable("rgi")
        if not self.is_installed():
            raise FileNotFoundError("RGI is not installed or not in PATH.")

        output_dir.mkdir(parents=True, exist_ok=True)
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
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            # Clean up the link in the execution path
            try:
                if local_link.is_symlink():
                    local_link.unlink()
                else:
                    shutil.rmtree(local_link)
            except Exception:
                pass

            txt_output = Path(f"{output_prefix}.txt")
            json_output = Path(f"{output_prefix}.json")
            csv_output = Path(f"{output_prefix}.csv")

            if txt_output.exists():
                # Convert TXT to CSV using pandas
                try:
                    import pandas as pd
                    df = pd.read_csv(txt_output, sep="\t")
                    df.to_csv(csv_output, index=False)
                    print(f"[{self.name.upper()}] CSV file saved at: {csv_output}")
                except Exception as e:
                    print(f"[{self.name.upper()}] Error converting TXT to CSV: {e}")
                
                # Delete txt output
                try:
                    txt_output.unlink()
                except Exception:
                    pass

            if json_output.exists():
                # Delete json output
                try:
                    json_output.unlink()
                except Exception:
                    pass

            return csv_output
        except subprocess.CalledProcessError as e:
            # Try to clean up local link on failure as well
            try:
                if local_link.is_symlink():
                    local_link.unlink()
                else:
                    shutil.rmtree(local_link)
            except Exception:
                pass
            print(f"[{self.name.upper()}] Error running CARD/RGI on {input_file.name}:")
            print(e.stderr or e.stdout)
            raise e

    def get_version(self) -> str:
        rgi_cmd = config.get_executable("rgi")
        return get_cmd_version([rgi_cmd], "--version")
