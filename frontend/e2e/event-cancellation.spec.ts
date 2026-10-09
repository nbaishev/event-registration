import { randomUUID } from 'node:crypto';
import { expect, test, type BrowserContext } from './fixtures';

async function account(context: BrowserContext) {
  const email = `cancel-${randomUUID()}@example.com`;
  const csrf = (await (await context.request.get('/api/auth/csrf')).json()).csrf_token as string;
  const headers = { Origin: new URL(process.env.E2E_BASE_URL!).origin, 'X-CSRF-Token': csrf };
  expect((await context.request.post('/api/auth/register', { headers, data: { email, password: 'a long password' } })).status()).toBe(201);
  expect((await context.request.post('/api/auth/login', { headers, data: { email, password: 'a long password' } })).status()).toBe(200);
  return { email, headers };
}

test('event-cancellation: owner cancels, public status and active recipients receive SMTP notices', async ({ page, context, browser, baseURL, request }) => {
  const owner = await account(context);
  const starts = new Date(Date.now() + 3600000).toISOString();
  const created = await context.request.post('/api/events', { headers: owner.headers, data: {
    title: 'Отмена конференции', description: 'Мероприятие для участников', timezone: 'UTC', capacity: 1,
    starts_at: starts, ends_at: new Date(Date.now() + 10800000).toISOString(),
  } });
  expect(created.status()).toBe(201);
  const event = await created.json() as { id: string; slug: string };
  expect((await context.request.post(`/api/events/${event.id}/publish`, { headers: owner.headers })).status()).toBe(200);
  const confirmedContext = await browser.newContext({ baseURL });
  const waitingContext = await browser.newContext({ baseURL });
  try {
    const confirmed = await account(confirmedContext);
    const waiting = await account(waitingContext);
    const registration = await confirmedContext.request.post(`/api/events/${event.id}/registrations`, { headers: confirmed.headers });
    expect(registration.status()).toBe(201);
    const ticket = (await registration.json()).ticket_code as string;
    const waitlist = await waitingContext.request.post(`/api/events/${event.id}/registrations`, { headers: waiting.headers });
    expect(waitlist.status()).toBe(201);
    expect((await waitlist.json()).status).toBe('WAITLIST');
    await page.goto(`/organizer/events/${event.id}`);
    await page.getByRole('button', { name: 'Отменить мероприятие', exact: true }).click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await page.screenshot({ path: '../.verification/event-cancellation-dialog.png', animations: 'disabled' });
    const cancellation = page.waitForResponse(r => r.url().endsWith(`/api/events/${event.id}/cancel`) && r.request().method() === 'POST');
    await page.getByRole('button', { name: 'Подтвердить отмену' }).click();
    expect((await cancellation).status()).toBe(200);
    await expect(page.getByText('Отменено', { exact: true })).toBeVisible();
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await expect(page.getByRole('link', { name: 'Check-in' })).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'Изменить расписание' })).toHaveCount(0);
    await page.screenshot({ path: '../.verification/event-cancellation-saved.png', fullPage: true, animations: 'disabled' });
    const publicPage = await confirmedContext.newPage();
    await publicPage.goto(`/events/${event.slug}`);
    await publicPage.reload();
    await expect(publicPage.getByText('Отменено', { exact: true })).toBeVisible();
    await expect(publicPage.getByRole('button', { name: 'Зарегистрироваться', exact: true })).toHaveCount(0);
    const publicEvent = await (await request.get(`/api/public/events/${event.slug}`)).json();
    expect(publicEvent.status).toBe('CANCELLED');
    expect(Date.parse(publicEvent.starts_at)).toBe(Date.parse(starts));
    const rejected = await waitingContext.request.post(`/api/events/${event.id}/registrations`, { headers: waiting.headers });
    expect(rejected.status()).toBe(409);
    expect((await rejected.json()).error.code).toBe('EVENT_CANCELLED');
    // The browser mutation bootstrapped CSRF and replaced this context's cookie.
    const ownerHeaders = { ...owner.headers, 'X-CSRF-Token': (await (await context.request.get('/api/auth/csrf')).json()).csrf_token as string };
    const checkin = await context.request.post(`/api/events/${event.id}/check-ins`, { headers: ownerHeaders, data: { ticket_code: ticket } });
    expect(checkin.status()).toBe(409);
    expect((await checkin.json()).error.code).toBe('EVENT_CANCELLED');
    const repeat = await context.request.post(`/api/events/${event.id}/cancel`, { headers: ownerHeaders });
    expect(repeat.status()).toBe(409);
    const expected = starts.slice(0, 16).replace('T', ' ');
    await expect.poll(async () => {
      const messages = await (await request.get(`${process.env.MAILPIT_URL}/api/v1/messages`)).json() as { messages: { ID: string; Subject: string; To: { Address: string }[] }[] };
      const recipients = new Set<string>();
      for (const item of messages.messages) {
        if (item.Subject !== 'Мероприятие отменено') continue;
        for (const recipient of [confirmed.email, waiting.email]) {
          if (!item.To.some(to => to.Address === recipient)) continue;
          const mail = await (await request.get(`${process.env.MAILPIT_URL}/api/v1/message/${item.ID}`)).json() as { Text: string; HTML: string };
          if (mail.Text.includes(expected) && mail.Text.includes(`/events/${event.slug}`) && mail.Text.includes('Отмена конференции') && mail.HTML === '') recipients.add(recipient);
        }
      }
      return recipients.size;
    }, { timeout: 15000 }).toBe(2);
  } finally {
    await confirmedContext.close();
    await waitingContext.close();
  }
});
