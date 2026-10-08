import { randomUUID } from 'node:crypto';
import { expect, test, type Page } from './fixtures';

async function account(page: Page) {
  const email = `sse-${randomUUID()}@example.com`;
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

type StreamWindow = Window & {
  statsStream?: { abort: AbortController; frame: Promise<string>; reader: ReadableStreamDefaultReader<Uint8Array> };
};

test('stats-stream: committed frame arrives through Nginx before disconnect; wrong owner rejected', async ({ page, browser, baseURL }) => {
  await account(page);
  const token = await (await page.request.get('/api/auth/csrf')).json() as { csrf_token: string };
  const headers = { Origin: new URL(baseURL!).origin, 'X-CSRF-Token': token.csrf_token };
  const created = await page.request.post('/api/events', { headers, data: {
    title: 'SSE transport', description: 'Committed statistics notifications', timezone: 'UTC', capacity: 1,
    starts_at: new Date(Date.now() + 3600000).toISOString(), ends_at: new Date(Date.now() + 7200000).toISOString(),
  } });
  expect(created.status()).toBe(201);
  const event = await created.json() as { id: string };
  expect((await page.request.post(`/api/events/${event.id}/publish`, { headers })).status()).toBe(200);
  const other = await browser.newContext({ baseURL });
  try {
    const outsider = await other.newPage();
    await account(outsider);
    const rejection = await outsider.evaluate(async id => {
      const response = await fetch(`/api/events/${id}/stats/stream`, { credentials: 'same-origin' });
      return { status: response.status, body: await response.json() as { error: { code: string } } };
    }, event.id);
    expect(rejection.status).toBe(403);
    expect(rejection.body.error.code).toBe('EVENT_NOT_OWNER');
    const responseHeaders = await page.evaluate(async id => {
      const abort = new AbortController();
      const response = await fetch(`/api/events/${id}/stats/stream`, { credentials: 'same-origin', signal: abort.signal });
      if (!response.body || response.status !== 200) { abort.abort(); throw new Error(`Stream status ${response.status}`); }
      const reader = response.body.getReader();
      const frame = (async () => {
        const decoder = new TextDecoder();
        let text = '';
        for (;;) {
          const chunk = await reader.read();
          if (chunk.done) throw new Error('Stream closed before signal');
          text += decoder.decode(chunk.value, { stream: true });
          if (text.includes('event: stats_changed\ndata: {}\n\n')) return text;
        }
      })();
      // Ensure a read failure is handled even if the mutation itself fails.
      void frame.catch(() => undefined);
      (window as StreamWindow).statsStream = { abort, frame, reader };
      return { type: response.headers.get('content-type'), cache: response.headers.get('cache-control') };
    }, event.id);
    expect(responseHeaders.type).toContain('text/event-stream');
    expect(responseHeaders.cache).toBe('no-store');
    expect((await page.request.patch(`/api/events/${event.id}`, { headers, data: { capacity: 2 } })).status()).toBe(200);
    const received = await page.evaluate(async () => {
      const stream = (window as StreamWindow).statsStream!;
      const timer = setTimeout(() => stream.abort.abort(), 5000);
      try { return { frame: await stream.frame, open: !stream.abort.signal.aborted }; }
      finally { clearTimeout(timer); }
    });
    expect(received).toEqual({ frame: 'event: stats_changed\ndata: {}\n\n', open: true });
    const snapshot = await (await page.request.get(`/api/events/${event.id}/stats`)).json() as { capacity: number };
    expect(snapshot.capacity).toBe(2);
  } finally {
    await page.evaluate(async () => {
      const stream = (window as StreamWindow).statsStream;
      if (stream) { stream.abort.abort(); await stream.reader.cancel().catch(() => undefined); delete (window as StreamWindow).statsStream; }
    });
    await other.close();
  }
});
