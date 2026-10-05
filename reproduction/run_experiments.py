#!/usr/bin/env python3
"""Generate, submit, or locally run the MORDOR simulation classes."""

from __future__ import annotations

import argparse
import copy
import getpass
import os
import re
import shlex
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

from common import (
    BLAST_RADII, EXPERIMENT_CLASSES, LATENCY_TRACES, MECHANISMS, TRACES,
    repo_root_from_script, resolve_path,
)
from paper_config import (
    LATENCY_INSTRUCTIONS, MAIN_BRC, MAIN_INSTRUCTIONS, MAIN_RADIUS,
    apply_paper_parameters, parameter_manifest,
)


@dataclass
class Case:
    experiment_class: str
    name: str
    config_path: Path
    result_dir: Path
    stem_prefix: str
    mechanism: str | None = None
    scheduler: str = "baseline"
    nominal_nrh: int = 125
    cores: int = 8
    instructions: int = MAIN_INSTRUCTIONS
    radius: int = MAIN_RADIUS
    drfm_setup: bool = False
    latency_only: bool = False
    remove_plugins: bool = False


def load_defaults(path: Path | None) -> dict:
    if path is None:
        return {}
    with path.open() as stream:
        data = yaml.safe_load(stream) or {}
    return data


def parse_args() -> argparse.Namespace:
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--config", type=Path)
    known, _ = pre.parse_known_args()
    defaults = load_defaults(known.config)
    paths = defaults.get("paths", {})
    slurm = defaults.get("slurm", {})
    execution = defaults.get("execution", {})

    parser = argparse.ArgumentParser(description=__doc__, parents=[pre])
    parser.add_argument("--repo-root", default=paths.get("repo_root", repo_root_from_script()))
    parser.add_argument("--trace-dir", default=paths.get("trace_dir", "cputraces/cputraces"))
    parser.add_argument("--workspace-root", default=paths.get("workspace_root", "reproduction_workspace"))
    parser.add_argument("--ramulator", default=paths.get("ramulator", "ramulator2"))
    parser.add_argument("--classes", nargs="+", choices=EXPERIMENT_CLASSES,
                        default=defaults.get("experiment_classes", ["main"]))
    parser.add_argument("--mechanisms", nargs="+", choices=MECHANISMS,
                        default=defaults.get("mechanisms", MECHANISMS))
    parser.add_argument("--traces", nargs="+", default=defaults.get("traces", TRACES))
    parser.add_argument("--backend", choices=("slurm", "local"),
                        default=execution.get("backend", "slurm"))
    parser.add_argument("--partition", default=slurm.get("partition"))
    parser.add_argument("--memory", default=slurm.get("memory", "6GB"))
    parser.add_argument("--exclude", default=slurm.get("exclude"))
    parser.add_argument("--time", default=slurm.get("time"))
    parser.add_argument("--account", default=slurm.get("account"))
    parser.add_argument("--qos", default=slurm.get("qos"))
    parser.add_argument("--constraint", default=slurm.get("constraint"))
    parser.add_argument("--sbatch-arg", action="append",
                        default=list(slurm.get("extra_args") or []))
    parser.add_argument("--job-preamble", action="append",
                        default=list(slurm.get("job_preamble") or []))
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--allow-missing-traces", action="store_true")
    parser.add_argument("--submit", action="store_true")
    parser.add_argument(
        "--run-local", action="store_true",
        help="execute generated jobs on this host (requires --backend local)",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help=(
            "submit or locally run only results that do not already pass "
            "semantic validation"
        ),
    )
    parser.add_argument(
        "--status", action="store_true",
        help="report valid, partial, invalid, active, and missing runs without generating jobs",
    )
    parser.add_argument("--list-classes", action="store_true")
    return parser.parse_args()


def config_file(repo: Path, mechanism: str, prt: int, scheduler: str) -> Path:
    return repo / "ramulator_configs" / f"example_ddr5_config_{mechanism}_{prt}_{scheduler}.yaml"


def add_main_cases(cases: list[Case], repo: Path, results: Path, mechanisms: list[str]) -> None:
    baseline = config_file(repo, "abacus", 125, "read")
    cases.append(Case(
        "main", "baseline", baseline, results / "baseline/no_mitigation", "",
        remove_plugins=True,
    ))
    for mechanism in mechanisms:
        cases.extend([
            Case("main", f"{mechanism}-priority", config_file(repo, mechanism, 125, "priority"),
                 results / "main/priority" / mechanism,
                 "", mechanism, "priority"),
            Case("main", f"{mechanism}-mordor", config_file(repo, mechanism, 125, "read"),
                 results / "main/mordor" / mechanism,
                 "", mechanism, "mordor"),
            Case("main", f"{mechanism}-insecure", config_file(repo, mechanism, 125, "read"),
                 results / "main/insecure" / mechanism,
                 "", mechanism, "insecure"),
        ])


