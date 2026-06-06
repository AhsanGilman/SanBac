import click
from pathlib import Path
from .pipeline import PipelineRunner
from .updater import update_databases, update_tool
from .tools import load_tools
from .config import config, CONFIG_FILE

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
    default=None,
    help="Comma-separated list of tools to run (e.g. 'card,prokka'). By default, runs all tools."
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
        update_databases()
    else:
        click.secho("Update process failed.", fg="red")

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
