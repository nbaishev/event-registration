import os
from pathlib import Path


def ensure_env(root: Path) -> None:
    try:
        descriptor = os.open(root / ".env", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return
    with os.fdopen(descriptor, "w") as output:
        output.write((root / ".env.example").read_text())


if __name__ == "__main__":
    ensure_env(Path(__file__).resolve().parents[1])
    print("Local configuration present (existing .env preserved).")
