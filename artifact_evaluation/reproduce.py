#!/usr/bin/env python3
"""Coordinate hosted, generic-Slurm, local, plotting, and OpenROAD workflows."""

from __future__ import annotations

import argparse
import os
import posixpath
import shlex
import subprocess
import sys
from pathlib import Path, PurePosixPath

import yaml

from common import EXPERIMENT_CLASSES, resolve_path


SCRIPT_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = SCRIPT_DIR.parent
DEFAULT_SLURM_PROFILE = SCRIPT_DIR / "generic_slurm_config.yaml"
DEFAULT_LOCAL_PROFILE = SCRIPT_DIR / "local_config.yaml"


def load_config(path: Path) -> dict:
    with path.open() as stream:
        config = yaml.safe_load(stream) or {}
    if "cluster" not in config or "local" not in config:
        raise ValueError(f"{path} must contain cluster and local mappings")
    return config


def load_execution_profile(path: Path, backend: str) -> dict:
    with path.open() as stream:
        profile = yaml.safe_load(stream) or {}
    configured_backend = profile.get("execution", {}).get("backend")
    if configured_backend != backend:
        raise SystemExit(
            f"{path} configures backend {configured_backend!r}, expected {backend!r}"
        )
    if "paths" not in profile or "traces" not in profile:
        raise SystemExit(f"{path} must contain paths and traces mappings")
    return profile


def profile_path(value: str | Path) -> Path:
    return resolve_path(value, PACKAGE_ROOT)


def native_paths(profile: dict) -> dict[str, Path]:
    paths = profile["paths"]
    return {
        "repo_root": profile_path(paths.get("repo_root", "ramulator")),
        "trace_dir": profile_path(paths.get("trace_dir", "cputraces")),
        "workspace_root": profile_path(paths.get("workspace_root", ".")),
        "ramulator": profile_path(
            paths.get("ramulator", "ramulator/build/ramulator2")
        ),
    }


def native_setup(profile: dict, backend: str) -> None:
    paths = native_paths(profile)
    traces = profile["traces"]
    url = traces.get("archive_url")
    sha256 = traces.get("archive_sha256")
    if not url or not sha256:
        raise SystemExit(
            "execution profile requires traces.archive_url and archive_sha256"
        )
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIR / "fetch_traces.py"),
            "--url", os.path.expandvars(str(url)),
            "--sha256", str(sha256),
            "--destination", str(paths["trace_dir"]),
        ],
        check=True,
    )
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIR / "check_cluster.py"),
            "--backend", backend,
            "--repo-root", str(paths["repo_root"]),
            "--workspace-root", str(paths["workspace_root"]),
            "--trace-dir", str(paths["trace_dir"]),
            "--ramulator", str(paths["ramulator"]),
            "--build",
        ],
        check=True,
    )


def native_command(
    profile: dict,
    backend: str,
    action: str,
    classes: list[str],
    traces: list[str] | None,
) -> list[str]:
    paths = native_paths(profile)
    command = [
        sys.executable,
        str(SCRIPT_DIR / "run_experiments.py"),
        "--backend", backend,
        "--repo-root", str(paths["repo_root"]),
        "--workspace-root", str(paths["workspace_root"]),
        "--trace-dir", str(paths["trace_dir"]),
        "--ramulator", str(paths["ramulator"]),
        "--classes", *classes,
    ]
    if traces:
        command.extend(["--traces", *traces])
    if backend == "slurm":
        slurm = profile.get("slurm", {})
        for key, option in (
            ("partition", "--partition"),
            ("memory", "--memory"),
            ("exclude", "--exclude"),
            ("time", "--time"),
            ("account", "--account"),
            ("qos", "--qos"),
            ("constraint", "--constraint"),
        ):
            value = slurm.get(key)
            if value not in (None, ""):
                command.extend([option, str(value)])
        for value in slurm.get("extra_args") or []:
            command.append(f"--sbatch-arg={value}")
        for value in slurm.get("job_preamble") or []:
            command.append(f"--job-preamble={value}")
    else:
        local = profile.get("local", {})
        for value in local.get("job_preamble") or []:
            command.append(f"--job-preamble={value}")
    if action == "submit":
        command.append("--submit")
    elif action == "run":
        command.append("--run-local")
    elif action == "resume":
        command.append("--resume")
    elif action in ("status", "progress"):
        command.append("--status")
    return command


