"""Run isolated integration, build and browser verification; always clean up."""

import os
import secrets
import shlex
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(
    command: list[str], *, cwd: Path = ROOT, env: dict[str, str] | None = None
) -> None:
    print("Running:", shlex.join(command), flush=True)
    subprocess.run(command, cwd=cwd, env=env, check=True)


def verify(mode: str) -> None:
    environment = os.environ.copy()
    environment.update(
        JWT_SECRET=secrets.token_hex(32),
        APP_PORT="0",
        POSTGRES_DB="foundation_verification",
        POSTGRES_USER="event_registration",
        POSTGRES_PASSWORD="development",
        ENVIRONMENT="test",
        APP_ORIGIN="http://localhost:8080",
    )
    project = "foundation-verify-" + uuid.uuid4().hex[:12]
    compose = [
        "docker",
        "compose",
        "--project-name",
        project,
        "--env-file",
        str(ROOT / ".env.example"),
        "-f",
        str(ROOT / "compose.yaml"),
        "-f",
        str(ROOT / "compose.test.yaml"),
    ]
    uv = ["uv", "run", "--frozen", "--project", str(ROOT / "backend")]
    pnpm = shlex.split(os.environ.get("PNPM", "corepack pnpm"))
    try:
        run([*compose, "config", "--quiet"], env=environment)
        run(
            [*compose, "up", "-d", "--wait", "--wait-timeout", "90", "postgres"],
            env=environment,
        )
        address = subprocess.check_output(
            [*compose, "port", "postgres", "5432"], cwd=ROOT, env=environment, text=True
        ).strip()
        test_env = environment | {
            "TEST_DATABASE_URL": f"postgresql+psycopg://event_registration:development@{address}/foundation_verification"
        }
        if mode == "test":
            run([*uv, "pytest", "backend/tests", "-q"], env=test_env)
            run([*pnpm, "test"], cwd=ROOT / "frontend", env=environment)
        elif mode == "verify":
            run([*uv, "pytest", "backend/tests/integration", "-q"], env=test_env)
        if mode in {"e2e", "verify"}:
            if mode == "verify":
                run([*uv, "python", "scripts/verify_migrations.py"], env=test_env)
                run([*pnpm, "build"], cwd=ROOT / "frontend", env=environment)
            run([*compose, "build", "backend", "frontend"], env=environment)
            run(
                [*compose, "up", "-d", "--wait", "--wait-timeout", "120"],
                env=environment,
            )
            address = subprocess.check_output(
                [*compose, "port", "nginx", "80"], cwd=ROOT, env=environment, text=True
            ).strip()
            # Pin the allocated proxy port before recreating services: restarting
            # an ephemeral mapping can assign another port on Docker Desktop.
            environment["APP_PORT"] = address.rsplit(":", 1)[1]
            environment["APP_ORIGIN"] = f"http://{address}"
            run(
                [*compose, "up", "-d", "--wait", "--wait-timeout", "120", "nginx"],
                env=environment,
            )
            run([*compose, "exec", "-T", "nginx", "nginx", "-t"], env=environment)
            nginx_id = subprocess.check_output(
                [*compose, "ps", "-q", "nginx"], cwd=ROOT, env=environment, text=True
            ).strip()
            browser_env = environment | {
                "E2E_BASE_URL": f"http://{address}",
                "E2E_NGINX_CONTAINER": nginx_id,
            }
            # Keep the CI auth order; the automatic fixture resets the isolated
            # Nginx before every test, including consecutive tests in one file.
            event_groups = (
                "login limiter|event-drafts|event-publish|"
                "event-registration|my-registrations|check-in|organizer-stats|stats-stream|live-dashboard"
            )
            run(
                [*pnpm, "e2e", "--grep-invert", event_groups],
                cwd=ROOT / "frontend",
                env=browser_env,
            )
            run(
                [*pnpm, "e2e", "--grep", event_groups],
                cwd=ROOT / "frontend",
                env=browser_env,
            )
        print(f"{mode}: passed (isolated project {project}).")
    finally:
        # Only this invocation's unique project/volumes may be removed.
        run([*compose, "down", "--volumes", "--remove-orphans"], env=environment)


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode not in {"test", "e2e", "verify"}:
        raise SystemExit("Expected test, e2e or verify")
    verify(mode)
