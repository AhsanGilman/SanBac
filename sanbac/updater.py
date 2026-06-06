import os
import sys
import subprocess
from pathlib import Path
from .tools import load_tools

DEFAULT_REPO = "https://github.com/AhsanGilman/SanBac.git"

def update_databases(tool_name: str = None) -> bool:
    """Runs the database update function for all or specific tools."""
    tools = load_tools()
    
    if tool_name:
        if tool_name not in tools:
            print(f"Error: Tool '{tool_name}' is not registered.")
            return False
        targets = {tool_name: tools[tool_name]}
    else:
        targets = tools

    print("Starting database updates...\n")
    success = True
    for name, tool in targets.items():
        print(f"--- Updating database for tool: {name.upper()} ---")
        try:
            if tool.update_db():
                print(f"Success: Database for {name.upper()} is up to date.\n")
            else:
                print(f"Failed: Database update failed for {name.upper()}.\n")
                success = False
        except Exception as e:
            print(f"Error updating {name.upper()} database: {e}\n")
            success = False
    return success

def update_external_binaries() -> bool:
    """Attempts to update external binaries like parsnp and mashtree via conda."""
    conda_path = os.environ.get("CONDA_EXE")
    
    if not conda_path or not Path(conda_path).exists():
        import shutil
        conda_path = shutil.which("conda")
        
    if not conda_path:
        # Check common miniconda/anaconda installation paths
        home = Path.home()
        common_paths = [
            home / "miniconda3" / "bin" / "conda",
            home / "anaconda3" / "bin" / "conda",
            home / "miniconda" / "bin" / "conda",
            home / "anaconda" / "bin" / "conda",
            Path("/opt/conda/bin/conda"),
            Path("/opt/miniconda/bin/conda"),
            Path("/usr/local/bin/conda"),
            Path("/usr/bin/conda"),
        ]
        for p in common_paths:
            try:
                if p.exists() and os.access(p, os.X_OK):
                    conda_path = str(p)
                    break
            except Exception:
                pass

    if not conda_path:
        print("Conda executable not found on system path or common directories. Skipping external binary updates.")
        return False

    print("Installing/updating parsnp and mashtree to latest bioconda versions...")
    # Use -p sys.prefix to force installation into the active python environment
    cmd = [conda_path, "install", "-y", "-p", sys.prefix, "-c", "bioconda", "-c", "conda-forge", "parsnp", "mashtree"]
    try:
        print(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, check=False)
        if result.returncode == 0:
            print("Conda install/update completed successfully.")
            return True
        else:
            print(f"Notice: Conda install/update did not succeed (exit code {result.returncode}).")
            return False
    except Exception as e:
        print(f"Notice: Failed to run conda install: {e}")
        return False

def update_tool(repo_url: str = DEFAULT_REPO) -> bool:
    """
    Attempts to update the tool.
    If it's running inside a git clone (editable install), it runs `git pull`.
    Otherwise, it runs `pip install --upgrade git+<repo_url>`.
    """
    print(f"Checking for SanBac updates from repository: {repo_url}")
    
    # Check if we are running in a git repository context (editable mode)
    package_dir = Path(__file__).resolve().parent.parent
    git_dir = package_dir / ".git"
    
    if git_dir.exists():
        print("Detected local git repository. Pulling latest code via 'git pull'...")
        try:
            result = subprocess.run(
                ["git", "pull"],
                cwd=str(package_dir),
                capture_output=True,
                text=True,
                check=True
            )
            print(result.stdout)
            print("Successfully updated. Please reinstall if setup.py requirements changed.")
            update_external_binaries()
            return True
        except subprocess.CalledProcessError as e:
            print(f"Git pull failed: {e.stderr or e.stdout}")
            print("Falling back to pip upgrade...")
            
    # Run pip upgrade
    print("Running pip upgrade...")
    pip_cmd = [sys.executable, "-m", "pip", "install", "--upgrade", f"git+{repo_url}"]
    try:
        result = subprocess.run(
            pip_cmd,
            capture_output=True,
            text=True,
            check=True
        )
        print(result.stdout)
        print("SanBac has been successfully updated.")
        update_external_binaries()
        return True
    except subprocess.CalledProcessError as e:
        print(f"Pip upgrade failed: {e.stderr or e.stdout}")
        return False
