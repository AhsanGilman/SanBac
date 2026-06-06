import unittest
from unittest.mock import patch, MagicMock
import tempfile
import shutil
from pathlib import Path
from sanbac.tools import load_tools
from sanbac.config import config
from sanbac.pipeline import discover_fasta_files, PipelineRunner
from sanbac.tools.base import BaseTool

class TestSanBac(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.input_path = Path(self.test_dir) / "input"
        self.output_path = Path(self.test_dir) / "output"
        self.input_path.mkdir()
        self.output_path.mkdir()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_plugin_discovery(self):
        """Test that default plugins are discovered by the plugin manager."""
        tools = load_tools()
        self.assertIn("card", tools)
        self.assertIn("vfdb", tools)
        self.assertIn("prokka", tools)
        self.assertTrue(isinstance(tools["card"], BaseTool))

    def test_config(self):
        """Test configuration defaults and value setting."""
        orig_val = config.get_executable("rgi")
        config.set_executable("rgi", "custom_rgi")
        self.assertEqual(config.get_executable("rgi"), "custom_rgi")
        config.set_executable("rgi", orig_val)

    def test_fasta_discovery(self):
        """Test that discover_fasta_files correctly detects FASTA files."""
        # Create dummy files
        fasta1 = self.input_path / "sample1.fasta"
        fna1 = self.input_path / "sample2.fna"
        txt1 = self.input_path / "sample3.txt"
        
        fasta1.write_text(">seq1\nATCG\n")
        fna1.write_text(">seq2\nCGTA\n")
        txt1.write_text("not a fasta file\n")
        
        discovered = discover_fasta_files(self.input_path)
        
        self.assertEqual(len(discovered), 2)
        self.assertEqual(discovered[0].name, "sample1.fasta")
        self.assertEqual(discovered[1].name, "sample2.fna")

    def test_pipeline_runner_initialization(self):
        """Test that PipelineRunner resolves selected tools correctly."""
        runner = PipelineRunner(selected_tools=["card", "prokka"])
        self.assertEqual(len(runner.tools_to_run), 2)
        self.assertEqual(runner.tools_to_run[0].name, "card")
        self.assertEqual(runner.tools_to_run[1].name, "prokka")

        runner_default = PipelineRunner()
        names = [t.name for t in runner_default.tools_to_run]
        self.assertListEqual(names, ["card", "vfdb", "prokka"])

    def test_parsnp_plugin_discovery_and_properties(self):
        """Test that Parsnp is discovered and implements properties correctly."""
        tools = load_tools()
        self.assertIn("parsnp", tools)
        parsnp = tools["parsnp"]
        self.assertEqual(parsnp.name, "parsnp")
        self.assertFalse(parsnp.run_per_file)

    def test_pipeline_runner_with_parsnp_reference(self):
        """Test that parsnp is added to tools_to_run when reference_parsnp is provided."""
        ref_file = self.input_path / "reference.fasta"
        ref_file.write_text(">ref\nATCG\n")
        
        runner = PipelineRunner(reference_parsnp=ref_file)
        names = [t.name for t in runner.tools_to_run]
        self.assertListEqual(names, ["card", "vfdb", "prokka", "parsnp"])

    @patch("subprocess.run")
    def test_parsnp_tool_run(self, mock_run):
        """Test ParsnpTool.run execution, directory preparation, copying, and cleanup."""
        tools = load_tools()
        parsnp = tools["parsnp"]
        
        ref_file = self.input_path / "reference.fasta"
        ref_file.write_text(">ref\nATCG\n")
        
        query_file = self.input_path / "query1.fasta"
        query_file.write_text(">query1\nCGTA\n")
        
        parsnp.reference_parsnp = ref_file
        
        # Set up mock command execution
        mock_run.return_value = MagicMock(returncode=0)
        
        # Create a dummy output folder and parsnp.tree to mock success
        parsnp_outdir = self.output_path / "Phylogenetic tree" / "parsnp"
        
        # A side_effect to create the expected parsnp.tree during run execution
        def create_tree_file(*args, **kwargs):
            parsnp_outdir.mkdir(parents=True, exist_ok=True)
            (parsnp_outdir / "parsnp.tree").write_text("tree_content")
            return MagicMock(returncode=0)
            
        mock_run.side_effect = create_tree_file
        
        # We need parsnp to be marked installed
        with patch.object(parsnp, "is_installed", return_value=True):
            result = parsnp.run(self.input_path, parsnp_outdir, threads=2)
            
        # Verify the tree is copied to the right location
        dest_tree = self.output_path / "Phylogenetic tree" / "parsnp" / "presnp_treee.tree"
        self.assertTrue(dest_tree.exists())
        self.assertEqual(dest_tree.read_text(), "tree_content")
        self.assertEqual(result, dest_tree)

if __name__ == "__main__":
    unittest.main()
