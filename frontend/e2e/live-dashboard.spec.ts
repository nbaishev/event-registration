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

test('live-dashboard: registration, cancellation/promotion, capacity and check-in update without reload', async ({ page, browser, baseURL }) => {
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
  await expect(page.getByText('Обновляется в реальном времени')).toBeVisible();
  let navigations = 0;
  page.on('framenavigated', frame => { if (frame === page.mainFrame()) navigations++; });
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
    await counts(page, 1, 1, 1, 0, 0);
    await first.getByRole('button', { name: 'Отменить регистрацию' }).click();
    await expect(first.getByText('Регистрация отменена')).toBeVisible();
    await counts(page, 1, 1, 0, 0, 0);
    await second.reload();
    await expect(second.getByText('Регистрация подтверждена')).toBeVisible();
    const ticket = await second.getByText(/^[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{4}-[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{4}-[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{4}$/).textContent();
    const currentCsrf = (await page.context().cookies()).find(cookie => cookie.name === 'csrf_token')!;
    const capacity = await page.request.patch(`/api/events/${event.id}`, { headers: { ...headers, 'X-CSRF-Token': currentCsrf.value }, data: { capacity: 3 } });
    expect(capacity.status()).toBe(200);
    await counts(page, 3, 1, 0, 0, 2);
    const checkin = await page.context().newPage();
    try {
      await checkin.goto(`/organizer/events/${event.id}/check-in`);
      await checkin.getByLabel(/^Код билета/).fill(ticket!);
      await checkin.getByRole('button', { name: 'Отметить участника' }).click();
      await expect(checkin.getByText('Участник отмечен', { exact: true })).toBeVisible();
      await counts(page, 3, 1, 0, 1, 2);
      expect(navigations).toBe(0);
      await page.screenshot({ path: '../.verification/live-dashboard-desktop.png', fullPage: true });
      await page.setViewportSize({ width: 390, height: 844 });
      await counts(page, 3, 1, 0, 1, 2);
      await page.screenshot({ path: '../.verification/live-dashboard-mobile.png', fullPage: true });
    } finally { await checkin.close(); }
  } finally { await a.close(); await b.close(); }
});


test('live-dashboard: interrupted stream recovers missed snapshot with missing access; missing refresh returns to login', async ({ page, baseURL }) => {
  await registerAndLogin(page, 'reconnect-owner');
  const token = await (await page.request.get('/api/auth/csrf')).json() as { csrf_token: string };
  const headers = { Origin: new URL(baseURL!).origin, 'X-CSRF-Token': token.csrf_token };
  const created = await page.request.post('/api/events', { headers, data: {
    title: 'Reconnect statistics', description: 'Snapshot recovery', timezone: 'UTC', capacity: 1,
    starts_at: new Date(Date.now() + 3600000).toISOString(), ends_at: new Date(Date.now() + 7200000).toISOString(),
  } });
  expect(created.status()).toBe(201);
  const event = await created.json() as { id: string };
  expect((await page.request.post(`/api/events/${event.id}/publish`, { headers })).status()).toBe(200);
  let connections = 0;
  let interrupt = true;
  await page.route(`**/api/events/${event.id}/stats/stream`, async route => {
    connections++;
    if (interrupt) {
      // Finite SSE response ends the transport deterministically. Recovery must
      // close this EventSource and create another after refresh/validation.
      await route.fulfill({ status: 200, contentType: 'text/event-stream', body: ': heartbeat\n\n' });
    } else await route.continue();
  });
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/auth/refresh', async route => { await held; await route.continue(); });
  await page.goto(`/organizer/events/${event.id}`);
  await counts(page, 1, 0, 0, 0, 1);
  await expect(page.getByText('Восстанавливаем соединение…')).toBeVisible();
  await page.screenshot({ path: '../.verification/live-dashboard-reconnecting.png', fullPage: true });
  // Change data while detached. Use another HTTP client sharing the owner's
  // cookies so the dashboard never receives a mutation invalidation.
  expect((await page.request.patch(`/api/events/${event.id}`, { headers, data: { capacity: 4 } })).status()).toBe(200);
  await page.context().clearCookies({ name: 'access_token' });
  interrupt = false;
  const refreshed = page.waitForResponse(response => response.url().endsWith('/api/auth/refresh'));
  release();
  expect((await refreshed).status()).toBe(200);
  await expect(page.getByText('Обновляется в реальном времени')).toBeVisible();
  await counts(page, 4, 0, 0, 0, 4);
  expect(connections).toBe(2);
  await page.unroute('**/api/auth/refresh');
  // Remount with the same finite transport to force a second interruption.
  // SPA navigation preserves the existing auth/session implementation.
  await page.getByRole('link', { name: 'Мои мероприятия' }).click();
  // Wait for the dashboard to unmount before returning: SPA navigation can
  // still be pending when click() resolves, leaving the old stream alive.
  await expect(page.getByRole('heading', { name: 'Мои мероприятия' })).toBeVisible();
  interrupt = true;
  await page.context().clearCookies({ name: 'refresh_token' });
  const rejected = page.waitForResponse(response => response.url().endsWith('/api/auth/refresh'));
  await page.evaluate(id => {
    window.history.pushState({}, '', `/organizer/events/${id}`);
    window.dispatchEvent(new PopStateEvent('popstate'));
  }, event.id);
  expect((await rejected).status()).toBe(401);
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole('heading', { name: 'Войти' })).toBeVisible();
  expect(connections).toBe(3);
});
