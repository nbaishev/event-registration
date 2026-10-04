import { expect, test } from '@playwright/test';
for (const path of ['/', '/login']) {
  test(`direct navigation and reload at ${path}`, async ({ page }) => {
    await page.goto(path);
    await expect(page.getByRole('heading', { name: 'Войти' })).toBeVisible();
    await expect(page).toHaveURL(/\/login$/);
    await page.reload();
    await expect(page.getByRole('heading', { name: 'Войти' })).toBeVisible();
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
