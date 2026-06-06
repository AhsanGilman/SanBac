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

    # Collect candidate directories to search
    bin_dirs = set()
    bin_dirs.add(Path(sys.prefix) / "bin")
    
    conda_prefix = os.environ.get("CONDA_PREFIX")
    if conda_prefix:
        bin_dirs.add(Path(conda_prefix) / "bin")

    # Add isolated tools environments bin directories
    try:
        from ..updater import get_tools_env_prefix
        tools_base_dir = get_tools_env_prefix()
        if tools_base_dir.is_dir():
            for sub_dir in tools_base_dir.iterdir():
                if sub_dir.is_dir() and (sub_dir / 'bin').is_dir():
                    bin_dirs.add(sub_dir / "bin")
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
            
        if tools_base.is_dir():
            for sub_dir in tools_base.iterdir():
                if sub_dir.is_dir() and (sub_dir / 'bin').is_dir():
                    bin_dirs.add(sub_dir / "bin")

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


def get_cmd_version(cmd_list, version_arg="--version") -> str:
    """Helper function to run an external command and parse its version."""
    import subprocess
    try:
        exec_path = find_executable(cmd_list[0])
        if not exec_path:
            return "Not Installed"

        cmd = [exec_path] + cmd_list[1:] + [version_arg]
        res = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=5)
        output = (res.stdout or res.stderr or "").strip()
        if not output:
            return "Unknown"
        return output.splitlines()[0].strip()
    except Exception:
        return "Unknown"