def add_native_parser(
    subparsers: argparse._SubParsersAction,
    backend: str,
    default_profile: Path,
) -> None:
    parser = subparsers.add_parser(backend)
    actions = (
        ("setup", "build", "plan", "submit", "status", "progress", "resume")
        if backend == "slurm"
        else ("setup", "build", "plan", "run", "status", "progress", "resume")
    )
    parser.add_argument("action", choices=actions)
    parser.add_argument("--profile", type=Path, default=default_profile)
    parser.add_argument(
        "--classes", nargs="+", choices=EXPERIMENT_CLASSES,
        default=EXPERIMENT_CLASSES,
    )
    parser.add_argument("--traces", nargs="+")


def identity_file(config: dict, repo: Path) -> Path:
    value = config["cluster"].get("identity_file", "credentials/ae_cluster_key")
    return resolve_path(value, repo)


def validate_identity(config: dict, repo: Path) -> Path:
    identity = identity_file(config, repo)
    if not identity.is_file() or identity.stat().st_size == 0:
        raise SystemExit(
            f"SSH private key is missing or empty: {identity}\n"
            "Copy the evaluator key there and run ./setup_ae.sh."
        )
    if "PRIVATE KEY-----" not in identity.read_text(errors="replace"):
        raise SystemExit(
            f"SSH private-key slot does not contain a private key: {identity}"
        )
    mode = identity.stat().st_mode & 0o777
    if mode & 0o077:
        identity.chmod(0o600)
    return identity


def ssh_transport(config: dict, repo: Path) -> list[str]:
    cluster = config["cluster"]
    identity = validate_identity(config, repo)
    command = [
        "ssh", "-i", str(identity), "-o", "IdentitiesOnly=yes",
        "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new",
    ]
    if cluster.get("port"):
        command.extend(["-p", str(cluster["port"])])
    if cluster.get("proxy_jump"):
        command.extend(["-J", str(cluster["proxy_jump"])])
    return command


def ssh_command(
    config: dict,
    repo: Path,
    remote_command: list[str],
    *,
    use_working_directory: bool = True,
) -> list[str]:
    command = shlex.join(remote_command)
    working_directory = config["cluster"].get("working_directory")
    if use_working_directory and working_directory:
        directory = os.path.expandvars(str(working_directory))
        command = f"cd -- {shlex.quote(directory)} && {command}"
    return [
        *ssh_transport(config, repo),
        config["cluster"]["host"],
        command,
    ]


def validate_remote_repo_target(value: str) -> str:
    path = PurePosixPath(value)
    if value.strip() in ("", ".", "/", "~") or ".." in path.parts:
        raise SystemExit(f"Refusing unsafe remote repository target: {value!r}")
    if path.is_absolute() and len(path.parts) < 3:
        raise SystemExit(f"Remote repository target is too broad: {value!r}")
    return value.rstrip("/")


def source_revision(repo: Path) -> str | None:
    try:
        top = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--show-toplevel"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        if Path(top).resolve() != repo.resolve():
            return None
        revision = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        changes = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        if changes:
            raise SystemExit(
                "The local artifact checkout has uncommitted or untracked files. "
                "Commit, remove, or ignore them before uploading the AE source."
            )
        return revision
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None


def upload_source(config: dict, repo: Path) -> None:
    cluster = config["cluster"]
    host = cluster["host"]
    remote_repo = validate_remote_repo_target(
        os.path.expandvars(cluster["repo_root"])
    )
    python = cluster.get("python", "python3")
    mkdir_code = (
        "from pathlib import Path; "
        f"Path({remote_repo!r}).mkdir(parents=True, exist_ok=True)"
    )
    subprocess.run(
        ssh_command(
            config,
            repo,
            [python, "-c", mkdir_code],
            use_working_directory=False,
        ),
        check=True,
    )

    revision = source_revision(repo)
    description = f" at revision {revision}" if revision else ""
    print(f"Uploading local artifact{description} to {host}:{remote_repo}/")
    transport = shlex.join(ssh_transport(config, repo))
    subprocess.run(
        [
            "rsync", "-a", "--delete", "-e", transport,
            "--exclude=/.git/",
            "--exclude=/credentials/",
            "--exclude=/.venv/",
            "--exclude=/artifact_workspace/",
            "--exclude=/cputraces/",
            "--exclude=/results/",
            "--exclude=/paper_results/",
            "--exclude=/figures/",
            "--exclude=/slurm/",
            "--exclude=/ramulator/build/",
            "--exclude=/ramulator/libramulator.so",
            "--exclude=/ramulator/ramulator2",
            "--exclude=/openroad/out/",
            "--exclude=__pycache__/",
            "--exclude=*.pyc",
            f"{repo}/", f"{host}:{remote_repo}/",
        ],
        check=True,
    )
    if revision:
        revision_file = f"{remote_repo}/.artifact_source_revision"
        revision_code = (
            "from pathlib import Path; "
            f"Path({revision_file!r}).write_text({(revision + chr(10))!r})"
        )
        subprocess.run(
            ssh_command(config, repo, [python, "-c", revision_code]),
            check=True,
        )


