import os
import re
import secrets
from pathlib import Path


def ensure_env(root: Path) -> None:
    path = root / ".env"
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(descriptor, "w") as output:
            output.write((root / ".env.example").read_text())
    contents = path.read_text()
    values = {}
    for line in contents.splitlines():
        key, separator, value = line.partition("=")
        if separator and not key.lstrip().startswith("#"):
            values[key.strip()] = value.strip().strip("\"'")
    if values.get("JWT_SECRET"):
        return
    environment = os.environ.get(
        "ENVIRONMENT", values.get("ENVIRONMENT", "development")
    )
    if environment == "production":
        if not os.environ.get("JWT_SECRET"):
            raise ValueError("Production requires an explicit JWT_SECRET")
        return
    entry = "JWT_SECRET=" + secrets.token_hex(32)
    if "JWT_SECRET" in values:
        contents = re.sub(
            r"^\s*JWT_SECRET\s*=.*$", lambda _: entry, contents, flags=re.MULTILINE
        )
    else:
        contents = contents.rstrip("\n") + "\n" + entry + "\n"
    descriptor = os.open(path, os.O_WRONLY | os.O_TRUNC, 0o600)
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, "w") as output:
        output.write(contents)


if __name__ == "__main__":
    ensure_env(Path(__file__).resolve().parents[1])
    print(
        "Local configuration present; existing values preserved. JWT secret is never printed."
    )
