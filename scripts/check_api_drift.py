import argparse
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def generate_types(output: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="event-openapi-") as directory:
        schema = Path(directory) / "openapi.json"
        subprocess.run(
            [sys.executable, str(ROOT / "scripts/export_openapi.py"), str(schema)],
            check=True,
        )
        command = shlex.split(os.environ.get("PNPM", "corepack pnpm"))
        subprocess.run(
            [
                *command,
                "exec",
                "openapi-typescript",
                str(schema),
                "--output",
                str(output),
            ],
            cwd=ROOT / "frontend",
            check=True,
        )


def check_drift(expected: Path) -> bool:
    with tempfile.TemporaryDirectory(prefix="event-api-drift-") as directory:
        actual = Path(directory) / "schema.d.ts"
        generate_types(actual)
        return expected.is_file() and expected.read_bytes() == actual.read_bytes()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument(
        "--expected", type=Path, default=ROOT / "frontend/src/api/schema.d.ts"
    )
    args = parser.parse_args()
    if args.write:
        generate_types(args.expected)
    elif not check_drift(args.expected):
        print("OpenAPI drift detected. Run make api-generate.", file=sys.stderr)
        raise SystemExit(1)
    else:
        print("OpenAPI drift: none.")