def add_multi_prt_cases(cases: list[Case], repo: Path, results: Path,
                        mechanisms: list[str]) -> None:
    for prt in (250, 500, 1000):
        for mechanism in mechanisms:
            for source_scheduler, variant in (
                ("priority", "priority"),
                ("read", "mordor"),
            ):
                cases.append(Case(
                    "multi-prt", f"{mechanism}-{prt}-{variant}",
                    config_file(repo, mechanism, prt, source_scheduler),
                    results / "prt_sweep" / f"prt_{prt}" / variant / mechanism,
                    "", mechanism, variant, prt,
                ))


def add_latency_cases(cases: list[Case], repo: Path, results: Path,
                      mechanisms: list[str]) -> None:
    for mechanism in mechanisms:
        for source_scheduler, variant in (("priority", "priority"), ("read", "mordor")):
            cases.append(Case(
                "latency", f"{mechanism}-{variant}",
                config_file(repo, mechanism, 125, source_scheduler),
                results / "latency" / variant / mechanism,
                "", mechanism, variant, 125, 1, LATENCY_INSTRUCTIONS,
                latency_only=True,
            ))


def add_bank_cases(cases: list[Case], repo: Path, results: Path,
                   mechanisms: list[str]) -> None:
    for banks in (8, 32):
        baseline = (
            repo / "bank_count_study" / f"banks_{banks}"
            / "example_ddr5_config_abacus_125_read.yaml"
        )
        cases.append(Case(
            "bank-count", f"b{banks}-baseline", baseline,
            results / "bank_count" / f"banks_{banks}" / "baseline",
            "", remove_plugins=True,
        ))
        for mechanism in mechanisms:
            for source_scheduler, variant in (
                ("priority", "priority"),
                ("read", "mordor"),
            ):
                source = repo / "bank_count_study" / f"banks_{banks}" / (
                    f"example_ddr5_config_{mechanism}_125_{source_scheduler}.yaml"
                )
                cases.append(Case(
                    "bank-count", f"b{banks}-{mechanism}-{variant}", source,
                    results / "bank_count" / f"banks_{banks}"
                    / variant / mechanism,
                    "", mechanism, variant,
                ))


def add_blast_cases(cases: list[Case], repo: Path, results: Path,
                    mechanisms: list[str]) -> None:
    for radius in BLAST_RADII:
        for mechanism in mechanisms:
            for source_scheduler, variant in (
                ("priority", "priority"),
                ("read", "mordor"),
            ):
                source = config_file(repo, mechanism, 125, source_scheduler)
                cases.append(Case(
                    "blast-radius", f"r{radius}-{mechanism}-{variant}", source,
                    results / "blast_radius" / "brc_2" / f"radius_{radius}"
                    / variant / mechanism,
                    "", mechanism, variant, 125, 8, MAIN_INSTRUCTIONS, radius,
                ))


def add_drfm_setup_cases(cases: list[Case], repo: Path, results: Path,
                         mechanisms: list[str]) -> None:
    for mechanism in mechanisms:
        cases.append(Case(
            "drfm-address-setup", f"drfm-setup-{mechanism}-mordor",
            config_file(repo, mechanism, 125, "read"),
            results / "drfm_address_setup" / "mordor" / mechanism,
            "", mechanism, "mordor", 125, 8, MAIN_INSTRUCTIONS, MAIN_RADIUS,
            True,
        ))


def build_cases(classes: list[str], repo: Path, results: Path,
                mechanisms: list[str]) -> list[Case]:
    cases: list[Case] = []
    builders = {
        "main": lambda: add_main_cases(cases, repo, results, mechanisms),
        "multi-prt": lambda: add_multi_prt_cases(cases, repo, results, mechanisms),
        "latency": lambda: add_latency_cases(cases, repo, results, mechanisms),
        "bank-count": lambda: add_bank_cases(cases, repo, results, mechanisms),
        "blast-radius": lambda: add_blast_cases(cases, repo, results, mechanisms),
        "drfm-address-setup": lambda: add_drfm_setup_cases(cases, repo, results, mechanisms),
    }
    for name in classes:
        builders[name]()
    return cases


