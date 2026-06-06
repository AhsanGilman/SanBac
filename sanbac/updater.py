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

def is_aarch64_system() -> bool:
    """Detect if we are running on an aarch64 system (either natively or emulated)."""
    import platform
    if platform.machine() == 'aarch64':
        return True
    try:
        cpuinfo = Path('/proc/cpuinfo').read_text()
        if 'aarch64' in cpuinfo.lower() or 'arm' in cpuinfo.lower():
            return True
    except Exception:
        pass
    if Path('/usr/x86_64-linux-gnu/lib').is_dir():
        return True
    return False


def _ensure_x86_64_compat() -> bool:
    """On aarch64 systems, ensure x86_64 binaries can run by setting up:
    1. The x86_64 dynamic linker (/lib64/ld-linux-x86-64.so.2)
    2. The x86_64 shared library path (LD_LIBRARY_PATH)
    3. A conda activation script to persist these settings
    """
    if not is_aarch64_system():
        return True

    cross_lib_dir = '/usr/x86_64-linux-gnu/lib'
    needs_install = False

    # Check if the cross-arch libraries are installed
    if not Path(cross_lib_dir).is_dir():
        needs_install = True

    # Check if the dynamic linker symlink exists
    ld_path = Path('/lib64/ld-linux-x86-64.so.2')
    if not ld_path.exists():
        needs_install = True

    if needs_install:
        print("\nDetected aarch64 system running x86_64 conda packages.")
        print("Setting up x86_64 compatibility layer (required for mashtree/perl)...")

        # Install libc6-amd64-cross if cross libs are missing
        if not Path(cross_lib_dir).is_dir():
            print("Installing x86_64 cross-architecture support (libc6-amd64-cross)...")
            result = subprocess.run(
                ['sudo', 'apt-get', 'install', '-y', 'libc6-amd64-cross'],
                check=False
            )
            if result.returncode != 0:
                _print_manual_compat_instructions()
                return False

        # Create the /lib64 dynamic linker symlink if missing
        if not ld_path.exists():
            cross_ld_paths = [
                Path('/usr/x86_64-linux-gnu/lib/ld-linux-x86-64.so.2'),
                Path('/usr/x86_64-linux-gnu/lib64/ld-linux-x86-64.so.2'),
            ]
            cross_ld = None
            for p in cross_ld_paths:
                if p.exists():
                    cross_ld = p
                    break

            if cross_ld:
                subprocess.run(['sudo', 'mkdir', '-p', '/lib64'], check=False)
                subprocess.run(
                    ['sudo', 'ln', '-sf', str(cross_ld), '/lib64/ld-linux-x86-64.so.2'],
                    check=False
                )
                if ld_path.exists():
                    print("x86_64 dynamic linker symlink created.")
                else:
                    _print_manual_compat_instructions()
                    return False
            else:
                _print_manual_compat_instructions()
                return False

    # Always set LD_LIBRARY_PATH for the current process
    _apply_x86_64_ld_path()

    # Persist the fix via a conda env activation script
    _create_conda_x86_64_activation_script()

    return True


def _apply_x86_64_ld_path():
    """Add x86_64 cross-lib directory and conda environment lib directory to LD_LIBRARY_PATH for the current process."""
    if not is_aarch64_system():
        return

    paths_to_add = []
    
    # 1. Cross-architecture library dir
    cross_lib_dir = '/usr/x86_64-linux-gnu/lib'
    if Path(cross_lib_dir).is_dir():
        paths_to_add.append(cross_lib_dir)
        
    # 2. Active Python conda environment's lib dir
    conda_lib_dir = Path(sys.prefix) / 'lib'
    if conda_lib_dir.is_dir():
        paths_to_add.append(str(conda_lib_dir))

    # 3. Environment variable CONDA_PREFIX lib dir
    conda_prefix = os.environ.get('CONDA_PREFIX')
    if conda_prefix:
        env_lib_dir = Path(conda_prefix) / 'lib'
        if env_lib_dir.is_dir():
            paths_to_add.append(str(env_lib_dir))

    current_ld = os.environ.get('LD_LIBRARY_PATH', '')
    current_ld_parts = [p.strip() for p in current_ld.split(':') if p.strip()]

    added_any = False
    for path in paths_to_add:
        if path not in current_ld_parts:
            current_ld_parts.insert(0, path)
            added_any = True

    if added_any:
        os.environ['LD_LIBRARY_PATH'] = ':'.join(current_ld_parts)


