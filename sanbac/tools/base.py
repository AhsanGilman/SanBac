from abc import ABC, abstractmethod
from pathlib import Path

class BaseTool(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """The short identifier name for the tool (e.g., 'card', 'vfdb', 'prokka')."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """A brief description of what this tool does."""
        pass

    @property
    def run_per_file(self) -> bool:
        """Whether this tool runs per file (True) or on the entire input directory (False)."""
        return True

    @abstractmethod
    def is_installed(self) -> bool:
        """Checks if the underlying external commands needed are executable/installed."""
        pass

    @abstractmethod
    def update_db(self) -> bool:
        """Downloads/updates the database used by this tool. Returns True if successful."""
        pass

    @abstractmethod
    def run(self, input_file: Path, output_dir: Path, threads: int) -> Path:
        """
        Runs the tool on a single FASTA file.
        :param input_file: Path to the FASTA/FNA input file.
        :param output_dir: Directory where outputs for this specific tool should be saved.
        :param threads: Number of CPU threads/cores to use.
        :return: Path to the main output file or directory created.
        """
        pass

    @abstractmethod
    def get_version(self) -> str:
        """
        Returns the version of the underlying external tool.
        :return: Version string or 'Not Installed' / 'Unknown'.
        """
        pass

    def before_run(self, output_dir: Path):
        """Optional hook executed before starting run/parallel processing."""
        pass

    def after_run(self, output_dir: Path):
        """Optional hook executed after completing all run/parallel processing."""
        pass

def find_executable(cmd_name: str) -> str:
    """
    Finds an executable by searching:
    1. System PATH (shutil.which)
    2. sys.prefix/bin/<cmd_name> (conda env bin)
    3. sys.prefix/bin/<cmd_name>.pl (Perl scripts like mashtree)
    4. Glob sys.prefix/bin/<cmd_name>* (catch any variant)
    5. CONDA_PREFIX/bin/ (if different from sys.prefix)
    Returns the full path string or None.
    """
    import shutil
    import sys
    import os

    # 1. Standard PATH lookup
    p = shutil.which(cmd_name)
    if p:
        return p

    # Also try with .pl suffix via PATH
    p = shutil.which(f"{cmd_name}.pl")
    if p:
        return p

    # Collect candidate directories to search in priority order
    bin_dirs = []
    
    # Map command name to its dedicated tool environment folder name
    tool_env_map = {
        "diamond": "diamond",
        "rgi": "rgi",
        "prokka": "prokka",
        "parsnp": "parsnp",
        "mashtree": "mashtree"
    }
    
    # 1. Primary priority: check the dedicated tool environment directory first
    dedicated_env = tool_env_map.get(cmd_name.lower())
    tools_base = None
    try:
        from ..updater import get_tools_env_prefix
        tools_base = get_tools_env_prefix()
    except Exception:
        prefix = Path(sys.prefix)
        in_conda = os.environ.get('CONDA_PREFIX') is not None or (prefix / 'conda-meta').is_dir() or prefix.parent.name == 'envs'
        if in_conda:
            if prefix.parent.name == 'envs':
                tools_base = prefix.parent / f"{prefix.name}-tool-envs"
            else:
                tools_base = prefix / "envs" / "sanbac-tool-envs"
        else:
            tools_base = Path.home() / ".sanbac" / "envs" / "sanbac-tool-envs"

    if dedicated_env and tools_base and tools_base.is_dir():
        dedicated_bin = tools_base / dedicated_env / "bin"
        if dedicated_bin.is_dir():
            bin_dirs.append(dedicated_bin)

    # 2. Secondary priority: check other isolated tools environments bin directories
    if tools_base and tools_base.is_dir():
        try:
            for sub_dir in sorted(tools_base.iterdir()):
                if sub_dir.is_dir() and (sub_dir / 'bin').is_dir():
                    bin_dir_path = sub_dir / "bin"
                    if bin_dir_path not in bin_dirs:
                        bin_dirs.append(bin_dir_path)
        except Exception:
            pass

    # 3. Tertiary priority: Active Conda environment bin
    conda_prefix = os.environ.get("CONDA_PREFIX")
    if conda_prefix:
        conda_bin = Path(conda_prefix) / "bin"
        if conda_bin not in bin_dirs:
            bin_dirs.append(conda_bin)

    # 4. Quaternary priority: Sys prefix bin
    sys_bin = Path(sys.prefix) / "bin"
    if sys_bin not in bin_dirs:
        bin_dirs.append(sys_bin)

    for bin_dir in bin_dirs:
        if not bin_dir.is_dir():
            continue

        # 2. Exact name match
        exact = bin_dir / cmd_name
        if exact.exists():
            return str(exact)

        # 3. With .pl suffix
        pl_variant = bin_dir / f"{cmd_name}.pl"
        if pl_variant.exists():
            return str(pl_variant)

        # 4. Glob for any variant (e.g. mashtree_something)
        try:
            for candidate in sorted(bin_dir.glob(f"{cmd_name}*")):
                if candidate.is_file():
                    return str(candidate)
        except Exception:
            pass

    return None


def run_subprocess(cmd, **kwargs):
    """
    Runs a subprocess command, automatically resolving the executable's path
    and prepending its conda bin directory (and other tool bin directories)
    to PATH to ensure dependent libraries and binaries (like perl/python) are found.
    On aarch64, it also configures LD_LIBRARY_PATH compatibility.
    """
    import os
    import sys
    import subprocess
    from pathlib import Path

    # 1. Resolve executable's full path if it is a registered tool
    exe = cmd[0]
    resolved_exe = find_executable(exe)
    if resolved_exe:
        cmd[0] = resolved_exe
        exe_dir = Path(resolved_exe).parent
    else:
        # If not a registered tool or we couldn't resolve it, use the original executable name.
        exe_dir = None

    # 2. Build environment dictionary
    env = kwargs.get("env")
    if env is None:
        env = os.environ.copy()
    else:
        env = env.copy()

    # Determine tool bin directories to add to PATH
    bin_dirs = []
    if exe_dir:
        bin_dirs.append(str(exe_dir.resolve()))

    # Gather other tool bin directories under the tools environment prefix
    try:
        from ..updater import get_tools_env_prefix
        tools_base_dir = get_tools_env_prefix()
        if tools_base_dir.is_dir():
            for sub_dir in tools_base_dir.iterdir():
                if sub_dir.is_dir() and (sub_dir / 'bin').is_dir():
                    path_str = str((sub_dir / 'bin').resolve())
                    if path_str not in bin_dirs:
                        bin_dirs.append(path_str)
    except Exception:
        # In case of circular import issues or if updater is not importable
        pass

    # Prepend bin directories to PATH
    current_path = env.get("PATH", "")
    path_sep = ";" if os.name == "nt" else ":"
    current_path_parts = [p.strip() for p in current_path.split(path_sep) if p.strip()]
    
    new_path_parts = bin_dirs + [p for p in current_path_parts if p not in bin_dirs]
    env["PATH"] = path_sep.join(new_path_parts)

    # 3. Handle aarch64 LD_LIBRARY_PATH compatibility if on an aarch64 machine
    try:
        from ..updater import is_aarch64_system
        if is_aarch64_system():
            paths_to_add = []
            
            # Cross-architecture libraries
            cross_lib_dir = '/usr/x86_64-linux-gnu/lib'
            if Path(cross_lib_dir).is_dir():
                paths_to_add.append(cross_lib_dir)
                
            # Current Python conda environment
            conda_lib_dir = Path(sys.prefix) / 'lib'
            if conda_lib_dir.is_dir():
                paths_to_add.append(str(conda_lib_dir.resolve()))
                
            # CONDA_PREFIX
            conda_prefix = os.environ.get('CONDA_PREFIX')
            if conda_prefix:
                env_lib_dir = Path(conda_prefix) / 'lib'
                if env_lib_dir.is_dir():
                    paths_to_add.append(str(env_lib_dir.resolve()))
                    
            # Specific executing tool lib
            if exe_dir:
                lib_dir = exe_dir.parent / "lib"
                if lib_dir.is_dir():
                    paths_to_add.append(str(lib_dir.resolve()))
                    
            # All other tools lib
            for b_dir in bin_dirs:
                lib_dir = Path(b_dir).parent / "lib"
                if lib_dir.is_dir() and str(lib_dir.resolve()) not in paths_to_add:
                    paths_to_add.append(str(lib_dir.resolve()))

            current_ld = env.get('LD_LIBRARY_PATH', '')
            current_ld_parts = [p.strip() for p in current_ld.split(':') if p.strip()]
            
            new_ld_parts = paths_to_add + [p for p in current_ld_parts if p not in paths_to_add]
            env['LD_LIBRARY_PATH'] = ':'.join(new_ld_parts)
    except Exception:
        pass

    kwargs["env"] = env
    return subprocess.run(cmd, **kwargs)


def get_cmd_version(cmd_list, version_arg="--version") -> str:
    """Helper function to run an external command and parse its version."""
    try:
        exec_path = find_executable(cmd_list[0])
        if not exec_path:
            return "Not Installed"

        cmd = [exec_path] + cmd_list[1:] + [version_arg]
        res = run_subprocess(cmd, capture_output=True, text=True, errors="replace", timeout=5)
        output = (res.stdout or res.stderr or "").strip()
        if not output:
            return "Unknown"
        return output.splitlines()[0].strip()
    except Exception:
        return "Unknown"