def configure(case: Case, trace_path: Path) -> dict:
    with case.config_path.open() as stream:
        config = yaml.safe_load(stream)
    config = copy.deepcopy(config)
    config["Frontend"]["traces"] = [str(trace_path)] * case.cores
    controller = config["MemorySystem"]["Controller"]
    if case.remove_plugins:
        controller.pop("plugins", None)
        config["Frontend"]["num_expected_insts"] = case.instructions
        dram = config["MemorySystem"]["DRAM"]
        dram["RFM"] = {"BRC": MAIN_BRC}
        dram["RH_radius"] = case.radius
        return config
    if case.mechanism is None:
        raise ValueError(f"{case.name}: non-baseline case has no mechanism")
    apply_paper_parameters(
        config, case.mechanism, case.nominal_nrh, case.scheduler,
        radius=case.radius, drfm_setup=case.drfm_setup,
        instructions=case.instructions,
    )
    if case.latency_only:
        controller["log_request_latencies"] = 1
    return config


def case_manifest(case: Case, trace: str) -> dict:
    if case.remove_plugins:
        return {
            "experiment_class": case.experiment_class,
            "trace": trace,
            "scheduler": "baseline",
            "brc": MAIN_BRC,
            "blast_radius": case.radius,
            "instructions": case.instructions,
            "cores": case.cores,
        }
    assert case.mechanism is not None
    manifest = parameter_manifest(
        case.mechanism, case.nominal_nrh, case.scheduler,
        radius=case.radius, drfm_setup=case.drfm_setup,
        instructions=case.instructions, cores=case.cores,
    )
    manifest.update({"experiment_class": case.experiment_class, "trace": trace})
    return manifest


def active_jobs() -> set[str]:
    result = subprocess.run(
        ["squeue", "--noheader", "--user", getpass.getuser(), "--format=%j"],
        check=True, capture_output=True, text=True,
    )
    return set(result.stdout.splitlines())


def output_path(case: Case, trace: str) -> Path:
    suffix = "_latency.txt" if case.latency_only else "_output.yaml"
    return case.result_dir / f"{case.stem_prefix}{trace}{suffix}"


def partial_path(result: Path) -> Path:
    if result.name.endswith("_output.yaml"):
        return result.with_name(result.name.removesuffix(".yaml") + ".partial.yaml")
    if result.name.endswith("_latency.txt"):
        return result.with_name(result.name.removesuffix(".txt") + ".partial.txt")
    return result.with_name(result.name + ".partial")


def is_valid_result(path: Path, case: Case) -> bool:
    """Perform the same lightweight semantic checks as the job-side validator."""
    if not path.is_file() or path.stat().st_size == 0:
        return False
    text = path.read_text(errors="replace")
    if case.latency_only:
        return "[Lat (RD): " in text or "[Lat (PRO): " in text or "[Lat(PRO): " in text
    required = ["memory_system_cycles", "total_energy"]
    required.extend(f"cycles_recorded_core_{core}" for core in range(case.cores))
    return all(
        re.search(rf"^\s*{re.escape(key)}\s*:", text, re.MULTILINE)
        for key in required
    )


def report_status(cases: list[Case], traces: list[str], backend: str) -> int:
    active: set[str] = set()
    if backend == "slurm":
        try:
            active = active_jobs()
        except (FileNotFoundError, subprocess.CalledProcessError):
            active = set()
    totals: dict[str, dict[str, int]] = {}
    invalid_names: list[str] = []
    for case in cases:
        counts = totals.setdefault(
            case.experiment_class,
            {"valid": 0, "active": 0, "partial": 0, "invalid": 0, "missing": 0},
        )
        case_traces = LATENCY_TRACES if case.latency_only and traces == TRACES else traces
        for trace in case_traces:
            result = output_path(case, trace)
            job_name = f"mordor_{case.name}_{trace}".replace("_output", "")
            if is_valid_result(result, case):
                counts["valid"] += 1
            elif job_name in active:
                counts["active"] += 1
            elif partial_path(result).exists():
                counts["partial"] += 1
                invalid_names.append(f"{case.experiment_class}\tpartial\t{case.name}\t{trace}")
            elif result.exists():
                counts["invalid"] += 1
                invalid_names.append(f"{case.experiment_class}\tinvalid\t{case.name}\t{trace}")
            else:
                counts["missing"] += 1
                invalid_names.append(f"{case.experiment_class}\tmissing\t{case.name}\t{trace}")
    all_valid = True
    for name in dict.fromkeys(case.experiment_class for case in cases):
        counts = totals[name]
        total = sum(counts.values())
        all_valid &= counts["valid"] == total
        print(
            f"{name}: {counts['valid']}/{total} valid; "
            f"{counts['active']} active, {counts['partial']} partial, "
            f"{counts['invalid']} invalid, {counts['missing']} missing"
        )
    if invalid_names:
        print("\nIncomplete runs:")
        shown = invalid_names[:100]
        print("\n".join(shown))
        if len(invalid_names) > len(shown):
            print(f"... {len(invalid_names) - len(shown)} additional incomplete runs omitted")
    return 0 if all_valid else 1


