import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { test as base, expect } from '@playwright/test';

const exec = promisify(execFile);
export { expect, type Page, type BrowserContext } from '@playwright/test';

export const test = base.extend<{ resetLoginLimiter: void }, { isolatedNginx: string }>({
  // eslint-disable-next-line no-empty-pattern -- Playwright requires destructured fixture dependencies.
  isolatedNginx: [async ({}, use, worker) => {
    const container = process.env.E2E_NGINX_CONTAINER;
    if (process.env.ENVIRONMENT !== 'test' || !container || !/^[a-f0-9]{64}$/.test(container) || worker.config.workers !== 1) {
      throw new Error('E2E limiter isolation requires the isolated test stack (make e2e), an explicit Nginx container ID and one worker.');
    }
    const { stdout } = await exec('docker', ['inspect', '--format', '{{json .Config.Labels}}', container]);
    const labels = JSON.parse(stdout) as Record<string, string>;
    if (!/^foundation-verify-[a-f0-9]{12}$/.test(labels['com.docker.compose.project'] ?? '') || labels['com.docker.compose.service'] !== 'nginx' || !labels['com.docker.compose.project.config_files']?.split(',').some(path => path.endsWith('/compose.test.yaml'))) {
      throw new Error('Refusing to reset a container outside an isolated verification Nginx stack.');
    }
    await use(container);
  }, { scope: 'worker' }],
  resetLoginLimiter: [async ({ isolatedNginx, request }, use) => {
    // Restart, rather than reload: the shared limit_req zone survives a reload.
    // Production rate/burst stay intact; only this test project's process resets.
    await exec('docker', ['restart', isolatedNginx]);
    await expect.poll(async () => {
      try { return (await request.get('/api/ready')).status(); }
      catch { return 0; }
    }, { message: 'Isolated Nginx must be ready after restart', timeout: 5000 }).toBe(200);
    await use();
  }, { auto: true }],
});
