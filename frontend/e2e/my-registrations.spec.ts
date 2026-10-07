import { randomUUID } from 'node:crypto';
import { expect, test, type Page } from '@playwright/test';

async function account(page: Page) {
  const email = `my-registrations-${randomUUID()}@example.com`;
  await page.goto('/register');
  await expect(page.getByRole('heading', { name: 'Создать аккаунт' })).toBeVisible();
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Пароль').fill('a long password');
  await page.getByRole('button', { name: 'Создать аккаунт' }).click();
  await expect(page.getByRole('heading', { name: 'Войти' })).toBeVisible();
  await login(page, email);
  return email;
}
async function login(page: Page, email: string) {
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Пароль').fill('a long password');
  await page.getByRole('button', { name: 'Войти' }).click();
  await expect(page.getByRole('heading', { name: 'Мой аккаунт' })).toBeVisible();
}

test('my-registrations: direct route, cancellation, promotion, reload and account isolation', async ({ page, browser, baseURL }) => {
  await account(page);
  await page.getByRole('link', { name: 'Мои мероприятия' }).click();
  await page.getByRole('link', { name: 'Создать мероприятие' }).click();
  await page.getByLabel('Название').fill('My registrations meetup');
  await page.getByLabel('Описание').fill('Participant list flow');
  await page.getByLabel('Часовой пояс IANA').fill('Asia/Almaty');
  const date = new Date(Date.now() + 2 * 86400000).toISOString().slice(0, 10);
  await page.getByLabel(/^Начало/).fill(`${date}T18:30`);
  await page.getByLabel(/^Окончание/).fill(`${date}T20:30`);
  await page.getByLabel('Количество мест').fill('1');
  const created = page.waitForResponse(r => r.request().method() === 'POST' && r.url().endsWith('/api/events'));
  await page.getByRole('button', { name: 'Создать черновик' }).click();
  const event = await (await created).json() as { slug: string };
  await page.getByRole('button', { name: 'Опубликовать' }).click();
  await expect(page.getByRole('link', { name: 'Открыть публичную страницу' })).toBeVisible();
  const a = await browser.newContext({ baseURL }), b = await browser.newContext({ baseURL });
  try {
    const first = await a.newPage(), second = await b.newPage();
    await account(first);
    const secondEmail = await account(second);
    for (const participant of [first, second]) {
      await participant.goto(`/events/${event.slug}`);
      await participant.getByRole('button', { name: 'Зарегистрироваться' }).click();
      await expect(participant.getByText(participant === first ? 'Регистрация подтверждена' : 'Вы в списке ожидания')).toBeVisible();
      await participant.goto('/me/registrations');
      await expect(participant.getByRole('heading', { name: 'Мои регистрации' })).toBeVisible();
      await participant.reload();
      await expect(participant.getByRole('link', { name: 'My registrations meetup' })).toBeVisible();
    }
    const ticketPattern = /^[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{4}-[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{4}-[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{4}$/;
    const oldTicket = await first.getByText(ticketPattern).textContent();
    await expect(second.getByText('Место в очереди: 1')).toBeVisible();
    await first.screenshot({ path: '../.verification/my-registrations.png', fullPage: true });
    await first.getByRole('button', { name: 'Отменить регистрацию' }).click();
    await expect(first.getByText('Регистрация отменена')).toBeVisible();
    await first.reload();
    await expect(first.getByText('Регистрация отменена')).toBeVisible();
    await expect(first.getByText(oldTicket!)).toHaveCount(0);
    await second.getByRole('button', { name: 'Проверить текущий статус' }).click();
    await expect(second.getByText('Регистрация подтверждена')).toBeVisible();
    await second.reload();
    const promotedTicket = await second.getByText(ticketPattern).textContent();
    expect(promotedTicket).not.toBe(oldTicket);
    await first.getByRole('link', { name: 'My registrations meetup' }).click();
    await first.getByRole('button', { name: 'Зарегистрироваться' }).click();
    await expect(first.getByText('Место в очереди: 1')).toBeVisible();
    await first.goto('/');
    await first.getByRole('button', { name: 'Выйти' }).click();
    await expect(first.getByRole('heading', { name: 'Войти' })).toBeVisible();
    await first.goto('/me/registrations');
    await expect(first.getByRole('heading', { name: 'Войти' })).toBeVisible();
    await login(first, secondEmail);
    await first.getByRole('link', { name: 'Мои регистрации' }).click();
    await expect(first.getByText(promotedTicket!)).toBeVisible();
    await expect(first.getByText('Место в очереди: 1')).toHaveCount(0);
    await expect(first.getByText(oldTicket!)).toHaveCount(0);
  } finally { await a.close(); await b.close(); }
});
