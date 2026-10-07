import { randomUUID } from 'node:crypto';
import { expect, test, type Page } from './fixtures';

async function registerAndLogin(page: Page) {
  const email = `registration-${randomUUID()}@example.com`;
  await page.goto('/register');
  await expect(page.getByRole('heading', { name: 'Создать аккаунт' })).toBeVisible();
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Пароль').fill('a long password');
  await page.getByRole('button', { name: 'Создать аккаунт' }).click();
  await expect(page.getByRole('heading', { name: 'Войти' })).toBeVisible();
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Пароль').fill('a long password');
  await page.getByRole('button', { name: 'Войти' }).click();
  await expect(page.getByText(email)).toBeVisible();
}

test('event-registration: last seat, waitlist and saved participant states after reload', async ({ page, browser, baseURL }) => {
  await registerAndLogin(page);
  await page.getByRole('link', { name: 'Мои мероприятия' }).click();
  await page.getByRole('link', { name: 'Создать мероприятие' }).click();
  await page.getByLabel('Название').fill('Registration capacity one');
  await page.getByLabel('Описание').fill('Public registration description');
  await page.getByLabel('Часовой пояс IANA').fill('UTC');
  const date = new Date(Date.now() + 2 * 86400000).toISOString().slice(0, 10);
  await page.getByLabel(/^Начало/).fill(`${date}T18:30`);
  await page.getByLabel(/^Окончание/).fill(`${date}T20:30`);
  await page.getByLabel('Количество мест').fill('1');
  const created = page.waitForResponse(r => r.request().method() === 'POST' && r.url().endsWith('/api/events'));
  await page.getByRole('button', { name: 'Создать черновик' }).click();
  const event = await (await created).json() as { id: string; slug: string };
  await page.getByRole('button', { name: 'Опубликовать' }).click();
  await expect(page.getByRole('link', { name: 'Открыть публичную страницу' })).toBeVisible();
  const a = await browser.newContext({ baseURL });
  const b = await browser.newContext({ baseURL });
  try {
    const first = await a.newPage(), second = await b.newPage();
    await registerAndLogin(first);
    await registerAndLogin(second);
    for (const participant of [first, second]) {
      await participant.goto(`/events/${event.slug}`);
      await expect(participant.getByRole('heading', { name: 'Registration capacity one' })).toBeVisible();
      await expect(participant.getByRole('button', { name: 'Зарегистрироваться' })).toBeVisible();
    }
    await first.getByRole('button', { name: 'Зарегистрироваться' }).click();
    await expect(first.getByText('Регистрация подтверждена')).toBeVisible();
    const ticket = await first.getByText(/^[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{4}-[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{4}-[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{4}$/).textContent();
    await second.getByRole('button', { name: 'Зарегистрироваться' }).click();
    await expect(second.getByText('Место в очереди: 1')).toBeVisible();
    await first.reload();
    await second.reload();
    await expect(first.getByText(ticket!)).toBeVisible();
    await expect(second.getByText('Место в очереди: 1')).toBeVisible();
    await expect(second.getByText(ticket!)).toHaveCount(0);
    await first.screenshot({ path: '../.verification/registration-confirmed.png', fullPage: true });
    await second.screenshot({ path: '../.verification/registration-waitlist.png', fullPage: true });
    await page.getByRole('spinbutton', { name: 'Количество мест' }).fill('2');
    await page.getByRole('button', { name: 'Сохранить количество мест' }).click();
    await expect(page.getByText('Количество мест: 2')).toBeVisible();
    await page.reload();
    await expect(page.getByRole('spinbutton', { name: 'Количество мест' })).toHaveValue('2');
    await second.reload();
    await expect(second.getByText('Регистрация подтверждена')).toBeVisible();
    await expect(second.getByText('Количество мест: 2')).toBeVisible();
    await expect(second.getByText(/^[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{4}-[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{4}-[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{4}$/)).toBeVisible();
    await page.screenshot({ path: '../.verification/event-capacity-increased.png', fullPage: true });
    await second.screenshot({ path: '../.verification/event-capacity-promoted.png', fullPage: true });
    await page.getByRole('spinbutton', { name: 'Количество мест' }).fill('1');
    await page.getByRole('button', { name: 'Сохранить количество мест' }).click();
    await expect(page.getByRole('alert')).toContainText('подтверждённых участников');
    await page.screenshot({ path: '../.verification/event-capacity-rejected.png', fullPage: true });
    await page.reload();
    await expect(page.getByText('Количество мест: 2')).toBeVisible();
    await expect(page.getByRole('spinbutton', { name: 'Количество мест' })).toHaveValue('2');
    await first.getByRole('button', { name: 'Отменить регистрацию' }).click();
    await expect(first.getByText('Регистрация отменена')).toBeVisible();
    await page.getByRole('spinbutton', { name: 'Количество мест' }).fill('1');
    await page.getByRole('button', { name: 'Сохранить количество мест' }).click();
    await expect(page.getByText('Количество мест: 1')).toBeVisible();
    await second.reload();
    await expect(second.getByText('Регистрация подтверждена')).toBeVisible();
    await first.getByRole('button', { name: 'Зарегистрироваться' }).click();
    await expect(first.getByText('Место в очереди: 1')).toBeVisible();
    await second.getByRole('button', { name: 'Отменить регистрацию' }).click();
    await expect(second.getByText('Регистрация отменена')).toBeVisible();
    await first.reload();
    await expect(first.getByText('Регистрация подтверждена')).toBeVisible();
    const newTicket = await first.getByText(/^[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{4}-[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{4}-[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{4}$/).textContent();
    expect(newTicket).not.toBe(ticket);
    await first.screenshot({ path: '../.verification/registration-promoted.png', fullPage: true });
    await second.screenshot({ path: '../.verification/registration-cancelled.png', fullPage: true });
    // Failed refresh must leave this public route visible and remove private ticket data.
    for (const cookie of await a.cookies()) if (['access_token', 'refresh_token'].includes(cookie.name)) await a.addCookies([{ ...cookie, value: 'invalid-test-token' }]);
    const failed = first.waitForResponse(r => r.url().endsWith('/api/auth/refresh'));
    await first.evaluate(() => window.dispatchEvent(new Event('visibilitychange')));
    expect((await failed).status()).toBe(401);
    await expect(first.getByRole('link', { name: 'Войти для регистрации' })).toBeVisible();
    await expect(first.getByRole('heading', { name: 'Registration capacity one' })).toBeVisible();
    await expect(first.getByText(newTicket!)).toHaveCount(0);
    await expect(first).toHaveURL(new RegExp(`/events/${event.slug}$`));
  } finally { await a.close(); await b.close(); }
});
