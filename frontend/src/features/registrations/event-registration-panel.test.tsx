import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
let App: typeof import('../../app')['App'];
beforeEach(async () => { vi.resetModules(); App = (await import('../../app')).App; });
afterEach(() => vi.unstubAllGlobals());
const user = { id: '00000000-0000-4000-8000-000000000001', email: 'participant@example.com', created_at: '2026-10-04T12:00:00Z', updated_at: '2026-10-04T12:00:00Z' };
const event = { id: '00000000-0000-4000-8000-000000000002', title: 'Public meetup', description: 'Public content', slug: 'meetup', starts_at: '2099-10-10T12:00:00Z', ends_at: '2099-10-10T14:00:00Z', timezone: 'UTC', capacity: 1, status: 'PUBLISHED' };
const confirmed = { id: '00000000-0000-4000-8000-000000000003', event_id: event.id, user_id: user.id, status: 'CONFIRMED', confirmed_at: user.created_at, waitlisted_at: null, cancelled_at: null, waitlist_position: null, ticket_code: '7K4P-9Q2M-8RTA', checked_in_at: null };
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const error = (code: string, status: number) => json({ error: { code, message: 'diagnostic', details: {} } }, status);
function setup(handler: (input: RequestInfo | URL, options?: RequestInit) => Response | Promise<Response>, session: Response = json(user)) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  window.history.replaceState({}, '', '/events/meetup');
  vi.stubGlobal('fetch', vi.fn<typeof fetch>(async (input, options) => {
    if (input === '/api/auth/me') return session.clone();
    if (input === '/api/auth/csrf') return json({ csrf_token: 'test-token' });
    if (input === '/api/public/events/meetup') return json(event);
    return handler(input, options);
  }));
  render(<App client={client} />);
  return client;
}
it('registers once and persists the returned ticket without hiding public content', async () => {
  let posts = 0;
  setup((input, options) => {
    if (String(input).endsWith('/my-registration')) return error('REGISTRATION_NOT_FOUND', 404);
    if (options?.method === 'POST') { posts++; return json(confirmed, 201); }
    throw new Error('unexpected request');
  });
  fireEvent.click(await screen.findByRole('button', { name: 'Зарегистрироваться' }));
  expect(await screen.findByText('7K4P-9Q2M-8RTA')).toBeVisible();
  expect(screen.getByText('Public content')).toBeVisible();
  expect(posts).toBe(1);
  expect(screen.queryByRole('button', { name: 'Зарегистрироваться' })).toBeNull();
});
it('shows the saved waitlist position', async () => {
  setup(() => json({ ...confirmed, status: 'WAITLIST', confirmed_at: null, waitlisted_at: user.created_at, ticket_code: null, waitlist_position: 2 }));
  expect(await screen.findByText('Место в очереди: 2')).toBeVisible();
});
it('refetches own state after an already registered response', async () => {
  let reads = 0;
  setup((input, options) => {
    if (String(input).endsWith('/my-registration')) return ++reads === 1 ? error('REGISTRATION_NOT_FOUND', 404) : json(confirmed);
    if (options?.method === 'POST') return error('ALREADY_REGISTERED', 409);
    throw new Error('unexpected');
  });
  fireEvent.click(await screen.findByRole('button', { name: 'Зарегистрироваться' }));
  expect(await screen.findByText('7K4P-9Q2M-8RTA')).toBeVisible();
});
it('keeps public content during own loading and errors', async () => {
  let resolve!: (value: Response) => void;
  const promise = new Promise<Response>(r => { resolve = r; });
  setup(() => promise);
  expect(await screen.findByText('Public content')).toBeVisible();
  expect(await screen.findByText('Загружаем регистрацию…')).toBeVisible();
  await act(async () => resolve(error('SERVICE_UNAVAILABLE', 503)));
  expect(await screen.findByText('Не удалось загрузить регистрацию')).toBeVisible();
  expect(screen.getByText('Public content')).toBeVisible();
});
it('stays public after failed refresh and offers explicit login', async () => {
  setup(() => error('AUTH_REFRESH_INVALID', 401), error('AUTH_REQUIRED', 401));
  expect(await screen.findByRole('link', { name: 'Войти для регистрации' })).toBeVisible();
  expect(screen.getByText('Public content')).toBeVisible();
  expect(window.location.pathname).toBe('/events/meetup');
});
it('a delayed own GET cannot replace registration success', async () => {
  let resolve!: (value: Response) => void;
  let reads = 0;
  const delayed = new Promise<Response>(r => { resolve = r; });
  const client = setup((input, options) => {
    if (String(input).endsWith('/my-registration')) return ++reads === 1 ? error('REGISTRATION_NOT_FOUND', 404) : delayed;
    if (options?.method === 'POST') return json(confirmed, 201);
    throw new Error('unexpected');
  });
  await screen.findByRole('button', { name: 'Зарегистрироваться' });
  void client.invalidateQueries({ queryKey: ['registrations', user.id, 'detail', event.id] });
  await waitFor(() => expect(reads).toBe(2));
  fireEvent.click(screen.getByRole('button', { name: 'Зарегистрироваться' }));
  expect(await screen.findByText('7K4P-9Q2M-8RTA')).toBeVisible();
  await act(async () => resolve(error('REGISTRATION_NOT_FOUND', 404)));
  expect(screen.getByText('7K4P-9Q2M-8RTA')).toBeVisible();
});
it('does not automatically retry uncertain registration failures', async () => {
  let posts = 0;
  setup((input, options) => {
    if (String(input).endsWith('/my-registration')) return error('REGISTRATION_NOT_FOUND', 404);
    if (options?.method === 'POST') { posts++; throw new TypeError('network lost'); }
    throw new Error('unexpected');
  });
  fireEvent.click(await screen.findByRole('button', { name: 'Зарегистрироваться' }));
  expect(await screen.findByText(/Не удалось зарегистрироваться/)).toBeVisible();
  expect(posts).toBe(1);
});
