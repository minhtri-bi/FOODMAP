"""Prepare the pinned pilot PBF with the bounded, project-local Osmium container."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from backend.import_osm import BOUNDS, EXPECTED_MD5, OBSERVED_AT, SOURCE_URL

TOOLS_IMAGE = "foodroute-routing-tools:3.9.1-osmium1.16.0"


def prepare(source: Path, output: Path) -> None:
    source, output = source.resolve(), output.resolve()
    if not source.is_file() or source.stat().st_size > 512 * 1024 * 1024:
        raise ValueError("Expected the pinned local PBF below 512 MiB.")
    with source.open("rb") as stream:
        checksum = hashlib.file_digest(stream, "md5").hexdigest()
    if checksum != EXPECTED_MD5:
        raise ValueError("PBF checksum differs from the approved snapshot.")
    if output.exists() and any(path.name != "valhalla.json" for path in output.iterdir()):
        raise FileExistsError("Routing artifacts already exist; inspect them instead of overwriting.")
    output.mkdir(parents=True, exist_ok=True)
    command = [
        "docker", "run", "--rm", "--name", "foodroute-r0-extract", "--cpus", "2",
        "--memory", "4g", "--memory-swap", "4g", "--pids-limit", "128",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--network", "none",
        "--mount", f"type=bind,source={source},target=/input.osm.pbf,readonly",
        "--mount", f"type=bind,source={output},target=/data", TOOLS_IMAGE,
        "osmium", "extract", "-b", "106.2,10.35,107.1,11.2", "-s", "smart",
        "-S", "types=restriction", "-o", "/data/pilot.osm.pbf", "/input.osm.pbf", "-v",
    ]
    try:
        subprocess.run(command, check=True, timeout=300)
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "stop", "foodroute-r0-extract"], check=True, timeout=30)
        raise
    metadata(source, output)


def metadata(source: Path, output: Path) -> None:
    """Record provenance after a successful extraction, never claim a graph build."""
    with source.open("rb") as stream:
        source_checksum = hashlib.file_digest(stream, "md5").hexdigest()
    if source_checksum != EXPECTED_MD5:
        raise ValueError("Source checksum differs from the pinned snapshot.")
    with (output / "pilot.osm.pbf").open("rb") as stream:
        extracted_checksum = hashlib.file_digest(stream, "sha256").hexdigest()
    document = {
        "source_url": SOURCE_URL, "source_md5": source_checksum, "snapshot": OBSERVED_AT,
        "bounds_south_west_north_east": BOUNDS,
        "coverage": "Pilot rectangle, not an administrative boundary. Complete ways touching the rectangle and completed restriction relations. Boundary routes may be truncated; source access tags may be incomplete.",
        "license": "ODbL-1.0", "extract_sha256": extracted_checksum,
    }
    (output / "source.json").write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(document))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pbf", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    prepare(args.pbf, args.output)
