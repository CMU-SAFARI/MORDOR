"""Check reproduction entry points without downloads or simulation runs."""

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reproduction"))
SPEC = importlib.util.spec_from_file_location(
    "reproduction_cli", ROOT / "reproduction" / "reproduce.py"
)
CLI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLI)


class ReproductionTests(unittest.TestCase):
    def invoke(self, *arguments):
        with patch.object(sys, "argv", ["reproduce.py", *arguments]):
            with patch.object(CLI.subprocess, "run") as run:
                CLI.main()
        return run

    def test_default_plotting_and_trace_selection(self):
        run = self.invoke("figures", "--traces", "429.mcf", "--", "--figures", "6")
        command = run.call_args.args[0]
        self.assertIn(str(ROOT / "plotting" / "generate_paper_figures.py"), command)
        self.assertEqual(command[command.index("--source-root") + 1], str(ROOT / "results"))
        self.assertEqual(command[-4:], ["--traces", "429.mcf", "--figures", "6"])
        self.assertIn("--rebuild-results", command)

    def test_default_hardware_and_argument_forwarding(self):
        run = self.invoke("openroad", "--", "--sudo", "--quick")
        self.assertEqual(
            run.call_args.args[0],
            [str(ROOT / "openroad" / "reproduce_table1.sh"), "--sudo", "--quick"],
        )
        self.assertEqual(run.call_args.kwargs["cwd"], ROOT / "openroad")

    def test_custom_output_and_hardware_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            paths = {
                "results_root": str(directory / "simulation results"),
                "paper_results_dir": str(directory / "paper inputs"),
                "figure_dir": str(directory / "figures"),
                "plot_script": "plotting/generate_paper_figures.py",
                "openroad_dir": str(directory / "hardware flow"),
            }
            config = directory / "config.yaml"
            config.write_text(yaml.safe_dump({"paths": paths}))
            run = self.invoke("--config", str(config), "figures")
            command = run.call_args.args[0]
            for option, key in (
                ("--source-root", "results_root"),
                ("--results-dir", "paper_results_dir"),
                ("--figures-dir", "figure_dir"),
            ):
                self.assertEqual(command[command.index(option) + 1], paths[key])
            run = self.invoke("--config", str(config), "openroad")
            self.assertEqual(run.call_args.kwargs["cwd"], Path(paths["openroad_dir"]))

    def test_setup_uses_each_execution_profile(self):
        for backend in ("local", "slurm"):
            with self.subTest(backend=backend):
                run = self.invoke(backend, "setup")
                self.assertEqual(run.call_count, 2)
                download, environment = [call.args[0] for call in run.call_args_list]
                self.assertEqual(Path(download[1]).name, "fetch_traces.py")
                self.assertIn("--sha256", download)
                self.assertEqual(environment[environment.index("--backend") + 1], backend)
                self.assertIn("--build", environment)
                if backend == "local":
                    self.assertEqual(environment[environment.index("--build-jobs") + 1], "2")

    def test_native_plans_generate_jobs_without_running_them(self):
        for backend in ("local", "slurm"):
            with self.subTest(backend=backend), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                traces = directory / "traces"
                traces.mkdir()
                # Planning needs paths to exist, but does not consume trace data
                # or execute this placeholder binary.
                (traces / "429.mcf").touch()
                binary = directory / "unbuilt-simulator"
                binary.touch()
                profile = yaml.safe_load(
                    (ROOT / "reproduction" / f"{'generic_slurm' if backend == 'slurm' else 'local'}_config.yaml").read_text()
                )
                profile["paths"].update(
                    repo_root=str(ROOT / "ramulator"),
                    trace_dir=str(traces),
                    workspace_root=str(directory / "workspace"),
                    ramulator=str(binary),
                )
                config = directory / "profile.yaml"
                config.write_text(yaml.safe_dump(profile))
                result = subprocess.run(
                    [sys.executable, str(ROOT / "reproduce.py"), backend, "plan",
                     "--profile", str(config), "--classes", "main", "--traces", "429.mcf"],
                    capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                scripts = list((directory / "workspace").rglob("*.sh"))
                self.assertTrue(scripts)
                if backend == "slurm":
                    for script in scripts:
                        text = script.read_text()
                        self.assertNotIn("#SBATCH --partition", text)
                        self.assertNotIn("#SBATCH --exclude", text)


if __name__ == "__main__":
    unittest.main()