def run_local_jobs(
    jobs: list[tuple[str, Path, Path]],
    repo: Path,
) -> None:
    """Run generated job scripts serially and retain one log per simulation."""
    failures: list[str] = []
    print(
        f"Running {len(jobs)} local jobs serially. "
        "Interrupting is safe; rerun with resume to continue."
    )
    for completed, (name, script, log) in enumerate(jobs, start=1):
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("w") as stream:
            process = subprocess.Popen(
                [str(script)],
                cwd=repo,
                stdout=stream,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            try:
                returncode = process.wait()
            except KeyboardInterrupt:
                print(
                    "\nStopping the active local job; validated outputs "
                    "remain resumable."
                )
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait()
                raise SystemExit(130)
        if returncode:
            failures.append(name)
            print(f"[{completed}/{len(jobs)}] FAILED {name}")
        else:
            print(f"[{completed}/{len(jobs)}] completed {name}")
    if failures:
        shown = ", ".join(failures[:10])
        extra = f" (+{len(failures) - 10} more)" if len(failures) > 10 else ""
        raise SystemExit(
            f"{len(failures)} local jobs failed: {shown}{extra}. "
            "Inspect the corresponding *_local.log files."
        )


def main() -> None:
    args = parse_args()
    if args.backend == "slurm" and args.run_local:
        raise SystemExit("--run-local requires --backend local")
    if args.backend == "local" and args.submit:
        raise SystemExit("--submit requires --backend slurm; use --run-local")
    if args.list_classes:
        print("\n".join(EXPERIMENT_CLASSES))
        return
    repo = resolve_path(args.repo_root, Path.cwd())
    trace_dir = resolve_path(args.trace_dir, repo)
    workspace = resolve_path(args.workspace_root, repo)
    ramulator = resolve_path(args.ramulator, repo)
    results = workspace / "results"
    scripts = workspace / ("slurm" if args.backend == "slurm" else "local_jobs")
    if not ramulator.is_file():
        raise FileNotFoundError(f"Ramulator binary not found: {ramulator}")
    missing = [trace for trace in args.traces if not (trace_dir / trace).is_file()]
    if missing and not args.allow_missing_traces:
        raise FileNotFoundError(
            f"Missing {len(missing)} traces in {trace_dir}; first missing: {missing[0]}"
        )

    cases = build_cases(args.classes, repo, results, args.mechanisms)
    if args.status:
        raise SystemExit(report_status(cases, args.traces, args.backend))

    commands: list[tuple[str, list[str]]] = []
    local_jobs: list[tuple[str, Path, Path]] = []
    skipped = 0
    for case in cases:
        if not case.config_path.is_file():
            raise FileNotFoundError(case.config_path)
        case_traces = (LATENCY_TRACES
                       if case.experiment_class == "latency" and args.traces == TRACES
                       else args.traces)
        for trace in case_traces:
            stem = case.stem_prefix + trace
            output = output_path(case, trace)
            if args.resume and is_valid_result(output, case):
                skipped += 1
                continue
            if args.skip_existing and output.is_file() and output.stat().st_size:
                skipped += 1
                continue
            run_dir = scripts / case.experiment_class / case.name
            run_dir.mkdir(parents=True, exist_ok=True)
            case.result_dir.mkdir(parents=True, exist_ok=True)
            generated = run_dir / f"{stem}_config.yaml"
            generated_manifest = run_dir / f"{stem}_manifest.yaml"
            job_script = run_dir / f"{stem}.sh"
            with generated.open("w") as stream:
                yaml.safe_dump(configure(case, trace_dir / trace), stream, sort_keys=False)
            with generated_manifest.open("w") as stream:
                yaml.safe_dump(case_manifest(case, trace), stream, sort_keys=False)
            partial = partial_path(output)
            slurm_log = case.result_dir / f"{stem}_slurm.log"
            validator = Path(__file__).resolve().parent / "validate_result.py"
            command_line = f"{shlex.quote(str(ramulator))} -f {shlex.quote(str(generated))}"
            if case.latency_only:
                command_line += " | awk '/^\\[Lat \\(RD\\): [0-9]+\\]$/ || /^\\[Lat ?\\(PRO\\): [0-9]+\\]$/'"
            else:
                command_line += " 2>&1 | grep -v '\\[debug\\]'"
            validation = [
                sys.executable, str(validator), str(partial),
                "--cores", str(case.cores),
            ]
            if case.latency_only:
                validation.append("--latency")
            preamble = "\n".join(args.job_preamble)
            if preamble:
                preamble += "\n"
            job_script.write_text(
                "#!/bin/bash\n"
                "set -euo pipefail\n"
                f"{preamble}"
                f"rm -f {shlex.quote(str(partial))}\n"
                f"{command_line} > {shlex.quote(str(partial))}\n"
                f"{shlex.join(validation)}\n"
                f"mv {shlex.quote(str(partial))} {shlex.quote(str(output))}\n"
            )
            job_script.chmod(0o755)
            job_name = f"mordor_{case.name}_{trace}".replace("_output", "")
            local_log = case.result_dir / f"{stem}_local.log"
            local_jobs.append((job_name, job_script, local_log))
            sbatch = [
                "sbatch", "--cpus-per-task=1", "--nodes=1", "--ntasks=1",
                f"--chdir={repo}", f"--output={slurm_log}",
                f"--error={case.result_dir / (stem + '_slurm_error.log')}",
                "--open-mode=truncate",
                f"--mem={args.memory}", f"--job-name={job_name}", "--parsable",
            ]
            if args.partition:
                sbatch.append(f"--partition={args.partition}")
            if args.exclude:
                sbatch.append(f"--exclude={args.exclude}")
            if args.time:
                sbatch.append(f"--time={args.time}")
            if args.account:
                sbatch.append(f"--account={args.account}")
            if args.qos:
                sbatch.append(f"--qos={args.qos}")
            if args.constraint:
                sbatch.append(f"--constraint={args.constraint}")
            sbatch.extend(args.sbatch_arg)
            sbatch.append(str(job_script))
            commands.append((case.experiment_class, sbatch))

    scripts.mkdir(parents=True, exist_ok=True)
    if args.backend == "slurm":
        for name in args.classes:
            selected = [cmd for cls, cmd in commands if cls == name]
            master = scripts / f"submit_{name}.sh"
            master.write_text(
                "#!/bin/bash\nset -e\n"
                + "\n".join(map(shlex.join, selected)) + "\n"
            )
            master.chmod(0o755)
        master = scripts / "submit_all.sh"
        master.write_text(
            "#!/bin/bash\nset -e\n"
            + "\n".join(shlex.join(c) for _, c in commands) + "\n"
        )
        master.chmod(0o755)
    else:
        header = "#!/bin/bash\nset -euo pipefail\n"
        master = scripts / "run_all_local.sh"
        lines = [
            f"{shlex.quote(str(script))} > {shlex.quote(str(log))} 2>&1"
            for _, script, log in local_jobs
        ]
        master.write_text(header + "\n".join(lines) + "\n")
        master.chmod(0o755)

    should_execute = args.submit or args.resume or args.run_local
    if not should_execute:
        count = len(commands) if args.backend == "slurm" else len(local_jobs)
        print(f"Generated {count} {args.backend} jobs; skipped {skipped} existing outputs.")
        print(f"Review generated scripts under {scripts}")
        return
    if args.backend == "local":
        run_local_jobs(local_jobs, repo)
        print(f"Completed {len(local_jobs)} local jobs; skipped {skipped} valid outputs.")
        return

    active = active_jobs()
    manifest = scripts / "submitted_job_ids.tsv"
    submitted = skipped_active = 0
    with manifest.open("a") as stream:
        for experiment_class, command in commands:
            job_name = next(x.removeprefix("--job-name=") for x in command
                            if x.startswith("--job-name="))
            if job_name in active:
                skipped_active += 1
                continue
            result = subprocess.run(command, check=True, capture_output=True, text=True)
            stream.write(f"{result.stdout.strip().split(';')[0]}\t{experiment_class}\t{job_name}\n")
            submitted += 1
    print(f"Submitted {submitted}; skipped {skipped_active} active and {skipped} completed jobs.")


if __name__ == "__main__":
    main()