def relative_to_remote_repo(value: str, remote_repo: str) -> str:
    """Express an SSH-home-relative path relative to the Ramulator source."""
    if value.startswith("/"):
        return value
    return posixpath.relpath(value, start=remote_repo)


def cluster_command(
    config: dict,
    action: str,
    classes: list[str],
    traces: list[str] | None = None,
) -> list[str]:
    cluster = config["cluster"]
    remote_repo = os.path.expandvars(cluster["repo_root"])
    remote_ramulator_root = f"{remote_repo}/ramulator"
    remote_workspace = relative_to_remote_repo(
        os.path.expandvars(cluster["workspace_root"]), remote_ramulator_root
    )
    remote_trace_dir = os.path.expandvars(cluster["trace_dir"])
    remote_ramulator = relative_to_remote_repo(
        os.path.expandvars(
            cluster.get("ramulator", f"{remote_ramulator_root}/build/ramulator2")
        ),
        remote_ramulator_root,
    )
    command = [
        cluster.get("python", "python3"),
        f"{remote_repo}/artifact_evaluation/run_experiments.py",
        "--repo-root", remote_ramulator_root,
        "--workspace-root", remote_workspace,
        "--trace-dir", remote_trace_dir,
        "--ramulator", remote_ramulator,
        "--partition", cluster.get("partition", "high_latency"),
        "--memory", cluster.get("memory", "6GB"),
        "--classes", *classes,
    ]
    if traces:
        command.extend(["--traces", *traces])
    if cluster.get("exclude"):
        command.extend(["--exclude", str(cluster["exclude"])])
    if cluster.get("time"):
        command.extend(["--time", str(cluster["time"])])
    if action == "submit":
        command.append("--submit")
    elif action == "resume":
        command.append("--resume")
    elif action == "status":
        command.append("--status")
    return command


def run_remote(
    config: dict,
    repo: Path,
    action: str,
    classes: list[str],
    traces: list[str] | None = None,
    check: bool = True,
) -> int:
    cluster = config["cluster"]
    host = cluster["host"]
    if action == "build":
        remote_repo = os.path.expandvars(cluster["repo_root"])
        command = [
            cluster.get("python", "python3"),
            f"{remote_repo}/artifact_evaluation/run_artifact.py",
            "build",
        ]
    elif action == "setup":
        upload_source(config, repo)
        remote_repo = os.path.expandvars(cluster["repo_root"])
        remote_ramulator_root = f"{remote_repo}/ramulator"
        trace_url = cluster.get("trace_archive_url")
        trace_sha256 = cluster.get("trace_archive_sha256")
        if not trace_url or not trace_sha256:
            raise SystemExit(
                "cluster setup requires trace_archive_url and "
                "trace_archive_sha256 in the cluster configuration"
            )
        fetch_command = [
            cluster.get("python", "python3"),
            f"{remote_repo}/artifact_evaluation/fetch_traces.py",
            "--url", os.path.expandvars(str(trace_url)),
            "--sha256", str(trace_sha256),
            "--destination", os.path.expandvars(cluster["trace_dir"]),
        ]
        print(f"{host}: {shlex.join(fetch_command)}")
        subprocess.run(ssh_command(config, repo, fetch_command), check=True)
        command = [
            cluster.get("python", "python3"),
            f"{remote_repo}/artifact_evaluation/check_cluster.py",
            "--repo-root", remote_ramulator_root,
            "--workspace-root", os.path.expandvars(cluster["workspace_root"]),
            "--trace-dir", os.path.expandvars(cluster["trace_dir"]),
            "--ramulator", os.path.expandvars(
                cluster.get("ramulator", f"{remote_ramulator_root}/build/ramulator2")
            ),
            "--build",
        ]
    else:
        command = cluster_command(config, action, classes, traces)
    print(f"{host}: {shlex.join(command)}")
    result = subprocess.run(ssh_command(config, repo, command))
    if check and result.returncode:
        raise SystemExit(result.returncode)
    return result.returncode


