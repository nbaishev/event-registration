import { createHmac, randomUUID } from 'node:crypto';
import { expect, test, type BrowserContext, type Page } from '@playwright/test';

// Signing stays in the Node test runner. The isolated verification stack supplies
// its ephemeral secret; it is never sent to page JavaScript or included in output.
function expiredToken(userId: string, kind: 'access' | 'refresh') {
  const secret = process.env.JWT_SECRET;
  if (!secret) throw new Error('Run refresh E2E with the isolated verification stack');
  const ttl = kind === 'access' ? 900 : 2592000;
  const issued = Math.floor(Date.now() / 1000) - ttl - 3600;
  const encode = (value: unknown) => Buffer.from(JSON.stringify(value)).toString('base64url');
  const data = `${encode({ alg: 'HS256', typ: 'JWT' })}.${encode({ sub: userId, iat: issued, exp: issued + ttl, iss: 'event-registration', aud: 'event-registration-api', token_type: kind })}`;
  return `${data}.${createHmac('sha256', secret).update(data).digest('base64url')}`;
}
async function expireCookie(context: BrowserContext, userId: string, kind: 'access' | 'refresh') {
  const original = (await context.cookies()).find(cookie => cookie.name === `${kind}_token`);
  if (!original) throw new Error('Expected auth cookie missing');
  // Keep browser expiry in the future so the server actually validates JWT exp.
  await context.addCookies([{ ...original, value: expiredToken(userId, kind), expires: Math.floor(Date.now() / 1000) + 600 }]);
}
async function registerAndLogin(page: Page) {
  const email = `refresh-${randomUUID()}@example.com`;
  const password = 'a long test password';
  await page.goto('/register');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Пароль').fill(password);
  await page.getByRole('button', { name: 'Создать аккаунт' }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Пароль').fill(password);
  const loggedIn = page.waitForResponse(response => response.url().endsWith('/api/auth/login'));
  await page.getByRole('button', { name: 'Войти' }).click();
  const response = await loggedIn;
  expect(response.status()).toBe(200);
  const user = await response.json() as { id: string };
  await expect(page.getByText(email)).toBeVisible();
  return { email, id: user.id };
}
async function expectAuthCookiesCleared(context: BrowserContext) {
  const names = (await context.cookies()).map(cookie => cookie.name);
  expect(names).not.toContain('access_token');
  expect(names).not.toContain('refresh_token');
}

test('Day 1 register → login → me → expired-access refresh → logout', async ({ page }) => {
  const user = await registerAndLogin(page);
  const originalRefresh = (await page.context().cookies()).find(cookie => cookie.name === 'refresh_token')!;
  expect((await page.request.get('/api/auth/me')).status()).toBe(200);
  await expireCookie(page.context(), user.id, 'access');
  const refreshed = page.waitForResponse(response => response.url().endsWith('/api/auth/refresh'));
  await page.reload();
  expect((await refreshed).status()).toBe(200);
  await expect(page.getByText(user.email)).toBeVisible();
  const afterRefresh = (await page.context().cookies()).find(cookie => cookie.name === 'refresh_token')!;
  expect(afterRefresh.value === originalRefresh.value).toBe(true);
  expect(afterRefresh.expires).toBe(originalRefresh.expires);
  expect((await page.request.get('/api/auth/me')).status()).toBe(200);
  await page.getByRole('button', { name: 'Выйти' }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expectAuthCookiesCleared(page.context());
});
test('expired refresh clears auth cookies and returns to login without a recovery loop', async ({ page }) => {
  const user = await registerAndLogin(page);
  await expireCookie(page.context(), user.id, 'access');
  await expireCookie(page.context(), user.id, 'refresh');
  let refreshes = 0;
  page.on('request', request => { if (request.url().endsWith('/api/auth/refresh')) refreshes++; });
  const refreshed = page.waitForResponse(response => response.url().endsWith('/api/auth/refresh'));
  await page.reload();
  expect((await refreshed).status()).toBe(401);
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole('heading', { name: 'Войти' })).toBeVisible();
  await expectAuthCookiesCleared(page.context());
  expect(refreshes).toBe(1);
  await expect(page.getByText(user.email)).not.toBeVisible();
});
test('logout waits for an in-flight refresh and clears its new access cookie', async ({ page }) => {
  const user = await registerAndLogin(page);
  await expireCookie(page.context(), user.id, 'access');
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  let started!: () => void;
  const refreshing = new Promise<void>(resolve => { started = resolve; });
  let logoutRequests = 0;
  page.on('request', request => { if (request.url().endsWith('/api/auth/logout')) logoutRequests++; });
  await page.route('**/api/auth/refresh', async route => {
    started();
    await held;
    const response = await route.fetch();
    await route.fulfill({ response });
  });
  // TanStack Query refetches the stale session on visibilitychange; its cached
  // user keeps the logout action available while recovery is in flight.
  await page.evaluate(() => window.dispatchEvent(new Event('visibilitychange')));
  await refreshing;
  await page.getByRole('button', { name: 'Выйти' }).click();
  await expect(page.getByRole('button', { name: 'Выходим…' })).toBeDisabled();
  expect(logoutRequests).toBe(0);
  release();
  await expect(page).toHaveURL(/\/login$/);
  await expectAuthCookiesCleared(page.context());
  expect(logoutRequests).toBe(1);
  await expect(page.getByText(user.email)).not.toBeVisible();
  expect((await page.request.get('/api/auth/me')).status()).toBe(401);
});
