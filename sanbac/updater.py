import os
import sys
import subprocess
from pathlib import Path
from .tools import load_tools

DEFAULT_REPO = "https://github.com/AhsanGilman/SanBac.git"

def update_databases(tool_name: str = None, only_installed: bool = False) -> bool:
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
        if only_installed and not tool.is_installed():
            print(f"--- Skipping database update for tool: {name.upper()} (Not Installed) ---")
            continue
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

def get_tools_env_prefix() -> Path:
    """Gets the base path where isolated conda environments for external tools should be created."""
    prefix = Path(sys.prefix)
    
    # Check if we are in a conda environment
    in_conda = (
        os.environ.get('CONDA_PREFIX') is not None or
        (prefix / 'conda-meta').is_dir() or
        prefix.parent.name == 'envs'
    )
    
    if in_conda:
        # Nest tools inside the active conda environment's directory.
        # This keeps the global conda env list clean and ensures tool envs 
        # are automatically deleted if the main sanbac environment is removed.
        return prefix / "isolated_tools"
            
    # Fallback for system python / non-conda: try to find standard conda envs dir
    return Path.home() / ".conda" / "envs"


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

    # 4. Isolated tools environment's lib dirs
    tools_base_dir = get_tools_env_prefix()
    if tools_base_dir.is_dir():
        for sub_dir in tools_base_dir.iterdir():
            if sub_dir.is_dir() and sub_dir.name.startswith("sanbac_") and (sub_dir / 'lib').is_dir():
                paths_to_add.append(str(sub_dir / 'lib'))

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

    # Get tools env lib dirs
    tools_base_dir = get_tools_env_prefix()
    tools_libs = []
    if tools_base_dir.is_dir():
        for sub_dir in tools_base_dir.iterdir():
            if sub_dir.is_dir() and sub_dir.name.startswith("sanbac_") and (sub_dir / 'lib').is_dir():
                tools_libs.append(str(sub_dir / 'lib'))
    tools_lib_str = ":".join(tools_libs)
    if tools_lib_str:
        tools_lib_str += ":"

    try:
        activate_dir.mkdir(parents=True, exist_ok=True)
        # Always overwrite or write to ensure the latest LD_LIBRARY_PATH contents are present
        with open(activate_script, 'w') as f:
            f.write('#!/bin/sh\n')
            f.write(f'# Added by SanBac: x86_64 cross-arch library paths for aarch64 systems\n')
            f.write(f'export LD_LIBRARY_PATH="{cross_lib_dir}:$CONDA_PREFIX/lib:{tools_lib_str}$LD_LIBRARY_PATH"\n')
        os.chmod(str(activate_script), 0o755)
        print(f"Created/updated conda activation script: {activate_script}")
        print("  (After reactivating your conda env, mashtree will work automatically)")
    except Exception as e:
        print(f"Warning: Could not create/update conda activation script: {e}")
        print(f"  You may need to manually run: export LD_LIBRARY_PATH={cross_lib_dir}:$CONDA_PREFIX/lib:{tools_lib_str}$LD_LIBRARY_PATH")


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
        from .tools.base import run_subprocess
        result = run_subprocess(
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


def update_external_binaries(tool_name: str = None) -> bool:
    """Attempts to install/update external genomics tools in an isolated conda environment."""
    import platform
    from .tools.base import find_executable

    if platform.system() == "Windows":
        print("\nWarning: Native Windows installation of genomics tools (blast, prokka, rgi, parsnp, mashtree) is not supported.")
        print("To run the full SanBac pipeline, please install and run SanBac within Windows Subsystem for Linux (WSL).")
        print("For more details, see the installation guide in README.md.")
        return False

    # On aarch64 systems, set up x86_64 compatibility first
    # so we can verify if existing packages can run correctly
    _ensure_x86_64_compat()

    # Custom tools (installed via custom python logic in their update_db, not just conda)
    custom_tools = {"plasmidfinder", "phigaro", "crisprcasfinder", "integronfinder"}

    # Conda-based tools
    tool_checks = {
        "diamond": "diamond",
        "prokka": "prokka",
        "rgi": "rgi",
        "parsnp": "parsnp",
        "mashtree": "mashtree",
        "isescan": "isescan.py",
        "kma": "kma",
        "blast": "blastn"
    }

    all_known_tools = set(tool_checks.keys()) | custom_tools

    if tool_name and tool_name.lower() != 'all':
        selected_tools = [t.strip().lower() for t in tool_name.split(',')]
        invalid_tools = [t for t in selected_tools if t not in all_known_tools]
        if invalid_tools:
            print(f"Error: Unrecognized tool(s): {', '.join(invalid_tools)}")
            print(f"Available tools: {', '.join(sorted(all_known_tools))}")
            return False
    else:
        selected_tools = None  # means all

    # Handle custom tools first
    git_tools_to_install = []
    if selected_tools:
        git_tools_to_install = [t for t in selected_tools if t in custom_tools]
    else:
        git_tools_to_install = list(custom_tools)

    git_success = True
    if git_tools_to_install:
        tools = load_tools()
        for gt in git_tools_to_install:
            if gt in tools:
                tool_obj = tools[gt]
                if tool_obj.is_installed():
                    print(f"  {gt}: already installed")
                else:
                    print(f"\n--- Installing {gt} (custom) ---")
                    try:
                        if tool_obj.update_db():
                            print(f"  {gt}: installed successfully")
                        else:
                            print(f"  {gt}: installation failed")
                            git_success = False
                    except Exception as e:
                        print(f"  {gt}: installation failed: {e}")
                        git_success = False
            else:
                print(f"  {gt}: tool plugin not found")
                git_success = False

    # If only custom tools were requested, return early
    if selected_tools and all(t in custom_tools for t in selected_tools):
        return git_success

    # Filter conda tool_checks based on selection
    if selected_tools:
        conda_selected = [t for t in selected_tools if t not in custom_tools]
        tool_checks = {k: v for k, v in tool_checks.items() if k in conda_selected}

    # Check which conda tools actually need installation
    tools_to_install = []
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
        print("All external tools are already installed and working.")
        return git_success

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

    print(f"Installing missing tools in isolated environments: {', '.join(tools_to_install)}...")
    tools_base = get_tools_env_prefix()
    tools_base.mkdir(parents=True, exist_ok=True)
    
    for tool in tools_to_install:
        tool_env = tools_base / f"sanbac_{tool}"
        
        # If the environment folder already exists, remove it first to ensure a completely clean, conflict-free slate
        import shutil
        if tool_env.exists():
            print(f"Removing existing/corrupted environment folder for {tool}...")
            try:
                if tool_env.is_dir():
                    shutil.rmtree(str(tool_env), ignore_errors=True)
                else:
                    tool_env.unlink(missing_ok=True)
            except Exception as e:
                print(f"Warning: Could not remove {tool_env}: {e}")

        action = "create"
        specs = [tool]
        # Pin to standard CPython to prevent solver conflicts (like PyPy)
        specs.append("python=3.9")
            
        if tool == "mashtree" and is_aarch64_system():
            specs.append("libxcrypt")
            
        print(f"\n--- Installing {tool} ---")
        cmd = [conda_path, action, "-y", "-p", str(tool_env), "-c", "conda-forge", "-c", "bioconda", "-c", "defaults"] + specs
        success = False
        for attempt in range(2):
            try:
                print(f"Running: {' '.join(cmd)}")
                process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
                for line in process.stdout:
                    if line.startswith("#"):
                        continue
                    sys.stdout.write(line)
                    sys.stdout.flush()
                process.wait()
                if process.returncode == 0:
                    success = True
                    break
                else:
                    print(f"Notice: Conda {action} did not succeed for {tool} (exit code {result.returncode}).")
            except Exception as e:
                print(f"Notice: Failed to run conda install for {tool}: {e}")
                
            if attempt == 0:
                print("\nAttempting to clear conda cache and clean up corrupted files to free space...")
                try:
                    subprocess.run([conda_path, "clean", "-a", "-y"], check=False)
                except Exception as clean_err:
                    print(f"Notice: Conda clean failed: {clean_err}")
                
                import shutil
                if tool_env.exists():
                    try:
                        shutil.rmtree(str(tool_env), ignore_errors=True)
                    except Exception as rm_err:
                        print(f"Notice: Failed to clean directory {tool_env}: {rm_err}")
                        
        if not success:
            return False
            
    print("\nConda install/update completed successfully.")
    
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


def update_tool(repo_url: str = DEFAULT_REPO) -> bool:
    """
    Attempts to update the tool.
    If it's running inside a git clone (editable install), it runs `git pull` (with stash/pop protection).
    Otherwise, it runs `pip install --upgrade git+<repo_url>`.
    Also automatically runs `pip install -e .` to handle setup.py changes.
    """
    print(f"Checking for SanBac updates from repository: {repo_url}")
    
    # Check if we are running in a git repository context (editable mode)
    package_dir = Path(__file__).resolve().parent.parent
    git_dir = package_dir / ".git"
    
    if git_dir.exists():
        print("Detected local git repository. Pulling latest code via 'git pull'...")
        try:
            # 1. Check for local modifications to prevent git pull conflicts
            status_check = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(package_dir),
                capture_output=True,
                text=True,
                check=True
            )
            has_local_changes = bool(status_check.stdout.strip())
            
            if has_local_changes:
                print("Local modifications detected. Stashing changes temporarily...")
                subprocess.run(["git", "stash"], cwd=str(package_dir), check=True)
            
            # 2. Pull the latest commits
            result = subprocess.run(
                ["git", "pull"],
                cwd=str(package_dir),
                capture_output=True,
                text=True,
                check=True
            )
            print(result.stdout)
            
            # 3. Restore any local modifications
            if has_local_changes:
                print("Re-applying local changes (popping stash)...")
                subprocess.run(["git", "stash", "pop"], cwd=str(package_dir), check=False)
            
            # 4. Automatically run pip install to update dependencies in case setup.py changed
            print("Updating Python package dependencies...")
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-e", "."],
                cwd=str(package_dir),
                check=False
            )
            
            return True
        except subprocess.CalledProcessError as e:
            print(f"Git pull/update failed: {e.stderr or e.stdout}")
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
        return True
    except subprocess.CalledProcessError as e:
        print(f"Pip upgrade failed: {e.stderr or e.stdout}")
        return False
