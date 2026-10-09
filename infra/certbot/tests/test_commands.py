"""Exercise the real renewal wrapper and Make recipes against a fake Docker CLI."""
import os
import fcntl
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


class ProductionCommands(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.calls = self.directory / 'calls'
        docker = self.directory / 'docker'
        docker.write_text('''#!/bin/sh
printf '%s\\n' "$*" >> "$CALLS"
case "$*" in
  *"$FAIL_STEP"*) if [ -n "$FAIL_STEP" ]; then exit 17; fi ;;
esac
''')
        docker.chmod(0o755)
        self.env = dict(os.environ, PATH=f'{self.directory}:{os.environ["PATH"]}',
                        CALLS=str(self.calls), FAIL_STEP='')

    def run_command(self, *args, fail=''):
        self.env['FAIL_STEP'] = fail
        return subprocess.run(args, cwd=ROOT, env=self.env, capture_output=True)

    def records(self):
        return self.calls.read_text().splitlines() if self.calls.exists() else []

    def test_renew_checks_before_reload(self):
        result = self.run_command('sh', 'infra/certbot/renew.sh')
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.records()
        self.assertEqual(len(calls), 3)
        self.assertIn('run --rm --no-deps certbot renew --non-interactive', calls[0])
        self.assertTrue(calls[1].endswith('exec -T nginx nginx -t'))
        self.assertTrue(calls[2].endswith('exec -T nginx nginx -s reload'))

    def test_renew_failure_does_not_reload(self):
        for step, count in [('certbot renew', 1), ('nginx -t', 2), ('nginx -s reload', 3)]:
            with self.subTest(step=step):
                self.calls.unlink(missing_ok=True)
                result = self.run_command('sh', 'infra/certbot/renew.sh', fail=step)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(len(self.records()), count)

    def test_dry_run_and_invalid_arguments(self):
        result = self.run_command('sh', 'infra/certbot/renew.sh', '--dry-run')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--dry-run', self.records()[0])
        self.calls.unlink()
        result = self.run_command('sh', 'infra/certbot/renew.sh', '--other')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.records(), [])

    def test_parallel_renew_is_rejected(self):
        with (ROOT / 'infra/certbot/.renew.lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self.run_command('sh', 'infra/certbot/renew.sh')
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(self.records(), [])

    def test_up_validation_failure_prevents_start(self):
        result = self.run_command('make', 'prod-up', fail='config --quiet')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(self.records()), 1)

    def test_up_and_down_use_production_and_preserve_volumes(self):
        for target in ['prod-up', 'prod-down']:
            result = self.run_command('make', target)
            self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.records()
        self.assertTrue(all('--env-file .env.prod -f compose.prod.yaml' in c for c in calls))
        self.assertIn('up -d --build --wait --wait-timeout 180', calls[1])
        self.assertTrue(calls[2].endswith('down'))

    def test_make_reload_stops_on_invalid_config(self):
        result = self.run_command('make', 'prod-nginx-reload', fail='nginx -t')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(self.records()), 1)

    def test_certificate_targets_use_bootstrap_and_container_variables(self):
        for target in ['prod-cert-check', 'prod-cert-issue']:
            result = self.run_command('make', target)
            self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.records()
        self.assertEqual(len(calls), 2)
        for call in calls:
            self.assertIn('-f compose.certbot-bootstrap.yaml', call)
            self.assertIn('--entrypoint /bin/sh certbot -ec', call)
            self.assertIn('"$APP_DOMAIN"', call)
            self.assertIn('"$CERTBOT_EMAIL"', call)
        self.assertIn('--dry-run', calls[0])
        self.assertNotIn('--dry-run', calls[1])


if __name__ == '__main__':
    unittest.main()