def _create_conda_x86_64_activation_script():
    """Create a conda activation script that sets LD_LIBRARY_PATH on env activation."""
    cross_lib_dir = '/usr/x86_64-linux-gnu/lib'
    activate_dir = Path(sys.prefix) / 'etc' / 'conda' / 'activate.d'
    activate_script = activate_dir / 'x86_64_compat.sh'

    try:
        activate_dir.mkdir(parents=True, exist_ok=True)
        # Always overwrite or write to ensure the latest LD_LIBRARY_PATH contents are present
        with open(activate_script, 'w') as f:
            f.write('#!/bin/sh\n')
            f.write(f'# Added by SanBac: x86_64 cross-arch library paths for aarch64 systems\n')
            f.write(f'export LD_LIBRARY_PATH="{cross_lib_dir}:$CONDA_PREFIX/lib:$LD_LIBRARY_PATH"\n')
        os.chmod(str(activate_script), 0o755)
        print(f"Created/updated conda activation script: {activate_script}")
        print("  (After reactivating your conda env, mashtree will work automatically)")
    except Exception as e:
        print(f"Warning: Could not create/update conda activation script: {e}")
        print(f"  You may need to manually run: export LD_LIBRARY_PATH={cross_lib_dir}:$CONDA_PREFIX/lib:$LD_LIBRARY_PATH")


def _print_manual_compat_instructions():
    """Print manual instructions for setting up x86_64 compatibility."""
    print("\nCould not set up x86_64 compatibility automatically.")
    print("Please run these commands manually, then re-run 'sanbac update-tool':")
    print("  sudo apt-get install -y libc6-amd64-cross")
    print("  sudo mkdir -p /lib64")
    print("  sudo ln -sf /usr/x86_64-linux-gnu/lib/ld-linux-x86-64.so.2 /lib64/ld-linux-x86-64.so.2")


def _verify_tool_runs(cmd_path: str) -> bool:
    """Check if a tool binary actually runs (not just exists)."""
    try:
        result = subprocess.run(
            [cmd_path, '--version'],
            capture_output=True, text=True, errors='replace', timeout=10
        )
        combined = (result.stdout or '') + (result.stderr or '')
        
        # Check specifically for shared library / linker / dynamic link issues
        linker_errors = [
            'error while loading shared libraries',
            'cannot open shared object file',
            'ld-linux-x86-64.so.2'
        ]
        for err in linker_errors:
            if err in combined:
                return False
                
        # If execution fails with shell missing binary or loader issues
        if 'No such file or directory' in combined and ('error' in combined or 'failed' in combined or result.returncode != 0):
            return False
            
        return True
    except Exception:
        return False


def update_external_binaries() -> bool:
    """Attempts to install/update external binaries like parsnp and mashtree via conda."""
    from .tools.base import find_executable

    # On aarch64 systems, set up x86_64 compatibility first
    # so we can verify if existing packages can run correctly
    _ensure_x86_64_compat()

    # Check which tools actually need installation
    tools_to_install = []
    tool_checks = {"parsnp": "parsnp", "mashtree": "mashtree"}
    
    for pkg_name, cmd_name in tool_checks.items():
        exe_path = find_executable(cmd_name)
        if exe_path is None:
            tools_to_install.append(pkg_name)
        elif not _verify_tool_runs(exe_path):
            print(f"  {pkg_name}: found at {exe_path} but cannot execute (architecture issue)")
            tools_to_install.append(pkg_name)
        else:
            print(f"  {pkg_name}: already installed ({exe_path})")

    # If on aarch64 and mashtree is being installed/updated, install libxcrypt
    # to supply the required x86_64 libcrypt.so.1 inside the conda environment
    if is_aarch64_system() and "mashtree" in tools_to_install:
        tools_to_install.append("libxcrypt")

    if not tools_to_install:
        print("All external tools (parsnp, mashtree) are already installed and working.")
        return True

    # Find conda executable
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
        print(f"Missing tools that need manual installation: {', '.join(tools_to_install)}")
        return False

    print(f"Installing missing tools: {', '.join(tools_to_install)}...")
    # Use -p sys.prefix to force installation into the active python environment
    cmd = [conda_path, "install", "-y", "-p", sys.prefix, "-c", "bioconda", "-c", "conda-forge"] + tools_to_install
    try:
        print(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, check=False)
        if result.returncode != 0:
            print(f"Notice: Conda install/update did not succeed (exit code {result.returncode}).")
            return False
            
        print("Conda install/update completed successfully.")
        
        # On aarch64 systems, set up x86_64 compatibility if needed
        _ensure_x86_64_compat()
        
        # Verify the install actually worked
        still_broken = []
        for pkg_name, cmd_name in tool_checks.items():
            exe_path = find_executable(cmd_name)
            if exe_path is None:
                still_broken.append((pkg_name, "not found"))
            elif not _verify_tool_runs(exe_path):
                still_broken.append((pkg_name, "found but cannot execute"))
            
        if still_broken:
            print(f"\nWarning: Some tools are still not working after installation:")
            for pkg_name, reason in still_broken:
                print(f"  {pkg_name}: {reason}")
            return False
        return True
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
