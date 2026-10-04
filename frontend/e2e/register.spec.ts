import { randomUUID } from 'node:crypto';
import { expect, test } from '@playwright/test';

test('register through Nginx redirects to login without storing password', async ({ page }) => {
  const email = `register-${randomUUID()}@example.com`;
  const password = 'register password!';
  await page.goto('/register');
  await page.reload();
  await page.screenshot({ path: '../.verification/register-page.png', fullPage: true });
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Пароль').fill(password);
  await page.getByRole('button', { name: 'Создать аккаунт' }).click();
  await expect(page).toHaveURL(/\/login$/);
  const state = await page.evaluate(() => JSON.stringify({ history: history.state, local: { ...localStorage }, session: { ...sessionStorage } }));
  expect(state).not.toContain(password);
});

test('duplicate normalized email shows a registration error', async ({ page }) => {
  const email = `duplicate-${randomUUID()}@example.com`;
  await page.goto('/register');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Пароль').fill('register password!');
  await page.getByRole('button', { name: 'Создать аккаунт' }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.goto('/register');
  await page.getByLabel('Email').fill(` ${email.toUpperCase()} `);
  await page.getByLabel('Пароль').fill('register password!');
  await page.getByRole('button', { name: 'Создать аккаунт' }).click();
  await expect(page.getByRole('alert')).toContainText('Этот email уже зарегистрирован');
  await expect(page).toHaveURL(/\/register$/);
});

test('missing CSRF is rejected before malformed body through Nginx', async ({ request, baseURL }) => {
  const response = await request.post('/api/auth/register', { data: '{', headers: { Origin: baseURL! } });
  expect(response.status()).toBe(403);
  expect((await response.json()).error.code).toBe('CSRF_INVALID');
  expect(response.headers()['cache-control']).toBe('no-store');
});
