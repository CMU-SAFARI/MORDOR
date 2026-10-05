#!/usr/bin/env python3
"""Download, verify, and safely extract the canonical MORDOR trace set."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from common import TRACES


CHUNK_SIZE = 8 * 1024 * 1024


def trace_set_complete(destination: Path) -> bool:
    if not destination.is_dir():
        return False
    files = {path.name for path in destination.iterdir() if path.is_file()}
    return files == set(TRACES) and all(
        (destination / name).stat().st_size > 0 for name in TRACES
    )


def download(url: str, destination: Path, expected_sha256: str) -> None:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "MORDOR-reproduction/1.0"},
    )
    digest = hashlib.sha256()
    downloaded = 0
    next_report = 256 * 1024 * 1024
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            total = int(response.headers.get("Content-Length", 0))
            with destination.open("xb") as stream:
                while chunk := response.read(CHUNK_SIZE):
                    stream.write(chunk)
                    digest.update(chunk)
                    downloaded += len(chunk)
                    if downloaded >= next_report:
                        if total:
                            print(
                                f"  downloaded {downloaded / 1e9:.2f}/"
                                f"{total / 1e9:.2f} GB",
                                flush=True,
                            )
                        else:
                            print(f"  downloaded {downloaded / 1e9:.2f} GB", flush=True)
                        next_report += 256 * 1024 * 1024
    except urllib.error.HTTPError as error:
        raise SystemExit(
            f"trace download failed with HTTP {error.code}: {url}\n"
            "If this is a Zenodo preview draft, publish the record first."
        ) from error
    except urllib.error.URLError as error:
        raise SystemExit(f"trace download failed: {error.reason}") from error

    actual = digest.hexdigest()
    if actual != expected_sha256:
        raise SystemExit(
            "trace archive checksum mismatch:\n"
            f"  expected: {expected_sha256}\n"
            f"  received: {actual}"
        )


def extract(archive_path: Path, destination: Path) -> None:
    expected_files = {f"cputraces/{name}" for name in TRACES}
    allowed_members = expected_files | {"README.md", "SHA256SUMS", "cputraces"}
    temporary = Path(
        tempfile.mkdtemp(prefix=".cputraces-", dir=str(destination.parent))
    )
    try:
        with tarfile.open(archive_path, mode="r:gz") as archive:
            members = {member.name.rstrip("/"): member for member in archive}
            unexpected = set(members) - allowed_members
            missing = expected_files - set(members)
            if unexpected or missing:
                raise SystemExit(
                    "trace archive has an unexpected member set:\n"
                    f"  missing: {', '.join(sorted(missing)[:5]) or 'none'}\n"
                    f"  unexpected: {', '.join(sorted(unexpected)[:5]) or 'none'}"
                )

            for name in TRACES:
                member = members[f"cputraces/{name}"]
                if not member.isfile() or member.size <= 0:
                    raise SystemExit(f"invalid trace archive member: {member.name}")
                source = archive.extractfile(member)
                if source is None:
                    raise SystemExit(f"could not read trace archive member: {member.name}")
                target = temporary / name
                with source, target.open("xb") as stream:
                    shutil.copyfileobj(source, stream, CHUNK_SIZE)
                target.chmod(0o644)

        if destination.exists():
            if destination.is_symlink() or not destination.is_dir():
                raise SystemExit(f"refusing to replace unsafe trace path: {destination}")
            shutil.rmtree(destination)
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()

    expected_sha256 = args.sha256.strip().lower()
    if len(expected_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in expected_sha256
    ):
        raise SystemExit("--sha256 must be a 64-character hexadecimal digest")

    destination = args.destination.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if trace_set_complete(destination):
        print(f"Canonical trace set already present: {destination}")
        return

    descriptor, archive_name = tempfile.mkstemp(
        prefix=".mordor-cputraces-", suffix=".tar.gz", dir=str(destination.parent)
    )
    os.close(descriptor)
    archive_path = Path(archive_name)
    archive_path.unlink()
    try:
        print(f"Downloading canonical MORDOR traces from {args.url}", flush=True)
        download(args.url, archive_path, expected_sha256)
        print("Archive checksum verified; extracting 55 traces", flush=True)
        extract(archive_path, destination)
    finally:
        archive_path.unlink(missing_ok=True)

    if not trace_set_complete(destination):
        raise SystemExit("trace extraction completed but the canonical set is incomplete")
    print(f"Trace setup complete: 55/55 in {destination}")


if __name__ == "__main__":
    main()
