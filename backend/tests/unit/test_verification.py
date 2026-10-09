import subprocess

import pytest
from scripts import verification


@pytest.fixture
def commands(monkeypatch):
    monkeypatch.setenv("PNPM", "pnpm")
    calls = []

    def record(command, **kwargs):
        calls.append((command, kwargs | {"env": kwargs["env"].copy()}))

    monkeypatch.setattr(verification.subprocess, "run", record)

    def output(command, **kwargs):
        if command[-3:] == ["port", "postgres", "5432"]:
            return "127.0.0.1:15432\n"
        if command[-3:] == ["port", "nginx", "80"]:
            return "127.0.0.1:18080\n"
        if command[-3:] == ["port", "redis", "6379"]:
            return "127.0.0.1:16379\n"
        if command[-3:] == ["port", "mailpit", "8025"]:
            return "127.0.0.1:18025\n"
        if command[-3:] == ["ps", "-q", "nginx"]:
            return "nginx-id\n"
        raise AssertionError(f"Unexpected subprocess output: {command}")

    monkeypatch.setattr(verification.subprocess, "check_output", output)
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
    smoke = [
        i
        for i, c in enumerate(command_lists)
        if c[-1] == "scripts/verify_notifications.py"
    ]
    assert len(smoke) == 1
    smoke_env = commands[smoke[0]][1]["env"]
    assert smoke_env["REDIS_URL"] == "redis://127.0.0.1:16379/0"
    assert smoke_env["MAILPIT_URL"] == "http://127.0.0.1:18025"
    assert smoke_env["APP_ORIGIN"] == "http://127.0.0.1:18080"
    assert integration < migration < frontend_build < docker_build < smoke[0]
    assert smoke[0] < next(i for i, c in enumerate(command_lists) if "e2e" in c)
    assert any(c[-5:] == ["exec", "-T", "nginx", "nginx", "-t"] for c in command_lists)
    assert command_lists[-3:] == [
        [
            "pnpm",
            "e2e",
            "--grep-invert",
            (
                "login limiter|event-drafts|event-publish|"
                "event-registration|event-reschedule|event-cancellation|my-registrations|check-in|organizer-stats|stats-stream|live-dashboard"
            ),
        ],
        [
            "pnpm",
            "e2e",
            "--grep",
            (
                "login limiter|event-drafts|event-publish|"
                "event-registration|event-reschedule|event-cancellation|my-registrations|check-in|organizer-stats|stats-stream|live-dashboard"
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


@pytest.mark.parametrize("failure_index", range(13))
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


def test_final_origin_reaches_worker_and_beat_before_smoke(commands):
    verification.verify("verify")
    final_start = next(
        (command, kwargs)
        for command, kwargs in commands
        if "up" in command
        and kwargs["env"]["APP_ORIGIN"] == "http://127.0.0.1:18080"
        and command[-1] != "postgres"
    )
    assert set(final_start[0][-3:]) == {"nginx", "worker", "beat"}


def test_verify_ci_runs_all_non_browser_gates(commands):
    verification.verify("verify-ci")
    command_lists = [command for command, _ in commands]
    assert python_suites(commands) == [["pytest", "backend/tests/integration", "-q"]]
    assert ["pnpm", "build"] in command_lists
    assert any(c[-1] == "scripts/verify_migrations.py" for c in command_lists)
    assert any(c[-3:] == ["build", "backend", "frontend"] for c in command_lists)
    assert any(c[-5:] == ["exec", "-T", "nginx", "nginx", "-t"] for c in command_lists)
    assert sum(c[-1] == "scripts/verify_notifications.py" for c in command_lists) == 1
    assert not any("e2e" in c for c in command_lists)
    assert command_lists[-1][-3:] == ["down", "--volumes", "--remove-orphans"]


def test_verify_ci_smoke_failure_fails_and_cleans_up(commands, monkeypatch):
    error = subprocess.CalledProcessError(19, ["smtp-smoke"])
    original = verification.run

    def fail_smoke(command, **kwargs):
        if command[-1] == "scripts/verify_notifications.py":
            raise error
        original(command, **kwargs)

    monkeypatch.setattr(verification, "run", fail_smoke)
    with pytest.raises(subprocess.CalledProcessError) as caught:
        verification.verify("verify-ci")
    assert caught.value is error
    assert commands[-1][0][-3:] == ["down", "--volumes", "--remove-orphans"]


def test_reschedule_browser_runs_once_and_receives_smtp_sink(commands):
    verification.verify("verify")
    browser_calls = [(c, kw) for c, kw in commands if "e2e" in c]
    assert len(browser_calls) == 2
    assert "event-reschedule" in browser_calls[1][0][-1]
    assert browser_calls[1][1]["env"]["MAILPIT_URL"] == "http://127.0.0.1:18025"