def fetch_results(
    config: dict,
    repo: Path,
    classes: list[str],
    traces: list[str] | None = None,
    allow_incomplete: bool = False,
) -> None:
    cluster = config["cluster"]
    host = cluster["host"]
    status = run_remote(
        config, repo, "status", classes, traces=traces, check=False
    )
    if status and not allow_incomplete:
        raise SystemExit(
            "Remote results are incomplete; nothing was downloaded.\n"
            "Run './reproduce.py cluster progress' for details, or use "
            "'cluster fetch --allow-incomplete' to inspect partial progress."
        )
    if status:
        print("Warning: downloading an incomplete result set.")

    workspace = os.path.expandvars(cluster["workspace_root"]).rstrip("/")
    local_results = resolve_path(config["local"]["results_root"], repo)
    local_results.mkdir(parents=True, exist_ok=True)
    transport = shlex.join(ssh_transport(config, repo))
    subprocess.run(
        [
            "rsync", "-a", "-e", transport,
            "--exclude=*.partial.yaml", "--exclude=*.partial.txt",
            "--include=/baseline/***", "--include=/main/***",
            "--include=/prt_sweep/***", "--include=/latency/***",
            "--include=/bank_count/***", "--include=/blast_radius/***",
            "--include=/row_policy/***", "--exclude=*",
            f"{host}:{workspace}/results/", f"{local_results}/",
        ],
        check=True,
    )
    local_slurm = local_results.parent / "slurm"
    local_slurm.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "rsync", "-a", "-e", transport,
            f"{host}:{workspace}/slurm/", f"{local_slurm}/",
        ],
        check=True,
    )
    print(f"Validated results synchronized to {local_results}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path,
        default=SCRIPT_DIR / "ae_cluster_config.yaml",
        help="local cluster/reproduction configuration",
    )
    subparsers = parser.add_subparsers(dest="target", required=True)

    cluster_parser = subparsers.add_parser("cluster")
    cluster_parser.add_argument(
        "action",
        choices=[
            "setup", "build", "plan", "submit", "status", "progress", "resume", "fetch"
        ],
    )
    cluster_parser.add_argument(
        "--classes", nargs="+", choices=EXPERIMENT_CLASSES,
        default=EXPERIMENT_CLASSES,
    )
    cluster_parser.add_argument(
        "--traces",
        nargs="+",
        help=(
            "run or validate only these trace names; omit for the canonical "
            "paper cohorts"
        ),
    )
    cluster_parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="allow fetch before every selected result passes validation",
    )

    openroad_parser = subparsers.add_parser("openroad")
    openroad_parser.add_argument("arguments", nargs=argparse.REMAINDER)

    figure_parser = subparsers.add_parser("figures")
    figure_parser.add_argument("arguments", nargs=argparse.REMAINDER)
    add_native_parser(subparsers, "slurm", DEFAULT_SLURM_PROFILE)
    add_native_parser(subparsers, "local", DEFAULT_LOCAL_PROFILE)

    args = parser.parse_args()
    repo = PACKAGE_ROOT

    if args.target == "cluster":
        config = load_config(args.config)
        if args.action == "fetch":
            fetch_results(
                config,
                repo,
                args.classes,
                traces=args.traces,
                allow_incomplete=args.allow_incomplete,
            )
        else:
            action = "status" if args.action == "progress" else args.action
            run_remote(config, repo, action, args.classes, traces=args.traces)
        return
    if args.target in ("slurm", "local"):
        profile = load_execution_profile(profile_path(args.profile), args.target)
        if args.action == "setup":
            native_setup(profile, args.target)
            return
        if args.action == "build":
            subprocess.run(
                [sys.executable, str(SCRIPT_DIR / "run_artifact.py"), "build"],
                check=True,
            )
            return
        subprocess.run(
            native_command(
                profile, args.target, args.action, args.classes, args.traces
            ),
            check=True,
        )
        return
    config = load_config(args.config)
    if args.target == "openroad":
        forwarded = args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
        openroad_dir = resolve_path(config["local"]["openroad_dir"], repo)
        subprocess.run(
            [str(openroad_dir / "reproduce_table1.sh"), *forwarded],
            cwd=openroad_dir,
            check=True,
        )
        return

    local = config["local"]
    forwarded = args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
    plot_script = resolve_path(local["plot_script"], repo)
    command = [
        sys.executable, str(plot_script),
        "--source-root", str(resolve_path(local["results_root"], repo)),
        "--results-dir", str(resolve_path(local["paper_results_dir"], repo)),
        "--figures-dir", str(resolve_path(local["figure_dir"], repo)),
        "--rebuild-results",
        *forwarded,
    ]
    subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
