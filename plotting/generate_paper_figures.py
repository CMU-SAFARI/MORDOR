#!/usr/bin/env python3
"""Generate the data-derived MORDOR paper figures as labelled PNGs.

The script also creates a compact ``paper_results`` tree containing only the
canonical, semantically named result files consumed by the paper figures.

Examples
--------
    python plotting/generate_paper_figures.py
    python plotting/generate_paper_figures.py --rebuild-results
    python plotting/generate_paper_figures.py --rebuild-results --figures 6
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import csv
import io
import math
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


SCRIPT_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = SCRIPT_DIR.parent
FIGURE_CODE_DIR = SCRIPT_DIR / "figure_code"
DEFAULT_SOURCE_ROOT = PACKAGE_ROOT / "results"
DEFAULT_RESULTS_DIR = PACKAGE_ROOT / "paper_results"
DEFAULT_FIGURES_DIR = PACKAGE_ROOT / "figures"

MECHANISMS = ("Hydra", "PARA", "comet", "DAPPER", "graphene", "abacus")

FIGURE_SPECS = {
    1: "dram_organization",
    2: "priority_vs_insecure_overheads",
    3: "mordor_mechanism_overview",
    4: "pros_causing_other_pros",
    5: "processor_side_energy",
    6: "overheads_across_prt",
    7: "top25_pro_intensive_speedup",
    8: "priority_mordor_insecure_cycle_overhead",
    9: "bank_count_cycle_overhead",
    10: "blast_radius_reduction",
    11: "row_policy_reduction",
    12: "latency_percentiles",
    13: "requests_delayed_by_a_pro",
    14: "area_vs_execution_time_overhead",
}

CONTEXT_SOURCES = (
    FIGURE_CODE_DIR / "context.py",
    FIGURE_CODE_DIR / "shared_results.py",
)
FIGURE6_CONTEXT_SOURCE = FIGURE_CODE_DIR / "figure_06_context.py"
FIGURE_SOURCES = {
    number: FIGURE_CODE_DIR / f"figure_{number:02d}.py"
    for number in (2, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14)
}
PRE_FIGURE_SOURCES = {
    13: (FIGURE_CODE_DIR / "shared_results.py",),
}

@dataclass(frozen=True)
class ManifestEntry:
    figures: str
    destination: str
    source: str
    trace: str
    size_bytes: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=DEFAULT_RESULTS_DIR,
        help="consolidated result directory (default: %(default)s)",
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        default=DEFAULT_SOURCE_ROOT,
        help="raw result root used with --rebuild-results (default: %(default)s)",
    )
    parser.add_argument(
        "--figures-dir",
        type=Path,
        default=DEFAULT_FIGURES_DIR,
        help="PNG output directory (default: %(default)s)",
    )
    parser.add_argument(
        "--rebuild-results",
        action="store_true",
        help="recreate paper_results from canonical raw results",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="PNG resolution for generated plots (default: %(default)s)",
    )
    parser.add_argument(
        "--figures",
        nargs="+",
        type=int,
        choices=tuple(FIGURE_SOURCES),
        default=list(FIGURE_SOURCES),
        help="data-derived figure numbers to generate (default: all)",
    )
    return parser.parse_args()


def load_paper_traces() -> list[str]:
    tree = ast.parse(CONTEXT_SOURCES[0].read_text())
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(
            isinstance(target, ast.Name) and target.id == "PAPER_TRACES"
            for target in node.targets
        ):
            traces = ast.literal_eval(node.value)
            if len(traces) != len(set(traces)) or len(traces) != 55:
                raise ValueError("PAPER_TRACES must contain 55 unique traces")
            return traces
    raise ValueError(f"Could not find PAPER_TRACES in {CONTEXT_SOURCES[0]}")


def valid_result_yaml(path: Path) -> bool:
    """Check the minimum metrics required by the plotting sources."""
    if not path.is_file() or path.stat().st_size == 0:
        return False
    text = path.read_text(errors="replace")
    for core in range(8):
        match = re.search(
            rf"^\s+cycles_recorded_core_{core}:\s+([^\s#]+)",
            text,
            re.MULTILINE,
        )
        if match is None:
            return False
        try:
            if not math.isfinite(float(match.group(1))):
                return False
        except ValueError:
            return False
    energy = re.search(
        r"^\s+total_energy:\s+([^\s#]+)", text, re.MULTILINE
    )
    if energy is None:
        return False
    try:
        return math.isfinite(float(energy.group(1)))
    except ValueError:
        return False


def collect_results(
    directories: Iterable[Path],
    filename_pattern: re.Pattern[str],
    paper_trace_set: set[str],
) -> dict[str, Path]:
    """Collect valid results, with later directories taking precedence."""
    collected: dict[str, Path] = {}
    for directory in directories:
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*_output.yaml")):
            match = filename_pattern.match(path.name)
            if match is None:
                continue
            trace = match.group("trace")
            if trace in paper_trace_set and valid_result_yaml(path):
                collected[trace] = path
    return collected


def require_traces(context: str, values: dict[str, Path], paper_traces: list[str]) -> None:
    missing = [trace for trace in paper_traces if trace not in values]
    if missing:
        raise ValueError(
            f"{context} is missing {len(missing)}/{len(paper_traces)} traces: "
            + ", ".join(missing)
        )


def materialize_results(
    values: dict[str, Path],
    destination: Path,
    traces: Iterable[str],
    figures: str,
    source_root: Path,
    manifest: list[ManifestEntry],
) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    generated_root = next(
        (
            parent
            for parent in (destination, *destination.parents)
            if parent.name.startswith(".")
            and parent.name.endswith(".building")
        ),
        destination,
    )
    for trace in traces:
        source = values[trace]
        target = destination / source.name
        shutil.copy2(source, target)
        manifest.append(
            ManifestEntry(
                figures=figures,
                destination=str(target.relative_to(generated_root)),
                source=str(source.relative_to(source_root)),
                trace=trace,
                size_bytes=target.stat().st_size,
            )
        )


def build_consolidated_results(
    source_root: Path,
    destination: Path,
    paper_traces: list[str],
    figure6_only: bool = False,
) -> None:
    """Build the semantically named, paper-only result tree."""
    if destination.exists():
        shutil.rmtree(destination)
    building = destination.with_name(f".{destination.name}.building")
    if building.exists():
        shutil.rmtree(building)
    building.mkdir(parents=True)

    paper_trace_set = set(paper_traces)
    manifest: list[ManifestEntry] = []
    result_pattern = re.compile(r"^(?P<trace>.+)_output\.yaml$")

    try:
        # Shared no-mitigation baseline.
        baseline = collect_results(
            [source_root / "baseline" / "no_mitigation"],
            result_pattern,
            paper_trace_set,
        )
        require_traces("No-mitigation baseline", baseline, paper_traces)
        materialize_results(
            baseline,
            building / "baseline" / "no_mitigation",
            paper_traces,
            "2,6,8,9,10,14",
            source_root,
            manifest,
        )

        # PRT-125 multicore Priority, MORDOR, and insecure configurations.
        prt125_roots = {
            "priority": "priority",
            "mordor": "mordor",
            "insecure": "insecure",
        }
        if figure6_only:
            prt125_roots.pop("insecure")
        prt125_figures = {
            "priority": "2,5,6,7,8,9,10,11,13,14",
            "mordor": "5,6,7,8,9,10,11,13,14",
            "insecure": "2,8",
        }
        for label, variant in prt125_roots.items():
            for mechanism in MECHANISMS:
                source = source_root / "main" / variant / mechanism
                values = collect_results(
                    [source], result_pattern, paper_trace_set
                )
                require_traces(
                    f"PRT 125 / {label} / {mechanism}", values, paper_traces
                )
                materialize_results(
                    values,
                    building
                    / "main"
                    / label
                    / mechanism,
                    paper_traces,
                    prt125_figures[label],
                    source_root,
                    manifest,
                )

        # Figure 6 PRT sweep.
        for prt in (250, 500, 1000):
            for mechanism in MECHANISMS:
                priority = collect_results(
                    [
                        source_root
                        / "prt_sweep"
                        / f"prt_{prt}"
                        / "priority"
                        / mechanism
                    ],
                    result_pattern,
                    paper_trace_set,
                )
                require_traces(
                    f"PRT {prt} / priority / {mechanism}",
                    priority,
                    paper_traces,
                )
                materialize_results(
                    priority,
                    building
                    / "prt_sweep"
                    / f"prt_{prt}"
                    / "priority"
                    / mechanism,
                    paper_traces,
                    "6",
                    source_root,
                    manifest,
                )

                mordor = collect_results(
                    [
                        source_root
                        / "prt_sweep"
                        / f"prt_{prt}"
                        / "mordor"
                        / mechanism
                    ],
                    result_pattern,
                    paper_trace_set,
                )
                require_traces(
                    f"PRT {prt} / MORDOR / {mechanism}",
                    mordor,
                    paper_traces,
                )
                materialize_results(
                    mordor,
                    building
                    / "prt_sweep"
                    / f"prt_{prt}"
                    / "mordor"
                    / mechanism,
                    paper_traces,
                    "6",
                    source_root,
                    manifest,
                )

        if figure6_only:
            with (building / "manifest.csv").open("w", newline="") as stream:
                writer = csv.DictWriter(
                    stream,
                    fieldnames=[
                        "figures",
                        "destination",
                        "source",
                        "trace",
                        "size_bytes",
                    ],
                )
                writer.writeheader()
                for entry in manifest:
                    writer.writerow(entry.__dict__)
            (building / "README.md").write_text(
                "# Figure 6 result bundle\n\n"
                "This compact bundle contains the canonical 55-workload "
                "inputs required to reproduce Figure 6: the no-mitigation "
                "baseline, PRT-125 main results, and Priority/MORDOR results "
                "for PRT 250, 500, and 1000.\n"
            )
            building.rename(destination)
            return

        # Figure 9 bank-count study (the 16-bank inputs are the PRT-125 tree).
        for banks in (8, 32):
            bank_root = (
                source_root
                / "bank_count"
                / f"banks_{banks}"
            )
            bank_baseline = collect_results(
                [bank_root / "baseline"],
                result_pattern,
                paper_trace_set,
            )
            require_traces(
                f"{banks}-bank baseline", bank_baseline, paper_traces
            )
            materialize_results(
                bank_baseline,
                building
                / "bank_count"
                / f"banks_{banks}"
                / "baseline",
                paper_traces,
                "9",
                source_root,
                manifest,
            )
            for mechanism in MECHANISMS:
                for variant in ("priority", "mordor"):
                    values = collect_results(
                        [bank_root / variant / mechanism],
                        result_pattern,
                        paper_trace_set,
                    )
                    require_traces(
                        f"{banks} banks / {mechanism} / {variant}",
                        values,
                        paper_traces,
                    )
                    materialize_results(
                        values,
                        building
                        / "bank_count"
                        / f"banks_{banks}"
                        / variant
                        / mechanism,
                        paper_traces,
                        "9",
                        source_root,
                        manifest,
                    )

        # Figure 10 uses one shared available cohort across every blast-radius
        # configuration. Copy exactly that cohort, not partially unused files.
        blast_values: dict[tuple[int, str, str], dict[str, Path]] = {}
        for radius in (1, 2, 8):
            for mechanism in MECHANISMS:
                for variant in ("priority", "mordor"):
                    source = (
                        source_root
                        / "blast_radius"
                        / "brc_1"
                        / f"radius_{radius}"
                        / variant
                        / mechanism
                    )
                    blast_values[(radius, mechanism, variant)] = (
                        collect_results(
                            [source], result_pattern, paper_trace_set
                        )
                    )
        blast_common = set(paper_traces)
        for values in blast_values.values():
            blast_common &= set(values)
        blast_traces = [
            trace for trace in paper_traces if trace in blast_common
        ]
        if not blast_traces:
            raise ValueError("Figure 10 has no shared blast-radius traces")
        for (radius, mechanism, variant), values in blast_values.items():
            materialize_results(
                values,
                building
                / "blast_radius"
                / "brc_1"
                / f"radius_{radius}"
                / variant
                / mechanism,
                blast_traces,
                "10",
                source_root,
                manifest,
            )

        # Figure 11 row-policy caps. The open-row inputs reuse PRT 125.
        for cap in (4, 16):
            for mechanism in MECHANISMS:
                for variant in ("priority", "mordor"):
                    source = (
                        source_root
                        / "row_policy"
                        / f"cap_{cap}"
                        / variant
                        / mechanism
                    )
                    values = collect_results(
                        [source], result_pattern, paper_trace_set
                    )
                    require_traces(
                        f"Cap {cap} / {mechanism} / {variant}",
                        values,
                        paper_traces,
                    )
                    materialize_results(
                        values,
                        building
                        / "row_policy"
                        / f"cap_{cap}"
                        / variant
                        / mechanism,
                        paper_traces,
                        "11",
                        source_root,
                        manifest,
                    )

        # Figure 12 deliberately uses only 429.mcf.
        latency_root = source_root / "latency"
        latency_files = sorted(latency_root.glob("*/*/429.mcf_latency.txt"))
        if len(latency_files) != 12:
            raise ValueError(
                "Figure 12 requires 12 latency files for 429.mcf; "
                f"found {len(latency_files)}"
            )
        for source in latency_files:
            relative = source.relative_to(latency_root)
            latency_destination = building / "latency" / relative.parent
            latency_destination.mkdir(parents=True, exist_ok=True)
            target = latency_destination / source.name
            shutil.copy2(source, target)
            manifest.append(
                ManifestEntry(
                    figures="12",
                    destination=str(target.relative_to(building)),
                    source=str(source.relative_to(source_root)),
                    trace="429.mcf",
                    size_bytes=target.stat().st_size,
                )
            )

        # Write the manifest and a concise description before publishing.
        with (building / "manifest.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=[
                    "figures",
                    "destination",
                    "source",
                    "trace",
                    "size_bytes",
                ],
            )
            writer.writeheader()
            for entry in manifest:
                writer.writerow(entry.__dict__)

        excluded_blast = [
            trace for trace in paper_traces if trace not in blast_common
        ]
        readme = f"""# Paper-only result bundle

