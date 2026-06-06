# SanBac 🦠

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)

**SanBac** is a professional, modular, and multithreaded bacterial genomics analysis pipeline in Python. It provides a simple command-line interface (CLI) to automatically run a suite of annotation and screening tools sequentially on an entire directory of genome sequences (FASTA/FNA formats). 

By default, the pipeline runs the following tools in order:
1. **CARD** (Comprehensive Antibiotic Resistance Database) — via RGI (Resistance Gene Identifier) to identify antibiotic resistance genes (ARGs).
2. **VFDB** (Virulence Factor Database) — via blastn to screen for virulence factors.
3. **Prokka** — to execute rapid prokaryotic genome annotation (protein coding genes, tRNA, rRNA).
4. **Parsnp** (optional) — to perform core genome alignment and construct a phylogenetic tree (automatically appended to the default list if `--reference-parsnp` is supplied).
5. **Mashtree** (optional) — to perform alignment-free phylogenetic tree generation based on Mash distances (runs if selected via `--tools mashtree`).

The architecture is highly extensible, allowing you to easily add new tools (e.g. tools 4, 5, 6) simply by adding a Python script.

---

## Key Features

*   ⚡ **Extensible Plugin System**: Add new tools as self-contained plugins. They are automatically discovered, configured, and run in sequence.
*   🧵 **Smart Multithreading**: Parallelizes analysis across genomes and assigns optimal CPU threads per run, maximizing hardware utilization.
*   🔄 **Database Manager**: Build and update local databases (like CARD or VFDB) automatically with one command.
*   📦 **Self-Updater**: Keep the codebase up to date by pulling updates directly from GitHub.
*   ⚙️ **Custom Configuration**: Easily change default database directories or map custom binaries using config overrides.

---

## Installation

To make installation simple, follow these steps in order:

### 1. Clone the Repository & Change Directory
Clone the repository to your machine and move into the project folder:

```bash
git clone https://github.com/AhsanGilman/SanBac.git
cd SanBac
```

### 2. Create the Conda Environment
SanBac relies on external bioinformatics tools (`prokka`, `blast`, `rgi`) which require system dependencies. 

To ensure fast and clean package resolution, we recommend setting Conda's channel priority to `strict` first:

```bash
# Set channel priority to strict (recommended)
conda config --set channel_priority strict

# Create the environment using the local file
conda env create -f sanbac.yml
conda activate sanbac
```

### 3. Install SanBac CLI
With the conda environment active, install the CLI:

```bash
python -m pip install -e .
```

*Note: If you receive a `sanbac: command not found` error after installation, your system path is missing Python's binary directory. You can easily fix this by adding a command alias to your shell config:*
```bash
echo "alias sanbac='python -m sanbac.main'" >> ~/.bashrc
source ~/.bashrc
```

### 🚨 Ubuntu / ARM64 (aarch64) Native Installation
If you are running on an **ARM64 (aarch64) Linux** machine (like AWS Graviton or Apple Silicon Linux VMs), Bioconda does not provide pre-compiled packages for tools like `bamtools` or `rgi`.

#### Step-by-Step Installation:
```bash
# 1. Install system bioinformatics tools via apt
sudo apt-get update
sudo apt-get install -y ncbi-blast+ prokka prodigal diamond-aligner bamtools

# 2. Create and activate a permanent Conda environment with python 3.9 and pip installed inside it
conda create -n sanbac python=3.9 pip -y
conda activate sanbac

# 3. Install RGI (CARD) and SanBac using python's module invocation to bypass any shell path caching
git clone https://github.com/AhsanGilman/SanBac.git
cd ~/SanBac
python -m pip install --upgrade pip setuptools
python -m pip install git+https://github.com/arpcard/rgi.git
python -m pip install -e .

# 4. Map the command alias if system PATH is missing python binaries
echo "alias sanbac='python -m sanbac.main'" >> ~/.bashrc
source ~/.bashrc
```

---

## Usage Guide

### 1. View Available Tools
Check the status of registered tools and see if their command-line dependencies are found on your system path:
```bash
sanbac list-tools
```

### 2. Download and Update Databases
Download the latest versions of databases (CARD, VFDB) and index them:
```bash
sanbac update-db
```
*Note: The VFDB database will be downloaded and built automatically if you try to run the pipeline without it.*

### 3. Run the Pipeline
To run the default annotation tools (CARD, VFDB, Prokka) on a folder containing `.fasta` or `.fna` files:
```bash
sanbac run --input-dir /path/to/genomes --output-dir /path/to/results --threads 8
```

### 4. Run All Tools
To run all available annotation and phylogenetic tools (CARD, VFDB, Prokka, Parsnp, and Mashtree) at the same time:
```bash
sanbac run --input-dir /path/to/genomes --output-dir /path/to/results --threads 8 --tools card,vfdb,prokka,parsnp,mashtree --reference-parsnp /path/to/reference.fasta
```

