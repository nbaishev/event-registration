import os
import re
import secrets
from pathlib import Path

from dotenv import dotenv_values


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
    # Match BaseSettings dotenv semantics: export, comments, quotes and interpolation.
    values = {key.upper(): value for key, value in dotenv_values(path).items()}
    process_values = {key.upper(): value for key, value in os.environ.items()}
    if values.get("JWT_SECRET"):
        return
    environment = process_values.get(
        "ENVIRONMENT", values.get("ENVIRONMENT") or "development"
    )
    if environment == "production":
        if not process_values.get("JWT_SECRET"):
            raise ValueError("Production requires an explicit JWT_SECRET")
        return
    entry = "JWT_SECRET=" + secrets.token_hex(32)
    contents, replacements = re.subn(
        r"^[ \t]*(?:export[ \t]+)?JWT_SECRET[ \t]*(?:=[^\n]*|(?:#[^\n]*)?)$",
        lambda _: entry,
        contents,
        flags=re.MULTILINE | re.IGNORECASE,
    )
    if not replacements:
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
