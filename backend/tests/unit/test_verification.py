import subprocess
from unittest.mock import Mock

import pytest
from scripts import verification


@pytest.fixture
def commands(monkeypatch):
    monkeypatch.setenv("PNPM", "pnpm")
    calls = []

    def record(command, **kwargs):
        calls.append((command, kwargs))

    monkeypatch.setattr(verification.subprocess, "run", record)
    monkeypatch.setattr(
        verification.subprocess,
        "check_output",
        Mock(side_effect=["127.0.0.1:15432\n", "127.0.0.1:18080\n", "nginx-id\n"]),
    )
    return calls


def python_suites(commands):
    return [command[-3:] for command, _ in commands if "pytest" in command]


def test_verify_runs_integration_without_unit_or_vitest(commands):
    verification.verify("verify")
    assert python_suites(commands) == [["pytest", "backend/tests/integration", "-q"]]
    assert ["pnpm", "test"] not in [command for command, _ in commands]
    command_lists = [command for command, _ in commands]
    migration = next(
        i
        for i, c in enumerate(command_lists)
        if c[-1] == "scripts/verify_migrations.py"
    )
    integration = next(i for i, c in enumerate(command_lists) if "pytest" in c)
    frontend_build = command_lists.index(["pnpm", "build"])
    docker_build = next(
        i
        for i, c in enumerate(command_lists)
        if c[-3:] == ["build", "backend", "frontend"]
    )
    assert integration < migration < frontend_build < docker_build
    assert any(c[-5:] == ["exec", "-T", "nginx", "nginx", "-t"] for c in command_lists)
    assert command_lists[-3:] == [
        [
            "pnpm",
            "e2e",
            "--grep-invert",
            (
                "login limiter|event-drafts|event-publish|"
                "event-registration|my-registrations"
            ),
        ],
        [
            "pnpm",
            "e2e",
            "--grep",
            (
                "login limiter|event-drafts|event-publish|"
                "event-registration|my-registrations"
            ),
        ],
        command_lists[0][:-2] + ["down", "--volumes", "--remove-orphans"],
    ]
    integration_env = commands[integration][1]["env"]
    assert integration_env["TEST_DATABASE_URL"].endswith(
        "@127.0.0.1:15432/foundation_verification"
    )
    assert command_lists[0][3].startswith("foundation-verify-")


def test_test_runs_full_suites(commands):
    verification.verify("test")
    assert python_suites(commands) == [["pytest", "backend/tests", "-q"]]
    assert [command for command, _ in commands if command[0] == "pnpm"] == [
        ["pnpm", "test"]
    ]
    assert commands[-1][0][-3:] == ["down", "--volumes", "--remove-orphans"]


def test_e2e_skips_python_suites(commands):
    verification.verify("e2e")
    assert python_suites(commands) == []
    assert [command[:3] for command, _ in commands if command[0] == "pnpm"] == [
        ["pnpm", "e2e", "--grep-invert"],
        ["pnpm", "e2e", "--grep"],
    ]
    assert commands[-1][0][-3:] == ["down", "--volumes", "--remove-orphans"]


@pytest.mark.parametrize("failure_index", range(12))
def test_failure_propagates_and_cleans_up(commands, monkeypatch, failure_index):
    error = subprocess.CalledProcessError(17, ["failing-command"])

    def fail(command, **kwargs):
        commands.append((command, kwargs))
        if len(commands) - 1 == failure_index:
            raise error

    monkeypatch.setattr(verification.subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError) as caught:
        verification.verify("verify")
    assert caught.value is error
    assert commands[-1][0][-3:] == ["down", "--volumes", "--remove-orphans"]