This directory contains only files consumed by the reproduced paper figures.
The canonical cohort contains {len(paper_traces)} traces.

- `main/priority`: Priority scheduling.
- `main/mordor`: the secure MORDOR policy.
- `main/insecure`: read-queue scheduling without blacklisting.
- `prt_sweep/prt_*/priority`: Priority results for PRT 250/500/1000.
- `prt_sweep/prt_*/mordor`: MORDOR results for PRT 250/500/1000.
- `bank_count`: Figure 9 inputs.
- `blast_radius`: Figure 10 inputs.
- `row_policy`: Figure 11 inputs.
- `latency`: Figure 12's designated 429.mcf inputs.

Figure 10 currently uses {len(blast_traces)}/{len(paper_traces)} traces in
every bar. Excluded uniformly: {", ".join(excluded_blast) if excluded_blast else "none"}.

`manifest.csv` records the source and paper-figure consumers of every file.
"""
        (building / "README.md").write_text(readme)
        building.rename(destination)
    except Exception:
        if building.exists():
            shutil.rmtree(building)
        raise


def display_for_script(value: object) -> None:
    if hasattr(value, "to_string"):
        print(value.to_string(index=False))
    else:
        print(value)


def figure_filename(number: int) -> str:
    return f"Figure_{number:02d}_{FIGURE_SPECS[number]}.png"


def execute_silently(source_path: Path, namespace: dict[str, object]) -> None:
    """Run notebook-derived plotting code without exposing its diagnostics."""
    with (
        contextlib.redirect_stdout(io.StringIO()),
        contextlib.redirect_stderr(io.StringIO()),
    ):
        exec(
            compile(source_path.read_text(), str(source_path), "exec"),
            namespace,
        )


def execute_figure_sources(
    results_dir: Path,
    figures_dir: Path,
    dpi: int,
    selected_figures: set[int],
) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as error:
        raise RuntimeError(
            "Plotting dependencies are missing. Run this script with the "
            "repository virtual environment, e.g. `.venv/bin/python`."
        ) from error

    figures_dir.mkdir(parents=True, exist_ok=True)
    namespace: dict[str, object] = {
        "__name__": "__mordor_paper_figure_generator__",
        "__file__": str(Path(__file__).resolve()),
        "display": display_for_script,
    }

    old_cwd = Path.cwd()
    old_show = plt.show
    plt.show = lambda *args, **kwargs: None
    try:
        os.chdir(results_dir)
        context_sources = (
            (CONTEXT_SOURCES[0], FIGURE6_CONTEXT_SOURCE)
            if selected_figures == {6}
            else CONTEXT_SOURCES
        )
        for source_path in context_sources:
            execute_silently(source_path, namespace)

        for figure_number, source_path in FIGURE_SOURCES.items():
            if figure_number not in selected_figures:
                continue
            plt.close("all")
            for prerequisite in PRE_FIGURE_SOURCES.get(figure_number, ()):
                execute_silently(prerequisite, namespace)
            print(f"Generating Figure {figure_number}...")
            execute_silently(source_path, namespace)
            open_figures = [
                plt.figure(number) for number in plt.get_fignums()
            ]
            if len(open_figures) != 1:
                raise RuntimeError(
                    f"Figure {figure_number} produced "
                    f"{len(open_figures)} open Matplotlib figures; expected 1"
                )
            output = figures_dir / figure_filename(figure_number)
            open_figures[0].savefig(
                output,
                dpi=dpi,
                bbox_inches="tight",
                metadata={"Title": f"Figure {figure_number}"},
            )
            print(f"Saved {output}")
            plt.close("all")
    finally:
        plt.show = old_show
        os.chdir(old_cwd)


def write_figure_index(figures_dir: Path, selected_figures: set[int]) -> None:
    lines = ["# Reproduced data-derived paper figures", ""]
    for number in FIGURE_SOURCES:
        if number not in selected_figures:
            continue
        filename = figure_filename(number)
        lines.append(f"- Figure {number}: `{filename}`")
    if selected_figures == set(FIGURE_SOURCES):
        generated_description = (
            "Figures 2 and 5–14 are regenerated from `paper_results` using "
            "the canonical Python plotting sources."
        )
    else:
        generated_description = (
            "Figure 6 is regenerated from its compact `paper_results` bundle "
            "using the canonical Python plotting source."
        )
    lines.extend(
        [
            "",
            generated_description,
            "Conceptual Figures 1, 3, and 4 are intentionally not bundled or "
            "regenerated because the paper is not yet public.",
            "",
        ]
    )
    (figures_dir / "README.md").write_text("\n".join(lines))


def main() -> None:
    args = parse_args()
    results_dir = args.results_dir.resolve()
    source_root = args.source_root.resolve()
    figures_dir = args.figures_dir.resolve()
    selected_figures = set(args.figures)
    all_figures = set(FIGURE_SOURCES)
    if selected_figures not in (all_figures, {6}):
        raise SystemExit(
            "Reduced result-bundle generation currently supports only "
            "--figures 6; omit --figures to generate all data-derived figures."
        )
    paper_traces = load_paper_traces()

    if args.rebuild_results or not results_dir.is_dir():
        build_consolidated_results(
            source_root,
            results_dir,
            paper_traces,
            figure6_only=selected_figures == {6},
        )

    execute_figure_sources(
        results_dir=results_dir,
        figures_dir=figures_dir,
        dpi=args.dpi,
        selected_figures=selected_figures,
    )
    for number in set(FIGURE_SPECS) - selected_figures:
        (figures_dir / figure_filename(number)).unlink(missing_ok=True)
    write_figure_index(figures_dir, selected_figures)

    expected = {
        figure_filename(number)
        for number in selected_figures
    }
    present = {path.name for path in figures_dir.glob("Figure_*.png")}
    missing = sorted(expected - present)
    if missing:
        raise RuntimeError("Missing generated figures: " + ", ".join(missing))


if __name__ == "__main__":
    main()
