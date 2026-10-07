import { randomUUID } from 'node:crypto';
import { expect, test, type Page } from './fixtures';

async function registerAndLogin(page: Page, prefix: string) {
  const email = `${prefix}-${randomUUID()}@example.com`;
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
async function counts(page: Page, capacity: number, confirmed: number, waitlist: number, checkedIn: number, available: number) {
  for (const [label, value] of [['Вместимость', capacity], ['Подтверждено', confirmed], ['В листе ожидания', waitlist], ['Отмечено на входе', checkedIn], ['Свободных мест', available]] as const) {
    await expect(page.getByRole('group', { name: label }).getByText(String(value), { exact: true })).toBeVisible();
  }
}

test('organizer-stats: refresh registration, cancellation/promotion, capacity and check-in snapshots', async ({ page, browser, baseURL }) => {
  await registerAndLogin(page, 'stats-owner');
  const token = await (await page.request.get('/api/auth/csrf')).json() as { csrf_token: string };
  const headers = { Origin: new URL(baseURL!).origin, 'X-CSRF-Token': token.csrf_token };
  const created = await page.request.post('/api/events', { headers, data: {
    title: 'Статистика встречи', description: 'Регистрация участников и отметки на входе', timezone: 'UTC', capacity: 1,
    starts_at: new Date(Date.now() + 3600000).toISOString(), ends_at: new Date(Date.now() + 7200000).toISOString(),
  } });
  expect(created.status()).toBe(201);
  const event = await created.json() as { id: string; slug: string };
  await page.goto(`/organizer/events/${event.id}`);
  await expect(page.getByRole('button', { name: 'Опубликовать' })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Статистика мероприятия' })).toHaveCount(0);
  await page.getByRole('button', { name: 'Опубликовать' }).click();
  await counts(page, 1, 0, 0, 0, 1);
  const a = await browser.newContext({ baseURL });
  const b = await browser.newContext({ baseURL });
  try {
    const first = await a.newPage(), second = await b.newPage();
    await registerAndLogin(first, 'stats-first');
    await registerAndLogin(second, 'stats-second');
    await first.goto(`/events/${event.slug}`);
    await first.getByRole('button', { name: 'Зарегистрироваться' }).click();
    await expect(first.getByText('Регистрация подтверждена')).toBeVisible();
    await second.goto(`/events/${event.slug}`);
    await second.getByRole('button', { name: 'Зарегистрироваться' }).click();
    await expect(second.getByText('Место в очереди: 1')).toBeVisible();
    await counts(page, 1, 0, 0, 0, 1);
    await page.getByRole('button', { name: 'Обновить статистику' }).click();
    await counts(page, 1, 1, 1, 0, 0);
    await first.getByRole('button', { name: 'Отменить регистрацию' }).click();
    await expect(first.getByText('Регистрация отменена')).toBeVisible();
    await page.getByRole('button', { name: 'Обновить статистику' }).click();
    await counts(page, 1, 1, 0, 0, 0);
    await second.reload();
    await expect(second.getByText('Регистрация подтверждена')).toBeVisible();
    const ticket = await second.getByText(/^[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{4}-[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{4}-[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{4}$/).textContent();
    await page.getByRole('spinbutton', { name: 'Количество мест' }).fill('3');
    await page.getByRole('button', { name: 'Сохранить количество мест' }).click();
    await expect(page.getByText('Количество мест: 3')).toBeVisible();
    await page.getByRole('button', { name: 'Обновить статистику' }).click();
    await counts(page, 3, 1, 0, 0, 2);
    const checkin = await page.context().newPage();
    try {
      await checkin.goto(`/organizer/events/${event.id}/check-in`);
      await checkin.getByLabel(/^Код билета/).fill(ticket!);
      await checkin.getByRole('button', { name: 'Отметить участника' }).click();
      await expect(checkin.getByText('Участник отмечен', { exact: true })).toBeVisible();
      await page.getByRole('button', { name: 'Обновить статистику' }).click();
      await counts(page, 3, 1, 0, 1, 2);
      await page.reload();
      await counts(page, 3, 1, 0, 1, 2);
      await page.screenshot({ path: '../.verification/organizer-stats-desktop.png', fullPage: true });
      await page.setViewportSize({ width: 390, height: 844 });
      await counts(page, 3, 1, 0, 1, 2);
      await page.screenshot({ path: '../.verification/organizer-stats-mobile.png', fullPage: true });
    } finally { await checkin.close(); }
  } finally { await a.close(); await b.close(); }
});
