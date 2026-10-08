import { randomUUID } from 'node:crypto';
import { expect, test, type BrowserContext } from './fixtures';

async function account(context: BrowserContext) {
  const email = `reschedule-${randomUUID()}@example.com`;
  const request = context.request;
  const csrf = (await (await request.get('/api/auth/csrf')).json()).csrf_token as string;
  const headers = { Origin: new URL(process.env.E2E_BASE_URL!).origin, 'X-CSRF-Token': csrf };
  expect((await request.post('/api/auth/register', { headers, data: { email, password: 'a long password' } })).status()).toBe(201);
  expect((await request.post('/api/auth/login', { headers, data: { email, password: 'a long password' } })).status()).toBe(200);
  return { email, headers };
}

test('event-reschedule: organizer changes schedule, public page and SMTP use committed snapshot', async ({ page, context, browser, baseURL, request }) => {
  const owner = await account(context);
  const start = new Date(Date.now() + 3 * 86400000);
  start.setUTCSeconds(37, 0);
  const created = await context.request.post('/api/events', { headers: owner.headers, data: {
    title: 'Перенос конференции', description: 'Новое расписание для участников', timezone: 'UTC', capacity: 1,
    starts_at: start.toISOString(), ends_at: new Date(start.getTime() + 7200000).toISOString(),
  } });
  expect(created.status()).toBe(201);
  const event = await created.json() as { id: string; slug: string };
  expect((await context.request.post(`/api/events/${event.id}/publish`, { headers: owner.headers })).status()).toBe(200);
  const guestContext = await browser.newContext({ baseURL });
  try {
    const guest = await account(guestContext);
    expect((await guestContext.request.post(`/api/events/${event.id}/registrations`, { headers: guest.headers })).status()).toBe(201);
    await page.goto(`/organizer/events/${event.id}`);
    await expect(page.getByRole('heading', { name: 'Изменить расписание' })).toBeVisible();
    await page.screenshot({ path: '../.verification/event-reschedule-form.png', fullPage: true });
    const newStart = new Date(start.getTime() + 86400000).toISOString();
    const newEnd = new Date(start.getTime() + 86400000 + 7200000).toISOString();
    await page.getByLabel('Начало', { exact: true }).fill(newStart.slice(0, 16));
    await page.getByLabel('Окончание', { exact: true }).fill(newEnd.slice(0, 16));
    const patch = page.waitForResponse(r => r.request().method() === 'PATCH');
    await page.getByRole('button', { name: 'Сохранить расписание' }).click();
    const response = await patch;
    expect(response.status()).toBe(200);
    expect(response.request().postDataJSON()).toEqual({ starts_at: newStart, ends_at: newEnd });
    await expect(page.getByRole('button', { name: 'Сохранить расписание' })).toBeDisabled();
    await page.reload();
    await expect(page.getByLabel('Начало', { exact: true })).toHaveValue(newStart.slice(0, 16));
    await page.screenshot({ path: '../.verification/event-reschedule-saved.png', fullPage: true });
    const publicPage = await guestContext.newPage();
    await publicPage.goto(`/events/${event.slug}`);
    await expect(publicPage.getByText('Регистрация подтверждена')).toBeVisible();
    const publicEvent = await (await guestContext.request.get(`/api/public/events/${event.slug}`)).json();
    expect(Date.parse(publicEvent.starts_at)).toBe(Date.parse(newStart));
    expect(Date.parse(publicEvent.ends_at)).toBe(Date.parse(newEnd));
    const expected = newStart.slice(0, 16).replace('T', ' ');
    await expect.poll(async () => {
      const messages = await (await request.get(`${process.env.MAILPIT_URL}/api/v1/messages`)).json() as { messages: { ID: string; Subject: string; To: { Address: string }[] }[] };
      for (const item of messages.messages) {
        if (item.Subject === 'Изменение расписания мероприятия' && item.To.some(to => to.Address === guest.email)) {
          const mail = await (await request.get(`${process.env.MAILPIT_URL}/api/v1/message/${item.ID}`)).json() as { Text: string };
          return mail.Text.includes(expected) && mail.Text.includes(`/events/${event.slug}`);
        }
      }
      return false;
    }, { timeout: 15000 }).toBe(true);
  } finally { await guestContext.close(); }
});
