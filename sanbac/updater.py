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
    import shutil
    conda_path = shutil.which("conda")
    if not conda_path:
        print("Conda not found on system path. Skipping external binary updates.")
        return False

    print("Checking/updating parsnp and mashtree to latest bioconda versions...")
    cmd = [conda_path, "update", "-y", "-c", "bioconda", "parsnp", "mashtree"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print("Conda update check completed successfully.")
            return True
        else:
            print("Notice: Conda update did not succeed (e.g. packages may not be installed in the active environment).")
            return False
    except Exception as e:
        print(f"Notice: Failed to run conda update: {e}")
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
