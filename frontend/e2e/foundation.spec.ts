import { expect, test } from '@playwright/test';
for (const path of ['/', '/login', '/register']) {
  test(`direct navigation and reload at ${path}`, async ({ page }) => {
    await page.goto(path);
    await expect(page.getByRole('heading', { name: 'Event Registration' })).toBeVisible();
    await expect(page.getByText('Auth is not implemented yet.')).toBeVisible();
    await page.reload();
    await expect(page.getByRole('heading', { name: 'Event Registration' })).toBeVisible();
  });
}
test('API health and readiness share browser origin', async ({ request }) => {
  const health = await request.get('/api/health');
  expect(health.status()).toBe(200);
  expect(await health.json()).toEqual({ status: 'ok' });
  const ready = await request.get('/api/ready');
  expect(ready.status()).toBe(200);
  expect(await ready.json()).toEqual({ status: 'ready' });
});
