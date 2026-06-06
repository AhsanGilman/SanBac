import concurrent.futures
from pathlib import Path
from typing import List, Dict
from .tools import load_tools
from .tools.base import BaseTool

def discover_fasta_files(input_dir: Path) -> List[Path]:
    """Finds all FASTA/FNA/FA files (including gzipped ones) in the input directory."""
    extensions = (".fasta", ".fna", ".fa", ".fasta.gz", ".fna.gz", ".fa.gz")
    fasta_files = []
    if not input_dir.is_dir():
        raise NotADirectoryError(f"Input path '{input_dir}' is not a directory.")
        
    for p in input_dir.iterdir():
        if p.is_file() and p.name.lower().endswith(extensions):
            fasta_files.append(p)
            
    return sorted(fasta_files)

class PipelineRunner:
    def __init__(self, selected_tools: List[str] = None, reference_parsnp: Path = None):
        self.all_tools: Dict[str, BaseTool] = load_tools()
        self.reference_parsnp = reference_parsnp
        
        if selected_tools and "all" not in selected_tools:
            # Normalize selected_tools to lowercase
            selected_tools = [t.lower() for t in selected_tools]
            
            # Ensure 'prokka' is run if 'vfdb' is requested, since 'vfdb' depends on Prokka's protein output
            if "vfdb" in selected_tools and "prokka" not in selected_tools:
                selected_tools.append("prokka")

            # Order tools dynamically based on preferred pipeline order
            preferred_order = ["card", "prokka", "vfdb", "parsnp", "mashtree"]
            ordered = []
            for name in preferred_order:
                if name in selected_tools and name in self.all_tools:
                    ordered.append(self.all_tools[name])
            for name in selected_tools:
                if name not in preferred_order and name in self.all_tools and self.all_tools[name] not in ordered:
                    ordered.append(self.all_tools[name])
            self.tools_to_run = ordered
        else:
            # Default sequence: run all registered tools sequentially
            preferred_order = ["card", "prokka", "vfdb", "parsnp", "mashtree"]
            ordered = []
            for name in preferred_order:
                if name in self.all_tools:
                    ordered.append(self.all_tools[name])
            for name, tool in self.all_tools.items():
                if name not in preferred_order:
                    ordered.append(tool)
            self.tools_to_run = ordered

    def run_pipeline(self, input_dir: Path, output_dir: Path, total_threads: int = 4):
        """Runs all selected tools on all fasta files in the input directory."""
        input_path = Path(input_dir)
        output_path = Path(output_dir)
        
        fasta_files = discover_fasta_files(input_path)
        if not fasta_files:
            print(f"No FASTA/FNA files found in {input_path}")
            return
            
        print(f"Found {len(fasta_files)} FASTA file(s) to process.")
        print(f"Tools in pipeline: {', '.join([t.name for t in self.tools_to_run])}")
        
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Run tools in sequence
        for tool in self.tools_to_run:
            print(f"\n==================================================")
            print(f"Running Tool: {tool.name.upper()} - {tool.description}")
            print(f"==================================================")
            
            if not tool.is_installed():
                print(f"Skipping: {tool.name.upper()} is not installed on this system.")
                continue
                
            if tool.name in ("parsnp", "mashtree"):
                tool_output_dir = output_path / "Phylogenetic tree" / tool.name
            else:
                tool_output_dir = output_path / tool.name
            tool_output_dir.mkdir(parents=True, exist_ok=True)
            
            try:
                tool.before_run(tool_output_dir)
                
                if not tool.run_per_file:
                    if tool.name == "parsnp":
                        tool.reference_parsnp = self.reference_parsnp
                        if not self.reference_parsnp:
                            print(f"Skipping: {tool.name.upper()} (no reference FASTA path provided).")
                            continue
                    
                    print(f"Processing directory: {input_path} as a single run for {tool.name.upper()}")
                    try:
                        result_path = tool.run(input_path, tool_output_dir, total_threads)
                        print(f"Finished: {tool.name.upper()} on {input_path.name} -> Output at: {result_path}")
                    except Exception as exc:
                        print(f"Error: {tool.name.upper()} failed on {input_path.name} with exception: {exc}")
                    continue

                # Determine parallel files configuration:
                # Divide threads evenly across files processed in parallel.
                num_files = len(fasta_files)
                concurrency = min(total_threads, num_files)
                threads_per_file = max(1, total_threads // concurrency)
                
                print(f"Processing {num_files} file(s) with concurrency={concurrency} (threads_per_file={threads_per_file})")
                
                # Use ThreadPoolExecutor to process files in parallel
                with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
                    futures = {}
                    for f in fasta_files:
                        futures[executor.submit(tool.run, f, tool_output_dir, threads_per_file)] = f
                        
                    for future in concurrent.futures.as_completed(futures):
                        fasta_file = futures[future]
                        try:
                            result_path = future.result()
                            print(f"Finished: {tool.name.upper()} on {fasta_file.name} -> Output at: {result_path}")
                        except Exception as exc:
                            print(f"Error: {tool.name.upper()} failed on {fasta_file.name} with exception: {exc}")
            finally:
                tool.after_run(tool_output_dir)
                        
        print("\nPipeline execution completed.")
