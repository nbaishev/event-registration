import { randomUUID } from 'node:crypto';
import { expect, test } from './fixtures';

test('Day 2 create → edit → publish → anonymous, failed refresh and logout public access', async ({ page, browser, baseURL }) => {
  const email = `publish-${randomUUID()}@example.com`, password = 'a long password';
  await page.goto('/register');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Пароль').fill(password);
  await page.getByRole('button', { name: 'Создать аккаунт' }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Пароль').fill(password);
  await page.getByRole('button', { name: 'Войти' }).click();
  await expect(page.getByText(email)).toBeVisible();
  await page.getByRole('link', { name: 'Мои мероприятия' }).click();
  await page.getByRole('link', { name: 'Создать мероприятие' }).click();
  await page.getByLabel('Название').fill('Day 2 meetup');
  await page.getByLabel('Описание').fill('<b>Plain public description</b>');
  await page.getByLabel('Часовой пояс IANA').fill('Asia/Almaty');
  const date = new Date(Date.now() + 2 * 86400000).toISOString().slice(0, 10);
  await page.getByLabel(/^Начало/).fill(`${date}T18:30`);
  await page.getByLabel(/^Окончание/).fill(`${date}T20:30`);
  await page.getByLabel('Количество мест').fill('25');
  const created = page.waitForResponse(r => r.request().method() === 'POST' && r.url().endsWith('/api/events'));
  await page.getByRole('button', { name: 'Создать черновик' }).click();
  const event = await (await created).json() as { id: string; slug: string };
  const publicPath = `/events/${event.slug}`;
  const anonymous = await browser.newContext({ baseURL });
  try {
    const visitor = await anonymous.newPage();
    const authCalls: string[] = [];
    visitor.on('request', r => { if (r.url().includes('/api/auth/')) authCalls.push(r.url()); });
    await visitor.goto(publicPath);
    await expect(visitor.getByRole('alert')).toContainText('Мероприятие не найдено');
    await page.getByRole('link', { name: 'Редактировать черновик' }).click();
    await page.getByLabel('Название').fill('Day 2 published meetup');
    await page.getByRole('button', { name: 'Сохранить изменения' }).click();
    await expect(page.getByRole('heading', { name: 'Day 2 published meetup' })).toBeVisible();
    const published = page.waitForResponse(r => r.url().endsWith(`/api/events/${event.id}/publish`));
    await page.getByRole('button', { name: 'Опубликовать' }).click();
    expect((await published).status()).toBe(200);
    await expect(page.getByRole('link', { name: 'Открыть публичную страницу' })).toHaveAttribute('href', publicPath);
    await page.screenshot({ path: '../.verification/event-published-owner.png', fullPage: true });
    await visitor.reload();
    await expect(visitor.getByRole('heading', { name: 'Day 2 published meetup' })).toBeVisible();
    await expect(visitor.getByText('<b>Plain public description</b>')).toBeVisible();
    await expect(visitor.locator('b')).toHaveCount(0);
    await expect(visitor.getByText(/18:30/)).toBeVisible();
    await expect(visitor.getByText('Количество мест: 25')).toBeVisible();
    await visitor.screenshot({ path: '../.verification/event-public.png', fullPage: true });
    await visitor.reload();
    await expect(visitor.getByText('Опубликовано')).toBeVisible();
    expect(authCalls.filter(url => !/\/api\/auth\/(me|csrf|refresh)$/.test(url))).toEqual([]);
  } finally { await anonymous.close(); }

  // Invalid access and refresh cookies exercise terminal recovery against the real server.
  for (const cookie of await page.context().cookies()) {
    if (['access_token', 'refresh_token'].includes(cookie.name)) await page.context().addCookies([{ ...cookie, value: 'invalid-test-token' }]);
  }
  const failed = page.waitForResponse(r => r.url().endsWith('/api/auth/refresh'));
  await page.evaluate(() => window.dispatchEvent(new Event('visibilitychange')));
  expect((await failed).status()).toBe(401);
  await expect(page).toHaveURL(/\/login$/);
  let authRequests = 0;
  page.on('request', r => { if (r.url().includes('/api/auth/')) authRequests++; });
  const navigate = async (path: string) => page.evaluate(p => { history.pushState({}, '', p); window.dispatchEvent(new PopStateEvent('popstate')); }, path);
  await navigate(publicPath);
  await expect(page.getByRole('heading', { name: 'Day 2 published meetup' })).toBeVisible();
  expect(authRequests).toBe(0);
  await navigate('/login');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Пароль').fill(password);
  await page.getByRole('button', { name: 'Войти' }).click();
  await expect(page.getByText(email)).toBeVisible();
  await page.getByRole('button', { name: 'Выйти' }).click();
  await expect(page).toHaveURL(/\/login$/);
  authRequests = 0;
  await navigate(publicPath);
  await expect(page.getByRole('heading', { name: 'Day 2 published meetup' })).toBeVisible();
  expect(authRequests).toBe(0);
});
