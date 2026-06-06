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

def get_cmd_version(cmd_list, version_arg="--version") -> str:
    """Helper function to run an external command and parse its version."""
    import shutil
    import subprocess
    try:
        if not shutil.which(cmd_list[0]):
            return "Not Installed"
        res = subprocess.run([cmd_list[0], version_arg], capture_output=True, text=True, errors="replace", timeout=5)
        output = (res.stdout or res.stderr or "").strip()
        if not output:
            return "Unknown"
        return output.splitlines()[0].strip()
    except Exception:
        return "Unknown"
