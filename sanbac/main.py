import os
import platform
import click
from pathlib import Path
from .pipeline import PipelineRunner
from .updater import update_databases, update_tool, is_aarch64_system, get_tools_env_prefix
from .tools import load_tools
from .config import config, CONFIG_FILE


def _apply_aarch64_compat():
    """On aarch64 systems, ensure x86_64 cross-architecture libraries are in LD_LIBRARY_PATH."""
    import sys
    if not is_aarch64_system():
        return
        
    paths_to_add = []
    
    # 1. Cross-architecture library dir
    cross_lib_dir = '/usr/x86_64-linux-gnu/lib'
    if Path(cross_lib_dir).is_dir():
        paths_to_add.append(cross_lib_dir)
        
    # 2. Active Python conda environment's lib dir (contains libxcrypt/libcrypt.so.1)
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
            if sub_dir.is_dir() and (sub_dir / 'lib').is_dir():
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


# Apply at import time so all subprocess calls inherit the correct LD_LIBRARY_PATH
_apply_aarch64_compat()

def print_version(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return
    click.echo("SanBac 1.0.0")
    click.echo("\nTool dependency versions:")
    click.echo("-" * 30)
    try:
        tools = load_tools()
        for name, tool in sorted(tools.items()):
            try:
                version = tool.get_version()
            except Exception:
                version = "Unknown"
            click.echo(f"  {name:<10}: {version}")
    except Exception as e:
        click.echo(f"  Error loading tools: {e}")
    ctx.exit()

@click.group()
@click.option(
    "--version",
    is_flag=True,
    callback=print_version,
    expose_value=False,
    is_eager=True,
    help="Show the version and exit."
)
def main():
    """SanBac: A modular, multithreaded bacterial genomics analysis pipeline.
    
    Orchestrates CARD, VFDB, Prokka, and other plugins sequentially.
    """
    pass

@main.command("run")
@click.option(
    "-i", "--input-dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    required=True,
    help="Path to the import folder containing FNA/FASTA files."
)
@click.option(
    "-o", "--output-dir",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    required=True,
    help="Path to the output folder where analysis results will be saved."
)
@click.option(
    "-t", "--threads",
    type=int,
    default=4,
    show_default=True,
    help="Total threads/CPU cores to allocate to the run."
)
@click.option(
    "--tools",
    type=str,
    required=True,
    help="Comma-separated list of tools to run (e.g. 'card,prokka' or 'all')."
)
@click.option(
    "--reference-parsnp",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
    default=None,
    help="Path to the reference FASTA/FNA file for Parsnp phylogenetic tree generation."
)
def run_pipeline(input_dir: Path, output_dir: Path, threads: int, tools: str, reference_parsnp: Path):
    """Scan the input folder for FASTA files and run selected genomics analysis tools."""
    selected = None
    if tools:
        selected = [t.strip().lower() for t in tools.split(",")]
        
    try:
        runner = PipelineRunner(selected_tools=selected, reference_parsnp=reference_parsnp)
        runner.run_pipeline(input_dir=input_dir, output_dir=output_dir, total_threads=threads)
    except Exception as e:
        click.secho(f"Pipeline error: {e}", fg="red", err=True)
        raise click.Abort()

@main.command("list-tools")
def list_tools():
    """List all registered and available tool plugins."""
    click.echo("Scanning for available tools...")
    tools = load_tools()
    if not tools:
        click.echo("No tool plugins found!")
        return
        
    click.echo(f"\nFound {len(tools)} registered tool(s):")
    click.echo("-" * 60)
    for name, tool in tools.items():
        status = "Installed" if tool.is_installed() else "Not Found (Missing Dependency)"
        fg_color = "green" if tool.is_installed() else "yellow"
        
        click.echo(f"Name:        {name}")
        click.echo(f"Description: {tool.description}")
        click.echo("Status:      ", nl=False)
        click.secho(status, fg=fg_color)
        click.echo("-" * 60)

@main.command("update-db")
@click.option(
    "--tool",
    type=str,
    default=None,
    help="Specify a single tool database to update (e.g., 'card' or 'vfdb'). Updates all by default."
)
def update_db_cmd(tool):
    """Download or update databases used by the analysis tools (e.g. CARD, VFDB)."""
    success = update_databases(tool_name=tool)
    if success:
        click.secho("\nAll database updates completed successfully.", fg="green")
    else:
        click.secho("\nOne or more database updates failed.", fg="yellow")

@main.command("update-tool")
@click.option(
    "--repo",
    type=str,
    default=None,
    help="Custom GitHub repository URL to pull updates from."
)
def update_tool_cmd(repo):
    """Self-update the SanBac tool code to the latest version from GitHub."""
    kwargs = {}
    if repo:
        kwargs["repo_url"] = repo
        
    success = update_tool(**kwargs)
    if success:
        click.secho("Update process finished.", fg="green")
        click.echo("Updating analysis databases (CARD, VFDB) to match latest versions...")
        import sys
        import subprocess
        subprocess.run([sys.executable, "-m", "sanbac.main", "update-db"])
    else:
        click.secho("Update process failed.", fg="red")

@main.command("install-tools")
@click.argument("tool", required=False)
def install_tools_cmd(tool):
    """Install or update external bioinformatics tools (parsnp, mashtree) via conda."""
    if tool and tool.lower() != 'all':
        click.echo(f"Checking/installing external tool dependencies for: {tool}...")
    else:
        click.echo("Checking/installing external tool dependencies (diamond, prokka, rgi, parsnp, mashtree, isescan)...")
        
    from .updater import update_external_binaries
    success = update_external_binaries(tool_name=tool)
    if success:
        click.secho("External tools installed successfully and are ready to use.", fg="green")
    else:
        click.secho("Failed to install or verify one or more external tools.", fg="red")

@main.command("config")
@click.option("--db-dir", type=click.Path(file_okay=False, dir_okay=True, path_type=Path), help="Change database storage folder.")
@click.option("--exec-name", type=str, help="Specify executable name to override (e.g. 'rgi', 'blastn').")
@click.option("--exec-path", type=str, help="Path to the specified executable.")
def config_cmd(db_dir, exec_name, exec_path):
    """View or modify configuration parameters."""
    if db_dir:
        config.db_dir = db_dir
        config.save()
        click.echo(f"Database folder updated to: {db_dir}")
        
    if exec_name and exec_path:
        config.set_executable(exec_name, exec_path)
        click.echo(f"Executable path for '{exec_name}' set to: {exec_path}")
        
    if not db_dir and not (exec_name and exec_path):
        click.echo(f"Config path:      {CONFIG_FILE}")
        click.echo(f"Database path:    {config.db_dir}")
        click.echo("Registered Executables:")
        for k, v in config.executables.items():
            click.echo(f"  {k}: {v}")

if __name__ == "__main__":
    main()
