import { randomUUID } from 'node:crypto';
import { expect, test, type Page } from './fixtures';

async function registerAndLogin(page: Page, email: string) {
  await page.goto('/register');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Пароль').fill('a long password');
  await page.getByRole('button', { name: 'Создать аккаунт' }).click();
  await expect(page.getByRole('heading', { name: 'Войти' })).toBeVisible();
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Пароль').fill('a long password');
  await page.getByRole('button', { name: 'Войти' }).click();
  await expect(page.getByText(email)).toBeVisible();
}

test('check-in: owner marks participant once and sees duplicate error', async ({ page, browser, baseURL }) => {
  await registerAndLogin(page, `checkin-owner-${randomUUID()}@example.com`);
  const token = await (await page.request.get('/api/auth/csrf')).json() as { csrf_token: string };
  const headers = { Origin: new URL(baseURL!).origin, 'X-CSRF-Token': token.csrf_token };
  const created = await page.request.post('/api/events', { headers, data: {
    title: 'Check-in meetup', description: 'Organizer check-in', timezone: 'UTC', capacity: 1,
    starts_at: new Date(Date.now() + 3600000).toISOString(), ends_at: new Date(Date.now() + 7200000).toISOString(),
  } });
  expect(created.status()).toBe(201);
  const event = await created.json() as { id: string; slug: string };
  expect((await page.request.post(`/api/events/${event.id}/publish`, { headers })).status()).toBe(200);
  const context = await browser.newContext({ baseURL });
  try {
    const participant = await context.newPage();
    const email = `checkin-participant-${randomUUID()}@example.com`;
    await registerAndLogin(participant, email);
    await participant.goto(`/events/${event.slug}`);
    await participant.getByRole('button', { name: 'Зарегистрироваться' }).click();
    await expect(participant.getByText('Регистрация подтверждена')).toBeVisible();
    const ticket = await participant.getByText(/^[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{4}-[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{4}-[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{4}$/).textContent();
    await page.goto(`/organizer/events/${event.id}`);
    await page.getByRole('link', { name: 'Check-in' }).click();
    await page.getByLabel(/^Код билета/).fill(ticket!.toLowerCase());
    await page.getByRole('button', { name: 'Отметить участника' }).click();
    await expect(page.getByText('Участник отмечен', { exact: true })).toBeVisible();
    await expect(page.getByText(email)).toBeVisible();
    await expect(page.getByText(ticket!, { exact: true })).toBeVisible();
    await expect(page.getByText(/Время отметки:/)).toBeVisible();
    await page.screenshot({ path: '../.verification/check-in-success.png', fullPage: true });
    await page.getByRole('button', { name: 'Отметить участника' }).click();
    await expect(page.getByRole('alert')).toContainText('Участник уже отмечен');
    await expect(page.getByText(email)).toHaveCount(0);
    await page.screenshot({ path: '../.verification/check-in-duplicate.png', fullPage: true });
  } finally { await context.close(); }
});