#### Full CLI Usage Reference:
```
Usage: sanbac [OPTIONS] COMMAND [ARGS]...

  SanBac: A modular, multithreaded bacterial genomics analysis pipeline.
  Orchestrates CARD, VFDB, Prokka, and other plugins sequentially.

Options:
  --version                   Show the version and exit.
  --help                      Show this message and exit.

Commands:
  run                         Scan the input folder for FASTA files and run tools.
  list-tools                  List all registered and available tool plugins.
  update-db                   Download or update databases used by the analysis tools.
  update-tool                 Self-update the SanBac tool code to the latest version.
  config                      View or modify configuration parameters.

COMMAND OPTIONS

  run Options:
    -i, --input-dir DIRECTORY Path to the import folder containing FNA/FASTA files. [Required]
    -o, --output-dir DIRECTORY Path to the output folder where analysis results will be saved. [Required]
    -t, --threads INTEGER     Total threads/CPU cores to allocate to the run. [Default: 4]
    --tools TEXT              Comma-separated list of tools to run (e.g. 'card,prokka,parsnp,mashtree').
    --reference-parsnp FILE   Path to the reference FASTA/FNA file for Parsnp.

  config Options:
    --db-dir DIRECTORY        Change database storage folder.
    --exec-name TEXT          Specify executable name to override (e.g. 'rgi', 'blastn').
    --exec-path TEXT          Path to the specified executable.

  update-db Options:
    --tool TEXT               Specify a single tool database to update (e.g., 'card' or 'vfdb').

  update-tool Options:
    --repo TEXT               Custom GitHub repository URL to pull updates from.
```

---

## Deep Dive: How it Works

### 1. Multithreading Architecture
SanBac uses a smart resource scheduler to distribute threads. If you assign `-t 8` and have 4 genomes in your input directory:
*   All 4 genomes are processed in parallel (concurrency of 4).
*   Each tool run is allocated `8 / 4 = 2` threads.
This ensures your CPU cores are fully saturated without incurring heavy thrashing or context-switching overhead.

### 2. Output File Structure
Results are structured cleanly by tool:
```
results/
├── card/
│   ├── sample1.csv       # CARD antibiotic resistance gene report (CSV only)
│   └── sample2.csv
├── vfdb/
│   ├── sample1.txt       # Virulence gene summary report (TXT only)
│   └── sample2.txt
├── prokka/
│   ├── sample1/          # Full Prokka annotation folder
│   │   ├── sample1.gff
│   │   ├── sample1.faa
│   │   └── sample1.fna
│   └── sample2/
│       ├── sample2.gff
│       └── sample2.faa
└── Phylogenetic tree/
    ├── parsnp/           # Parsnp outputs (grouped by phylogenetic tool)
    │   ├── parsnp.xmfa       # Core alignment
    │   ├── parsnp.snps.mblocks # SNP signatures
    │   └── presnp_treee.tree # Resulting phylogeny (renamed)
    └── mashtree/         # Mashtree outputs
        └── mashtree.dnd      # Mash distance-based tree (Newick format)
```

### 3. Self-Updating
To upgrade the pipeline to the latest version directly from GitHub:
```bash
sanbac update-tool
```
*   If running inside a git checkout, this executes `git pull`.
*   Otherwise, it upgrades the python package using `pip`.

---

## Adding Custom Tools (Plugins)

You can extend SanBac with features 4, 5, 6, etc. by placing a new Python file in the `sanbac/tools/` directory.

### Example: Adding a custom tool (`sanbac/tools/my_tool.py`)
Create a new file in `sanbac/tools/` and subclass `BaseTool`:

```python
from pathlib import Path
import subprocess
import shutil
from .base import BaseTool

class MyCustomTool(BaseTool):
    @property
    def name(self) -> str:
        # This is the CLI name and the folder name for output
        return "mytool"

    @property
    def description(self) -> str:
        return "My custom genomics plugin (e.g., PlasmidFinder)"

    def is_installed(self) -> bool:
        # Verify the dependency command is on the path
        return shutil.which("mytool-cli") is not None

    def update_db(self) -> bool:
        # Command to update this tool's database
        print("Updating custom databases...")
        return True

    def run(self, input_file: Path, output_dir: Path, threads: int) -> Path:
        # Execute the tool
        output_dir.mkdir(parents=True, exist_ok=True)
        out_file = output_dir / f"{input_file.stem}_report.txt"
        
        cmd = ["mytool-cli", "-i", str(input_file), "-o", str(out_file), "-t", str(threads)]
        subprocess.run(cmd, check=True)
        
        return out_file
```

Once saved, this tool is **automatically detected**. You will see it listed when running `sanbac list-tools`, and it will execute as part of your pipeline!

---

## Configuration overrides

If you have custom binary paths or want to store databases in a specific directory, use the `config` command:

```bash
# View configuration
sanbac config

# Change database directory
sanbac config --db-dir /path/to/shared/dbs

# Override executable path (e.g. if blastn is in a non-standard path)
sanbac config --exec-name blastn --exec-path /usr/local/bin/blastn
```

Configuration is persisted in `~/.sanbac/config.json`.
